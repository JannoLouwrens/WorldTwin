"""Dartmouth Flood Observatory — global flood event archive.

Free, public. Every flood event since 1985 with polygons, cause, deaths.
We keep the last 90 days.
"""
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="dartmouth_floods",
    name="Dartmouth Flood Observatory — Recent Events",
    category="nature",
    kind="points",
    source="Dartmouth Flood Observatory",
    source_url="https://floodobservatory.colorado.edu/",
    license="Free with attribution",
    refresh_s=86400,
    initial_delay_s=30,
    description="Global flood events from the last 90 days with location, cause, deaths, and severity.",
    requires_key=False,
    enabled=False,  # 2026-04-25 disabled: upstream URL returns 404 consistently. Re-enable when Dartmouth restores feed.
)


async def fetch(client: httpx.AsyncClient):
    # Try CSV direct; fall back gracefully
    urls = [
        "https://floodobservatory.colorado.edu/temp/FloodArchive.txt",
        "https://floodobservatory.colorado.edu/temp/MasterListrev.htm",
    ]
    for url in urls:
        try:
            r = await client.get(url, timeout=60, headers={"User-Agent": "WorldTwin/1.0"})
            if r.status_code != 200:
                continue
            text = r.text
            # The DFO txt file is tab-separated
            reader = csv.DictReader(io.StringIO(text), delimiter="\t")
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
            events = []
            for row in reader:
                began = row.get("Began", "") or row.get("began", "")
                if began and began < cutoff:
                    continue
                try:
                    lat = float(row.get("lat") or row.get("LAT") or 0)
                    lon = float(row.get("long") or row.get("LONG") or 0)
                except ValueError:
                    continue
                if lat == 0 and lon == 0:
                    continue
                try:
                    deaths = int(float(row.get("Dead") or 0))
                except ValueError:
                    deaths = 0
                sev = 1
                if deaths > 100: sev = 5
                elif deaths > 20: sev = 4
                elif deaths > 5: sev = 3
                elif deaths > 0: sev = 2
                events.append({
                    "id": row.get("ID") or row.get("Register#", ""),
                    "name": row.get("Country", "") + " " + began,
                    "country": row.get("Country", ""),
                    "began": began,
                    "ended": row.get("Ended", "") or row.get("ended", ""),
                    "lat": lat,
                    "lon": lon,
                    "deaths": deaths,
                    "cause": row.get("Main cause", "") or row.get("cause", ""),
                    "severity": sev,
                })
            return {
                "source": "Dartmouth Flood Observatory",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": len(events),
                "events": events,
            }
        except Exception as e:
            print(f"[dartmouth_floods] {url} error: {e}")
            continue
    return None


register(LAYER, fetch)
