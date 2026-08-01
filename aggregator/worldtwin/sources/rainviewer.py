"""RainViewer weather radar tile metadata."""
import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="rainviewer",
    name="Weather Radar Tiles",
    category="nature",
    kind="tiles",
    source="RainViewer",
    source_url="https://api.rainviewer.com/public/weather-maps.json",
    license="Free",
    refresh_s=300,
    initial_delay_s=18,
    description="Global precipitation radar tile index (past and forecast frames).",
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=15)
    r.raise_for_status()
    raw = r.json()
    # Normalized v1: just pass the structure as a 'tiles' kind — single metadata blob
    # The host + frames give the tile URL templates.
    host = raw.get("host", "")
    past = raw.get("radar", {}).get("past", [])
    v1 = {
        "host": host,
        "url_template": f"{host}{{path}}/256/{{z}}/{{x}}/{{y}}/6/1_1.png",
        "min_zoom": 0,
        "max_zoom": 6,
        "attribution": "RainViewer",
        "frames": past,
    }
    return v1, raw


register(LAYER, fetch)
