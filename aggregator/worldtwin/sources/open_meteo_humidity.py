"""Open-Meteo Humidity — global grid.
Returns 15x9 grid (135 pts) of relative_humidity_2m + dew_point_2m.
Free, no key, CC BY 4.0.
"""
import asyncio
from datetime import datetime, timezone
import httpx
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="humidity_field",
    name="Humidity — Global Grid",
    category="weather",
    kind="points",
    source="Open-Meteo (ECMWF/GFS blend)",
    source_url="https://open-meteo.com/",
    license="CC BY 4.0",
    refresh_s=1800,
    initial_delay_s=65,
    description="Global 15x9 grid of relative humidity (%) and dew point.",
    requires_key=False,
)

async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(6)
    points = [(lat, lon) for lat in range(-72, 73, 18) for lon in range(-180, 171, 24)]

    async def _one(lat, lon):
        async with sem:
            try:
                r = await client.get("https://api.open-meteo.com/v1/forecast",
                    params={"latitude": lat, "longitude": lon,
                            "current": "relative_humidity_2m,dew_point_2m,temperature_2m",
                            "timezone": "UTC"}, timeout=20)
                if r.status_code != 200: return None
                d = r.json().get("current", {})
                return {"lat": lat, "lon": lon,
                        "humidity_pct": d.get("relative_humidity_2m"),
                        "dew_point_c": d.get("dew_point_2m"),
                        "temp_c": d.get("temperature_2m"),
                        "time": d.get("time")}
            except Exception:
                return None

    results = await asyncio.gather(*[_one(lat, lon) for lat, lon in points])
    grid = [r for r in results if r and r.get("humidity_pct") is not None]
    return {"source": "Open-Meteo", "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(grid), "grid": grid}

register(LAYER, fetch)
