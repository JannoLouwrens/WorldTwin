"""Pulse Mode — directional change radar.

For each country, compute "how worrying is this right now" on 5 dimensions:
  - water_stress      (high BWS = red)
  - food_security     (high IPC phase = red)
  - conflict_intensity (UCDP last-30-day fatality count vs 12mo baseline = red if spiking)
  - fire_activity      (FIRMS last-24h vs 30-day baseline = red if spiking)
  - grid_carbon        (high gCO2/kWh = red)

Outputs a composite "pulse score" (0-100) per country that the frontend
renders as a choropleth on the Pulse mode — red regions are getting worse,
green are fine.

Gives the user the "apocalypse is coming far away" feeling.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))


LAYER = LayerMeta(
    id="pulse_mode",
    name="Pulse Mode — directional change radar",
    category="meta",
    kind="raw",
    source="Aggregated across cached sources",
    source_url="internal",
    license="Aggregated",
    refresh_s=1800,  # 30 min
    initial_delay_s=500,
    description=(
        "Per-country composite 'how worrying' score across water stress, "
        "food security, conflict intensity, fire activity, and grid carbon. "
        "Powers the apocalypse-radar Pulse mode."
    ),
    requires_key=False,
)


def _read_cache(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    # Read existing caches
    deep = _read_cache("country_deep_dive") or {}
    deep_countries = deep.get("countries") or {}
    ucdp = _read_cache("ucdp_ged") or {}
    fires = _read_cache("fires") or []

    # Conflict intensity per country: sum fatalities in last 30 days
    cutoff_30 = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    cutoff_365 = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    conflict_30: dict[str, int] = defaultdict(int)
    conflict_365: dict[str, int] = defaultdict(int)
    for e in ucdp.get("events", []):
        country = e.get("country", "")
        if not country:
            continue
        best = e.get("best", 0) or 0
        d = e.get("date_start", "")
        if d >= cutoff_30:
            conflict_30[country] += best
        if d >= cutoff_365:
            conflict_365[country] += best

    # Fire activity — simple last-day count per 5-degree grid cell
    # Then map each country centroid's cell to get relative intensity
    fire_grid: dict[tuple, int] = defaultdict(int)
    for f in (fires if isinstance(fires, list) else []):
        lat = f.get("lat")
        lon = f.get("lon")
        if lat is None or lon is None:
            continue
        cell = (int(lat // 5), int(lon // 5))
        fire_grid[cell] += 1

    # Build per-country pulse
    out: dict[str, dict[str, Any]] = {}
    for iso3, rec in deep_countries.items():
        meta = rec.get("meta") or {}
        water = rec.get("water") or {}
        food = rec.get("food") or {}
        electricity = rec.get("electricity") or {}
        bws = water.get("baseline_water_stress")
        ipc = food.get("ipc_phase")
        gen = electricity.get("carbon_intensity_gco2_kwh")
        country_name = meta.get("name", iso3)

        # 0-100 severity per component
        water_score = int((bws / 5) * 100) if bws is not None else None
        food_score = int((ipc / 5) * 100) if ipc is not None else None

        # Conflict: fatalities in last 30 days, log-scaled to 0-100
        c30 = 0
        for k, v in conflict_30.items():
            if k.lower() == (country_name or "").lower():
                c30 = v
                break
        conflict_score = None
        if c30 > 0:
            import math
            conflict_score = min(100, int(math.log10(max(1, c30)) * 30 + 10))

        # Grid carbon: 0 (green) = 0, 800 gCO2/kWh (coal) = 100
        grid_score = None
        if gen is not None:
            grid_score = min(100, int(gen / 8))

        # Fire: by country centroid 5° cell
        lat = meta.get("lat")
        lon = meta.get("lon")
        fire_score = None
        if lat is not None and lon is not None:
            cell = (int(lat // 5), int(lon // 5))
            cnt = fire_grid.get(cell, 0)
            if cnt > 0:
                import math
                fire_score = min(100, int(math.log10(max(1, cnt)) * 25))

        scores = {
            "water": water_score,
            "food": food_score,
            "conflict": conflict_score,
            "grid_carbon": grid_score,
            "fires": fire_score,
        }
        # Composite — average of non-null components
        vals = [v for v in scores.values() if v is not None]
        composite = sum(vals) // len(vals) if vals else 0

        # "Trend arrow" heuristic — need historical deltas. For v1 we flag
        # "worsening" if (a) water_stress ≥ 4 or (b) food phase ≥ 3 or
        # (c) conflict last-30 > 0.1 * conflict last-365, else "stable"
        trend = "stable"
        if (bws or 0) >= 4 or (ipc or 0) >= 3 or (c30 > 0 and c30 > 0.1 * conflict_365.get(country_name, 1)):
            trend = "worsening"
        elif composite <= 20:
            trend = "ok"

        out[iso3] = {
            "iso3": iso3,
            "name": country_name,
            "lat": lat,
            "lon": lon,
            "composite": composite,
            "trend": trend,
            "scores": scores,
            "details": {
                "water_stress_score": bws,
                "water_stress_label": water.get("stress_description"),
                "food_ipc_phase": ipc,
                "food_ipc_description": food.get("ipc_description"),
                "conflict_fatalities_30d": c30,
                "grid_carbon_gco2_kwh": gen,
                "fire_count_nearby": fire_score,
            },
        }

    # Top-N most concerning
    top_concerning = sorted(out.values(), key=lambda c: c["composite"], reverse=True)[:30]

    return {
        "source": "pulse_mode",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(out),
        "countries": out,
        "top_concerning": top_concerning,
    }


register(LAYER, fetch)
