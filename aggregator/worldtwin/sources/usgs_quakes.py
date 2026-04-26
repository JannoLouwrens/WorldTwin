"""USGS earthquakes — past 24h, M2.5+."""
import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="quakes",
    name="Earthquakes (M2.5+ past day)",
    category="nature",
    kind="points",
    source="USGS Earthquake Hazards Program",
    source_url="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
    license="Public domain (US Government)",
    refresh_s=120,
    initial_delay_s=4,
    units="magnitude (Richter)",
    description="All magnitude 2.5+ earthquakes in the past 24 hours worldwide.",
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get(LAYER.source_url, timeout=30)
    r.raise_for_status()
    geo = r.json()
    # Normalized v1 data
    points = []
    for f in geo.get("features", []):
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        props = f.get("properties") or {}
        mag = props.get("mag")
        if mag is None:
            continue
        points.append(point(
            lat=coords[1],
            lon=coords[0],
            id=f.get("id"),
            value=mag,
            label=f"M{mag:.1f}",
            place=props.get("place", ""),
            depth_km=coords[2] if len(coords) > 2 else None,
            time_ms=props.get("time"),
            usgs_url=props.get("url", ""),
        ))
    # Freshness timestamp — injected into both shapes
    from datetime import datetime, timezone
    geo["fetched"] = datetime.now(timezone.utc).isoformat()
    # Legacy: raw GeoJSON (current frontend expects this exact shape)
    return points, geo


register(LAYER, fetch)
