"""GDACS Global Disaster Alert Coordination System — unified hazard hub.

Fuses USGS quakes, NHC/JTWC cyclones, GloFAS floods, Smithsonian volcanoes,
GWIS wildfires, droughts into a single CC-BY severity-scored GeoJSON feed.
Free, no key, ~15-min updates.

This is the single most efficient threats feed on Earth.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="gdacs_events",
    name="GDACS Disaster Alerts",
    category="war",  # 'threats' category would be new — reuse war for now
    kind="points",
    source="GDACS (Global Disaster Alert and Coordination System, JRC)",
    source_url="https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP",
    license="CC-BY 4.0",
    refresh_s=900,  # 15 min
    initial_delay_s=35,
    description=(
        "Unified alert feed for earthquakes, tropical cyclones, floods, "
        "volcanoes, wildfires, and droughts — with severity (green/orange/red), "
        "impact estimate, and event polygons."
    ),
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://www.gdacs.org/gdacsapi/api/events/geteventlist/MAP",
            timeout=45,
        )
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])

        events = []
        by_type: dict[str, int] = {}
        for f in features:
            props = f.get("properties") or {}
            geom = f.get("geometry") or {}
            coords = geom.get("coordinates") or []
            if len(coords) < 2:
                continue
            lon, lat = coords[0], coords[1]
            # Parse severity — GDACS uses 'alertlevel' (Green, Orange, Red) and 'alertscore'
            alert_level = props.get("alertlevel", "Green")
            severity_map = {"Green": 1, "Orange": 3, "Red": 5}
            severity = severity_map.get(alert_level, 1)
            ev_type = props.get("eventtype", "UNK")  # EQ, TC, FL, VO, WF, DR
            type_names = {
                "EQ": "Earthquake",
                "TC": "Tropical Cyclone",
                "FL": "Flood",
                "VO": "Volcano",
                "WF": "Wildfire",
                "DR": "Drought",
            }
            events.append({
                "id": props.get("eventid", ""),
                "type_code": ev_type,
                "type_name": type_names.get(ev_type, ev_type),
                "name": props.get("name", ""),
                "country": props.get("country", ""),
                "alert_level": alert_level,
                "severity": severity,
                "alert_score": props.get("alertscore"),
                "from_date": props.get("fromdate", ""),
                "to_date": props.get("todate", ""),
                "lat": lat,
                "lon": lon,
                "url": props.get("url", {}).get("report") if isinstance(props.get("url"), dict) else props.get("url"),
                "description": props.get("description", "")[:400],
                "icon": props.get("icon", ""),
                "population_impact": props.get("population", ""),
            })
            by_type[ev_type] = by_type.get(ev_type, 0) + 1

        events.sort(key=lambda e: (e["severity"], e.get("from_date", "")), reverse=True)

        return {
            "source": "GDACS",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(events),
            "by_type": by_type,
            "events": events,
        }
    except Exception as e:
        print(f"[gdacs_events] error: {e}")
        return None


register(LAYER, fetch)
