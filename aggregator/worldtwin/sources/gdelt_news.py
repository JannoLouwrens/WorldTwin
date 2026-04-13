"""GDELT doc API — breaking news."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="news",
    name="Breaking News (GDELT)",
    category="social",
    kind="points",
    source="GDELT Project",
    source_url="https://api.gdeltproject.org/api/v2/doc/doc",
    license="CC0",
    refresh_s=300,
    initial_delay_s=45,
    description="Recent global breaking news articles.",
)


async def fetch(client: httpx.AsyncClient):
    await asyncio.sleep(10)
    r = await client.get(
        LAYER.source_url,
        params={
            "query": "breaking news world",
            "mode": "artlist",
            "format": "json",
            "maxrecords": 150,
            "sort": "datedesc",
        },
        timeout=30,
    )
    if r.status_code == 429:
        return None
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        return None
    articles = data.get("articles", [])
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
