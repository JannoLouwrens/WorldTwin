"""EIA-930 — Hourly US balancing authority generation, demand, interchange.

Covers CAISO, ERCOT, PJM, MISO, NYISO, ISO-NE plus 60 other US balancing
authorities. Hourly refresh. Shows live US grid state.
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

LAYER = LayerMeta(
    id="eia_930_grid",
    name="EIA-930 — US Balancing Authority Data",
    category="resources",
    kind="raw",
    source="US EIA Hourly Electric Grid Monitor",
    source_url="https://api.eia.gov/v2/electricity/rto/",
    license="US Public Domain",
    refresh_s=3600,
    initial_delay_s=205,
    description="Hourly generation/demand/interchange for every US balancing authority.",
    requires_key=True,
    key_env="EIA_API_KEY",
    enabled=bool(EIA_API_KEY),
)

# Curated BA centroids for map rendering
BA_CENTROIDS = {
    "CISO": (36.77, -119.42, "California ISO"),
    "ERCO": (31.00, -99.00, "ERCOT"),
    "PJM":  (39.95, -77.00, "PJM Interconnection"),
    "MISO": (41.50, -90.00, "Midcontinent ISO"),
    "NYIS": (42.75, -75.50, "New York ISO"),
    "ISNE": (42.50, -71.50, "ISO New England"),
    "SWPP": (37.80, -97.00, "Southwest Power Pool"),
    "BPAT": (45.50, -122.60, "Bonneville"),
    "TVA":  (35.55, -86.40, "Tennessee Valley"),
    "SOCO": (32.90, -84.50, "Southern Company"),
    "DUK":  (35.40, -80.50, "Duke Energy"),
    "FPC":  (28.50, -81.60, "Florida Power"),
    "AZPS": (33.45, -112.10, "Arizona Public Service"),
    "PACE": (41.10, -111.90, "PacifiCorp East"),
    "PSCO": (39.70, -104.80, "Public Service Colorado"),
}


async def fetch(client: httpx.AsyncClient):
    if not EIA_API_KEY:
        return None
    try:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=6)
        r = await client.get(
            "https://api.eia.gov/v2/electricity/rto/region-data/data/",
            params={
                "api_key": EIA_API_KEY,
                "frequency": "hourly",
                "data[0]": "value",
                "start": start.strftime("%Y-%m-%dT%H"),
                "end": end.strftime("%Y-%m-%dT%H"),
                "length": 5000,
                "sort[0][column]": "period",
                "sort[0][direction]": "desc",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[eia_930] {r.status_code}: {r.text[:120]}")
            return None
        body = r.json()
        rows = body.get("response", {}).get("data", []) or []

        # Each row: { period, respondent, respondent-name, type, value, value-units }
        # type = D (demand), NG (net generation), TI (total interchange), DF (forecast)
        by_ba: dict[str, dict[str, Any]] = {}
        for row in rows:
            ba = row.get("respondent", "")
            type_ = row.get("type", "")
            value = row.get("value")
            if not ba or value in (None, ""):
                continue
            rec = by_ba.setdefault(ba, {
                "ba": ba,
                "name": (BA_CENTROIDS.get(ba) or ("", 0, 0))[2] or row.get("respondent-name", ba),
                "lat": (BA_CENTROIDS.get(ba) or (0, 0, ""))[0],
                "lon": (BA_CENTROIDS.get(ba) or (0, 0, ""))[1],
                "latest_period": row.get("period", ""),
            })
            # Keep only the most recent value per type per BA
            cur_period = rec.get(f"{type_}_period", "")
            if row.get("period", "") >= cur_period:
                rec[type_] = value
                rec[f"{type_}_period"] = row.get("period", "")

        # Filter out BAs without centroids if we want map-renderable
        renderable = [b for b in by_ba.values() if b["lat"] != 0]

        return {
            "source": "EIA-930",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(renderable),
            "by_ba": by_ba,
            "renderable": renderable,
        }
    except Exception as e:
        print(f"[eia_930] error: {e}")
        return None


register(LAYER, fetch)
