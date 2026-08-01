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
    # BATCHED: one multi-location request instead of 135 (quota fix —
    # the per-point burst kept tripping Open-Meteo's rate limit and the
    # near-empty grid was silently written over good data).
    points = [(lat, lon) for lat in range(-72, 73, 18) for lon in range(-180, 171, 24)]
    try:
        r = await client.get("https://api.open-meteo.com/v1/forecast",
            params={"latitude": ",".join(str(p[0]) for p in points),
                    "longitude": ",".join(str(p[1]) for p in points),
                    "current": "relative_humidity_2m,dew_point_2m,temperature_2m",
                    "timezone": "UTC"}, timeout=60)
        if r.status_code != 200:
            print(f"[humidity_field] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[humidity_field] error: {e}")
        return None
    rows = body if isinstance(body, list) else [body]
    grid = []
    for (lat, lon), row in zip(points, rows):
        d = (row or {}).get("current", {})
        if d.get("relative_humidity_2m") is None:
            continue
        grid.append({"lat": lat, "lon": lon,
                     "humidity_pct": d.get("relative_humidity_2m"),
                     "dew_point_c": d.get("dew_point_2m"),
                     "temp_c": d.get("temperature_2m"),
                     "time": d.get("time")})
    if len(grid) < len(points) * 0.3:
        print(f"[humidity_field] only {len(grid)}/{len(points)} points — keeping previous cache")
        return None
    return {"source": "Open-Meteo", "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(grid), "grid": grid}

register(LAYER, fetch)
