"""NASA Mars Rover Photos — latest sol images from Curiosity and Perseverance.

Mars-only layer — only rendered when the planet selector is on Mars.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

LAYER = LayerMeta(
    id="nasa_mars_photos",
    name="Mars Rover — Latest Photos",
    category="space",
    kind="raw",
    source="NASA Mars Photo API",
    source_url="https://api.nasa.gov/mars-photos/api/v1/",
    license="Public Domain (NASA)",
    refresh_s=86400,
    initial_delay_s=95,
    description="Latest sol photos from Curiosity and Perseverance. Rendered only on the Mars planet view.",
    requires_key=True,
    key_env="NASA_API_KEY",
    enabled=bool(NASA_API_KEY),
)


async def _fetch_rover(client: httpx.AsyncClient, rover: str):
    try:
        r = await client.get(
            f"https://api.nasa.gov/mars-photos/api/v1/rovers/{rover}/latest_photos",
            params={"api_key": NASA_API_KEY},
            timeout=30,
        )
        if r.status_code != 200:
            return {"rover": rover, "photos": []}
        d = r.json()
        photos = d.get("latest_photos") or []
        # Keep top 20 per rover to stay compact
        out = []
        for p in photos[:20]:
            out.append({
                "id": p.get("id"),
                "sol": p.get("sol"),
                "earth_date": p.get("earth_date"),
                "camera": (p.get("camera") or {}).get("full_name", ""),
                "img_src": p.get("img_src", ""),
                "rover_status": (p.get("rover") or {}).get("status", ""),
            })
        return {"rover": rover, "photos": out, "total": len(photos)}
    except Exception as e:
        print(f"[nasa_mars_rovers] {rover} failed: {e}")
        return {"rover": rover, "photos": []}


async def fetch(client: httpx.AsyncClient):
    if not NASA_API_KEY:
        return None
    rovers = ["curiosity", "perseverance"]
    results = await asyncio.gather(*[_fetch_rover(client, r) for r in rovers])
    return {
        "source": "NASA Mars Photos",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": sum(len(r["photos"]) for r in results),
        "rovers": {r["rover"]: r for r in results},
        "planet_scope": "mars",
    }


register(LAYER, fetch)
