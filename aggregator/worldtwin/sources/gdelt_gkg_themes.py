"""GDELT GKG 2.1 themes — anomaly detection per country per theme.

Downloads the most recent GKG 15-min file, parses V2Themes + V2Locations,
counts theme-country co-occurrences over the last hour, and surfaces
the top anomalies as a "themed pulses" layer.
"""
import asyncio
import csv
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="gdelt_gkg_themes",
    name="GDELT GKG Themes (last hour)",
    category="social",
    kind="points",
    source="GDELT Global Knowledge Graph 2.1",
    source_url="http://data.gdeltproject.org/gdeltv2/",
    license="CC BY 4.0",
    refresh_s=900,  # 15 min — matches GDELT cadence
    initial_delay_s=120,
    description=(
        "Top themed anomalies per country over the last ~hour, derived "
        "from GDELT GKG 2.1 V2Themes + V2Locations. Catches stories "
        "the Events table misses."
    ),
    requires_key=False,
)

# Whitelist the themes we care about surfacing on the globe
INTERESTING_THEMES = {
    "KILL", "WOUND", "TERROR", "ARMEDCONFLICT", "ARREST",
    "PROTEST", "STRIKE", "RIOT",
    "REFUGEES", "DISPLACED", "HUMAN_RIGHTS",
    "NATURAL_DISASTER", "EARTHQUAKE", "FLOOD", "DROUGHT", "WILDFIRE",
    "HURRICANE", "CYCLONE", "TYPHOON", "TSUNAMI",
    "EPIDEMIC", "DISEASE", "MEDICAL_*",
    "ECON_BANKRUPTCY", "ECON_INFLATION", "ECON_MONETARY", "ECON_WORLDCURRENCIES",
    "ENV_CLIMATECHANGE", "ENV_OILSPILL", "ENV_POLLUTION",
    "MILITARY", "CRIME",
    "ELECTION", "COUP",
    "CYBER_ATTACK",
}


def _theme_interesting(t: str) -> bool:
    if t in INTERESTING_THEMES:
        return True
    for prefix in ("CRISISLEX_", "MILITARY_", "MEDICAL_", "ECON_", "ENV_", "TERROR"):
        if t.startswith(prefix):
            return True
    return False


async def _latest_gkg_url(client: httpx.AsyncClient) -> str:
    try:
        r = await client.get("http://data.gdeltproject.org/gdeltv2/lastupdate.txt", timeout=30)
        if r.status_code != 200:
            return ""
        for line in r.text.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3 and "gkg.csv.zip" in parts[2]:
                return parts[2]
    except Exception:
        pass
    return ""


async def fetch(client: httpx.AsyncClient):
    url = await _latest_gkg_url(client)
    if not url:
        return None
    try:
        r = await client.get(url, timeout=120)
        if r.status_code != 200:
            return None
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
        if not name:
            return None
        with zf.open(name) as f:
            text = io.TextIOWrapper(f, encoding="utf-8", errors="ignore")
            # GKG is tab-separated, no header row
            reader = csv.reader(text, delimiter="\t")

            country_theme_counts: dict[tuple, dict[str, Any]] = {}
            theme_country_mentions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

            for row in reader:
                if len(row) < 20:
                    continue
                try:
                    themes_field = row[7] if len(row) > 7 else ""
                    locations_field = row[9] if len(row) > 9 else ""
                    tone_field = row[15] if len(row) > 15 else ""
                    doc_id = row[4] if len(row) > 4 else ""
                    img = row[18] if len(row) > 18 else ""
                except IndexError:
                    continue
                if not themes_field or not locations_field:
                    continue

                # Parse themes (semicolon separated, may include offset as "THEME,offset")
                theme_set = set()
                for t in themes_field.split(";"):
                    t = t.strip().split(",")[0]
                    if t and _theme_interesting(t):
                        theme_set.add(t)
                if not theme_set:
                    continue

                # Parse locations — format: Type#FullName#CountryCode#ADM1#Lat#Lon#FeatureID
                for loc in locations_field.split(";"):
                    parts = loc.split("#")
                    if len(parts) < 6:
                        continue
                    try:
                        loc_type = int(parts[0]) if parts[0] else 0
                        cc = parts[2] if parts[2] else ""
                        lat = float(parts[4]) if parts[4] else 0
                        lon = float(parts[5]) if parts[5] else 0
                    except ValueError:
                        continue
                    if not cc or (lat == 0 and lon == 0):
                        continue
                    for theme in theme_set:
                        theme_country_mentions[theme][cc] += 1
                        key = (theme, cc)
                        rec = country_theme_counts.setdefault(key, {
                            "theme": theme,
                            "country_code": cc,
                            "count": 0,
                            "lat_sum": 0,
                            "lon_sum": 0,
                            "sample_url": "",
                            "sample_img": "",
                        })
                        rec["count"] += 1
                        rec["lat_sum"] += lat
                        rec["lon_sum"] += lon
                        if not rec["sample_url"] and doc_id:
                            rec["sample_url"] = doc_id
                        if not rec["sample_img"] and img and img != "":
                            rec["sample_img"] = img

            # Build top anomalies: per (theme, country) need count >= 5
            pulses = []
            for (theme, cc), rec in country_theme_counts.items():
                if rec["count"] < 5:
                    continue
                n = rec["count"]
                pulses.append({
                    "theme": theme,
                    "country": cc,
                    "count": n,
                    "lat": rec["lat_sum"] / n,
                    "lon": rec["lon_sum"] / n,
                    "sample_url": rec["sample_url"],
                    "sample_img": rec["sample_img"],
                })
            pulses.sort(key=lambda x: x["count"], reverse=True)

            return {
                "source": "GDELT GKG 2.1",
                "file": url,
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": len(pulses),
                "pulses": pulses[:300],
                "pulses_full": pulses,    # full set for History Store
            }
    except Exception as e:
        print(f"[gdelt_gkg_themes] error: {e}")
        return None


register(LAYER, fetch)
