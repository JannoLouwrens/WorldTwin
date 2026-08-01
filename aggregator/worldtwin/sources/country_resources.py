"""Per-country resource fact sheet — the "what does this country have" answer.

For every country Comtrade reports on:
  - Top 10 export commodities (HS2 aggregation)
  - Top 10 import commodities
  - Top 10 trading partners (by total bilateral trade)
  - Trade balance USD
  - Dominant export category (used to colour the country on the choropleth)
  - Power mix from WRI Global Power Plant DB (loaded lazily)

The frontend CountryCard reads one key from this payload keyed by ISO3.
"""
import asyncio
import csv
import io
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _commodities as cdb
from . import _comtrade_common as cc

# HS2 is AG2 aggregation — for the fact sheet we want the broad picture.
# HS2 human-readable names.
HS2_NAMES = {
    "01": "Live animals", "02": "Meat", "03": "Fish", "04": "Dairy",
    "05": "Animal products", "06": "Live plants", "07": "Vegetables",
    "08": "Fruit & nuts", "09": "Coffee/tea/spices", "10": "Cereals",
    "11": "Milling products", "12": "Oilseeds", "13": "Gums/resins",
    "14": "Vegetable materials", "15": "Fats & oils", "16": "Meat preparations",
    "17": "Sugar", "18": "Cocoa", "19": "Baked goods", "20": "Vegetable preparations",
    "21": "Misc food", "22": "Beverages", "23": "Animal feed",
    "24": "Tobacco", "25": "Salt/sulphur/stone", "26": "Ores & slag",
    "27": "Mineral fuels (oil, gas, coal)", "28": "Inorganic chemicals",
    "29": "Organic chemicals", "30": "Pharmaceuticals", "31": "Fertilizers",
    "32": "Dyes & paints", "33": "Perfumes & cosmetics", "34": "Soaps & waxes",
    "35": "Starches & glues", "36": "Explosives", "37": "Photo/film",
    "38": "Misc chemicals", "39": "Plastics", "40": "Rubber", "41": "Rawhides",
    "42": "Leather goods", "43": "Furskins", "44": "Wood",
    "45": "Cork", "46": "Basketwork", "47": "Wood pulp",
    "48": "Paper", "49": "Books & printing", "50": "Silk", "51": "Wool",
    "52": "Cotton", "53": "Vegetable fibers", "54": "Man-made filament",
    "55": "Man-made staple", "56": "Wadding/felt", "57": "Carpets",
    "58": "Special fabrics", "59": "Impregnated textiles",
    "60": "Knitted fabrics", "61": "Apparel (knit)", "62": "Apparel (woven)",
    "63": "Textile articles", "64": "Footwear", "65": "Headgear",
    "66": "Umbrellas", "67": "Feathers/flowers", "68": "Stone articles",
    "69": "Ceramics", "70": "Glass", "71": "Precious metals & gems",
    "72": "Iron & steel", "73": "Iron/steel articles", "74": "Copper",
    "75": "Nickel", "76": "Aluminium", "78": "Lead", "79": "Zinc",
    "80": "Tin", "81": "Base metals", "82": "Tools & cutlery",
    "83": "Base metal articles", "84": "Machinery", "85": "Electrical machinery",
    "86": "Railway", "87": "Vehicles", "88": "Aircraft", "89": "Ships",
    "90": "Optical/medical instruments", "91": "Clocks & watches",
    "92": "Musical instruments", "93": "Arms & ammunition", "94": "Furniture",
    "95": "Toys & sports", "96": "Misc manufactures", "97": "Art & antiques",
    "98": "Special transactions", "99": "Commodities NES",
}

# Map HS2 → commodity-taxonomy parent category for the dominant-category colour
HS2_TO_PARENT = {
    "27": "energy",  # oil gas coal
    "26": "metals", "72": "metals", "73": "metals", "74": "metals", "75": "metals",
    "76": "metals", "78": "metals", "79": "metals", "80": "metals", "71": "metals",
    "81": "metals", "28": "metals",
    "84": "manufactures", "85": "tech", "87": "manufactures", "88": "manufactures", "89": "manufactures",
    "90": "tech", "91": "manufactures", "86": "manufactures",
    "29": "chemicals", "30": "chemicals", "31": "chemicals", "32": "chemicals", "33": "chemicals",
    "34": "chemicals", "35": "chemicals", "36": "chemicals", "38": "chemicals", "39": "chemicals", "40": "chemicals",
    "01": "agri", "02": "agri", "03": "agri", "04": "agri", "05": "agri",
    "06": "agri", "07": "agri", "08": "agri", "09": "agri", "10": "agri",
    "11": "agri", "12": "agri", "13": "agri", "14": "agri", "15": "agri",
    "16": "agri", "17": "agri", "18": "agri", "19": "agri", "20": "agri",
    "21": "agri", "22": "agri", "23": "agri", "24": "agri",
    "50": "textiles", "51": "textiles", "52": "textiles", "53": "textiles", "54": "textiles",
    "55": "textiles", "56": "textiles", "57": "textiles", "58": "textiles", "59": "textiles",
    "60": "textiles", "61": "textiles", "62": "textiles", "63": "textiles", "64": "textiles",
    "65": "textiles",
}


LAYER = LayerMeta(
    id="country_resources",
    name="Country Resource Fact Sheets",
    category="resources",
    kind="raw",
    source="UN Comtrade + WRI Global Power Plant DB",
    source_url="https://comtradeapi.un.org/public/v1/preview/C/A/HS",
    license="UN Open Data + CC BY 4.0",
    refresh_s=604800,  # weekly
    initial_delay_s=300,  # Come up last so trade_annual's year-probe has already cached
    units="USD",
    description=(
        "Per-country fact sheet: top 10 exports (HS2), top 10 imports, "
        "top 10 trading partners, trade balance, power-plant mix, "
        "dominant export category (used for the Resources choropleth). "
        "Covers every Comtrade reporter with a known centroid."
    ),
    requires_key=False,
)

# WRI Power Plant DB — loaded once, reused across refreshes
_wri_power_by_iso3: dict[str, dict[str, Any]] = {}
_wri_loaded = False


async def _load_wri_power(client: httpx.AsyncClient):
    """Download the WRI Global Power Plant Database CSV and aggregate by country + fuel."""
    global _wri_loaded, _wri_power_by_iso3
    if _wri_loaded:
        return
    try:
        r = await client.get(
            "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv",
            timeout=120,
            follow_redirects=True,
        )
        if r.status_code != 200:
            return
        text = r.text
        reader = csv.DictReader(io.StringIO(text))
        by_country: dict[str, dict[str, Any]] = {}
        for row in reader:
            iso3 = row.get("country", "").strip()
            if not iso3:
                continue
            try:
                capacity = float(row.get("capacity_mw") or 0)
            except ValueError:
                capacity = 0
            fuel = (row.get("primary_fuel") or "Other").strip()
            rec = by_country.setdefault(iso3, {
                "country_long": row.get("country_long", ""),
                "total_mw": 0.0,
                "plant_count": 0,
                "by_fuel": {},
                "top_plants": [],
            })
            rec["total_mw"] += capacity
            rec["plant_count"] += 1
            rec["by_fuel"][fuel] = rec["by_fuel"].get(fuel, 0.0) + capacity
            if capacity > 0:
                rec["top_plants"].append({
                    "name": row.get("name", ""),
                    "capacity_mw": capacity,
                    "fuel": fuel,
                    "lat": float(row.get("latitude") or 0) or None,
                    "lon": float(row.get("longitude") or 0) or None,
                    "commissioned": row.get("commissioning_year") or "",
                })
        # Keep top 10 plants per country by capacity
        for iso3, rec in by_country.items():
            rec["top_plants"] = sorted(rec["top_plants"], key=lambda p: p["capacity_mw"], reverse=True)[:10]
        _wri_power_by_iso3 = by_country
        _wri_loaded = True
        print(f"[country_resources] WRI loaded: {len(by_country)} countries")
    except Exception as e:
        print(f"[country_resources] WRI load failed: {e}")


async def _fetch_reporter_exports(client: httpx.AsyncClient, reporter: int, year: int, sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    async with sem:
        try:
            r = await client.get(
                "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                params={
                    "reporterCode": reporter,
                    "period": year,
                    "flowCode": "X",
                    "partnerCode": 0,
                    "cmdCode": "AG2",
                    "maxRecords": 50,
                },
                timeout=30,
            )
            if r.status_code != 200:
                return []
            await asyncio.sleep(0.4)
            return r.json().get("data", [])
        except Exception:
            return []


async def _fetch_reporter_imports(client: httpx.AsyncClient, reporter: int, year: int, sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    async with sem:
        try:
            r = await client.get(
                "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                params={
                    "reporterCode": reporter,
                    "period": year,
                    "flowCode": "M",
                    "partnerCode": 0,
                    "cmdCode": "AG2",
                    "maxRecords": 50,
                },
                timeout=30,
            )
            if r.status_code != 200:
                return []
            await asyncio.sleep(0.4)
            return r.json().get("data", [])
        except Exception:
            return []


async def fetch(client: httpx.AsyncClient):
    year = await cc.detect_latest_annual_year(client)
    await _load_wri_power(client)

    sem = asyncio.Semaphore(2)

    # For efficiency, fetch only countries we have centroids for (~198)
    reporters = list(cc.COUNTRY_COORDS.keys())

    # Launch all export + import fetches concurrently (semaphore-gated)
    exp_tasks = [_fetch_reporter_exports(client, r, year, sem) for r in reporters]
    imp_tasks = [_fetch_reporter_imports(client, r, year, sem) for r in reporters]

    exp_results = await asyncio.gather(*exp_tasks, return_exceptions=True)
    imp_results = await asyncio.gather(*imp_tasks, return_exceptions=True)

    countries: dict[str, dict[str, Any]] = {}

    for reporter, exp_rows, imp_rows in zip(reporters, exp_results, imp_results):
        if isinstance(exp_rows, Exception):
            exp_rows = []
        if isinstance(imp_rows, Exception):
            imp_rows = []
        iso3 = cc.iso3_for(reporter)
        if not iso3:
            continue
        name = cc.name_for(reporter)
        lat, lon = cc.coords_for(reporter) or (0, 0)

        # Aggregate exports by HS2
        exports: list[dict[str, Any]] = []
        partners_by_exp: dict[int, float] = {}
        total_exports = 0.0
        for row in exp_rows:
            hs = row.get("cmdCode", "")
            value = row.get("primaryValue") or 0
            if value < 100_000:
                continue
            exports.append({
                "hs": hs,
                "category": HS2_NAMES.get(hs, hs),
                "parent": HS2_TO_PARENT.get(hs, "other"),
                "value_usd": float(value),
            })
            total_exports += float(value)

        # Aggregate imports
        imports: list[dict[str, Any]] = []
        total_imports = 0.0
        for row in imp_rows:
            hs = row.get("cmdCode", "")
            value = row.get("primaryValue") or 0
            if value < 100_000:
                continue
            imports.append({
                "hs": hs,
                "category": HS2_NAMES.get(hs, hs),
                "parent": HS2_TO_PARENT.get(hs, "other"),
                "value_usd": float(value),
            })
            total_imports += float(value)

        exports.sort(key=lambda x: x["value_usd"], reverse=True)
        imports.sort(key=lambda x: x["value_usd"], reverse=True)

        top_exports = exports[:10]
        top_imports = imports[:10]

        # Dominant export parent category (drives the choropleth colour)
        parent_totals: dict[str, float] = {}
        for e in exports:
            parent_totals[e["parent"]] = parent_totals.get(e["parent"], 0) + e["value_usd"]
        dominant = max(parent_totals.items(), key=lambda kv: kv[1])[0] if parent_totals else "other"

        # WRI power mix
        power = _wri_power_by_iso3.get(iso3, {})
        power_summary = None
        if power:
            total_mw = power["total_mw"]
            mix = sorted(power["by_fuel"].items(), key=lambda x: x[1], reverse=True)
            power_summary = {
                "total_mw": total_mw,
                "plant_count": power["plant_count"],
                "mix": [{"fuel": f, "mw": mw, "pct": (mw / total_mw * 100) if total_mw else 0} for f, mw in mix[:6]],
                "top_plants": power["top_plants"],
            }

        countries[iso3] = {
            "iso3": iso3,
            "m49": reporter,
            "name": name,
            "lat": lat,
            "lon": lon,
            "year": year,
            "total_exports_usd": total_exports,
            "total_imports_usd": total_imports,
            "trade_balance_usd": total_exports - total_imports,
            "top_exports": top_exports,
            "top_imports": top_imports,
            "dominant_category": dominant,
            "power": power_summary,
        }

    payload = {
        "source": "UN Comtrade + WRI Global Power Plant DB",
        "year": year,
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(countries),
        "countries": countries,
        "categories": cdb.all_categories(),
    }
    return payload


register(LAYER, fetch)
