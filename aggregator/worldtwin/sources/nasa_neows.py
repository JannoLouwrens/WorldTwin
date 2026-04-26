"""NASA NeoWs — Near Earth Object Web Service.

Asteroid close approaches in the next 7 days. List of potentially hazardous
objects with estimated diameter, miss distance, and relative velocity.
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

LAYER = LayerMeta(
    id="nasa_neows",
    name="NASA NeoWs — Asteroid Close Approaches",
    category="space",
    kind="raw",
    source="NASA Near Earth Object Web Service",
    source_url="https://api.nasa.gov/neo/rest/v1/feed",
    license="Public Domain (NASA)",
    refresh_s=86400,  # daily — full 38k-asteroid catalogue is heavy
    initial_delay_s=85,
    description="Live 7-day window of close approaches PLUS the full paginated NEO catalogue (up to 4000 asteroids per fetch).",
    requires_key=True,
    key_env="NASA_API_KEY",
    enabled=bool(NASA_API_KEY),
)


async def fetch(client: httpx.AsyncClient):
    if not NASA_API_KEY:
        return None
    now = datetime.now(timezone.utc)
    start = now.strftime("%Y-%m-%d")
    end = (now + timedelta(days=7)).strftime("%Y-%m-%d")

    # ---- Pull the FULL NEO catalogue via paginated /browse ----
    # This is bounded — ~38k known NEOs as of 2026, ~20 per page = ~1900 pages.
    # We cap at 200 pages = 4000 NEOs per fetch to bound runtime.
    catalogue = []
    try:
        for page in range(0, 200):
            cr = await client.get(
                "https://api.nasa.gov/neo/rest/v1/neo/browse",
                params={"page": page, "size": 20, "api_key": NASA_API_KEY},
                timeout=30,
            )
            if cr.status_code != 200:
                break
            cd = cr.json()
            objs = cd.get("near_earth_objects") or []
            if not objs:
                break
            for obj in objs:
                cad_list = obj.get("close_approach_data") or []
                catalogue.append({
                    "id": obj.get("id"),
                    "name": obj.get("name"),
                    "designation": obj.get("designation"),
                    "absolute_magnitude_h": obj.get("absolute_magnitude_h"),
                    "diameter_m_min": ((obj.get("estimated_diameter") or {}).get("meters") or {}).get("estimated_diameter_min"),
                    "diameter_m_max": ((obj.get("estimated_diameter") or {}).get("meters") or {}).get("estimated_diameter_max"),
                    "is_potentially_hazardous": obj.get("is_potentially_hazardous_asteroid"),
                    "is_sentry_object": obj.get("is_sentry_object"),
                    "approach_count": len(cad_list),
                    "first_observation": (cad_list[0].get("close_approach_date") if cad_list else None),
                    "last_observation": (cad_list[-1].get("close_approach_date") if cad_list else None),
                    "url": obj.get("nasa_jpl_url"),
                })
            page_info = cd.get("page") or {}
            if page >= (page_info.get("total_pages") or 0) - 1:
                break
    except Exception as e:
        print(f"[nasa_neows] browse exception: {e}")

    try:
        r = await client.get(
            "https://api.nasa.gov/neo/rest/v1/feed",
            params={"start_date": start, "end_date": end, "api_key": NASA_API_KEY},
            timeout=45,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        near = d.get("near_earth_objects") or {}
        asteroids: list[dict[str, Any]] = []
        for date_key, rows in near.items():
            for row in rows:
                diameter = (row.get("estimated_diameter") or {}).get("meters") or {}
                d_min = diameter.get("estimated_diameter_min", 0)
                d_max = diameter.get("estimated_diameter_max", 0)
                cad = (row.get("close_approach_data") or [{}])[0]
                rel_vel = float((cad.get("relative_velocity") or {}).get("kilometers_per_second", 0) or 0)
                miss = cad.get("miss_distance") or {}
                miss_lunar = float(miss.get("lunar", 0) or 0)
                hazardous = row.get("is_potentially_hazardous_asteroid", False)
                sev = 1
                if hazardous: sev = 4
                if miss_lunar < 1: sev = 5
                asteroids.append({
                    "id": row.get("id"),
                    "name": row.get("name", ""),
                    "diameter_min_m": d_min,
                    "diameter_max_m": d_max,
                    "diameter_avg_m": (d_min + d_max) / 2 if d_min and d_max else 0,
                    "approach_time": cad.get("close_approach_date_full", ""),
                    "velocity_kms": rel_vel,
                    "miss_distance_lunar": miss_lunar,
                    "miss_distance_km": float((miss.get("kilometers") or 0) or 0),
                    "orbiting_body": cad.get("orbiting_body", "Earth"),
                    "hazardous": hazardous,
                    "severity": sev,
                    "url": row.get("nasa_jpl_url", ""),
                })
        asteroids.sort(key=lambda a: (a["severity"], -a["miss_distance_lunar"]), reverse=True)
        return {
            "source": "NASA NeoWs",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(asteroids),
            "hazardous_count": sum(1 for a in asteroids if a["hazardous"]),
            "asteroids": asteroids,
            "catalogue": catalogue,
            "catalogue_count": len(catalogue),
        }
    except Exception as e:
        print(f"[nasa_neows] error: {e}")
        return None


register(LAYER, fetch)
