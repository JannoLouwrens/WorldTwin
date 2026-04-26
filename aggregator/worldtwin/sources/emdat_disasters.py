"""EM-DAT (Emergency Events Database) — natural disaster history since 1900.

The canonical academic disaster dataset, maintained by CRED (UCLouvain). The
raw EM-DAT CSV requires a registered account; OWID re-publishes aggregated
year-by-type slices through their grapher CSV API which we mirror here.

Coverage: 1900 → present, ~26,000 events aggregated by:
  - count of events per disaster type per year
  - deaths per disaster type per year
  - people affected per disaster type per year
  - economic damages USD per disaster type per year

This deepens our disaster picture from EONET's 10-year window to **126 years**
of measured human-relevant disasters — every flood, drought, earthquake,
volcanic event, storm, wildfire, mass movement.

Source: https://www.emdat.be/ (CRED, UCLouvain) via OWID grapher mirror.
License: CC-BY-NC for non-commercial. Cite EM-DAT + OWID.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="emdat_disasters",
    name="EM-DAT Disaster History (1900-present)",
    category="nature",
    kind="raw",
    source="EM-DAT (CRED) via OWID grapher mirror",
    source_url="https://www.emdat.be/",
    license="CC-BY-NC (non-commercial)",
    refresh_s=86400 * 7,  # weekly — OWID refreshes EM-DAT mirror periodically
    initial_delay_s=200,
    description=(
        "126 years of natural disaster history from EM-DAT, the canonical "
        "academic disaster dataset, sourced via OWID grapher CSVs. Counts, "
        "deaths, affected, damage USD per disaster type per year since 1900."
    ),
    requires_key=False,
)


# OWID grapher CSV slugs for EM-DAT-derived metrics. Each returns:
#   Entity,Year,Value
# where Entity is a disaster category name like "All disasters", "Drought",
# "Flood", "Earthquake", "Volcanic activity", "Wildfire", "Storm",
# "Extreme temperature", "Mass movement (dry)", "Glacial lake outburst flood".
SLUGS = [
    ("count",          "number-of-natural-disaster-events"),
    ("deaths",         "deaths-from-natural-disasters-by-type"),
    ("affected",       "total-affected-by-natural-disasters"),
    ("damage_usd",     "damage-costs-from-natural-disasters"),
]


async def _fetch_one(client: httpx.AsyncClient, metric: str, slug: str):
    url = f"https://ourworldindata.org/grapher/{slug}.csv"
    try:
        r = await client.get(url, timeout=60, headers={"User-Agent": "WorldTwin/1.0"})
        if r.status_code != 200:
            print(f"[emdat] {metric} {r.status_code}")
            return metric, []
        reader = csv.DictReader(io.StringIO(r.text))
        rows = []
        for row in reader:
            entity = row.get("Entity", "").strip()
            year = row.get("Year", "").strip()
            # Find the value column — varies by slug
            value_col = next((k for k in row if k not in ("Entity", "Year", "Code")), None)
            if not value_col:
                continue
            val_str = row.get(value_col, "").strip()
            if not val_str or not year.isdigit():
                continue
            try:
                value = float(val_str)
            except ValueError:
                continue
            rows.append({
                "metric": metric,
                "type": entity,
                "year": int(year),
                "value": value,
            })
        return metric, rows
    except Exception as e:
        print(f"[emdat] {metric} error: {e}")
        return metric, []


async def fetch(client: httpx.AsyncClient):
    import asyncio
    results = await asyncio.gather(*[_fetch_one(client, m, s) for m, s in SLUGS])

    # Reshape into events_full = list of {metric, type, year, value}
    # Plus per-type summary timeseries for the live UI
    events_full: list[dict[str, Any]] = []
    by_type: dict[str, dict[str, list]] = {}     # type -> metric -> [{year, value}]
    by_year: dict[int, dict[str, dict[str, float]]] = {}  # year -> type -> metric -> value

    for metric, rows in results:
        for r in rows:
            events_full.append(r)
            t, y, v = r["type"], r["year"], r["value"]
            by_type.setdefault(t, {}).setdefault(metric, []).append({"year": y, "value": v})
            by_year.setdefault(y, {}).setdefault(t, {})[metric] = v

    # Sort each type's metric series chronologically
    for t in by_type:
        for m in by_type[t]:
            by_type[t][m].sort(key=lambda x: x["year"])

    # Latest year row count
    if events_full:
        latest_year = max(r["year"] for r in events_full)
    else:
        latest_year = None

    # Total all-disaster count + deaths in latest year
    headline = {}
    if latest_year and "All disasters" in by_year.get(latest_year, {}):
        headline = {
            "year": latest_year,
            "events_count": by_year[latest_year]["All disasters"].get("count"),
            "deaths": by_year[latest_year]["All disasters"].get("deaths"),
            "affected": by_year[latest_year]["All disasters"].get("affected"),
            "damage_usd": by_year[latest_year]["All disasters"].get("damage_usd"),
        }

    return {
        "source": "EM-DAT via OWID grapher mirror",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "year_range": [
            min(r["year"] for r in events_full) if events_full else None,
            latest_year,
        ],
        "count": len(events_full),
        "headline": headline,
        "events_full": events_full,
        "by_type": by_type,
        "by_year": by_year,
        "types": sorted(by_type.keys()),
    }


register(LAYER, fetch)
