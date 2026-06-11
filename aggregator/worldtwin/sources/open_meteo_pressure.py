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
    # BATCHED: one multi-location request instead of 135 (quota fix).
    points = [(lat, lon) for lat in range(-72, 73, 18) for lon in range(-180, 171, 24)]
    try:
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": ",".join(str(p[0]) for p in points),
                "longitude": ",".join(str(p[1]) for p in points),
                "current": "surface_pressure,cloud_cover",
                "timezone": "UTC",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[pressure_field] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[pressure_field] error: {e}")
        return None
    rows = body if isinstance(body, list) else [body]
    grid = []
    for (lat, lon), row in zip(points, rows):
        d = (row or {}).get("current", {})
        if d.get("surface_pressure") is None:
            continue
        grid.append({
            "lat": lat,
            "lon": lon,
            "pressure_hpa": d.get("surface_pressure"),
            "cloud_pct": d.get("cloud_cover"),
            "time": d.get("time"),
        })
    if len(grid) < len(points) * 0.3:
        print(f"[pressure_field] only {len(grid)}/{len(points)} points — keeping previous cache")
        return None

    return {
        "source": "Open-Meteo",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(grid),
        "grid": grid,
    }


register(LAYER, fetch)
