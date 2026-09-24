"""File-backed atomic cache + durable status + the delivery contract.

The cache directory is shared with Caddy so static files can be served directly
without going through FastAPI. All writes are atomic (unique tmp file +
os.replace).

This module also owns the three contract artifacts (MASTER_PLAN §5):
  /cache/v1/manifest.json  — the delivery contract: every registry layer
                             (enabled AND retired) with a COMPUTED state.
  /cache/v1/counts.json    — per-layer daily count ledger (no-entry-never-zero).
  /history/_status.json    — durable fetch status incl. last_success_at.
                             /history is a private mount, NOT publicly served;
                             status may contain (scrubbed) error text and must
                             never land under /cache.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import __version__

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

V1_DIR = CACHE_DIR / "v1"
V1_DIR.mkdir(parents=True, exist_ok=True)

# Same default resolution as history.py: /cache/../history == /history in the
# container. NOT served by Caddy — that is the point.
HISTORY_DIR = Path(os.environ.get("HISTORY_DIR", str(CACHE_DIR / ".." / "history")))
STATUS_PATH = HISTORY_DIR / "_status.json"

MANIFEST_PATH = V1_DIR / "manifest.json"
COUNTS_PATH = V1_DIR / "counts.json"

# In-memory status — durable via /history/_status.json (load_status at boot,
# throttled persist on every mark, flush_status() at shutdown).
_status: dict[str, dict[str, Any]] = {}
_status_lock = threading.Lock()
_STATUS_FLUSH_INTERVAL_S = 5.0
_last_status_flush = 0.0  # time.monotonic() of the last persist


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    """Tolerant ISO-8601 parse → aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _newer_iso(a, b):
    """Return whichever ISO timestamp is newer; tolerate None/unparseable."""
    da, db = _parse_iso(a), _parse_iso(b)
    if da is not None and db is not None:
        return a if da >= db else b
    return a or b


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------

def _atomic_write(path: Path, payload: Any, sidecar: bool = True) -> None:
    """JSON-serialize `payload` to `path` atomically.

    Unique tmp names via mkstemp: two threads writing the same target (e.g.
    manifest.json from two envelope commits) can never truncate each other's
    half-written tmp — each os.replace is atomic and last-writer-wins.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        # mkstemp creates 0600; these files are served by Caddy and read by
        # host-side (opc) consumers like build_brief and nightly_audit.
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if not sidecar:
        return
    # Precompressed sidecar for Caddy's `file_server precompressed gzip` —
    # an 18 MB world_bank.json ships as ~2 MB with zero per-request CPU.
    # Written atomically alongside the json so the sidecar can never be
    # stale relative to its source.
    gz_tmp: Path | None = None
    try:
        if path.stat().st_size > 4096:
            gz_fd, gz_name = tempfile.mkstemp(
                dir=path.parent, prefix=path.name, suffix=".gz.tmp")
            gz_tmp = Path(gz_name)
            os.fchmod(gz_fd, 0o644)
            with os.fdopen(gz_fd, "wb") as raw, path.open("rb") as src:
                with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        dst.write(chunk)
            os.replace(gz_tmp, path.with_suffix(path.suffix + ".gz"))
        else:
            # Small file — drop any leftover sidecar so it can't go stale.
            path.with_suffix(path.suffix + ".gz").unlink(missing_ok=True)
    except Exception as e:
        if gz_tmp is not None:
            gz_tmp.unlink(missing_ok=True)
        print(f"[cache] gzip sidecar failed for {path.name}: {e}")


# ---------------------------------------------------------------------------
# Secret scrubbing — error text is stored, persisted, and served (manifest
# state_detail, /api/health). httpx exception strings embed the full request
# URL, including api_key= query params and FIRMS-style path keys
# (/api/area/csv/<32-char MAP_KEY>/...). Nothing key-shaped may survive.
# ---------------------------------------------------------------------------

_QUERY_RE = re.compile(r"\?[^\s'\"]*")          # whole query string
_TOKEN_RE = re.compile(r"[A-Za-z0-9]{24,}")     # key-shaped path segment / token


def _scrub(text: str | None) -> str | None:
    if not text:
        return text
    text = _QUERY_RE.sub("?…", text)
    text = _TOKEN_RE.sub("…", text)
    return text


# ---------------------------------------------------------------------------
# Envelope / legacy writes
# ---------------------------------------------------------------------------

def write_envelope(layer_id: str, envelope_dict: dict[str, Any],
                   meta: Any = None) -> None:
    """Write the v1 envelope to /cache/v1/<layer>.json and, when `meta` is
    given (the scheduler's commit path), update the render slice + manifest.

    The former `.data.json` duplicate write was DELETED 2026-09-24: 92
    near-byte-identical files (361 MB) that no checked-in client read. This
    also retired server.py's undocumented /api/{layer_id} data_path fallback.
    """
    path = V1_DIR / f"{layer_id}.json"
    _atomic_write(path, envelope_dict)
    if meta is None:
        return
    reps = [_full_representation(layer_id, envelope_dict)]
    # Render slice: best-effort — a render failure must never block the
    # envelope (it already committed above).
    try:
        from . import render
        rep = render.write_render_slice(meta, envelope_dict, V1_DIR)
        if rep:
            reps.append(rep)
    except Exception as e:
        print(f"[cache] render slice failed for {layer_id}: {e}")
    try:
        update_manifest_entry(meta, envelope_dict, reps)
        write_manifest()
    except Exception as e:
        print(f"[cache] manifest update failed for {layer_id}: {e}")


def write_legacy(layer_id: str, legacy_data: Any) -> None:
    """Write the legacy flat file at /cache/<layer>.json — the path the
    current CesiumJS frontend expects (Caddy serves /api/cache/<layer>.json
    from this directory directly, bypassing the backend entirely).

    NOTE 2026-09-24: the sanity sweep moved OUT of this function into the
    scheduler, which now runs sanity.sweep_and_tag ONCE and feeds the swept
    payload to BOTH writers (the v1 envelope previously shipped un-swept
    values to the new client). Callers must pass already-swept data.

    Convention: keys starting with `_history_only_` are sent to
    history.snapshot() for decomposition into observations but STRIPPED from
    the disk cache so the legacy .json file stays small. Used by ucdp_ged
    (events_full ~350k rows = 139 MB) and similar bulk plugins.
    """
    # Build a smaller payload for the on-disk cache (strip _history_only_ keys).
    # The full payload still goes to history.snapshot below.
    if isinstance(legacy_data, dict):
        cache_payload = {k: v for k, v in legacy_data.items()
                         if not k.startswith("_history_only_")}
    else:
        cache_payload = legacy_data
    _atomic_write(CACHE_DIR / f"{layer_id}.json", cache_payload)

    # History store — best-effort persistence; never block the live cache
    # write on a history failure. (Recording is default-off since 2026-08-09;
    # history.snapshot returns immediately for policy "none".)
    try:
        from . import history
        history.snapshot(layer_id, legacy_data)
    except Exception as e:
        print(f"[cache] history snapshot failed for {layer_id}: {e}")


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


def legacy_path(layer_id: str) -> Path:
    return CACHE_DIR / f"{layer_id}.json"


# ---------------------------------------------------------------------------
# Status marks — durable, honest
# ---------------------------------------------------------------------------

def mark_ok(layer_id: str, count: int | None, elapsed_s: float = 0.0) -> None:
    now = _now_iso()
    with _status_lock:
        _status[layer_id] = {
            "ok": True,
            "count": count,
            "error": None,
            "last_fetch": now,
            "last_success_at": now,
            "elapsed_s": round(elapsed_s, 3),
        }
    _flush_status_maybe()


def _mark_failure(layer_id: str, error: str, elapsed_s: float) -> None:
    with _status_lock:
        prev = _status.get(layer_id) or {}
        _status[layer_id] = {
            "ok": False,
            "count": prev.get("count"),                      # last-known count
            "error": (_scrub(error) or "")[:500],
            "last_fetch": _now_iso(),
            "last_success_at": prev.get("last_success_at"),  # PRESERVED
            "elapsed_s": round(elapsed_s, 3),
        }
    _flush_status_maybe()


def mark_error(layer_id: str, error: str, elapsed_s: float = 0.0) -> None:
    """The fetch raised. Preserves last-known count and last_success_at —
    a failed attempt must never erase the record of when data last arrived."""
    _mark_failure(layer_id, error, elapsed_s)


def mark_attempt_failed(layer_id: str, reason: str, elapsed_s: float = 0.0) -> None:
    """The fetch completed but produced nothing usable (returned None / empty)
    — the previous cache is KEPT and keeps serving. Same bookkeeping as
    mark_error; the distinct name records the distinct semantics."""
    _mark_failure(layer_id, reason, elapsed_s)


def all_status() -> dict[str, dict[str, Any]]:
    return dict(_status)


def get_status(layer_id: str) -> dict[str, Any] | None:
    return _status.get(layer_id)


# --- Status persistence ----------------------------------------------------

def _write_status_file() -> None:
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        with _status_lock:
            snap = {k: dict(v) for k, v in _status.items()}
        _atomic_write(STATUS_PATH, snap, sidecar=False)
    except Exception as e:
        print(f"[cache] status persist failed: {e}")


def _flush_status_maybe() -> None:
    """Persist _status at most once per 5 s. flush_status() covers the tail."""
    global _last_status_flush
    now = time.monotonic()
    if now - _last_status_flush < _STATUS_FLUSH_INTERVAL_S:
        return
    _last_status_flush = now
    _write_status_file()


def flush_status() -> None:
    """Unconditional persist — the server calls this at shutdown so the last
    throttled marks survive the restart."""
    _write_status_file()


def load_status() -> None:
    """Seed _status from /history/_status.json. Called once in server
    lifespan, BEFORE scheduler.start_all, so last_success_at survives
    restarts and the computed health never resets to amnesia."""
    try:
        if not STATUS_PATH.exists():
            return
        data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        n = 0
        with _status_lock:
            for k, v in data.items():
                if isinstance(v, dict):
                    _status[k] = v
                    n += 1
        print(f"[cache] status seeded from disk: {n} layers")
    except Exception as e:
        print(f"[cache] status load failed: {e}")


# ---------------------------------------------------------------------------
# Computed state — the single truth used by manifest.json, /api/health and
# /v1/health. NEVER asserted, never taken from _status.last_fetch.
#
# Thresholds (REVIVAL_V1 §6.7):
#   grace = max(3 × refresh_s, 1800 s)     — fetch-age allowance
#   age   = now − last_success_at          (durable; falls back to the
#                                           envelope's own fetched_at)
#     ok     age ≤ grace
#     stale  grace < age ≤ 3 × grace
#     dead   age > 3 × grace, or no success on record at all
#   Data age is ORTHOGONAL (a layer can fetch on schedule while serving
#   March-2018 data). When BOTH meta.max_staleness_s and the envelope's
#   data_period are present, data_age = now − max(data_period):
#     data_age > max_staleness_s      → at least stale
#     data_age > 3 × max_staleness_s  → dead
#   The WORSE of fetch-age and data-age wins.
#   retired (meta.enabled == False) is first-class, excluded from the error
#   budget, and never appears in the health endpoints.
# ---------------------------------------------------------------------------

_STATE_RANK = {"ok": 0, "stale": 1, "dead": 2}


def compute_state(meta: Any, last_success_at: str | None,
                  data_period: list | None = None,
                  now: datetime | None = None) -> tuple[str, str | None]:
    """Return (state, state_detail). See threshold comment above."""
    if not getattr(meta, "enabled", True):
        return "retired", getattr(meta, "retired_reason", None) or "retired"
    if now is None:
        now = datetime.now(timezone.utc)
    grace = max(3 * (getattr(meta, "refresh_s", 600) or 600), 1800)
    ls = _parse_iso(last_success_at)
    if ls is None:
        return "dead", "no successful fetch on record"
    age = (now - ls).total_seconds()
    if age <= grace:
        state, detail = "ok", None
    elif age <= 3 * grace:
        state = "stale"
        detail = f"last success {int(age)}s ago (grace {grace}s)"
    else:
        state = "dead"
        detail = f"last success {int(age)}s ago (>3× grace of {grace}s)"
    max_staleness = getattr(meta, "max_staleness_s", None)
    if max_staleness and data_period:
        parsed = [p for p in (_parse_iso(x) for x in data_period) if p is not None]
        if parsed:
            data_age = (now - max(parsed)).total_seconds()
            if data_age > 3 * max_staleness:
                data_state = "dead"
            elif data_age > max_staleness:
                data_state = "stale"
            else:
                data_state = "ok"
            if _STATE_RANK[data_state] > _STATE_RANK[state]:
                state = data_state
                detail = (f"data age {int(data_age)}s exceeds "
                          f"max_staleness_s={max_staleness}")
    return state, detail


# ---------------------------------------------------------------------------
# Manifest — /cache/v1/manifest.json (MASTER_PLAN §5 shape)
# ---------------------------------------------------------------------------

_manifest_lock = threading.Lock()
_manifest_entries: dict[str, dict[str, Any]] = {}   # id → facts (no computed state)
_manifest_metas: dict[str, Any] = {}                # id → LayerMeta


def _full_representation(layer_id: str, env_like: dict[str, Any]) -> dict[str, Any]:
    p = V1_DIR / f"{layer_id}.json"
    rep: dict[str, Any] = {
        "rel": "full",
        "url": p.name,                       # relative to the manifest
        "bytes": None,
        "bytes_gz": None,
        "count": env_like.get("count"),
        "lossy": False,
    }
    try:
        rep["bytes"] = p.stat().st_size
    except OSError:
        pass
    try:
        rep["bytes_gz"] = p.with_suffix(".json.gz").stat().st_size
    except OSError:
        pass  # files ≤ 4 KB have no sidecar
    return rep


def update_manifest_entry(meta: Any, env_dict: dict[str, Any],
                          representations: list[dict[str, Any]]) -> None:
    """Record the facts of a fresh envelope commit. State is computed at
    flush time, never stored."""
    with _manifest_lock:
        _manifest_metas[meta.id] = meta
        _manifest_entries[meta.id] = {
            "fetched_at": env_dict.get("fetched_at"),
            "expires_at": env_dict.get("expires_at"),
            "count": env_dict.get("count"),
            "data_period": env_dict.get("data_period"),
            "license_url": env_dict.get("license_url"),
            "representations": representations,
        }


def manifest_facts(layer_id: str) -> dict[str, Any]:
    """Facts the health endpoints need: the envelope's own fetched_at (the
    durable fallback for last_success_at), data_period, and count."""
    with _manifest_lock:
        e = _manifest_entries.get(layer_id) or {}
        return {"fetched_at": e.get("fetched_at"),
                "data_period": e.get("data_period"),
                "count": e.get("count")}


def seed_manifest(metas: list[Any]) -> None:
    """Boot-time seed — ONE disk scan, boot only. Builds an entry for EVERY
    registry meta (enabled AND disabled) from the on-disk envelope head so
    the first flush already lists all layers: live ones with fetched_at/
    count/bytes, retired ones as first-class 'retired' rows (tombstones or
    missing files alike — state comes from meta.enabled, reason from
    meta.retired_reason). Called from server lifespan before the scheduler."""
    _ensure_counts_loaded()
    with _manifest_lock:
        for meta in metas:
            _manifest_metas[meta.id] = meta
            if meta.id in _manifest_entries:
                continue  # a live commit already produced a fresher entry
            entry: dict[str, Any] = {
                "fetched_at": None, "expires_at": None, "count": None,
                "data_period": None, "license_url": None,
                "representations": [],
            }
            p = V1_DIR / f"{meta.id}.json"
            try:
                with p.open("r", encoding="utf-8") as f:
                    head = f.read(8192)
            except (OSError, ValueError):
                _manifest_entries[meta.id] = entry
                continue
            for field in ("fetched_at", "expires_at", "license_url"):
                m = re.search(rf'"{field}":"([^"]+)"', head)
                if m:
                    entry[field] = m.group(1)
            m = re.search(r'"count":(\d+)', head)
            if m:
                entry["count"] = int(m.group(1))
            m = re.search(r'"data_period":(\[[^\]]*\])', head)
            if m:
                try:
                    entry["data_period"] = json.loads(m.group(1))
                except ValueError:
                    pass
            reps = [_full_representation(meta.id, entry)]
            rp = V1_DIR / f"{meta.id}.render.json"
            if rp.exists():
                try:
                    rj = json.loads(rp.read_text(encoding="utf-8"))
                    rrep: dict[str, Any] = {
                        "rel": "render", "url": rp.name,
                        "bytes": rp.stat().st_size, "bytes_gz": None,
                        "mode": rj.get("mode"), "cell_deg": rj.get("cell_deg"),
                        "shown": rj.get("shown"), "lossy": True,
                        "selection": rj.get("selection"),
                    }
                    try:
                        rrep["bytes_gz"] = rp.with_suffix(".json.gz").stat().st_size
                    except OSError:
                        pass
                    reps.append(rrep)
                except Exception:
                    pass
            entry["representations"] = reps
            _manifest_entries[meta.id] = entry
    try:
        write_manifest()
    except Exception as e:
        print(f"[cache] boot manifest write failed (non-fatal): {e}")


def write_manifest() -> None:
    """Build + atomically write /cache/v1/manifest.json (and its gz sidecar).
    Serialized under _manifest_lock — concurrent envelope commits can never
    interleave a build. `state` is computed here, at write time, from the
    durable last_success_at (fallback: the envelope's own fetched_at)."""
    with _manifest_lock:
        now = datetime.now(timezone.utc)
        counts = {"total": 0, "live": 0, "stale": 0, "dead": 0, "retired": 0}
        layers: list[dict[str, Any]] = []
        for lid in sorted(_manifest_metas):
            meta = _manifest_metas[lid]
            entry = _manifest_entries.get(lid) or {}
            st = _status.get(lid) or {}
            last_success = _newer_iso(st.get("last_success_at"),
                                      entry.get("fetched_at"))
            state, detail = compute_state(meta, last_success,
                                          entry.get("data_period"), now)
            if state not in ("ok", "retired") and not detail:
                detail = st.get("error")
            elif state not in ("ok", "retired") and st.get("error"):
                detail = f"{detail}; last error: {st.get('error')}"
            counts["total"] += 1
            counts["live" if state == "ok" else state] += 1
            layer: dict[str, Any] = {
                "id": lid,
                "name": meta.name,
                "category": meta.category,
                "kind": meta.kind,
                "state": state,
                "state_detail": _scrub(detail),
                "fetched_at": entry.get("fetched_at"),
                "expires_at": entry.get("expires_at"),
                "refresh_s": meta.refresh_s,
                "max_staleness_s": getattr(meta, "max_staleness_s", None),
                "max_bytes": getattr(meta, "max_bytes", None),
                "last_success_at": last_success,
                "count": entry.get("count"),
                "source": {"name": meta.source, "url": meta.source_url},
                "license": {"name": meta.license,
                            "url": entry.get("license_url")},
                "representations": entry.get("representations") or [],
            }
            if entry.get("data_period"):
                layer["data_period"] = entry["data_period"]
            layers.append(layer)
        payload = {
            "manifest_version": 1,
            "generated_at": now.isoformat(),
            "generator": f"worldtwin-aggregator/{__version__}",
            "envelope_version": 1,
            "counts": counts,
            "layers": layers,
        }
        _atomic_write(MANIFEST_PATH, payload)


# ---------------------------------------------------------------------------
# Counts ledger — /cache/v1/counts.json
# Per-layer {YYYY-MM-DD: count}. Written from the envelope's own count at
# commit time; last successful value of the day wins so a day freezes once it
# closes; a layer that failed gets NO entry, never a zero. 90-day retention.
# ---------------------------------------------------------------------------

_counts_lock = threading.Lock()
_counts: dict[str, dict[str, int]] = {}
_counts_loaded = False


def _ensure_counts_loaded() -> None:
    global _counts_loaded
    with _counts_lock:
        if _counts_loaded:
            return
        try:
            if COUNTS_PATH.exists():
                data = json.loads(COUNTS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for lid, days in data.items():
                        if isinstance(days, dict):
                            _counts[lid] = {d: int(c) for d, c in days.items()
                                            if isinstance(c, (int, float))}
        except Exception as e:
            print(f"[cache] counts load failed: {e}")
        _counts_loaded = True


def update_counts(layer_id: str, count: int | None) -> None:
    """Record today's count for a layer after a SUCCESSFUL envelope commit.
    Never called on failure — absence of an entry is the honest record."""
    if count is None:
        return
    _ensure_counts_loaded()
    today = datetime.now(timezone.utc).date()
    cutoff = (today - timedelta(days=90)).isoformat()
    with _counts_lock:
        _counts.setdefault(layer_id, {})[today.isoformat()] = int(count)
        for lid in list(_counts):
            days = _counts[lid]
            for day in [d for d in days if d < cutoff]:
                del days[day]
            if not days:
                del _counts[lid]
        try:
            _atomic_write(COUNTS_PATH, _counts)
        except Exception as e:
            print(f"[cache] counts persist failed: {e}")
