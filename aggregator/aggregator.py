"""
World Twin Aggregator
=====================
Background service that fetches data from all upstream APIs on scheduled
intervals and caches them as JSON files in /cache. The frontend fetches
ONE URL per layer instead of hammering 30+ APIs directly from the browser.

Architecture:
    - Async background tasks for each data source (different intervals)
    - Writes atomic JSON files to /cache/<layer>.json
    - FastAPI serves /api/<layer> endpoints reading from cache
    - /api/health returns status of all layers
    - /api/_stats returns aggregator stats (last fetch, errors, etc.)

The cache files are also mounted into Caddy at /srv/cache so Caddy can
serve them directly with zero backend CPU cost.
"""

import asyncio
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

WINDY_KEY = os.environ.get("WINDY_KEY", "REDACTED_WINDY_KEY")
FIRMS_KEY = os.environ.get("FIRMS_KEY", "REDACTED_FIRMS_KEY")
WEATHER_KEY = os.environ.get("WEATHER_KEY", "REDACTED_WEATHERAPI_KEY")
OWM_KEY = os.environ.get("OWM_KEY", "REDACTED_OWM_KEY")

# Global stats
stats: dict[str, dict[str, Any]] = {}

app = FastAPI(title="World Twin Aggregator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def write_cache(layer: str, data: Any) -> None:
    """Atomic write: write to .tmp then rename."""
    path = CACHE_DIR / f"{layer}.json"
    tmp = CACHE_DIR / f"{layer}.json.tmp"
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)

def mark(layer: str, ok: bool, count: int | None = None, error: str | None = None) -> None:
    stats[layer] = {
        "ok": ok,
        "count": count,
        "error": error,
        "last_fetch": datetime.now(timezone.utc).isoformat(),
    }

# ---------------------------------------------------------------------------
# Individual worker functions
# ---------------------------------------------------------------------------

async def fetch_quakes(client: httpx.AsyncClient) -> None:
    """USGS earthquakes (past day, M2.5+) — free, no key."""
    try:
        r = await client.get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        write_cache("quakes", data)
        mark("quakes", True, len(data.get("features", [])))
    except Exception as e:
        mark("quakes", False, error=str(e))

async def fetch_fires(client: httpx.AsyncClient) -> None:
    """NASA FIRMS VIIRS fires — CSV format, we convert to simplified JSON."""
    try:
        r = await client.get(
            f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/VIIRS_SNPP_NRT/world/1",
            timeout=60,
        )
        r.raise_for_status()
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            raise ValueError("No fire data")
        header = lines[0].split(",")
        idx = {name: i for i, name in enumerate(header)}
        # Sample down — we don't need all 21k fires
        step = max(1, len(lines) // 2000)
        fires: list[dict[str, Any]] = []
        for i in range(1, len(lines), step):
            cols = lines[i].split(",")
            if len(cols) < len(header):
                continue
            try:
                fires.append({
                    "lat": float(cols[idx.get("latitude", 0)]),
                    "lon": float(cols[idx.get("longitude", 1)]),
                    "bright": float(cols[idx.get("bright_ti4", 2)]) if idx.get("bright_ti4") is not None else 0,
                    "date": cols[idx.get("acq_date", 5)] if idx.get("acq_date") is not None else "",
                    "time": cols[idx.get("acq_time", 6)] if idx.get("acq_time") is not None else "",
                    "sat": cols[idx.get("satellite", 7)] if idx.get("satellite") is not None else "",
                    "conf": cols[idx.get("confidence", 9)] if idx.get("confidence") is not None else "",
                    "frp": float(cols[idx.get("frp", 12)]) if idx.get("frp") is not None and cols[idx.get("frp", 12)] else 0,
                    "dn": cols[idx.get("daynight", 13)] if idx.get("daynight") is not None else "",
                })
            except (ValueError, IndexError):
                continue
        write_cache("fires", fires)
        mark("fires", True, len(fires))
    except Exception as e:
        mark("fires", False, error=str(e))

async def fetch_flights(client: httpx.AsyncClient) -> None:
    """OpenSky Network — aircraft positions.
    Anonymous users get 400 credits/day; we fetch every 2 min = 720/day.
    Respect 429 by backing off and keeping stale data."""
    try:
        r = await client.get("https://opensky-network.org/api/states/all", timeout=30)
        if r.status_code == 429:
            # Don't overwrite existing cache
            mark("flights", False, error="429 rate limited — keeping last cache")
            return
        r.raise_for_status()
        data = r.json()
        states = data.get("states") or []
        step = max(1, len(states) // 600)
        sampled = states[::step]
        write_cache("flights", {"time": data.get("time"), "states": sampled})
        mark("flights", True, len(sampled))
    except Exception as e:
        mark("flights", False, error=str(e))

async def fetch_iss(client: httpx.AsyncClient) -> None:
    """ISS position — every 10s."""
    try:
        r = await client.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=15)
        r.raise_for_status()
        iss = r.json()
        # Also fetch crew
        crew_list: list[dict[str, Any]] = []
        try:
            r2 = await client.get("http://api.open-notify.org/astros.json", timeout=15)
            if r2.status_code == 200:
                crew = r2.json()
                crew_list = [p for p in crew.get("people", []) if p.get("craft") == "ISS"]
        except Exception:
            pass
        write_cache("iss", {"iss": iss, "crew": crew_list})
        mark("iss", True, 1)
    except Exception as e:
        mark("iss", False, error=str(e))

async def fetch_disasters(client: httpx.AsyncClient) -> None:
    """NASA EONET disasters — retries with backoff on 503."""
    for attempt in range(3):
        try:
            r = await client.get(
                "https://eonet.gsfc.nasa.gov/api/v3/events",
                params={"status": "open", "limit": 200},
                timeout=30,
            )
            if r.status_code == 503:
                retry_after = 0
                try:
                    retry_after = int(r.json().get("retry_after", 15))
                except Exception:
                    retry_after = 15
                await asyncio.sleep(retry_after + 1)
                continue
            r.raise_for_status()
            data = r.json()
            write_cache("disasters", data)
            mark("disasters", True, len(data.get("events", [])))
            return
        except Exception as e:
            if attempt == 2:
                mark("disasters", False, error=str(e))
                return
            await asyncio.sleep(10)

async def fetch_crises(client: httpx.AsyncClient) -> None:
    """ReliefWeb v1 is decommissioned and v2 blocks all non-approved appnames
    since November 2025. Fall back to HDX (Humanitarian Data Exchange)
    CKAN API which exposes crisis data without auth."""
    try:
        # HDX (Humanitarian Data Exchange) — open CKAN API
        r = await client.get(
            "https://data.humdata.org/api/3/action/package_search",
            params={
                "q": "crisis OR disaster OR emergency",
                "fq": "res_format:(GeoJSON OR JSON)",
                "rows": 50,
                "sort": "metadata_modified desc",
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("result", {}).get("results", [])
            # Simplify to lat/lon + name list if possible
            crises = []
            for pkg in results:
                crises.append({
                    "name": pkg.get("title", ""),
                    "country": (pkg.get("groups") or [{}])[0].get("title", ""),
                    "description": (pkg.get("notes") or "")[:300],
                    "date": pkg.get("metadata_modified", ""),
                    "url": f"https://data.humdata.org/dataset/{pkg.get('name','')}",
                })
            write_cache("crises", {"data": crises, "source": "HDX"})
            mark("crises", True, len(crises))
            return
    except Exception:
        pass
    # Fallback 2: derive from EONET disasters if available
    eonet_path = CACHE_DIR / "disasters.json"
    if eonet_path.exists():
        try:
            with eonet_path.open() as f:
                eonet = json.load(f)
            crises = []
            for ev in eonet.get("events", []):
                if ev.get("categories"):
                    cat = ev["categories"][0].get("title", "")
                    geo = ev.get("geometry", [])
                    if geo and geo[-1].get("coordinates"):
                        crises.append({
                            "name": ev.get("title", ""),
                            "type": cat,
                            "date": geo[-1].get("date", ""),
                            "coordinates": geo[-1]["coordinates"],
                            "url": (ev.get("sources") or [{}])[0].get("url", ""),
                        })
            write_cache("crises", {"data": crises, "source": "EONET-derived"})
            mark("crises", True, len(crises))
            return
        except Exception as e:
            pass
    mark("crises", False, error="All crisis sources unavailable")

async def fetch_volcanoes(client: httpx.AsyncClient) -> None:
    """Smithsonian GVP volcanoes — slow changing, fetch once per day."""
    try:
        # Smithsonian WFS is the authoritative source
        r = await client.get(
            "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs",
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes",
                "outputFormat": "application/json",
            },
            timeout=60,
        )
        r.raise_for_status()
        write_cache("volcanoes", r.json())
        mark("volcanoes", True, len(r.json().get("features", [])))
    except Exception as e:
        # Fallback to USGS VHP
        try:
            r = await client.get(
                "https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcanoesGVP",
                timeout=60,
            )
            r.raise_for_status()
            write_cache("volcanoes", r.json())
            mark("volcanoes", True, -1)
        except Exception as e2:
            mark("volcanoes", False, error=f"primary:{e} fallback:{e2}")

async def fetch_cables(client: httpx.AsyncClient) -> None:
    """Submarine cables GeoJSON — rarely changes, fetch once per day."""
    try:
        r = await client.get(
            "https://www.submarinecablemap.com/api/v3/cable/cable-geo.json",
            timeout=60,
        )
        r.raise_for_status()
        write_cache("cables", r.json())
        mark("cables", True, len(r.json().get("features", [])))
    except Exception as e:
        mark("cables", False, error=str(e))

async def fetch_radio(client: httpx.AsyncClient) -> None:
    """Radio Browser — top stations with geo info."""
    try:
        # Try multiple servers for reliability
        servers = [
            "https://de1.api.radio-browser.info",
            "https://nl1.api.radio-browser.info",
            "https://at1.api.radio-browser.info",
        ]
        for server in servers:
            try:
                r = await client.get(
                    f"{server}/json/stations/search",
                    params={
                        "limit": 500,
                        "offset": 0,
                        "order": "clickcount",
                        "reverse": "true",
                        "has_geo_info": "true",
                    },
                    headers={"User-Agent": "WorldTwin/1.0"},
                    timeout=30,
                )
                r.raise_for_status()
                # Filter to stations that actually have lat/lon
                stations = [s for s in r.json() if s.get("geo_lat") and s.get("geo_long")]
                write_cache("radio", stations)
                mark("radio", True, len(stations))
                return
            except Exception:
                continue
        raise RuntimeError("All Radio Browser servers failed")
    except Exception as e:
        mark("radio", False, error=str(e))

async def fetch_satellites(client: httpx.AsyncClient) -> None:
    """CelesTrak TLE data for major satellite groups."""
    groups = [
        ("stations", 0),
        ("visual", 100),
        ("gps-ops", 100),
        ("geo", 100),
        ("starlink", 200),  # was failing 403 from browser; from server it works
    ]
    all_sats: list[dict[str, Any]] = []
    for group, limit in groups:
        try:
            r = await client.get(
                f"https://celestrak.org/NORAD/elements/gp.php",
                params={"GROUP": group, "FORMAT": "json"},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            # CelesTrak returns text error pages when rate-limited
            try:
                sats = r.json()
            except json.JSONDecodeError:
                continue
            if not isinstance(sats, list):
                continue
            if limit and len(sats) > limit:
                # Sample evenly
                step = max(1, len(sats) // limit)
                sats = sats[::step]
            for s in sats:
                s["_group"] = group
            all_sats.extend(sats)
        except Exception:
            continue
    if all_sats:
        write_cache("satellites", all_sats)
        mark("satellites", True, len(all_sats))
    else:
        mark("satellites", False, error="No satellites fetched from any group")

async def fetch_conflicts(client: httpx.AsyncClient) -> None:
    """GDELT doc API for conflict news — GDELT requires 5s between requests.
    We add a 10s safety sleep BEFORE to guarantee gap from any previous call."""
    await asyncio.sleep(10)
    try:
        r = await client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "conflict war military attack",
                "mode": "artlist",
                "format": "json",
                "maxrecords": 150,
                "sort": "datedesc",
            },
            timeout=30,
        )
        if r.status_code == 429:
            mark("conflicts", False, error="429 rate limited — keeping cache")
            return
        r.raise_for_status()
        try:
            data = r.json()
            write_cache("conflicts", data)
            mark("conflicts", True, len(data.get("articles", [])))
        except json.JSONDecodeError:
            mark("conflicts", False, error=f"non-json: {r.text[:100]}")
    except Exception as e:
        mark("conflicts", False, error=str(e))

async def fetch_news(client: httpx.AsyncClient) -> None:
    """GDELT doc API for general breaking news.
    Guaranteed 10s gap from the conflicts fetch."""
    await asyncio.sleep(10)
    try:
        r = await client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "breaking news world",
                "mode": "artlist",
                "format": "json",
                "maxrecords": 150,
                "sort": "datedesc",
            },
            timeout=30,
        )
        if r.status_code == 429:
            mark("news", False, error="429 rate limited — keeping cache")
            return
        r.raise_for_status()
        try:
            data = r.json()
            write_cache("news", data)
            mark("news", True, len(data.get("articles", [])))
        except json.JSONDecodeError:
            mark("news", False, error=f"non-json: {r.text[:100]}")
    except Exception as e:
        mark("news", False, error=str(e))

async def fetch_air_quality(client: httpx.AsyncClient) -> None:
    """Open-Meteo AQ for major cities worldwide."""
    cities = [
        ("Beijing", 39.9, 116.4), ("Delhi", 28.6, 77.2), ("Mumbai", 19.1, 72.9),
        ("Shanghai", 31.2, 121.5), ("Dhaka", 23.8, 90.4), ("Cairo", 30.0, 31.2),
        ("Lagos", 6.5, 3.4), ("Istanbul", 41.0, 29.0), ("Karachi", 24.9, 67.0),
        ("Bangkok", 13.8, 100.5), ("Jakarta", -6.2, 106.8), ("Tokyo", 35.7, 139.7),
        ("Seoul", 37.6, 127.0), ("Mexico City", 19.4, -99.1), ("Sao Paulo", -23.5, -46.6),
        ("Moscow", 55.8, 37.6), ("London", 51.5, -0.1), ("Paris", 48.9, 2.3),
        ("Berlin", 52.5, 13.4), ("Madrid", 40.4, -3.7), ("New York", 40.7, -74.0),
        ("Los Angeles", 34.1, -118.2), ("Chicago", 41.9, -87.6), ("Sydney", -33.9, 151.2),
        ("Johannesburg", -26.2, 28.0), ("Cape Town", -33.9, 18.4), ("Nairobi", -1.3, 36.8),
        ("Riyadh", 24.7, 46.7), ("Dubai", 25.2, 55.3), ("Tehran", 35.7, 51.4),
        ("Lahore", 31.5, 74.3), ("Kolkata", 22.6, 88.4), ("Manila", 14.6, 121.0),
        ("Hanoi", 21.0, 105.8), ("Toronto", 43.7, -79.4), ("Singapore", 1.3, 103.8),
        ("Addis Ababa", 9.0, 38.7), ("Kinshasa", -4.3, 15.3), ("Baghdad", 33.3, 44.4),
        ("Kabul", 34.5, 69.2), ("Warsaw", 52.2, 21.0), ("Bucharest", 44.4, 26.1),
        ("Buenos Aires", -34.6, -58.4), ("Lima", -12.0, -77.0), ("Bogota", 4.7, -74.1),
    ]
    results: list[dict[str, Any]] = []
    # Batch requests with concurrency 10
    sem = asyncio.Semaphore(10)
    async def fetch_one(name: str, lat: float, lon: float) -> None:
        async with sem:
            try:
                r = await client.get(
                    "https://air-quality-api.open-meteo.com/v1/air-quality",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide",
                    },
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    cur = data.get("current", {})
                    if cur.get("us_aqi") is not None:
                        results.append({
                            "name": name,
                            "lat": lat,
                            "lon": lon,
                            "aqi": cur.get("us_aqi"),
                            "pm25": cur.get("pm2_5"),
                            "pm10": cur.get("pm10"),
                            "no2": cur.get("nitrogen_dioxide"),
                            "o3": cur.get("ozone"),
                            "so2": cur.get("sulphur_dioxide"),
                            "co": cur.get("carbon_monoxide"),
                        })
            except Exception:
                pass
    try:
        await asyncio.gather(*[fetch_one(n, la, lo) for (n, la, lo) in cities])
        write_cache("air_quality", results)
        mark("air_quality", True, len(results))
    except Exception as e:
        mark("air_quality", False, error=str(e))

async def fetch_population(client: httpx.AsyncClient) -> None:
    """REST Countries — REST Countries v3.1 caps /all at max 10 fields.
    We issue two requests and merge."""
    try:
        # First request: 10 fields
        r1 = await client.get(
            "https://restcountries.com/v3.1/all",
            params={"fields": "name,population,latlng,cca2,cca3,area,region,subregion,capital,flags"},
            timeout=60,
        )
        r1.raise_for_status()
        core = {c.get("cca3"): c for c in r1.json() if c.get("cca3")}
        # Second request: remaining fields
        try:
            r2 = await client.get(
                "https://restcountries.com/v3.1/all",
                params={"fields": "cca3,currencies,languages,tld,idd,timezones"},
                timeout=60,
            )
            if r2.status_code == 200:
                for c in r2.json():
                    cca3 = c.get("cca3")
                    if cca3 and cca3 in core:
                        core[cca3].update({k: v for k, v in c.items() if k != "cca3"})
        except Exception:
            pass
        filtered = [
            c for c in core.values()
            if c.get("population") and c.get("latlng") and len(c["latlng"]) >= 2
        ]
        write_cache("population", filtered)
        mark("population", True, len(filtered))
    except Exception as e:
        mark("population", False, error=str(e))

async def fetch_rainviewer(client: httpx.AsyncClient) -> None:
    """RainViewer radar metadata."""
    try:
        r = await client.get("https://api.rainviewer.com/public/weather-maps.json", timeout=15)
        r.raise_for_status()
        write_cache("rainviewer", r.json())
        mark("rainviewer", True, 1)
    except Exception as e:
        mark("rainviewer", False, error=str(e))

async def fetch_webcams(client: httpx.AsyncClient) -> None:
    """Windy webcams — max 50 per request. Fetch 10 pages = 500 total."""
    all_cams: list[dict[str, Any]] = []
    try:
        for offset in range(0, 500, 50):
            r = await client.get(
                "https://api.windy.com/webcams/api/v3/webcams",
                params={
                    "lang": "en",
                    "limit": 50,
                    "offset": offset,
                    "include": "images,location,player",
                },
                headers={"X-WINDY-API-KEY": WINDY_KEY},
                timeout=30,
            )
            if r.status_code != 200:
                break
            data = r.json()
            cams = data.get("webcams", [])
            if not cams:
                break
            all_cams.extend(cams)
        write_cache("webcams", {"webcams": all_cams, "total": len(all_cams)})
        mark("webcams", True, len(all_cams))
    except Exception as e:
        mark("webcams", False, error=str(e))

# ---------------------------------------------------------------------------
# PHASE 3 WORKERS: Gaming, Sports, Economy, Trends
# ---------------------------------------------------------------------------

async def fetch_gaming(client: httpx.AsyncClient) -> None:
    """Top Steam games by concurrent players + optional Twitch viewers by language."""
    top_appids = [
        (730,    "Counter-Strike 2"),
        (570,    "Dota 2"),
        (578080, "PUBG"),
        (440,    "Team Fortress 2"),
        (271590, "GTA V"),
        (252490, "Rust"),
        (1172470,"Apex Legends"),
        (1086940,"Baldur's Gate 3"),
        (1599340,"Lost Ark"),
        (359550, "Rainbow Six Siege"),
        (238960, "Path of Exile"),
        (236390, "War Thunder"),
        (394360, "Hearts of Iron IV"),
        (892970, "Valheim"),
        (1569040,"Football Manager 2024"),
        (1245620,"ELDEN RING"),
        (2358720,"Black Myth: Wukong"),
        (1091500,"Cyberpunk 2077"),
        (2073850,"THE FINALS"),
        (381210, "Dead by Daylight"),
    ]
    sem = asyncio.Semaphore(5)
    results: list[dict[str, Any]] = []
    async def fetch_one(appid: int, name: str) -> None:
        async with sem:
            try:
                r = await client.get(
                    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
                    params={"appid": appid},
                    timeout=15,
                )
                if r.status_code == 200:
                    data = r.json()
                    players = data.get("response", {}).get("player_count", 0)
                    if players:
                        results.append({
                            "appid": appid,
                            "name": name,
                            "players": players,
                            "store": f"https://store.steampowered.com/app/{appid}/",
                        })
            except Exception:
                pass
    try:
        await asyncio.gather(*[fetch_one(a, n) for a, n in top_appids])
        results.sort(key=lambda x: x["players"], reverse=True)
        total_players = sum(r["players"] for r in results)
        payload: dict[str, Any] = {
            "source": "Steam" + (" + Twitch" if os.environ.get("TWITCH_CLIENT_ID") else ""),
            "fetched": datetime.now(timezone.utc).isoformat(),
            "totalPlayers": total_players,
            "topGames": results,
            "regions": [],
            "totalStreams": 0,
            "totalViewers": 0,
        }
        twitch_id = os.environ.get("TWITCH_CLIENT_ID", "")
        twitch_secret = os.environ.get("TWITCH_CLIENT_SECRET", "")
        if twitch_id and twitch_secret:
            try:
                tok = await client.post(
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": twitch_id,
                        "client_secret": twitch_secret,
                        "grant_type": "client_credentials",
                    },
                    timeout=15,
                )
                if tok.status_code == 200:
                    token = tok.json().get("access_token", "")
                    if token:
                        sr = await client.get(
                            "https://api.twitch.tv/helix/streams",
                            params={"first": 100},
                            headers={
                                "Authorization": f"Bearer {token}",
                                "Client-Id": twitch_id,
                            },
                            timeout=15,
                        )
                        if sr.status_code == 200:
                            streams = sr.json().get("data", [])
                            payload["totalStreams"] = len(streams)
                            payload["totalViewers"] = sum(s.get("viewer_count", 0) for s in streams)
                            by_lang: dict[str, dict[str, Any]] = {}
                            for s in streams:
                                lang = s.get("language", "?")
                                if lang not in by_lang:
                                    by_lang[lang] = {"viewers": 0, "topGame": "", "count": 0}
                                by_lang[lang]["viewers"] += s.get("viewer_count", 0)
                                by_lang[lang]["count"] += 1
                                if not by_lang[lang]["topGame"]:
                                    by_lang[lang]["topGame"] = s.get("game_name", "")
                            lang_geo = {
                                "en": (51.5, -0.1, "English"),
                                "es": (40.4, -3.7, "Spanish"),
                                "pt": (-23.5, -46.6, "Portuguese"),
                                "ko": (37.6, 127.0, "Korean"),
                                "ru": (55.8, 37.6, "Russian"),
                                "de": (52.5, 13.4, "German"),
                                "fr": (48.9, 2.3, "French"),
                                "ja": (35.7, 139.7, "Japanese"),
                                "zh": (31.2, 121.5, "Chinese"),
                                "it": (41.9, 12.5, "Italian"),
                                "pl": (52.2, 21.0, "Polish"),
                                "tr": (41.0, 29.0, "Turkish"),
                                "th": (13.8, 100.5, "Thai"),
                                "ar": (24.7, 46.7, "Arabic"),
                                "nl": (52.4, 4.9, "Dutch"),
                                "sv": (59.3, 18.1, "Swedish"),
                            }
                            regions = []
                            for lang, info in by_lang.items():
                                if lang in lang_geo:
                                    lat, lon, name = lang_geo[lang]
                                    regions.append({
                                        "code": lang,
                                        "name": name,
                                        "lat": lat,
                                        "lon": lon,
                                        "viewers": info["viewers"],
                                        "streams": info["count"],
                                        "topGame": info["topGame"],
                                    })
                            payload["regions"] = sorted(regions, key=lambda r: r["viewers"], reverse=True)
            except Exception:
                pass
        write_cache("gaming", payload)
        mark("gaming", True, len(results))
    except Exception as e:
        mark("gaming", False, error=str(e))


async def fetch_sports(client: httpx.AsyncClient) -> None:
    """Live sports from ESPN's unofficial public API."""
    matches: list[dict[str, Any]] = []
    leagues = [
        ("soccer/eng.1",       "Premier League",  "soccer"),
        ("soccer/esp.1",       "La Liga",         "soccer"),
        ("soccer/ita.1",       "Serie A",         "soccer"),
        ("soccer/ger.1",       "Bundesliga",      "soccer"),
        ("soccer/fra.1",       "Ligue 1",         "soccer"),
        ("soccer/uefa.champions", "UCL",          "soccer"),
        ("basketball/nba",     "NBA",             "basketball"),
        ("football/nfl",       "NFL",             "football"),
        ("baseball/mlb",       "MLB",             "baseball"),
        ("hockey/nhl",         "NHL",             "hockey"),
        ("racing/f1",          "Formula 1",       "f1"),
        ("tennis/atp",         "ATP Tour",        "tennis"),
        ("cricket/all",        "Cricket",         "cricket"),
    ]
    sem = asyncio.Semaphore(6)
    async def fetch_league(path: str, name: str, sport: str) -> None:
        async with sem:
            try:
                r = await client.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard",
                    timeout=20,
                )
                if r.status_code != 200:
                    return
                data = r.json()
                for event in (data.get("events") or [])[:15]:
                    try:
                        competition = (event.get("competitions") or [{}])[0]
                        competitors = competition.get("competitors", [])
                        if len(competitors) < 2:
                            continue
                        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
                        venue = competition.get("venue", {}) or {}
                        addr = venue.get("address", {}) or {}
                        city = addr.get("city", "")
                        country = addr.get("country", "")
                        status = (event.get("status") or {}).get("type", {}) or {}
                        matches.append({
                            "league": name,
                            "sport": sport,
                            "home": ((home.get("team") or {}).get("displayName")) or "?",
                            "away": ((away.get("team") or {}).get("displayName")) or "?",
                            "homeScore": home.get("score", ""),
                            "awayScore": away.get("score", ""),
                            "venue": venue.get("fullName", "") or city,
                            "city": city,
                            "country": country,
                            "state": status.get("name", ""),
                            "completed": status.get("completed", False),
                            "date": event.get("date", ""),
                            "lat": None,
                            "lon": None,
                        })
                    except Exception:
                        continue
            except Exception:
                pass
    try:
        await asyncio.gather(*[fetch_league(p, n, s) for p, n, s in leagues])
        city_coords = {
            "London": (51.5, -0.1), "Madrid": (40.4, -3.7), "Manchester": (53.5, -2.2),
            "Liverpool": (53.4, -3.0), "Barcelona": (41.4, 2.2), "Milan": (45.5, 9.2),
            "Rome": (41.9, 12.5), "Munich": (48.1, 11.6), "Berlin": (52.5, 13.4),
            "Paris": (48.9, 2.3), "Lyon": (45.8, 4.8), "Amsterdam": (52.4, 4.9),
            "Lisbon": (38.7, -9.1), "Istanbul": (41.0, 29.0), "New York": (40.7, -74.0),
            "Boston": (42.4, -71.1), "Los Angeles": (34.1, -118.2), "Chicago": (41.9, -87.6),
            "Miami": (25.8, -80.2), "Dallas": (32.8, -96.8), "Houston": (29.8, -95.4),
            "Atlanta": (33.7, -84.4), "Philadelphia": (40.0, -75.2), "Detroit": (42.3, -83.0),
            "Toronto": (43.7, -79.4), "Montreal": (45.5, -73.6), "Vancouver": (49.3, -123.1),
            "Mexico City": (19.4, -99.1), "Sao Paulo": (-23.5, -46.6), "Rio de Janeiro": (-22.9, -43.2),
            "Buenos Aires": (-34.6, -58.4), "Tokyo": (35.7, 139.7), "Osaka": (34.7, 135.5),
            "Seoul": (37.6, 127.0), "Sydney": (-33.9, 151.2), "Melbourne": (-37.8, 145.0),
            "Monaco": (43.7, 7.4), "Dubai": (25.2, 55.3), "Doha": (25.3, 51.5),
            "Singapore": (1.3, 103.8), "Mumbai": (19.1, 72.9), "Delhi": (28.6, 77.2),
            "Johannesburg": (-26.2, 28.0), "Cape Town": (-33.9, 18.4),
            "Seattle": (47.6, -122.3), "Phoenix": (33.4, -112.1), "Denver": (39.7, -105.0),
            "Minneapolis": (45.0, -93.3), "Tampa": (27.9, -82.5), "Orlando": (28.5, -81.4),
            "Cleveland": (41.5, -81.7), "Indianapolis": (39.8, -86.2),
        }
        for m in matches:
            coords = city_coords.get(m.get("city", ""))
            if coords:
                m["lat"], m["lon"] = coords
        matches_geo = [m for m in matches if m.get("lat") is not None and m.get("lon") is not None]
        payload = {
            "source": "ESPN",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "matches": matches_geo,
            "total": len(matches),
            "geocoded": len(matches_geo),
        }
        write_cache("sports", payload)
        mark("sports", True, len(matches_geo))
    except Exception as e:
        mark("sports", False, error=str(e))


async def fetch_economy(client: httpx.AsyncClient) -> None:
    """Economy: forex (Frankfurter) + crypto (CoinGecko)."""
    result: dict[str, Any] = {
        "source": "Frankfurter + CoinGecko",
        "fetched": datetime.now(timezone.utc).isoformat(),
    }
    try:
        r = await client.get("https://api.frankfurter.dev/v1/latest", params={"base": "USD"}, timeout=20)
        if r.status_code == 200:
            result["forex"] = r.json()
    except Exception as e:
        result["forex_error"] = str(e)
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 25,
                "page": 1,
                "sparkline": "false",
            },
            timeout=20,
        )
        if r.status_code == 200:
            coins = r.json()
            result["crypto"] = [
                {
                    "id": c.get("id"),
                    "symbol": c.get("symbol"),
                    "name": c.get("name"),
                    "image": c.get("image"),
                    "price_usd": c.get("current_price"),
                    "market_cap": c.get("market_cap"),
                    "change_24h": c.get("price_change_percentage_24h"),
                    "volume": c.get("total_volume"),
                }
                for c in coins
            ]
    except Exception as e:
        result["crypto_error"] = str(e)
    try:
        r = await client.get("https://api.coingecko.com/api/v3/global", timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            result["crypto_market_cap"] = data.get("total_market_cap", {}).get("usd")
            result["crypto_volume"] = data.get("total_volume", {}).get("usd")
            result["btc_dominance"] = data.get("market_cap_percentage", {}).get("btc")
    except Exception:
        pass
    if "forex" in result or "crypto" in result:
        write_cache("economy", result)
        mark("economy", True, len(result.get("crypto", [])))
    else:
        mark("economy", False, error="All economy sources failed")


async def fetch_trade(client: httpx.AsyncClient) -> None:
    """UN Comtrade — bilateral commodity trade flows.
    Uses the public preview endpoint (no key) capped at 50 records/call.
    We fetch the top 5 commodities for the top 12 reporters and build a
    flow graph keyed by commodity.
    """
    # Key commodities (HS2 codes):
    # 27 = Mineral fuels/oil, 10 = Cereals, 72 = Iron/steel, 85 = Electrical,
    # 87 = Vehicles, 84 = Machinery, 71 = Precious metals, 09 = Coffee/tea
    commodities = [
        ("2709", "Crude Oil"),
        ("2711", "Natural Gas"),
        ("1001", "Wheat"),
        ("1201", "Soybeans"),
        ("2601", "Iron Ore"),
        ("8517", "Phones/Telecom"),
        ("8542", "Semiconductors"),
        ("8703", "Cars"),
        ("0901", "Coffee"),
        ("7108", "Gold"),
    ]
    # Top importing reporters (by economic weight) — M49 codes
    # 156=China, 842=USA, 276=Germany, 392=Japan, 356=India, 826=UK,
    # 250=France, 380=Italy, 410=S.Korea, 528=Netherlands, 724=Spain, 756=Switzerland
    reporters = [156, 842, 276, 392, 356, 826, 250, 380, 410, 528]
    year = 2023  # Comtrade annual lags ~1-2 years

    # Fetch reference mapping once
    try:
        ref_r = await client.get(
            "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json",
            timeout=30,
        )
        if ref_r.status_code != 200:
            mark("trade", False, error=f"Reference fetch failed {ref_r.status_code}")
            return
        ref = {}
        for item in ref_r.json().get("results", []):
            code = item.get("reporterCode") or item.get("id")
            iso3 = item.get("reporterCodeIsoAlpha3")
            name = item.get("reporterDesc") or item.get("text", "")
            if code and iso3:
                ref[int(code)] = {"iso3": iso3, "name": name}
    except Exception as e:
        mark("trade", False, error=f"Reference error: {e}")
        return

    # Country lat/lon lookup (top world capitals/centers)
    # Aligned with the M49 codes we care about
    country_coords = {
        156: (35.86, 104.19),  # China
        842: (39.50, -98.35),  # USA
        276: (51.17, 10.45),   # Germany
        392: (36.20, 138.25),  # Japan
        356: (20.59, 78.96),   # India
        826: (55.38, -3.44),   # UK
        250: (46.23, 2.21),    # France
        380: (41.87, 12.57),   # Italy
        410: (35.91, 127.77),  # South Korea
        528: (52.13, 5.29),    # Netherlands
        724: (40.46, -3.75),   # Spain
        756: (46.82, 8.23),    # Switzerland
        36:  (-25.27, 133.78), # Australia
        124: (56.13, -106.35), # Canada
        76:  (-14.24, -51.93), # Brazil
        643: (61.52, 105.32),  # Russia
        484: (23.63, -102.55), # Mexico
        682: (23.89, 45.08),   # Saudi Arabia
        784: (23.42, 53.85),   # UAE
        364: (32.43, 53.69),   # Iran
        368: (33.22, 43.68),   # Iraq
        364: (32.43, 53.69),
        434: (26.34, 17.23),   # Libya
        566: (9.08, 8.68),     # Nigeria
        12:  (28.03, 1.66),    # Algeria
        818: (26.82, 30.80),   # Egypt
        752: (60.13, 18.64),   # Sweden
        578: (60.47, 8.47),    # Norway
        208: (56.26, 9.50),    # Denmark
        246: (61.92, 25.75),   # Finland
        616: (51.92, 19.15),   # Poland
        40:  (47.52, 14.55),   # Austria
        56:  (50.50, 4.47),    # Belgium
        372: (53.41, -8.24),   # Ireland
        620: (39.40, -8.22),   # Portugal
        300: (39.07, 21.82),   # Greece
        792: (38.96, 35.24),   # Turkey
        376: (31.05, 34.85),   # Israel
        702: (1.35, 103.82),   # Singapore
        458: (4.21, 101.98),   # Malaysia
        764: (15.87, 100.99),  # Thailand
        704: (14.06, 108.28),  # Vietnam
        360: (-0.79, 113.92),  # Indonesia
        608: (12.88, 121.77),  # Philippines
        410: (35.91, 127.77),
        158: (23.70, 121.00),  # Taiwan
        344: (22.30, 114.17),  # Hong Kong
        32:  (-38.42, -63.62), # Argentina
        152: (-35.68, -71.54), # Chile
        604: (-9.19, -75.02),  # Peru
        170: (4.57, -74.30),   # Colombia
        710: (-30.56, 22.94),  # South Africa
        404: (-0.02, 37.91),   # Kenya
        231: (9.15, 40.49),    # Ethiopia
        188: (9.75, -83.75),   # Costa Rica
        36:  (-25.27, 133.78),
        554: (-40.90, 174.89), # New Zealand
    }

    flows: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(2)  # Comtrade doesn't like parallelism

    async def fetch_flow(reporter_code: int, cmd_code: str, cmd_name: str) -> None:
        async with sem:
            try:
                r = await client.get(
                    "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                    params={
                        "reporterCode": reporter_code,
                        "period": year,
                        "cmdCode": cmd_code,
                        "flowCode": "M",  # imports
                        "maxRecords": 50,
                    },
                    timeout=30,
                )
                if r.status_code != 200:
                    return
                data = r.json().get("data", [])
                for row in data:
                    pcode = row.get("partnerCode")
                    value = row.get("primaryValue") or 0
                    if not pcode or pcode == 0 or value < 100_000_000:  # $100M min
                        continue
                    if pcode not in country_coords or reporter_code not in country_coords:
                        continue
                    from_lat, from_lon = country_coords[pcode]
                    to_lat, to_lon = country_coords[reporter_code]
                    flows.append({
                        "from_code": pcode,
                        "to_code": reporter_code,
                        "from_name": ref.get(pcode, {}).get("name", str(pcode)),
                        "to_name": ref.get(reporter_code, {}).get("name", str(reporter_code)),
                        "from_iso3": ref.get(pcode, {}).get("iso3", ""),
                        "to_iso3": ref.get(reporter_code, {}).get("iso3", ""),
                        "from_lat": from_lat,
                        "from_lon": from_lon,
                        "to_lat": to_lat,
                        "to_lon": to_lon,
                        "commodity": cmd_name,
                        "hs": cmd_code,
                        "value_usd": value,
                        "year": year,
                    })
                # Rate limit: be polite
                await asyncio.sleep(0.5)
            except Exception:
                pass

    try:
        tasks = []
        for reporter in reporters:
            for hs, name in commodities:
                tasks.append(fetch_flow(reporter, hs, name))
        await asyncio.gather(*tasks)
        # Sort by value, keep top 200
        flows.sort(key=lambda f: f["value_usd"], reverse=True)
        payload = {
            "source": "UN Comtrade (preview endpoint)",
            "year": year,
            "fetched": datetime.now(timezone.utc).isoformat(),
            "flows": flows[:200],
            "total_flows": len(flows),
            "reporters_queried": len(reporters),
            "commodities_queried": len(commodities),
        }
        write_cache("trade", payload)
        mark("trade", True, len(flows[:200]))
    except Exception as e:
        mark("trade", False, error=str(e))


async def fetch_trends(client: httpx.AsyncClient) -> None:
    """Wikipedia pageview trends — top read articles yesterday (en wiki)."""
    from datetime import timedelta
    try:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y/%m/%d")
        r = await client.get(
            f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{yesterday}",
            timeout=20,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code == 200:
            data = r.json()
            items = ((data.get("items") or [{}])[0]).get("articles", [])
            filtered = [
                {
                    "title": a.get("article", "").replace("_", " "),
                    "views": a.get("views", 0),
                    "rank": a.get("rank", 0),
                    "url": f"https://en.wikipedia.org/wiki/{a.get('article', '')}",
                }
                for a in items
                if a.get("article")
                and not a.get("article", "").startswith("Special:")
                and a.get("article") != "Main_Page"
            ][:50]
            write_cache("trends", {"source": "Wikipedia", "date": yesterday, "top": filtered})
            mark("trends", True, len(filtered))
            return
        mark("trends", False, error=f"HTTP {r.status_code}")
    except Exception as e:
        mark("trends", False, error=str(e))


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

# (worker_fn, interval_seconds, initial_delay)
SCHEDULE: list[tuple[Any, int, int]] = [
    (fetch_iss, 10, 0),                 # ISS moves fast
    (fetch_flights, 120, 2),             # Flights every 2 min (OpenSky credit budget)
    (fetch_quakes, 120, 4),              # Quakes every 2 min
    (fetch_fires, 600, 6),               # Fires every 10 min
    (fetch_disasters, 600, 8),           # EONET every 10 min
    (fetch_crises, 1800, 10),            # ReliefWeb every 30 min
    (fetch_conflicts, 300, 15),          # GDELT every 5 min
    (fetch_news, 300, 45),               # GDELT news every 5 min (30s gap from conflicts)
    (fetch_air_quality, 1800, 16),       # AQ every 30 min
    (fetch_rainviewer, 300, 18),         # Radar frames every 5 min
    (fetch_satellites, 7200, 20),        # TLEs every 2 hr
    (fetch_volcanoes, 86400, 22),        # Daily
    (fetch_cables, 86400, 24),           # Daily (barely changes)
    (fetch_radio, 86400, 26),            # Daily
    (fetch_population, 86400, 28),       # Daily (barely changes)
    (fetch_webcams, 1800, 30),           # Every 30 min
    # Phase 3 workers
    (fetch_gaming, 600, 32),             # Steam + Twitch every 10 min
    (fetch_sports, 300, 34),             # ESPN every 5 min
    (fetch_economy, 300, 36),            # Forex + crypto every 5 min
    (fetch_trends, 3600, 38),            # Wikipedia trends every hour
    (fetch_trade, 86400, 40),            # UN Comtrade daily (annual data)
]

async def worker(fn: Any, interval: int, delay: int, client: httpx.AsyncClient) -> None:
    """Run a worker on a fixed schedule."""
    if delay:
        await asyncio.sleep(delay)
    while True:
        t0 = time.time()
        try:
            await fn(client)
        except Exception as e:
            print(f"[worker {fn.__name__}] unhandled error: {e}")
            traceback.print_exc()
        elapsed = time.time() - t0
        sleep_for = max(1, interval - elapsed)
        await asyncio.sleep(sleep_for)

@app.on_event("startup")
async def startup() -> None:
    # Shared HTTP client with sensible defaults
    app.state.client = httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        http2=False,  # server may not support
        headers={"User-Agent": "WorldTwin-Aggregator/1.0"},
    )
    for fn, interval, delay in SCHEDULE:
        asyncio.create_task(worker(fn, interval, delay, app.state.client))
    print(f"Started {len(SCHEDULE)} background workers")

@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.client.aclose()

# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "time": datetime.now(timezone.utc).isoformat(),
        "layers": stats,
    }

@app.get("/api/_stats")
async def get_stats() -> dict[str, Any]:
    return stats

@app.get("/api/{layer}")
async def get_layer(layer: str) -> Response:
    # Guard against path traversal
    if "/" in layer or ".." in layer:
        return JSONResponse({"error": "invalid layer"}, status_code=400)
    path = CACHE_DIR / f"{layer}.json"
    if not path.exists():
        return JSONResponse({"error": f"layer '{layer}' not cached yet"}, status_code=404)
    return FileResponse(path, media_type="application/json")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
