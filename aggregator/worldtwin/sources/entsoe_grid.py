"""ENTSO-E European Grid Monitor — generation by fuel, load, prices.

Fetches from the ENTSO-E Transparency Platform API for 20 European countries:
- Actual generation per fuel type (A75)
- Actual total load (A65)
- Day-ahead electricity prices (A44)

Returns per-country: total generation MW, fuel mix breakdown, load MW, price EUR/MWh.
Free API key from https://transparency.entsoe.eu/ — set ENTSOE_API_KEY in .env.
"""
import asyncio
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

ENTSOE_API_KEY = os.environ.get("ENTSOE_API_KEY", "")

LAYER = LayerMeta(
    id="entsoe_grid",
    name="ENTSO-E European Grid Monitor",
    category="resources",
    kind="raw",
    source="ENTSO-E Transparency Platform",
    source_url="https://transparency.entsoe.eu/",
    license="Free with attribution",
    refresh_s=1800,
    initial_delay_s=35,
    description="European grid: generation by fuel type, total load, day-ahead prices for 20 countries.",
    requires_key=True,
    key_env="ENTSOE_API_KEY",
    enabled=bool(ENTSOE_API_KEY),
)

BASE_URL = "https://web-api.tp.entsoe.eu/api"
NS = {"ns": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"}
NS_PRICE = {"ns": "urn:iec62325.351:tc57wg16:451-6:publicationdocument:7:0"}

# ENTSO-E bidding zone codes for major European countries
AREAS = {
    "DE": ("10Y1001A1001A83F", "Germany",     51.2, 10.4),
    "FR": ("10YFR-RTE------C", "France",      46.2, 2.2),
    "ES": ("10YES-REE------0", "Spain",       40.5, -3.7),
    "IT": ("10YIT-GRTN-----B", "Italy",       41.9, 12.6),
    "GB": ("10YGB----------A", "UK",          55.4, -3.4),
    "NL": ("10YNL----------L", "Netherlands", 52.1, 5.3),
    "BE": ("10YBE----------2", "Belgium",     50.5, 4.5),
    "AT": ("10YAT-APG------L", "Austria",     47.5, 14.6),
    "CH": ("10YCH-SWISSGRIDZ", "Switzerland", 46.8, 8.2),
    "PL": ("10YPL-AREA-----S", "Poland",      51.9, 19.1),
    "NO": ("10YNO-0--------C", "Norway",      60.5, 8.5),
    "SE": ("10YSE-1--------K", "Sweden",      60.1, 18.6),
    "DK": ("10Y1001A1001A65H", "Denmark",     56.3, 9.5),
    "FI": ("10YFI-1--------U", "Finland",     61.9, 25.7),
    "PT": ("10YPT-REN------W", "Portugal",    39.4, -8.2),
    "CZ": ("10YCZ-CEPS-----N", "Czech Rep.",  49.8, 15.5),
    "GR": ("10YGR-HTSO-----Y", "Greece",      39.1, 21.8),
    "RO": ("10YRO-TEL------P", "Romania",     45.9, 25.0),
    "HU": ("10YHU-MAVIR----U", "Hungary",     47.2, 19.5),
    "IE": ("10YIE-1001A00010", "Ireland",     53.4, -8.2),
}

# ENTSO-E PSR type codes → human-readable fuel names
PSR_TYPES = {
    "B01": "Biomass", "B02": "Fossil Brown Coal/Lignite", "B03": "Fossil Coal-derived Gas",
    "B04": "Fossil Gas", "B05": "Fossil Hard Coal", "B06": "Fossil Oil",
    "B07": "Fossil Oil Shale", "B08": "Fossil Peat", "B09": "Geothermal",
    "B10": "Hydro Pumped Storage", "B11": "Hydro Run-of-river", "B12": "Hydro Water Reservoir",
    "B13": "Marine", "B14": "Nuclear", "B15": "Other Renewable", "B16": "Solar",
    "B17": "Waste", "B18": "Wind Offshore", "B19": "Wind Onshore", "B20": "Other",
}

# Simplified fuel categories for the frontend
def simplify_fuel(psr_code):
    mapping = {
        "B01": "biomass", "B02": "coal", "B03": "gas", "B04": "gas", "B05": "coal",
        "B06": "oil", "B07": "oil", "B08": "coal", "B09": "geothermal",
        "B10": "hydro", "B11": "hydro", "B12": "hydro", "B13": "marine",
        "B14": "nuclear", "B15": "renewable_other", "B16": "solar",
        "B17": "waste", "B18": "wind", "B19": "wind", "B20": "other",
    }
    return mapping.get(psr_code, "other")


def _parse_generation_xml(xml_text: str) -> dict[str, float]:
    """Parse A75 generation response → {fuel_category: MW total}."""
    fuel_totals: dict[str, float] = {}
    try:
        root = ET.fromstring(xml_text)
        for ts in root.findall(".//ns:TimeSeries", NS):
            psr_el = ts.find(".//ns:MktPSRType/ns:psrType", NS)
            psr_code = psr_el.text if psr_el is not None else "B20"
            fuel = simplify_fuel(psr_code)
            # Get the last (most recent) observation
            points = ts.findall(".//ns:Point", NS)
            if points:
                last = points[-1]
                qty_el = last.find("ns:quantity", NS)
                if qty_el is not None and qty_el.text:
                    try:
                        mw = float(qty_el.text)
                        fuel_totals[fuel] = fuel_totals.get(fuel, 0) + mw
                    except ValueError:
                        pass
    except ET.ParseError:
        pass
    return fuel_totals


def _parse_load_xml(xml_text: str) -> float:
    """Parse A65 load response → latest load MW."""
    try:
        root = ET.fromstring(xml_text)
        points = root.findall(".//{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}Point")
        if not points:
            # Try without namespace
            points = root.findall(".//Point")
        if points:
            last = points[-1]
            for child in last:
                if "quantity" in child.tag:
                    return float(child.text)
    except (ET.ParseError, ValueError):
        pass
    return 0


def _parse_price_xml(xml_text: str) -> float:
    """Parse A44 day-ahead price → latest price EUR/MWh."""
    try:
        root = ET.fromstring(xml_text)
        # Price documents use a different namespace
        for ts in root.iter():
            if "Point" in ts.tag:
                for child in ts:
                    if "price.amount" in child.tag and child.text:
                        try:
                            return float(child.text)
                        except ValueError:
                            pass
        # Fallback: find any price.amount
        for el in root.iter():
            if el.text and "price" in el.tag.lower():
                try:
                    return float(el.text)
                except ValueError:
                    continue
    except ET.ParseError:
        pass
    return 0


async def fetch(client: httpx.AsyncClient):
    if not ENTSOE_API_KEY:
        return None

    now = datetime.now(timezone.utc)
    # Query last 4 hours to ensure we get recent data
    period_start = (now - timedelta(hours=4)).strftime("%Y%m%d%H00")
    period_end = now.strftime("%Y%m%d%H00")

    sem = asyncio.Semaphore(4)  # ENTSO-E rate limit is ~400/min but be polite
    countries: dict[str, dict[str, Any]] = {}

    async def _fetch_country(iso2: str, area_code: str, name: str, lat: float, lon: float):
        async with sem:
            result = {
                "iso2": iso2,
                "name": name,
                "lat": lat,
                "lon": lon,
                "total_generation_mw": 0,
                "fuel_mix": {},
                "load_mw": 0,
                "price_eur_mwh": 0,
                "renewable_pct": 0,
            }

            # 1) Actual generation per type (A75)
            try:
                r = await client.get(BASE_URL, params={
                    "securityToken": ENTSOE_API_KEY,
                    "documentType": "A75",
                    "processType": "A16",
                    "in_Domain": area_code,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }, timeout=20)
                if r.status_code == 200:
                    fuel_totals = _parse_generation_xml(r.text)
                    result["fuel_mix"] = fuel_totals
                    result["total_generation_mw"] = round(sum(fuel_totals.values()))
                    renewables = sum(v for k, v in fuel_totals.items()
                                     if k in ("solar", "wind", "hydro", "geothermal", "biomass", "marine", "renewable_other"))
                    total = sum(fuel_totals.values())
                    result["renewable_pct"] = round(renewables / total * 100, 1) if total > 0 else 0
            except Exception as e:
                print(f"[entsoe] {iso2} gen: {e}")

            await asyncio.sleep(0.3)  # rate limit politeness

            # 2) Actual total load (A65)
            try:
                r = await client.get(BASE_URL, params={
                    "securityToken": ENTSOE_API_KEY,
                    "documentType": "A65",
                    "processType": "A16",
                    "outBiddingZone_Domain": area_code,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }, timeout=20)
                if r.status_code == 200:
                    result["load_mw"] = round(_parse_load_xml(r.text))
            except Exception as e:
                print(f"[entsoe] {iso2} load: {e}")

            await asyncio.sleep(0.3)

            # 3) Day-ahead prices (A44)
            try:
                r = await client.get(BASE_URL, params={
                    "securityToken": ENTSOE_API_KEY,
                    "documentType": "A44",
                    "in_Domain": area_code,
                    "out_Domain": area_code,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }, timeout=20)
                if r.status_code == 200:
                    result["price_eur_mwh"] = round(_parse_price_xml(r.text), 2)
            except Exception as e:
                print(f"[entsoe] {iso2} price: {e}")

            if result["total_generation_mw"] > 0 or result["load_mw"] > 0:
                countries[iso2] = result

    tasks = [_fetch_country(iso2, code, name, lat, lon) for iso2, (code, name, lat, lon) in AREAS.items()]
    await asyncio.gather(*tasks)

    # 4) Cross-border physical flows (A11) for major interconnectors
    INTERCONNECTORS = [
        ("FR", "DE"), ("FR", "ES"), ("FR", "IT"), ("FR", "GB"), ("FR", "BE"), ("FR", "CH"),
        ("DE", "NL"), ("DE", "PL"), ("DE", "CZ"), ("DE", "AT"), ("DE", "DK"), ("DE", "CH"),
        ("NO", "SE"), ("NO", "DK"), ("NO", "GB"), ("NO", "NL"),
        ("SE", "DK"), ("SE", "FI"), ("SE", "PL"),
        ("ES", "PT"),
        ("IT", "AT"), ("IT", "CH"), ("IT", "GR"),
        ("GB", "BE"), ("GB", "NL"), ("GB", "IE"),
        ("PL", "CZ"), ("AT", "HU"), ("AT", "CZ"), ("HU", "RO"),
    ]

    flows = []

    async def _fetch_flow(from_iso2, to_iso2):
        async with sem:
            from_code = AREAS.get(from_iso2, (None,))[0]
            to_code = AREAS.get(to_iso2, (None,))[0]
            if not from_code or not to_code:
                return
            try:
                r = await client.get(BASE_URL, params={
                    "securityToken": ENTSOE_API_KEY,
                    "documentType": "A11",
                    "in_Domain": to_code,
                    "out_Domain": from_code,
                    "periodStart": period_start,
                    "periodEnd": period_end,
                }, timeout=15)
                if r.status_code != 200:
                    return
                # Parse — A11 uses Publication_MarketDocument namespace
                mw = 0
                try:
                    root = ET.fromstring(r.text)
                    # Find the last quantity in any TimeSeries/Point
                    for el in root.iter():
                        if 'quantity' in el.tag and el.text:
                            try:
                                mw = float(el.text)
                            except ValueError:
                                pass
                except ET.ParseError:
                    pass
                if mw and abs(mw) > 10:
                    from_data = AREAS.get(from_iso2)
                    to_data = AREAS.get(to_iso2)
                    if from_data and to_data:
                        flows.append({
                            "from": from_iso2,
                            "to": to_iso2,
                            "mw": round(mw),
                            "from_lat": from_data[2],
                            "from_lon": from_data[3],
                            "to_lat": to_data[2],
                            "to_lon": to_data[3],
                        })
            except Exception:
                pass
            await asyncio.sleep(0.2)

    flow_tasks = [_fetch_flow(f, t) for f, t in INTERCONNECTORS]
    await asyncio.gather(*flow_tasks)

    return {
        "source": "ENTSO-E Transparency Platform",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(countries),
        "period": {"start": period_start, "end": period_end},
        "countries": countries,
        "flows": flows,
    }


register(LAYER, fetch)
