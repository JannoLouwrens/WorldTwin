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
    name="World Bank Indicators (102 per country, 1960-2024 history)",
    category="resources",
    kind="raw",
    source="World Bank API v2",
    source_url="https://api.worldbank.org/v2/",
    license="CC BY 4.0",
    refresh_s=86400 * 7,
    initial_delay_s=265,
    description="102 World Bank indicators per country with 64-year history (economic, trade, fiscal, labour, demographic, health, education, infrastructure, energy, environment, security, governance, innovation). Per-indicator series enable timeline scrubbing.",
    requires_key=False,
)


INDICATORS = [
    # ==== ECONOMIC — output, prices, capital ====
    ("NY.GDP.MKTP.CD",         "GDP current USD"),
    ("NY.GDP.MKTP.KD",         "GDP constant 2015 USD"),
    ("NY.GDP.PCAP.CD",         "GDP per capita USD"),
    ("NY.GDP.PCAP.KD",         "GDP per capita constant 2015 USD"),
    ("NY.GDP.MKTP.KD.ZG",      "GDP growth %"),
    ("NY.GDP.PCAP.KD.ZG",      "GDP per capita growth %"),
    ("NY.GNP.MKTP.CD",         "GNI current USD"),
    ("NY.GNP.PCAP.PP.CD",      "GNI PPP per capita"),
    ("NY.GDP.PCAP.PP.CD",      "GDP PPP per capita"),
    ("NV.IND.MANF.ZS",         "Manufacturing value-added % GDP"),
    ("NV.SRV.TOTL.ZS",         "Services value-added % GDP"),
    ("NV.AGR.TOTL.ZS",         "Agriculture value-added % GDP"),
    ("NV.IND.TOTL.ZS",         "Industry value-added % GDP"),
    ("FP.CPI.TOTL.ZG",         "Inflation % (CPI)"),
    ("FP.CPI.TOTL",            "CPI index 2010=100"),
    ("FR.INR.RINR",            "Real interest rate %"),
    ("FR.INR.LEND",            "Lending interest rate %"),
    ("FR.INR.DPST",            "Deposit interest rate %"),
    ("BX.KLT.DINV.WD.GD.ZS",   "FDI net inflows % GDP"),
    ("BX.KLT.DINV.CD.WD",      "FDI net inflows BoP USD"),
    ("BN.CAB.XOKA.GD.ZS",      "Current account balance % GDP"),
    ("CM.MKT.LCAP.GD.ZS",      "Stock market cap % GDP"),
    ("CM.MKT.TRAD.GD.ZS",      "Stocks traded % GDP"),

    # ==== TRADE ====
    ("NE.IMP.GNFS.ZS",         "Imports % GDP"),
    ("NE.EXP.GNFS.ZS",         "Exports % GDP"),
    ("NE.IMP.GNFS.CD",         "Imports current USD"),
    ("NE.EXP.GNFS.CD",         "Exports current USD"),
    ("TX.VAL.TECH.CD",         "High-tech exports USD"),
    ("TX.VAL.TECH.MF.ZS",      "High-tech exports % manufactured"),
    ("TM.TAX.MRCH.SM.AR.ZS",   "Tariff rate % (manufactured)"),

    # ==== FISCAL / DEBT ====
    ("GC.DOD.TOTL.GD.ZS",      "Central gov debt % GDP"),
    ("GC.REV.XGRT.GD.ZS",      "Revenue % GDP"),
    ("GC.XPN.TOTL.GD.ZS",      "Expense % GDP"),
    ("GC.NLD.TOTL.GD.ZS",      "Net lending % GDP"),
    ("DT.DOD.DECT.CD",         "External debt stocks USD"),
    ("DT.TDS.DECT.GN.ZS",      "External debt service % GNI"),

    # ==== LABOUR / EMPLOYMENT ====
    ("SL.UEM.TOTL.ZS",         "Unemployment %"),
    ("SL.UEM.TOTL.MA.ZS",      "Unemployment male %"),
    ("SL.UEM.TOTL.FE.ZS",      "Unemployment female %"),
    ("SL.UEM.1524.ZS",         "Youth unemployment %"),
    ("SL.TLF.CACT.ZS",         "Labour force participation %"),
    ("SL.AGR.EMPL.ZS",         "Employment in agriculture %"),
    ("SL.IND.EMPL.ZS",         "Employment in industry %"),
    ("SL.SRV.EMPL.ZS",         "Employment in services %"),

    # ==== POPULATION / DEMOGRAPHICS ====
    ("SP.POP.TOTL",            "Population total"),
    ("SP.POP.GROW",            "Population growth %"),
    ("SP.URB.TOTL.IN.ZS",      "Urban population %"),
    ("SP.RUR.TOTL.ZS",         "Rural population %"),
    ("SP.DYN.CBRT.IN",         "Birth rate per 1000"),
    ("SP.DYN.CDRT.IN",         "Death rate per 1000"),
    ("SP.DYN.TFRT.IN",         "Fertility rate"),
    ("SP.POP.65UP.TO.ZS",      "Population 65+ %"),
    ("SP.POP.0014.TO.ZS",      "Population 0-14 %"),
    ("SP.POP.DPND",            "Age dependency ratio %"),
    ("SM.POP.REFG",            "Refugees by country of asylum"),
    ("SM.POP.REFG.OR",         "Refugees by country of origin"),
    ("SM.POP.NETM",            "Net migration"),

    # ==== HEALTH ====
    ("SP.DYN.LE00.IN",         "Life expectancy"),
    ("SP.DYN.LE00.MA.IN",      "Life expectancy male"),
    ("SP.DYN.LE00.FE.IN",      "Life expectancy female"),
    ("SH.DYN.MORT",            "Under-5 mortality per 1000"),
    ("SH.DYN.NMRT",            "Neonatal mortality per 1000"),
    ("SH.STA.MMRT",            "Maternal mortality per 100k"),
    ("SH.XPD.CHEX.GD.ZS",      "Health spend % GDP"),
    ("SH.XPD.CHEX.PC.CD",      "Health spend per capita USD"),
    ("SH.MED.PHYS.ZS",         "Physicians per 1000"),
    ("SH.MED.BEDS.ZS",         "Hospital beds per 1000"),
    ("SH.IMM.MEAS",            "Measles immunisation % age 12-23m"),

    # ==== EDUCATION ====
    ("SE.XPD.TOTL.GD.ZS",      "Education spend % GDP"),
    ("SE.PRM.ENRR",            "Primary school enrolment % gross"),
    ("SE.SEC.ENRR",            "Secondary school enrolment %"),
    ("SE.TER.ENRR",            "Tertiary enrolment %"),
    ("SE.ADT.LITR.ZS",         "Literacy rate adults %"),

    # ==== INFRASTRUCTURE / TECH ====
    ("IT.NET.USER.ZS",         "Internet users %"),
    ("IT.CEL.SETS.P2",         "Mobile subs per 100"),
    ("IT.NET.BBND.P2",         "Fixed broadband subs per 100"),
    ("EG.ELC.ACCS.ZS",         "Electricity access %"),
    ("SH.H2O.SMDW.ZS",         "Safely managed drinking water %"),
    ("SH.STA.SMSS.ZS",         "Safely managed sanitation %"),

    # ==== ENERGY / EMISSIONS ====
    ("EG.USE.PCAP.KG.OE",      "Energy per capita kg oil-eq"),
    ("EG.USE.COMM.GD.PP.KD",   "Energy use per $ GDP PPP"),
    ("EG.ELC.RNEW.ZS",         "Renewable electricity %"),
    ("EG.FEC.RNEW.ZS",         "Renewable energy total %"),
    ("EN.GHG.CO2.PC.CE.AR5",   "CO2 per capita t"),
    ("EN.GHG.CO2.MT.CE.AR5",   "CO2 emissions Mt"),
    ("EN.GHG.ALL.MT.CE.AR5",   "Total GHG Mt"),
    ("EN.GHG.CH4.AG.MT.CE.AR5", "Methane Mt"),

    # ==== ENVIRONMENT / LAND ====
    ("AG.LND.FRST.ZS",         "Forest area %"),
    ("AG.LND.FRST.K2",         "Forest area km2"),
    ("AG.LND.AGRI.ZS",         "Agricultural land %"),
    ("AG.LND.ARBL.ZS",         "Arable land %"),
    ("ER.H2O.FWTL.ZS",         "Freshwater withdrawal %"),
    ("ER.H2O.FWTL.K3",         "Freshwater withdrawal km3"),
    ("EN.URB.MCTY.TL.ZS",      "Population in cities >1M %"),

    # ==== SECURITY ====
    ("MS.MIL.XPND.GD.ZS",      "Military spend % GDP"),
    ("MS.MIL.XPND.CD",         "Military spend USD"),
    ("MS.MIL.TOTL.P1",         "Armed forces personnel"),
    ("VC.IHR.PSRC.P5",         "Intentional homicides per 100k"),

    # ==== GOVERNANCE / SOCIAL ====
    ("SG.GEN.PARL.ZS",         "Women in parliament %"),
    ("IC.BUS.EASE.XQ",         "Ease of doing business score"),
    ("SI.POV.GINI",            "Gini index"),
    ("SI.POV.NAHC",            "Poverty headcount national %"),
    ("SI.POV.DDAY",            "Poverty <$2.15/day %"),

    # ==== INNOVATION ====
    ("IP.JRN.ARTC.SC",         "Scientific articles published"),
    ("IP.PAT.RESD",            "Patent applications residents"),
    ("GB.XPD.RSDV.GD.ZS",      "R&D spend % GDP"),
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


# World Bank AGGREGATE pseudo-countries — they have 3-letter codes too, so
# the length check alone let regions/income groups leak in as "countries"
# and paint on choropleths (e.g. AFE "Africa Eastern" colored like a state).
WB_AGGREGATES = {
    "WLD", "EUU", "ARB", "EAS", "EAP", "ECS", "ECA", "LCN", "LAC", "MEA",
    "MNA", "NAC", "SAS", "SSF", "SSA", "AFE", "AFW", "HIC", "LIC", "LMC",
    "UMC", "MIC", "LMY", "IBD", "IBT", "IDA", "IDB", "IDX", "OED", "PRE",
    "PST", "EAR", "LTE", "TEA", "TEC", "TLA", "TMN", "TSA", "TSS", "FCS",
    "HPC", "LDC", "OSS", "PSS", "SST", "CEB", "EMU", "CSS",
}


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(3)         # WB throttles aggressive parallelism
    by_country: dict[str, dict[str, Any]] = {}
    labels = {c: l for c, l in INDICATORS}

    # Fold each indicator's ~25k-row result into by_country AS IT ARRIVES
    # and let the rows list go — gather() used to hold all 102 result sets
    # (~2M row dicts) in RAM simultaneously.
    tasks = [_fetch_indicator(client, c, sem) for c, _ in INDICATORS]
    for fut in asyncio.as_completed(tasks):
        code, rows = await fut
        # Build per-country full series, then pick latest non-null
        per_country_history: dict[str, dict[str, float]] = {}
        for row in rows:
            country_obj = row.get("country") or {}
            iso3 = row.get("countryiso3code") or country_obj.get("id", "")
            if not iso3 or len(iso3) != 3 or iso3 in WB_AGGREGATES:
                continue                 # skip aggregates and malformed codes
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
