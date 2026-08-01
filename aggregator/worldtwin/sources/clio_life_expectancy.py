"""Life expectancy 1770→2023 — Clio-Infra + Riley + UN WPP via OWID.

Per-country life expectancy at birth, going back to 1770 for some countries
(UK, Sweden, France) and 1900s for most others. Used to extend the 'life'
mapmode back beyond World Bank's 1960 cutoff.

Output envelope:
  { source, fetched, year_range, countries: { iso3: { name, history: {year_str: years} } } }
"""
import csv
import io
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta
from ..registry import register

URL = "https://ourworldindata.org/grapher/life-expectancy.csv?v=1&csvType=full&useColumnShortNames=true"

LAYER = LayerMeta(
    id="clio_life_expectancy",
    name="Life expectancy 1770→2023 (Clio-Infra + UN WPP)",
    category="meta",
    kind="countries",
    source="OWID composite (Clio-Infra + Riley + UN WPP)",
    source_url="https://ourworldindata.org/grapher/life-expectancy",
    license="CC-BY 4.0",
    refresh_s=86400 * 30,
    initial_delay_s=260,
    units="years",
    description=(
        "Per-country life expectancy at birth, 1770→2023. Pre-1900 figures "
        "are scholarly reconstructions (Clio-Infra, Riley)."
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
    try:
        ent_i  = header.index("Entity")
        code_i = header.index("Code")
        year_i = header.index("Year")
    except ValueError:
        ent_i, code_i, year_i = 0, 1, 2
    val_i = 3
    for row in reader:
        if len(row) <= val_i:
            continue
        iso3 = (row[code_i] or "").strip().upper()
        if not iso3 or len(iso3) != 3:
            continue
        try:
            year = int(row[year_i])
            val = float(row[val_i])
        except ValueError:
            continue
        if not (10 <= val <= 100):    # sanity
            continue
        bucket = countries.setdefault(iso3, {
            "name": (row[ent_i] or "").strip(),
            "history": {},
        })
        bucket["history"][str(year)] = round(val, 2)

    if not countries:
        return None
    all_years = []
    for c in countries.values():
        all_years.extend(int(y) for y in c["history"].keys())
    return {
        "source": "OWID composite (Clio-Infra + Riley + UN WPP)",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "year_range": [min(all_years), max(all_years)],
        "countries": countries,
        "country_count": len(countries),
    }


register(LAYER, fetch)
