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
    refresh_s=10800,                        # every 3 hours — forecasts update often
    initial_delay_s=380,
    units="various (°C, %, hPa, m/s, mm, %)",
    description=(
        "Global 10°×10° lattice (~600 points) of next-72-hour hourly weather "
        "forecast from Open-Meteo (blend of ECMWF, DWD ICON, NOAA GFS). Pairs "
        "with nasa_power for past + future coverage. Refresh every 3h."
    ),
    requires_key=False,
)

LAT_STEP = 10
LON_STEP = 10

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
    lats = list(range(-80, 81, LAT_STEP))
    lons = list(range(-180, 180, LON_STEP))
    points = [(la, lo) for la in lats for lo in lons]
    print(f"[open_meteo_forecast] lattice = {len(points)} points × {len(PARAMS)} params × next 72h")

    sem = asyncio.Semaphore(10)
    results = await asyncio.gather(*[_fetch_point(client, la, lo, sem) for la, lo in points])
    successes = [r for r in results if r is not None]

    # Flatten — single grid_records list (same shape as nasa_power) so the
    # History Store decomposer treats it identically.
    grid_records = []
    for r in successes:
        grid_records.extend(r["records"])

    return {
        "source": "Open-Meteo Forecast",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "forecast_horizon_h": 72,
        "lattice_step_deg": LAT_STEP,
        "lattice_points": len(points),
        "successful_points": len(successes),
        "params": PARAMS,
        "param_labels": PARAM_LABELS,
        "count": len(grid_records),
        "grid_records": grid_records,
    }


register(LAYER, fetch)
