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


def _decompose_list(layer_id: str, payload: list, fetched_at: str) -> list[tuple]:
    """Top-level list of dicts (air_quality, population, ships, satellites,
    radio). One observation row per item, identified by the most-specific
    available id field."""
    rows: list[tuple] = []
    for i, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        # Best-guess identifier
        item_id = (item.get("id") or item.get("uuid") or item.get("stationuuid")
                   or item.get("mmsi") or item.get("norad")
                   or item.get("OBJECT_ID") or item.get("NORAD_CAT_ID")
                   or item.get("name") or item.get("portid")
                   or item.get("ICAO24") or item.get("country") or i)
        # Best-guess time — drill into common nested locations.
        # ALWAYS prefer the data's own datetime over fetched_at.
        observed = _extract_observed_at(item, fetched_at)
        # Best-guess numeric
        num_val = None
        for nk in ("value", "aqi", "pm25", "magnitude", "severity",
                   "population", "viewers", "players", "score"):
            v = item.get(nk)
            if isinstance(v, (int, float)):
                num_val = float(v); break
        # Friendly text
        txt = (item.get("name") or item.get("title") or item.get("OBJECT_NAME")
               or item.get("city") or "")[:200]
        meta = {}
        for mk in ("lat", "lon", "country", "iso3", "country_iso3",
                   "category", "type", "url"):
            if mk in item:
                meta[mk] = item[mk]
        rows.append((
            f"{layer_id}.{item_id}", observed, fetched_at,
            num_val, txt or None,
            json.dumps(item, default=str)[:3000],
            json.dumps(meta, default=str) if meta else None,
        ))
    return rows


def _extract_observed_at(item: dict, fallback: str) -> str:
    """Extract the data's OWN datetime from an event dict. Honors the vision:
    prefer the upstream's measurement timestamp over our fetch time. Drills
    into nested .props if needed (GDELT events). Decodes Unix timestamps.

    Order of preference:
      1. Top-level direct date fields
      2. Nested under .props (GDELT) or .properties (GeoJSON)
      3. Unix timestamps (int/float seconds)
      4. fetched_at fallback
    """
    # Direct top-level date fields
    DATE_FIELDS = ("date", "datetime", "date_start", "date_added",
                   "startDate", "start", "pubDate", "EPOCH",
                   "acq_date", "seendate", "startTime", "fromdate",
                   "from_date", "publication_date", "PublicationDateAndTime",
                   "observed_at", "measurement_time", "ts", "lastUpdatedOn")
    for f in DATE_FIELDS:
        v = item.get(f)
        if isinstance(v, str) and len(v) >= 4:
            return v[:25]
        if isinstance(v, (int, float)) and v > 1_000_000_000:
            # Unix epoch seconds
            try:
                from datetime import datetime as _dt, timezone as _tz
                return _dt.fromtimestamp(v, tz=_tz.utc).isoformat()[:25]
            except Exception:
                pass

    # Unix epoch ms field
    for f in ("time", "updated", "time_position"):
        v = item.get(f)
        if isinstance(v, (int, float)):
            try:
                from datetime import datetime as _dt, timezone as _tz
                # Heuristic: > 1e12 means milliseconds
                ts = v / 1000.0 if v > 1e12 else float(v)
                return _dt.fromtimestamp(ts, tz=_tz.utc).isoformat()[:25]
            except Exception:
                pass
        if isinstance(v, str) and len(v) >= 4:
            return v[:25]

    # Drill into nested props / properties (GDELT events, GeoJSON features)
    for nest_key in ("props", "properties"):
        nested = item.get(nest_key)
        if isinstance(nested, dict):
            for f in DATE_FIELDS:
                v = nested.get(f)
                if isinstance(v, str) and len(v) >= 4:
                    return v[:25]
            # Properties.time is often Unix ms
            for f in ("time", "updated"):
                v = nested.get(f)
                if isinstance(v, (int, float)):
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        ts = v / 1000.0 if v > 1e12 else float(v)
                        return _dt.fromtimestamp(ts, tz=_tz.utc).isoformat()[:25]
                    except Exception:
                        pass

    # Fallback — fetched_at, but trimmed to the day
    return fallback[:25] if fallback else ""


def _decompose(layer_id: str, payload: Any, fetched_at: str) -> list[tuple]:
    """Walk a plugin payload and return a list of observation row tuples
    (source_id, observed_at, fetched_at, value_num, value_text, value_json, meta_json).

    Permissive: returns [] if the shape doesn't match a known pattern.
    The snapshot is still saved either way, so we can re-decompose later.
    """
    rows: list[tuple] = []

    # Top-level list payloads (population/rest_countries, satellites/celestrak,
    # ships/aisstream, radio/radio_browser, air_quality/open_meteo_aq).
    # Must run BEFORE the dict guard.
    if isinstance(payload, list):
        return _decompose_list(layer_id, payload, fetched_at)

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

    # ---- Pattern: top-level list of dicts (no envelope) ----
    # air_quality, population (rest_countries), satellites (celestrak),
    # ships, radio.
    if isinstance(payload, list):
        return _decompose_list(layer_id, payload, fetched_at)

    # ---- Pattern: assets (climatetrace_assets) ----
    if isinstance(payload.get("assets"), list):
        for asset in payload["assets"]:
            if not isinstance(asset, dict):
                continue
            aid = asset.get("id") or asset.get("name")
            emissions = asset.get("emissions_quantity") or asset.get("emissions") or asset.get("activity")
            rows.append((
                f"{layer_id}.asset.{aid}", fetched_at[:10], fetched_at,
                float(emissions) if isinstance(emissions, _NUMERIC_TYPES) else None,
                str(asset.get("name") or "")[:200],
                json.dumps(asset, default=str)[:5000],
                json.dumps({"sector": asset.get("sector"), "country": asset.get("country"),
                            "lat": asset.get("lat"), "lon": asset.get("lon")}),
            ))
        if rows:
            return rows

    # ---- Pattern: countries dict where each value has nested fact sheets ----
    # country_deep_dive (water/food/oil/emissions), country_intel (snapshot/risks),
    # country_resources (top_exports/top_imports/total_exports_usd).
    countries_raw = payload.get("countries")
    if isinstance(countries_raw, dict) and countries_raw:
        first = next(iter(countries_raw.values()), None)
        if isinstance(first, dict) and any(k in first for k in
            ("snapshot", "electricity", "water", "food", "oil", "emissions",
             "total_exports_usd", "top_exports", "risks", "meta")):
            for iso3, entry in countries_raw.items():
                if not isinstance(entry, dict):
                    continue
                rows.append((
                    f"{layer_id}.{iso3}", fetched_at[:10], fetched_at,
                    None,
                    str(entry.get("name") or "")[:200],
                    json.dumps(entry, default=str)[:8000],
                    json.dumps({"iso3": iso3, "lat": entry.get("lat"), "lon": entry.get("lon")}),
                ))
            if rows:
                return rows

    # ---- Pattern: oecd_cli — countries[iso3] = [{period, value}] ----
    if isinstance(countries_raw, dict) and countries_raw:
        first = next(iter(countries_raw.values()), None)
        if isinstance(first, list) and first and isinstance(first[0], dict) and "period" in first[0]:
            for iso3, samples in countries_raw.items():
                if not isinstance(samples, list):
                    continue
                for s in samples:
                    if not isinstance(s, dict):
                        continue
                    period = s.get("period")
                    val = s.get("value")
                    if period is None or val is None:
                        continue
                    rows.append((
                        f"{layer_id}.{iso3}", str(period), fetched_at,
                        float(val) if isinstance(val, _NUMERIC_TYPES) else None,
                        None, None, json.dumps({"iso3": iso3}),
                    ))
            if rows:
                return rows

    # ---- Pattern: youtube_trending — countries[] each with videos[] ----
    if isinstance(payload.get("countries"), list) and payload["countries"] \
       and isinstance(payload["countries"][0], dict) \
       and "videos" in payload["countries"][0]:
        for country in payload["countries"]:
            cc = country.get("code") or country.get("name") or "?"
            for vid in (country.get("videos") or []):
                if not isinstance(vid, dict):
                    continue
                vid_id = vid.get("id") or vid.get("videoId")
                if not vid_id:
                    continue
                views = vid.get("viewCount") or vid.get("views")
                rows.append((
                    f"{layer_id}.{cc}.{vid_id}", fetched_at[:10], fetched_at,
                    float(views) if isinstance(views, _NUMERIC_TYPES) else None,
                    str(vid.get("title", ""))[:200],
                    json.dumps(vid, default=str)[:3000],
                    json.dumps({"country": cc, "lat": country.get("lat"),
                                "lon": country.get("lon")}),
                ))
        if rows:
            return rows

    # ---- Pattern: opensky flights — states[] is list-of-LISTS ----
    # OpenSky state vector: [icao24, callsign, origin_country, ts_pos, ts_contact,
    #   lon, lat, baro_alt, on_ground, velocity, true_track, vertical_rate,
    #   sensors, geo_alt, squawk, spi, position_source]
    if isinstance(payload.get("states"), list) and payload["states"] \
       and isinstance(payload["states"][0], list):
        for state in payload["states"]:
            if not isinstance(state, list) or len(state) < 17:
                continue
            icao24 = state[0]
            if not icao24:
                continue
            ts = state[3] or state[4] or 0
            from datetime import datetime as _dt, timezone as _tz
            try:
                observed = _dt.fromtimestamp(ts, tz=_tz.utc).isoformat() if ts else fetched_at
            except Exception:
                observed = fetched_at
            rows.append((
                f"{layer_id}.{icao24}", observed, fetched_at,
                float(state[7]) if isinstance(state[7], (int, float)) else None,
                state[1] or None,
                None,
                json.dumps({"icao24": icao24, "callsign": state[1],
                            "country": state[2], "lat": state[6], "lon": state[5],
                            "alt_m": state[7], "velocity": state[9],
                            "on_ground": state[8]}),
            ))
        if rows:
            return rows

    # ---- Pattern: FAO food-price raw_csv ----
    # Header: Date,Food Price Index,Meat,Dairy,Cereals,Oils,Sugar
    # Rows: "Jan-90, 108.7, 112.3, 94.3, 106.4, 73, 201.5"
    if "raw_csv" in payload and isinstance(payload.get("raw_csv"), str):
        import csv as _csv
        import io as _io
        import re as _re
        text = payload["raw_csv"]
        try:
            reader = _csv.reader(_io.StringIO(text))
            header = None
            for row in reader:
                if not row or not row[0].strip():
                    continue
                if header is None:
                    if row[0].lower().startswith("date"):
                        header = [c.strip() for c in row]
                    continue
                date_str = row[0].strip()
                # Parse "Jan-90" → 1990-01-01
                m = _re.match(r"^([A-Za-z]+)-(\d{2,4})$", date_str)
                if not m:
                    continue
                mname, yy = m.group(1), m.group(2)
                month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                             "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                month = month_map.get(mname.lower())
                if not month:
                    continue
                year = int(yy)
                if year < 100:
                    year += 2000 if year < 50 else 1900
                observed_iso = f"{year:04d}-{month:02d}-01"
                for i, val in enumerate(row[1:], 1):
                    if i >= len(header):
                        break
                    val = val.strip()
                    if not val:
                        continue
                    try:
                        v = float(val)
                    except ValueError:
                        continue
                    field = header[i]
                    rows.append((
                        f"{layer_id}.{field}", observed_iso, fetched_at,
                        v, None, None, json.dumps({"index": field}),
                    ))
            if rows:
                return rows
        except Exception:
            pass

    # ---- Pattern: by_ba dict (eia_930_grid) ----
    by_ba = payload.get("by_ba")
    if isinstance(by_ba, dict) and by_ba:
        for ba_id, entry in by_ba.items():
            if not isinstance(entry, dict):
                continue
            for key in ("D", "NG", "TI", "DF"):
                v = entry.get(key)
                # EIA returns numerics as strings sometimes — coerce
                if isinstance(v, str):
                    try: v = float(v)
                    except (ValueError, TypeError): v = None
                if isinstance(v, _NUMERIC_TYPES):
                    period = entry.get(f"{key}_period") or fetched_at[:13]
                    rows.append((
                        f"{layer_id}.{ba_id}.{key}", str(period), fetched_at,
                        float(v), None, None,
                        json.dumps({"ba": ba_id, "name": entry.get("name"),
                                    "lat": entry.get("lat"), "lon": entry.get("lon")}),
                    ))
        if rows:
            return rows

    # ---- Pattern: gemini_narrative council + digest snapshot ----
    council = payload.get("council")
    if isinstance(council, dict):
        for voice in ("general", "treasurer", "augur"):
            entry = council.get(voice)
            if not isinstance(entry, dict):
                continue
            rows.append((
                f"{layer_id}.council.{voice}", fetched_at[:10], fetched_at,
                None,
                str(entry.get("headline") or "")[:200],
                json.dumps(entry, default=str)[:5000],
                json.dumps({"voice": voice}),
            ))
        if rows:
            return rows

    # ---- Pattern: features_by_year — historical_borders ----
    # 1 row per (era, polity) so each border boundary becomes queryable —
    # plus a summary row per era with the count.
    if isinstance(payload.get("features_by_year"), dict):
        for y_str, feats in payload["features_by_year"].items():
            if not _is_year_string(y_str):
                continue
            if not isinstance(feats, list):
                continue
            n_feats = len(feats)
            # Summary row
            rows.append((
                f"{layer_id}.summary.{y_str}", _year_to_iso(y_str), fetched_at,
                float(n_feats), None, None,
                json.dumps({"year": y_str, "feature_count": n_feats}),
            ))
            # Per-polity row — keep the geometry in value_json so the user
            # can drill from a border claim to the actual polygon
            name_prop = payload.get("name_property") or "name"
            for f in feats:
                if not isinstance(f, dict):
                    continue
                props = f.get("properties") or {}
                polity = props.get(name_prop) or props.get("name") or props.get("admin") or "?"
                rows.append((
                    f"{layer_id}.{polity}", _year_to_iso(y_str), fetched_at,
                    None, str(polity)[:120],
                    json.dumps(f, default=str)[:8000],
                    json.dumps({"year": y_str, "polity": polity}),
                ))
        if rows:
            return rows

    # ---- Pattern: rovers (nasa_mars_photos) — rovers.<name>.photos ----
    rovers = payload.get("rovers")
    if isinstance(rovers, dict):
        for rover_name, info in rovers.items():
            if not isinstance(info, dict):
                continue
            photos = info.get("photos") or []
            rows.append((
                f"{layer_id}.{rover_name}", fetched_at[:10], fetched_at,
                float(len(photos)), None,
                json.dumps(info, default=str)[:5000],
                json.dumps({"rover": rover_name}),
            ))
        if rows:
            return rows

    # ---- Pattern: rainviewer radar/satellite frames ----
    if "radar" in payload and isinstance(payload.get("radar"), dict):
        for kind in ("past", "nowcast"):
            frames = payload["radar"].get(kind) or []
            for f in frames:
                t = f.get("time")
                rows.append((
                    f"{layer_id}.radar.{kind}", str(t), fetched_at,
                    None, f.get("path"), None,
                    json.dumps({"kind": kind}),
                ))
        if rows:
            return rows

    # ---- Pattern: iss + crew (wheretheiss) ----
    iss = payload.get("iss")
    if isinstance(iss, dict) and iss.get("latitude") is not None:
        rows.append((
            f"{layer_id}.position", fetched_at[:19], fetched_at,
            None, "ISS",
            json.dumps(iss, default=str)[:1000],
            json.dumps({"lat": iss.get("latitude"), "lon": iss.get("longitude"),
                        "altitude_km": iss.get("altitude")}),
        ))
        for crew_member in (payload.get("crew") or []):
            if isinstance(crew_member, dict):
                rows.append((
                    f"{layer_id}.crew.{crew_member.get('name', '?')}",
                    fetched_at[:10], fetched_at,
                    None, str(crew_member.get("name", ""))[:120],
                    json.dumps(crew_member, default=str), None,
                ))
        if rows:
            return rows

    # ---- Pattern: gaming snapshot (steam+twitch) ----
    if "topGames" in payload and isinstance(payload.get("topGames"), list):
        for game in payload["topGames"]:
            if not isinstance(game, dict):
                continue
            rows.append((
                f"{layer_id}.game.{game.get('appid', game.get('name', '?'))}",
                fetched_at[:10], fetched_at,
                float(game.get("players", 0)) if isinstance(game.get("players"), _NUMERIC_TYPES) else None,
                str(game.get("name", ""))[:120],
                None, json.dumps({"appid": game.get("appid"), "store": game.get("store")}),
            ))
        for region in (payload.get("regions") or []):
            if isinstance(region, dict):
                rows.append((
                    f"{layer_id}.region.{region.get('code', '?')}",
                    fetched_at[:10], fetched_at,
                    float(region.get("viewers", 0)) if isinstance(region.get("viewers"), _NUMERIC_TYPES) else None,
                    str(region.get("name", ""))[:120],
                    None,
                    json.dumps({"lat": region.get("lat"), "lon": region.get("lon"),
                                "topGame": region.get("topGame")}),
                ))
        if rows:
            return rows

    # ---- Pattern: NASA POWER grid_records — list of {lat,lon,t,param,value} ----
    grid_records = payload.get("grid_records")
    if isinstance(grid_records, list) and grid_records and isinstance(grid_records[0], dict) \
       and all(k in grid_records[0] for k in ("lat", "lon", "t", "param", "value")):
        for rec in grid_records:
            try:
                t_str = str(rec["t"])
                # YYYYMMDDHH → YYYY-MM-DDTHH:00
                if len(t_str) == 10 and t_str.isdigit():
                    iso_t = f"{t_str[:4]}-{t_str[4:6]}-{t_str[6:8]}T{t_str[8:10]}:00"
                else:
                    iso_t = t_str
                rows.append((
                    f"{layer_id}.{rec['param']}.{rec['lat']}_{rec['lon']}",
                    iso_t, fetched_at,
                    float(rec["value"]) if isinstance(rec["value"], _NUMERIC_TYPES) else None,
                    None, None,
                    json.dumps({"lat": rec["lat"], "lon": rec["lon"], "param": rec["param"]}),
                ))
            except (TypeError, ValueError, KeyError):
                continue
        if rows:
            return rows

    # ---- Pattern: top-level Open-Meteo grid ----
    if isinstance(payload.get("grid"), list):
        for cell in payload["grid"]:
            if not isinstance(cell, dict):
                continue
            lat, lon = cell.get("lat"), cell.get("lon")
            for k, v in cell.items():
                if k in ("lat", "lon"):
                    continue
                if isinstance(v, _NUMERIC_TYPES):
                    rows.append((
                        f"{layer_id}.{k}.{lat}_{lon}",
                        fetched_at[:13], fetched_at,
                        float(v), None, None,
                        json.dumps({"lat": lat, "lon": lon, "field": k}),
                    ))
        if rows:
            return rows

    # ---- Pattern: spacetrack_gp — flat lists already in payload ----
    for plist_key in ("payloads", "rocket_bodies", "debris_sample"):
        plist = payload.get(plist_key)
        if isinstance(plist, list):
            for item in plist:
                if not isinstance(item, dict):
                    continue
                norad = item.get("norad")
                if norad is None:
                    continue
                rows.append((
                    f"{layer_id}.{plist_key}.{norad}", fetched_at[:10], fetched_at,
                    None, str(item.get("name", ""))[:120],
                    json.dumps(item, default=str)[:3000],
                    json.dumps({"type": item.get("type"), "country": item.get("country"),
                                "regime": item.get("regime")}),
                ))
    if rows:
        return rows

    # ---- Pattern: top-level history dict ----
    # eia_petroleum: payload.history.<series_id> = [{t,v}, ...]
    history_dict = payload.get("history")
    if isinstance(history_dict, dict) and history_dict:
        first_v = next(iter(history_dict.values()), None)
        if isinstance(first_v, list) and first_v and isinstance(first_v[0], dict) \
           and ("t" in first_v[0] or "v" in first_v[0]):
            for sid, samples in history_dict.items():
                if not isinstance(samples, list):
                    continue
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
                        None, None,
                    ))
            if rows:
                return rows

    # ---- Pattern: by_country dict (country_relations, gdelt_relations) ----
    by_country = payload.get("by_country")
    if isinstance(by_country, dict) and by_country:
        for iso3, entry in by_country.items():
            if not isinstance(entry, dict):
                continue
            rows.append((
                f"{layer_id}.{iso3}", fetched_at[:10], fetched_at,
                None,
                str(entry.get("bloc_primary") or entry.get("name") or "")[:200],
                json.dumps(entry, default=str)[:5000],
                json.dumps({"iso3": iso3}),
            ))
        if rows:
            return rows

    # ---- Pattern: by_country_year dict (cow_alliances) ----
    bcy = payload.get("by_country_year")
    if isinstance(bcy, dict) and bcy:
        for iso3, year_map in bcy.items():
            if not isinstance(year_map, dict):
                continue
            for y_str, val in year_map.items():
                if not _is_year_string(y_str):
                    continue
                rows.append((
                    f"{layer_id}.{iso3}", _year_to_iso(y_str), fetched_at,
                    None,
                    str(val)[:200],
                    None, json.dumps({"iso3": iso3}),
                ))
        if rows:
            return rows

    # ---- Pattern: top-level annual list (berkeley_earth) ----
    annual_list = payload.get("annual")
    if isinstance(annual_list, list) and annual_list and isinstance(annual_list[0], dict) and "year" in annual_list[0]:
        for sample in annual_list:
            yr = sample.get("year")
            if not isinstance(yr, _NUMERIC_TYPES):
                continue
            anomaly = sample.get("anomaly_c")
            rows.append((
                f"{layer_id}.annual", _year_to_iso(int(yr)), fetched_at,
                float(anomaly) if isinstance(anomaly, _NUMERIC_TYPES) else None,
                None, json.dumps(sample, default=str), None,
            ))
        if rows:
            return rows

    # ---- Pattern: economy.crypto list of dicts with id/symbol ----
    crypto_list = payload.get("crypto")
    if isinstance(crypto_list, list) and crypto_list and isinstance(crypto_list[0], dict) \
       and ("symbol" in crypto_list[0] or "id" in crypto_list[0]):
        for c in crypto_list:
            sym = (c.get("symbol") or c.get("id") or "").upper()
            if not sym:
                continue
            price = c.get("price_usd") or c.get("current_price")
            ch = c.get("change_24h") or c.get("price_change_percentage_24h")
            rows.append((
                f"{layer_id}.crypto.{sym}.price_usd", fetched_at[:10], fetched_at,
                float(price) if isinstance(price, _NUMERIC_TYPES) else None,
                None, None, json.dumps({"symbol": sym, "name": c.get("name")}),
            ))
            if isinstance(ch, _NUMERIC_TYPES):
                rows.append((
                    f"{layer_id}.crypto.{sym}.change_24h_pct", fetched_at[:10], fetched_at,
                    float(ch), None, None, json.dumps({"symbol": sym}),
                ))
        # Don't return — let other rules also run if they match (e.g. forex below)
    forex = payload.get("forex")
    if isinstance(forex, dict):
        rates = forex.get("rates") or {}
        date = forex.get("date") or fetched_at[:10]
        for ccy, rate in rates.items():
            if isinstance(rate, _NUMERIC_TYPES):
                rows.append((
                    f"{layer_id}.forex.USD_{ccy}", date, fetched_at,
                    float(rate), None, None, json.dumps({"ccy": ccy}),
                ))
    if rows:
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

            # Categorical / per-country dict — country_culture, country_relations,
            # cow_alliances etc. Emit one row per country with the full entry
            # as value_json so the user can drill in.
            for iso3, entry in countries.items():
                if not isinstance(entry, dict):
                    continue
                rows.append((
                    f"{layer_id}.{iso3}", fetched_at[:10], fetched_at,
                    None,
                    str(entry.get("name") or entry.get("religion_primary") or
                        entry.get("ethnicity_primary") or entry.get("bloc_primary") or "")[:200],
                    json.dumps(entry, default=str)[:5000],
                    json.dumps({"iso3": iso3}),
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
                  "annual", "monthly_global_trend", "daily_trend",
                  "articles",          # gdelt_news, gdelt_conflicts
                  "data",              # crises (HDX-derived)
                  "top",               # wikipedia_trends
                  "webcams",           # windy_webcams
                  "renderable",        # eia_930_grid alt list
                  "rovers",            # nasa_mars (also dict-handled above)
                  "by_country_top20",  # openaq stations summary
                  )
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
            # Use the data's own datetime (drills into props/properties,
            # decodes Unix timestamps). Falls back to fetched_at only if
            # the upstream payload truly carries no datetime.
            observed = _extract_observed_at(evt, fetched_at)
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


def redecompose_all(only_layer: str | None = None) -> dict:
    """Walk every snapshot in the store, decompose each, and write any new
    observation rows. PRIMARY KEY (source_id, observed_at, fetched_at) means
    re-runs are idempotent — existing rows are silently ignored.

    Uses a 60-second busy_timeout to coexist with the live aggregator writers,
    plus per-snapshot retries on lock errors.
    """
    c = _conn()
    c.execute("PRAGMA busy_timeout=60000")
    sql = "SELECT layer_id, fetched_at, payload FROM snapshots"
    args: list = []
    if only_layer:
        sql += " WHERE layer_id = ?"; args.append(only_layer)
    sql += " ORDER BY layer_id, fetched_at"
    stats = {"snapshots_processed": 0, "observations_added": 0,
             "errors": 0, "by_layer": {}}
    snaps = list(c.execute(sql, args))
    for row in snaps:
        layer_id, fetched_at, payload_blob = row["layer_id"], row["fetched_at"], row["payload"]
        try:
            payload = json.loads(zlib.decompress(payload_blob).decode("utf-8"))
        except Exception:
            continue
        decomposed = _decompose(layer_id, payload, fetched_at)
        if decomposed:
            for attempt in range(5):
                try:
                    c.executemany(
                        "INSERT OR IGNORE INTO observations "
                        "(source_id, observed_at, fetched_at, value_num, value_text, value_json, meta_json) "
                        "VALUES (?,?,?,?,?,?,?)",
                        decomposed,
                    )
                    stats["observations_added"] += len(decomposed)
                    stats["by_layer"][layer_id] = stats["by_layer"].get(layer_id, 0) + len(decomposed)
                    break
                except sqlite3.OperationalError:
                    import time
                    time.sleep(0.5 * (attempt + 1))
                except sqlite3.Error as e:
                    stats["errors"] += 1
                    print(f"[redecompose] {layer_id}: {e}")
                    break
        stats["snapshots_processed"] += 1
    return stats


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
