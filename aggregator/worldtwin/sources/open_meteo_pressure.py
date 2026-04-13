"""Open-Meteo Surface Pressure — global grid sampled hourly.

Returns a 15x9 grid (135 points) of surface_pressure (hPa).
Free, no key, CC BY 4.0.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="pressure_field",
    name="Surface Pressure — Global Grid",
    category="weather",
    kind="points",
    source="Open-Meteo (ECMWF/GFS blend)",
    source_url="https://open-meteo.com/",
    license="CC BY 4.0",
    refresh_s=1800,
    initial_delay_s=55,
    description="Global 15x9 grid of surface pressure (hPa).",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(6)
    points = []
    for lat in range(-72, 73, 18):
        for lon in range(-180, 171, 24):
            points.append((lat, lon))

    async def _one(lat, lon):
        async with sem:
            try:
                r = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "surface_pressure,cloud_cover",
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
                    "pressure_hpa": d.get("surface_pressure"),
                    "cloud_pct": d.get("cloud_cover"),
                    "time": d.get("time"),
                }
            except Exception:
                return None

    results = await asyncio.gather(*[_one(lat, lon) for lat, lon in points])
    grid = [r for r in results if r and r.get("pressure_hpa") is not None]

    return {
        "source": "Open-Meteo",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(grid),
        "grid": grid,
    }


register(LAYER, fetch)
