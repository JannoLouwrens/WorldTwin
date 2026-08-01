"""UN Comtrade annual bilateral flows — the structural backbone.

Auto-detects the latest available year (probes 2025 → 2024 → 2023).
For each of ~30 major importers, fetches the top partner flows for
each commodity in the taxonomy, building a unified flow dataset keyed
by (commodity, from_iso3, to_iso3) with lat/lon and USD value.

Refreshes weekly (annual data).
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _commodities as cdb
from . import _comtrade_common as cc

# Top importers by economic weight — M49 codes. Covers >85% of global trade.
TOP_IMPORTERS = [
    156, 842, 276, 392, 356, 826, 250, 380, 410, 528,  # CN US DE JP IN UK FR IT KR NL
    724, 756, 36, 124, 76, 643, 484, 682, 784, 792,    # ES CH AU CA BR RU MX SA AE TR
    702, 458, 764, 704, 360, 608, 158, 344, 616, 40,   # SG MY TH VN ID PH TW HK PL AT
    56, 620, 300, 578, 246, 208, 752,                  # BE PT GR NO FI DK SE
]


LAYER = LayerMeta(
    id="trade_annual",
    name="Global Trade Flows — Annual (Comtrade)",
    category="resources",
    kind="flows",
    source="UN Comtrade (annual, HS 4-digit)",
    source_url="https://comtradeapi.un.org/public/v1/preview/C/A/HS",
    license="UN Open Data Licence",
    refresh_s=604800,  # weekly
    initial_delay_s=90,
    units="USD",
    description=(
        "Bilateral commodity trade flows (annual) from UN Comtrade. "
        "Auto-detects the freshest available year. Covers 51 commodities "
        "across 8 categories for the top 37 importers."
    ),
    requires_key=False,  # preview tier works
)


async def _fetch_one(client: httpx.AsyncClient, reporter: int, cmd_code: str, year: int, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                params={
                    "reporterCode": reporter,
                    "period": year,
                    "flowCode": "M",    # Imports
                    "cmdCode": cmd_code,
                    "maxRecords": 50,
                },
                timeout=30,
            )
            if r.status_code != 200:
                return []
            rows = r.json().get("data", [])
            await asyncio.sleep(0.3)  # gentle rate
            return rows
        except Exception:
            return []


async def fetch(client: httpx.AsyncClient):
    year = await cc.detect_latest_annual_year(client)

    flows: list[dict[str, Any]] = []
    sem = asyncio.Semaphore(3)  # Comtrade is grumpy with parallelism

    # Heavy backfill: pull last 5 years × ALL HS codes per commodity once,
    # then thereafter only the latest year. Marker file gates the heavy run.
    from pathlib import Path
    marker = Path(os.environ.get("CACHE_DIR", "/cache")) / ".trade_annual_backfill_done"
    needs_backfill = not marker.exists()
    years_to_pull = list(range(year - 4, year + 1)) if needs_backfill else [year]

    # Build the task list
    tasks = []
    for yr in years_to_pull:
        for reporter in TOP_IMPORTERS:
            if reporter not in cc.COUNTRY_COORDS:
                continue
            for commodity in cdb.COMMODITIES:
                cid = commodity[0]
                hs_list = commodity[3]
                # Query EVERY HS4 per commodity (was first only)
                for hs in hs_list:
                    tasks.append(("cid", cid, reporter, hs, yr, _fetch_one(client, reporter, hs, yr, sem)))

    # Execute in chunks to avoid thundering herd
    results = await asyncio.gather(*[t[5] for t in tasks], return_exceptions=True)

    for (tag, cid, reporter, hs, task_year, _), rows in zip(tasks, results):
        if isinstance(rows, Exception) or not rows:
            continue
        to_coords = cc.coords_for(reporter)
        if not to_coords:
            continue
        to_lat, to_lon = to_coords
        to_iso3 = cc.iso3_for(reporter)
        to_name = cc.name_for(reporter)
        for row in rows:
            pcode = row.get("partnerCode")
            value = row.get("primaryValue") or 0
            if not pcode or pcode == 0 or value < 50_000_000:
                # Skip world-aggregates and tiny flows (<$50M)
                continue
            from_coords = cc.coords_for(pcode)
            if not from_coords:
                continue
            from_lat, from_lon = from_coords
            flows.append({
                "commodity": cid,
                "commodity_name": cdb.BY_ID[cid]["name"],
                "category": cdb.BY_ID[cid]["category"],
                "hs": row.get("cmdCode", hs),
                "from_code": pcode,
                "from_iso3": cc.iso3_for(pcode),
                "from_name": cc.name_for(pcode),
                "from_lat": from_lat,
                "from_lon": from_lon,
                "to_code": reporter,
                "to_iso3": to_iso3,
                "to_name": to_name,
                "to_lat": to_lat,
                "to_lon": to_lon,
                "value_usd": float(value),
                "qty": row.get("qty") or 0,
                "year": task_year,
            })

    # Mark backfill done so subsequent fetches only do the latest year
    if needs_backfill and flows:
        try:
            marker.write_text(datetime.now(timezone.utc).isoformat())
        except Exception:
            pass

    flows.sort(key=lambda f: f["value_usd"], reverse=True)

    # Build per-commodity top-N summaries for quick rendering
    by_commodity: dict[str, list[dict[str, Any]]] = {}
    for f in flows:
        by_commodity.setdefault(f["commodity"], []).append(f)
    # Keep top 30 arcs per commodity
    for cid in by_commodity:
        by_commodity[cid] = by_commodity[cid][:30]

    # Keep a global top-500 for the "all commodities" default view
    top_global = flows[:500]

    payload = {
        "source": "UN Comtrade (preview)",
        "year": year,
        "fetched": datetime.now(timezone.utc).isoformat(),
        "total_flows": len(flows),
        "categories": cdb.all_categories(),
        "commodities": [{"id": c["id"], "name": c["name"], "category": c["category"], "unit": c["unit"], "icon": c["icon"]} for c in cdb.all_commodities()],
        "flows": top_global,
        "by_commodity": by_commodity,
    }
    return payload


register(LAYER, fetch)
