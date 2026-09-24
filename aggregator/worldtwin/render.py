"""Render slices — honest, bounded summaries of oversized point layers.

A phone must never be handed fires.json whole (4.3 MB raw / ~0.4 MB gz for
~24k detections). For kind='points' layers whose FULL envelope gzips over
LEAN_GZ_BUDGET, this writes `<id>.render.json`: density bins on an adaptive
grid (0.1° → 0.25° → 0.5°, coarsening until the slice itself fits the
budget), each bin weighted by detections per unit area (cos-lat corrected,
so a 0.25° cell in Siberia and one at the equator compare honestly).

The slice never pretends to be the data: `n` is the true total, `shown` the
cell count, and `selection` states the method in one sentence — the manifest
carries the same fields in its representations[] entry (lossy: true).

Layers whose full file already fits the budget get NO slice — the client
uses the full file — and any stale slice from a fatter past is unlinked so
Caddy cannot serve it.

Called from cache.write_envelope's commit path (inside the scheduler's
CPU_SEM tail), wrapped in try/except there: a render failure must never
block the envelope.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from typing import Any

from . import cache

LEAN_GZ_BUDGET = 120_000          # bytes, gzipped — one comfortable 3G fetch
_CELL_LADDER = (0.1, 0.25, 0.5)   # degrees, coarsening until it fits


def _is_point(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    lat, lon = p.get("lat"), p.get("lon")
    return (isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            and math.isfinite(lat) and math.isfinite(lon))


def _extract_points(data: Any) -> list[dict[str, Any]]:
    """Mirror app/src/lib/api.ts extractPoints: a flat list of {lat, lon}
    dicts, or the first list value inside the data dict that contains
    point-shaped entries (gdacs_events wraps its list in data.events)."""
    if isinstance(data, list):
        return [p for p in data if _is_point(p)]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                pts = [p for p in value if _is_point(p)]
                if pts:
                    return pts
    return []


def _bin_points(points: list[dict[str, Any]], cell_deg: float) -> list[list[float]]:
    """Aggregate points onto a cell_deg grid. Returns [[lat, lon, weight], ...]
    sorted by weight descending (progressive render friendly).

    weight = count / cos(lat_center): detections per unit area. A cell's
    ground area shrinks with cos(lat), so raw counts would systematically
    understate high-latitude density. cos clamped at 0.05 so polar cells
    can't blow up to infinity."""
    max_row = math.ceil(90.0 / cell_deg) - 1  # keep centers inside ±90
    bins: dict[tuple[int, int], int] = {}
    for p in points:
        lat = float(p["lat"])
        lon = float(p["lon"])
        if not -90.0 <= lat <= 90.0:
            continue
        lon = ((lon + 180.0) % 360.0) - 180.0
        iy = min(max(math.floor(lat / cell_deg), -max_row - 1), max_row)
        ix = math.floor(lon / cell_deg)
        key = (iy, ix)
        bins[key] = bins.get(key, 0) + 1
    out: list[list[float]] = []
    for (iy, ix), n in bins.items():
        clat = (iy + 0.5) * cell_deg
        clon = (ix + 0.5) * cell_deg
        weight = n / max(math.cos(math.radians(clat)), 0.05)
        out.append([round(clat, 3), round(clon, 3), round(weight, 2)])
    out.sort(key=lambda b: -b[2])
    return out


def _drop_slice(v1_dir: Path, layer_id: str) -> None:
    (v1_dir / f"{layer_id}.render.json").unlink(missing_ok=True)
    (v1_dir / f"{layer_id}.render.json.gz").unlink(missing_ok=True)


def write_render_slice(meta: Any, env_dict: dict[str, Any],
                       v1_dir: Path) -> dict[str, Any] | None:
    """Write `<id>.render.json` when warranted; return the representations[]
    entry for the manifest, or None when the full file is small enough (or
    the layer isn't points-shaped)."""
    v1_dir = Path(v1_dir)
    if getattr(meta, "kind", None) != "points":
        return None
    # Size test against the envelope's own gz sidecar, which write_envelope
    # just committed. No sidecar means the file is under 4 KB — trivially small.
    try:
        raw_gz = (v1_dir / f"{meta.id}.json.gz").stat().st_size
    except OSError:
        raw_gz = 0
    if raw_gz <= LEAN_GZ_BUDGET:
        _drop_slice(v1_dir, meta.id)
        return None

    points = _extract_points(env_dict.get("data"))
    if not points:
        _drop_slice(v1_dir, meta.id)
        return None

    n = len(points)
    payload: dict[str, Any] | None = None
    for cell_deg in _CELL_LADDER:
        bins = _bin_points(points, cell_deg)
        payload = {
            "mode": "bins",
            "cell_deg": cell_deg,
            "n": n,
            "shown": len(bins),
            "selection": (f"{cell_deg} degree density bins, area-weighted "
                          f"(count / cos lat); {len(bins):,} cells of "
                          f"{n:,} points"),
            "bins": bins,
        }
        blob = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(gzip.compress(blob, 6)) <= LEAN_GZ_BUDGET:
            break
        # else: coarsen; if even 0.5° overshoots, ship 0.5° — still ~10×
        # smaller than the full file, and the manifest carries true sizes.
    assert payload is not None  # ladder is non-empty

    render_path = v1_dir / f"{meta.id}.render.json"
    cache._atomic_write(render_path, payload)

    rep: dict[str, Any] = {
        "rel": "render",
        "url": render_path.name,     # relative to the manifest
        "bytes": None,
        "bytes_gz": None,
        "mode": "bins",
        "cell_deg": payload["cell_deg"],
        "shown": payload["shown"],
        "lossy": True,
        "selection": payload["selection"],
    }
    try:
        rep["bytes"] = render_path.stat().st_size
    except OSError:
        pass
    try:
        rep["bytes_gz"] = (v1_dir / f"{meta.id}.render.json.gz").stat().st_size
    except OSError:
        pass
    return rep
