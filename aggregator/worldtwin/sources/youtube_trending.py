"""YouTube Data API v3 — trending videos per country.

Fetches the `mostPopular` video chart for ~25 countries and returns
the top 5 from each as geotagged points (positioned at the country capital).

Quota: each mostPopular call = 1 unit. 25 countries = 25 units per fetch.
Free quota = 10,000/day → safely within budget even fetching hourly.

Requires YOUTUBE_API_KEY env var. Free key at:
https://console.cloud.google.com/apis → enable YouTube Data API v3
"""
import asyncio
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

YOUTUBE_KEY = os.environ.get("YOUTUBE_API_KEY", "")

# Country code → (lat, lon, display name) at the capital
# YouTube uses ISO 3166-1 alpha-2 codes
COUNTRIES = [
    ("US", 38.90, -77.04, "United States"),
    ("GB", 51.51, -0.13, "United Kingdom"),
    ("DE", 52.52, 13.41, "Germany"),
    ("FR", 48.86, 2.35, "France"),
    ("IT", 41.90, 12.50, "Italy"),
    ("ES", 40.42, -3.70, "Spain"),
    ("NL", 52.37, 4.89, "Netherlands"),
    ("SE", 59.33, 18.07, "Sweden"),
    ("PL", 52.23, 21.01, "Poland"),
    ("RU", 55.75, 37.62, "Russia"),
    ("TR", 39.93, 32.87, "Turkey"),
    ("JP", 35.68, 139.77, "Japan"),
    ("KR", 37.57, 126.98, "South Korea"),
    ("CN", 39.90, 116.40, "China"),
    ("IN", 28.61, 77.21, "India"),
    ("ID", -6.21, 106.85, "Indonesia"),
    ("TH", 13.76, 100.50, "Thailand"),
    ("VN", 21.03, 105.85, "Vietnam"),
    ("PH", 14.60, 120.98, "Philippines"),
    ("AU", -35.31, 149.13, "Australia"),
    ("CA", 45.42, -75.70, "Canada"),
    ("BR", -15.79, -47.88, "Brazil"),
    ("MX", 19.43, -99.13, "Mexico"),
    ("AR", -34.60, -58.38, "Argentina"),
    ("EG", 30.04, 31.24, "Egypt"),
    ("ZA", -25.75, 28.19, "South Africa"),
    ("NG", 9.08, 7.48, "Nigeria"),
    ("SA", 24.71, 46.68, "Saudi Arabia"),
    ("AE", 24.47, 54.37, "UAE"),
    ("IL", 31.77, 35.22, "Israel"),
]

LAYER = LayerMeta(
    id="youtube",
    name="YouTube Trending",
    category="social",
    kind="points",
    source="YouTube Data API v3",
    source_url="https://developers.google.com/youtube/v3/docs/videos/list",
    license="YouTube API ToS",
    refresh_s=3600,          # 25 countries × 1 unit × 24/day = 600 units/day
    initial_delay_s=50,
    description="Top 5 trending videos for ~30 major countries, geotagged at the country capital.",
    requires_key=True,
    key_env="YOUTUBE_API_KEY",
    enabled=bool(YOUTUBE_KEY),
)


async def fetch(client: httpx.AsyncClient):
    if not YOUTUBE_KEY:
        return None

    sem = asyncio.Semaphore(6)
    v1_points: list = []
    legacy_countries: list = []

    async def fetch_one(code: str, lat: float, lon: float, name: str):
        async with sem:
            try:
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params={
                        "part": "snippet,statistics",
                        "chart": "mostPopular",
                        "regionCode": code,
                        "maxResults": 5,
                        "key": YOUTUBE_KEY,
                    },
                    timeout=20,
                )
                if r.status_code != 200:
                    return
                data = r.json()
                items = data.get("items", [])
                if not items:
                    return
                top_videos = []
                for v in items:
                    snip = v.get("snippet") or {}
                    stats = v.get("statistics") or {}
                    top_videos.append({
                        "id": v.get("id"),
                        "title": snip.get("title", ""),
                        "channel": snip.get("channelTitle", ""),
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)) if stats.get("likeCount") else None,
                        "thumbnail": ((snip.get("thumbnails") or {}).get("medium") or {}).get("url", ""),
                        "published": snip.get("publishedAt", ""),
                        "url": f"https://www.youtube.com/watch?v={v.get('id')}",
                    })
                top1 = top_videos[0]
                v1_points.append(point(
                    lat=lat, lon=lon,
                    id=code,
                    label=f"{name} · {top1['title'][:60]}",
                    value=top1["views"],
                    country=name,
                    country_code=code,
                    top_video=top1,
                    videos=top_videos,
                ))
                legacy_countries.append({
                    "code": code,
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "videos": top_videos,
                })
            except Exception:
                pass

    await asyncio.gather(*[fetch_one(c, la, lo, n) for (c, la, lo, n) in COUNTRIES])

    if not v1_points:
        return None

    legacy = {
        "source": "YouTube Data API v3",
        "countries": legacy_countries,
        "total_countries": len(legacy_countries),
    }
    return v1_points, legacy


register(LAYER, fetch)
