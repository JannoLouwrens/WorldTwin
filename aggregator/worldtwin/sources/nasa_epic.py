"""NASA EPIC — DSCOVR full-disk Earth images from Sun-Earth L1.

Returns the latest full-disk natural-colour image of Earth taken from the
DSCOVR spacecraft at L1 Lagrange point.
"""
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

LAYER = LayerMeta(
    id="nasa_epic_earth",
    name="NASA EPIC — L1 Earth Images",
    category="space",
    kind="raw",
    source="NASA EPIC (DSCOVR)",
    source_url="https://api.nasa.gov/EPIC/api/natural/images",
    license="Public Domain (NASA)",
    refresh_s=10800,
    initial_delay_s=110,
    description="Latest full-disk Earth images from DSCOVR at Sun-Earth L1. Sub-solar point per image.",
    requires_key=True,
    key_env="NASA_API_KEY",
    enabled=bool(NASA_API_KEY),
)


async def fetch(client: httpx.AsyncClient):
    if not NASA_API_KEY:
        return None
    try:
        r = await client.get(
            "https://api.nasa.gov/EPIC/api/natural/images",
            params={"api_key": NASA_API_KEY},
            timeout=30,
        )
        if r.status_code != 200:
            return None
        rows = r.json() or []
        images = []
        for row in rows[:24]:
            images.append({
                "identifier": row.get("identifier"),
                "caption": row.get("caption", ""),
                "date": row.get("date", ""),
                "image": row.get("image", ""),
                "centroid": row.get("centroid_coordinates") or {},
                "dscovr_j2000": row.get("dscovr_j2000_position") or {},
            })
        return {
            "source": "NASA EPIC",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(images),
            "latest": images[0] if images else None,
            "images": images,
        }
    except Exception as e:
        print(f"[nasa_epic] error: {e}")
        return None


register(LAYER, fetch)
