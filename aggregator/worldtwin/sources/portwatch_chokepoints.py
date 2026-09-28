"""IMF PortWatch — live shipping chokepoint data.

CC-BY, no auth, refreshed weekly by IMF from AIS feeds (~90k ships).
28 chokepoints with daily vessel-type breakdown.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

# Approximate centroids of the 28 PortWatch chokepoints (for map rendering).
# 2026-09-28 name audit against the upstream ArcGIS layer
# (returnDistinctValues on `portname`, exactly 28 values): dropped 7 names
# that do not exist upstream (La Perouse Strait, Cook Strait, Bass Strait,
# Florida Strait, Skagerrak, Oresund, English Channel — Dover Strait already
# covers the Channel), added the 7 real ones that were silently dropped
# (Balabac, Bering, Bohai, Kerch, Magellan, Mindoro, Oresund Strait).
CHOKEPOINT_COORDS = {
    "Suez Canal":                   (30.07, 32.55),
    "Panama Canal":                 (9.08, -79.68),
    "Strait of Hormuz":             (26.57, 56.25),
    "Bab el-Mandeb Strait":         (12.58, 43.33),
    "Malacca Strait":               (2.75, 101.50),
    "Bosporus Strait":              (41.12, 29.07),
    "Dover Strait":                 (51.04, 1.44),
    "Gibraltar Strait":             (35.96, -5.50),
    "Cape of Good Hope":            (-34.36, 18.47),
    "Sunda Strait":                 (-6.00, 105.80),
    "Lombok Strait":                (-8.70, 115.75),
    "Ombai Strait":                 (-8.50, 125.00),
    "Makassar Strait":              (-3.00, 118.00),
    "Luzon Strait":                 (20.50, 121.00),
    "Taiwan Strait":                (24.50, 119.00),
    "Korea Strait":                 (34.50, 129.00),
    "Tsugaru Strait":               (41.50, 140.50),
    "Torres Strait":                (-10.50, 142.50),
    "Yucatan Channel":              (21.60, -85.50),
    "Windward Passage":             (20.00, -73.80),
    "Mona Passage":                 (18.30, -67.80),
    "Oresund Strait":               (55.70, 12.80),
    "Balabac Strait":               (7.60, 116.95),
    "Bering Strait":                (65.75, -168.95),
    "Bohai Strait":                 (38.35, 121.10),
    "Kerch Strait":                 (45.25, 36.55),
    "Magellan Strait":              (-53.50, -70.90),
    "Mindoro Strait":               (12.70, 120.50),
}


LAYER = LayerMeta(
    id="portwatch_chokepoints",
    name="PortWatch Chokepoints (IMF/AIS)",
    category="resources",
    kind="points",
    source="IMF PortWatch (derived from AIS)",
    source_url="https://portwatch.imf.org/",
    license="IMF ToU",
    refresh_s=86400,  # daily
    initial_delay_s=50,
    max_staleness_s=7 * 86400,  # IMF refreshes weekly from AIS
    units="ships / DWT",
    description=(
        "28 global shipping chokepoints with daily vessel-type breakdowns "
        "(container / dry_bulk / general_cargo / roro / tanker / cargo). "
        "AIS-derived by the IMF Research Department. Ships and DWT capacity."
    ),
    requires_key=False,
    enabled=True,
)


async def fetch(client: httpx.AsyncClient):
    try:
        # ONE page of 1000, newest first. page_size 1000 per MASTER_PLAN §4
        # (asking for 2000 made the server return a silently truncated 752).
        # Measured 2026-09-28: at 1000 the upstream pagination actually
        # WORKS, and the old 50-iteration loop pulled 50 pages = 50,000 rows
        # per daily fetch. One page = the latest ~35 days across all 28
        # chokepoints — the whole point of this layer is the latest day, and
        # a single page keeps it the best info-per-byte layer (~12 KB gz).
        page_size = 1000
        r = await client.get(
            "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "orderByFields": "date DESC",
                "resultRecordCount": page_size,
                "f": "json",
            },
            timeout=90,
        )
        if r.status_code != 200:
            return None
        all_feats = r.json().get("features", [])
        if not all_feats:
            return None

        # `date` arrives as an ISO 'YYYY-MM-DD' string (not epoch ms);
        # lexicographic max is chronological. `or ""` guards mixed-type max.
        latest_date_ms = max(f["attributes"].get("date") or "" for f in all_feats)
        latest_rows = [f["attributes"] for f in all_feats if f["attributes"].get("date") == latest_date_ms]

        chokepoints: list[dict[str, Any]] = []
        for row in latest_rows:
            port = row.get("portname", "")
            coords = CHOKEPOINT_COORDS.get(port)
            if not coords:
                continue
            lat, lon = coords
            chokepoints.append({
                "name": port,
                "lat": lat,
                "lon": lon,
                "date_ms": row.get("date"),
                "n_total": row.get("n_total", 0),
                "n_container": row.get("n_container", 0),
                "n_dry_bulk": row.get("n_dry_bulk", 0),
                "n_general_cargo": row.get("n_general_cargo", 0),
                "n_roro": row.get("n_roro", 0),
                "n_tanker": row.get("n_tanker", 0),
                "n_cargo": row.get("n_cargo", 0),
                "capacity": row.get("capacity", 0),
                "capacity_container": row.get("capacity_container", 0),
                "capacity_dry_bulk": row.get("capacity_dry_bulk", 0),
                "capacity_tanker": row.get("capacity_tanker", 0),
                "capacity_general_cargo": row.get("capacity_general_cargo", 0),
                "capacity_roro": row.get("capacity_roro", 0),
            })

        chokepoints.sort(key=lambda x: x.get("capacity", 0), reverse=True)

        # Full historical record for the History Store
        history_records = []
        for f in all_feats:
            a = f["attributes"]
            port = a.get("portname", "")
            coords = CHOKEPOINT_COORDS.get(port)
            if not coords:
                continue
            lat, lon = coords
            history_records.append({
                "name": port,
                "lat": lat, "lon": lon,
                "date": a.get("date"),
                "n_total": a.get("n_total", 0),
                "n_tanker": a.get("n_tanker", 0),
                "n_container": a.get("n_container", 0),
                "capacity": a.get("capacity", 0),
            })

        payload = {
            "source": "IMF PortWatch",
            "latest_date_ms": latest_date_ms,
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(chokepoints),
            "chokepoints": chokepoints,
            "chokepoints_full": history_records,
            "chokepoints_full_count": len(history_records),
        }
        return payload
    except Exception as e:
        print(f"[portwatch_chokepoints] error: {e}")
        return None


register(LAYER, fetch)
