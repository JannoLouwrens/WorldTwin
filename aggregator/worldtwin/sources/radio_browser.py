"""Radio Browser — worldwide radio stations."""
import httpx

from ..models import LayerMeta, point
from ..registry import register

SERVERS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
]

LAYER = LayerMeta(
    id="radio",
    name="Radio Stations",
    category="social",
    kind="points",
    source="Radio Browser (community)",
    source_url="https://www.radio-browser.info/",
    license="CC0",
    refresh_s=86400,
    initial_delay_s=26,
    description="Top 500 internet radio stations with geographic location data.",
)


async def fetch(client: httpx.AsyncClient):
    for server in SERVERS:
        try:
            r = await client.get(
                f"{server}/json/stations/search",
                params={
                    "limit": 500,
                    "offset": 0,
                    "order": "clickcount",
                    "reverse": "true",
                    "has_geo_info": "true",
                },
                headers={"User-Agent": "WorldTwin/1.0"},
                timeout=30,
            )
            r.raise_for_status()
            stations = [s for s in r.json() if s.get("geo_lat") and s.get("geo_long")]
            points = []
            for s in stations:
                try:
                    lat = float(s["geo_lat"])
                    lon = float(s["geo_long"])
                except (TypeError, ValueError):
                    continue
                points.append(point(
                    lat=lat, lon=lon,
                    id=s.get("stationuuid"),
                    label=s.get("name", "Station"),
                    url=s.get("url_resolved") or s.get("url"),
                    country=s.get("country"),
                    language=s.get("language"),
                    tags=s.get("tags"),
                    codec=s.get("codec"),
                    bitrate=s.get("bitrate"),
                    votes=s.get("votes"),
                ))
            return points, stations
        except Exception:
            continue
    return None


register(LAYER, fetch)
