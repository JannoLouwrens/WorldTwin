"""Wikidata SPARQL — geocoded battles since 2023.

Free, CC0/CC-BY-SA, map-legal. A curated goldmine that no other
public globe visualises.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="wikidata_battles",
    name="Notable Battles (Wikidata)",
    category="war",
    kind="points",
    source="Wikidata SPARQL (P31=Q178561)",
    source_url="https://query.wikidata.org/sparql",
    license="CC0 / CC-BY-SA",
    refresh_s=21600,  # 6h — Wikidata edits continuously
    initial_delay_s=100,
    description=(
        "All Wikidata-indexed battles with coordinates and dates since 2023. "
        "Each battle links back to its Wikipedia article."
    ),
    requires_key=False,
)


SPARQL_QUERY = """
SELECT DISTINCT ?battle ?battleLabel ?coord ?date ?article WHERE {
  ?battle wdt:P31/wdt:P279* wd:Q178561 ;
          wdt:P625 ?coord ;
          wdt:P585 ?date .
  FILTER(?date >= "2023-01-01T00:00:00Z"^^xsd:dateTime)
  OPTIONAL {
    ?article schema:about ?battle ;
             schema:isPartOf <https://en.wikipedia.org/> .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
ORDER BY DESC(?date)
LIMIT 500
"""


def _parse_wkt_point(wkt: str):
    """Parse 'Point(lon lat)' to (lat, lon)."""
    try:
        inside = wkt.strip().replace("Point(", "").rstrip(")")
        lon, lat = inside.split()
        return float(lat), float(lon)
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://query.wikidata.org/sparql",
            params={"format": "json", "query": SPARQL_QUERY},
            headers={"User-Agent": "WorldTwin/1.0 (janno@grassrootsgroup.co.za)"},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        bindings = data.get("results", {}).get("bindings", [])
        battles = []
        for b in bindings:
            wkt = b.get("coord", {}).get("value", "")
            coords = _parse_wkt_point(wkt)
            if not coords:
                continue
            lat, lon = coords
            battles.append({
                "id": b.get("battle", {}).get("value", "").split("/")[-1],
                "name": b.get("battleLabel", {}).get("value", ""),
                "lat": lat,
                "lon": lon,
                "date": b.get("date", {}).get("value", ""),
                "wikidata_url": b.get("battle", {}).get("value", ""),
                "article_url": b.get("article", {}).get("value", ""),
            })
        battles.sort(key=lambda x: x["date"], reverse=True)
        payload = {
            "source": "Wikidata SPARQL",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(battles),
            "battles": battles,
        }
        return payload
    except Exception as e:
        print(f"[wikidata_battles] error: {e}")
        return None


register(LAYER, fetch)
