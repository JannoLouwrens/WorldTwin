"""NASA EPIC — DSCOVR full-disk Earth images from Sun-Earth L1.

Returns the latest full-disk natural-colour image of Earth taken from the
DSCOVR spacecraft at L1 Lagrange point.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from .. import cache
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="nasa_epic_earth",
    name="NASA EPIC — L1 Earth Images",
    category="space",
    kind="raw",
    source="NASA EPIC (DSCOVR)",
    # api.nasa.gov's EPIC proxy now 302-redirects to a GitHub-Pages 404
    # (verified 2026-06-12) — use the canonical keyless GSFC API instead.
    source_url="https://epic.gsfc.nasa.gov/api/natural",
    license="Public Domain (NASA)",
    refresh_s=10800,
    initial_delay_s=110,
    description="Latest full-disk Earth images from DSCOVR at Sun-Earth L1. Sub-solar point per image.",
)


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://epic.gsfc.nasa.gov/api/natural",
            timeout=30,
        )
        if r.status_code != 200:
            # Surface the failure in /api/health — scheduler skips silently on None.
            cache.mark_error(LAYER.id, f"HTTP {r.status_code} from EPIC API")
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
        cache.mark_error(LAYER.id, f"{type(e).__name__}: {e}")
        return None


register(LAYER, fetch)
