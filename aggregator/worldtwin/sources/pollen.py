"""Pollen (Europe — CAMS) — Open-Meteo air-quality pollen variables.

HONESTY CONSTRAINT: pollen in Open-Meteo comes from the CAMS *European*
model only. Verified in-container 2026-09-28: Berlin returns values for all
six species; Tokyo and New York return null for every species. The layer
name declares the domain and the served payload carries a `coverage` note so
no consumer can mistake absence (outside the domain) for zero pollen.
"""
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta, point
from ..registry import register
# Source of truth for the city table is the air_quality plugin's list.
from .open_meteo_aq import CITIES as _AQ_CITIES

# CAMS European domain is roughly 25°W–45°E, 30°N–72°N. Cities outside it
# return null for every species (verified 2026-09-28), so only the subset of
# the air_quality list inside the domain is requested at all.
CITIES = [(n, la, lo) for (n, la, lo) in _AQ_CITIES
          if 30.0 <= la <= 72.0 and -25.0 <= lo <= 45.0]

SPECIES = ("alder_pollen", "birch_pollen", "grass_pollen",
           "mugwort_pollen", "olive_pollen", "ragweed_pollen")

COVERAGE_NOTE = ("CAMS European domain — Europe only; other regions have "
                 "no data, shown as absent")

LAYER = LayerMeta(
    id="pollen",
    name="Pollen (Europe — CAMS)",
    category="health",
    kind="points",
    source="Open-Meteo CAMS (European domain)",
    source_url="https://air-quality-api.open-meteo.com/v1/air-quality",
    license="Open-Meteo free tier (non-commercial); data CC BY 4.0",
    refresh_s=3600,
    initial_delay_s=210,
    max_staleness_s=21600,  # source updates hourly; 6 h is generous
    units="grains/m³",
    description=("Hourly pollen (alder, birch, grass, mugwort, olive, "
                 "ragweed) at European cities from the CAMS European model. "
                 "Europe only — no data outside the model domain."),
    enabled=True,
    provenance="modelled",  # CAMS model product, not station measurements
)


async def fetch(client: httpx.AsyncClient):
    # One batched multi-coordinate call (open_meteo_temp.py idiom). A failed
    # fetch returns None so the previous cache is kept.
    try:
        r = await client.get(
            LAYER.source_url,
            params={
                "latitude": ",".join(str(la) for _, la, _ in CITIES),
                "longitude": ",".join(str(lo) for _, _, lo in CITIES),
                "current": ",".join(SPECIES),
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[pollen] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[pollen] error: {e} — keeping previous cache")
        return None

    rows = body if isinstance(body, list) else [body]
    if len(rows) != len(CITIES):
        print(f"[pollen] {len(rows)} rows for {len(CITIES)} cities "
              "— response misaligned, keeping previous cache")
        return None

    pts, no_data = [], []
    for (name, lat, lon), row in zip(CITIES, rows):
        cur = (row or {}).get("current") or {}
        species = {s: cur.get(s) for s in SPECIES}
        # All-null means the city sits outside the CAMS domain (or the model
        # has no value there) — EXCLUDE it, never zero it.
        present = {s: v for s, v in species.items() if v is not None}
        if not present:
            no_data.append(name)
            continue
        dominant, dominant_value = max(present.items(), key=lambda kv: kv[1])
        dominant = dominant.removesuffix("_pollen")
        pts.append(point(
            lat=lat, lon=lon,
            id=name.lower().replace(" ", "_"),
            value=dominant_value,
            label=f"{name}: {dominant} {dominant_value} grains/m³",
            city=name,
            dominant=dominant,
            dominant_value=dominant_value,
            species=species,
        ))

    if no_data:
        print(f"[pollen] no data (outside CAMS domain?) for "
              f"{len(no_data)}/{len(CITIES)} cities: {', '.join(no_data)}")
    if not pts:
        print("[pollen] 0 cities with data — keeping previous cache")
        return None

    return {
        "source": "Open-Meteo CAMS (European domain)",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "coverage": COVERAGE_NOTE,
        "units": "grains/m³",
        "count": len(pts),
        "points": pts,
    }


register(LAYER, fetch)
