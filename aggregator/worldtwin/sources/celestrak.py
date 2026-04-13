"""CelesTrak — satellite TLE data."""
import json

import httpx

from ..models import LayerMeta
from ..registry import register

GROUPS = [
    ("stations", 0),
    ("visual", 100),
    ("gps-ops", 100),
    ("geo", 100),
    ("starlink", 200),
]

LAYER = LayerMeta(
    id="satellites",
    name="Active Satellites",
    category="space",
    kind="raw",  # TLE data doesn't map cleanly to points (needs SGP4 propagation)
    source="CelesTrak",
    source_url="https://celestrak.org/NORAD/elements/gp.php",
    license="CelesTrak Terms (non-commercial use)",
    refresh_s=7200,
    initial_delay_s=20,
    units="orbital elements (TLE)",
    description="TLE orbital elements for space stations, GPS, geostationary, Starlink, and visible satellites. Clients propagate positions using SGP4.",
)


async def fetch(client: httpx.AsyncClient):
    all_sats = []
    for group, limit in GROUPS:
        try:
            r = await client.get(
                LAYER.source_url,
                params={"GROUP": group, "FORMAT": "json"},
                timeout=30,
            )
            if r.status_code != 200:
                continue
            try:
                sats = r.json()
            except json.JSONDecodeError:
                continue
            if not isinstance(sats, list):
                continue
            if limit and len(sats) > limit:
                step = max(1, len(sats) // limit)
                sats = sats[::step]
            for s in sats:
                s["_group"] = group
            all_sats.extend(sats)
        except Exception:
            continue
    if not all_sats:
        return None
    return all_sats, all_sats


register(LAYER, fetch)
