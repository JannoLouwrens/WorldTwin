"""EIA Petroleum — US weekly oil stocks + SPR drawdown + refinery utilization.

Weekly dataset, usually published Wed 10:30 ET. Shows US oil inventory
health as a macro signal.
"""
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

EIA_API_KEY = os.environ.get("EIA_API_KEY", "")

LAYER = LayerMeta(
    id="eia_petroleum",
    name="EIA Petroleum — Weekly US Stocks",
    category="economy",
    kind="raw",
    source="US EIA Weekly Petroleum Status",
    source_url="https://api.eia.gov/v2/petroleum/",
    license="US Public Domain",
    refresh_s=86400,
    initial_delay_s=225,
    description="US crude oil stocks, SPR level, gasoline/distillate stocks, refinery utilization.",
    requires_key=True,
    key_env="EIA_API_KEY",
    enabled=bool(EIA_API_KEY),
)

# EIA petroleum series IDs for the weekly dataset
SERIES = [
    ("crude_stocks_mbbl",         "PET.WCESTUS1.W"),  # Weekly US Commercial Crude Oil Ending Stocks
    ("spr_stocks_mbbl",           "PET.WCSSTUS1.W"),  # Strategic Petroleum Reserve
    ("gasoline_stocks_mbbl",      "PET.WGTSTUS1.W"),  # Motor gasoline
    ("distillate_stocks_mbbl",    "PET.WDISTUS1.W"),  # Distillate fuel oil
    ("refinery_utilization_pct",  "PET.WPULEUS3.W"),  # Percent utilisation
]


async def fetch(client: httpx.AsyncClient):
    if not EIA_API_KEY:
        return None
    latest = {}
    history: dict[str, list] = {}
    for name, series_id in SERIES:
        try:
            r = await client.get(
                "https://api.eia.gov/v2/seriesid/" + series_id,
                params={"api_key": EIA_API_KEY},
                timeout=45,
            )
            if r.status_code != 200:
                # Fall back to the data endpoint
                parts = series_id.split(".")
                r = await client.get(
                    "https://api.eia.gov/v2/petroleum/stoc/wstk/data/",
                    params={
                        "api_key": EIA_API_KEY,
                        "frequency": "weekly",
                        "data[0]": "value",
                        "length": 5000,         # widened — full available series
                        "sort[0][column]": "period",
                        "sort[0][direction]": "desc",
                    },
                    timeout=120,
                )
                if r.status_code != 200:
                    continue
            data = r.json().get("response", {}).get("data", [])
            if not data:
                continue
            # Data is sorted desc — latest is first
            latest[name] = {"value": data[0].get("value"), "period": data[0].get("period", "")}
            # Full series — was capped at 12 samples; now keep everything
            history[name] = [{"t": d.get("period"), "v": d.get("value")} for d in data]
        except Exception as e:
            print(f"[eia_petroleum] {name} error: {e}")

    return {
        "source": "EIA Petroleum",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(latest),
        "latest": latest,
        "history": history,
    }


register(LAYER, fetch)
