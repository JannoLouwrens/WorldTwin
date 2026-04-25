"""AISStream.io — live ship positions via WebSocket.

Unlike other sources which do request-response HTTP, this source maintains
a persistent WebSocket connection in a background task, collecting ship
position reports and writing a snapshot to the cache every 30 seconds.
"""
import asyncio
import json
import os
import time
from typing import Any

import httpx  # only used for type; we actually use websockets below

from ..models import LayerMeta, point
from ..registry import register

# AISStream public API — free key (register at https://aisstream.io).
# NEVER commit the key inline. Set AISSTREAM_KEY in .env.
AISSTREAM_KEY = os.environ.get("AISSTREAM_KEY", "")

LAYER = LayerMeta(
    id="ships",
    name="Live Vessels (AIS)",
    category="transit",
    kind="points",
    source="AISStream.io",
    source_url="https://aisstream.io/documentation",
    license="Free non-commercial",
    refresh_s=30,              # snapshot write interval
    initial_delay_s=5,
    description="Live ship positions worldwide via AISStream WebSocket feed. Max 500 vessels cached.",
    requires_key=True,
    key_env="AISSTREAM_KEY",
)

# In-memory ship state: {mmsi: {lat, lon, name, sog, cog, status, updated}}
_ships: dict[str, dict[str, Any]] = {}
_ws_task: asyncio.Task | None = None
_last_snapshot = 0.0

NAV_STATUS = [
    "Under way using engine", "At anchor", "Not under command",
    "Restricted manoeuvrability", "Constrained by draught", "Moored",
    "Aground", "Engaged in fishing", "Under way sailing",
    "Reserved", "Reserved", "Reserved", "Reserved", "Reserved",
    "AIS-SART", "Not defined",
]


async def _websocket_loop() -> None:
    """Persistent WebSocket loop — connects, subscribes, consumes until error,
    then reconnects with backoff. Never raises.
    """
    try:
        import websockets
    except ImportError:
        print("[ships] websockets library not installed — ship layer disabled")
        return

    backoff = 5
    while True:
        try:
            async with websockets.connect(
                "wss://stream.aisstream.io/v0/stream",
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                max_size=2**20,
            ) as ws:
                # Subscribe to global bounding box (no filter — take all msg types)
                await ws.send(json.dumps({
                    "APIKey": AISSTREAM_KEY,
                    "BoundingBoxes": [[[-90, -180], [90, 180]]],
                }))
                backoff = 5  # reset
                async for raw in ws:
                    try:
                        # Raw may be bytes or str
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        msg = json.loads(raw)
                        _ingest_message(msg)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[ships] websocket error: {e}, reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)


def _ingest_message(msg: dict[str, Any]) -> None:
    """Update _ships from a single AIS message."""
    global _ships
    try:
        inner = msg.get("Message") or {}
        pos = (
            inner.get("PositionReport")
            or inner.get("StandardClassBCSPositionReport")
            or {}
        )
        meta = msg.get("MetaData") or {}
        mmsi = meta.get("MMSI") or pos.get("UserID")
        if not mmsi:
            return

        lat = pos.get("Latitude")
        lon = pos.get("Longitude")
        if lat is None or lon is None:
            # Might be static data (ShipStaticData) — update name only
            static = inner.get("ShipStaticData") or {}
            if static and str(mmsi) in _ships:
                _ships[str(mmsi)]["name"] = static.get("Name", _ships[str(mmsi)].get("name", ""))
                _ships[str(mmsi)]["type"] = static.get("Type")
            return
        if abs(lat) < 0.01 and abs(lon) < 0.01:
            return

        key = str(mmsi)
        _ships[key] = {
            "mmsi": str(mmsi),
            "lat": float(lat),
            "lon": float(lon),
            "name": (meta.get("ShipName") or _ships.get(key, {}).get("name") or "").strip(),
            "sog": pos.get("Sog"),
            "cog": pos.get("Cog"),
            "nav_status": pos.get("NavigationalStatus"),
            "updated": time.time(),
        }
    except Exception:
        pass


def _prune_stale() -> None:
    """Remove ships we haven't seen in 10 minutes, cap total at 500."""
    global _ships
    now = time.time()
    cutoff = now - 600
    _ships = {k: v for k, v in _ships.items() if v.get("updated", 0) > cutoff}
    # Cap at 500 most recent
    if len(_ships) > 500:
        sorted_items = sorted(_ships.items(), key=lambda kv: kv[1].get("updated", 0), reverse=True)
        _ships = dict(sorted_items[:500])


def _snapshot() -> tuple[list, list]:
    """Build a v1 points list + legacy list from current _ships state."""
    _prune_stale()
    points_list = []
    legacy_list = []
    for s in _ships.values():
        lat, lon = s["lat"], s["lon"]
        name = s.get("name") or "Vessel"
        sog = s.get("sog") or 0
        cog = s.get("cog") or 0
        ns = s.get("nav_status")
        status_text = NAV_STATUS[ns] if ns is not None and 0 <= ns < len(NAV_STATUS) else "Unknown"
        points_list.append(point(
            lat=lat, lon=lon,
            id=s["mmsi"],
            label=name,
            value=sog,
            mmsi=s["mmsi"],
            sog=sog,
            cog=cog,
            nav_status=status_text,
            updated=s["updated"],
        ))
        legacy_list.append({
            "mmsi": s["mmsi"],
            "name": name,
            "lat": lat,
            "lon": lon,
            "sog": sog,
            "cog": cog,
            "nav_status": status_text,
            "updated": s["updated"],
        })
    return points_list, legacy_list


async def fetch(client: httpx.AsyncClient):
    """Called by scheduler every refresh_s — spawns the WS loop on first call
    and returns the current snapshot.
    """
    global _ws_task, _last_snapshot
    if _ws_task is None or _ws_task.done():
        _ws_task = asyncio.create_task(_websocket_loop())

    points_list, legacy_list = _snapshot()
    _last_snapshot = time.time()

    if not points_list:
        # First time through — no ships yet, return None to keep stale cache
        return None
    return points_list, legacy_list


register(LAYER, fetch)
