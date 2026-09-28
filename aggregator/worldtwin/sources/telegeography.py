"""TeleGeography — submarine internet cable map.

LEGAL: upstream is CC BY-NC-SA 3.0 and attribution is mandatory. The served
payload embeds an `attribution` member (GeoJSON foreign member) so re-serving
the cache endpoint can never strip it (MASTER_PLAN §4 resources/cables).
"""
import httpx

from ..models import LayerMeta
from ..registry import register

ATTRIBUTION = (
    "Submarine Cable Map © TeleGeography "
    "(https://www.submarinecablemap.com) — "
    "licensed CC BY-NC-SA 3.0 "
    "(https://creativecommons.org/licenses/by-nc-sa/3.0/)"
)

LAYER = LayerMeta(
    id="cables",
    name="Submarine Internet Cables",
    category="infra",
    kind="raw",  # GeoJSON FeatureCollection (MultiLineString) — clients render polylines
    source="TeleGeography",
    source_url="https://www.submarinecablemap.com/api/v3/cable/cable-geo.json",
    license="CC BY-NC-SA 3.0",
    refresh_s=86400,
    initial_delay_s=24,
    max_staleness_s=45 * 86400,  # static-ish infrastructure data
    description="All major operational submarine internet cables.",
    enabled=True,
)


def _quantize(coords, ndigits: int = 4):
    """Recursively round nested coordinate arrays to `ndigits` decimals.

    4 dp ≈ 11 m — invisible at globe zoom, halves the gzipped payload
    (upstream ships full-precision floats)."""
    if isinstance(coords, (int, float)) and not isinstance(coords, bool):
        return round(coords, ndigits)
    if isinstance(coords, list):
        return [_quantize(c, ndigits) for c in coords]
    return coords


async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=60)
    r.raise_for_status()
    geo = r.json()
    # Undocumented internal endpoint, no fallback: a partial or malformed
    # response must NOT clobber the cache. The real map carries ~730 cables;
    # anything <=100 features is a truncated/degraded payload — return None
    # so the scheduler marks the attempt and keeps the previous cache.
    if not isinstance(geo, dict) or geo.get("type") != "FeatureCollection":
        return None
    features = geo.get("features")
    if not isinstance(features, list) or len(features) <= 100:
        return None
    for f in features:
        geom = f.get("geometry")
        if isinstance(geom, dict) and "coordinates" in geom:
            geom["coordinates"] = _quantize(geom["coordinates"])
        props = f.get("properties")
        if isinstance(props, dict) and "coordinates" in props:
            props["coordinates"] = _quantize(props["coordinates"])
    # Mandatory CC BY-NC-SA attribution, carried inside the payload itself.
    geo["attribution"] = ATTRIBUTION
    geo["license"] = "CC BY-NC-SA 3.0"
    # Same shape for v1 and legacy — clients handle GeoJSON directly
    return geo, geo


register(LAYER, fetch)
