#!/usr/bin/env python3
"""WorldTwin nightly Trust Tier audit — emailed via Gmail API.

Runs as a system cron on the aggregator server. Pulls every cache file
the dashboard depends on, scores each one as GREEN/YELLOW/RED based on
freshness, cross-checks a few values against authoritative independent
sources (Binance, USGS, NOAA, CoinGecko), validates the Council shape,
and emails a single report to jannolouwrens@gmail.com via the Gmail API.

OAuth2 refresh token lives in /home/opc/worldtwin/.gmail_oauth.json,
created once by gmail_oauth_setup.py. The script mints a short-lived
access token on every run and POSTs to gmail.googleapis.com.

No App Password, no SMTP — pure HTTPS.
"""
from __future__ import annotations
import base64
import json
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path

OAUTH_PATH = Path("/home/opc/worldtwin/.gmail_oauth.json")
CACHE_BASE = "http://127.0.0.1/api/cache"     # served by Caddy on the same host
USER_AGENT = "WorldTwin-NightlyAudit/1.0"
TO_ADDR = "jannolouwrens@gmail.com"
FROM_ADDR = None  # filled from oauth config (the account that consented)

CACHES = [
    ("gemini_narrative", "Council / Narrative"),
    ("fred", "FRED macros"),
    ("economy", "Crypto + forex"),
    ("pulse_mode", "Pulse composite"),
    ("quakes", "USGS quakes"),
    ("portwatch_chokepoints", "PortWatch chokepoints"),
    ("gdacs_events", "GDACS hazards"),
    ("ucdp_ged", "UCDP-GED conflict"),
    ("nhc_cyclones", "NHC cyclones"),
    ("noaa_co2", "NOAA CO2"),
    ("paleo_temperature", "Paleo temperature"),
    ("imf_data", "IMF country data"),
    ("world_bank", "World Bank WDI"),
    ("country_relations", "Country relations"),
    ("vdem_democracy", "V-Dem democracy"),
    ("trade_annual", "Trade flows"),
    ("who_don", "WHO outbreaks"),
    ("country_resources", "Country resources"),
]

# ---- HTTP helpers ----

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


# ---- Audit logic ----

def hours_since(iso_ts: str) -> float | None:
    if not iso_ts:
        return None
    try:
        ts = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def tier_for(hours: float | None) -> str:
    if hours is None:
        return "RED"
    if hours < 6:
        return "GREEN"
    if hours < 48:
        return "YELLOW"
    return "RED"


def audit_caches() -> list[dict]:
    rows = []
    for cid, name in CACHES:
        data = http_json(f"{CACHE_BASE}/{cid}.json")
        if data is None:
            rows.append({"id": cid, "name": name, "tier": "RED",
                         "hours": None, "note": "fetch failed"})
            continue
        h = hours_since(data.get("fetched"))
        rows.append({
            "id": cid, "name": name, "tier": tier_for(h),
            "hours": h, "fetched": data.get("fetched"),
            "note": "" if h is not None else "no fetched timestamp",
        })
    return rows


def audit_council() -> dict:
    data = http_json(f"{CACHE_BASE}/gemini_narrative.json") or {}
    council = data.get("council")
    if not isinstance(council, dict):
        return {"present": False, "note": "council field missing or null"}
    out = {"present": True, "synthesized": bool(council.get("_synthesized")),
           "voices": {}, "warnings": []}
    for v in ("general", "treasurer", "augur"):
        body = council.get(v) or {}
        cites = body.get("citations") or []
        valid = []
        for c in cites:
            if isinstance(c, dict) and all(c.get(k) for k in
                    ("label", "value", "source", "digest_path", "data_date")):
                valid.append(c)
        out["voices"][v] = {
            "headline": body.get("headline", ""),
            "cite_count": len(cites),
            "valid_cite_count": len(valid),
        }
        if not body.get("reading"):
            out["warnings"].append(f"{v}: empty reading")
        if len(valid) < len(cites):
            out["warnings"].append(f"{v}: {len(cites) - len(valid)} citation(s) missing required fields")
    return out


def audit_crosschecks() -> list[dict]:
    results = []

    eco = http_json(f"{CACHE_BASE}/economy.json") or {}
    cached_btc = next((c for c in (eco.get("crypto") or [])
                       if (c.get("symbol") or "").lower() == "btc"), None)
    cached_price = cached_btc.get("price_usd") if cached_btc else None

    bin_data = http_json("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
    bin_price = float(bin_data["lastPrice"]) if bin_data and bin_data.get("lastPrice") else None

    cg_data = http_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
    cg_price = (cg_data or {}).get("bitcoin", {}).get("usd")

    if cached_price and bin_price:
        div = abs(cached_price - bin_price) / bin_price * 100
        results.append({"label": "BTC USD vs Binance",
                        "cached": f"${cached_price:,.0f}", "external": f"${bin_price:,.0f}",
                        "divergence": f"{div:.2f}%", "ok": div < 2.0})
    else:
        results.append({"label": "BTC USD vs Binance", "ok": False,
                        "note": f"cached={cached_price} binance={bin_price}"})

    if cached_price and cg_price:
        div = abs(cached_price - cg_price) / cg_price * 100
        results.append({"label": "BTC USD vs CoinGecko",
                        "cached": f"${cached_price:,.0f}", "external": f"${cg_price:,.0f}",
                        "divergence": f"{div:.2f}%", "ok": div < 2.0})

    usgs = http_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
    usgs_count = len((usgs or {}).get("features") or [])
    cached_quakes = http_json(f"{CACHE_BASE}/quakes.json") or {}
    cached_45 = [f for f in (cached_quakes.get("features") or [])
                 if (f.get("properties", {}).get("mag") or 0) >= 4.5]
    delta = abs(usgs_count - len(cached_45))
    results.append({"label": "USGS quakes M4.5+ past day",
                    "cached": str(len(cached_45)), "external": str(usgs_count),
                    "divergence": f"{delta} events", "ok": delta <= 5})

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
    cached_co2 = http_json(f"{CACHE_BASE}/noaa_co2.json") or {}
    cached_ppm = (cached_co2.get("headline") or {}).get("current_co2_ppm")
    if last_ppm and cached_ppm:
        div = abs(last_ppm - cached_ppm)
        results.append({"label": "NOAA CO2 ppm vs Mauna Loa CSV",
                        "cached": f"{cached_ppm:.2f}", "external": f"{last_ppm:.2f}",
                        "divergence": f"{div:.2f} ppm", "ok": div < 1.0})
    else:
        results.append({"label": "NOAA CO2 ppm", "ok": False,
                        "note": f"cached={cached_ppm} external={last_ppm}"})

    return results


def render_report(cache_rows: list[dict], council: dict, cross: list[dict]) -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    g = sum(1 for r in cache_rows if r["tier"] == "GREEN")
    y = sum(1 for r in cache_rows if r["tier"] == "YELLOW")
    rd = sum(1 for r in cache_rows if r["tier"] == "RED")
    n = len(cache_rows)

    cross_failures = [c for c in cross if not c.get("ok")]
    council_problem = (not council.get("present")) or council.get("warnings")

    if rd == 0 and not cross_failures and not council_problem:
        subject = f"WorldTwin audit {today}: ALL GREEN ({g}/{n})"
    elif rd > 0 or cross_failures or not council.get("present"):
        subject = f"WorldTwin audit {today}: {rd} RED · {y} YELLOW · {g} GREEN"
    else:
        subject = f"WorldTwin audit {today}: {y} YELLOW · {g} GREEN"

    lines = [f"WorldTwin Trust Tier Audit — {today} UTC", "=" * 60, "",
             f"SUMMARY: {g} GREEN · {y} YELLOW · {rd} RED · {n} total caches", ""]
    lines.append("CACHE FRESHNESS")
    lines.append("-" * 60)
    for r in cache_rows:
        h = r.get("hours")
        h_str = f"{h:5.1f}h" if h is not None else "  ----"
        note = f"  ({r['note']})" if r.get("note") else ""
        lines.append(f"  [{r['tier']:6}] {r['name']:30} {h_str}{note}")
    lines.append("")

    lines.append("COUNCIL SHAPE")
    lines.append("-" * 60)
    if not council.get("present"):
        lines.append("  RED — council field missing or null")
    else:
        lines.append(f"  Present · synthesized={council.get('synthesized')}")
        for v, info in (council.get("voices") or {}).items():
            lines.append(f"    {v:10} · {info['valid_cite_count']}/{info['cite_count']} valid citations · {info['headline'][:55]}")
        for w in council.get("warnings") or []:
            lines.append(f"  WARN: {w}")
    lines.append("")

    lines.append("CROSS-CHECKS (cache value vs independent live source)")
    lines.append("-" * 60)
    for c in cross:
        ok = "OK" if c.get("ok") else "DIVERGE"
        if "cached" in c:
            lines.append(f"  [{ok:7}] {c['label']:32} cached={c['cached']:>10} external={c['external']:>10} delta={c['divergence']}")
        else:
            lines.append(f"  [{ok:7}] {c['label']:32} {c.get('note', '')}")
    lines.append("")

    lines.append(f"Live dashboard: http://129.151.191.74/weather/")
    lines.append(f"Generated by /home/opc/worldtwin/scripts/nightly_audit.py")
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
    cache_rows = audit_caches()
    council = audit_council()
    cross = audit_crosschecks()
    subject, body = render_report(cache_rows, council, cross)
    print(body)
    print("")
    sent = gmail_send(subject, body)
    return 0 if sent else 1


if __name__ == "__main__":
    sys.exit(main())
