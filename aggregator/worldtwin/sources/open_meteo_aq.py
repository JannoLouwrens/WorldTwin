"""Open-Meteo Air Quality — major world cities.

Un-retired 2026-09-28 through the MASTER_PLAN §4 gate: the 45 per-city
requests are batched into ONE multi-coordinate call (idiom from
open_meteo_temp.py), and the bare `except: pass` that silently dropped
8 cities is gone — a city with no data is now logged and skipped visibly,
and a failed fetch keeps the previous cache instead of shipping a subset.
"""
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
    license="Open-Meteo free tier (non-commercial); data CC BY 4.0",
    refresh_s=1800,
    initial_delay_s=16,
    max_staleness_s=21600,  # source updates hourly; 6 h is generous
    units="US AQI",
    description="Real-time air quality at 45 major world cities from Open-Meteo CAMS.",
    enabled=True,
    provenance="modelled",  # CAMS is a model product, not station measurements
)


async def fetch(client: httpx.AsyncClient):
    # BATCHED: one multi-coordinate request for every city instead of 45
    # parallel calls (MASTER_PLAN §4 weather/air_quality; idiom from
    # open_meteo_temp.py). On any transport/HTTP failure the whole fetch
    # returns None so the previous cache is kept — never a silent subset.
    try:
        r = await client.get(
            LAYER.source_url,
            params={
                "latitude": ",".join(str(la) for _, la, _ in CITIES),
                "longitude": ",".join(str(lo) for _, _, lo in CITIES),
                "current": "us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[air_quality] HTTP {r.status_code} — keeping previous cache")
            return None
        body = r.json()
    except Exception as e:
        print(f"[air_quality] error: {e} — keeping previous cache")
        return None

    rows = body if isinstance(body, list) else [body]
    if len(rows) != len(CITIES):
        print(f"[air_quality] {len(rows)} rows for {len(CITIES)} cities "
              "— response misaligned, keeping previous cache")
        return None

    results_legacy, results_v1, missing = [], [], []
    for (name, lat, lon), row in zip(CITIES, rows):
        cur = (row or {}).get("current") or {}
        aqi = cur.get("us_aqi")
        if aqi is None:
            missing.append(name)  # skipped VISIBLY — was a bare `except: pass`
            continue
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

    if missing:
        print(f"[air_quality] no us_aqi for {len(missing)}/{len(CITIES)} "
              f"cities: {', '.join(missing)}")
    return results_v1, results_legacy


register(LAYER, fetch)
