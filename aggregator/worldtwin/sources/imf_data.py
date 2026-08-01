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
    # Core macro
    ("NGDPD",       "GDP USD bn (current)"),
    ("NGDPDPC",     "GDP per capita USD"),
    ("PPPGDP",      "GDP PPP USD bn"),
    ("PPPPC",       "GDP PPP per capita"),
    ("NGDP_RPCH",   "Real GDP growth %"),
    ("NGDPRPPPPCPCH", "Real GDP per capita growth %"),
    ("PPPSH",       "Share of world GDP PPP %"),
    # Inflation / prices
    ("PCPIPCH",     "Inflation avg % (CPI)"),
    ("PCPIEPCH",    "Inflation end-of-year %"),
    ("PCPI",        "Average CPI index"),
    # External
    ("BCA",         "Current account USD bn"),
    ("BCA_NGDPD",   "Current account % GDP"),
    # Labour
    ("LUR",         "Unemployment %"),
    ("LP",          "Population millions"),
    ("LE",          "Employment millions"),
    # Fiscal
    ("GGXWDG_NGDP", "Gov gross debt % GDP"),
    ("GGXWDG",      "Gov gross debt USD bn"),
    ("GGXCNL_NGDP", "Gov net lending % GDP"),
    ("GGR_NGDP",    "Gov revenue % GDP"),
    ("GGX_NGDP",    "Gov expenditure % GDP"),
    ("GGSB_NPGDP",  "Gov structural balance % GDP"),
    # Investment / saving
    ("NID_NGDP",    "Total investment % GDP"),
    ("NGSD_NGDP",   "Gross national savings % GDP"),
]


async def _fetch_one(client: httpx.AsyncClient, code: str, label: str, sem: asyncio.Semaphore):
    """Polite, retried fetch — IMF DataMapper 503s under heavy parallelism."""
    async with sem:
        for attempt in range(3):
            try:
                # IMF's Akamai edge 403-blocks non-browser User-Agents from
                # datacenter IPs (verified live 2026-06-11) — the custom
                # "WorldTwin/1.0" UA was the reason this cache went empty.
                r = await client.get(
                    f"https://www.imf.org/external/datamapper/api/v1/{code}",
                    timeout=60,
                    headers={
                        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                                       "Chrome/124.0.0.0 Safari/537.36"),
                        "Accept": "application/json",
                    },
                )
                if r.status_code == 200:
                    body = r.json()
                    values = body.get("values", {}).get(code, {}) or {}
                    await asyncio.sleep(0.4)   # politeness between calls
                    return code, values
                if r.status_code in (403, 429, 503):
                    print(f"[imf_data] {code} HTTP {r.status_code} (attempt {attempt + 1})")
                    await asyncio.sleep(5 + attempt * 5)
                    continue
                print(f"[imf_data] {code} HTTP {r.status_code}")
                return code, {}
            except Exception as e:
                if attempt == 2:
                    print(f"[imf_data] {code} error after 3 tries: {type(e).__name__}: {e}")
                await asyncio.sleep(2)
        return code, {}


async def fetch(client: httpx.AsyncClient):
    sem = asyncio.Semaphore(2)    # IMF doesn't like parallelism > 2
    results = await asyncio.gather(*[_fetch_one(client, c, l, sem) for c, l in INDICATORS])
    by_country: dict[str, dict[str, Any]] = {}
    labels = {c: l for c, l in INDICATORS}
    # IMF WEO ships forecasts 5+ years past the current calendar year.
    # We must distinguish "latest actual reading" from "latest forecast" so
    # the dashboard never quotes a 2031 prediction as "today's inflation."
    # Strategy: `latest` = nearest year ≤ current calendar year. If somehow
    # the cache has only forecasts (shouldn't happen), fall back to the
    # earliest forecast year so we still have a value but year is correct.
    current_year = datetime.now(timezone.utc).year
    for code, country_map in results:
        for iso3, year_map in country_map.items():
            if not year_map:
                continue
            historical = {y: v for y, v in year_map.items()
                          if (isinstance(y, str) and int(y) <= current_year)
                          or (isinstance(y, int) and y <= current_year)}
            if historical:
                latest_year = max(historical.keys(), key=lambda y: int(y))
                latest_value = historical[latest_year]
            else:
                # All entries are forecasts (rare). Pick the earliest forecast.
                latest_year = min(year_map.keys(), key=lambda y: int(y))
                latest_value = year_map[latest_year]
            rec = by_country.setdefault(iso3, {})
            # Keep history (for time-aware mapmodes) AND latest (for current readers)
            rec[code] = {
                "year": latest_year,
                "value": latest_value,
                "latest": {"year": latest_year, "value": latest_value},
                "history": year_map,    # already {year_str: value} — full series including forecasts
            }

    if not by_country:
        # Total upstream failure (e.g. Akamai 403 streak) — never overwrite
        # a good cache with an empty payload.
        print("[imf_data] all indicators failed — keeping previous cache")
        return None

    return {
        "source": "IMF DataMapper",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "indicators": labels,
        "count": len(by_country),
        "countries": by_country,
    }


register(LAYER, fetch)
