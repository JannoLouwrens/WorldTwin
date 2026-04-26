"""WorldTwin History Store — append-only EAV + snapshot substrate.

Vision: A lab where anyone — from the king of Rome to a sceptical citizen —
can read the world from raw, dated, cross-checked sources instead of someone
else's framing, and trace every claim back to the instrument that measured it.

This module is the substrate that lets the lab REMEMBER. Every cache write
also appends to this store: structured rows in `observations` (queryable EAV)
plus the raw payload in `snapshots` (forensic receipt).

See docs/architecture/HISTORY_STORE.md for the full design rationale.

Public API:
    history.snapshot(layer_id, payload)            — called from cache.write_legacy
    history.query_series(source_id, since, until)  — read a single source's history
    history.read_snapshot(layer_id, at)            — fetch a closest-at-or-before payload
    history.coverage()                             — top-level row counts per layer
    history.compact()                              — nightly retention enforcement
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import threading
import zlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterable

# Single SQLite file. CACHE_DIR is /cache inside the container, which is
# bind-mounted from /data/cache on the host. The history db lives at
# /data/history/history.sqlite.
HISTORY_DIR = Path(os.environ.get("HISTORY_DIR", "/cache/../history"))
HISTORY_DB = Path(os.environ.get("HISTORY_DB", str(HISTORY_DIR / "history.sqlite")))

# One connection per thread; SQLite handles concurrency via WAL.
_local = threading.local()
_init_lock = threading.Lock()
_init_done = False


# ============================================================
# Connection + schema
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
  source_id    TEXT NOT NULL,
  observed_at  TEXT NOT NULL,
  fetched_at   TEXT NOT NULL,
  value_num    REAL,
  value_text   TEXT,
  value_json   TEXT,
  meta_json    TEXT,
  PRIMARY KEY (source_id, observed_at, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_obs_source_observed ON observations(source_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_observed        ON observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_fetched         ON observations(fetched_at DESC);

CREATE TABLE IF NOT EXISTS snapshots (
  layer_id    TEXT NOT NULL,
  fetched_at  TEXT NOT NULL,
  payload_kb  REAL,
  payload     BLOB NOT NULL,
  rows_added  INTEGER,
  PRIMARY KEY (layer_id, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_snap_layer_time ON snapshots(layer_id, fetched_at DESC);
"""


def _conn() -> sqlite3.Connection:
    """Per-thread connection. Creates the db on first use."""
    global _init_done
    c = getattr(_local, "conn", None)
    if c is not None:
        return c
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(HISTORY_DB), isolation_level=None, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA mmap_size=268435456")     # 256 MB
    with _init_lock:
        if not _init_done:
            for stmt in SCHEMA.strip().split(";"):
                s = stmt.strip()
                if s:
                    c.execute(s)
            _init_done = True
    _local.conn = c
    return c


# ============================================================
# Decomposer — turn a plugin payload into observation rows
# ============================================================

_NUMERIC_TYPES = (int, float)


def _is_year_string(s: Any) -> bool:
    return isinstance(s, str) and len(s) <= 6 and re.fullmatch(r"-?\d{1,5}", s) is not None


def _year_to_iso(year: int | str) -> str:
    """Convert a year (positive or negative integer) to ISO8601 first-of-year.
    Negative years (BC) are emitted with a leading minus sign in the year part.
    SQLite text comparison still orders correctly for queries within AD years."""
    y = int(year)
    if y >= 0:
        return f"{y:04d}-01-01"
    return f"-{abs(y):04d}-01-01"


def _decompose(layer_id: str, payload: Any, fetched_at: str) -> list[tuple]:
    """Walk a plugin payload and return a list of observation row tuples
    (source_id, observed_at, fetched_at, value_num, value_text, value_json, meta_json).

    Permissive: returns [] if the shape doesn't match a known pattern.
    The snapshot is still saved either way, so we can re-decompose later.
    """
    rows: list[tuple] = []
    if not isinstance(payload, dict):
        return rows

    # ---- Pattern: FRED-style series dict ----
    # payload.series = { 'DCOILBRENTEU': { latest, series: [{t,v}, ...],
    #                                       series_full: [{t,v}, ...] }, ... }
    # Prefer series_full (deep history) when present; fall back to series.
    series_dict = payload.get("series")
    if isinstance(series_dict, dict) and series_dict:
        first_v = next(iter(series_dict.values()), None)
        if isinstance(first_v, dict) and (
            isinstance(first_v.get("series_full"), list) or isinstance(first_v.get("series"), list)
        ):
            for sid, entry in series_dict.items():
                if not isinstance(entry, dict):
                    continue
                samples = entry.get("series_full") or entry.get("series") or []
                meta = {"label": entry.get("name") or entry.get("label"),
                        "category": entry.get("category"),
                        "unit": entry.get("unit")}
                meta_json = json.dumps({k: v for k, v in meta.items() if v is not None})
                for sample in samples:
                    if not isinstance(sample, dict):
                        continue
                    t = sample.get("t") or sample.get("date")
                    v = sample.get("v")
                    if t is None or v is None:
                        continue
                    rows.append((
                        f"{layer_id}.{sid}", str(t), fetched_at,
                        float(v) if isinstance(v, _NUMERIC_TYPES) else None,
                        None if isinstance(v, _NUMERIC_TYPES) else str(v),
                        None, meta_json,
                    ))
            return rows

    # ---- Pattern: World Bank country×indicator ----
    # payload.countries[iso3][indicator_code] = { value, year, history: {year_str: value} }
    countries = payload.get("countries")
    if isinstance(countries, dict) and countries:
        sample_country = next(iter(countries.values()), None)
        if isinstance(sample_country, dict):
            sample_field = next(iter(sample_country.values()), None)
            # WB shape: each indicator is a dict with year+value+history
            if isinstance(sample_field, dict) and ("history" in sample_field or "value" in sample_field):
                for iso3, ind_map in countries.items():
                    if not isinstance(ind_map, dict):
                        continue
                    for ind_code, entry in ind_map.items():
                        if not isinstance(entry, dict):
                            continue
                        meta_json = json.dumps({"iso3": iso3, "indicator": ind_code})
                        history = entry.get("history") or {}
                        if isinstance(history, dict) and history:
                            for y_str, v in history.items():
                                if v is None or not _is_year_string(y_str):
                                    continue
                                rows.append((
                                    f"{layer_id}.{ind_code}.{iso3}",
                                    _year_to_iso(y_str), fetched_at,
                                    float(v) if isinstance(v, _NUMERIC_TYPES) else None,
                                    None if isinstance(v, _NUMERIC_TYPES) else str(v),
                                    None, meta_json,
                                ))
                        # Also emit the latest as a row (even if history covered it)
                        latest = entry.get("latest") or entry
                        ly = latest.get("year") if isinstance(latest, dict) else None
                        lv = latest.get("value") if isinstance(latest, dict) else None
                        if ly is not None and lv is not None:
                            rows.append((
                                f"{layer_id}.{ind_code}.{iso3}",
                                _year_to_iso(ly), fetched_at,
                                float(lv) if isinstance(lv, _NUMERIC_TYPES) else None,
                                None if isinstance(lv, _NUMERIC_TYPES) else str(lv),
                                None, meta_json,
                            ))
                return rows
            # V-Dem / Clio shape: countries[iso3].history = {year: value}
            if isinstance(sample_country.get("history"), dict):
                for iso3, entry in countries.items():
                    if not isinstance(entry, dict):
                        continue
                    history = entry.get("history") or {}
                    name = entry.get("name")
                    meta_json = json.dumps({"iso3": iso3, "name": name})
                    for y_str, v in history.items():
                        if v is None or not _is_year_string(y_str):
                            continue
                        rows.append((
                            f"{layer_id}.{iso3}", _year_to_iso(y_str), fetched_at,
                            float(v) if isinstance(v, _NUMERIC_TYPES) else None,
                            None if isinstance(v, _NUMERIC_TYPES) else str(v),
                            None, meta_json,
                        ))
                if rows:
                    return rows
            # Pulse / single-snapshot shape: countries[iso3] = {composite, scores}
            for iso3, entry in countries.items():
                if not isinstance(entry, dict):
                    continue
                composite = entry.get("composite")
                if composite is not None:
                    rows.append((
                        f"{layer_id}.composite.{iso3}", fetched_at[:10], fetched_at,
                        float(composite), None, None,
                        json.dumps({"iso3": iso3, "name": entry.get("name"),
                                    "trend": entry.get("trend")}),
                    ))
            if rows:
                return rows

    # ---- Pattern: HYDE/Maddison-style numbered country dict with series ----
    # payload.countries[ent].series = [[year, value], ...] with iso3 / name keys
    if isinstance(countries, dict) and countries:
        sample_country = next(iter(countries.values()), None)
        if isinstance(sample_country, dict) and isinstance(sample_country.get("series"), list):
            for ent, entry in countries.items():
                iso3 = entry.get("iso3") or ent
                name = entry.get("name")
                meta_json = json.dumps({"iso3": iso3, "name": name})
                for row in entry["series"]:
                    if not isinstance(row, (list, tuple)) or len(row) < 2:
                        continue
                    y, v = row[0], row[1]
                    if v is None or not isinstance(y, _NUMERIC_TYPES):
                        continue
                    rows.append((
                        f"{layer_id}.{iso3}", _year_to_iso(int(y)), fetched_at,
                        float(v) if isinstance(v, _NUMERIC_TYPES) else None,
                        None if isinstance(v, _NUMERIC_TYPES) else str(v),
                        None, meta_json,
                    ))
            if rows:
                return rows

    # ---- Pattern: NOAA CO2 / paleo temp — top-level series array ----
    # payload.historical_series = [[year, ppm], ...]
    # payload.series = [[year, anomaly_c], ...]
    for series_field in ("historical_series", "series"):
        s = payload.get(series_field)
        if isinstance(s, list) and s and isinstance(s[0], (list, tuple)) and len(s[0]) >= 2:
            for row in s:
                if not isinstance(row, (list, tuple)) or len(row) < 2:
                    continue
                y, v = row[0], row[1]
                if v is None or not isinstance(y, _NUMERIC_TYPES):
                    continue
                rows.append((
                    f"{layer_id}.{series_field}", _year_to_iso(int(y)), fetched_at,
                    float(v), None, None, None,
                ))
            if rows:
                # also capture the headline if present
                head = payload.get("headline")
                if isinstance(head, dict):
                    rows.append((
                        f"{layer_id}.headline", fetched_at[:10], fetched_at,
                        None, None, json.dumps(head, default=str), None,
                    ))
                return rows

    # ---- Pattern: GeoJSON FeatureCollection (USGS quakes etc.) ----
    # Walk both the live `features` array AND the deeper `historical_features`
    # array (used by usgs_quakes.py's M5+ archive backfill).
    feats_combined = []
    for fkey in ("features", "historical_features"):
        if isinstance(payload.get(fkey), list):
            feats_combined.extend(payload[fkey])
    if feats_combined:
        for i, feat in enumerate(feats_combined[:60000]):
            if not isinstance(feat, dict):
                continue
            props = feat.get("properties") or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") if isinstance(geom, dict) else None
            event_id = feat.get("id") or props.get("id") or f"feat_{i}"
            mag = props.get("mag")
            t_ms = props.get("time")
            observed = (
                datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).isoformat()
                if isinstance(t_ms, (int, float)) else fetched_at
            )
            meta = {"place": props.get("place"), "depth_km": coords[2] if coords and len(coords) > 2 else None}
            if coords and len(coords) >= 2:
                meta["lat"] = coords[1]; meta["lon"] = coords[0]
            rows.append((
                f"{layer_id}.{event_id}", observed, fetched_at,
                float(mag) if isinstance(mag, _NUMERIC_TYPES) else None,
                props.get("title") or props.get("place"),
                json.dumps(props, default=str),
                json.dumps(meta, default=str),
            ))
        return rows

    # ---- Pattern: Generic event lists ----
    # Plugins can append "_full" suffix to a list to mark it as the
    # full-archive version that the History Store should ingest in full
    # (without the UI's render budget). e.g. events_full, asteroids_full.
    EVENT_KEYS = ("events", "events_full", "outbreaks", "outbreaks_full",
                  "battles", "battles_full", "disasters", "disasters_full",
                  "storms", "alerts", "asteroids", "asteroids_full",
                  "catalogue",
                  "headlines", "items", "stations", "ports", "ports_full",
                  "chokepoints", "chokepoints_full",
                  "facilities", "plants", "samples", "cables", "themes",
                  "concerns", "pulses", "pulses_full", "tracks",
                  "stories", "videos", "tweets",
                  "channels", "schedules", "matches", "outages", "trips",
                  "ships", "flights", "satellites", "powerplants",
                  "payloads", "payloads_full", "rocket_bodies", "rocket_bodies_full",
                  "debris", "debris_full", "debris_sample",
                  "trades", "flows", "flows_full", "edges", "points", "annual",
                  "pairs", "pairs_full",
                  "history_records",
                  "kp_index_history", "solar_wind_history",
                  "ports_full", "chokepoints_full",
                  "annual", "monthly_global_trend", "daily_trend")
    seen_event_keys = set()
    for key in EVENT_KEYS:
        seq = payload.get(key)
        if not isinstance(seq, list) or not seq:
            continue
        # Skip if a _full variant is also present and we already processed it
        # to avoid double-counting. (e.g. if events_full exists, also seeing
        # `events` would be redundant for the same row contents — but they
        # have different ids in the source_id so it's still distinct.)
        if key in seen_event_keys:
            continue
        seen_event_keys.add(key)
        # No 5000 cap — let the full archive land. The decomposer is the
        # canonical record; the UI gets bounded slices via the cache file.
        for i, evt in enumerate(seq):
            if not isinstance(evt, dict):
                continue
            evt_id = (evt.get("id") or evt.get("uuid") or evt.get("name")
                      or evt.get("title") or evt.get("eventId") or f"{key}_{i}")
            observed = (evt.get("date") or evt.get("date_start") or evt.get("startDate")
                        or evt.get("pubDate") or evt.get("time") or evt.get("date_added")
                        or evt.get("fetched") or fetched_at)
            if isinstance(observed, str):
                observed = observed[:25] or fetched_at
            else:
                observed = fetched_at
            value_text = (evt.get("title") or evt.get("name") or evt.get("label")
                          or evt.get("description") or "")[:200]
            meta = {}
            for mk in ("lat", "lon", "country", "country_iso3", "iso3", "magnitude",
                       "category", "type", "severity"):
                if mk in evt:
                    meta[mk] = evt[mk]
            num_val = None
            for nk in ("value", "magnitude", "severity", "count", "score"):
                v = evt.get(nk)
                if isinstance(v, _NUMERIC_TYPES):
                    num_val = float(v); break
            rows.append((
                f"{layer_id}.{key}.{evt_id}", str(observed), fetched_at,
                num_val, value_text or None,
                json.dumps(evt, default=str)[:5000],
                json.dumps(meta, default=str) if meta else None,
            ))
        if rows:
            return rows

    # ---- Fallback: store nothing structured; snapshot still saved ----
    return rows


# ============================================================
# Public API
# ============================================================

def snapshot(layer_id: str, payload: Any) -> dict:
    """Append a fetch to the history store. Called from cache.write_legacy.

    Always saves the raw snapshot. Tries to decompose into observation rows.
    Returns a dict {snapshot_added, observation_rows, errors}. Never raises;
    a failed history write must not block the live cache write.
    """
    result = {"snapshot_added": False, "observation_rows": 0, "errors": []}
    try:
        fetched_at = (payload.get("fetched") if isinstance(payload, dict) else None) \
                     or datetime.now(timezone.utc).isoformat()
        c = _conn()

        # 1. Decompose to observation rows
        rows = _decompose(layer_id, payload, fetched_at)
        if rows:
            try:
                c.executemany(
                    "INSERT OR IGNORE INTO observations "
                    "(source_id, observed_at, fetched_at, value_num, value_text, value_json, meta_json) "
                    "VALUES (?,?,?,?,?,?,?)",
                    rows,
                )
                result["observation_rows"] = len(rows)
            except sqlite3.Error as e:
                result["errors"].append(f"observations write: {e}")

        # 2. Snapshot the full payload (compressed)
        try:
            payload_str = json.dumps(payload, ensure_ascii=False, default=str)
            payload_kb = round(len(payload_str.encode()) / 1024.0, 1)
            blob = zlib.compress(payload_str.encode("utf-8"), level=6)
            c.execute(
                "INSERT OR IGNORE INTO snapshots "
                "(layer_id, fetched_at, payload_kb, payload, rows_added) "
                "VALUES (?,?,?,?,?)",
                (layer_id, fetched_at, payload_kb, blob, len(rows)),
            )
            result["snapshot_added"] = True
        except sqlite3.Error as e:
            result["errors"].append(f"snapshot write: {e}")

    except Exception as e:
        result["errors"].append(f"top-level: {e}")
    return result


def query_series(source_id: str, since: str | None = None,
                 until: str | None = None, limit: int = 5000) -> list[dict]:
    """Return time-series rows for one source_id, ordered by observed_at desc.

    Each row: {observed_at, value_num, value_text, fetched_at, meta}.
    """
    c = _conn()
    sql = "SELECT observed_at, fetched_at, value_num, value_text, meta_json " \
          "FROM observations WHERE source_id = ?"
    args: list[Any] = [source_id]
    if since:
        sql += " AND observed_at >= ?"; args.append(since)
    if until:
        sql += " AND observed_at <= ?"; args.append(until)
    sql += " ORDER BY observed_at DESC, fetched_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in c.execute(sql, args):
        out.append({
            "observed_at": r["observed_at"],
            "fetched_at": r["fetched_at"],
            "value_num": r["value_num"],
            "value_text": r["value_text"],
            "meta": json.loads(r["meta_json"]) if r["meta_json"] else None,
        })
    return out


def read_snapshot(layer_id: str, at: str | None = None) -> dict | None:
    """Return the closest snapshot at-or-before `at` (default: latest)."""
    c = _conn()
    if at:
        row = c.execute(
            "SELECT fetched_at, payload, payload_kb, rows_added FROM snapshots "
            "WHERE layer_id = ? AND fetched_at <= ? ORDER BY fetched_at DESC LIMIT 1",
            (layer_id, at),
        ).fetchone()
    else:
        row = c.execute(
            "SELECT fetched_at, payload, payload_kb, rows_added FROM snapshots "
            "WHERE layer_id = ? ORDER BY fetched_at DESC LIMIT 1",
            (layer_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "layer_id": layer_id,
        "fetched_at": row["fetched_at"],
        "payload_kb": row["payload_kb"],
        "rows_added": row["rows_added"],
        "payload": json.loads(zlib.decompress(row["payload"]).decode("utf-8")),
    }


def coverage() -> dict:
    """Return a top-level summary: total observations, total snapshots,
    per-layer counts, observed_at range."""
    c = _conn()
    obs_total = c.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    snap_total = c.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
    by_layer = []
    rows = c.execute(
        "SELECT SUBSTR(source_id, 1, INSTR(source_id, '.') - 1) AS layer, "
        "       COUNT(*) AS n, MIN(observed_at) AS lo, MAX(observed_at) AS hi "
        "FROM observations "
        "WHERE INSTR(source_id, '.') > 0 "
        "GROUP BY layer ORDER BY n DESC"
    ).fetchall()
    for r in rows:
        by_layer.append({"layer": r["layer"], "rows": r["n"],
                         "observed_min": r["lo"], "observed_max": r["hi"]})
    snap_by_layer = c.execute(
        "SELECT layer_id, COUNT(*) AS n, SUM(payload_kb) AS kb "
        "FROM snapshots GROUP BY layer_id ORDER BY n DESC"
    ).fetchall()
    snaps = [{"layer": r["layer_id"], "snapshots": r["n"],
              "total_kb": round(r["kb"] or 0, 1)} for r in snap_by_layer]
    return {
        "observations_total": obs_total,
        "snapshots_total": snap_total,
        "by_layer_observations": by_layer,
        "by_layer_snapshots": snaps,
        "db_path": str(HISTORY_DB),
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def compact() -> dict:
    """Apply the retention policy:
       <30d: keep all snapshots
       30d-1y: one per day
       1y-5y: one per week
       >5y:  one per month
    Observations are NEVER deleted."""
    c = _conn()
    now = datetime.now(timezone.utc)
    # bucket boundaries
    cut_30d = (now - timedelta(days=30)).isoformat()
    cut_1y  = (now - timedelta(days=365)).isoformat()
    cut_5y  = (now - timedelta(days=365 * 5)).isoformat()

    deleted = {"daily_compact": 0, "weekly_compact": 0, "monthly_compact": 0}

    def _compact(window_lo: str, window_hi: str, bucket_expr: str, label: str):
        # For each (layer, bucket) keep the LATEST snapshot, delete the rest
        sql = f"""
            DELETE FROM snapshots
            WHERE fetched_at >= ? AND fetched_at < ?
              AND ROWID NOT IN (
                SELECT MAX(ROWID) FROM snapshots
                WHERE fetched_at >= ? AND fetched_at < ?
                GROUP BY layer_id, {bucket_expr}
              )
        """
        before = c.execute("SELECT COUNT(*) FROM snapshots WHERE fetched_at >= ? AND fetched_at < ?",
                           (window_lo, window_hi)).fetchone()[0]
        c.execute(sql, (window_lo, window_hi, window_lo, window_hi))
        after = c.execute("SELECT COUNT(*) FROM snapshots WHERE fetched_at >= ? AND fetched_at < ?",
                          (window_lo, window_hi)).fetchone()[0]
        deleted[label] = before - after

    # 30d-1y: bucket by day
    _compact(cut_1y,  cut_30d, "SUBSTR(fetched_at, 1, 10)",  "daily_compact")
    # 1y-5y: bucket by ISO week (year-week)
    _compact(cut_5y,  cut_1y,  "STRFTIME('%Y-%W', fetched_at)", "weekly_compact")
    # >5y: bucket by month
    _compact("0000-01-01T00:00:00", cut_5y, "SUBSTR(fetched_at, 1, 7)", "monthly_compact")

    c.execute("VACUUM")
    return deleted
