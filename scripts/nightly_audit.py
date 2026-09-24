#!/usr/bin/env python3
"""WorldTwin nightly audit — assertions A–F over the delivery contract, emailed via Gmail.

Rewritten 2026-09-24 (REVIVAL_V1 Commit C): the hand-maintained 18-name cache
allowlist and the LLM "council" section are gone. The audit now asserts the
manifest contract (MASTER_PLAN invariants A–F) from STATIC FILES on disk, plus
two deterministic cross-checks against independent live sources (USGS, NOAA)
for layers that are still enabled. No LLM anywhere in the audit.

  A. manifest.counts.total == len(manifest.layers)  (+ sources-dir cross-count, informational)
  B. every stale/dead layer is named with stale_since / last_success_at
  C. every representation over max_bytes (default 2 MB) is flagged
  D. every /data/cache/v1/*.json has a manifest entry (orphans reported;
     manifest.json / counts.json / _status.json / brief/ excluded)
  E. counts.json has yesterday's entry for every layer whose state is ok
     (skipped gracefully on day 1)
  F. /data free > 30 GB, root free > 4 GB, /var/oled free > 1 GB, and the
     newest file in /home/opc/worldtwin/weather/brief/ is under 72 h old

OAuth2 refresh token lives in /home/opc/worldtwin/.gmail_oauth.json,
created once by gmail_oauth_setup.py. The script mints a short-lived
access token on every run and POSTs to gmail.googleapis.com.

No App Password, no SMTP — pure HTTPS.
"""
from __future__ import annotations
import base64
import json
import shutil
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

OAUTH_PATH = Path("/home/opc/worldtwin/.gmail_oauth.json")
USER_AGENT = "WorldTwin-NightlyAudit/2.0"
TO_ADDR = "jannolouwrens@gmail.com"
FROM_ADDR = None  # filled from oauth config (the account that consented)

V1_DIR = Path("/data/cache/v1")
MANIFEST_PATH = V1_DIR / "manifest.json"
COUNTS_PATH = V1_DIR / "counts.json"
BRIEF_DIR = Path("/home/opc/worldtwin/weather/brief")
SOURCES_DIR = Path("/home/opc/worldtwin/aggregator/worldtwin/sources")
DEFAULT_MAX_BYTES = 2 * 1024 * 1024

LIVE_STATES = {"ok", "live"}


# ---- HTTP helpers (external cross-checks + Gmail only — never localhost) ----

def http_json(url: str, timeout: int = 25, headers: dict | None = None) -> dict | None:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def http_text(url: str, timeout: int = 25) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def http_post_form(url: str, data: dict, timeout: int = 30) -> dict | None:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                  headers={"Content-Type": "application/x-www-form-urlencoded",
                                           "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"[audit] OAuth refresh HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
        return None
    except Exception as e:
        print(f"[audit] OAuth refresh error: {e}")
        return None


def http_post_json(url: str, payload: dict, headers: dict, timeout: int = 30) -> tuple[int, dict | str]:
    body = json.dumps(payload).encode()
    h = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers}
    req = urllib.request.Request(url, data=body, method="POST", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")
    except Exception as e:
        return 0, str(e)


# ---- static-file helpers ----

def read_json_file(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def norm_state(s) -> str:
    s = str(s or "unknown").lower()
    return "live" if s in LIVE_STATES else s


def load_counts_ledger() -> dict:
    """Tolerant reader → {layer_id: {date: count}}; {} on any problem."""
    raw = read_json_file(COUNTS_PATH)
    if not isinstance(raw, dict):
        return {}
    body = raw
    for key in ("layers", "counts", "days"):
        if isinstance(raw.get(key), dict):
            body = raw[key]
            break
    import re
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    out: dict = {}
    keys = list(body.keys())
    if keys and all(date_re.match(k) for k in keys):
        for d, per in body.items():
            if isinstance(per, dict):
                for lid, n in per.items():
                    if isinstance(n, (int, float)):
                        out.setdefault(lid, {})[d] = n
    else:
        for lid, per in body.items():
            if isinstance(per, dict):
                for d, n in per.items():
                    if date_re.match(str(d)) and isinstance(n, (int, float)):
                        out.setdefault(lid, {})[str(d)] = n
    return out


# ---- assertions ----

def run_assertions() -> tuple[dict, list[str], list[str], list[str]]:
    """Returns (counts_dict, failures, warnings, info_lines)."""
    failures: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    manifest = read_json_file(MANIFEST_PATH)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("layers"), list):
        failures.append("MANIFEST MISSING — /data/cache/v1/manifest.json absent or unreadable; "
                        "the delivery contract does not exist and every assertion below is moot")
        return {}, failures, warnings, info

    layers = [l for l in manifest["layers"] if isinstance(l, dict) and l.get("id")]
    by_id = {l["id"]: l for l in layers}

    tally = {"live": 0, "stale": 0, "dead": 0, "retired": 0}
    for l in layers:
        st = norm_state(l.get("state"))
        if st in tally:
            tally[st] += 1
    counts = dict(manifest.get("counts") or {})
    counts.setdefault("total", len(layers))
    counts.update({"computed_" + k: v for k, v in tally.items()})
    info.append(f"manifest generated_at={manifest.get('generated_at')} · "
                f"{tally['live']} live · {tally['stale']} stale · {tally['dead']} dead · "
                f"{tally['retired']} retired of {len(layers)}")

    # A — counts.total equals the number of layer entries
    total_claimed = (manifest.get("counts") or {}).get("total")
    if total_claimed != len(layers):
        failures.append(f"A: manifest.counts.total={total_claimed} != len(layers)={len(layers)}")
    if SOURCES_DIR.is_dir():
        n_sources = len([p for p in SOURCES_DIR.glob("*.py") if not p.name.startswith("_")])
        if n_sources != len(layers):
            info.append(f"A (informational): sources dir has {n_sources} plugin files vs "
                        f"{len(layers)} manifest layers (helpers/multi-layer plugins make "
                        f"an exact match non-mandatory)")

    # B — every stale/dead layer named, with stale_since and last_success_at
    for l in layers:
        st = norm_state(l.get("state"))
        if st in ("stale", "dead"):
            since = l.get("stale_since")
            last = l.get("last_success_at")
            warnings.append(f"B: [{st.upper():5}] {l['id']:24} stale_since={since} "
                            f"last_success_at={last}")
            if not since and not last:
                failures.append(f"B: {l['id']} is {st} but carries neither stale_since "
                                f"nor last_success_at — contract violation")

    # C — representations over max_bytes
    for l in layers:
        cap = l.get("max_bytes") or DEFAULT_MAX_BYTES
        for rep in l.get("representations") or []:
            if isinstance(rep, dict) and isinstance(rep.get("bytes"), (int, float)) \
                    and rep["bytes"] > cap:
                failures.append(f"C: {l['id']} rep '{rep.get('rel')}' is "
                                f"{int(rep['bytes']):,} B > max_bytes {int(cap):,} B")

    # D — every v1/*.json file has a manifest entry (orphan hunt)
    exclude = {"manifest.json", "counts.json", "_status.json"}
    data_dupes = 0
    if V1_DIR.is_dir():
        for p in sorted(V1_DIR.glob("*.json")):
            if p.name in exclude:
                continue
            stem = p.name[:-5]  # strip .json
            for suffix in (".data", ".render"):
                if stem.endswith(suffix):
                    if suffix == ".data":
                        data_dupes += 1
                    stem = stem[: -len(suffix)]
                    break
            if stem not in by_id:
                failures.append(f"D: orphan cache file with no manifest entry: {p.name}")
    else:
        failures.append(f"D: {V1_DIR} does not exist")
    if data_dupes:
        warnings.append(f"D: {data_dupes} legacy .data.json duplicate(s) still present in v1/ "
                        f"(scheduled for deletion in Commit C)")

    # E — counts.json freshness per ok layer, scaled to refresh cadence
    # (day-1 graceful; sub-daily layers need yesterday's entry, slower layers
    # need any entry within ~2 refresh periods)
    ledger = load_counts_ledger()
    today_d = datetime.now(timezone.utc).date()
    yesterday = (today_d - timedelta(days=1)).isoformat()
    all_dates = {d for per in ledger.values() for d in per}
    if not ledger or not any(d <= yesterday for d in all_dates):
        info.append("E: counts.json has no closed day yet — day 1, skipped gracefully")
    else:
        for l in layers:
            if norm_state(l.get("state")) != "live":
                continue
            refresh_s = l.get("refresh_s") or 600
            if refresh_s <= 86400:
                if yesterday not in ledger.get(l["id"], {}):
                    failures.append(f"E: counts.json missing {yesterday} entry for ok layer "
                                    f"{l['id']} (no-entry-never-zero means it did not fetch "
                                    f"— or the ledger writer is broken)")
            else:
                window_days = max(int(2 * refresh_s // 86400), 2)
                cutoff = (today_d - timedelta(days=window_days)).isoformat()
                if not any(d >= cutoff for d in ledger.get(l["id"], {})):
                    failures.append(f"E: counts.json has no entry in the last "
                                    f"{window_days} d for ok layer {l['id']} "
                                    f"(cadence {refresh_s} s ≈ every "
                                    f"{refresh_s / 86400:.1f} d — it should have "
                                    f"fetched at least once in that window)")

    # F — disk floors + the brief actually publishing
    for path, floor_gb, label in (("/data", 30, "/data"), ("/", 4, "root"),
                                  ("/var/oled", 1, "/var/oled")):
        try:
            free_gb = shutil.disk_usage(path).free / 1e9
            (info if free_gb > floor_gb else failures).append(
                f"F: {label} free {free_gb:.1f} GB (floor {floor_gb} GB)"
                + ("" if free_gb > floor_gb else " — BELOW FLOOR"))
        except OSError as e:
            failures.append(f"F: cannot stat {label}: {e}")
    try:
        # Only published dated pages count — _failures.log / .git / index.html
        # must never satisfy the freshness check.
        newest = max((p.stat().st_mtime for p in BRIEF_DIR.glob("????-??-??.html")
                      if p.is_file()), default=None)
    except OSError:
        newest = None
    if newest is None:
        failures.append(f"F: no dated brief page has ever published under {BRIEF_DIR}")
    else:
        age_h = (datetime.now(timezone.utc).timestamp() - newest) / 3600
        (info if age_h < 72 else failures).append(
            f"F: newest dated brief page in weather/brief/ is {age_h:.1f} h old"
            + ("" if age_h < 72 else " — OVER 72 h, the brief has stopped"))

    return counts, failures, warnings, info


# ---- cross-checks (enabled layers only; BTC/economy retired → dropped) ----

def cross_checks() -> list[dict]:
    results: list[dict] = []
    manifest = read_json_file(MANIFEST_PATH) or {}
    states = {l.get("id"): norm_state(l.get("state"))
              for l in (manifest.get("layers") or []) if isinstance(l, dict)}

    # USGS quakes M4.5+ past day — cached v1 envelope data[] vs live USGS feed
    if states.get("quakes", "live") != "retired":
        cached = read_json_file(V1_DIR / "quakes.json") or {}
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        cached_45 = [q for q in (cached.get("data") or [])
                     if isinstance(q, dict)
                     and isinstance(q.get("value"), (int, float)) and q["value"] >= 4.5
                     and isinstance((q.get("props") or {}).get("time_ms"), (int, float))
                     and now_ms - q["props"]["time_ms"] <= 86_400_000]
        usgs = http_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
        usgs_count = len((usgs or {}).get("features") or [])
        if usgs is None:
            results.append({"label": "USGS quakes M4.5+ past day", "ok": True,
                            "note": "external feed unreachable — skipped, not failed"})
        else:
            delta = abs(usgs_count - len(cached_45))
            results.append({"label": "USGS quakes M4.5+ past day",
                            "cached": str(len(cached_45)), "external": str(usgs_count),
                            "divergence": f"{delta} events", "ok": delta <= 5})

    # NOAA CO2 ppm — cached v1 envelope vs Mauna Loa daily CSV
    if states.get("noaa_co2", "live") != "retired":
        cached_co2 = read_json_file(V1_DIR / "noaa_co2.json") or {}
        head = ((cached_co2.get("data") or {}).get("headline")
                if isinstance(cached_co2.get("data"), dict) else None) or {}
        cached_ppm = head.get("current_co2_ppm")
        noaa = http_text("https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.csv")
        last_ppm = None
        if noaa:
            for line in reversed(noaa.splitlines()):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 5:
                    try:
                        v = float(parts[4])
                        if v > 0:
                            last_ppm = v
                            break
                    except ValueError:
                        continue
        if last_ppm and isinstance(cached_ppm, (int, float)):
            div = abs(last_ppm - cached_ppm)
            results.append({"label": "NOAA CO2 ppm vs Mauna Loa CSV",
                            "cached": f"{cached_ppm:.2f}", "external": f"{last_ppm:.2f}",
                            "divergence": f"{div:.2f} ppm", "ok": div < 1.0})
        else:
            results.append({"label": "NOAA CO2 ppm", "ok": False,
                            "note": f"cached={cached_ppm} external={last_ppm}"})

    return results


# ---- report ----

def render_report(counts: dict, failures: list[str], warnings: list[str],
                  info: list[str], cross: list[dict]) -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cross_failures = [c for c in cross if not c.get("ok")]
    n_fail = len(failures) + len(cross_failures)

    live = counts.get("computed_live", counts.get("live", "?"))
    stale = counts.get("computed_stale", counts.get("stale", "?"))
    dead = counts.get("computed_dead", counts.get("dead", "?"))
    retired = counts.get("computed_retired", counts.get("retired", "?"))
    total = counts.get("total", "?")
    counts_line = f"{live} live · {stale} stale · {dead} dead · {retired} retired of {total}"

    verdict = "PASS" if n_fail == 0 else f"{n_fail} FAILED"
    subject = f"WorldTwin audit {today}: {counts_line} — {verdict}"

    lines = [f"WorldTwin Manifest Audit — {today} UTC", "=" * 60, "",
             f"COUNTS: {counts_line}", f"VERDICT: {verdict}", ""]

    lines.append("ASSERTIONS A–F")
    lines.append("-" * 60)
    if failures:
        for f in failures:
            lines.append(f"  [FAIL] {f}")
    else:
        lines.append("  all assertions hold")
    for w in warnings:
        lines.append(f"  [note] {w}")
    lines.append("")

    lines.append("CROSS-CHECKS (cached value vs independent live source)")
    lines.append("-" * 60)
    if not cross:
        lines.append("  none applicable (source layers retired)")
    for c in cross:
        ok = "OK" if c.get("ok") else "DIVERGE"
        if "cached" in c:
            lines.append(f"  [{ok:7}] {c['label']:32} cached={c['cached']:>10} "
                         f"external={c['external']:>10} delta={c['divergence']}")
        else:
            lines.append(f"  [{ok:7}] {c['label']:32} {c.get('note', '')}")
    lines.append("")

    lines.append("CONTEXT")
    lines.append("-" * 60)
    for i in info:
        lines.append(f"  {i}")
    lines.append("")

    lines.append("Live site: https://worldtwin.duckdns.org/worldtwin/")
    lines.append("Generated by /home/opc/worldtwin/scripts/nightly_audit.py")
    return subject, "\n".join(lines)


# ---- Gmail API send ----

def gmail_send(subject: str, body: str) -> bool:
    """Send email via Gmail API using a stored OAuth refresh token.

    .gmail_oauth.json shape:
      { "client_id": "...", "client_secret": "...",
        "refresh_token": "...", "user_email": "..." }
    """
    if not OAUTH_PATH.exists():
        print(f"[audit] no OAuth config at {OAUTH_PATH} — printing report only")
        return False
    try:
        cfg = json.loads(OAUTH_PATH.read_text())
    except Exception as e:
        print(f"[audit] cannot read OAuth config: {e}")
        return False

    # Mint access token
    tok_resp = http_post_form("https://oauth2.googleapis.com/token", {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": cfg["refresh_token"],
        "grant_type": "refresh_token",
    })
    if not tok_resp or "access_token" not in tok_resp:
        print(f"[audit] failed to mint access token: {tok_resp}")
        return False
    access = tok_resp["access_token"]

    # Build RFC822 message
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = cfg.get("user_email", "")
    msg["To"] = TO_ADDR
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    # Send via Gmail API
    status, resp = http_post_json(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        {"raw": raw},
        headers={"Authorization": f"Bearer {access}"},
    )
    if status == 200:
        msg_id = resp.get("id") if isinstance(resp, dict) else "?"
        print(f"[audit] Gmail send OK · message_id={msg_id}")
        return True
    print(f"[audit] Gmail send failed · http={status} · {str(resp)[:300]}")
    return False


def main() -> int:
    print(f"[audit] starting at {datetime.now(timezone.utc).isoformat()}")
    counts, failures, warnings, info = run_assertions()
    cross = cross_checks()
    subject, body = render_report(counts, failures, warnings, info, cross)
    print(body)
    print("")
    sent = gmail_send(subject, body)
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
