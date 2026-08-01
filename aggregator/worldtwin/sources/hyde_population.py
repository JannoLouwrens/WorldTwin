"""HYDE 3.3 historical population per country (10,000 BC → 2023).

We use Our World in Data's pre-aggregated mirror — they ingest HYDE 3.3 and
present it as a clean per-country CSV. Coverage 10,000 BC → 2023, decadal
pre-1500 then annual.

Output envelope:
  {
    "countries": { "<iso3>": { "name": "...", "series": [[year, pop], ...], "year_range": [ya, yb] } },
    "year_range": [global_min, global_max]
  }
"""
import csv
import io

import httpx

from ..models import LayerMeta
from ..registry import register

URL = "https://ourworldindata.org/grapher/population.csv?v=1&csvType=full&useColumnShortNames=true"

LAYER = LayerMeta(
    id="hyde_population",
    name="Population (10,000 BC → today)",
    category="economy",
    kind="countries",
    source="HYDE 3.3 + UN WPP via Our World in Data",
    source_url="https://ourworldindata.org/grapher/population",
    license="CC-BY 4.0",
    refresh_s=86400 * 30,
    initial_delay_s=90,
    units="persons",
    description=(
        "Per-country population spanning 12,000 years. Decadal samples for "
        "deep prehistory transitioning to annual after 1950. Pre-1950 figures "
        "come from HYDE 3.3 (Klein Goldewijk et al.); modern figures from UN WPP."
    ),
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get(URL, timeout=120, follow_redirects=True)
    if r.status_code != 200:
        return None
    text = r.text
    countries: dict[str, dict] = {}
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    # OWID full CSV columns: Entity, Code, Year, population_historical (or similar)
    if not header:
        return None
    code_idx = 1
    year_idx = 2
    pop_idx = -1  # last col
    for row in reader:
        if len(row) < 4:
            continue
        iso3 = (row[code_idx] or "").strip().upper()
        if not iso3 or len(iso3) != 3:
            # Skip OWID aggregates ('OWID_WRL', regions) — we only want sovereign countries
            continue
        try:
            year = int(row[year_idx])
        except ValueError:
            continue
        try:
            pop = float(row[pop_idx])
        except ValueError:
            continue
        if pop <= 0:
            continue
        bucket = countries.setdefault(iso3, {
            "name": (row[0] or "").strip(),
            "series": [],
        })
        bucket["series"].append([year, int(pop)])

    global_min = None
    global_max = None
    for iso3, data in countries.items():
        data["series"].sort(key=lambda x: x[0])
        ys = [r[0] for r in data["series"]]
        data["year_range"] = [ys[0], ys[-1]] if ys else [None, None]
        if ys:
            if global_min is None or ys[0]  < global_min: global_min = ys[0]
            if global_max is None or ys[-1] > global_max: global_max = ys[-1]

    v1_data = {
        "countries": countries,
        "year_range": [global_min, global_max],
        "country_count": len(countries),
    }
    return v1_data, v1_data


register(LAYER, fetch)
