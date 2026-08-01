"""NASA POWER — global gridded hourly weather, 1981→present.

NASA's Prediction Of Worldwide Energy Resources project. Same MERRA-2
reanalysis data climate scientists publish on. Free, no auth, no rate
limit beyond polite citizenship.

Replaces our broken Open-Meteo grid plugins (humidity_field, pressure_field,
temperature_field, noaa_sst) with one canonical source.

Strategy:
  - Sample a 5° × 5° lattice = 73 × 37 = 2,701 lat/lon points covering Earth
  - Pull the past 30 days of HOURLY readings for 6 core parameters per point
  - Store the lattice as a single cache + decompose to per-(lat,lon,t,param) rows
    in the History Store

After ~30 days running, the History Store contains hourly weather for every
5°x5° cell of Earth. On-demand POWER queries can backfill any historic period
the user asks about (1981-present).

Source: https://power.larc.nasa.gov/
License: Public Domain (US Gov).
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
    id="nasa_power",
    name="NASA POWER — Hourly Weather Grid (1981→present)",
    category="weather",
    kind="raw",
    source="NASA POWER (MERRA-2 reanalysis + CERES)",
    source_url="https://power.larc.nasa.gov/",
    license="Public Domain (US Government)",
    refresh_s=86400,           # daily lattice refresh
    initial_delay_s=320,
    units="various (°C, %, kPa, m/s, mm/hr)",
    description=(
        "Global 5°×5° lattice (~2,700 points) of hourly weather from NASA POWER "
        "MERRA-2: temperature, humidity, pressure, wind, precipitation, solar. "
        "Past 30-day window per fetch; History Store accumulates indefinitely. "
        "Replaces the broken Open-Meteo humidity/pressure/temperature grids."
    ),
    requires_key=False,
)

# Lattice — 5° spacing covers Earth in 73 lon × 37 lat = 2701 points.
# Reduce to 10° (37 × 19 = 703 points) for the live cache to keep API
# call count reasonable. The History Store will accumulate density over
# weeks/months of fetches.
LAT_STEP = 10
LON_STEP = 10

# 6 parameters covering the most common weather questions
PARAMS = ["T2M", "RH2M", "PS", "WS10M", "PRECTOTCORR", "ALLSKY_SFC_SW_DWN"]
PARAM_LABELS = {
    "T2M":               "Air temperature 2m (°C)",
    "RH2M":              "Relative humidity 2m (%)",
    "PS":                "Surface pressure (kPa)",
    "WS10M":             "Wind speed 10m (m/s)",
    "PRECTOTCORR":       "Precipitation (mm/hr)",
    "ALLSKY_SFC_SW_DWN": "Solar radiation (kWh/m²/day)",
}


async def _fetch_point(client: httpx.AsyncClient, lat: float, lon: float,
                       start: str, end: str, sem: asyncio.Semaphore) -> dict | None:
    """Fetch hourly readings for one lat/lon over the [start, end] window.
    Returns {lat, lon, hourly: { 'YYYYMMDDHH': {param: value, ...} }} or None.
    """
    async with sem:
        try:
            r = await client.get(
                "https://power.larc.nasa.gov/api/temporal/hourly/point",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start": start,
                    "end": end,
                    "parameters": ",".join(PARAMS),
                    "community": "RE",
                    "format": "JSON",
                },
                timeout=60,
                headers={"User-Agent": "WorldTwin/1.0"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            params_data = (data.get("properties") or {}).get("parameter") or {}
            # params_data shape: { 'T2M': {'YYYYMMDDHH': value, ...}, ... }
            # Reshape to: hourly = { 'YYYYMMDDHH': {param: value, ...} }
            hourly: dict[str, dict[str, float]] = {}
            for param, by_time in params_data.items():
                if not isinstance(by_time, dict):
                    continue
                for t_str, value in by_time.items():
                    if not isinstance(value, (int, float)) or value <= -999:
                        continue
                    hourly.setdefault(t_str, {})[param] = float(value)
            await asyncio.sleep(0.15)  # politeness
            return {"lat": lat, "lon": lon, "hourly": hourly}
        except Exception as e:
            print(f"[nasa_power] ({lat},{lon}) error: {e}")
            return None


async def fetch(client: httpx.AsyncClient):
    end = datetime.now(timezone.utc)
    # Window: past 7 days on first run after deploy; refresh window is 7 days
    # so each daily fetch overlaps the previous by 6 days but PRIMARY KEY
    # idempotency in the History Store dedupes naturally.
    start = end - timedelta(days=7)
    start_str = start.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    # Build the lattice (lat 90 to -90, lon -180 to 180 step 10° each)
    lats = list(range(-80, 81, LAT_STEP))   # skip poles to avoid bad data
    lons = list(range(-180, 180, LON_STEP))
    points = [(la, lo) for la in lats for lo in lons]
    print(f"[nasa_power] lattice = {len(points)} points × {len(PARAMS)} params × past 7 days")

    sem = asyncio.Semaphore(6)   # be polite — NASA POWER suggests <10 concurrent
    results = await asyncio.gather(*[
        _fetch_point(client, lat, lon, start_str, end_str, sem) for lat, lon in points
    ])
    successes = [r for r in results if r is not None]

    # Reshape into an array the History Store decomposer can walk
    grid_records = []
    for r in successes:
        for t_str, params_at_t in r["hourly"].items():
            for param, value in params_at_t.items():
                grid_records.append({
                    "lat": r["lat"],
                    "lon": r["lon"],
                    "t": t_str,    # YYYYMMDDHH
                    "param": param,
                    "value": value,
                })

    return {
        "source": "NASA POWER MERRA-2",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "window_start": start_str,
        "window_end": end_str,
        "lattice_step_deg": LAT_STEP,
        "lattice_points": len(points),
        "successful_points": len(successes),
        "params": PARAMS,
        "param_labels": PARAM_LABELS,
        "count": len(grid_records),
        "grid_records": grid_records,
    }


register(LAYER, fetch)
