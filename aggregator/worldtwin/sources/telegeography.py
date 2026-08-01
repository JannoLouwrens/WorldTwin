"""TeleGeography — submarine internet cable map."""
import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="cables",
    name="Submarine Internet Cables",
    category="infra",
    kind="raw",  # GeoJSON FeatureCollection — clients render polylines
    source="TeleGeography",
    source_url="https://www.submarinecablemap.com/api/v3/cable/cable-geo.json",
    license="CC BY-NC-SA 3.0",
    refresh_s=86400,
    initial_delay_s=24,
    description="All major operational submarine internet cables.",
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=60)
    r.raise_for_status()
    geo = r.json()
    # Same shape for v1 and legacy — clients handle GeoJSON directly
    return geo, geo


register(LAYER, fetch)
