"""UCDP — Uppsala Conflict Data Program (backup conflict source).

Academic-quality conflict event data with lat/lon, split fatality counts
(deaths_a, deaths_b, deaths_civilians), and dyad attribution. Complements
ACLED — UCDP is slower (monthly candidate data) but more rigorously coded.

Requires UCDP_TOKEN env var. Token is free but email-request:
  Email: ucdp@pcr.uu.se (or mertcan.yilmaz@pcr.uu.se)
  Subject: "API token request for non-commercial visualization"
  Turnaround: 1-3 business days

If UCDP_TOKEN is not set, the worker is disabled and returns None.
"""
import os
from datetime import date, timedelta
from typing import Any

import httpx

from ..models import LayerMeta, point
from ..registry import register

UCDP_TOKEN = os.environ.get("UCDP_TOKEN", "")
BASE = "https://ucdpapi.pcr.uu.se/api"

LAYER = LayerMeta(
    id="ucdp",
    name="UCDP Conflict Events",
    category="war",
    kind="points",
    source="Uppsala Conflict Data Program",
    source_url="https://ucdp.uu.se/apidocs/",
    license="UCDP open data (attribution required)",
    refresh_s=86400,  # daily
    initial_delay_s=100,
    units="fatalities",
    description=(
        "Academic-quality conflict events with split fatality counts "
        "(side A / side B / civilians) and dyad attribution. Requires "
        "a free UCDP API token via email request."
    ),
    requires_key=True,
    key_env="UCDP_TOKEN",
    enabled=bool(UCDP_TOKEN),
)


async def _fetch_paginated(client: httpx.AsyncClient, resource: str, version: str, **params) -> tuple[list[dict], bool]:
    headers = {"x-ucdp-access-token": UCDP_TOKEN}
    params.setdefault("pagesize", 1000)
    params.setdefault("page", 0)
    out = []
    truncated = False
    while True:
        r = await client.get(
            f"{BASE}/{resource}/{version}",
            params=params,
            headers=headers,
            timeout=60,
        )
        if r.status_code == 401:
            print(f"[ucdp] 401 — token invalid or expired")
            return [], truncated
        if r.status_code != 200:
            print(f"[ucdp] HTTP {r.status_code}: {r.text[:200]}")
            return out, truncated
        try:
            body = r.json()
        except Exception:
            return out, truncated
        batch = body.get("Result", [])
        out.extend(batch)
        total_pages = body.get("TotalPages", 1)
        if params["page"] >= total_pages - 1:
            break
        params["page"] += 1
        if params["page"] > 19:  # safety
            truncated = True
            print(f"[ucdp] page cap hit at page {params['page']}/{total_pages} — results truncated")
            break
    return out, truncated


async def fetch(client: httpx.AsyncClient):
    if not UCDP_TOKEN:
        return None

    # Try to fetch candidate events (most recent) — we try a few version
    # strings because UCDP increments these. If all fail, return None.
    candidates = [
        ("gedevents", "25.1"),
        ("gedevents", "24.1"),
    ]
    # Rolling window: recent events only, so the result fits under the page cap
    # (the API returns id-ascending, so a too-wide window keeps the OLDEST events).
    start_date = (date.today() - timedelta(days=180)).isoformat()
    events = []
    truncated = False
    for resource, version in candidates:
        try:
            events, truncated = await _fetch_paginated(client, resource, version, pagesize=1000, StartDate=start_date)
            if events:
                print(f"[ucdp] fetched {len(events)} events from {resource}/{version}")
                break
        except Exception as e:
            continue
    if not events:
        return None

    points_list = []
    for ev in events:
        try:
            lat = float(ev.get("latitude") or 0)
            lon = float(ev.get("longitude") or 0)
        except (TypeError, ValueError):
            continue
        if lat == 0.0 and lon == 0.0:
            continue
        deaths_a = int(ev.get("deaths_a") or 0)
        deaths_b = int(ev.get("deaths_b") or 0)
        deaths_civ = int(ev.get("deaths_civilians") or 0)
        total = int(ev.get("best") or (deaths_a + deaths_b + deaths_civ))
        side_a = ev.get("side_a") or "?"
        side_b = ev.get("side_b") or "?"
        points_list.append(point(
            lat=lat,
            lon=lon,
            id=str(ev.get("id") or ""),
            value=total,
            label=f"{side_a} vs {side_b}",
            popup=f"{side_a} vs {side_b} — {total} fatalities",
            side_a=side_a,
            side_b=side_b,
            dyad_name=ev.get("dyad_name"),
            conflict_name=ev.get("conflict_name"),
            deaths_a=deaths_a,
            deaths_b=deaths_b,
            deaths_civ=deaths_civ,
            total_deaths=total,
            country=ev.get("country"),
            adm_1=ev.get("adm_1"),
            date_start=ev.get("date_start"),
            date_end=ev.get("date_end"),
            type_of_violence=ev.get("type_of_violence"),
            source_article=(ev.get("source_article") or "")[:200],
        ))

    legacy = {
        "source": "UCDP GED",
        "event_count": len(points_list),
        "truncated": truncated,
        "events": points_list,
    }
    return points_list, legacy


register(LAYER, fetch)
