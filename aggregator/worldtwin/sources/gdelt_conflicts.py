"""GDELT doc API — conflict/war news articles."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="conflicts",
    name="Conflict News (GDELT)",
    category="war",
    kind="points",
    source="GDELT Project",
    source_url="https://api.gdeltproject.org/api/v2/doc/doc",
    license="CC0",
    refresh_s=300,
    initial_delay_s=15,
    description="Recent news articles about armed conflict, military action, or bombing.",
)


async def fetch(client: httpx.AsyncClient):
    await asyncio.sleep(10)  # Guarantee 10s gap from any other GDELT call
    r = await client.get(
        LAYER.source_url,
        params={
            "query": "conflict war military attack",
            "mode": "artlist",
            "format": "json",
            "maxrecords": 150,
            "sort": "datedesc",
        },
        timeout=30,
    )
    if r.status_code == 429:
        return None  # keep stale cache
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        return None
    articles = data.get("articles", [])
    # GDELT doesn't give lat/lon directly — mark as ungeocoded, frontend can scatter
    points = []
    for a in articles:
        points.append(point(
            lat=0.0, lon=0.0,
            id=a.get("url"),
            label=a.get("title", "")[:120],
            url=a.get("url"),
            source=a.get("domain", ""),
            date=a.get("seendate", ""),
            image=a.get("socialimage", ""),
            geocoded=False,
        ))
    return points, data


register(LAYER, fetch)
