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


async def _fetch_one(client: httpx.AsyncClient, lat: float, lon: float, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "windspeed_10m,winddirection_10m,temperature_2m",
                    "timezone": "UTC",
                },
                timeout=20,
            )
            if r.status_code != 200:
                return None
            d = r.json().get("current", {})
            return {
                "lat": lat,
                "lon": lon,
                "speed_ms": d.get("windspeed_10m"),
                "dir_deg": d.get("winddirection_10m"),
                "temp_c": d.get("temperature_2m"),
            }
        except Exception:
            return None


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(8)
    tasks = []
    lats = list(range(LAT_MIN, LAT_MAX + 1, LAT_STEP))
    lons = list(range(-180, 180, LON_STEP))
    for lat in lats:
        for lon in lons:
            tasks.append(_fetch_one(client, lat + 0.5, lon + 0.5, sem))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    points = [r for r in results if isinstance(r, dict) and r.get("speed_ms") is not None]

    return {
        "source": "Open-Meteo global grid",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "grid_lat_step": LAT_STEP,
        "grid_lon_step": LON_STEP,
        "count": len(points),
        "points": points,
    }


register(LAYER, fetch)
