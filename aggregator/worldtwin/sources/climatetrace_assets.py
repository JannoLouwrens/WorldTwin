"""ClimateTRACE v6 — facility-level emissions across all sectors.

Covers oil-gas-production, oil-gas-refining, coal-mining, electricity-generation,
iron-steel, cement, transportation, aluminum, buildings, agriculture, forestry,
manufacturing, waste. Each asset has name, country, sector, emissions, owners,
confidence, centroid (lat/lon), and a Mapbox satellite thumbnail.

CC-BY 4.0, free API, no key. https://api.climatetrace.org/v6/
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="climatetrace_assets",
    name="Global Facility Emissions (ClimateTRACE)",
    category="resources",
    kind="points",
    source="ClimateTRACE v6",
    source_url="https://api.climatetrace.org/v6/assets",
    license="CC BY 4.0",
    refresh_s=86400 * 7,  # weekly
    initial_delay_s=220,
    units="tCO2e / year",
    description=(
        "Facility-level emissions for every sector (oil-gas, coal mining, power, "
        "steel, cement, transport, ag, etc). Assets include name, owner, "
        "lat/lon, emissions, and a Mapbox satellite thumbnail."
    ),
    requires_key=False,
)

# The main sectors we want on the globe, ordered by visibility priority
SECTORS = [
    "oil-and-gas-production",
    "oil-and-gas-refining",
    "coal-mining",
    "electricity-generation",
    "iron-and-steel",
    "cement",
    "aluminum",
    "pulp-and-paper",
    "chemicals",
    "fluorinated-gases",
    "petrochemicals",
    "solid-waste-disposal",
]


async def _fetch_sector(client: httpx.AsyncClient, sector: str, year: int = 2024):
    try:
        r = await client.get(
            "https://api.climatetrace.org/v6/assets",
            params={"sectors": sector, "year": year, "limit": 500},
            timeout=90,
        )
        if r.status_code != 200:
            print(f"[climatetrace] {sector} returned {r.status_code}")
            return []
        return r.json().get("assets", [])
    except Exception as e:
        print(f"[climatetrace] {sector} failed: {e}")
        return []


async def fetch(client: httpx.AsyncClient):
    # Fetch all sectors concurrently (semaphore to be polite)
    sem = asyncio.Semaphore(3)

    async def run(s):
        async with sem:
            rows = await _fetch_sector(client, s)
            await asyncio.sleep(0.2)
            return (s, rows)

    results = await asyncio.gather(*[run(s) for s in SECTORS])

    assets = []
    by_sector: dict[str, list] = {}
    for sector, rows in results:
        by_sector[sector] = []
        for row in rows:
            centroid = row.get("Centroid") or {}
            geom = centroid.get("Geometry") or []
            if len(geom) < 2:
                continue
            lon, lat = geom[0], geom[1]
            if not lon or not lat:
                continue
            # Parse emissions
            emissions_row = (row.get("EmissionsSummary") or [{}])[0]
            qty = emissions_row.get("EmissionsQuantity") or 0
            owners = row.get("Owners") or []
            owner_names = [o.get("CompanyName", "") for o in owners if o.get("CompanyName")]
            asset = {
                "id": row.get("Id"),
                "name": row.get("Name", ""),
                "country": row.get("Country", ""),
                "sector": sector,
                "lat": lat,
                "lon": lon,
                "emissions_tco2e": qty,
                "owners": owner_names[:3],
                "thumbnail": row.get("Thumbnail", ""),
            }
            assets.append(asset)
            by_sector[sector].append(asset)

    # Sort assets by emissions, keep top 5000 global + keep per-sector list of top 500
    assets.sort(key=lambda a: a.get("emissions_tco2e", 0) or 0, reverse=True)
    top_assets = assets[:5000]
    for s in by_sector:
        by_sector[s].sort(key=lambda a: a.get("emissions_tco2e", 0) or 0, reverse=True)
        by_sector[s] = by_sector[s][:500]

    return {
        "source": "ClimateTRACE v6",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "total": len(assets),
        "count": len(top_assets),
        "sectors": SECTORS,
        "assets": top_assets,
        "by_sector": by_sector,
    }


register(LAYER, fetch)
