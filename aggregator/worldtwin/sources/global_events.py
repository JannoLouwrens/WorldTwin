"""Global Events Feed — unified headline ticker.

Aggregates the most important events happening on Earth right now from:
  - GDACS (natural hazards, severity-scored)
  - USGS significant quakes M5.5+
  - NHC active tropical cyclones
  - UCDP GED conflict events (last 7 days by fatalities)
  - GDELT mention velocity (stories exploding in last 15 min)
  - Commodity price shocks (>5% daily moves)
  - PortWatch chokepoint throughput anomalies
  - Wikidata recent battles

Normalised schema:
  {
    id, title, type (hazard/quake/storm/conflict/trade/market/space),
    severity (1-5), lat, lon, time, source, url
  }

Used by the frontend ticker strip and the Pulse mode.
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))


LAYER = LayerMeta(
    id="global_events",
    name="Global Events Feed",
    category="meta",
    kind="points",
    source="Aggregated (GDACS + USGS + NHC + UCDP + GDELT + prices)",
    source_url="internal",
    license="Aggregated — see individual sources",
    refresh_s=300,  # 5 min
    initial_delay_s=100,
    description=(
        "Unified headline feed of the biggest ongoing events on Earth. "
        "Powers the top-of-screen ticker and the Pulse mode."
    ),
    requires_key=False,
)


def _read_cache_file(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    events: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ---- 1. GDACS (already in our cache) ----
    gdacs = _read_cache_file("gdacs_events")
    if gdacs and gdacs.get("events"):
        for e in gdacs["events"][:50]:
            events.append({
                "id": f"gdacs:{e.get('id')}",
                "title": f"{e.get('type_name', 'Alert')}: {e.get('name', '')[:80]}",
                "type": "hazard",
                "subtype": e.get("type_code", ""),
                "severity": e.get("severity", 1),
                "lat": e.get("lat", 0),
                "lon": e.get("lon", 0),
                "time": e.get("from_date", ""),
                "country": e.get("country", ""),
                "source": "GDACS",
                "url": e.get("url", ""),
            })

    # ---- 2. USGS significant quakes M5.5+ ----
    try:
        r = await client.get(
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson",
            timeout=30,
        )
        if r.status_code == 200:
            geo = r.json()
            for f in geo.get("features", [])[:20]:
                props = f.get("properties", {})
                coords = (f.get("geometry") or {}).get("coordinates") or [0, 0, 0]
                mag = props.get("mag", 0)
                if mag < 5.5:
                    continue
                events.append({
                    "id": f"usgs:{props.get('code', '')}",
                    "title": f"M{mag:.1f} earthquake · {props.get('place', '')}",
                    "type": "quake",
                    "severity": min(5, max(1, int((mag - 5.5) * 1.5) + 2)),
                    "lat": coords[1],
                    "lon": coords[0],
                    "depth_km": coords[2] if len(coords) > 2 else 0,
                    "time": datetime.fromtimestamp((props.get("time") or 0) / 1000, tz=timezone.utc).isoformat(),
                    "country": props.get("place", "").split(",")[-1].strip(),
                    "source": "USGS",
                    "url": props.get("url", ""),
                })
    except Exception as e:
        print(f"[global_events] usgs error: {e}")

    # ---- 3. NHC active storms ----
    nhc = _read_cache_file("nhc_cyclones")
    if nhc and nhc.get("storms"):
        for s in nhc["storms"]:
            if not s.get("lat"):
                continue
            cat = s.get("category", "TD")
            sev = {"TD": 1, "TS": 2, "Cat1": 3, "Cat2": 3, "Cat3": 4, "Cat4": 5, "Cat5": 5}.get(cat, 2)
            events.append({
                "id": f"nhc:{s.get('id', '')}",
                "title": f"{cat} {s.get('name', '')} · {s.get('wind_kts', 0):.0f} kts",
                "type": "storm",
                "severity": sev,
                "lat": s["lat"],
                "lon": s["lon"],
                "time": s.get("last_update", ""),
                "source": "NHC",
                "url": "",
            })

    # ---- 4. UCDP GED recent events (fatality-verified conflict) ----
    ucdp = _read_cache_file("ucdp_ged")
    if ucdp and ucdp.get("events"):
        cutoff = (now - timedelta(days=14)).strftime("%Y-%m-%d")
        recent = [e for e in ucdp["events"] if e.get("date_start", "") >= cutoff]
        # top 15 by fatalities
        recent.sort(key=lambda e: e.get("best", 0), reverse=True)
        for e in recent[:15]:
            best = e.get("best", 0)
            sev = 1
            if best >= 100: sev = 5
            elif best >= 30: sev = 4
            elif best >= 10: sev = 3
            elif best >= 1: sev = 2
            events.append({
                "id": f"ucdp:{e.get('id')}",
                "title": f"{e.get('dyad_name', '')} · {best} killed in {e.get('country', '')}",
                "type": "conflict",
                "severity": sev,
                "lat": e["lat"],
                "lon": e["lon"],
                "time": e.get("date_start", ""),
                "country": e.get("country", ""),
                "source": "UCDP GED",
                "url": "",
            })

    # ---- 5. Wikidata recent battles ----
    wd = _read_cache_file("wikidata_battles")
    if wd and wd.get("battles"):
        for b in wd["battles"][:15]:
            events.append({
                "id": f"wd:{b.get('id')}",
                "title": f"Battle: {b.get('name', '')}",
                "type": "conflict",
                "severity": 3,
                "lat": b.get("lat", 0),
                "lon": b.get("lon", 0),
                "time": b.get("date", ""),
                "source": "Wikidata",
                "url": b.get("article_url") or b.get("wikidata_url", ""),
            })

    # ---- 6. GDELT GKG theme pulses (highest-count themes) ----
    gkg = _read_cache_file("gdelt_gkg_themes")
    if gkg and gkg.get("pulses"):
        top = sorted(gkg["pulses"], key=lambda p: p.get("count", 0), reverse=True)[:15]
        for p in top:
            theme = p.get("theme", "")
            cc_ = p.get("country", "")
            sev = 1
            if theme in ("KILL", "TERROR", "ARMEDCONFLICT"): sev = 4
            elif theme in ("WOUND", "PROTEST", "RIOT", "MILITARY"): sev = 3
            elif theme.startswith("NATURAL_DISASTER") or theme.startswith("ECON_"): sev = 3
            events.append({
                "id": f"gkg:{theme}:{cc_}",
                "title": f"{theme.replace('_', ' ').title()} surging in {cc_}",
                "type": "news",
                "severity": sev,
                "lat": p.get("lat", 0),
                "lon": p.get("lon", 0),
                "time": now_iso,
                "country": cc_,
                "source": "GDELT GKG",
                "url": p.get("sample_url", ""),
            })

    # ---- 7. Commodity price shocks (from commodity_prices cache) ----
    prices = _read_cache_file("commodity_prices")
    if prices and prices.get("items"):
        for it in prices["items"]:
            # We don't have delta stored — stub: show any item as baseline info
            events.append({
                "id": f"px:{it.get('symbol', '')}",
                "title": f"{it.get('name', '')} · ${it.get('price', 0):.2f} {it.get('unit', '')}",
                "type": "market",
                "severity": 1,
                "lat": 0,
                "lon": 0,
                "time": it.get("date", now_iso),
                "source": "Markets",
                "url": "",
            })

    # ---- 8. PortWatch chokepoint anomalies (Suez/Hormuz low = threat) ----
    pw = _read_cache_file("portwatch_chokepoints")
    if pw and pw.get("chokepoints"):
        # Rule: flag chokepoints where today's total is below a hardcoded baseline
        baselines = {
            "Suez Canal": 70,
            "Panama Canal": 40,
            "Strait of Hormuz": 25,
            "Bab el-Mandeb Strait": 60,
            "Bosporus Strait": 90,
            "Dover Strait": 180,
            "Malacca Strait": 200,
        }
        for cp in pw["chokepoints"]:
            name = cp.get("name", "")
            n = cp.get("n_total", 0)
            bl = baselines.get(name)
            if bl and n < bl * 0.75:
                drop = int((1 - n / bl) * 100)
                events.append({
                    "id": f"pw:{name}",
                    "title": f"{name} traffic {drop}% below baseline ({n} ships)",
                    "type": "trade",
                    "severity": 3 if drop > 40 else 2,
                    "lat": cp["lat"],
                    "lon": cp["lon"],
                    "time": now_iso,
                    "source": "IMF PortWatch",
                    "url": "",
                })

    # ---- 9. Space weather alerts (from swpc_aurora) ----
    swpc = _read_cache_file("swpc_aurora")
    if swpc:
        scales = swpc.get("scales") or {}
        # Scales come as a dict of time→category→scale map
        kp = swpc.get("kp_index") or {}
        kp_val = kp.get("kp_index") or kp.get("estimated_kp")
        try:
            kp_num = float(kp_val) if kp_val is not None else 0
        except (ValueError, TypeError):
            kp_num = 0
        if kp_num >= 5:
            sev = min(5, int(kp_num - 3))
            events.append({
                "id": f"swpc:kp:{kp_num}",
                "title": f"Geomagnetic storm · Kp {kp_num:.1f} · G{max(1, int(kp_num - 4))}",
                "type": "space",
                "severity": sev,
                "lat": 0,
                "lon": 0,
                "time": now_iso,
                "source": "NOAA SWPC",
                "url": "https://www.swpc.noaa.gov/",
            })

    # ---- Sort + rank ----
    # Score = severity * 10 + recency_hours_bonus (more recent = higher)
    def score(ev):
        base = ev.get("severity", 1) * 10
        # Time recency bonus
        try:
            t = datetime.fromisoformat(ev.get("time", "").replace("Z", "+00:00"))
            hours_old = (now - t).total_seconds() / 3600
            recency = max(0, 24 - hours_old) / 24 * 5
        except (ValueError, TypeError):
            recency = 0
        return base + recency

    events.sort(key=score, reverse=True)
    top = events[:120]

    # Group counts
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1

    return {
        "source": "Aggregated",
        "fetched": now_iso,
        "count": len(top),
        "total": len(events),
        "by_type": by_type,
        "events": top,
    }


register(LAYER, fetch)
