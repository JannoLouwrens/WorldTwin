"""Open-Meteo Air Quality — major world cities."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

CITIES = [
    ("Beijing", 39.9, 116.4), ("Delhi", 28.6, 77.2), ("Mumbai", 19.1, 72.9),
    ("Shanghai", 31.2, 121.5), ("Dhaka", 23.8, 90.4), ("Cairo", 30.0, 31.2),
    ("Lagos", 6.5, 3.4), ("Istanbul", 41.0, 29.0), ("Karachi", 24.9, 67.0),
    ("Bangkok", 13.8, 100.5), ("Jakarta", -6.2, 106.8), ("Tokyo", 35.7, 139.7),
    ("Seoul", 37.6, 127.0), ("Mexico City", 19.4, -99.1), ("Sao Paulo", -23.5, -46.6),
    ("Moscow", 55.8, 37.6), ("London", 51.5, -0.1), ("Paris", 48.9, 2.3),
    ("Berlin", 52.5, 13.4), ("Madrid", 40.4, -3.7), ("New York", 40.7, -74.0),
    ("Los Angeles", 34.1, -118.2), ("Chicago", 41.9, -87.6), ("Sydney", -33.9, 151.2),
    ("Johannesburg", -26.2, 28.0), ("Cape Town", -33.9, 18.4), ("Nairobi", -1.3, 36.8),
    ("Riyadh", 24.7, 46.7), ("Dubai", 25.2, 55.3), ("Tehran", 35.7, 51.4),
    ("Lahore", 31.5, 74.3), ("Kolkata", 22.6, 88.4), ("Manila", 14.6, 121.0),
    ("Hanoi", 21.0, 105.8), ("Toronto", 43.7, -79.4), ("Singapore", 1.3, 103.8),
    ("Addis Ababa", 9.0, 38.7), ("Kinshasa", -4.3, 15.3), ("Baghdad", 33.3, 44.4),
    ("Kabul", 34.5, 69.2), ("Warsaw", 52.2, 21.0), ("Bucharest", 44.4, 26.1),
    ("Buenos Aires", -34.6, -58.4), ("Lima", -12.0, -77.0), ("Bogota", 4.7, -74.1),
]

LAYER = LayerMeta(
    id="air_quality",
    name="Air Quality (major cities)",
    category="health",
    kind="points",
    source="Open-Meteo CAMS",
    source_url="https://air-quality-api.open-meteo.com/v1/air-quality",
    license="Free for non-commercial use",
    refresh_s=1800,
    initial_delay_s=16,
    units="US AQI",
    description="Real-time air quality at 45 major world cities from Open-Meteo CAMS.",
)


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(10)
    results_legacy = []
    results_v1 = []

    async def fetch_one(name: str, lat: float, lon: float):
        async with sem:
            try:
                r = await client.get(
                    LAYER.source_url,
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide",
                    },
                    timeout=20,
                )
                if r.status_code != 200:
                    return
                cur = r.json().get("current", {})
                aqi = cur.get("us_aqi")
                if aqi is None:
                    return
                legacy = {
                    "name": name, "lat": lat, "lon": lon,
                    "aqi": aqi,
                    "pm25": cur.get("pm2_5"),
                    "pm10": cur.get("pm10"),
                    "no2": cur.get("nitrogen_dioxide"),
                    "o3": cur.get("ozone"),
                    "so2": cur.get("sulphur_dioxide"),
                    "co": cur.get("carbon_monoxide"),
                }
                results_legacy.append(legacy)
                results_v1.append(point(
                    lat=lat, lon=lon,
                    id=name.lower().replace(" ", "_"),
                    value=aqi,
                    label=f"{name}: AQI {aqi}",
                    **{k: legacy[k] for k in ("pm25", "pm10", "no2", "o3", "so2", "co")},
                ))
            except Exception:
                pass

    await asyncio.gather(*[fetch_one(n, la, lo) for (n, la, lo) in CITIES])
    return results_v1, results_legacy


register(LAYER, fetch)
