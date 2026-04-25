"""IMF DataMapper — WEO forecasts and key fiscal/BOP indicators.

Free, no key. 6 core indicators covering the full IMF member list.
"""
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="imf_data",
    name="IMF DataMapper — Core Indicators",
    category="economy",
    kind="raw",
    source="IMF DataMapper API",
    source_url="https://www.imf.org/external/datamapper/api/v1/",
    license="Free with attribution",
    refresh_s=86400 * 7,
    initial_delay_s=285,
    description="IMF WEO forecasts: GDP per capita PPP, inflation, current account, unemployment, debt, investment.",
    requires_key=False,
)


INDICATORS = [
    ("NGDPDPC", "GDP per capita USD"),
    ("PCPIPCH", "Inflation %"),
    ("BCA_NGDPD", "Current account % GDP"),
    ("LUR", "Unemployment %"),
    ("GGXWDG_NGDP", "Gov gross debt % GDP"),
    ("NID_NGDP", "Total investment % GDP"),
]


async def _fetch_one(client: httpx.AsyncClient, code: str, label: str):
    try:
        r = await client.get(
            f"https://www.imf.org/external/datamapper/api/v1/{code}",
            timeout=30,
        )
        if r.status_code != 200:
            return code, {}
        body = r.json()
        values = body.get("values", {}).get(code, {}) or {}
        # values = { "USA": { "2022": 76, "2023": 80, ... }, ... }
        return code, values
    except Exception as e:
        print(f"[imf_data] {code} error: {e}")
        return code, {}


async def fetch(client: httpx.AsyncClient):
    results = await asyncio.gather(*[_fetch_one(client, c, l) for c, l in INDICATORS])
    by_country: dict[str, dict[str, Any]] = {}
    labels = {c: l for c, l in INDICATORS}
    for code, country_map in results:
        for iso3, year_map in country_map.items():
            if not year_map:
                continue
            latest_year = max(year_map.keys())
            latest_value = year_map[latest_year]
            rec = by_country.setdefault(iso3, {})
            # Keep history (for time-aware mapmodes) AND latest (for current readers)
            rec[code] = {
                "year": latest_year,
                "value": latest_value,
                "latest": {"year": latest_year, "value": latest_value},
                "history": year_map,    # already {year_str: value}
            }

    return {
        "source": "IMF DataMapper",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "indicators": labels,
        "count": len(by_country),
        "countries": by_country,
    }


register(LAYER, fetch)
