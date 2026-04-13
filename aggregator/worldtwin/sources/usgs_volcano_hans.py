"""USGS Volcano HANS — Currently elevated volcano alerts.

Free, no key. Returns volcanoes currently at elevated alert level (above
NORMAL/GREEN). Complements Smithsonian GVP (which has all 1200+ volcanoes).
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="usgs_volcano_hans",
    name="USGS Elevated Volcanoes (HANS)",
    category="nature",
    kind="points",
    source="USGS Volcano Hazards Program HANS",
    source_url="https://volcanoes.usgs.gov/hans2/",
    license="US Public Domain",
    refresh_s=3600,
    initial_delay_s=305,
    description="Volcanoes currently at elevated alert level (YELLOW/ORANGE/RED).",
    requires_key=False,
)


ALERT_SEVERITY = {"NORMAL": 1, "GREEN": 1, "YELLOW": 3, "ADVISORY": 3, "ORANGE": 4, "WATCH": 4, "RED": 5, "WARNING": 5}


async def fetch(client: httpx.AsyncClient):
    # Verified 2026-04-11: correct URL is hans-public (not hans2)
    try:
        r = await client.get(
            "https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes",
            timeout=30,
        )
        if r.status_code != 200:
            print(f"[usgs_volcano_hans] HTTP {r.status_code}")
            return None
        rows = r.json()
        if not isinstance(rows, list):
            rows = rows.get("data") or []
        volcanoes = []
        for row in rows:
            # hans-public schema: vnum, volcano_name, notice_type_cd, color_code,
            # alert_level, obs_fullname, obs_abbr, sent_utc, latitude, longitude
            lat = row.get("latitude") or row.get("lat")
            lon = row.get("longitude") or row.get("lon")
            if lat is None or lon is None:
                continue
            try:
                lat = float(lat); lon = float(lon)
            except (ValueError, TypeError):
                continue
            alert = (row.get("color_code") or row.get("alert_level") or "").upper()
            sev = ALERT_SEVERITY.get(alert, 2)
            volcanoes.append({
                "id": row.get("vnum") or row.get("volcano_id") or row.get("id"),
                "name": row.get("volcano_name") or row.get("volcanoName") or "",
                "lat": lat,
                "lon": lon,
                "alert_color": alert,
                "alert_level": row.get("alert_level", ""),
                "notice_type": row.get("notice_type_cd", ""),
                "severity": sev,
                "observatory": row.get("obs_fullname") or row.get("obs_abbr", ""),
                "updated": row.get("sent_utc") or row.get("activity_date", ""),
            })
        volcanoes.sort(key=lambda v: v.get("severity", 0), reverse=True)
        return {
            "source": "USGS Volcano HANS",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(volcanoes),
            "volcanoes": volcanoes,
        }
    except Exception as e:
        print(f"[usgs_volcano_hans] error: {type(e).__name__}: {e}")
        return None


register(LAYER, fetch)
