"""Windy — worldwide webcams."""
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

# NEVER commit the key inline. Set WINDY_KEY in .env.
WINDY_KEY = os.environ.get("WINDY_KEY", "")

LAYER = LayerMeta(
    id="webcams",
    name="Live Webcams",
    category="infra",
    kind="points",
    source="Windy Webcams",
    source_url="https://api.windy.com/webcams/api/v3/webcams",
    license="Windy API Terms",
    refresh_s=1800,
    initial_delay_s=30,
    description="Top 500 public webcams worldwide.",
    requires_key=True,
    key_env="WINDY_KEY",
)


async def fetch(client: httpx.AsyncClient):
    all_cams = []
    for offset in range(0, 500, 50):
        r = await client.get(
            LAYER.source_url,
            params={
                "lang": "en",
                "limit": 50,
                "offset": offset,
                "include": "images,location,player",
            },
            headers={"X-WINDY-API-KEY": WINDY_KEY},
            timeout=30,
        )
        if r.status_code != 200:
            break
        cams = r.json().get("webcams", [])
        if not cams:
            break
        all_cams.extend(cams)
    points = []
    for cam in all_cams:
        loc = cam.get("location") or {}
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if lat is None or lon is None:
            continue
        img = ""
        imgs = cam.get("images") or {}
        cur = imgs.get("current")
        if isinstance(cur, dict):
            img = cur.get("preview") or cur.get("thumbnail") or ""
        elif isinstance(cur, str):
            img = cur
        player = ""
        pl = cam.get("player") or {}
        day = pl.get("day") if isinstance(pl, dict) else None
        if isinstance(day, dict):
            player = day.get("embed", "")
        elif isinstance(day, str):
            player = day
        points.append(point(
            lat=lat, lon=lon,
            id=str(cam.get("webcamId", "")),
            label=cam.get("title", "Webcam"),
            image=img,
            player=player or f"https://www.windy.com/webcams/{cam.get('webcamId','')}",
            city=loc.get("city"),
            country=loc.get("country"),
            status=cam.get("status"),
        ))
    return points, {"webcams": all_cams, "total": len(all_cams)}


register(LAYER, fetch)
