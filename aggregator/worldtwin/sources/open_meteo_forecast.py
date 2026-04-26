"""Open-Meteo per-point forecast — FUTURE weather across a global lattice.

Open-Meteo offers per-lat/lon hourly forecast for the next 7 days, free
no-key. Same lattice approach as nasa_power.py but pulls FORECAST (next 72h)
instead of REANALYSIS (past 7d). Together they give the lab past + present +
future weather coverage:

  - PAST    : nasa_power.py (MERRA-2 hourly 1981→present)
  - PRESENT : nhc_cyclones, gdacs_events, noaa_sst, swpc_aurora
  - FUTURE  : THIS plugin (next 72h hourly forecast)

Strategy:
  - Same 10°×10° lattice as nasa_power → ~600 lat/lon points
  - For each point, fetch next 72h hourly: temperature_2m, relative_humidity_2m,
    surface_pressure, wind_speed_10m, precipitation, cloud_cover
  - Store as forecast_records[] with the same shape NASA POWER uses so the
    History Store decomposer's grid_records rule picks it up

After 1 day running, the History Store has every grid cell's forecasted
weather for the next 72h, dated by the forecast valid time. Comparing
forecast vs nasa_power's actuals over time lets the user see where models
were right vs wrong — a real differentiator.

Source: https://open-meteo.com/
License: CC-BY 4.0 NonCommercial.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="open_meteo_forecast",
    name="Open-Meteo Forecast Grid (next 72h)",
    category="weather",
    kind="raw",
    source="Open-Meteo (ECMWF + DWD + NOAA blend)",
    source_url="https://open-meteo.com/",
    license="CC-BY 4.0 NonCommercial",
    refresh_s=21600,                        # every 6 hours = 4×/day × 60 cities = 240 calls
    initial_delay_s=380,
    units="various (°C, %, hPa, m/s, mm, %)",
    description=(
        "Global 10°×10° lattice (~600 points) of next-72-hour hourly weather "
        "forecast from Open-Meteo (blend of ECMWF, DWD ICON, NOAA GFS). Pairs "
        "with nasa_power for past + future coverage. Refresh every 3h."
    ),
    requires_key=False,
)

# Open-Meteo free tier caps at 10k calls/day. A 10° lattice = 612 calls/fetch,
# fine for daily but our other Open-Meteo plugins (humidity/pressure/temp/aq)
# share that quota. Switched to a CURATED CITIES list — the 60 most populous
# metros + capitals + key chokepoints. 60 × 8 fetches/day = 480 calls/day.
CITIES = [
    # Megacities
    ("Tokyo",        35.68,  139.76),
    ("Delhi",        28.61,   77.21),
    ("Shanghai",     31.23,  121.47),
    ("São Paulo",   -23.55,  -46.63),
    ("Mexico City",  19.43,  -99.13),
    ("Cairo",        30.04,   31.24),
    ("Mumbai",       19.08,   72.88),
    ("Beijing",      39.90,  116.41),
    ("Dhaka",        23.81,   90.41),
    ("Osaka",        34.69,  135.50),
    ("New York",     40.71,  -74.01),
    ("Karachi",      24.86,   67.00),
    ("Buenos Aires",-34.61,  -58.38),
    ("Chongqing",    29.56,  106.55),
    ("Istanbul",     41.01,   28.98),
    ("Kolkata",      22.57,   88.36),
    ("Manila",       14.60,  120.98),
    ("Lagos",         6.52,    3.38),
    ("Rio de Janeiro",-22.91,-43.17),
    ("Tianjin",      39.34,  117.36),
    ("Guangzhou",    23.13,  113.26),
    ("Moscow",       55.76,   37.62),
    ("Lahore",       31.55,   74.34),
    ("Bangalore",    12.97,   77.59),
    ("Paris",        48.86,    2.35),
    ("Bogotá",        4.71,  -74.07),
    ("Jakarta",      -6.21,  106.85),
    ("Chennai",      13.08,   80.27),
    ("Lima",        -12.05,  -77.04),
    ("Bangkok",      13.76,  100.50),
    ("Seoul",        37.57,  126.98),
    ("Nagoya",       35.18,  136.91),
    ("Hyderabad",    17.39,   78.49),
    ("London",       51.51,   -0.13),
    ("Tehran",       35.69,   51.39),
    ("Chicago",      41.88,  -87.63),
    ("Chengdu",      30.57,  104.07),
    ("Nanjing",      32.06,  118.80),
    ("Wuhan",        30.59,  114.31),
    ("Ho Chi Minh",  10.82,  106.63),
    ("Luanda",       -8.84,   13.23),
    ("Ahmedabad",    23.02,   72.57),
    ("Kuala Lumpur",  3.14,  101.69),
    ("Hong Kong",    22.32,  114.17),
    ("Riyadh",       24.71,   46.68),
    ("Baghdad",      33.31,   44.36),
    ("Santiago",    -33.45,  -70.67),
    ("Surat",        21.17,   72.83),
    ("Madrid",       40.42,   -3.70),
    ("Pune",         18.52,   73.86),
    ("Sydney",      -33.87,  151.21),
    ("Toronto",      43.65,  -79.38),
    ("Berlin",       52.52,   13.41),
    ("Johannesburg",-26.20,   28.04),
    ("Nairobi",      -1.29,   36.82),
    ("Dubai",        25.20,   55.27),
    # Strategic chokepoints (often weather-sensitive)
    ("Suez",         30.07,   32.55),
    ("Hormuz",       26.57,   56.25),
    ("Malacca",       2.75,  101.50),
    ("Panama",        9.08,  -79.68),
]

# 6 forecast variables — match nasa_power's set so the lab can compare
# past vs forecast for the same parameters
PARAMS = [
    "temperature_2m",
    "relative_humidity_2m",
    "surface_pressure",
    "wind_speed_10m",
    "precipitation",
    "cloud_cover",
]
PARAM_LABELS = {
    "temperature_2m":      "Air temperature 2m (°C)",
    "relative_humidity_2m":"Relative humidity 2m (%)",
    "surface_pressure":    "Surface pressure (hPa)",
    "wind_speed_10m":      "Wind speed 10m (m/s)",
    "precipitation":       "Precipitation (mm)",
    "cloud_cover":         "Cloud cover (%)",
}


async def _fetch_point(client: httpx.AsyncClient, lat: float, lon: float,
                       sem: asyncio.Semaphore) -> dict | None:
    """Fetch next-72h hourly forecast for one lat/lon."""
    async with sem:
        try:
            r = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(PARAMS),
                    "forecast_days": 3,        # next 72h
                    "timezone": "UTC",
                },
                timeout=30,
                headers={"User-Agent": "WorldTwin/1.0"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            hourly = data.get("hourly") or {}
            times = hourly.get("time") or []
            if not times:
                return None
            # Reshape into list of {t, param: value} aligned to times
            records = []
            for i, t in enumerate(times):
                for p in PARAMS:
                    series = hourly.get(p) or []
                    if i >= len(series):
                        continue
                    v = series[i]
                    if v is None:
                        continue
                    records.append({"lat": lat, "lon": lon, "t": t, "param": p, "value": v})
            await asyncio.sleep(0.1)  # gentle
            return {"lat": lat, "lon": lon, "records": records}
        except Exception as e:
            print(f"[open_meteo_forecast] ({lat},{lon}) error: {e}")
            return None


async def fetch(client: httpx.AsyncClient):
    print(f"[open_meteo_forecast] {len(CITIES)} cities × {len(PARAMS)} params × next 72h")

    sem = asyncio.Semaphore(5)   # Polite — 5 parallel connections
    results = await asyncio.gather(*[
        _fetch_point(client, lat, lon, sem) for (name, lat, lon) in CITIES
    ])
    # Tag each result with its city name
    for r, (name, lat, lon) in zip(results, CITIES):
        if r is not None:
            r["city"] = name

    successes = [r for r in results if r is not None]

    # Flatten — single grid_records list. Add `city` to each record for richer meta.
    grid_records = []
    for r in successes:
        for rec in r["records"]:
            rec["city"] = r.get("city")
            grid_records.append(rec)

    return {
        "source": "Open-Meteo Forecast (city sample)",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "forecast_horizon_h": 72,
        "city_count": len(CITIES),
        "successful_cities": len(successes),
        "params": PARAMS,
        "param_labels": PARAM_LABELS,
        "count": len(grid_records),
        "grid_records": grid_records,
    }


register(LAYER, fetch)
