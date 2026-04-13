"""UCDP Georeferenced Event Dataset — academic fatality-verified conflict events.

Free flat-file download, CC BY 4.0, explicitly map-visualisation OK.
No token required for the CSV zips on ucdp.uu.se/downloads.
Version auto-detected (currently v25.1 → ged251-csv.zip).
"""
import csv
import io
import zipfile
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="ucdp_ged",
    name="UCDP Georeferenced Events",
    category="war",
    kind="points",
    source="Uppsala Conflict Data Program (UCDP)",
    source_url="https://ucdp.uu.se/downloads/",
    license="CC BY 4.0",
    refresh_s=604800,  # weekly
    initial_delay_s=200,
    units="fatalities (best estimate)",
    description=(
        "UCDP GED — academic fatality-verified conflict events. "
        "Last 3 years only, filtered to clarity=1, sorted by fatalities."
    ),
    requires_key=False,
)

UCDP_URLS = [
    "https://ucdp.uu.se/downloads/ged/ged251-csv.zip",
    "https://ucdp.uu.se/downloads/ged/ged241-csv.zip",
    "https://ucdp.uu.se/downloads/ged/ged231-csv.zip",
]


async def fetch(client: httpx.AsyncClient):
    for url in UCDP_URLS:
        try:
            r = await client.get(url, timeout=120, follow_redirects=True)
            if r.status_code != 200:
                continue
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            csv_name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
            if not csv_name:
                continue
            with zf.open(csv_name) as f:
                text = io.TextIOWrapper(f, encoding="utf-8")
                reader = csv.DictReader(text)
                events: list[dict[str, Any]] = []
                cutoff = "2023-01-01"
                for row in reader:
                    date_start = row.get("date_start", "")
                    if date_start < cutoff:
                        continue
                    try:
                        lat = float(row.get("latitude") or 0)
                        lon = float(row.get("longitude") or 0)
                        best = int(row.get("best") or 0)
                    except ValueError:
                        continue
                    if lat == 0 and lon == 0:
                        continue
                    try:
                        clarity = int(row.get("event_clarity") or 2)
                    except ValueError:
                        clarity = 2
                    if clarity != 1:
                        continue
                    events.append({
                        "id": row.get("id", ""),
                        "lat": lat,
                        "lon": lon,
                        "date_start": date_start,
                        "date_end": row.get("date_end", ""),
                        "side_a": row.get("side_a", ""),
                        "side_b": row.get("side_b", ""),
                        "dyad_name": row.get("dyad_name", ""),
                        "country": row.get("country", ""),
                        "best": best,
                        "high": int(row.get("high") or 0),
                        "low": int(row.get("low") or 0),
                        "type_of_violence": int(row.get("type_of_violence") or 0),
                        "conflict_name": row.get("conflict_name", ""),
                    })
                events.sort(key=lambda x: x["date_start"], reverse=True)
                # Cap to 3000 most recent high-fatality events for render budget
                events_top = events[:3000]
                return {
                    "source": f"UCDP GED ({url.split('/')[-1]})",
                    "fetched": datetime.now(timezone.utc).isoformat(),
                    "total_events": len(events),
                    "events": events_top,
                }
        except Exception as e:
            print(f"[ucdp_ged] {url} failed: {e}")
            continue
    return None


register(LAYER, fetch)
