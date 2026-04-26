"""UN Comtrade monthly bilateral flows — last 6 months rolling.

Monthly Comtrade data typically lags 4-7 months behind realtime, but
it lets us detect trend divergence from the annual baseline.

The frontend uses this to highlight arcs growing/shrinking vs annual.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _commodities as cdb
from . import _comtrade_common as cc

# Subset of top importers to keep under rate limits
TOP_MONTHLY_IMPORTERS = [
    156, 842, 276, 392, 356, 826, 250, 380, 410, 528, 702, 158
]
# Subset of key commodities for monthly tracking
MONTHLY_COMMODITIES = [
    "crude_oil", "natural_gas", "wheat", "soybeans", "iron_ore",
    "copper", "gold", "semiconductors", "cars", "coffee",
]


LAYER = LayerMeta(
    id="trade_monthly",
    name="Monthly Trade Flows (Comtrade)",
    category="resources",
    kind="flows",
    source="UN Comtrade (monthly, HS 4-digit)",
    source_url="https://comtradeapi.un.org/public/v1/preview/C/M/HS",
    license="UN Open Data Licence",
    refresh_s=86400,  # daily
    initial_delay_s=450,
    units="USD",
    description=(
        "Monthly bilateral flows for 10 key commodities across 12 top importers. "
        "Used to detect trend divergence vs annual baseline."
    ),
    requires_key=False,
)


async def _probe_latest_month(client: httpx.AsyncClient) -> str:
    """Walk backwards month-by-month from 4 months ago until we find data.
    Returns YYYYMM string.
    """
    now = datetime.now(timezone.utc)
    # Try from 4 months back to 12 months back
    for offset in range(4, 13):
        year = now.year
        month = now.month - offset
        while month <= 0:
            month += 12
            year -= 1
        period = f"{year}{month:02d}"
        try:
            r = await client.get(
                "https://comtradeapi.un.org/public/v1/preview/C/M/HS",
                params={
                    "reporterCode": 842,
                    "period": period,
                    "flowCode": "M",
                    "cmdCode": "2709",
                    "maxRecords": 1,
                },
                timeout=20,
            )
            if r.status_code == 200 and r.json().get("count", 0) > 0:
                return period
        except Exception:
            continue
    return ""


async def _fetch_one(client: httpx.AsyncClient, reporter: int, hs: str, period: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                "https://comtradeapi.un.org/public/v1/preview/C/M/HS",
                params={
                    "reporterCode": reporter,
                    "period": period,
                    "flowCode": "M",
                    "cmdCode": hs,
                    "maxRecords": 500,    # widened from 20 — full bilateral partners
                },
                timeout=30,
            )
            if r.status_code != 200:
                return []
            await asyncio.sleep(0.5)
            return r.json().get("data", [])
        except Exception:
            return []


async def fetch(client: httpx.AsyncClient):
    latest = await _probe_latest_month(client)
    if not latest:
        return None

    sem = asyncio.Semaphore(2)
    tasks = []
    meta = []
    for reporter in TOP_MONTHLY_IMPORTERS:
        for cid in MONTHLY_COMMODITIES:
            commodity = cdb.BY_ID[cid]
            hs = commodity["hs"][0]
            tasks.append(_fetch_one(client, reporter, hs, latest, sem))
            meta.append((reporter, cid, hs))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    flows: list[dict[str, Any]] = []
    for (reporter, cid, hs), rows in zip(meta, results):
        if isinstance(rows, Exception) or not rows:
            continue
        to_coords = cc.coords_for(reporter)
        if not to_coords:
            continue
        to_lat, to_lon = to_coords
        for row in rows:
            pcode = row.get("partnerCode")
            value = row.get("primaryValue") or 0
            if not pcode or pcode == 0 or value < 1_000_000:
                continue
            from_coords = cc.coords_for(pcode)
            if not from_coords:
                continue
            from_lat, from_lon = from_coords
            flows.append({
                "commodity": cid,
                "commodity_name": cdb.BY_ID[cid]["name"],
                "category": cdb.BY_ID[cid]["category"],
                "hs": hs,
                "from_code": pcode,
                "from_iso3": cc.iso3_for(pcode),
                "from_name": cc.name_for(pcode),
                "from_lat": from_lat,
                "from_lon": from_lon,
                "to_code": reporter,
                "to_iso3": cc.iso3_for(reporter),
                "to_name": cc.name_for(reporter),
                "to_lat": to_lat,
                "to_lon": to_lon,
                "value_usd": float(value),
                "qty": row.get("qty") or 0,
                "period": latest,
            })

    flows.sort(key=lambda f: f["value_usd"], reverse=True)

    payload = {
        "source": "UN Comtrade monthly (preview)",
        "period": latest,
        "fetched": datetime.now(timezone.utc).isoformat(),
        "total_flows": len(flows),
        "flows": flows[:500],
        "flows_full": flows,    # full set for History Store
    }
    return payload


register(LAYER, fetch)
