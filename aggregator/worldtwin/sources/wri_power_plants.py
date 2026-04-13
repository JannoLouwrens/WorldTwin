"""WRI Global Power Plant Database — ~30k plants worldwide.

Static reference data, CC BY 4.0. Loaded once a week into a per-country
aggregation. The raw plant locations are exposed so the Resources mode
can render dots on the globe coloured by fuel type.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="wri_power_plants",
    name="Global Power Plants (WRI)",
    category="resources",
    kind="points",
    source="World Resources Institute Global Power Plant Database",
    source_url="https://github.com/wri/global-power-plant-database",
    license="CC BY 4.0",
    refresh_s=604800,  # weekly
    initial_delay_s=150,
    units="MW",
    description=(
        "~30,000 power plants worldwide with capacity, fuel type, and "
        "location. Used for the Resources mode power layer."
    ),
    requires_key=False,
)

# Canonical fuel categories (mapped to colours on the frontend)
FUEL_CANONICAL = {
    "Coal": "coal",
    "Gas": "gas",
    "Oil": "oil",
    "Hydro": "hydro",
    "Solar": "solar",
    "Wind": "wind",
    "Nuclear": "nuclear",
    "Geothermal": "geothermal",
    "Biomass": "biomass",
    "Waste": "biomass",
    "Wave and Tidal": "tidal",
    "Storage": "storage",
    "Petcoke": "oil",
    "Cogeneration": "gas",
    "Other": "other",
}


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv",
            timeout=120,
            follow_redirects=True,
        )
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        plants: list[dict[str, Any]] = []
        for row in reader:
            try:
                lat = float(row.get("latitude") or 0)
                lon = float(row.get("longitude") or 0)
                capacity = float(row.get("capacity_mw") or 0)
            except ValueError:
                continue
            if lat == 0 and lon == 0:
                continue
            if capacity <= 0:
                continue
            fuel = (row.get("primary_fuel") or "Other").strip()
            plants.append({
                "id": row.get("gppd_idnr", ""),
                "name": row.get("name", ""),
                "country": row.get("country", ""),
                "country_long": row.get("country_long", ""),
                "lat": lat,
                "lon": lon,
                "capacity_mw": capacity,
                "fuel": fuel,
                "fuel_canonical": FUEL_CANONICAL.get(fuel, "other"),
                "commissioned": row.get("commissioning_year", ""),
                "owner": row.get("owner", ""),
            })
        # Sort by capacity desc and keep top 5000 for render budget
        plants.sort(key=lambda p: p["capacity_mw"], reverse=True)
        top = plants[:5000]
        # Summary by country
        by_country: dict[str, dict[str, Any]] = {}
        for p in plants:
            c = p["country"]
            rec = by_country.setdefault(c, {"total_mw": 0, "count": 0, "by_fuel": {}})
            rec["total_mw"] += p["capacity_mw"]
            rec["count"] += 1
            f = p["fuel_canonical"]
            rec["by_fuel"][f] = rec["by_fuel"].get(f, 0) + p["capacity_mw"]

        payload = {
            "source": "WRI Global Power Plant Database",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "total_plants": len(plants),
            "plants": top,
            "by_country": by_country,
        }
        return payload
    except Exception as e:
        print(f"[wri_power_plants] error: {e}")
        return None


register(LAYER, fetch)
