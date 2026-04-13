"""OECD Composite Leading Indicators — monthly, canonical recession signal.

Free, no key. CLI < 100 and falling = recession approaching.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="oecd_cli",
    name="OECD Composite Leading Indicators",
    category="economy",
    kind="raw",
    source="OECD SDMX",
    source_url="https://sdmx.oecd.org/public/rest/",
    license="Free with attribution",
    refresh_s=86400 * 7,
    initial_delay_s=345,
    description="Monthly composite leading indicators for OECD members. CLI <100 and falling = recession risk.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    # OECD SDMX CLI — parse the sdmx-json structure properly.
    # The endpoint returns: { dataSets: [{ series: { "0:0:0": { observations: { "0": [value] }}}}], structure: {...} }
    # structure.dimensions.series lists country codes, structure.dimensions.observation lists time periods.
    try:
        r = await client.get(
            "https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.0/.M.LI......",
            params={"format": "jsondata", "startPeriod": "2024-01"},
            headers={
                "Accept": "application/vnd.sdmx.data+json; charset=utf-8; version=1.0",
                "User-Agent": "WorldTwin/1.0",
            },
            timeout=60,
            follow_redirects=True,
        )
        if r.status_code != 200:
            print(f"[oecd_cli] HTTP {r.status_code}: {r.text[:200]}")
            return {
                "source": "OECD CLI",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": 0,
                "countries": {},
                "note": f"HTTP {r.status_code}",
            }
        body = r.json()
        # OECD SDMX API nests everything under "data" key
        inner = body.get("data", body)
        datasets = inner.get("dataSets") or body.get("dataSets") or []
        struct = inner.get("structure") or body.get("structure") or (body.get("structures") or [{}])[0]
        dims = (struct.get("dimensions") or {})
        series_dims = dims.get("series") or []
        obs_dims = dims.get("observation") or []

        # Find the country dimension
        country_dim = None
        country_idx = None
        for i, dim in enumerate(series_dims):
            if dim.get("id") in ("REF_AREA", "COUNTRY", "LOCATION"):
                country_dim = dim
                country_idx = i
                break
        if country_dim is None:
            return {
                "source": "OECD CLI",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": 0,
                "countries": {},
                "note": "no country dim found",
            }
        country_values = country_dim.get("values") or []

        # Find time dimension
        time_values = []
        if obs_dims:
            for d in obs_dims:
                if d.get("id") in ("TIME_PERIOD", "TIME"):
                    time_values = [v.get("id") or v.get("name") for v in (d.get("values") or [])]
                    break

        out_countries: dict[str, list] = {}
        for ds in datasets:
            series_map = ds.get("series") or {}
            for key, series_entry in series_map.items():
                idxs = [int(x) for x in key.split(":") if x.isdigit()]
                if len(idxs) <= country_idx:
                    continue
                ci = idxs[country_idx]
                if ci >= len(country_values):
                    continue
                cc_code = country_values[ci].get("id")
                if not cc_code:
                    continue
                obs_map = series_entry.get("observations") or {}
                # obs_map = { "0": [val], "1": [val] }
                points = []
                for obs_key, obs_val in sorted(obs_map.items(), key=lambda x: int(x[0])):
                    ti = int(obs_key)
                    period = time_values[ti] if ti < len(time_values) else str(ti)
                    value = obs_val[0] if obs_val else None
                    if value is not None:
                        points.append({"period": period, "value": value})
                if points:
                    out_countries[cc_code] = points

        return {
            "source": "OECD CLI",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(out_countries),
            "countries": out_countries,
        }
    except Exception as e:
        print(f"[oecd_cli] error: {type(e).__name__}: {e}")
        return None


register(LAYER, fetch)
