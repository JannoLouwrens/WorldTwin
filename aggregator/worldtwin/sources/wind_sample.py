"""Wind field sampling via Open-Meteo — 180-point global grid.

Open-Meteo serves aggregated model data as clean JSON with no key.
We sample an 18x10 lat/lon grid once per hour and expose wind speed
and direction at 10m for the frontend to render as animated arrows
or particles.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


# 18 longitude bins x 10 latitude bins = 180 global sample points
LON_STEP = 20     # -180 → +180 in 20° steps
LAT_STEP = 18     # -80 → +80 in 16° steps
LAT_MIN, LAT_MAX = -80, 80


LAYER = LayerMeta(
    id="wind_sample",
    name="Wind Field (Open-Meteo)",
    category="nature",
    kind="points",
    source="Open-Meteo (ECMWF / GFS blend)",
    source_url="https://open-meteo.com/",
    license="CC BY 4.0",
    refresh_s=3600,   # hourly
    initial_delay_s=60,
    units="m/s, degrees",
    description="Global wind field (speed + direction @ 10m) sampled on an 18×10 lat/lon grid.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    # BATCHED: Open-Meteo accepts comma-separated coordinate lists, so the
    # whole 180-point grid is ONE request instead of 180. The per-point
    # version burned the free-tier daily quota (10k req/day) within hours
    # whenever the container restart loop re-ran every plugin, and the grid
    # then silently shrank to 0-5 points.
    lats = [lat + 0.5 for lat in range(LAT_MIN, LAT_MAX + 1, LAT_STEP)]
    lons = [lon + 0.5 for lon in range(-180, 180, LON_STEP)]
    coords = [(la, lo) for la in lats for lo in lons]
    try:
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": ",".join(str(la) for la, _ in coords),
                "longitude": ",".join(str(lo) for _, lo in coords),
                "current": "windspeed_10m,winddirection_10m,temperature_2m",
                "timezone": "UTC",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[wind_sample] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[wind_sample] error: {e}")
        return None

    # Multi-location responses are a list of per-point objects (single
    # location degrades to one object).
    rows = body if isinstance(body, list) else [body]
    points = []
    for (la, lo), row in zip(coords, rows):
        d = (row or {}).get("current", {})
        if d.get("windspeed_10m") is None:
            continue
        points.append({
            "lat": la,
            "lon": lo,
            "speed_ms": d.get("windspeed_10m"),
            "dir_deg": d.get("winddirection_10m"),
            "temp_c": d.get("temperature_2m"),
        })

    if len(points) < len(coords) * 0.3:
        # Partial/failed grid (rate limit mid-response) — keep previous cache.
        print(f"[wind_sample] only {len(points)}/{len(coords)} grid points — keeping previous cache")
        return None

    return {
        "source": "Open-Meteo global grid",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "grid_lat_step": LAT_STEP,
        "grid_lon_step": LON_STEP,
        "count": len(points),
        "points": points,
    }


register(LAYER, fetch)
