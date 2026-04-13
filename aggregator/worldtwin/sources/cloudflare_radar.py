"""Cloudflare Radar — internet outages, DDoS attacks, BGP changes.

Authenticated via CLOUDFLARE_RADAR_TOKEN (free Cloudflare API token with
Radar:Read permission). Rate limit ~1200 req/5min.
"""
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc

CLOUDFLARE_RADAR_TOKEN = os.environ.get("CLOUDFLARE_RADAR_TOKEN", "")


LAYER = LayerMeta(
    id="cloudflare_radar",
    name="Cloudflare Radar — Internet Health",
    category="infra",
    kind="points",
    source="Cloudflare Radar",
    source_url="https://radar.cloudflare.com/",
    license="Free with attribution",
    refresh_s=1800,
    initial_delay_s=150,
    description="Internet outages, DDoS attacks, and BGP route changes as seen by Cloudflare's global network.",
    requires_key=True,
    key_env="CLOUDFLARE_RADAR_TOKEN",
    enabled=bool(CLOUDFLARE_RADAR_TOKEN),
)

ISO2_TO_COORDS = None


def _build_iso_index():
    global ISO2_TO_COORDS
    if ISO2_TO_COORDS is not None:
        return
    # Curated ISO2 → lat/lon from _comtrade_common
    mapping = {
        "US": (39.50, -98.35), "CN": (35.86, 104.19), "IN": (20.59, 78.96),
        "RU": (61.52, 105.32), "BR": (-14.24, -51.93), "CA": (56.13, -106.35),
        "AU": (-25.27, 133.78), "DE": (51.17, 10.45), "FR": (46.23, 2.21),
        "GB": (55.38, -3.44), "JP": (36.20, 138.25), "KR": (35.91, 127.77),
        "IT": (41.87, 12.57), "ES": (40.46, -3.75), "PL": (51.92, 19.15),
        "TR": (38.96, 35.24), "MX": (23.63, -102.55), "ID": (-0.79, 113.92),
        "SA": (23.89, 45.08), "IR": (32.43, 53.69), "IQ": (33.22, 43.68),
        "ZA": (-30.56, 22.94), "EG": (26.82, 30.80), "NG": (9.08, 8.68),
        "ET": (9.15, 40.49), "KE": (-0.02, 37.91), "MA": (31.79, -7.09),
        "DZ": (28.03, 1.66), "AR": (-38.42, -63.62), "CL": (-35.68, -71.54),
        "PE": (-9.19, -75.02), "VE": (6.42, -66.59), "CO": (4.57, -74.30),
        "TH": (15.87, 100.99), "VN": (14.06, 108.28), "MY": (4.21, 101.98),
        "PH": (12.88, 121.77), "PK": (30.38, 69.35), "BD": (23.68, 90.36),
        "NL": (52.13, 5.29), "BE": (50.50, 4.47), "CH": (46.82, 8.23),
        "AT": (47.52, 14.55), "SE": (60.13, 18.64), "NO": (60.47, 8.47),
        "FI": (61.92, 25.75), "DK": (56.26, 9.50), "IE": (53.41, -8.24),
        "PT": (39.40, -8.22), "GR": (39.07, 21.82), "CZ": (49.82, 15.47),
        "HU": (47.16, 19.50), "RO": (45.94, 24.97), "BG": (42.73, 25.49),
        "UA": (48.38, 31.17), "AE": (23.42, 53.85), "IL": (31.05, 34.85),
        "SG": (1.35, 103.82), "NZ": (-40.90, 174.89), "TW": (23.70, 121.00),
        "HK": (22.30, 114.17), "YE": (15.55, 48.52), "SY": (34.80, 38.99),
        "LB": (33.85, 35.86), "JO": (30.59, 36.24), "AF": (33.93, 67.71),
        "MM": (21.91, 95.96), "KH": (12.57, 104.99), "LA": (19.85, 102.50),
        "KZ": (48.02, 66.92), "UZ": (41.38, 64.59), "LK": (7.87, 80.77),
        "NP": (28.39, 84.12), "CU": (21.52, -77.78), "HN": (15.20, -86.24),
        "GT": (15.78, -90.23), "SV": (13.79, -88.90), "CR": (9.75, -83.75),
        "PA": (8.54, -80.78), "UY": (-32.52, -55.77), "PY": (-23.44, -58.44),
        "BO": (-16.29, -63.59), "EC": (-1.83, -78.18), "DO": (18.74, -70.16),
    }
    ISO2_TO_COORDS = mapping


async def fetch(client: httpx.AsyncClient):
    if not CLOUDFLARE_RADAR_TOKEN:
        return None
    _build_iso_index()
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_RADAR_TOKEN}",
        "Content-Type": "application/json",
    }
    out = {
        "source": "Cloudflare Radar",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "outages": [],
    }
    try:
        r = await client.get(
            "https://api.cloudflare.com/client/v4/radar/annotations/outages",
            params={"dateRange": "7d", "limit": 50},
            timeout=30,
            headers=headers,
        )
        if r.status_code == 200:
            data = r.json()
            annotations = (data.get("result") or {}).get("annotations", [])
            outages = []
            for a in annotations:
                # Each annotation: { id, dataSource, description, scope,
                #                    startDate, endDate, locations[], asns[],
                #                    eventType, linkedUrl, asnsDetails[],
                #                    locationsDetails[], outage{ outageCause, ... } }
                locs = a.get("locationsDetails") or []
                if not locs:
                    continue
                loc = locs[0]
                iso2 = loc.get("code") or ""
                coords = ISO2_TO_COORDS.get(iso2)
                if not coords:
                    continue
                lat, lon = coords
                outage_info = a.get("outage") or {}
                asn_names = [ad.get("name", "") for ad in (a.get("asnsDetails") or [])[:3]]
                outages.append({
                    "id": a.get("id"),
                    "country_code": iso2,
                    "country_name": loc.get("name", ""),
                    "lat": lat,
                    "lon": lon,
                    "description": (a.get("description") or "")[:300],
                    "scope": a.get("scope", ""),
                    "start": a.get("startDate"),
                    "end": a.get("endDate"),
                    "event_type": a.get("eventType", ""),
                    "outage_cause": outage_info.get("outageCause", ""),
                    "outage_type": outage_info.get("outageType", ""),
                    "asns": asn_names,
                    "url": a.get("linkedUrl", ""),
                })
            out["outages"] = outages
            out["count"] = len(outages)
        else:
            out["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
            out["count"] = 0
    except Exception as e:
        out["error"] = str(e)
        out["count"] = 0

    # DDoS attacks — top attack targets last 24h
    try:
        r = await client.get(
            "https://api.cloudflare.com/client/v4/radar/attacks/layer3/top/locations/target",
            params={"dateRange": "1d", "limit": 10},
            timeout=30,
            headers=headers,
        )
        if r.status_code == 200:
            data = r.json()
            top = (data.get("result") or {}).get("top_0", [])
            ddos = []
            for t in top[:10]:
                iso2 = t.get("originCountryAlpha2") or t.get("targetCountryAlpha2", "")
                coords = ISO2_TO_COORDS.get(iso2)
                if not coords:
                    continue
                ddos.append({
                    "country_code": iso2,
                    "country_name": t.get("targetCountryName") or t.get("originCountryName", ""),
                    "lat": coords[0],
                    "lon": coords[1],
                    "value_pct": t.get("value", 0),
                })
            out["ddos_targets"] = ddos
    except Exception:
        pass

    return out


register(LAYER, fetch)

