"""USGS Volcano HANS — Currently elevated volcano alerts.

Free, no key. Returns volcanoes currently at elevated alert level (above
NORMAL/GREEN). Complements Smithsonian GVP (which has all 1200+ volcanoes).

The HANS getElevatedVolcanoes response carries NO coordinates (verified
live 2026-06-11) — every row was being dropped and the layer was
permanently empty. Coordinates are joined from the Smithsonian GVP cache
(volcanoes.json) by Volcano_Number == vnum.
"""
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import cache
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


def _gvp_coords() -> dict[int, tuple[float, float]]:
    """Volcano_Number → (lat, lon) from the on-disk Smithsonian GVP cache."""
    out: dict[int, tuple[float, float]] = {}
    try:
        with open(cache.legacy_path("volcanoes"), "r", encoding="utf-8") as f:
            gvp = json.load(f)
        for feat in gvp.get("features", []):
            props = feat.get("properties") or {}
            num = props.get("Volcano_Number")
            coords = (feat.get("geometry") or {}).get("coordinates") or []
            if num is not None and len(coords) >= 2:
                out[int(num)] = (float(coords[1]), float(coords[0]))
    except Exception as e:
        print(f"[usgs_volcano_hans] GVP coord join unavailable: {e}")
    return out


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
        coords_by_vnum = _gvp_coords()
        volcanoes = []
        for row in rows:
            # hans-public schema (live 2026-06-11): vnum, volcano_name,
            # notice_type_cd, color_code, alert_level, obs_*, sent_utc —
            # NO coordinates. Join via Smithsonian GVP by vnum.
            lat = lon = None
            try:
                vnum = int(row.get("vnum") or 0)
            except (ValueError, TypeError):
                vnum = 0
            if vnum and vnum in coords_by_vnum:
                lat, lon = coords_by_vnum[vnum]
            if lat is None or lon is None:
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
        } if (volcanoes or not rows) else None  # rows present but none parsed = schema drift — keep previous cache
    except Exception as e:
        print(f"[usgs_volcano_hans] error: {type(e).__name__}: {e}")
        return None


register(LAYER, fetch)
