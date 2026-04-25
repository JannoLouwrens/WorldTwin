"""Maddison Project Database (Bolt & van Zanden 2020) — historical GDP, GDPpc, population.

Mirrored on Our World in Data's owid-datasets GitHub repo. Coverage: year 1 →
2018 for some countries; many start ~1500 or 1820. Real GDP per capita in
2011 international dollars.

Output envelope:
  {
    "countries": {
       "<entity_name>": {
          "iso3": "...",  # filled where the OWID entity name has an obvious ISO3 mapping
          "series": [[year, gdp_pc, population, gdp_total], ...],
          "year_range": [ya, yb]
       }
    },
    "year_range": [global_min, global_max]
  }
"""
import csv
import io

import httpx

from ..models import LayerMeta
from ..registry import register

URL = (
    "https://raw.githubusercontent.com/owid/owid-datasets/master/datasets/"
    "Maddison%20Project%20Database%202020%20%28Bolt%20and%20van%20Zanden%20%282020%29%29/"
    "Maddison%20Project%20Database%202020%20%28Bolt%20and%20van%20Zanden%20%282020%29%29.csv"
)

# Minimal entity-name → ISO3 map for the bigger economies. Anything not in this
# map will still be returned but keyed by entity name only.
ENTITY_TO_ISO3 = {
    "Afghanistan": "AFG", "Albania": "ALB", "Algeria": "DZA", "Angola": "AGO",
    "Argentina": "ARG", "Armenia": "ARM", "Australia": "AUS", "Austria": "AUT",
    "Azerbaijan": "AZE", "Bahrain": "BHR", "Bangladesh": "BGD", "Belarus": "BLR",
    "Belgium": "BEL", "Benin": "BEN", "Bolivia": "BOL", "Bosnia and Herzegovina": "BIH",
    "Botswana": "BWA", "Brazil": "BRA", "Bulgaria": "BGR", "Burkina Faso": "BFA",
    "Burundi": "BDI", "Cambodia": "KHM", "Cameroon": "CMR", "Canada": "CAN",
    "Central African Republic": "CAF", "Chad": "TCD", "Chile": "CHL", "China": "CHN",
    "Colombia": "COL", "Comoros": "COM", "Costa Rica": "CRI", "Croatia": "HRV",
    "Cuba": "CUB", "Cyprus": "CYP", "Czechia": "CZE", "Czechoslovakia": "CSK",
    "Democratic Republic of Congo": "COD", "Denmark": "DNK", "Djibouti": "DJI",
    "Dominican Republic": "DOM", "Ecuador": "ECU", "Egypt": "EGY",
    "El Salvador": "SLV", "Estonia": "EST", "Ethiopia": "ETH", "Fiji": "FJI",
    "Finland": "FIN", "France": "FRA", "Gabon": "GAB", "Gambia": "GMB",
    "Georgia": "GEO", "Germany": "DEU", "Ghana": "GHA", "Greece": "GRC",
    "Guatemala": "GTM", "Guinea": "GIN", "Haiti": "HTI", "Honduras": "HND",
    "Hong Kong": "HKG", "Hungary": "HUN", "Iceland": "ISL", "India": "IND",
    "Indonesia": "IDN", "Iran": "IRN", "Iraq": "IRQ", "Ireland": "IRL",
    "Israel": "ISR", "Italy": "ITA", "Ivory Coast": "CIV", "Jamaica": "JAM",
    "Japan": "JPN", "Jordan": "JOR", "Kazakhstan": "KAZ", "Kenya": "KEN",
    "Kuwait": "KWT", "Kyrgyzstan": "KGZ", "Laos": "LAO", "Latvia": "LVA",
    "Lebanon": "LBN", "Lesotho": "LSO", "Liberia": "LBR", "Libya": "LBY",
    "Lithuania": "LTU", "Luxembourg": "LUX", "Madagascar": "MDG", "Malawi": "MWI",
    "Malaysia": "MYS", "Mali": "MLI", "Mauritania": "MRT", "Mauritius": "MUS",
    "Mexico": "MEX", "Moldova": "MDA", "Mongolia": "MNG", "Montenegro": "MNE",
    "Morocco": "MAR", "Mozambique": "MOZ", "Myanmar": "MMR", "Namibia": "NAM",
    "Nepal": "NPL", "Netherlands": "NLD", "New Zealand": "NZL", "Nicaragua": "NIC",
    "Niger": "NER", "Nigeria": "NGA", "North Korea": "PRK", "North Macedonia": "MKD",
    "Norway": "NOR", "Oman": "OMN", "Pakistan": "PAK", "Panama": "PAN",
    "Paraguay": "PRY", "Peru": "PER", "Philippines": "PHL", "Poland": "POL",
    "Portugal": "PRT", "Qatar": "QAT", "Romania": "ROU", "Russia": "RUS",
    "Rwanda": "RWA", "Saudi Arabia": "SAU", "Senegal": "SEN", "Serbia": "SRB",
    "Sierra Leone": "SLE", "Singapore": "SGP", "Slovakia": "SVK", "Slovenia": "SVN",
    "Somalia": "SOM", "South Africa": "ZAF", "South Korea": "KOR", "South Sudan": "SSD",
    "Spain": "ESP", "Sri Lanka": "LKA", "Sudan": "SDN", "Sweden": "SWE",
    "Switzerland": "CHE", "Syria": "SYR", "Taiwan": "TWN", "Tajikistan": "TJK",
    "Tanzania": "TZA", "Thailand": "THA", "Togo": "TGO", "Trinidad and Tobago": "TTO",
    "Tunisia": "TUN", "Turkey": "TUR", "Turkmenistan": "TKM", "Uganda": "UGA",
    "Ukraine": "UKR", "United Arab Emirates": "ARE", "United Kingdom": "GBR",
    "United States": "USA", "Uruguay": "URY", "Uzbekistan": "UZB", "Venezuela": "VEN",
    "Vietnam": "VNM", "Yemen": "YEM", "Zambia": "ZMB", "Zimbabwe": "ZWE",
    "USSR": "RUS", "Yugoslavia": "SRB",
}

LAYER = LayerMeta(
    id="maddison_history",
    name="Maddison GDP & Population (1 AD → 2018)",
    category="economy",
    kind="countries",
    source="Bolt & van Zanden 2020 / Maddison Project (via OWID mirror)",
    source_url="https://www.rug.nl/ggdc/historicaldevelopment/maddison/releases/maddison-project-database-2020",
    license="CC-BY 4.0",
    refresh_s=86400 * 14,
    initial_delay_s=60,
    units="2011 int$ / persons",
    description=(
        "Historical GDP per capita and population for 169 countries. "
        "Coverage starts year 1 for a handful of polities (Belgium, Bulgaria, "
        "Italy, Egypt, ...) and 1500–1820 for most modern states. Real GDPpc "
        "in 2011 international dollars."
    ),
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get(URL, timeout=120, follow_redirects=True)
    if r.status_code != 200:
        return None
    text = r.text
    countries: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        ent = row.get("Entity", "").strip()
        if not ent:
            continue
        try:
            year = int(row["Year"])
        except (ValueError, KeyError):
            continue
        try:
            gdp_pc = float(row["GDP per capita"]) if row.get("GDP per capita") else None
        except ValueError:
            gdp_pc = None
        try:
            pop = float(row["Population"]) if row.get("Population") else None
        except ValueError:
            pop = None
        try:
            gdp = float(row["GDP"]) if row.get("GDP") else None
        except ValueError:
            gdp = None
        if gdp_pc is None and pop is None and gdp is None:
            continue
        bucket = countries.setdefault(ent, {
            "iso3": ENTITY_TO_ISO3.get(ent),
            "series": [],
        })
        bucket["series"].append([year, gdp_pc, pop, gdp])

    # Sort each series by year + compute year_range
    global_min = None
    global_max = None
    for ent, data in countries.items():
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
