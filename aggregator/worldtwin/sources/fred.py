"""FRED — St. Louis Fed Reserve Economic Data. 50 series covering global macro.

Expanded from 10 US-centric series to ~50 across inflation, unemployment,
bond yields, commodity prices, currencies, industrial production, risk
indicators, and monetary policy across major economies.

Rate: FRED free tier = 120 req/min. 50 calls/refresh × hourly = well under.
"""
import asyncio
import os
from typing import Any

import httpx

from ..models import LayerMeta, timeseries_point
from ..registry import register

FRED_KEY = os.environ.get("FRED_API_KEY", "")

# (series_id, human name, unit, category)
SERIES = [
    # === INTEREST RATES ===
    ("FEDFUNDS",    "US Fed Funds Rate",        "%",        "rates"),
    ("DFEDTARU",    "US Fed Upper Target",      "%",        "rates"),
    ("ECBESTRVOLWGTTRMDMNRT","ECB €STR",        "%",        "rates"),
    ("IRLTLT01JPM156N", "Japan 10Y Bond",       "%",        "rates"),
    ("IRLTLT01GBM156N", "UK 10Y Bond",          "%",        "rates"),
    ("IRLTLT01DEM156N", "Germany 10Y Bund",     "%",        "rates"),
    ("DGS10",       "US 10Y Treasury",          "%",        "rates"),
    ("T10Y2Y",      "US 10Y-2Y Spread",         "%",        "rates"),

    # === INFLATION ===
    ("CPIAUCSL",    "US CPI",                   "index",    "inflation"),
    ("CPALCY01GBM661N", "UK CPI",               "index",    "inflation"),
    ("CPALCY01DEM661N", "Germany CPI",          "index",    "inflation"),
    ("CPALCY01JPM661N", "Japan CPI",            "index",    "inflation"),
    ("CPALCY01FRM661N", "France CPI",           "index",    "inflation"),

    # === UNEMPLOYMENT ===
    ("UNRATE",      "US Unemployment",          "%",        "unemployment"),
    ("LRHUTTTTDEM156S", "Germany Unemp",        "%",        "unemployment"),
    ("LRHUTTTTJPM156S", "Japan Unemp",          "%",        "unemployment"),
    ("LRHUTTTTFRM156S", "France Unemp",         "%",        "unemployment"),
    ("LRHUTTTTGBM156S", "UK Unemp",             "%",        "unemployment"),

    # === GDP / GROWTH ===
    ("GDP",         "US GDP (Real)",            "$B",       "growth"),
    ("GDPC1",       "US Real GDP",              "$B",       "growth"),

    # === MONEY SUPPLY / CREDIT ===
    ("M2SL",        "US M2 Money Supply",       "$B",       "money"),
    ("WALCL",       "Fed Balance Sheet",        "$M",       "money"),
    ("BAMLH0A0HYM2", "US HY Credit Spread",     "%",        "money"),

    # === COMMODITIES ===
    ("DCOILWTICO",  "WTI Crude Oil",            "$/bbl",    "commodities"),
    ("DCOILBRENTEU","Brent Crude Oil",          "$/bbl",    "commodities"),
    ("DHHNGSP",     "Henry Hub Natural Gas",    "$/MMBtu",  "commodities"),
    ("PCOPPUSDM",   "Copper",                   "$/t",      "commodities"),
    ("PIORECRUSDM", "Iron Ore",                 "$/t",      "commodities"),
    ("PWHEAMTUSDM", "Wheat",                    "$/t",      "commodities"),
    ("PSOYBUSDM",   "Soybeans",                 "$/t",      "commodities"),
    ("GOLDAMGBD228NLBM", "Gold AM Fix",         "$/oz",     "commodities"),

    # === CURRENCIES ===
    ("DEXUSEU",     "USD/EUR",                  "rate",     "forex"),
    ("DEXCHUS",     "CNY/USD",                  "rate",     "forex"),
    ("DEXJPUS",     "JPY/USD",                  "rate",     "forex"),
    ("DEXUSUK",     "GBP/USD",                  "rate",     "forex"),
    ("DEXINUS",     "INR/USD",                  "rate",     "forex"),
    ("DEXBZUS",     "BRL/USD",                  "rate",     "forex"),
    ("DEXSFUS",     "CHF/USD",                  "rate",     "forex"),
    ("DTWEXBGS",    "Trade-Weighted USD",       "index",    "forex"),

    # === RISK / SENTIMENT ===
    ("VIXCLS",      "VIX Volatility",           "index",    "risk"),
    ("DGS30",       "US 30Y Treasury",          "%",        "risk"),
    ("TB3MS",       "US 3M T-Bill",             "%",        "risk"),

    # === INDUSTRIAL PRODUCTION ===
    ("INDPRO",      "US Industrial Production", "index",    "production"),
    ("IPMAN",       "US Manufacturing IP",      "index",    "production"),
    ("PRGDPG",      "Real GDP (latest YoY)",    "%",        "production"),

    # === TRADE ===
    ("EXPGSC1",     "US Real Exports",          "$B",       "trade"),
    ("IMPGSC1",     "US Real Imports",          "$B",       "trade"),
    ("BOPGSTB",     "US Trade Balance",         "$M",       "trade"),

    # === LABOR ===
    ("PAYEMS",      "US Nonfarm Payrolls",      "thousands","labor"),
    ("CIVPART",     "US Labor Force Part",      "%",        "labor"),
]


LAYER = LayerMeta(
    id="fred",
    name="FRED Global Macro (50 series)",
    category="economy",
    kind="raw",
    source="Federal Reserve Bank of St. Louis (FRED)",
    source_url="https://fred.stlouisfed.org/docs/api/fred/",
    license="Public (US Government)",
    refresh_s=3600,
    initial_delay_s=245,
    description=f"{len(SERIES)} global macro series — inflation, rates, unemployment, commodities, currencies, risk, production, trade, labor.",
    requires_key=True,
    key_env="FRED_API_KEY",
    enabled=bool(FRED_KEY),
)


async def _fetch_one(client: httpx.AsyncClient, series_id: str, name: str, unit: str, category: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": FRED_KEY,
                    "file_type": "json",
                    "limit": 12,
                    "sort_order": "desc",
                },
                timeout=30,
            )
            if r.status_code != 200:
                return None
            obs = r.json().get("observations", [])
            if not obs:
                return None
            series = [
                timeseries_point(
                    t=o.get("date"),
                    v=float(o.get("value")) if o.get("value") not in ("", ".") else None,
                )
                for o in reversed(obs)
            ]
            latest = next((o for o in obs if o.get("value") not in ("", ".")), None)
            return series_id, {
                "name": name,
                "unit": unit,
                "category": category,
                "latest": float(latest["value"]) if latest else None,
                "latest_date": latest.get("date") if latest else None,
                "series": series,
            }
        except Exception as e:
            print(f"[fred] {series_id} failed: {type(e).__name__}: {e}")
            return None


async def fetch(client: httpx.AsyncClient):
    if not FRED_KEY:
        return None
    sem = asyncio.Semaphore(4)
    tasks = [_fetch_one(client, sid, nm, un, cat, sem) for sid, nm, un, cat in SERIES]
    results = await asyncio.gather(*tasks)
    result = {"source": "FRED", "series": {}}
    by_category: dict[str, list[str]] = {}
    for r in results:
        if not r:
            continue
        series_id, data = r
        result["series"][series_id] = data
        by_category.setdefault(data["category"], []).append(series_id)
    if not result["series"]:
        return None
    result["by_category"] = by_category
    # Freshness timestamp — every public number must carry a date
    from datetime import datetime, timezone
    result["fetched"] = datetime.now(timezone.utc).isoformat()
    return result


register(LAYER, fetch)
