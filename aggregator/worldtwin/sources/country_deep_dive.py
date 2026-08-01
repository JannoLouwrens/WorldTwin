"""Per-country deep-dive resource metrics — ELECTRICITY / WATER / FOOD / OIL.

Reads existing cache files and augments with:
  - FEWS NET IPC food security phase per country (free API)
  - A hardcoded Aqueduct 4.0 country-level baseline water stress table
  - OWID energy latest year per country (already cached by owid_energy)
  - ClimateTRACE emissions (already cached)

Produces one unified per-country record consumed by the CountryCard
"Resources Deep Dive" section.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))


LAYER = LayerMeta(
    id="country_deep_dive",
    name="Country Resource Deep Dive",
    category="resources",
    kind="raw",
    source="Aggregated: OWID + FEWS NET + WRI Aqueduct + ClimateTRACE",
    source_url="internal",
    license="Aggregated — see individual sources",
    refresh_s=86400,  # daily
    initial_delay_s=420,
    description=(
        "Per-country ELECTRICITY/WATER/FOOD/OIL deep-dive panel. Fuses "
        "OWID energy mix, FEWS NET food security phase, WRI Aqueduct baseline "
        "water stress, ClimateTRACE facility emissions."
    ),
    requires_key=False,
)


# WRI Aqueduct 4.0 baseline water stress (BWS) by country.
# Score 0 (very low) to 5 (extremely high). Source: WRI Aqueduct Country Rankings 2023.
AQUEDUCT_BWS = {
    "BHR": 5.0, "CYP": 5.0, "KWT": 5.0, "LBN": 5.0, "OMN": 5.0, "QAT": 5.0,
    "ARE": 5.0, "SAU": 5.0, "ISR": 4.9, "EGY": 4.9, "LBY": 4.9, "YEM": 4.9,
    "BWA": 4.8, "IRN": 4.7, "JOR": 4.6, "CHL": 4.6, "SYR": 4.5, "TKM": 4.5,
    "PAK": 4.3, "BEL": 4.2, "TUN": 4.1, "ERI": 4.0, "GRC": 3.9, "ESP": 3.9,
    "MAR": 3.8, "IND": 3.8, "DZA": 3.7, "TUR": 3.7, "MEX": 3.6, "ARM": 3.6,
    "KAZ": 3.5, "AFG": 3.5, "IRQ": 3.5, "UZB": 3.4, "AZE": 3.4, "ITA": 3.4,
    "ZAF": 3.3, "MLT": 3.3, "AUS": 3.2, "USA": 3.2, "CHN": 3.0, "FRA": 2.9,
    "KOR": 2.9, "BGD": 2.8, "DEU": 2.7, "JPN": 2.7, "NLD": 2.7, "GBR": 2.6,
    "POL": 2.6, "UKR": 2.5, "CAN": 2.3, "NGA": 2.3, "RUS": 2.2, "BRA": 2.1,
    "IDN": 2.1, "VNM": 2.0, "NZL": 1.9, "NOR": 1.5, "ISL": 1.3, "FIN": 1.3,
    "SWE": 1.4, "COD": 1.2,
}


def _read_cache(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


async def _fetch_fews_ipc(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch FEWS NET IPC food security phase per country.

    FEWS NET sometimes times out or returns a pagination wrapper.
    Handle both gracefully without logging noise.
    """
    try:
        r = await client.get(
            "https://fdw.fews.net/api/ipcphase/?format=json&limit=800",
            timeout=20,  # short timeout — FEWS is flaky
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code != 200:
            return {}
        body = r.json()
        # FEWS sometimes returns a dict with results, sometimes a list
        rows = body if isinstance(body, list) else (body.get("results") or [])
        by_country: dict[str, dict[str, Any]] = {}
        for row in rows:
            iso2 = row.get("country_code", "")
            if not iso2 or len(iso2) != 2:
                continue
            if row.get("unit_type") != "admin0":
                continue
            value = row.get("value")
            if value is None:
                continue
            # Keep the most recent record per country
            cur = by_country.get(iso2)
            period = row.get("projection_end") or row.get("reporting_date", "")
            if not cur or period > (cur.get("period") or ""):
                by_country[iso2] = {
                    "iso2": iso2,
                    "country": row.get("country", ""),
                    "phase": value,
                    "description": row.get("description", ""),
                    "scenario": row.get("scenario_name", ""),
                    "period": period,
                    "pct_phase3": row.get("pct_phase3"),
                    "pct_phase4": row.get("pct_phase4"),
                    "pct_phase5": row.get("pct_phase5"),
                }
        return by_country
    except Exception:
        # Silent — FEWS is often unavailable, we just skip food security for the refresh
        return {}


def _iso2_to_iso3(iso2: str) -> str:
    """Cheap lookup via COUNTRY_COORDS scan."""
    iso2 = (iso2 or "").upper()
    mapping = {
        "US":"USA","CN":"CHN","IN":"IND","RU":"RUS","BR":"BRA","CA":"CAN","AU":"AUS","DE":"DEU",
        "FR":"FRA","GB":"GBR","JP":"JPN","KR":"KOR","IT":"ITA","ES":"ESP","PL":"POL","TR":"TUR",
        "MX":"MEX","ID":"IDN","SA":"SAU","IR":"IRN","ZA":"ZAF","EG":"EGY","NG":"NGA","ET":"ETH",
        "KE":"KEN","MA":"MAR","DZ":"DZA","AR":"ARG","CL":"CHL","PE":"PER","VE":"VEN","CO":"COL",
        "TH":"THA","VN":"VNM","MY":"MYS","PH":"PHL","PK":"PAK","BD":"BGD","NL":"NLD","BE":"BEL",
        "CH":"CHE","AT":"AUT","SE":"SWE","NO":"NOR","FI":"FIN","DK":"DNK","IE":"IRL","PT":"PRT",
        "GR":"GRC","CZ":"CZE","HU":"HUN","RO":"ROU","BG":"BGR","UA":"UKR","IQ":"IRQ","AE":"ARE",
        "IL":"ISR","SG":"SGP","NZ":"NZL","TW":"TWN","HK":"HKG","SO":"SOM","SD":"SDN","SS":"SSD",
        "YE":"YEM","SY":"SYR","LB":"LBN","JO":"JOR","AF":"AFG","MM":"MMR","KH":"KHM","LA":"LAO",
        "UG":"UGA","TZ":"TZA","CD":"COD","AO":"AGO","MZ":"MOZ","ZM":"ZMB","ZW":"ZWE","CI":"CIV",
        "GH":"GHA","CM":"CMR","SN":"SEN","ML":"MLI","BF":"BFA","NE":"NER","TD":"TCD","MG":"MDG",
    }
    return mapping.get(iso2, "")


async def fetch(client: httpx.AsyncClient):
    # Read existing caches
    owid = _read_cache("owid_energy") or {}
    owid_countries = owid.get("countries") or {}
    owid_history = owid.get("history") or {}
    country_res = _read_cache("country_resources") or {}
    country_res_countries = country_res.get("countries") or {}
    climatetrace = _read_cache("climatetrace_assets") or {}
    wri = _read_cache("wri_power_plants") or {}
    wri_by_country = wri.get("by_country") or {}

    # Aggregate ClimateTRACE emissions per country
    ct_by_country: dict[str, dict[str, float]] = {}
    for a in climatetrace.get("assets", []):
        country = a.get("country", "")
        sector = a.get("sector", "")
        em = a.get("emissions_tco2e") or 0
        if not country or not em:
            continue
        rec = ct_by_country.setdefault(country, {"total": 0})
        rec["total"] += em
        rec[sector] = rec.get(sector, 0) + em

    # Fetch FEWS NET IPC
    fews = await _fetch_fews_ipc(client)

    # Build deep-dive per country — union of all source country lists
    all_iso3 = set(owid_countries.keys()) | set(country_res_countries.keys()) | set(ct_by_country.keys())

    deep: dict[str, dict[str, Any]] = {}
    for iso3 in all_iso3:
        owid_row = owid_countries.get(iso3) or {}
        cr = country_res_countries.get(iso3) or {}
        ct = ct_by_country.get(iso3) or {}
        wri_row = wri_by_country.get(iso3) or {}

        # Electricity block
        electricity = {
            "year": owid_row.get("year"),
            "generation_twh": owid_row.get("electricity_generation"),
            "demand_twh": owid_row.get("electricity_demand"),
            "fossil_share": owid_row.get("fossil_share_elec"),
            "renewables_share": owid_row.get("renewables_share_elec"),
            "nuclear_share": owid_row.get("nuclear_share_elec"),
            "hydro_share": owid_row.get("hydro_share_elec"),
            "solar_share": owid_row.get("solar_share_elec"),
            "wind_share": owid_row.get("wind_share_elec"),
            "gas_share": owid_row.get("gas_share_elec"),
            "coal_share": owid_row.get("coal_share_elec"),
            "oil_share": owid_row.get("oil_share_elec"),
            "carbon_intensity_gco2_kwh": owid_row.get("carbon_intensity_elec"),
            "total_plants": wri_row.get("count"),
            "total_capacity_mw": wri_row.get("total_mw"),
            "mix_mw": wri_row.get("by_fuel"),
        }

        # Water block
        water = {
            "baseline_water_stress": AQUEDUCT_BWS.get(iso3),
            "stress_description": _stress_label(AQUEDUCT_BWS.get(iso3)),
        }

        # Food block — FEWS NET by ISO2
        iso2_match = None
        for k, v in fews.items():
            if _iso2_to_iso3(k) == iso3:
                iso2_match = v
                break
        food = {
            "ipc_phase": iso2_match.get("phase") if iso2_match else None,
            "ipc_description": iso2_match.get("description") if iso2_match else None,
            "ipc_period": iso2_match.get("period") if iso2_match else None,
            "ipc_scenario": iso2_match.get("scenario") if iso2_match else None,
        }

        # Oil block — OWID energy has fossil_energy_per_capita etc
        oil = {
            "primary_energy_twh": owid_row.get("primary_energy_consumption"),
            "fossil_per_capita_kwh": owid_row.get("fossil_energy_per_capita"),
            "renewables_per_capita_kwh": owid_row.get("renewables_energy_per_capita"),
            "greenhouse_gas_emissions_mt": owid_row.get("greenhouse_gas_emissions"),
        }

        # ClimateTRACE emissions by sector
        emissions = {
            "total_tco2e": ct.get("total"),
            "by_sector": {k: v for k, v in ct.items() if k != "total"},
        }

        # Country metadata from country_resources
        meta = {
            "name": cr.get("name") or cc.name_for_iso3(iso3),
            "lat": cr.get("lat"),
            "lon": cr.get("lon"),
            "population": None,
            "trade_balance_usd": cr.get("trade_balance_usd"),
            "total_exports_usd": cr.get("total_exports_usd"),
            "total_imports_usd": cr.get("total_imports_usd"),
        }

        deep[iso3] = {
            "iso3": iso3,
            "meta": meta,
            "electricity": electricity,
            "water": water,
            "food": food,
            "oil": oil,
            "emissions": emissions,
        }

    return {
        "source": "country_deep_dive",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(deep),
        "countries": deep,
    }


def _stress_label(score):
    if score is None:
        return None
    if score >= 4.5: return "Extremely High"
    if score >= 3.5: return "High"
    if score >= 2.5: return "Medium-High"
    if score >= 1.5: return "Low-Medium"
    return "Low"


register(LAYER, fetch)
