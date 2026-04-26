"""USGS earthquakes — live past 24h M2.5+ feed PLUS historical M5+ archive."""
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="quakes",
    name="Earthquakes — live + historical M5+ archive",
    category="nature",
    kind="points",
    source="USGS Earthquake Hazards Program",
    source_url="https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson",
    license="Public domain (US Government)",
    refresh_s=300,    # live feed — every 5 min
    initial_delay_s=4,
    units="magnitude (Richter)",
    description="Live past-24h M2.5+ feed + (on first run, then weekly) historical M5+ archive back to 1990 via the FDSNWS query API.",
)

# Marker file to track when we last did the heavy historical backfill
_HIST_MARKER = Path(os.environ.get("CACHE_DIR", "/cache")) / ".usgs_historical_done"


async def _fetch_historical_window(client, start_iso, end_iso):
    """Pull all M5+ events in a window. USGS caps responses at 20,000 features."""
    try:
        r = await client.get(
            "https://earthquake.usgs.gov/fdsnws/event/1/query",
            params={
                "format": "geojson",
                "starttime": start_iso,
                "endtime": end_iso,
                "minmagnitude": 5.0,
                "orderby": "time",
                "limit": 20000,
            },
            timeout=120,
        )
        if r.status_code != 200:
            return []
        return r.json().get("features") or []
    except Exception as e:
        print(f"[usgs_quakes] historical {start_iso}..{end_iso} failed: {e}")
        return []


async def fetch(client: httpx.AsyncClient):
    # 1. Live past-day feed
    r = await client.get(LAYER.source_url, timeout=30)
    r.raise_for_status()
    geo = r.json()
    points = []
    for f in geo.get("features", []):
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        props = f.get("properties") or {}
        mag = props.get("mag")
        if mag is None:
            continue
        points.append(point(
            lat=coords[1], lon=coords[0], id=f.get("id"),
            value=mag, label=f"M{mag:.1f}",
            place=props.get("place", ""),
            depth_km=coords[2] if len(coords) > 2 else None,
            time_ms=props.get("time"),
            usgs_url=props.get("url", ""),
        ))
    geo["fetched"] = datetime.now(timezone.utc).isoformat()

    # 2. Historical M5+ archive — only if we haven't done it yet, or it's been
    #    over 7 days. Each window is at most 1 year; we go back to 1990.
    needs_backfill = not _HIST_MARKER.exists()
    if not needs_backfill:
        try:
            age_days = (datetime.now() - datetime.fromtimestamp(_HIST_MARKER.stat().st_mtime)).days
            needs_backfill = age_days >= 7
        except Exception:
            needs_backfill = True

    historical_features = []
    if needs_backfill:
        print("[usgs_quakes] starting historical M5+ backfill 1990 → present (this takes a few minutes)")
        end = datetime.now(timezone.utc)
        cur = datetime(1990, 1, 1, tzinfo=timezone.utc)
        while cur < end:
            nxt = min(cur + timedelta(days=365), end)
            feats = await _fetch_historical_window(
                client, cur.strftime("%Y-%m-%dT%H:%M:%S"),
                       nxt.strftime("%Y-%m-%dT%H:%M:%S"))
            historical_features.extend(feats)
            cur = nxt
        try:
            _HIST_MARKER.write_text(datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
        print(f"[usgs_quakes] historical backfill complete — {len(historical_features)} M5+ events")
        # Mix the historical features into the geojson so the History Store
        # decomposer picks them up. Keep features array small for the live UI;
        # historical_features is a separate field the decomposer reads.
        geo["historical_features"] = historical_features
        geo["historical_count"] = len(historical_features)

    return points, geo


register(LAYER, fetch)
