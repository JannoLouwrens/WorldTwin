"""HDX (Humanitarian Data Exchange) — crisis datasets.
Fallback for ReliefWeb which now blocks all non-approved appnames.
"""
import json
from pathlib import Path

import httpx

from .. import cache
from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="crises",
    name="Humanitarian Crises",
    category="war",
    kind="points",
    source="HDX / NASA EONET (derived)",
    source_url="https://data.humdata.org/api/3/action/package_search",
    license="HDX open license",
    refresh_s=1800,
    initial_delay_s=10,
    description="Active humanitarian datasets and crisis events.",
)


async def fetch(client: httpx.AsyncClient):
    # Try HDX for crisis-labeled datasets
    try:
        r = await client.get(
            "https://data.humdata.org/api/3/action/package_search",
            params={
                "q": "crisis OR disaster OR emergency",
                "fq": "res_format:(GeoJSON OR JSON)",
                "rows": 1000,    # widened from 50 — full HDX crisis catalogue per fetch
                "sort": "metadata_modified desc",
            },
            timeout=30,
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("result", {}).get("results", [])
            # HDX doesn't give lat/lon directly — we emit raw records as points with no coords
            # and flag them so the client can choose to render or list only.
            points = []
            for pkg in results:
                points.append(point(
                    lat=0.0, lon=0.0,  # HDX doesn't expose coords directly
                    id=pkg.get("id"),
                    label=pkg.get("title", ""),
                    description=(pkg.get("notes") or "")[:300],
                    date=pkg.get("metadata_modified"),
                    url=f"https://data.humdata.org/dataset/{pkg.get('name','')}",
                    geocoded=False,
                ))
            legacy = {"data": [
                {
                    "name": p.get("label"),
                    "country": (pkg.get("groups") or [{}])[0].get("title", ""),
                    "description": p["props"].get("description"),
                    "date": p["props"].get("date"),
                    "url": p["props"].get("url"),
                }
                for p, pkg in zip(points, results)
            ], "source": "HDX"}
            if points:
                return points, legacy
    except Exception:
        pass

    # Fallback: derive from EONET disasters cache if available
    eonet_path = cache.legacy_path("disasters")
    if eonet_path.exists():
        try:
            with eonet_path.open() as f:
                eonet = json.load(f)
            points = []
            legacy_list = []
            for ev in eonet.get("events", []):
                if not ev.get("categories"):
                    continue
                cat = ev["categories"][0].get("title", "")
                geo = ev.get("geometry") or []
                if not geo:
                    continue
                coords = geo[-1].get("coordinates") or []
                if len(coords) < 2:
                    continue
                p = point(
                    lat=coords[1], lon=coords[0],
                    id=ev.get("id"),
                    label=ev.get("title", cat),
                    category=cat,
                    date=geo[-1].get("date"),
                    url=((ev.get("sources") or [{}])[0].get("url")),
                )
                points.append(p)
                legacy_list.append({
                    "name": ev.get("title"),
                    "type": cat,
                    "date": geo[-1].get("date"),
                    "coordinates": coords,
                    "url": p["props"].get("url"),
                })
            return points, {"data": legacy_list, "source": "EONET-derived"}
        except Exception:
            pass
    return None


register(LAYER, fetch)
