"""COW-style historical alliance graph 1815→present (curated).

Correlates of War's full alliance dataset (v4.1) is intermittently 404 at the
Wisconsin host. We embed the main alliance systems users actually want to
scrub through: Concert of Europe, Triple Alliance, Triple Entente, League of
Nations major powers, Axis, Allies (WWII), NATO, Warsaw Pact, modern blocs.

For each year we emit the active alliance memberships per country, so the
'political' mapmode can colour by primary alliance and the dossier can list
"in 1914, country X was member of: Triple Entente."

Output envelope:
  {
    "source": "Curated from Correlates of War + historical consensus",
    "year_range": [1815, 2026],
    "alliances": {
       "<alliance_id>": { "name": ..., "color": ..., "active": [start, end], "members": ["USA","GBR",...] },
       ...
    },
    "by_country_year": { "<iso3>": { "<year>": "<alliance_id>" } }   // primary alliance per country/year
  }
"""
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="cow_alliances",
    name="Historical Alliances 1815→present",
    category="meta",
    kind="raw",
    source="Curated from COW + historical consensus",
    source_url="https://correlatesofwar.org/data-sets/formal-alliances/",
    license="Free academic use",
    refresh_s=86400 * 30,
    initial_delay_s=200,
    description=(
        "Major historical alliance systems by year. Powers a time-aware "
        "'political' mapmode that shows pre-WWI, interwar, Cold War, post-"
        "Cold War alignments correctly when the user scrubs back."
    ),
    requires_key=False,
)


# Curated alliance systems, with start/end years and primary members.
ALLIANCES = {
    "concert_europe": {
        "name": "Concert of Europe",
        "color": "#7c8cff",
        "active": [1815, 1853],
        "members": ["GBR", "FRA", "DEU", "AUT", "RUS"],   # post-1871 DEU stands for Prussia/Germany
    },
    "triple_alliance": {
        "name": "Triple Alliance",
        "color": "#dc2626",
        "active": [1882, 1915],
        "members": ["DEU", "AUT", "ITA"],
    },
    "triple_entente": {
        "name": "Triple Entente",
        "color": "#2563eb",
        "active": [1907, 1917],
        "members": ["GBR", "FRA", "RUS"],
    },
    "central_powers": {
        "name": "Central Powers (WWI)",
        "color": "#7f1d1d",
        "active": [1914, 1918],
        "members": ["DEU", "AUT", "TUR", "BGR"],
    },
    "allies_ww1": {
        "name": "Allies (WWI)",
        "color": "#1e40af",
        "active": [1914, 1918],
        "members": ["GBR", "FRA", "RUS", "ITA", "USA", "JPN", "ROU", "SRB", "BEL"],
    },
    "axis": {
        "name": "Axis Powers",
        "color": "#7f1d1d",
        "active": [1936, 1945],
        "members": ["DEU", "ITA", "JPN", "HUN", "ROU", "BGR", "FIN", "THA"],
    },
    "allies_ww2": {
        "name": "Allies (WWII)",
        "color": "#1e40af",
        "active": [1939, 1945],
        "members": ["GBR", "USA", "RUS", "FRA", "CHN", "CAN", "AUS", "NZL", "ZAF",
                     "IND", "POL", "NOR", "NLD", "BEL", "GRC", "YUG", "BRA", "MEX"],
    },
    "nato": {
        "name": "NATO",
        "color": "#2B5BAA",
        "active": [1949, 2026],
        "members": ["USA", "GBR", "FRA", "DEU", "ITA", "CAN", "BEL", "NLD", "LUX",
                     "NOR", "DNK", "ISL", "PRT", "GRC", "TUR", "ESP", "CZE", "HUN",
                     "POL", "BGR", "EST", "LVA", "LTU", "ROU", "SVK", "SVN", "HRV",
                     "ALB", "MNE", "MKD", "FIN", "SWE"],
    },
    "warsaw_pact": {
        "name": "Warsaw Pact",
        "color": "#dc2626",
        "active": [1955, 1991],
        "members": ["RUS", "POL", "DEU", "CZE", "HUN", "ROU", "BGR", "ALB"],
    },
    "non_aligned": {
        "name": "Non-Aligned Movement",
        "color": "#16a34a",
        "active": [1961, 2026],
        "members": ["IND", "EGY", "YUG", "IDN", "CUB", "NGA", "GHA", "ZAF", "BRA",
                     "PAK", "BGD", "VEN", "DZA", "ETH"],
    },
    "g7": {
        "name": "G7",
        "color": "#FFD700",
        "active": [1975, 2026],
        "members": ["USA", "CAN", "GBR", "FRA", "DEU", "ITA", "JPN"],
    },
    "eu": {
        "name": "European Union",
        "color": "#003399",
        "active": [1993, 2026],
        "members": ["AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN",
                     "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX",
                     "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"],
    },
    "brics": {
        "name": "BRICS",
        "color": "#7c3aed",
        "active": [2009, 2026],
        "members": ["BRA", "RUS", "IND", "CHN", "ZAF", "IRN", "EGY", "ETH", "ARE"],
    },
}

# Priority (most "primary" first) for assigning a country's primary alliance per year.
# Wartime alliances trump peacetime; defense pacts trump trade clubs.
PRIORITY = ["axis", "allies_ww2", "central_powers", "allies_ww1",
            "warsaw_pact", "nato",
            "triple_alliance", "triple_entente", "concert_europe",
            "non_aligned", "brics", "eu", "g7"]


async def fetch(client: httpx.AsyncClient):
    by_country_year: dict[str, dict[str, str]] = {}
    for aid in PRIORITY:
        if aid not in ALLIANCES:
            continue
        a = ALLIANCES[aid]
        start, end = a["active"]
        for iso3 in a["members"]:
            for year in range(start, end + 1):
                ystr = str(year)
                bucket = by_country_year.setdefault(iso3, {})
                # Don't overwrite — first writer (higher priority) wins
                if ystr not in bucket:
                    bucket[ystr] = aid

    return {
        "source": "Curated from COW + historical consensus",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "year_range": [1815, 2026],
        "alliances": ALLIANCES,
        "by_country_year": by_country_year,
        "country_count": len(by_country_year),
    }


register(LAYER, fetch)
