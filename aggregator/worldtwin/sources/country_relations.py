"""Country relations — alliances, enmities, blocs.

Combines:
  - Hardcoded bloc memberships (NATO, EU, G7, G20, BRICS, OECD, ASEAN, AU,
    Mercosur, CIS, GCC, AUKUS, Commonwealth, Arab League, QUAD)
  - Bilateral enmities derived from GDELT Events 2.0 QuadClass ratios
    (already cached by gdelt_relations.py as /cache/relations.json)
  - Bilateral allies derived from the same QuadClass cooperation signal
    plus shared bloc memberships

Output shape:
  {
    blocs: { "NATO": ["USA","GBR",...], ... },
    by_country: {
      "USA": {
        blocs: ["NATO","G7","G20","QUAD","OECD"],
        allies: ["GBR","FRA","DEU","JPN","KOR","AUS","CAN",...],
        enemies: ["RUS","IRN","PRK","CHN"],
        bloc_primary: "NATO",
        bloc_color: "#2B5BAA"
      },
      ...
    }
  }
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))


LAYER = LayerMeta(
    id="country_relations",
    name="Country Relations — blocs + alliances + enmities",
    category="meta",
    kind="raw",
    source="Curated blocs + GDELT QuadClass",
    source_url="internal",
    license="Public data + CC BY 4.0 (GDELT)",
    refresh_s=21600,  # 6 hours — alliances don't change often
    initial_delay_s=55,
    description=(
        "Country blocs (NATO, EU, G7/G20, BRICS, etc) plus live bilateral "
        "cooperation/conflict signals from GDELT. Used for EU4-style alliance "
        "highlights when hovering a country."
    ),
    requires_key=False,
)


# ============================================================
# Hardcoded bloc memberships (ISO3)
# Sources: official bloc websites, last verified 2026-04
# ============================================================
BLOCS: dict[str, dict[str, Any]] = {
    "NATO": {
        "color": "#2B5BAA",
        "members": [
            "USA", "GBR", "FRA", "DEU", "ITA", "CAN", "BEL", "NLD", "LUX",
            "NOR", "DNK", "ISL", "PRT", "GRC", "TUR", "ESP", "CZE", "HUN",
            "POL", "BGR", "EST", "LVA", "LTU", "ROU", "SVK", "SVN", "HRV",
            "ALB", "MNE", "MKD", "FIN", "SWE",
        ],
    },
    "EU": {
        "color": "#003399",
        "members": [
            "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN",
            "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX",
            "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
        ],
    },
    "G7": {
        "color": "#FFD700",
        "members": ["USA", "CAN", "GBR", "FRA", "DEU", "ITA", "JPN"],
    },
    "G20": {
        "color": "#F08080",
        "members": [
            "ARG", "AUS", "BRA", "CAN", "CHN", "FRA", "DEU", "IND", "IDN",
            "ITA", "JPN", "MEX", "RUS", "SAU", "ZAF", "KOR", "TUR", "GBR", "USA",
        ],
    },
    "BRICS": {
        "color": "#DC3545",
        "members": ["BRA", "RUS", "IND", "CHN", "ZAF", "IRN", "EGY", "ETH", "ARE"],
    },
    "OECD": {
        "color": "#556B8D",
        "members": [
            "AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK",
            "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR",
            "ITA", "JPN", "KOR", "LVA", "LTU", "LUX", "MEX", "NLD", "NZL",
            "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR",
            "GBR", "USA",
        ],
    },
    "ASEAN": {
        "color": "#0066CC",
        "members": ["BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM"],
    },
    "AU": {
        "color": "#228B22",
        "members": [
            "DZA", "AGO", "BEN", "BWA", "BFA", "BDI", "CMR", "CPV", "CAF",
            "TCD", "COM", "COD", "COG", "CIV", "DJI", "EGY", "GNQ", "ERI",
            "SWZ", "ETH", "GAB", "GMB", "GHA", "GIN", "GNB", "KEN", "LSO",
            "LBR", "LBY", "MDG", "MWI", "MLI", "MRT", "MUS", "MAR", "MOZ",
            "NAM", "NER", "NGA", "RWA", "STP", "SEN", "SYC", "SLE", "SOM",
            "ZAF", "SSD", "SDN", "TZA", "TGO", "TUN", "UGA", "ZMB", "ZWE",
        ],
    },
    "MERCOSUR": {
        "color": "#FFA500",
        "members": ["ARG", "BRA", "PRY", "URY", "BOL", "VEN"],
    },
    "CIS": {
        "color": "#8B0000",
        "members": ["ARM", "AZE", "BLR", "KAZ", "KGZ", "MDA", "RUS", "TJK", "UZB"],
    },
    "GCC": {
        "color": "#DAA520",
        "members": ["BHR", "KWT", "OMN", "QAT", "SAU", "ARE"],
    },
    "AUKUS": {
        "color": "#4682B4",
        "members": ["AUS", "GBR", "USA"],
    },
    "QUAD": {
        "color": "#9370DB",
        "members": ["AUS", "IND", "JPN", "USA"],
    },
    "ARABLEAGUE": {
        "color": "#006400",
        "members": [
            "DZA", "BHR", "COM", "DJI", "EGY", "IRQ", "JOR", "KWT", "LBN",
            "LBY", "MRT", "MAR", "OMN", "PSE", "QAT", "SAU", "SOM", "SDN",
            "SYR", "TUN", "ARE", "YEM",
        ],
    },
    "COMMONWEALTH": {
        "color": "#4169E1",
        "members": [
            "GBR", "CAN", "AUS", "NZL", "IND", "ZAF", "NGA", "KEN", "GHA",
            "PAK", "BGD", "LKA", "MYS", "SGP", "JAM", "TTO", "ZWE", "UGA",
            "TZA", "ZMB", "MWI", "LSO", "BWA", "SWZ", "MOZ", "RWA",
        ],
    },
}


def _read_cache(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _primary_bloc(blocs: list[str]) -> str:
    """Return the most visually dominant bloc for a country.
    Priority: NATO > EU > G7 > BRICS > ASEAN > AU > MERCOSUR > CIS > GCC > COMMONWEALTH > G20 > OECD
    """
    priority = [
        "NATO", "EU", "G7", "BRICS", "ASEAN", "AU", "MERCOSUR",
        "CIS", "GCC", "ARABLEAGUE", "COMMONWEALTH", "QUAD", "AUKUS", "G20", "OECD",
    ]
    for p in priority:
        if p in blocs:
            return p
    return blocs[0] if blocs else ""


async def fetch(client: httpx.AsyncClient):
    # 1) Build per-country bloc membership lookup
    country_blocs: dict[str, list[str]] = {}
    for bloc, meta in BLOCS.items():
        for iso3 in meta["members"]:
            country_blocs.setdefault(iso3, []).append(bloc)

    # 2) Read GDELT QuadClass relations from existing cache
    relations = _read_cache("relations") or {}
    # relations has either .pairs or .data.pairs depending on envelope
    pairs = []
    if isinstance(relations, dict):
        if "pairs" in relations:
            pairs = relations["pairs"]
        elif "data" in relations and isinstance(relations["data"], dict):
            pairs = relations["data"].get("pairs") or []

    # 3) Build per-country allies / enemies from GDELT pair ratios
    #    ratio > 0.30 and total_events >= 20 = ally
    #    ratio < -0.30 and total_events >= 20 = enemy
    allies_map: dict[str, set] = {}
    enemies_map: dict[str, set] = {}
    for pair in pairs:
        from_iso = pair.get("from")
        to_iso = pair.get("to")
        ratio = pair.get("ratio", 0)
        total = pair.get("total_events") or pair.get("total") or 0
        if not from_iso or not to_iso or total < 20:
            continue
        if ratio >= 0.30:
            allies_map.setdefault(from_iso, set()).add(to_iso)
        elif ratio <= -0.30:
            enemies_map.setdefault(from_iso, set()).add(to_iso)

    # 4) Augment allies from shared bloc membership — every pair of countries
    #    in the same bloc is considered an ally (for hover highlighting).
    for bloc, meta in BLOCS.items():
        members = meta["members"]
        for i, a in enumerate(members):
            for b in members[i+1:]:
                allies_map.setdefault(a, set()).add(b)
                allies_map.setdefault(b, set()).add(a)

    # 5) Compose final per-country record
    all_countries = set(country_blocs.keys()) | set(allies_map.keys()) | set(enemies_map.keys())
    by_country: dict[str, dict[str, Any]] = {}
    for iso3 in sorted(all_countries):
        blocs = country_blocs.get(iso3, [])
        allies = sorted(allies_map.get(iso3, set()))
        enemies = sorted(enemies_map.get(iso3, set()))
        primary = _primary_bloc(blocs)
        by_country[iso3] = {
            "blocs": blocs,
            "bloc_primary": primary,
            "bloc_color": BLOCS[primary]["color"] if primary else "#6b7790",
            "allies": allies,
            "enemies": enemies,
        }

    return {
        "source": "WorldTwin country relations",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(by_country),
        "blocs": {name: {"color": m["color"], "members": m["members"]} for name, m in BLOCS.items()},
        "by_country": by_country,
    }


register(LAYER, fetch)
