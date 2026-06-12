"""NASA Mars Rover Photos — latest sol images from Curiosity and Perseverance.

Mars-only layer — only rendered when the planet selector is on Mars.

The old api.nasa.gov/mars-photos API was retired (404, verified 2026-06-12;
its heroku mirror is dead too). This now reads the raw-image feeds that power
mars.nasa.gov's own galleries — no API key required.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="nasa_mars_photos",
    name="Mars Rover — Latest Photos",
    category="space",
    kind="raw",
    source="NASA Mars Raw Images",
    source_url="https://mars.nasa.gov/mars2020/multimedia/raw-images/",
    license="Public Domain (NASA)",
    refresh_s=86400,
    initial_delay_s=95,
    description="Latest sol photos from Curiosity and Perseverance. Rendered only on the Mars planet view.",
)

# Feeds behind mars.nasa.gov's raw-image galleries. Curiosity (msl) is only
# served by the raw_image_items endpoint; Perseverance (mars2020) by rss/api.
CURIOSITY_URL = (
    "https://mars.nasa.gov/api/v1/raw_image_items/"
    "?order=sol+desc&per_page=40&page=0&condition_1=msl:mission"
)
PERSEVERANCE_URL = (
    "https://mars.nasa.gov/rss/api/"
    "?feed=raw_images&category=mars2020&feedtype=json&num=40&order=sol+desc"
)


def _parse_curiosity(d: dict) -> list[dict]:
    out = []
    for p in d.get("items") or []:
        if p.get("is_thumbnail"):
            continue
        out.append({
            "id": p.get("imageid") or p.get("id"),
            "sol": p.get("sol"),
            "earth_date": str(p.get("date_taken") or "")[:10],
            "camera": p.get("instrument", ""),
            "img_src": p.get("https_url") or p.get("url") or "",
            "rover_status": "",
        })
    return out


def _parse_perseverance(d: dict) -> list[dict]:
    out = []
    for p in d.get("images") or []:
        if "thumbnail" in str(p.get("sample_type") or "").lower():
            continue
        files = p.get("image_files") or {}
        # title looks like "Mars Perseverance Sol 1888: Right Mastcam-Z Camera"
        title = p.get("title") or ""
        out.append({
            "id": p.get("imageid"),
            "sol": p.get("sol"),
            "earth_date": str(p.get("date_taken_utc") or "")[:10],
            "camera": title.split(": ", 1)[-1] or (p.get("camera") or {}).get("instrument", ""),
            "img_src": files.get("large") or files.get("medium") or files.get("full_res") or "",
            "rover_status": "",
        })
    return out


ROVERS = {
    "curiosity": (CURIOSITY_URL, _parse_curiosity),
    "perseverance": (PERSEVERANCE_URL, _parse_perseverance),
}


async def _fetch_rover(client: httpx.AsyncClient, rover: str):
    url, parse = ROVERS[rover]
    try:
        r = await client.get(url, timeout=30)
        if r.status_code != 200:
            print(f"[nasa_mars_rovers] {rover} HTTP {r.status_code}")
            return None
        photos = parse(r.json())
        # Keep top 20 per rover to stay compact
        return {"rover": rover, "photos": photos[:20], "total": len(photos)}
    except Exception as e:
        print(f"[nasa_mars_rovers] {rover} failed: {e}")
        return None


async def fetch(client: httpx.AsyncClient):
    results = await asyncio.gather(*[_fetch_rover(client, r) for r in ROVERS])
    ok = [r for r in results if r is not None]
    if not ok:
        # Both rovers failed — return None so the previous cache is kept.
        return None
    return {
        "source": "NASA Mars Photos",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": sum(len(r["photos"]) for r in ok),
        "rovers": {r["rover"]: r for r in ok},
        "planet_scope": "mars",
    }


register(LAYER, fetch)
