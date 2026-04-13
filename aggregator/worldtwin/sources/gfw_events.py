"""Global Fishing Watch — dark vessel / AIS-gap events.

Sanctions evasion / illegal fishing / dark fleet detection. AIS gaps are
periods where a vessel's transponder goes dark for 12+ hours in suspicious
conditions (inside EEZs, transiting known dark-fleet areas, etc.).

Also fetches fishing encounters and port visits for context.

Requires GFW_TOKEN (free 10-year JWT).
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

GFW_TOKEN = os.environ.get("GFW_TOKEN", "")

LAYER = LayerMeta(
    id="gfw_events",
    name="Global Fishing Watch — AIS Gap Events",
    category="transit",
    kind="points",
    source="Global Fishing Watch v3",
    source_url="https://gateway.api.globalfishingwatch.org/v3/",
    license="CC BY-SA 4.0",
    refresh_s=10800,
    initial_delay_s=165,
    description="Dark fleet (AIS gap) events + fishing encounters + port visits from GFW satellite AIS.",
    requires_key=True,
    key_env="GFW_TOKEN",
    enabled=bool(GFW_TOKEN),
)


async def _fetch_events(client: httpx.AsyncClient, dataset: str, headers: dict, limit: int = 100):
    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        r = await client.get(
            "https://gateway.api.globalfishingwatch.org/v3/events",
            params={
                "datasets[0]": dataset,
                "start-date": start,
                "end-date": end,
                "limit": limit,
                "offset": 0,
            },
            headers=headers,
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[gfw_events] {dataset} {r.status_code}: {r.text[:120]}")
            return []
        data = r.json()
        return data.get("entries") or data.get("entries", []) or []
    except Exception as e:
        print(f"[gfw_events] {dataset} error: {e}")
        return []


async def fetch(client: httpx.AsyncClient):
    if not GFW_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {GFW_TOKEN}", "User-Agent": "WorldTwin/1.0"}

    # Fetch 3 event types in parallel
    gaps, encounters, ports = await asyncio.gather(
        _fetch_events(client, "public-global-gaps-events:latest", headers, limit=100),
        _fetch_events(client, "public-global-encounters-events:latest", headers, limit=50),
        _fetch_events(client, "public-global-port-visits-events:latest", headers, limit=50),
    )

    def _safe_dict(v):
        """Return v if it's a dict, else {}."""
        return v if isinstance(v, dict) else {}

    def _as_time(v):
        """v may be a dict with .time, a string, or None."""
        if isinstance(v, dict):
            return v.get("time") or v.get("timestamp") or ""
        if isinstance(v, str):
            return v
        return ""

    def _norm(ev, type_name, severity):
        # GFW v3 events schema varies: position may be top-level OR nested
        # under start.position. start/end may be strings OR dicts.
        pos = _safe_dict(ev.get("position"))
        start_dict = _safe_dict(ev.get("start"))
        start_pos = _safe_dict(start_dict.get("position"))
        lat = pos.get("lat") or start_pos.get("lat")
        lon = pos.get("lon") or start_pos.get("lon")
        if lat is None or lon is None:
            return None
        vessel = _safe_dict(ev.get("vessel"))
        return {
            "id": ev.get("id"),
            "type": type_name,
            "severity": severity,
            "lat": lat,
            "lon": lon,
            "start": _as_time(ev.get("start")),
            "end": _as_time(ev.get("end")),
            "duration_hours": ev.get("duration_hours") or ev.get("durationHours") or 0,
            "vessel_id": vessel.get("id") or vessel.get("name"),
            "vessel_name": vessel.get("name", ""),
            "vessel_flag": vessel.get("flag", ""),
            "vessel_type": vessel.get("type") or vessel.get("ssvid", ""),
        }

    all_events: list[dict[str, Any]] = []
    for ev in gaps:
        norm = _norm(ev, "gap", 4)
        if norm: all_events.append(norm)
    for ev in encounters:
        norm = _norm(ev, "encounter", 3)
        if norm: all_events.append(norm)
    for ev in ports:
        norm = _norm(ev, "port_visit", 1)
        if norm: all_events.append(norm)

    by_type = {"gap": len(gaps), "encounter": len(encounters), "port_visit": len(ports)}

    return {
        "source": "Global Fishing Watch v3",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(all_events),
        "by_type": by_type,
        "events": all_events,
    }


register(LAYER, fetch)
