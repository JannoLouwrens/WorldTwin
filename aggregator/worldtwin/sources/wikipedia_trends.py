"""Wikipedia pageviews — yesterday's top-read articles."""
from datetime import datetime, timedelta, timezone

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="trends",
    name="Wikipedia Trends",
    category="social",
    kind="raw",
    source="Wikimedia Pageviews API",
    source_url="https://wikimedia.org/api/rest_v1/metrics/pageviews/top/",
    license="CC BY-SA",
    refresh_s=3600,
    initial_delay_s=38,
    description="Top 50 most-read Wikipedia articles worldwide from the previous day.",
)


async def fetch(client: httpx.AsyncClient):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y/%m/%d")
    r = await client.get(
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{yesterday}",
        timeout=20,
        headers={"User-Agent": "WorldTwin/1.0"},
    )
    r.raise_for_status()
    data = r.json()
    items = ((data.get("items") or [{}])[0]).get("articles", [])
    filtered = [
        {
            "title": a.get("article", "").replace("_", " "),
            "views": a.get("views", 0),
            "rank": a.get("rank", 0),
            "url": f"https://en.wikipedia.org/wiki/{a.get('article','')}",
        }
        for a in items
        if a.get("article")
        and not a.get("article", "").startswith("Special:")
        and a.get("article") != "Main_Page"
    ][:50]
    payload = {"source": "Wikipedia", "date": yesterday, "top": filtered}
    return payload, payload


register(LAYER, fetch)
