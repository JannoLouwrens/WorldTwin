"""geoBoundaries ADM0/ADM1/ADM2 polygons for every country.

Fetches each country's ADM1 (province/state) simplified GeoJSON and merges
into a single FeatureCollection keyed by ISO3 + admUnit. CC-BY / ODbL.

This is the backbone for per-province clicks and the resources choropleth.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc


LAYER = LayerMeta(
    id="geoboundaries_adm1",
    name="Administrative Boundaries — ADM1 (geoBoundaries)",
    category="meta",
    kind="raw",
    source="geoBoundaries (William & Mary geoLab)",
    source_url="https://www.geoboundaries.org/api/current/gbOpen/",
    license="CC-BY 4.0 / ODbL",
    refresh_s=86400 * 30,  # monthly
    initial_delay_s=280,
    description=(
        "ADM1 (province/state) boundaries for every country in the world, "
        "simplified geometry for web rendering. Used as the choropleth "
        "backbone for per-province energy/water/threat overlays."
    ),
    requires_key=False,
)


# Top 60 countries by economic weight — ADM1 only for these to keep cache size sensible
PRIORITY_ISO3 = [
    "USA", "CHN", "IND", "RUS", "BRA", "CAN", "AUS", "DEU", "FRA", "GBR",
    "JPN", "KOR", "ITA", "ESP", "POL", "TUR", "MEX", "IDN", "SAU", "IRN",
    "ZAF", "EGY", "NGA", "COL", "ARG", "CHL", "PER", "VEN", "PAK", "BGD",
    "VNM", "THA", "PHL", "MYS", "NLD", "BEL", "CHE", "AUT", "SWE", "NOR",
    "FIN", "DNK", "PRT", "GRC", "CZE", "HUN", "UKR", "KAZ", "ETH", "KEN",
    "MAR", "DZA", "IRQ", "ARE", "ISR", "NZL", "SGP", "DOM", "GTM", "CUB",
]


async def _fetch_one(client: httpx.AsyncClient, iso3: str, sem: asyncio.Semaphore):
    async with sem:
        try:
            r = await client.get(
                f"https://www.geoboundaries.org/api/current/gbOpen/{iso3}/ADM1/",
                timeout=30,
            )
            if r.status_code != 200:
                return None
            meta = r.json()
            gj_url = meta.get("simplifiedGeometryGeoJSON") or meta.get("gjDownloadURL")
            if not gj_url:
                return None
            g = await client.get(gj_url, timeout=60)
            if g.status_code != 200:
                return None
            gj = g.json()
            await asyncio.sleep(0.3)
            return iso3, gj
        except Exception as e:
            print(f"[geoboundaries] {iso3} failed: {e}")
            return None


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(4)
    tasks = [_fetch_one(client, iso3, sem) for iso3 in PRIORITY_ISO3]
    results = await asyncio.gather(*tasks)

    # Merge every country's features into one giant FeatureCollection,
    # stamping each feature with its iso3 for easy client-side lookup.
    merged_features = []
    by_iso3 = {}
    for r in results:
        if not r:
            continue
        iso3, gj = r
        feats = gj.get("features", [])
        by_iso3[iso3] = len(feats)
        for f in feats:
            props = f.get("properties") or {}
            props["iso3"] = iso3
            f["properties"] = props
            merged_features.append(f)

    return {
        "type": "FeatureCollection",
        "source": "geoBoundaries ADM1",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(merged_features),
        "by_iso3": by_iso3,
        "features": merged_features,
    }


register(LAYER, fetch)
