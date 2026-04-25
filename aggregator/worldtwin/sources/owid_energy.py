"""Our World in Data — Energy dataset per country 2000–present.

Free CSV on GitHub, CC-BY 4.0. ~100 energy indicators per country per year:
electricity generation by source, per-capita consumption, CO2 intensity,
fossil share, renewable share, gas/oil/coal/nuclear/hydro/solar/wind split.

Used to populate the CountryCard energy panel.
"""
import csv
import io
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="owid_energy",
    name="Energy Indicators by Country (OWID)",
    category="resources",
    kind="raw",
    source="Our World in Data Energy",
    source_url="https://github.com/owid/energy-data",
    license="CC-BY 4.0",
    refresh_s=86400 * 7,  # weekly
    initial_delay_s=320,
    description=(
        "~100 energy indicators per country (electricity mix, per-capita "
        "consumption, fossil/renewable share, CO2 intensity). Used for the "
        "CountryCard energy panel."
    ),
    requires_key=False,
)

# The columns we care about for the country fact sheet
KEY_COLUMNS = [
    "country", "iso_code", "year", "population",
    "electricity_generation", "electricity_demand",
    "fossil_share_elec", "renewables_share_elec",
    "nuclear_share_elec", "hydro_share_elec", "solar_share_elec",
    "wind_share_elec", "gas_share_elec", "coal_share_elec", "oil_share_elec",
    "biofuel_share_elec", "other_renewables_share_elec",
    "energy_per_capita", "energy_per_gdp",
    "fossil_energy_per_capita", "renewables_energy_per_capita",
    "primary_energy_consumption", "greenhouse_gas_emissions",
    "carbon_intensity_elec",
]


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://nyc3.digitaloceanspaces.com/owid-public/data/energy/owid-energy-data.csv",
            timeout=120,
            follow_redirects=True,
        )
        if r.status_code != 200:
            r = await client.get(
                "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv",
                timeout=120,
                follow_redirects=True,
            )
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))

        # Keep only latest year per country + a 10-year history for sparklines
        latest_by_country: dict[str, dict[str, Any]] = {}
        history_by_country: dict[str, list] = {}
        all_rows = list(reader)
        for row in all_rows:
            iso3 = (row.get("iso_code") or "").strip()
            if not iso3 or len(iso3) != 3:
                continue
            try:
                year = int(row.get("year") or 0)
            except ValueError:
                continue
            if year < 1985:           # 40 years of history for time-aware mapmodes
                continue
            # Keep only key columns, coerce to float where possible
            out = {}
            for k in KEY_COLUMNS:
                v = row.get(k, "")
                if v in ("", None):
                    out[k] = None
                else:
                    try:
                        out[k] = float(v)
                    except (ValueError, TypeError):
                        out[k] = v
            history_by_country.setdefault(iso3, []).append(out)
            cur_latest = latest_by_country.get(iso3)
            if not cur_latest or year > (cur_latest.get("year") or 0):
                latest_by_country[iso3] = out

        # Sort history per country by year
        for iso3 in history_by_country:
            history_by_country[iso3].sort(key=lambda r: r.get("year") or 0)
            # Keep all years 1985+ (~40 entries per country) — needed for time-aware mapmodes

        return {
            "source": "Our World in Data Energy",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(latest_by_country),
            "countries": latest_by_country,
            "history": history_by_country,
        }
    except Exception as e:
        print(f"[owid_energy] error: {e}")
        return None


register(LAYER, fetch)
