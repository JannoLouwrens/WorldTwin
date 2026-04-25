"""World Bank API v2 — 30 key indicators per country, with TIME SERIES.

Free, no key. Each indicator is fetched as a 64-year time series (1960:2024).
Cache schema (backwards-compatible — `latest` still has the {year, value}
shape used by existing dossier/mapmode readers):

  countries[iso3][indicator] = {
      latest:  {year, value},          # most recent non-null sample
      history: {year_str: value, ...}  # full series, year_str like "2024"
  }
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="world_bank",
    name="World Bank Indicators (30 per country, 1960-2024 history)",
    category="resources",
    kind="raw",
    source="World Bank API v2",
    source_url="https://api.worldbank.org/v2/",
    license="CC BY 4.0",
    refresh_s=86400 * 7,
    initial_delay_s=265,
    description="30 key World Bank indicators per country with 64-year history. Per-indicator series enable timeline scrubbing.",
    requires_key=False,
)


INDICATORS = [
    ("NY.GDP.MKTP.CD",         "GDP current USD"),
    ("NY.GDP.PCAP.CD",         "GDP per capita USD"),
    ("NY.GDP.MKTP.KD.ZG",      "GDP growth %"),
    ("SP.POP.TOTL",            "Population total"),
    ("SP.POP.GROW",            "Population growth %"),
    ("SP.DYN.LE00.IN",         "Life expectancy"),
    ("SP.URB.TOTL.IN.ZS",      "Urban population %"),
    ("EN.GHG.CO2.PC.CE.AR5",   "CO2 per capita (t)"),
    ("EG.USE.PCAP.KG.OE",      "Energy per capita"),
    ("EG.ELC.ACCS.ZS",         "Electricity access %"),
    ("EG.ELC.RNEW.ZS",         "Renewable electricity %"),
    ("IT.NET.USER.ZS",         "Internet users %"),
    ("MS.MIL.XPND.GD.ZS",      "Military spend % GDP"),
    ("FP.CPI.TOTL.ZG",         "Inflation %"),
    ("SL.UEM.TOTL.ZS",         "Unemployment %"),
    ("NE.IMP.GNFS.ZS",         "Imports % GDP"),
    ("NE.EXP.GNFS.ZS",         "Exports % GDP"),
    ("BX.KLT.DINV.WD.GD.ZS",   "FDI net inflows % GDP"),
    ("GC.DOD.TOTL.GD.ZS",      "Central gov debt % GDP"),
    ("AG.LND.FRST.ZS",         "Forest area %"),
    ("AG.LND.AGRI.ZS",         "Agricultural land %"),
    ("ER.H2O.FWTL.ZS",         "Freshwater withdrawal %"),
    ("SH.DYN.MORT",            "Under-5 mortality (per 1000)"),
    ("SE.XPD.TOTL.GD.ZS",      "Education spend % GDP"),
    ("SH.XPD.CHEX.GD.ZS",      "Health spend % GDP"),
    ("IT.CEL.SETS.P2",         "Mobile subs per 100"),
    ("SM.POP.REFG",            "Refugees by country"),
    ("NY.GNP.PCAP.PP.CD",      "GNI PPP per capita"),
    ("SP.RUR.TOTL.ZS",         "Rural population %"),
    ("SG.GEN.PARL.ZS",         "Women in parliament %"),
    ("IP.JRN.ARTC.SC",         "Scientific articles"),
]


async def _fetch_indicator(client: httpx.AsyncClient, code: str, sem: asyncio.Semaphore):
    """Fetch a single indicator across all countries × 1960..now in one call."""
    async with sem:
        try:
            r = await client.get(
                f"https://api.worldbank.org/v2/country/all/indicator/{code}",
                params={"format": "json", "per_page": 25000, "date": "1960:2024"},
                timeout=90,
            )
            if r.status_code != 200:
                return code, []
            body = r.json()
            if not isinstance(body, list) or len(body) < 2:
                return code, []
            return code, body[1] or []
        except Exception as e:
            print(f"[world_bank] {code} error: {e}")
            return code, []


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(3)         # WB throttles aggressive parallelism
    results = await asyncio.gather(*[_fetch_indicator(client, c, sem) for c, _ in INDICATORS])
    by_country: dict[str, dict[str, Any]] = {}
    labels = {c: l for c, l in INDICATORS}

    for code, rows in results:
        # Build per-country full series, then pick latest non-null
        per_country_history: dict[str, dict[str, float]] = {}
        for row in rows:
            country_obj = row.get("country") or {}
            iso3 = row.get("countryiso3code") or country_obj.get("id", "")
            if not iso3 or len(iso3) != 3:
                continue                 # skip aggregates (region codes are 2-3 chars but not country ISO3)
            value = row.get("value")
            year = row.get("date", "")
            if value is None or not year:
                continue
            try:
                year_int = int(year)
            except ValueError:
                continue
            per_country_history.setdefault(iso3, {})[str(year_int)] = value

        for iso3, history in per_country_history.items():
            latest_year = max(history.keys(), key=lambda y: int(y))
            latest_value = history[latest_year]
            rec = by_country.setdefault(iso3, {})
            # Backwards compat: existing readers use {year, value} directly.
            # New readers use latest{year,value} or history{year:value}.
            rec[code] = {
                "year": latest_year,
                "value": latest_value,
                "latest": {"year": latest_year, "value": latest_value},
                "history": history,
            }

    return {
        "source": "World Bank API v2",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "indicators": labels,
        "count": len(by_country),
        "countries": by_country,
        "history_year_range": [1960, 2024],
    }


register(LAYER, fetch)
