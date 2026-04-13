"""Country polygons — Natural Earth 1:50m admin-0 countries GeoJSON.

Fetched once a week. Stamps every feature with standardised iso3 + name +
population + continent for the EU4-style mapmode system.

CC0 public domain — no attribution required but we credit Natural Earth.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="country_polygons",
    name="Country Polygons (Natural Earth 50m)",
    category="meta",
    kind="raw",
    source="Natural Earth 1:50m Cultural",
    source_url="https://www.naturalearthdata.com/",
    license="CC0 (public domain)",
    refresh_s=86400 * 7,
    initial_delay_s=40,
    description=(
        "242 country polygons from Natural Earth 1:50m. Every feature has "
        "iso3, name, population, continent stamped in properties. This is THE "
        "polygon file every mapmode reads from."
    ),
    requires_key=False,
)


NE_URLS = [
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson",
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson",
]


async def fetch(client: httpx.AsyncClient):
    for url in NE_URLS:
        try:
            r = await client.get(url, timeout=120, headers={"User-Agent": "WorldTwin/1.0"})
            if r.status_code != 200:
                continue
            geo = r.json()
            feats = geo.get("features") or []
            if not feats:
                continue
            # Normalise: stamp each feature with lowercase iso3 + population + continent
            out_feats = []
            by_iso3: dict[str, dict[str, Any]] = {}
            for f in feats:
                props = f.get("properties") or {}
                iso3 = props.get("ADM0_A3") or props.get("ISO_A3") or props.get("iso_a3") or ""
                if not iso3 or iso3 == "-99":
                    iso3 = props.get("SOV_A3") or props.get("GU_A3") or ""
                name = props.get("NAME") or props.get("ADMIN") or ""
                pop = props.get("POP_EST") or 0
                continent = props.get("CONTINENT") or ""
                region = props.get("REGION_UN") or ""
                subregion = props.get("SUBREGION") or ""
                # Strip noisy legacy properties — keep only what mapmodes need
                clean_props = {
                    "iso3": iso3,
                    "name": name,
                    "admin": props.get("ADMIN") or name,
                    "pop": pop,
                    "continent": continent,
                    "region": region,
                    "subregion": subregion,
                    "income_grp": props.get("INCOME_GRP") or "",
                    "economy": props.get("ECONOMY") or "",
                    "iso_a2": props.get("ISO_A2") or "",
                }
                out_feats.append({
                    "type": "Feature",
                    "properties": clean_props,
                    "geometry": f.get("geometry"),
                })
                if iso3:
                    by_iso3[iso3] = clean_props

            return {
                "type": "FeatureCollection",
                "source": "Natural Earth 1:50m",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": len(out_feats),
                "features": out_feats,
                "by_iso3": by_iso3,
            }
        except Exception as e:
            print(f"[country_polygons] {url.split('/')[-1]} error: {e}")
            continue
    return None


register(LAYER, fetch)
