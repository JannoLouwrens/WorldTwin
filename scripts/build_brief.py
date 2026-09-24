#!/usr/bin/env python3
"""build_brief.py — the daily Earth brief, generated from static cache files only.

Stdlib only. Reads ONLY static files:
  /data/cache/v1/manifest.json          (the delivery contract; may be absent)
  /data/cache/v1/<layer>.json           (envelopes / tombstones)
  /data/cache/v1/counts.json            (per-layer daily count ledger; may be absent)
  /home/opc/worldtwin/weather/brief/*.json   (previous briefs — yesterday's is the state store)

NEVER any HTTP call. NEVER /api/health, /api/history/*, or any /api/* endpoint —
those 502 when the aggregator dies, and the whole point of this script is that it
publishes an honest brief *especially* when the aggregator is dead.

Writes (atomic tmp+rename, only after the whole brief built without exception):
  weather/brief/YYYY-MM-DD.json   — the citable record (append-only items; corrections add)
  weather/brief/YYYY-MM-DD.html   — a rendering of that JSON
  weather/brief/index.html        — archive index, newest first
  weather/brief/feed.xml          — RSS 2.0, forward-dated items only

ABSENCE CONTRACT: any exception → write NOTHING, leave the previous index.html,
append one line to weather/brief/_failures.log, exit 1.

Usage:
  build_brief.py                    # today (UTC)
  build_brief.py --date 2026-09-25  # a specific date
  build_brief.py --dry-run          # compute + print, write nothing
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

GENERATOR = "build_brief/1.0"
CACHE_DIR = Path(os.environ.get("WT_CACHE_DIR", "/data/cache/v1"))
BRIEF_DIR = Path(os.environ.get("WT_BRIEF_DIR", "/home/opc/worldtwin/weather/brief"))
SITE_BASE = "https://worldtwin.duckdns.org"
BRIEF_BASE = SITE_BASE + "/worldtwin/brief/"
RECORD_START = "2026-09-24"
DESTROYED_NOTE = (
    "The record begins 2026-09-24. The prior recorded range 11 June – 9 August 2026 "
    "was destroyed on 9 August 2026 when the history store was emptied. No off-site copy "
    "existed. This notice is dated 2026-09-24 and is permanent."
)

# The locked enabled set (REVIVAL_V1 §6.12). Everything else is retired/dropped.
ENABLED = [
    "quakes", "fires", "gdacs_events", "volcanoes", "usgs_volcano_hans",
    "flights", "swpc_aurora", "cloudflare_radar", "country_polygons",
    "noaa_co2", "fred",
]

# Instrument-of-the-day pool — enabled sources only (REVIVAL_V1 §6.17).
INSTRUMENT_POOL = ["cloudflare_outages", "swpc_kp", "noaa_co2_ppm", "fred_brent"]

DARK_STATES = {"stale", "dead"}
LIVE_STATES = {"ok", "live"}

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- time helpers

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(v) -> datetime | None:
    """Parse an ISO timestamp (naive treated as UTC) or epoch-ms number."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(v, str) or not v:
        return None
    s = v.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # bare date
        if ISO_DATE_RE.match(v.strip()):
            return datetime.strptime(v.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_str(dt: datetime | None, ref: datetime | None = None) -> str:
    if dt is None:
        return "unknown age"
    ref = ref or utcnow()
    s = (ref - dt).total_seconds()
    if s < 0:
        return "in the future"
    if s < 3600:
        return f"{int(s // 60)} min"
    if s < 172800:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} d"


# ---------------------------------------------------------------- file helpers

def read_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o644)  # mkstemp creates 0600; these pages are served by Caddy
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class PartialPublishError(Exception):
    """A publish failed part-way. .replaced lists the paths already renamed
    live (empty when the failure hit during staging — nothing published)."""

    def __init__(self, replaced: list[Path], cause: BaseException):
        self.replaced = replaced
        self.cause = cause
        super().__init__(f"{type(cause).__name__}: {cause} "
                         f"({len(replaced)} file(s) already replaced)")


def publish_all(outputs: dict[Path, str]) -> list[Path]:
    """Two-phase publish: stage EVERY output as a fsynced tmp file first, then
    perform the os.replace renames only after all staging succeeded. Returns
    the replaced paths; on any failure unlinks the un-renamed tmps and raises
    PartialPublishError carrying whatever was already replaced."""
    staged: list[tuple[str, Path]] = []
    replaced: list[Path] = []
    try:
        for path, text in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                                       prefix=f".{path.name}.", suffix=".tmp")
            os.fchmod(fd, 0o644)  # mkstemp creates 0600; served by Caddy
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            staged.append((tmp, path))
        for tmp, path in staged:  # phase 2: same-fs renames, no new space needed
            os.replace(tmp, path)
            replaced.append(path)
        return replaced
    except BaseException as e:
        for tmp, _ in staged:
            try:
                os.unlink(tmp)  # no-op for tmps already renamed
            except OSError:
                pass
        raise PartialPublishError(replaced, e) from e


def envelope(layer_id: str):
    """Read a layer envelope from the static v1 tree. None if absent/corrupt."""
    return read_json(CACHE_DIR / f"{layer_id}.json")


def env_retired(env) -> bool:
    return bool(isinstance(env, dict) and env.get("state") == "retired")


def esc(s) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


# ---------------------------------------------------------------- manifest

def load_manifest():
    """Return (manifest_dict_or_None, states dict id -> {state, since, reason, last_success_at})."""
    man = read_json(CACHE_DIR / "manifest.json")
    if not isinstance(man, dict) or not isinstance(man.get("layers"), list):
        return None, None
    states = {}
    for lay in man["layers"]:
        if not isinstance(lay, dict) or not lay.get("id"):
            continue
        st = (lay.get("state") or "unknown").lower()
        states[lay["id"]] = {
            "state": "ok" if st in LIVE_STATES else st,
            "since": lay.get("stale_since") or lay.get("last_success_at"),
            "last_success_at": lay.get("last_success_at"),
            "reason": lay.get("reason") or lay.get("retired_reason")
                      or lay.get("state_detail") or None,
        }
    return man, states


def fallback_states(now: datetime):
    """No manifest → derive an honest per-layer state for the ENABLED set from
    each envelope's own fetched_at/expires_at: past expires_at by more than
    max(3× the layer's own refresh interval, 30 min) = dark. This respects
    slow-cadence layers (volcanoes refreshes weekly) without a manifest."""
    states = {}
    for lid in ENABLED:
        env = envelope(lid)
        if env is None:
            states[lid] = {"state": "dead", "since": None, "last_success_at": None,
                           "reason": "cache file missing"}
            continue
        if env_retired(env):
            states[lid] = {"state": "retired", "since": env.get("fetched_at"),
                           "last_success_at": env.get("fetched_at"),
                           "reason": env.get("reason") or env.get("retired_reason") or "retired"}
            continue
        ft = parse_ts(env.get("fetched_at"))
        xt = parse_ts(env.get("expires_at"))
        if ft and xt and xt > ft:
            grace = max((xt - ft) * 3, timedelta(minutes=30))
            st = "ok" if now <= xt + grace else "stale"
        elif ft:
            st = "ok" if (now - ft) <= timedelta(hours=24) else "stale"
        else:
            st = "stale"
        states[lid] = {"state": st, "since": env.get("fetched_at"),
                       "last_success_at": env.get("fetched_at"),
                       "reason": None if st == "ok" else
                       f"envelope fetched_at is {age_str(ft, now)} old (no manifest to consult)"}
    return states


# ---------------------------------------------------------------- counts ledger

def load_counts():
    """Tolerant reader for /data/cache/v1/counts.json.
    Returns {layer_id: {date_str: count}} or {} — never raises."""
    raw = read_json(CACHE_DIR / "counts.json")
    if not isinstance(raw, dict):
        return {}
    body = raw
    for key in ("layers", "counts", "days"):
        if isinstance(raw.get(key), dict):
            body = raw[key]
            break
    out = {}
    keys = list(body.keys())
    if keys and all(ISO_DATE_RE.match(k) for k in keys):
        # date -> {layer: n}
        for d, per in body.items():
            if not isinstance(per, dict):
                continue
            for lid, n in per.items():
                if isinstance(n, (int, float)):
                    out.setdefault(lid, {})[d] = n
    else:
        # layer -> {date: n}
        for lid, per in body.items():
            if not isinstance(per, dict):
                continue
            for d, n in per.items():
                if ISO_DATE_RE.match(str(d)) and isinstance(n, (int, float)):
                    out.setdefault(lid, {})[str(d)] = n
    return out


# ---------------------------------------------------------------- item builders

def base_item(kind, env, cache_id, view_layer):
    src = None
    src_url = None
    lic = None
    fetched = None
    if isinstance(env, dict):
        src = env.get("source")
        src_url = env.get("source_url")
        lic = env.get("license")
        fetched = env.get("fetched_at")
    return {
        "kind": kind,
        "in_window": False,
        "headline": None,
        "value": None,
        "units": None,
        "observed_at": None,
        "source": src,
        "source_url": src_url,
        "license": lic,
        "fetched_at": fetched,
        "cache": f"/api/cache/v1/{cache_id}.json",
        "view": f"/worldtwin/v2/?layers={view_layer}",
    }


def absence(item, source_name, last_update: datetime | None, now, what="no observation"):
    ts = iso(last_update)
    if last_update:
        item["headline"] = (f"{what} in the last 24 h; the {source_name} feed has not "
                            f"updated since {ts} ({age_str(last_update, now)}).")
    else:
        item["headline"] = (f"{what} in the last 24 h; the {source_name} cache file is "
                            f"missing or unreadable, so no last update time is on record.")
    item["in_window"] = False
    item["observed_at"] = ts
    return item


def newest_data_ts(env) -> datetime | None:
    """Best 'source last updated' timestamp: inner data.fetched, else envelope fetched_at."""
    if not isinstance(env, dict):
        return None
    data = env.get("data")
    if isinstance(data, dict):
        t = parse_ts(data.get("fetched"))
        if t:
            return t
    return parse_ts(env.get("fetched_at"))


def item_largest_quake(win_start, win_end, now):
    env = envelope("quakes")
    it = base_item("largest_quake", env, "quakes", "quakes")
    if not isinstance(env, dict) or env_retired(env) or not isinstance(env.get("data"), list):
        return absence(it, "USGS", newest_data_ts(env), now, "Largest quake: no observation")
    best, best_t = None, None
    for q in env["data"]:
        if not isinstance(q, dict):
            continue
        t = parse_ts((q.get("props") or {}).get("time_ms"))
        if t is None or not (win_start <= t <= win_end):
            continue
        v = q.get("value")
        if isinstance(v, (int, float)) and (best is None or v > best.get("value", -99)):
            best, best_t = q, t
    if best is None:
        return absence(it, "USGS", newest_data_ts(env), now, "Largest quake: no observation")
    props = best.get("props") or {}
    depth = props.get("depth_km")
    depth_s = f", depth {depth:g} km" if isinstance(depth, (int, float)) else ""
    it.update({
        "in_window": True,
        "headline": f"M{best['value']:g} — {props.get('place') or 'location not stated'}{depth_s}",
        "value": best["value"],
        "units": "Mw",
        "observed_at": iso(best_t),
        "source_url": props.get("usgs_url") or it["source_url"],
    })
    return it


GDACS_RANK = {"red": 3, "orange": 2, "green": 1}


def item_gdacs(win_start, win_end, now):
    env = envelope("gdacs_events")
    it = base_item("gdacs_alert", env, "gdacs_events", "gdacs_events")
    events = []
    if isinstance(env, dict) and not env_retired(env):
        data = env.get("data")
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            events = data["events"]
    if not events:
        return absence(it, "GDACS", newest_data_ts(env), now, "Highest GDACS alert: no active alert")
    best, best_rank, best_t = None, -1, None
    for ev in events:
        if not isinstance(ev, dict):
            continue
        to_t = parse_ts(ev.get("to_date")) or parse_ts(ev.get("from_date"))
        # active = the event's own window touches the brief window
        if to_t is None or to_t < win_start:
            continue
        rank = GDACS_RANK.get(str(ev.get("alert_level") or "").lower(), 0)
        sev = ev.get("severity") if isinstance(ev.get("severity"), (int, float)) else 0
        key = (rank, sev)
        if best is None or key > best_rank:
            best, best_rank, best_t = ev, key, to_t
    if best is None:
        return absence(it, "GDACS", newest_data_ts(env), now, "Highest GDACS alert: no active alert")
    pop = best.get("population_impact")
    pop_s = f" · population impact: {pop}" if pop else ""
    it.update({
        "in_window": True,
        "headline": (f"GDACS {best.get('alert_level')} — {best.get('type_name')}"
                     f", {best.get('country') or 'multiple countries'}{pop_s}"),
        "value": best.get("alert_level"),
        "units": "GDACS alert level",
        "observed_at": iso(best_t),
        "source_url": best.get("url") or it["source_url"],
    })
    return it


def fires_ts(props) -> datetime | None:
    d = props.get("date")
    if not isinstance(d, str) or not ISO_DATE_RE.match(d):
        return None
    t = str(props.get("time") or "0").strip()
    t = re.sub(r"\D", "", t).rjust(4, "0")[:4]
    try:
        return datetime.strptime(f"{d} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return parse_ts(d)


def item_fires(win_start, win_end, now, counts, date_s):
    env = envelope("fires")
    it = base_item("fires_24h", env, "fires", "fires")
    if not isinstance(env, dict) or env_retired(env) or not isinstance(env.get("data"), list):
        return absence(it, "NASA FIRMS", newest_data_ts(env), now, "Fire detections: no observation")
    n, newest = 0, None
    for f in env["data"]:
        if not isinstance(f, dict):
            continue
        t = fires_ts(f.get("props") or {})
        if t is None or not (win_start <= t <= win_end):
            continue
        n += 1
        if newest is None or t > newest:
            newest = t
    if n == 0:
        return absence(it, "NASA FIRMS", newest_data_ts(env), now, "Fire detections: no observation")
    per_day = counts.get("fires", {})
    prior = sorted(d for d in per_day if d < date_s)[-7:]
    median_note = None
    sigma = None
    if len(prior) >= 7:
        vals = [per_day[d] for d in prior]
        med = statistics.median(vals)
        sd = statistics.pstdev(vals)
        median_note = f"vs the layer's own 7-day median of {int(med):,}"
        if sd > 0:
            sigma = (n - med) / sd
    else:
        first = min(per_day) if per_day else RECORD_START
        median_note = f"no 7-day median yet — count record since {first}"
    it.update({
        "in_window": True,
        "headline": f"{n:,} VIIRS fire detections in 24 h — {median_note}",
        "value": n,
        "units": "detections",
        "observed_at": iso(newest),
        "median_note": median_note,
        "sigma_vs_median": round(sigma, 2) if sigma is not None else None,
    })
    return it


def _series_window_label(times):
    ts = sorted(t for t in times if t)
    if not ts:
        return None
    if len(ts) == 1 or ts[0].date() == ts[-1].date():
        return f"as of {iso(ts[-1])}"
    return f"{ts[0].strftime('%Y-%m-%d')} → {ts[-1].strftime('%Y-%m-%d')}"


def instrument_cloudflare(win_start, win_end, now):
    env = envelope("cloudflare_radar")
    it = base_item("instrument", env, "cloudflare_radar", "cloudflare_radar")
    it["instrument"] = "cloudflare_outages"
    outages = []
    if isinstance(env, dict) and not env_retired(env):
        data = env.get("data")
        if isinstance(data, dict) and isinstance(data.get("outages"), list):
            outages = data["outages"]
    active = []
    for o in outages:
        if not isinstance(o, dict):
            continue
        start = parse_ts(o.get("start"))
        end = parse_ts(o.get("end"))
        if start and start <= win_end and (end is None or end >= win_start):
            active.append((o, start, end))
    if not active:
        return absence(it, "Cloudflare Radar", newest_data_ts(env), now,
                       "Internet outages: none observed")
    national = [a for a in active if str(a[0].get("outage_type", "")).upper() == "NATIONWIDE"]
    active.sort(key=lambda a: a[1], reverse=True)
    lead = (national or active)[0]
    o = lead[0]
    times = [a[1] for a in active] + [a[2] for a in active if a[2]]
    it.update({
        "in_window": True,
        "headline": (f"{len(active)} internet outage(s) touched the window — "
                     f"largest: {o.get('country_name')} "
                     f"({str(o.get('outage_type') or 'scope not stated').lower()}"
                     f", {str(o.get('outage_cause') or 'cause not stated').lower().replace('_', ' ')})"),
        "value": len(active),
        "units": "outages",
        "observed_at": iso(lead[1]),
        "window": _series_window_label(times),
        "national_scale": bool(national),
        "source_url": o.get("url") or it["source_url"],
    })
    return it


def instrument_swpc(win_start, win_end, now):
    env = envelope("swpc_aurora")
    it = base_item("instrument", env, "swpc_aurora", "swpc_aurora")
    it["instrument"] = "swpc_kp"
    data = env.get("data") if isinstance(env, dict) and not env_retired(env) else None
    rows = []
    if isinstance(data, dict):
        hist = data.get("kp_index_history")
        if isinstance(hist, list):
            rows.extend(hist)
        if isinstance(data.get("kp_index"), (dict, list)):
            rows.append(data["kp_index"])
    best, best_t, times = None, None, []
    for r in rows:
        t = kp = None
        if isinstance(r, dict):
            t, kp = parse_ts(r.get("time_tag")), r.get("Kp")
        elif isinstance(r, list) and len(r) >= 2:
            t, kp = parse_ts(r[0]), r[1]
        try:
            kp = float(kp)
        except (TypeError, ValueError):
            continue
        if t is None or not (win_start <= t <= win_end):
            continue
        times.append(t)
        if best is None or kp > best:
            best, best_t = kp, t
    if best is not None:
        it.update({
            "in_window": True,
            "headline": f"Peak planetary Kp {best:g} in 24 h (NOAA SWPC)",
            "value": best, "units": "Kp", "observed_at": iso(best_t),
            "window": _series_window_label(times),
        })
        return it
    # No numeric Kp rows (the current cache stores header rows only) —
    # fall back to SWPC's own G-scale summary, which carries a real timestamp.
    scales = (data or {}).get("scales") if isinstance(data, dict) else None
    cur = scales.get("0") if isinstance(scales, dict) else None
    if isinstance(cur, dict) and isinstance(cur.get("G"), dict):
        g = cur["G"]
        t = parse_ts(f"{cur.get('DateStamp', '')}T{cur.get('TimeStamp', '')}")
        if t and win_start <= t <= win_end:
            it.update({
                "in_window": True,
                "headline": (f"Geomagnetic storm scale G{g.get('Scale')} "
                             f"({g.get('Text')}) — numeric Kp series not parseable "
                             f"in today's cache"),
                "value": g.get("Scale"), "units": "NOAA G scale",
                "observed_at": iso(t), "window": f"as of {iso(t)}",
            })
            return it
    return absence(it, "NOAA SWPC", newest_data_ts(env), now, "Kp index: no observation")


def instrument_co2(win_start, win_end, now):
    env = envelope("noaa_co2")
    it = base_item("instrument", env, "noaa_co2", "noaa_co2")
    it["instrument"] = "noaa_co2_ppm"
    data = env.get("data") if isinstance(env, dict) and not env_retired(env) else None
    head = data.get("headline") if isinstance(data, dict) else None
    ppm = head.get("current_co2_ppm") if isinstance(head, dict) else None
    obs = parse_ts(head.get("measurement_date")) if isinstance(head, dict) else None
    if not isinstance(ppm, (int, float)) or obs is None:
        return absence(it, "NOAA GML", newest_data_ts(env), now, "CO₂: no observation")
    # CO2 is a daily series; the newest reading is legitimately a couple of days
    # behind wall clock. Window label comes from the series' own timestamp.
    it.update({
        "in_window": win_start <= obs <= win_end,
        "headline": (f"Atmospheric CO₂ {ppm:.1f} ppm at "
                     f"{head.get('station') or 'Mauna Loa'} "
                     f"(measured {head.get('measurement_date')})"),
        "value": ppm, "units": "ppm",
        "observed_at": iso(obs),
        "window": f"as of {head.get('measurement_date')}",
    })
    if not it["in_window"]:
        it["headline"] += f" — newest reading is {age_str(obs, now)} old"
    return it


def instrument_brent(win_start, win_end, now):
    env = envelope("fred")
    it = base_item("instrument", env, "fred", "fred")
    it["instrument"] = "fred_brent"
    data = env.get("data") if isinstance(env, dict) and not env_retired(env) else None
    series = data.get("series") if isinstance(data, dict) else None
    brent = series.get("DCOILBRENTEU") if isinstance(series, dict) else None
    if not isinstance(brent, dict) or not isinstance(brent.get("latest"), (int, float)):
        return absence(it, "FRED", newest_data_ts(env), now, "Brent crude: no observation")
    obs = parse_ts(brent.get("latest_date"))
    it.update({
        "in_window": bool(obs and win_start <= obs <= win_end),
        "headline": (f"Brent crude ${brent['latest']:.2f}/bbl "
                     f"(FRED, series date {brent.get('latest_date')})"),
        "value": brent["latest"], "units": brent.get("unit") or "$/bbl",
        "observed_at": iso(obs),
        "window": f"as of {brent.get('latest_date')}",
    })
    if not it["in_window"]:
        it["headline"] += (f" — a daily market series; newest point is "
                           f"{age_str(obs, now)} old" if obs else "")
    return it


INSTRUMENTS = {
    "cloudflare_outages": instrument_cloudflare,
    "swpc_kp": instrument_swpc,
    "noaa_co2_ppm": instrument_co2,
    "fred_brent": instrument_brent,
}


# ---------------------------------------------------------------- dark/back delta

def previous_brief(date_s):
    """Newest brief JSON strictly older than date_s. Returns (date, dict) or (None, None)."""
    if not BRIEF_DIR.is_dir():
        return None, None
    dates = sorted(p.stem for p in BRIEF_DIR.glob("????-??-??.json")
                   if ISO_DATE_RE.match(p.stem) and p.stem < date_s)
    for d in reversed(dates):
        data = read_json(BRIEF_DIR / f"{d}.json")
        if isinstance(data, dict):
            return d, data
    return None, None


def compute_delta(states, prev_brief):
    """went_dark / came_back — a 24 h DELTA vs yesterday's brief JSON.
    A 'retired' layer is NEVER dark: retirement is a dated decision, not a failure."""
    went_dark, came_back = [], []
    today_dark = {lid for lid, s in states.items() if s["state"] in DARK_STATES}
    if prev_brief is None:
        return went_dark, came_back, "first day of record"
    prev_states = prev_brief.get("layer_states") or {}
    prev_dark = {lid for lid, s in prev_states.items()
                 if isinstance(s, dict) and s.get("state") in DARK_STATES}
    for lid in sorted(today_dark - prev_dark):
        s = states[lid]
        went_dark.append({"id": lid, "since": s.get("since"),
                          "reason": s.get("reason") or s["state"]})
    for lid in sorted(prev_dark):
        s = states.get(lid)
        if s and s["state"] in LIVE_STATES.union({"ok"}):
            came_back.append({"id": lid, "at": s.get("last_success_at"),
                              "dark_since": (prev_states.get(lid) or {}).get("since")})
    return went_dark, came_back, "delta vs previous brief"


# ---------------------------------------------------------------- the brief

def build_brief(date_s: str):
    now = utcnow()
    if date_s == now.strftime("%Y-%m-%d"):
        win_end = now
    else:
        win_end = datetime.strptime(date_s, "%Y-%m-%d").replace(
            hour=6, minute=47, tzinfo=timezone.utc)
    win_start = win_end - timedelta(hours=24)

    manifest, states = load_manifest()
    manifest_missing = manifest is None
    if states is None:
        states = fallback_states(now)

    # §0 pipeline state — newest fetch across enabled envelopes + manifest age
    newest_fetch = None
    for lid in ENABLED:
        env = envelope(lid)
        if isinstance(env, dict) and not env_retired(env):
            t = parse_ts(env.get("fetched_at"))
            if t and (newest_fetch is None or t > newest_fetch):
                newest_fetch = t
    man_gen = parse_ts(manifest.get("generated_at")) if manifest else None
    fetch_stale = newest_fetch is None or (now - newest_fetch) > timedelta(hours=1)
    manifest_stale = manifest_missing or man_gen is None or (now - man_gen) > timedelta(hours=1)
    pipeline_stale = fetch_stale or manifest_stale
    if fetch_stale:
        lead = (f"The aggregator has not written since "
                f"{iso(newest_fetch) if newest_fetch else 'an unknown time'} "
                f"({age_str(newest_fetch, now)} ago)"
                + (" and its contract file (manifest.json) is missing" if manifest_missing else "")
                + ". The observations below are the last on record, not today's.")
    elif manifest_missing:
        lead = (f"The aggregator's contract file (manifest.json) is missing, so pipeline "
                f"state cannot be asserted; envelope files were still updating as of "
                f"{iso(newest_fetch)}. The observations below are read from those envelopes.")
    elif manifest_stale:
        lead = (f"The manifest has not been regenerated since {iso(man_gen)} "
                f"({age_str(man_gen, now)} ago). The observations below are the last "
                f"on record, not today's.")
    else:
        lead = None
    pipeline = {
        "manifest_generated_at": iso(man_gen),
        "manifest_missing": manifest_missing,
        "newest_fetch_at": iso(newest_fetch),
        "stale": pipeline_stale,
        "note": lead,
    }

    counts_ledger = load_counts()

    items = [
        item_largest_quake(win_start, win_end, now),
        item_gdacs(win_start, win_end, now),
        item_fires(win_start, win_end, now, counts_ledger, date_s),
    ]
    inst_key = INSTRUMENT_POOL[
        datetime.strptime(date_s, "%Y-%m-%d").toordinal() % len(INSTRUMENT_POOL)]
    items.append(INSTRUMENTS[inst_key](win_start, win_end, now))

    prev_date, prev = previous_brief(date_s)
    went_dark, came_back, delta_state = compute_delta(states, prev)

    # currently-dark roster (non-retired only) for the lede threshold + HTML
    dark_now = sorted(lid for lid, s in states.items() if s["state"] in DARK_STATES)

    # -------- exception-led lede
    lede = None
    if pipeline_stale:
        lede = pipeline["note"]
    if lede is None:
        quake = items[0]
        if quake["in_window"] and isinstance(quake["value"], (int, float)) and quake["value"] >= 7:
            lede = f"A magnitude-{quake['value']:g} earthquake crossed the M7 threshold: {quake['headline']}."
    if lede is None:
        gd = items[1]
        if gd["in_window"] and str(gd.get("value", "")).lower() == "red":
            lede = f"GDACS holds a Red alert: {gd['headline']}."
    if lede is None:
        for it in items:
            if it.get("instrument") == "cloudflare_outages" and it.get("national_scale"):
                lede = f"A national-scale internet outage is on the board: {it['headline']}."
                break
    if lede is None and dark_now:
        lede = ("An enabled source is dark: " +
                ", ".join(f"{lid} (since {states[lid].get('since') or 'unknown'})"
                          for lid in dark_now) + ".")
    if lede is None:
        fr = items[2]
        sg = fr.get("sigma_vs_median")
        if isinstance(sg, (int, float)) and abs(sg) > 2:
            lede = (f"Fire detections are {sg:+.1f}σ from their own 7-day median: "
                    f"{fr['headline']}.")
    if lede is None:
        lede = "Nothing crossed a threshold today."

    man_counts = (manifest or {}).get("counts") or {}
    brief = {
        "date": date_s,
        "generated_at": iso(now),
        "window_start": iso(win_start),
        "window_end": iso(win_end),
        "generator": GENERATOR,
        "card": None,
        "pipeline": pipeline,
        "sources_live": man_counts.get("live"),
        "sources_total": man_counts.get("total"),
        "lede": lede,
        "items": items,
        "went_dark": went_dark,
        "came_back": came_back,
        "delta_state": delta_state,
        "previous_brief": prev_date,
        "corrections": [],
        # state store for tomorrow's delta — retired excluded from darkness by contract
        "layer_states": {lid: {"state": s["state"], "since": s.get("since")}
                         for lid, s in states.items() if s["state"] != "retired"},
    }
    return brief


# ---------------------------------------------------------------- HTML rendering

CSS = """
:root { --ink:#161310; --paper:#f8f5ef; --rule:#d9d2c3; --muted:#6b6459;
        --accent:#1d4ed8; --warn:#92400e; --card:#fffdf7; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#e8e4da; --paper:#15171c; --rule:#34373f; --muted:#9a958a;
          --accent:#8ab0ff; --warn:#e0a458; --card:#1b1e25; }
}
* { margin:0; padding:0; box-sizing:border-box; }
body { background:var(--paper); color:var(--ink); line-height:1.6;
  font-family: Georgia, 'Iowan Old Style', 'Times New Roman', Times, serif; }
.wrap { max-width:720px; margin:0 auto; padding:40px 22px 80px; }
.mono { font-family:ui-monospace,'SF Mono',Menlo,Consolas,monospace; }
header.mast { border-bottom:3px double var(--ink); padding-bottom:14px; }
.kicker { font-family:ui-monospace,monospace; font-size:11px; letter-spacing:.22em;
  text-transform:uppercase; color:var(--warn); }
h1 { font-size:38px; font-weight:700; letter-spacing:-.5px; line-height:1.1; margin-top:6px; }
.promise { font-style:italic; color:var(--muted); margin-top:6px; }
.dateline { font-family:ui-monospace,monospace; font-size:12px; color:var(--muted);
  margin-top:10px; display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; }
.pipeline { font-family:ui-monospace,monospace; font-size:11px; color:var(--muted);
  border:1px solid var(--rule); padding:8px 12px; margin-top:16px; background:var(--card); }
.pipeline.down { border-color:var(--warn); color:var(--warn); }
.lede { font-size:20px; margin:26px 0 6px; }
.lede::first-letter { font-size:52px; float:left; line-height:.9; padding-right:8px; font-weight:700; }
section.item { border:1px solid var(--rule); background:var(--card); margin:22px 0; }
section.item h2 { font-family:ui-monospace,monospace; font-size:11px; letter-spacing:.2em;
  text-transform:uppercase; padding:9px 14px; border-bottom:1px solid var(--rule); color:var(--warn); }
.item .head { padding:14px 16px 4px; font-size:19px; }
.item .head b { font-variant-numeric: tabular-nums; }
.num { font-variant-numeric: tabular-nums; }
.item .prov { font-family:ui-monospace,monospace; font-size:10.5px; color:var(--muted);
  padding:8px 16px 12px; }
.item .prov a { color:var(--accent); text-decoration:none; }
.absent { color:var(--muted); font-style:italic; }
ul.delta { padding:6px 16px 12px 34px; font-size:15px; }
.banner { border:1px solid var(--warn); color:var(--warn); background:var(--card);
  padding:10px 14px; margin:18px 0; font-size:14px; }
footer { margin-top:44px; border-top:3px double var(--ink); padding-top:16px;
  font-size:12px; color:var(--muted); font-family:ui-monospace,monospace; line-height:1.9; }
footer a, .note a { color:var(--accent); }
.idx { list-style:none; margin-top:22px; }
.idx li { border-bottom:1px solid var(--rule); padding:10px 2px; font-size:17px;
  display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.idx a { color:var(--ink); text-decoration:none; }
.idx a:hover { color:var(--accent); }
.idx .mono { color:var(--muted); font-size:11px; }
.note { border:1px solid var(--rule); background:var(--card); padding:12px 14px;
  margin-top:20px; font-size:14px; }
"""

SECTION_TITLES = {
    "largest_quake": "1 · Largest earthquake · 24 h · USGS",
    "gdacs_alert": "2 · Highest active GDACS alert",
    "fires_24h": "3 · Fire detections · 24 h · NASA FIRMS (VIIRS)",
    "instrument": "4 · Instrument of the day",
}


def render_item_html(it, now):
    title = SECTION_TITLES.get(it["kind"], it["kind"])
    if it["kind"] == "instrument" and it.get("instrument"):
        pretty = {"cloudflare_outages": "Internet outages · Cloudflare Radar",
                  "swpc_kp": "Planetary Kp · NOAA SWPC",
                  "noaa_co2_ppm": "Atmospheric CO₂ · NOAA GML",
                  "fred_brent": "Brent crude · FRED"}.get(it["instrument"], it["instrument"])
        title = f"4 · Instrument of the day · {pretty}"
    head_cls = "head" if it["in_window"] else "head absent"
    fetched = parse_ts(it.get("fetched_at"))
    fetched_s = fetched.strftime("%H:%M UTC") if fetched else "unknown"
    prov_bits = [
        esc(it.get("source") or "source unknown"),
        f"observed {esc(it.get('observed_at') or '—')}",
        f"fetched {esc(fetched_s)}",
    ]
    if it.get("window"):
        prov_bits.append(f"window {esc(it['window'])}")
    if it.get("license"):
        prov_bits.append(esc(it["license"]))
    links = [f'<a href="{esc(it["cache"])}">raw cache ↗</a>',
             f'<a href="{esc(it["view"])}">view on globe ↗</a>']
    if it.get("source_url"):
        links.insert(0, f'<a href="{esc(it["source_url"])}">source ↗</a>')
    return (f'<section class="item"><h2>{esc(title)}</h2>'
            f'<div class="{head_cls}">{esc(it.get("headline") or "no data")}</div>'
            f'<div class="prov">{" · ".join(prov_bits)}<br>{" · ".join(links)}</div>'
            f'</section>')


def render_brief_html(brief):
    now = utcnow()
    p = brief["pipeline"]
    pipe_cls = "pipeline down" if p["stale"] else "pipeline"
    if p["manifest_missing"]:
        pipe_txt = (f"PIPELINE: manifest.json MISSING · newest fetch "
                    f"{p['newest_fetch_at'] or 'none on record'}")
    else:
        pipe_txt = (f"PIPELINE: manifest generated {p['manifest_generated_at']} · "
                    f"newest fetch {p['newest_fetch_at'] or 'none on record'}")
    if p["stale"]:
        pipe_txt += " · " + (p.get("note") or "PIPELINE STALE — observations below are "
                             "the last on record")

    items_html = "\n".join(render_item_html(it, now) for it in brief["items"])

    if brief["delta_state"] == "first day of record":
        delta_html = ('<div class="head absent">First day of record — '
                      'no previous brief to diff against.</div>')
    else:
        parts = []
        if brief["went_dark"]:
            parts.append("<div class='head'>Went dark</div><ul class='delta'>" + "".join(
                f"<li><b>{esc(d['id'])}</b> — since {esc(d.get('since') or 'unknown')}"
                f" · {esc(d.get('reason') or '')}</li>" for d in brief["went_dark"]) + "</ul>")
        if brief["came_back"]:
            parts.append("<div class='head'>Came back</div><ul class='delta'>" + "".join(
                f"<li><b>{esc(d['id'])}</b> — dark since {esc(d.get('dark_since') or 'unknown')},"
                f" back at {esc(d.get('at') or 'unknown')}</li>" for d in brief["came_back"]) + "</ul>")
        if not parts:
            parts.append('<div class="head absent">No enabled source went dark or came '
                         'back in this window.</div>')
        delta_html = "".join(parts)
    delta_section = (f'<section class="item"><h2>5 · Went dark / came back · '
                     f'24 h delta</h2>{delta_html}'
                     f'<div class="prov">computed against '
                     f'{esc(brief["previous_brief"] or "no prior brief")} · a retired layer '
                     f'is never “dark” — retirement is a dated decision, '
                     f'not a failure</div></section>')

    src_line = ""
    if brief["sources_live"] is not None and brief["sources_total"] is not None:
        src_line = (f'<span class="num">{brief["sources_live"]}</span> of '
                    f'<span class="num">{brief["sources_total"]}</span> sources reporting · ')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Brief — {esc(brief['date'])} — WorldTwin</title>
<meta name="description" content="What the instruments said on {esc(brief['date'])} — dated, sourced, never quietly fixed.">
<style>{CSS}</style>
</head>
<body><div class="wrap">
<header class="mast">
  <div class="kicker">WorldTwin · The Daily Brief</div>
  <h1>Daily Brief — {esc(brief['date'])}</h1>
  <div class="promise">What the instruments said. Dated, sourced, and never quietly fixed.</div>
  <div class="dateline">
    <span>window {esc(brief['window_start'])} → {esc(brief['window_end'])}</span>
    <span>{src_line}generated {esc(brief['generated_at'])}</span>
  </div>
</header>
<div class="{pipe_cls}">{esc(pipe_txt)}</div>
<p class="lede">{esc(brief['lede'])}</p>
{items_html}
{delta_section}
<footer>
  This page is a rendering of the citable record
  <a href="{esc(brief['date'])}.json">{esc(brief['date'])}.json</a> — claims are never
  edited in place; corrections append (charter rule 4).<br>
  <a href="./">archive</a> · <a href="feed.xml">rss</a> ·
  <a href="/worldtwin/charter.html">charter</a> ·
  <a href="/worldtwin/status.html">status</a> ·
  <a href="/worldtwin/v2/">globe</a> · generated by {esc(brief['generator'])}
</footer>
</div></body></html>
"""


def list_brief_dates():
    if not BRIEF_DIR.is_dir():
        return []
    return sorted(p.stem for p in BRIEF_DIR.glob("????-??-??.json") if ISO_DATE_RE.match(p.stem))


def render_index_html(all_dates, today_s, ledes):
    now = utcnow()
    newest = max(all_dates) if all_dates else None
    banner = ""
    if newest:
        newest_dt = datetime.strptime(newest, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if (now - newest_dt) > timedelta(days=3):
            banner = (f'<div class="banner">This record has not updated since {esc(newest)} '
                      f'(noted {esc(now.strftime("%Y-%m-%d"))}). Generation failures are '
                      f'logged, not hidden — see the charter.</div>')
    rows = "\n".join(
        f'<li><a href="{esc(d)}.html">{esc(d)}</a>'
        f'<span class="mono">{esc((ledes.get(d) or "")[:110])}</span></li>'
        for d in sorted(all_dates, reverse=True))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Brief — archive — WorldTwin</title>
<meta name="description" content="Daily instrument briefs — dated, sourced, never quietly fixed. Record begins 2026-09-24.">
<style>{CSS}</style>
</head>
<body><div class="wrap">
<header class="mast">
  <div class="kicker">WorldTwin · The Daily Brief</div>
  <h1>The Daily Brief</h1>
  <div class="promise">What the instruments said. Dated, sourced, and never quietly fixed.</div>
  <div class="dateline"><span>one brief per day · 06:47 UTC</span>
  <span><a href="feed.xml">RSS</a></span></div>
</header>
{banner}
<div class="note"><span class="mono">NOTE · dated 2026-09-24</span><br>
{esc(DESTROYED_NOTE)} Full disclosure: <a href="/worldtwin/charter.html">the charter</a>.</div>
<ul class="idx">
{rows}
</ul>
<footer>
  <a href="/worldtwin/charter.html">charter</a> ·
  <a href="/worldtwin/status.html">status</a> ·
  <a href="/worldtwin/v2/">globe</a> · index regenerated {esc(iso(now))}
</footer>
</div></body></html>
"""


def render_feed_xml(all_dates, ledes, gen_ats):
    # Forward-dated items only: nothing before the record start ever enters the
    # feed (backfilled or gap pages index in the archive, never here).
    items = []
    for d in sorted(all_dates, reverse=True):
        if d < RECORD_START:
            continue
        url = f"{BRIEF_BASE}{d}.html"
        pub = parse_ts(gen_ats.get(d)) or datetime.strptime(d, "%Y-%m-%d").replace(
            hour=6, minute=47, tzinfo=timezone.utc)
        pub_s = pub.strftime("%a, %d %b %Y %H:%M:%S +0000")
        desc = esc(ledes.get(d) or f"Daily brief for {d}")
        items.append(
            f"    <item>\n"
            f"      <title>Daily Brief — {d}</title>\n"
            f"      <link>{url}</link>\n"
            f"      <guid isPermaLink=\"true\">{url}</guid>\n"
            f"      <pubDate>{pub_s}</pubDate>\n"
            f"      <description>{desc}</description>\n"
            f"    </item>")
        if len(items) >= 30:
            break
    now_s = utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\">\n"
        "  <channel>\n"
        "    <title>WorldTwin — The Daily Brief</title>\n"
        f"    <link>{BRIEF_BASE}</link>\n"
        "    <description>What the instruments said. Dated, sourced, and never "
        "quietly fixed. Record begins 2026-09-24.</description>\n"
        "    <language>en</language>\n"
        f"    <lastBuildDate>{now_s}</lastBuildDate>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n"
        "</rss>\n")


# ---------------------------------------------------------------- main

def log_failure(date_s, err, dry_run):
    line = f"{iso(utcnow())} date={date_s} {type(err).__name__}: {err}\n"
    if dry_run:
        sys.stderr.write("[dry-run] would append to _failures.log: " + line)
        return
    try:
        BRIEF_DIR.mkdir(parents=True, exist_ok=True)
        with open(BRIEF_DIR / "_failures.log", "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as e:
        sys.stderr.write(f"[brief] could not write _failures.log: {e}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the daily brief from static cache files.")
    ap.add_argument("--date", default=utcnow().strftime("%Y-%m-%d"),
                    help="brief date, YYYY-MM-DD (default: today UTC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print, write nothing")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an already-published brief (violates charter "
                         "rule 4; prefer a correction)")
    args = ap.parse_args()
    date_s = args.date
    if not ISO_DATE_RE.match(date_s):
        print(f"[brief] bad --date {date_s!r} (want YYYY-MM-DD)", file=sys.stderr)
        return 2

    # Charter rule 4: published briefs are byte-stable — never rebuilt in place.
    # Refuse BEFORE the try block so the refusal is not logged as a build failure,
    # and write NOTHING (no index/feed regeneration — that would leak recomputed
    # values into the archive while the published JSON keeps the originals).
    target = BRIEF_DIR / f"{date_s}.json"
    if not args.dry_run and not args.force and target.exists():
        print(f"[brief] {target} already exists — briefs are byte-stable "
              f"(charter rule 4). Append a correction to the published JSON "
              f"instead, or re-run with --force to knowingly overwrite.",
              file=sys.stderr)
        return 1

    try:
        brief = build_brief(date_s)

        # Assemble every output in memory BEFORE any write (absence contract:
        # an exception anywhere leaves the previous index.html untouched).
        brief_json = json.dumps(brief, ensure_ascii=False, indent=1)
        brief_html = render_brief_html(brief)

        all_dates = set(list_brief_dates())
        all_dates.add(date_s)
        ledes, gen_ats = {date_s: brief["lede"]}, {date_s: brief["generated_at"]}
        for d in all_dates:
            if d == date_s:
                continue
            j = read_json(BRIEF_DIR / f"{d}.json")
            if isinstance(j, dict):
                ledes[d] = j.get("lede")
                gen_ats[d] = j.get("generated_at")
        index_html = render_index_html(all_dates, date_s, ledes)
        feed_xml = render_feed_xml(all_dates, ledes, gen_ats)

        outputs = {
            BRIEF_DIR / f"{date_s}.json": brief_json,
            BRIEF_DIR / f"{date_s}.html": brief_html,
            BRIEF_DIR / "index.html": index_html,
            BRIEF_DIR / "feed.xml": feed_xml,
        }

        if args.dry_run:
            print(f"[dry-run] brief for {date_s} built cleanly. Would write:")
            for p, text in outputs.items():
                print(f"  {p}  ({len(text.encode('utf-8')):,} bytes)")
            print("\n[dry-run] lede:", brief["lede"])
            print("[dry-run] pipeline:", json.dumps(brief["pipeline"]))
            print("[dry-run] delta:", brief["delta_state"],
                  f"went_dark={len(brief['went_dark'])} came_back={len(brief['came_back'])}")
            print("\n" + brief_json)
            return 0

        publish_all(outputs)
        print(f"[brief] wrote {date_s}.json/.html + index.html + feed.xml "
              f"under {BRIEF_DIR} · lede: {brief['lede']}")
        return 0

    except Exception as e:  # noqa: BLE001 — the absence contract catches everything
        log_failure(date_s, e, args.dry_run)
        import traceback
        traceback.print_exc()
        replaced = list(getattr(e, "replaced", None) or [])
        if replaced:
            print(f"[brief] FAILED for {date_s} MID-PUBLISH — already replaced: "
                  f"{', '.join(p.name for p in replaced)}; every other output "
                  f"(index/feed) was left at the previous day; one line appended "
                  f"to _failures.log", file=sys.stderr)
        else:
            print(f"[brief] FAILED for {date_s} — wrote nothing, previous index left "
                  f"in place, one line appended to _failures.log", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
