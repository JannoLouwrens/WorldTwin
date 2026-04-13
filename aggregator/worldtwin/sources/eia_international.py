"""EIA International Energy — per-country oil/gas/coal/electricity.

Despite the "US agency" name, EIA International has comprehensive per-country
data on production, consumption, and reserves for every major energy source.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

LAYER = LayerMeta(
    id="eia_international",
    name="EIA International — Energy by Country",
    category="resources",
    kind="raw",
    source="US EIA International Energy",
    source_url="https://api.eia.gov/v2/international/",
    license="US Public Domain",
    refresh_s=604800,
    initial_delay_s=185,
    description="Per-country crude oil, natural gas, coal, and electricity production + consumption + reserves.",
    requires_key=True,
    key_env="EIA_API_KEY",
    enabled=bool(EIA_API_KEY),
)

# EIA v2 international uses facets[productId][] and facets[activityId][] syntax
# Correct productIds (verified via live probe 2026-04-11):
#   57 = Crude oil including lease condensate
#   55 = Petroleum and other liquids (proxy for consumption)
#   26 = Natural gas dry
#   7  = Coal (production)
#   2  = Electricity total
# activityId: 1 = Production, 2 = Consumption, 6 = Reserves, 12 = Generation
QUERIES = [
    ("crude_oil_production",   {"facets[productId][]": "57", "facets[activityId][]": "1"}),
    ("crude_oil_consumption",  {"facets[productId][]": "55", "facets[activityId][]": "2"}),
    ("natural_gas_production", {"facets[productId][]": "26", "facets[activityId][]": "1"}),
    ("coal_production",        {"facets[productId][]": "7",  "facets[activityId][]": "1"}),
    ("electricity_generation", {"facets[productId][]": "2",  "facets[activityId][]": "12"}),
]


async def _fetch_one(client: httpx.AsyncClient, name: str, facets: dict[str, str]):
    try:
        params: list = [
            ("api_key", EIA_API_KEY),
            ("frequency", "annual"),
            ("data[0]", "value"),
            ("start", "2022"),
            ("end", "2024"),
            ("length", "5000"),
        ]
        # httpx encodes list-value params correctly when we pass tuples
        for k, v in facets.items():
            params.append((k, v))
        r = await client.get(
            "https://api.eia.gov/v2/international/data/",
            params=params,
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[eia_international] {name} {r.status_code}: {r.text[:120]}")
            return name, []
        body = r.json()
        return name, body.get("response", {}).get("data", []) or []
    except Exception as e:
        print(f"[eia_international] {name} error: {e}")
        return name, []


async def fetch(client: httpx.AsyncClient):
    if not EIA_API_KEY:
        return None
    results = await asyncio.gather(*[_fetch_one(client, n, f) for n, f in QUERIES])

    # Reshape: { countryIso: { metric: latest_value, metric_year: Y } }
    by_country: dict[str, dict[str, Any]] = {}
    for metric_name, rows in results:
        # Group rows by country, keep the latest year
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            country = row.get("countryRegionName") or row.get("country") or row.get("name", "")
            iso = row.get("countryRegionId") or ""
            year = row.get("period", "")
            value = row.get("value")
            if not country or value in (None, "", "--", "N/A", "NA", "null"):
                continue
            try:
                fv = float(value)
            except (ValueError, TypeError):
                continue
            key = iso or country
            cur = latest.get(key)
            if not cur or year > cur.get("year", ""):
                latest[key] = {
                    "year": year,
                    "value": fv,
                    "unit": row.get("unit") or row.get("unitName", ""),
                    "country": country,
                    "iso": iso,
                }
        for k, v in latest.items():
            rec = by_country.setdefault(k, {"country": v["country"], "iso": v["iso"]})
            rec[metric_name] = v["value"]
            rec[f"{metric_name}_year"] = v["year"]
            rec[f"{metric_name}_unit"] = v["unit"]

    return {
        "source": "EIA International v2",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(by_country),
        "countries": by_country,
    }


register(LAYER, fetch)
