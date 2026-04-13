"""NOAA SWPC OVATION Aurora Forecast + space weather summary.

Free, no key, public domain. Refresh every 5 minutes.
The aurora oval is a 1-degree grid of probabilities over both poles.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="swpc_aurora",
    name="Aurora Oval + Space Weather (NOAA SWPC)",
    category="space",
    kind="raw",
    source="NOAA Space Weather Prediction Center",
    source_url="https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
    license="Public Domain (US Gov)",
    refresh_s=300,
    initial_delay_s=70,
    description=(
        "OVATION aurora oval probability grid (~65k points) + planetary "
        "K-index, G-scale storm level, solar wind plasma, and X-ray flux."
    ),
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    payload: dict[str, Any] = {
        "fetched": datetime.now(timezone.utc).isoformat(),
    }
    # Aurora oval
    try:
        r = await client.get(
            "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json",
            timeout=30,
        )
        if r.status_code == 200:
            d = r.json()
            coords = d.get("coordinates", [])
            # Downsample — the full 65k grid is overkill for a globe overlay.
            # Keep only points with nonzero probability, which is ~10-15% of the grid.
            filtered = [c for c in coords if c[2] > 0]
            payload["aurora"] = {
                "forecast_time": d.get("Forecast Time"),
                "observation_time": d.get("Observation Time"),
                "data_format": d.get("Data Format"),
                "points": filtered,
                "count": len(filtered),
            }
    except Exception as e:
        payload["aurora_error"] = str(e)
    # K-index
    try:
        r = await client.get(
            "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
            timeout=15,
        )
        if r.status_code == 200:
            arr = r.json()
            if len(arr) > 1:
                latest = arr[-1]
                header = arr[0]
                rec = dict(zip(header, latest))
                payload["kp_index"] = rec
    except Exception:
        pass
    # G-scale storm level
    try:
        r = await client.get(
            "https://services.swpc.noaa.gov/products/noaa-scales.json",
            timeout=15,
        )
        if r.status_code == 200:
            payload["scales"] = r.json()
    except Exception:
        pass
    # Solar wind plasma (latest sample)
    try:
        r = await client.get(
            "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
            timeout=15,
        )
        if r.status_code == 200:
            arr = r.json()
            if len(arr) > 1:
                latest = arr[-1]
                header = arr[0]
                payload["solar_wind"] = dict(zip(header, latest))
    except Exception:
        pass
    return payload


register(LAYER, fetch)
