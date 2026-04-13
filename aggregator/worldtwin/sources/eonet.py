"""NASA EONET — Earth Observatory natural events."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="disasters",
    name="Natural Disasters (EONET)",
    category="nature",
    kind="points",
    source="NASA EONET",
    source_url="https://eonet.gsfc.nasa.gov/api/v3/events",
    license="NASA open data",
    refresh_s=600,
    initial_delay_s=8,
    description="Active wildfires, storms, volcanoes, floods, and other natural events tracked by NASA.",
)


async def fetch(client: httpx.AsyncClient):
    url = "https://eonet.gsfc.nasa.gov/api/v3/events"
    params = {"status": "open", "limit": 200}
    # EONET can be flaky — retry with backoff
    for attempt in range(3):
        r = await client.get(url, params=params, timeout=30)
        if r.status_code == 503:
            wait = 15
            try:
                wait = int(r.json().get("retry_after", 15))
            except Exception:
                pass
            await asyncio.sleep(wait + 1)
            continue
        r.raise_for_status()
        raw = r.json()
        events = raw.get("events", [])
        points = []
        for evt in events:
            geo = evt.get("geometry") or []
            if not geo:
                continue
            last = geo[-1]
            coords = last.get("coordinates") or []
            if len(coords) < 2:
                continue
            cat = (evt.get("categories") or [{}])[0].get("title", "?")
            points.append(point(
                lat=coords[1], lon=coords[0],
                id=evt.get("id"),
                label=evt.get("title", cat),
                category=cat,
                date=last.get("date"),
                description=evt.get("description", ""),
                sources=[s.get("url") for s in evt.get("sources", []) if s.get("url")],
            ))
        return points, raw
    return None


register(LAYER, fetch)
