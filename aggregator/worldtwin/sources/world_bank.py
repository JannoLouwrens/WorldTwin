"""World Bank API v2 — 30 key indicators per country.

Free, no key, 1500+ indicators available. We pull 30 of the most useful.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="world_bank",
    name="World Bank Indicators (30 per country)",
    category="resources",
    kind="raw",
    source="World Bank API v2",
    source_url="https://api.worldbank.org/v2/",
    license="CC BY 4.0",
    refresh_s=86400 * 7,
    initial_delay_s=265,
    description="30 key World Bank indicators per country: GDP, life expectancy, CO2, debt, military spend, internet users, etc.",
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
    ("EN.GHG.CO2.PC.CE.AR5",         "CO2 per capita (t)"),
    ("EG.USE.PCAP.KG.OE",      "Energy per capita"),
    ("EG.ELC.ACCS.ZS",         "Electricity access %"),
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


async def _fetch_indicator(client: httpx.AsyncClient, code: str, label: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                f"https://api.worldbank.org/v2/country/all/indicator/{code}",
                params={"format": "json", "per_page": 25000, "date": "2020:2024"},
                timeout=45,
            )
            if r.status_code != 200:
                return code, []
            body = r.json()
            if not isinstance(body, list) or len(body) < 2:
                return code, []
            rows = body[1] or []
            return code, rows
        except Exception as e:
            print(f"[world_bank] {code} error: {e}")
            return code, []


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*[_fetch_indicator(client, c, l, sem) for c, l in INDICATORS])
    # Pivot to {iso3: {indicator: {year, value}}}
    by_country: dict[str, dict[str, Any]] = {}
    labels = {c: l for c, l in INDICATORS}
    for code, rows in results:
        # Keep most recent non-null per country
        latest_per_country: dict[str, dict[str, Any]] = {}
        for row in rows:
            country_obj = row.get("country") or {}
            iso3 = row.get("countryiso3code") or country_obj.get("id", "")
            if not iso3 or iso3 in ("", "None"):
                continue
            value = row.get("value")
            year = row.get("date", "")
            if value is None:
                continue
            cur = latest_per_country.get(iso3)
            if not cur or year > cur.get("year", ""):
                latest_per_country[iso3] = {"year": year, "value": value}
        for iso3, v in latest_per_country.items():
            rec = by_country.setdefault(iso3, {})
            rec[code] = v

    return {
        "source": "World Bank API v2",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "indicators": labels,
        "count": len(by_country),
        "countries": by_country,
    }


register(LAYER, fetch)
