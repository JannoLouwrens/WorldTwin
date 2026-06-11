"""Live aircraft — primary source is adsb.lol (free, no key, reliable),
fallback to OpenSky Network."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="flights",
    name="Live Aircraft (ADS-B)",
    category="transit",
    kind="points",
    source="adsb.lol + OpenSky Network",
    source_url="https://api.adsb.lol/",
    license="ODbL",
    refresh_s=60,
    initial_delay_s=2,
    units="altitude (feet)",
    description="Live positions of ~800 aircraft worldwide from adsb.lol (primary) or OpenSky Network (fallback).",
)

# Regional search centers — adsb.lol returns ac within a radius (nautical miles)
# 250nm is the max. We query 12 regions to cover the globe.
REGIONS = [
    # (lat, lon, name)
    (40.7, -74.0, "NYC"),
    (33.9, -118.4, "LA"),
    (41.4, -87.8, "Chicago"),
    (29.6, -95.5, "Houston"),
    (51.5, -0.5, "London"),
    (48.9, 2.3, "Paris"),
    (50.0, 8.5, "Frankfurt"),
    (41.0, 29.0, "Istanbul"),
    (25.3, 55.3, "Dubai"),
    (1.4, 103.8, "Singapore"),
    (35.7, 139.7, "Tokyo"),
    (-33.9, 151.2, "Sydney"),
    (-23.6, -46.7, "São Paulo"),
    (19.4, -99.1, "Mexico City"),
    (55.8, 37.6, "Moscow"),
    (28.6, 77.2, "Delhi"),
]


# Route cache — callsign → {origin: {iata, name, lat, lon}, dest: {...}}
# Callsigns rarely change routes, so we cache for 1 hour
_route_cache: dict[str, dict] = {}
_route_cache_time: dict[str, float] = {}


async def _fetch_routes(client: httpx.AsyncClient, callsigns: list[str]) -> None:
    """Bulk-lookup routes for the given callsigns via adsb.lol /api/0/routeset.

    Populates _route_cache as a side effect.
    """
    import time as _time
    now = _time.time()
    # Filter out cached-fresh ones
    needed = [c for c in callsigns if c and (
        c not in _route_cache_time or now - _route_cache_time[c] > 3600
    )]
    if not needed:
        return
    # Batch into groups of 50 (API limit)
    for i in range(0, len(needed), 50):
        batch = needed[i:i+50]
        try:
            r = await client.post(
                "https://api.adsb.lol/api/0/routeset",
                json={"planes": [{"callsign": c, "lat": 0, "lng": 0} for c in batch]},
                timeout=20,
            )
            if r.status_code != 200:
                continue
            results = r.json()
            for entry in results:
                callsign = entry.get("callsign", "").strip()
                if not callsign:
                    continue
                airports = entry.get("_airports") or []
                if len(airports) >= 2:
                    origin = airports[0]
                    dest = airports[-1]
                    _route_cache[callsign] = {
                        "origin": {
                            "iata": origin.get("iata"),
                            "icao": origin.get("icao"),
                            "name": origin.get("name"),
                            "location": origin.get("location"),
                            "country": origin.get("countryiso2"),
                            "lat": origin.get("lat"),
                            "lon": origin.get("lon"),
                        },
                        "dest": {
                            "iata": dest.get("iata"),
                            "icao": dest.get("icao"),
                            "name": dest.get("name"),
                            "location": dest.get("location"),
                            "country": dest.get("countryiso2"),
                            "lat": dest.get("lat"),
                            "lon": dest.get("lon"),
                        },
                        "route_code": entry.get("_airport_codes_iata"),
                    }
                    _route_cache_time[callsign] = now
        except Exception:
            continue


async def _fetch_adsblol(client: httpx.AsyncClient) -> list | None:
    """Fetch live aircraft from adsb.lol via multiple regional queries."""
    sem = asyncio.Semaphore(6)
    seen_hex: set[str] = set()
    points: list = []

    async def fetch_region(lat: float, lon: float, name: str):
        async with sem:
            try:
                r = await client.get(
                    f"https://api.adsb.lol/v2/point/{lat}/{lon}/250",
                    timeout=20,
                    headers={"Accept": "application/json"},
                )
                if r.status_code != 200:
                    return
                data = r.json()
                for ac in data.get("ac", []):
                    hex_id = ac.get("hex")
                    if not hex_id or hex_id in seen_hex:
                        continue
                    lat_ac = ac.get("lat")
                    lon_ac = ac.get("lon")
                    if lat_ac is None or lon_ac is None:
                        continue
                    seen_hex.add(hex_id)
                    alt_ft = ac.get("alt_baro")
                    if isinstance(alt_ft, str):
                        alt_ft = 0  # "ground"
                    alt_m = (alt_ft or 0) * 0.3048
                    gs_knots = ac.get("gs") or 0
                    vel_ms = gs_knots * 0.514444
                    heading_deg = ac.get("track") or ac.get("mag_heading") or 0
                    on_ground = (ac.get("alt_baro") == "ground")
                    callsign = (ac.get("flight") or "").strip()
                    points.append(point(
                        lat=lat_ac, lon=lon_ac,
                        id=hex_id,
                        value=alt_m,
                        label=callsign or hex_id,
                        callsign=callsign,
                        country="",
                        altitude_m=alt_m,
                        altitude_ft=alt_ft or 0,
                        velocity_ms=vel_ms,
                        velocity_knots=gs_knots,
                        heading_deg=heading_deg,
                        on_ground=on_ground,
                        aircraft_type=ac.get("t", ""),
                        registration=ac.get("r", ""),
                        squawk=ac.get("squawk", ""),
                    ))
            except Exception:
                pass

    await asyncio.gather(*[fetch_region(la, lo, n) for (la, lo, n) in REGIONS])
    if not points:
        return None

    # Evict stale route-cache entries — the module-level dict grew without
    # bound (one entry per callsign ever seen) and the WHOLE cache was
    # serialized into flights.json every refresh.
    import time as _time
    _cutoff = _time.time() - 6 * 3600
    for cs in [c for c, t in _route_cache_time.items() if t < _cutoff]:
        _route_cache.pop(cs, None)
        _route_cache_time.pop(cs, None)

    # Enrich with route data — look up top 200 callsigns' origin/dest airports
    callsigns = list({p["props"].get("callsign", "") for p in points if p["props"].get("callsign")})[:200]
    await _fetch_routes(client, callsigns)

    # Attach route info to points
    for p in points:
        cs = p["props"].get("callsign", "")
        if cs and cs in _route_cache:
            route = _route_cache[cs]
            p["props"]["origin"] = route.get("origin")
            p["props"]["dest"] = route.get("dest")
            p["props"]["route_code"] = route.get("route_code")

    return points


async def _fetch_opensky(client: httpx.AsyncClient) -> tuple[list, dict] | None:
    """Fallback: OpenSky Network anonymous states."""
    try:
        r = await client.get(
            "https://opensky-network.org/api/states/all",
            timeout=30,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        states = data.get("states") or []
        step = max(1, len(states) // 600)
        sampled = states[::step]
        points = []
        for s in sampled:
            try:
                lon, lat = s[5], s[6]
                if lon is None or lat is None:
                    continue
                alt = s[7] or 0
                vel = s[9] or 0
                heading = s[10] or 0
                points.append(point(
                    lat=lat, lon=lon,
                    id=s[0],
                    value=alt,
                    label=(s[1] or "").strip() or s[0],
                    callsign=(s[1] or "").strip(),
                    country=s[2],
                    altitude_m=alt,
                    velocity_ms=vel,
                    heading_deg=heading,
                    on_ground=bool(s[8]),
                    vertical_rate=s[11] or 0,
                ))
            except (IndexError, TypeError):
                continue
        return points, {"time": data.get("time"), "states": sampled}
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    # Try adsb.lol first (more reliable, no rate limit)
    points = await _fetch_adsblol(client)
    if points:
        # Legacy format = OpenSky states array shape:
        # [icao, callsign, country, time_pos, time_contact, lon, lat, baro_alt,
        #  on_ground, velocity, heading, vert_rate, ...]
        # This keeps the existing frontend parser working.
        import time as _time
        now_s = int(_time.time())
        states = []
        for p in points:
            props = p.get("props", {})
            states.append([
                p.get("id") or "",                         # 0 icao
                props.get("callsign", ""),                 # 1 callsign
                "",                                        # 2 country
                now_s,                                     # 3 time_position
                now_s,                                     # 4 last_contact
                p["lon"],                                  # 5 longitude
                p["lat"],                                  # 6 latitude
                props.get("altitude_m", 0),                # 7 baro_altitude
                props.get("on_ground", False),             # 8 on_ground
                props.get("velocity_ms", 0),               # 9 velocity
                props.get("heading_deg", 0),               # 10 true_track
                0,                                         # 11 vert_rate
                None,                                      # 12 sensors
                props.get("altitude_m", 0),                # 13 geo_altitude
                props.get("squawk", ""),                   # 14 squawk
                False,                                     # 15 spi
                0,                                         # 16 pos_source
            ])
        # Include routes keyed by callsign — only for aircraft currently in
        # view (the full accumulated cache was being shipped every refresh).
        active = {p["props"].get("callsign", "") for p in points}
        routes = {cs: _route_cache[cs] for cs in active if cs and cs in _route_cache}
        legacy = {"time": now_s, "states": states, "routes": routes}
        return points, legacy
    # Fallback to OpenSky
    os_result = await _fetch_opensky(client)
    if os_result:
        return os_result
    return None


register(LAYER, fetch)
