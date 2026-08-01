"""V-Dem Electoral Democracy Index — per-country yearly score 1789→2025.

Source: V-Dem v14 via Our World in Data mirror. Coverage 235 years × ~200
countries, single index 0..1 (where 1 = full electoral democracy).

We could fetch all 5 V-Dem high-level indicators (electoral, liberal,
participatory, deliberative, egalitarian) but the electoral-democracy index is
the workhorse and cheapest to ship. Cache size ≈ 1.5 MB.

Output envelope:
  {
    "source": "V-Dem v14 (via OWID)",
    "fetched": "...",
    "year_range": [1789, 2025],
    "countries": {
       "<iso3>": { "name": "...", "history": {"1789": 0.019, ..., "2024": 0.92} },
       ...
    },
    "country_count": 200
  }
"""
import csv
import io

import httpx

from ..models import LayerMeta
from ..registry import register

URL = "https://ourworldindata.org/grapher/electoral-democracy-index.csv?v=1&csvType=full&useColumnShortNames=true"

LAYER = LayerMeta(
    id="vdem_democracy",
    name="Electoral Democracy Index (V-Dem 1789→2025)",
    category="meta",
    kind="countries",
    source="V-Dem v14 (via OWID)",
    source_url="https://www.v-dem.net/",
    license="CC-BY 4.0",
    refresh_s=86400 * 30,            # monthly — V-Dem releases yearly
    initial_delay_s=240,
    units="0..1 (1 = full electoral democracy)",
    description=(
        "Per-country electoral democracy score from V-Dem v14, spanning 235 years. "
        "Powers a time-aware 'democracy' mapmode that scrubs back to the French "
        "Revolution era. Pre-1900 scores are scholarly reconstructions."
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
    if not header:
        return None
    # Columns: Entity, Code, Year, electdem_vdem_owid, World region (or similar)
    # Be robust to column reorderings — find name/code/year/value indices.
    try:
        ent_i  = header.index("Entity")
        code_i = header.index("Code")
        year_i = header.index("Year")
    except ValueError:
        # fallback positional
        ent_i, code_i, year_i = 0, 1, 2
    # Value column is the 4th (index 3) typically
    val_i = 3
    for row in reader:
        if len(row) <= val_i:
            continue
        iso3 = (row[code_i] or "").strip().upper()
        if not iso3 or len(iso3) != 3:
            continue       # skip aggregates ("OWID_WRL", region rows)
        try:
            year = int(row[year_i])
        except ValueError:
            continue
        try:
            val = float(row[val_i])
        except ValueError:
            continue
        bucket = countries.setdefault(iso3, {
            "name": (row[ent_i] or "").strip(),
            "history": {},
        })
        bucket["history"][str(year)] = round(val, 4)

    if not countries:
        return None

    all_years = []
    for c in countries.values():
        all_years.extend(int(y) for y in c["history"].keys())
    if not all_years:
        return None
    year_range = [min(all_years), max(all_years)]

    v1 = {
        "source": "V-Dem v14 (via OWID)",
        "fetched": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "year_range": year_range,
        "countries": countries,
        "country_count": len(countries),
    }
    return v1


register(LAYER, fetch)
