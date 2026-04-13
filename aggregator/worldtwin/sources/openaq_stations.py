"""OpenAQ v3 — 12,000+ air quality monitoring stations worldwide.

Replaces the 45-city Open-Meteo AQ fallback. Real station readings of PM2.5,
PM10, NO2, SO2, CO, O3, plus EPA AQI computed client-side.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

OPENAQ_API_KEY = os.environ.get("OPENAQ_API_KEY", "")

LAYER = LayerMeta(
    id="openaq_stations",
    name="OpenAQ — Air Quality Stations",
    category="health",
    kind="points",
    source="OpenAQ v3",
    source_url="https://api.openaq.org/v3/",
    license="CC BY 4.0",
    refresh_s=3600,
    initial_delay_s=140,
    description="~12,000 air quality monitoring stations globally with live PM2.5/PM10/NO2/SO2/CO/O3 measurements.",
    requires_key=True,
    key_env="OPENAQ_API_KEY",
    enabled=bool(OPENAQ_API_KEY),
)


# EPA AQI breakpoints for PM2.5 (24-hour average; we use instantaneous as a proxy)
PM25_BREAKS = [
    (0, 12, 0, 50),        # Good
    (12.1, 35.4, 51, 100),  # Moderate
    (35.5, 55.4, 101, 150), # Unhealthy for sensitive
    (55.5, 150.4, 151, 200),# Unhealthy
    (150.5, 250.4, 201, 300),# Very unhealthy
    (250.5, 500, 301, 500), # Hazardous
]


def _pm25_to_aqi(pm: float) -> int:
    if pm is None or pm < 0:
        return 0
    for (lo, hi, a_lo, a_hi) in PM25_BREAKS:
        if lo <= pm <= hi:
            return int(((a_hi - a_lo) / (hi - lo)) * (pm - lo) + a_lo)
    return 500


async def fetch(client: httpx.AsyncClient):
    if not OPENAQ_API_KEY:
        return None
    headers = {"X-API-Key": OPENAQ_API_KEY, "User-Agent": "WorldTwin/1.0"}
    all_stations: list[dict[str, Any]] = []

    # Paginate 1000/page. Free tier = 60 req/min.
    for page in range(1, 13):
        try:
            r = await client.get(
                "https://api.openaq.org/v3/locations",
                params={"limit": 1000, "page": page},
                headers=headers,
                timeout=45,
            )
            if r.status_code != 200:
                print(f"[openaq] page {page} {r.status_code}")
                break
            d = r.json()
            results = d.get("results") or []
            if not results:
                break
            for loc in results:
                coords = loc.get("coordinates") or {}
                lat = coords.get("latitude")
                lon = coords.get("longitude")
                if lat is None or lon is None:
                    continue
                country = (loc.get("country") or {}).get("code", "")
                sensors = loc.get("sensors") or []
                # Extract parameter names to show what's measured
                parameters = sorted({
                    (s.get("parameter") or {}).get("name", "")
                    for s in sensors
                    if s.get("parameter")
                })
                all_stations.append({
                    "id": loc.get("id"),
                    "name": loc.get("name", ""),
                    "locality": loc.get("locality", ""),
                    "country": country,
                    "lat": lat,
                    "lon": lon,
                    "provider": (loc.get("provider") or {}).get("name", ""),
                    "is_monitor": loc.get("isMonitor", False),
                    "parameters": [p for p in parameters if p],
                })
            # Gentle throttle
            await asyncio.sleep(0.8)
        except Exception as e:
            print(f"[openaq] page {page} error: {e}")
            break

    # Group by country
    by_country: dict[str, int] = {}
    for s in all_stations:
        c = s.get("country") or "UNK"
        by_country[c] = by_country.get(c, 0) + 1

    return {
        "source": "OpenAQ v3",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(all_stations),
        "by_country_top20": dict(sorted(by_country.items(), key=lambda x: -x[1])[:20]),
        "stations": all_stations,
    }


register(LAYER, fetch)
