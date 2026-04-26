"""GDELT violent events — real-time conflict event markers.

Extracts events from GDELT with CAMEO EventRootCode 18, 19, 20:
  18 = Assault (attack, abduction, sexual violence)
  19 = Fight (fight with weapons, attack with conventional force)
  20 = Use unconventional mass violence (massacre, mass killing)

Each event has ActionGeo_Lat/Long which is the geocoded location from
the news article text. No fatality counts (GDELT doesn't provide them)
but has: actor names, event type, mention count, average tone, source URL.

This is the free, real-time, no-auth answer to "where are violent events
happening RIGHT NOW". It's less verified than ACLED/UCDP but updates
every 15 minutes and needs no credentials.

When ACLED or UCDP credentials are added, those sources will complement
this with fatality counts and verified attribution.
"""
import asyncio
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="conflict_events",
    name="Violent Events (GDELT real-time)",
    category="war",
    kind="points",
    source="GDELT Events 2.0 (EventRootCode 18/19/20)",
    source_url="http://data.gdeltproject.org/gdeltv2/",
    license="Free (GDELT)",
    refresh_s=1800,             # every 30 min (enough for news-paced data)
    initial_delay_s=75,          # avoid hitting GDELT the moment relations worker starts
    units="event (count)",
    description=(
        "Real-time violent event markers extracted from GDELT Events 2.0. "
        "Includes assaults, armed fights, and mass violence incidents with "
        "geocoded coordinates. Updates every 30 minutes. "
        "Source URLs point to the original news article."
    ),
)

# GDELT publishes every 15 minutes
FILES_PER_HOUR = 4
HOURS_TO_FETCH = 12            # last 12h of violent events (fewer than relations worker)

# Column indices in GDELT Events 2.0
# GDELT 2.0 Events column indices — verified against the official schema at
# https://raw.githubusercontent.com/linwoodc3/gdelt2HeaderRows/master/schema_csvs/GDELT_2.0_Events_Column_Labels_Header_Row_Sep2016.csv
# (Previously these were wrong: COL_ACTIONGEO_LAT was pointing at
# Actor1Geo_Lat (40) and COL_SOURCE_URL was pointing at ActionGeo_Long (57),
# so every "Read article" link in the popup was actually a longitude value.)
COL_GLOBAL_EVENT_ID = 0
COL_SQLDATE = 1
COL_ACTOR1_NAME = 6
COL_ACTOR1_COUNTRY = 7
COL_ACTOR2_NAME = 16
COL_ACTOR2_COUNTRY = 17
COL_EVENT_CODE = 26
COL_EVENT_BASE_CODE = 27
COL_EVENT_ROOT_CODE = 28
COL_QUAD_CLASS = 29
COL_GOLDSTEIN = 30
COL_NUM_MENTIONS = 31
COL_AVG_TONE = 34
COL_ACTIONGEO_LAT = 56
COL_ACTIONGEO_LONG = 57
COL_SOURCE_URL = 60

# Violent event root codes
VIOLENT_ROOT_CODES = {"18", "19", "20"}

# Sub-code → readable label
EVENT_LABELS = {
    "18":  "Assault",
    "180": "Assault",
    "181": "Abduction / hijack / hostage",
    "182": "Physical assault",
    "183": "Sexual assault",
    "184": "Torture",
    "185": "Kill by physical assault",
    "186": "Assassinate",
    "19":  "Fight",
    "190": "Fight",
    "191": "Impose blockade / restrict movement",
    "192": "Occupy territory",
    "193": "Fight with small arms",
    "194": "Fight with artillery / tanks",
    "195": "Aerial weapons / airstrike",
    "196": "Violate ceasefire",
    "20":  "Mass violence",
    "200": "Mass violence",
    "201": "Mass expulsion",
    "202": "Mass killing",
    "203": "Ethnic cleansing",
    "204": "Weapons of mass destruction",
}


def _generate_file_urls(hours: int) -> list[str]:
    urls = []
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    minute = (now.minute // 15) * 15
    now = now.replace(minute=minute) - timedelta(minutes=30)
    for i in range(hours * FILES_PER_HOUR):
        t = now - timedelta(minutes=15 * i)
        stamp = t.strftime("%Y%m%d%H%M%S")
        urls.append(f"http://data.gdeltproject.org/gdeltv2/{stamp}.export.CSV.zip")
    return urls


async def _download_and_parse(client: httpx.AsyncClient, url: str) -> list[dict]:
    try:
        r = await client.get(url, timeout=30)
        if r.status_code != 200:
            return []
        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                raw = f.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    events = []
    for line in raw.splitlines():
        cols = line.split("\t")
        if len(cols) < 61:  # need through SOURCEURL (col 60)
            continue
        root_code = cols[COL_EVENT_ROOT_CODE].strip()
        if root_code not in VIOLENT_ROOT_CODES:
            continue
        # Must have geocoded location
        try:
            lat = float(cols[COL_ACTIONGEO_LAT])
            lon = float(cols[COL_ACTIONGEO_LONG])
        except (ValueError, IndexError):
            continue
        if lat == 0.0 and lon == 0.0:
            continue
        try:
            mentions = int(cols[COL_NUM_MENTIONS])
            goldstein = float(cols[COL_GOLDSTEIN])
            tone = float(cols[COL_AVG_TONE])
        except (ValueError, IndexError):
            continue

        # Only keep meaningful events — require minimum mentions
        if mentions < 2:
            continue

        events.append({
            "id": cols[COL_GLOBAL_EVENT_ID],
            "date": cols[COL_SQLDATE],
            "actor1": cols[COL_ACTOR1_NAME].strip(),
            "actor1_country": cols[COL_ACTOR1_COUNTRY].strip(),
            "actor2": cols[COL_ACTOR2_NAME].strip(),
            "actor2_country": cols[COL_ACTOR2_COUNTRY].strip(),
            "event_code": cols[COL_EVENT_CODE].strip(),
            "root_code": root_code,
            "goldstein": goldstein,
            "mentions": mentions,
            "tone": tone,
            "lat": lat,
            "lon": lon,
            "source_url": cols[COL_SOURCE_URL].strip(),
        })
    return events


async def fetch(client: httpx.AsyncClient):
    urls = _generate_file_urls(HOURS_TO_FETCH)
    sem = asyncio.Semaphore(6)

    async def bounded(u):
        async with sem:
            return await _download_and_parse(client, u)

    results = await asyncio.gather(*[bounded(u) for u in urls])
    all_events = []
    for batch in results:
        all_events.extend(batch)

    if not all_events:
        return None

    # Deduplicate by lat/lon cluster (1 decimal ~11km) + event type + actor pair
    # GDELT often has the same underlying event reported by many outlets with slightly
    # different coordinates. We collapse them.
    clusters: dict[tuple, dict] = {}
    for ev in all_events:
        key = (
            round(ev["lat"], 1),
            round(ev["lon"], 1),
            ev["event_code"][:2],
            ev["actor1_country"],
            ev["actor2_country"],
        )
        cur = clusters.get(key)
        if cur is None or ev["mentions"] > cur["mentions"]:
            clusters[key] = ev
        # Also accumulate total mentions for the cluster
        if cur is not None:
            clusters[key]["_cluster_mentions"] = cur.get("_cluster_mentions", cur["mentions"]) + ev["mentions"]

    unique_events = list(clusters.values())

    # Sort by total mentions (importance)
    unique_events.sort(key=lambda e: -(e.get("_cluster_mentions", e["mentions"])))

    # History Store gets the full unique event set; UI renders top 1500
    unique_events_full = list(unique_events)
    unique_events = unique_events[:1500]

    # Build v1 points
    points_list = []
    for ev in unique_events:
        total_mentions = ev.get("_cluster_mentions", ev["mentions"])
        event_type = EVENT_LABELS.get(ev["event_code"], EVENT_LABELS.get(ev["root_code"], "Violent event"))
        # Size based on mention count (proxy for severity)
        severity = min(5, max(1, total_mentions // 20))
        # Format date as YYYY-MM-DD
        date_str = ev["date"]
        if len(date_str) == 8:
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        label_parts = [event_type]
        if ev["actor1"]:
            label_parts.append(ev["actor1"][:30])
        label = " · ".join(label_parts)

        popup_parts = []
        if ev["actor1"]:
            popup_parts.append(f"<b>{ev['actor1']}</b>")
        if ev["actor2"] and ev["actor2"] != ev["actor1"]:
            popup_parts.append(f"→ <b>{ev['actor2']}</b>")
        popup = " ".join(popup_parts) if popup_parts else event_type

        points_list.append(point(
            lat=ev["lat"],
            lon=ev["lon"],
            id=ev["id"],
            value=total_mentions,
            label=label,
            popup=popup,
            event_type=event_type,
            event_code=ev["event_code"],
            root_code=ev["root_code"],
            actor1=ev["actor1"],
            actor2=ev["actor2"],
            actor1_country=ev["actor1_country"],
            actor2_country=ev["actor2_country"],
            goldstein=ev["goldstein"],
            tone=ev["tone"],
            mentions=total_mentions,
            severity=severity,
            date=date_str,
            source_url=ev["source_url"],
        ))

    # Legacy: same structure (frontend can read directly).
    # events_full = the full clustered set so the History Store gets every
    # unique event, not just the top 1500.
    legacy = {
        "source": "GDELT Events 2.0",
        "window_hours": HOURS_TO_FETCH,
        "event_count": len(points_list),
        "events": points_list,
        "events_full": unique_events_full,
        "events_full_count": len(unique_events_full),
    }
    return points_list, legacy


register(LAYER, fetch)
