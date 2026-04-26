"""File-backed atomic cache + in-memory status tracking.

The cache directory is shared with Caddy so static files can be served directly
without going through FastAPI. All writes are atomic (tmp file + rename).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# In-memory status — not persisted, rebuilt on restart
_status: dict[str, dict[str, Any]] = {}


@dataclass
class LayerStatus:
    ok: bool
    count: int | None
    error: str | None
    last_fetch: str
    elapsed_s: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


V1_DIR = CACHE_DIR / "v1"
V1_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def write_envelope(layer_id: str, envelope_dict: dict[str, Any]) -> None:
    """Write the v1 envelope to /cache/v1/<layer>.json.
    Also writes the data-only slice to /cache/v1/<layer>.data.json.
    """
    _atomic_write(V1_DIR / f"{layer_id}.json", envelope_dict)
    _atomic_write(V1_DIR / f"{layer_id}.data.json", envelope_dict.get("data"))


def write_legacy(layer_id: str, legacy_data: Any) -> None:
    """Write the legacy flat file at /cache/<layer>.json — the path the
    current CesiumJS frontend expects (Caddy serves /api/cache/<layer>.json
    from this directory directly, bypassing the backend entirely).

    Vision: A lab where anyone can read the world from raw, dated,
    cross-checked sources. We pass every payload through sanity.sweep_and_tag
    so impossible values (BTC -113%, ship_count 999999, magnitude 12) get
    nulled with a `_sanity_warnings` field attached. The Inspector surfaces
    those warnings to the user.
    """
    try:
        from . import sanity
        legacy_data = sanity.sweep_and_tag(legacy_data)
    except Exception as e:
        print(f"[cache] sanity sweep failed for {layer_id}: {e}")
    _atomic_write(CACHE_DIR / f"{layer_id}.json", legacy_data)


def read_envelope(layer_id: str) -> dict[str, Any] | None:
    """Read a v1 envelope back from disk."""
    path = V1_DIR / f"{layer_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def envelope_path(layer_id: str) -> Path:
    return V1_DIR / f"{layer_id}.json"


def data_path(layer_id: str) -> Path:
    return V1_DIR / f"{layer_id}.data.json"


def legacy_path(layer_id: str) -> Path:
    return CACHE_DIR / f"{layer_id}.json"


def mark_ok(layer_id: str, count: int | None, elapsed_s: float = 0.0) -> None:
    _status[layer_id] = {
        "ok": True,
        "count": count,
        "error": None,
        "last_fetch": _now_iso(),
        "elapsed_s": round(elapsed_s, 3),
    }


def mark_error(layer_id: str, error: str, elapsed_s: float = 0.0) -> None:
    prev = _status.get(layer_id) or {}
    _status[layer_id] = {
        "ok": False,
        "count": prev.get("count"),  # retain last-known count
        "error": error[:500],
        "last_fetch": _now_iso(),
        "elapsed_s": round(elapsed_s, 3),
    }


def all_status() -> dict[str, dict[str, Any]]:
    return dict(_status)


def get_status(layer_id: str) -> dict[str, Any] | None:
    return _status.get(layer_id)
