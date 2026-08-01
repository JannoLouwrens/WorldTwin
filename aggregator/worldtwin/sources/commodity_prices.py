"""Live commodity price ticker — oil from datahub.io CSVs plus a handful
of other free endpoints. Populates the ticker strip in Economy mode.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="commodity_prices",
    name="Commodity Prices (live ticker)",
    category="economy",
    kind="raw",
    source="datahub.io oil + CoinGecko global + Frankfurter forex",
    source_url="https://github.com/datasets/oil-prices",
    license="CC-BY-SA",
    refresh_s=3600,
    initial_delay_s=80,
    units="USD",
    description=(
        "Brent + WTI from the datahub.io CSV mirror (updated weekly), "
        "crypto market cap from CoinGecko, and USD DXY from Frankfurter."
    ),
    requires_key=False,
)


async def _last_csv_row(client: httpx.AsyncClient, url: str):
    try:
        r = await client.get(url, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            return None
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return None
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        header = rows[0]
        last = rows[-1]
        return dict(zip(header, last))
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    out: dict[str, Any] = {
        "fetched": datetime.now(timezone.utc).isoformat(),
        "items": [],
    }
    # Brent daily
    brent = await _last_csv_row(
        client,
        "https://raw.githubusercontent.com/datasets/oil-prices/main/data/brent-daily.csv",
    )
    if brent:
        out["items"].append({
            "id": "brent",
            "name": "Brent Crude",
            "symbol": "BRENT",
            "unit": "$/bbl",
            "price": float(brent.get("Price", 0)),
            "date": brent.get("Date"),
            "category": "energy",
        })
    # WTI daily
    wti = await _last_csv_row(
        client,
        "https://raw.githubusercontent.com/datasets/oil-prices/main/data/wti-daily.csv",
    )
    if wti:
        out["items"].append({
            "id": "wti",
            "name": "WTI Crude",
            "symbol": "WTI",
            "unit": "$/bbl",
            "price": float(wti.get("Price", 0)),
            "date": wti.get("Date"),
            "category": "energy",
        })
    # Natural gas monthly
    ngas = await _last_csv_row(
        client,
        "https://raw.githubusercontent.com/datasets/natural-gas/main/data/daily.csv",
    )
    if ngas:
        try:
            out["items"].append({
                "id": "natgas",
                "name": "Natural Gas (Henry Hub)",
                "symbol": "NATGAS",
                "unit": "$/MMBtu",
                "price": float(ngas.get("Price", 0)),
                "date": ngas.get("Date"),
                "category": "energy",
            })
        except ValueError:
            pass
    # Gold monthly
    gold = await _last_csv_row(
        client,
        "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv",
    )
    if gold:
        try:
            out["items"].append({
                "id": "gold",
                "name": "Gold",
                "symbol": "GOLD",
                "unit": "$/oz",
                "price": float(gold.get("Price", 0)),
                "date": gold.get("Date"),
                "category": "metals",
            })
        except ValueError:
            pass
    # CoinGecko global
    try:
        r = await client.get("https://api.coingecko.com/api/v3/global", timeout=15)
        if r.status_code == 200:
            g = r.json().get("data", {})
            out["crypto_market_cap"] = g.get("total_market_cap", {}).get("usd")
            out["crypto_volume"] = g.get("total_volume", {}).get("usd")
            out["btc_dominance"] = g.get("market_cap_percentage", {}).get("btc")
    except Exception:
        pass
    # Forex — Frankfurter
    try:
        r = await client.get(
            "https://api.frankfurter.dev/v1/latest?base=USD",
            timeout=15,
        )
        if r.status_code == 200:
            out["forex"] = r.json()
    except Exception:
        pass
    return out


register(LAYER, fetch)
