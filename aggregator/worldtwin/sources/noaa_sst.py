"""Open-Meteo Marine SST — expanded ocean grid (~200 points).
Samples sea surface temperature across all major oceans at ~10-15 degree spacing.
Free, no key.
"""
import asyncio
from datetime import datetime, timezone
import httpx
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="noaa_sst",
    name="Sea Surface Temperature (expanded)",
    category="weather",
    kind="points",
    source="Open-Meteo Marine API",
    source_url="https://open-meteo.com/en/docs/marine-weather-api",
    license="CC BY 4.0",
    refresh_s=43200,
    initial_delay_s=80,
    description="Sea surface temperature + wave height sampled at ~200 ocean points worldwide.",
    requires_key=False,
)

# Dense ocean grid avoiding major land masses
OCEAN_POINTS = []
# Atlantic Ocean
for lat in range(-50, 65, 10):
    for lon in range(-70, 5, 15):
        OCEAN_POINTS.append((lat, lon))
# East Pacific
for lat in range(-50, 60, 10):
    for lon in range(-170, -75, 15):
        OCEAN_POINTS.append((lat, lon))
# West Pacific
for lat in range(-50, 60, 10):
    for lon in range(100, 180, 15):
        OCEAN_POINTS.append((lat, lon))
# Indian Ocean
for lat in range(-45, 25, 10):
    for lon in range(40, 110, 15):
        OCEAN_POINTS.append((lat, lon))
# Arctic / Southern Ocean belt
for lon in range(-180, 180, 30):
    OCEAN_POINTS.append((70, lon))
    OCEAN_POINTS.append((-60, lon))


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(8)

    async def _one(lat, lon):
        async with sem:
            try:
                r = await client.get("https://marine-api.open-meteo.com/v1/marine",
                    params={"latitude": lat, "longitude": lon,
                            "current": "ocean_current_velocity,ocean_current_direction",
                            "hourly": "sea_surface_temperature,wave_height",
                            "forecast_days": 1, "timezone": "UTC"}, timeout=20)
                if r.status_code != 200:
                    return None
                d = r.json()
                hourly = d.get("hourly", {})
                sst_vals = hourly.get("sea_surface_temperature", [])
                wave_vals = hourly.get("wave_height", [])
                sst = next((v for v in reversed(sst_vals) if v is not None), None)
                wave = next((v for v in reversed(wave_vals) if v is not None), None)
                if sst is None:
                    return None
                cur = d.get("current", {})
                return {"lat": lat, "lon": lon, "sst_c": sst,
                        "wave_height_m": wave,
                        "current_velocity": cur.get("ocean_current_velocity"),
                        "current_direction": cur.get("ocean_current_direction")}
            except Exception:
                return None

    results = await asyncio.gather(*[_one(lat, lon) for lat, lon in OCEAN_POINTS])
    grid = [r for r in results if r is not None]
    return {"source": "Open-Meteo Marine", "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(grid), "grid": grid}

register(LAYER, fetch)
