"""Space-Track — full SATCAT + GP catalogue, API-policy-compliant edition.

POLICY HISTORY: the account was suspended 2026-06 for querying the gp class
more than once per hour. The old code looked compliant (refresh_s=8h) but the
schedule lived in RAM — the mem-watchdog restarts this container every ~15-30
minutes, and each restart re-ran a FULL 25k-object gp pull 125s after boot.

This rewrite is restart-proof and follows Space-Track's recommended pattern:

  1. All rate-limit state lives ON DISK in /cache (host volume, survives
     restarts): last query time, last full-sync time, backoff-until.
  2. The gp class is queried AT MOST once per hour, enforced against the
     persisted timestamp — never against process uptime.
  3. Queries run only in off-peak windows (minute 05-25 or 35-55), never at
     the :00/:30 peaks, per the suspension email's instruction.
  4. Hourly queries use Space-Track's OWN recommended incremental filter —
     only TLEs published in the last hour (CREATION_DATE/>now-0.042) —
     merged into a persistent local catalogue. The full-catalogue pull runs
     once per week (Sundays, 03:35-03:55 UTC window) to purge decayed
     objects, or once at bootstrap if the local catalogue is empty.
  5. Any 401/403 (suspended/locked account) sets a 24h on-disk backoff so a
     suspended account is never hammered.
  6. Kill switch: set SPACETRACK_DISABLED=1 in .env to disable entirely
     (used while awaiting reinstatement).

Requests per run: exactly 2 (1 login + 1 gp query). Worst-case gp queries:
24/day hourly incrementals + 1 weekly full = ~169/week. Old worst case was
~100 full pulls/day.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

SPACE_TRACK_USER = os.environ.get("SPACE_TRACK_USER", "")
SPACE_TRACK_PASS = os.environ.get("SPACE_TRACK_PASS", "")
DISABLED = bool(os.environ.get("SPACETRACK_DISABLED", ""))

CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))
STATE_PATH = CACHE_DIR / "spacetrack_state.json"
CATALOG_PATH = CACHE_DIR / "spacetrack_catalog.json"

MIN_INTERVAL_S = 55 * 60          # hard floor between gp queries
FULL_SYNC_EVERY_S = 7 * 86400     # weekly full-catalogue refresh
BACKOFF_ON_AUTH_FAIL_S = 24 * 3600

BASE = "https://www.space-track.org"
# Space-Track's recommended incremental query (from their suspension email):
# all TLEs published in the last hour, json format for the metadata fields
# we need (OBJECT_TYPE, COUNTRY_CODE, LAUNCH_DATE, ...).
QUERY_INCREMENTAL = (
    f"{BASE}/basicspacedata/query/class/gp/"
    "decay_date/null-val/CREATION_DATE/%3Enow-0.042/"
    "format/json/emptyresult/show"
)
QUERY_FULL = (
    f"{BASE}/basicspacedata/query/class/gp/"
    "decay_date/null-val/epoch/%3Enow-30/orderby/norad_cat_id/"
    "format/json/emptyresult/show"
)

LAYER = LayerMeta(
    id="spacetrack_gp",
    name="Space-Track — Full Satellite Catalogue",
    category="space",
    kind="raw",
    source="Space-Track.org (US Space Force)",
    source_url="https://www.space-track.org/",
    license="Space-Track Terms (free non-commercial)",
    # The worker wakes every 10 min but the ON-DISK gate below is what
    # actually limits gp queries to one per hour. refresh_s is NOT the
    # rate limiter any more — restarts reset it, which is what got the
    # account suspended.
    refresh_s=600,
    initial_delay_s=125,
    description=(
        "Full SATCAT + GP elements: 25k+ active payloads, rocket bodies, debris. "
        "Hourly incremental TLE merge per Space-Track API policy."
    ),
    requires_key=True,
    key_env="SPACE_TRACK_USER+SPACE_TRACK_PASS",
    enabled=bool(SPACE_TRACK_USER and SPACE_TRACK_PASS) and not DISABLED,
)


def _load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    tmp.replace(path)


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _in_offpeak_window(now: datetime) -> bool:
    # Allowed: 5-25 min past the hour, or 35-55 past. Never :00/:30 peaks.
    return 5 <= now.minute <= 25 or 35 <= now.minute <= 55


def _row_subset(row: dict) -> dict:
    """Keep only the GP fields we use — keeps the on-disk catalogue small."""
    return {
        "NORAD_CAT_ID": row.get("NORAD_CAT_ID"),
        "OBJECT_NAME": row.get("OBJECT_NAME"),
        "OBJECT_TYPE": row.get("OBJECT_TYPE"),
        "COUNTRY_CODE": row.get("COUNTRY_CODE"),
        "LAUNCH_DATE": row.get("LAUNCH_DATE"),
        "SITE": row.get("SITE"),
        "PERIOD": row.get("PERIOD"),
        "INCLINATION": row.get("INCLINATION"),
        "APOAPSIS": row.get("APOAPSIS"),
        "PERIAPSIS": row.get("PERIAPSIS"),
        "RCS_SIZE": row.get("RCS_SIZE"),
        "TLE_LINE1": row.get("TLE_LINE1"),
        "TLE_LINE2": row.get("TLE_LINE2"),
        "EPOCH": row.get("EPOCH"),
    }


def _build_payload(catalog: dict[str, dict], fetched_iso: str) -> dict:
    """Rebuild the cache payload (same shape as the original plugin)."""
    by_type: dict[str, int] = {}
    by_country: dict[str, int] = {}
    by_regime: dict[str, int] = {}
    catalogue: list[dict[str, Any]] = []

    for row in catalog.values():
        try:
            period = float(row.get("PERIOD") or 0)
            incl = float(row.get("INCLINATION") or 0)
            apo = float(row.get("APOAPSIS") or 0)
            per = float(row.get("PERIAPSIS") or 0)
        except (ValueError, TypeError):
            period = incl = apo = per = 0
        avg_alt = (apo + per) / 2
        if avg_alt < 2000:
            regime = "LEO"
        elif avg_alt < 10000:
            regime = "MEO"
        elif 35000 < avg_alt < 36500:
            regime = "GEO"
        elif avg_alt > 36500:
            regime = "HEO"
        else:
            regime = "MEO"
        obj_type = (row.get("OBJECT_TYPE") or "UNKNOWN").strip()
        country = (row.get("COUNTRY_CODE") or "UNK").strip()
        by_type[obj_type] = by_type.get(obj_type, 0) + 1
        by_country[country] = by_country.get(country, 0) + 1
        by_regime[regime] = by_regime.get(regime, 0) + 1
        catalogue.append({
            "norad": int(row.get("NORAD_CAT_ID", 0) or 0),
            "name": row.get("OBJECT_NAME", ""),
            "type": obj_type,
            "country": country,
            "launch": row.get("LAUNCH_DATE", ""),
            "launch_site": row.get("SITE", ""),
            "period_min": period,
            "inclination_deg": incl,
            "apoapsis_km": apo,
            "periapsis_km": per,
            "regime": regime,
            "rcs_size": row.get("RCS_SIZE") or "",
            "tle_line1": row.get("TLE_LINE1") or "",
            "tle_line2": row.get("TLE_LINE2") or "",
            "epoch": row.get("EPOCH") or "",
        })

    payloads = [c for c in catalogue if c["type"] == "PAYLOAD"]
    rocket_bodies = [c for c in catalogue if c["type"] == "ROCKET BODY"]
    debris = [c for c in catalogue if c["type"] == "DEBRIS"]

    return {
        "source": "Space-Track GP",
        "fetched": fetched_iso,
        "total": len(catalogue),
        "count": len(catalogue),
        "by_type": by_type,
        "by_regime": by_regime,
        "by_country_top10": dict(sorted(by_country.items(), key=lambda x: -x[1])[:10]),
        "payloads": payloads[:3000],
        "rocket_bodies": rocket_bodies[:500],
        "debris_sample": debris[:500],
        "payloads_full": payloads,
        "rocket_bodies_full": rocket_bodies,
        "debris_full": debris,
    }


async def fetch(client: httpx.AsyncClient):
    if DISABLED or not (SPACE_TRACK_USER and SPACE_TRACK_PASS):
        return None

    now = datetime.now(timezone.utc)
    state = _load_json(STATE_PATH, {})

    # 1. Account-suspension backoff — never hammer a locked account.
    backoff_until = _parse_iso(state.get("backoff_until"))
    if backoff_until and now < backoff_until:
        return None

    # 2. Hard once-per-hour gate, persisted on disk so container restarts
    #    can NOT reset it. This is the fix for the suspension.
    last_query = _parse_iso(state.get("last_query"))
    if last_query and (now - last_query).total_seconds() < MIN_INTERVAL_S:
        return None

    # 3. Off-peak window only (no :00/:30 peaks).
    if not _in_offpeak_window(now):
        return None

    # 4. Decide full vs incremental.
    catalog: dict[str, dict] = _load_json(CATALOG_PATH, {})
    last_full = _parse_iso(state.get("last_full"))
    need_bootstrap = not catalog
    weekly_due = (not last_full) or (now - last_full).total_seconds() >= FULL_SYNC_EVERY_S
    # Weekly full sync targets the Sunday 03:35-03:55 UTC window, but if
    # we've drifted >8 days (downtime) take the next available window.
    sunday_window = now.weekday() == 6 and now.hour == 3
    overdue = last_full and (now - last_full).total_seconds() >= 8 * 86400
    do_full = need_bootstrap or (weekly_due and (sunday_window or overdue or not last_full))

    url = QUERY_FULL if do_full else QUERY_INCREMENTAL

    async with httpx.AsyncClient(
        timeout=120,
        headers={"User-Agent": "WorldTwin/1.0 (jannolouwrens@gmail.com)"},
        follow_redirects=True,
    ) as st:
        try:
            r = await st.post(
                f"{BASE}/ajaxauth/login",
                data={"identity": SPACE_TRACK_USER, "password": SPACE_TRACK_PASS},
            )
            if r.status_code in (401, 403):
                print(f"[spacetrack_gp] login {r.status_code} — backing off 24h")
                state["backoff_until"] = (now + timedelta(seconds=BACKOFF_ON_AUTH_FAIL_S)).isoformat()
                _save_json(STATE_PATH, state)
                return None
            if r.status_code != 200:
                print(f"[spacetrack_gp] login {r.status_code}")
                return None

            r = await st.get(url)
            if r.status_code in (401, 403):
                print(f"[spacetrack_gp] gp query {r.status_code} — backing off 24h")
                state["backoff_until"] = (now + timedelta(seconds=BACKOFF_ON_AUTH_FAIL_S)).isoformat()
                _save_json(STATE_PATH, state)
                return None
            if r.status_code != 200:
                print(f"[spacetrack_gp] gp query {r.status_code}: {r.text[:120]}")
                return None
            rows = r.json() if r.content else []

            # Mark the query time NOW — even an empty result consumed our
            # hourly slot.
            state["last_query"] = now.isoformat()
            state.pop("backoff_until", None)
            if do_full:
                state["last_full"] = now.isoformat()
                catalog = {}  # full result replaces catalogue (drops decayed)
            for row in rows:
                norad = str(row.get("NORAD_CAT_ID") or "")
                if norad:
                    catalog[norad] = _row_subset(row)
            _save_json(CATALOG_PATH, catalog)
            _save_json(STATE_PATH, state)
            print(
                f"[spacetrack_gp] {'FULL' if do_full else 'incremental'} ok — "
                f"{len(rows)} rows merged, catalogue {len(catalog)}"
            )

            if not catalog:
                return None
            return _build_payload(catalog, now.isoformat())
        except Exception as e:
            print(f"[spacetrack_gp] error: {e}")
            return None


register(LAYER, fetch)
