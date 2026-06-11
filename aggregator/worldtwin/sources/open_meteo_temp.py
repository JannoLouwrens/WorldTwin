"""Open-Meteo Surface Temperature — global grid sampled hourly.

Returns a 15×9 grid (135 points) of temperature_2m (°C) + apparent_temperature.
Free, no key, CC BY 4.0. Uses the same batch endpoint as wind_sample.py.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="temperature_field",
    name="Surface Temperature — Global Grid",
    category="weather",
    kind="points",
    source="Open-Meteo (ECMWF/GFS blend)",
    source_url="https://open-meteo.com/",
    license="CC BY 4.0",
    refresh_s=1800,
    initial_delay_s=45,
    description="Global 15×9 grid of surface temperature (2m) and apparent temp.",
    requires_key=False,
)

LAT_MIN, LAT_MAX = -72, 72
LON_MIN, LON_MAX = -180, 170
LAT_STEP = 18
LON_STEP = 24


async def fetch(client: httpx.AsyncClient):
    # BATCHED: one multi-location request instead of 135 (quota fix).
    points = [(lat, lon)
              for lat in range(LAT_MIN, LAT_MAX + 1, LAT_STEP)
              for lon in range(LON_MIN, LON_MAX + 1, LON_STEP)]
    try:
        r = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": ",".join(str(p[0]) for p in points),
                "longitude": ",".join(str(p[1]) for p in points),
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,surface_pressure,cloud_cover,weather_code",
                "timezone": "UTC",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[temperature_field] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[temperature_field] error: {e}")
        return None
    rows = body if isinstance(body, list) else [body]
    grid = []
    for (lat, lon), row in zip(points, rows):
        d = (row or {}).get("current", {})
        if d.get("temperature_2m") is None:
            continue
        grid.append({
            "lat": lat,
            "lon": lon,
            "temp_c": d.get("temperature_2m"),
            "feels_c": d.get("apparent_temperature"),
            "humidity": d.get("relative_humidity_2m"),
            "pressure_hpa": d.get("surface_pressure"),
            "cloud_pct": d.get("cloud_cover"),
            "wmo_code": d.get("weather_code"),
            "time": d.get("time"),
        })
    if len(grid) < len(points) * 0.3:
        print(f"[temperature_field] only {len(grid)}/{len(points)} points — keeping previous cache")
        return None

    return {
        "source": "Open-Meteo",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(grid),
        "grid": grid,
        "lat_range": [LAT_MIN, LAT_MAX],
        "lon_range": [LON_MIN, LON_MAX],
    }


register(LAYER, fetch)
