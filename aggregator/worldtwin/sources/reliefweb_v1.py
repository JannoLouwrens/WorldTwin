"""ReliefWeb v1 — humanitarian disasters and reports.

Free with proper appname parameter. Replaces broken frontend direct fetch.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc


LAYER = LayerMeta(
    id="reliefweb",
    name="Humanitarian Crises (HDX-derived)",
    category="war",
    kind="points",
    source="HDX CKAN (ReliefWeb v2 requires approved appname)",
    source_url="https://data.humdata.org/api/3/action/package_search",
    license="Varies — see HDX dataset",
    refresh_s=3600,
    initial_delay_s=325,
    description=(
        "Active humanitarian crises via HDX CKAN. ReliefWeb v2 is gated behind "
        "an approved appname which WorldTwin does not have; ReliefWeb v1 is decommissioned."
    ),
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    # HDX CKAN package search for current humanitarian crises
    try:
        r = await client.get(
            "https://data.humdata.org/api/3/action/package_search",
            params={
                "q": "humanitarian crisis emergency",
                "rows": 1000,        # widened from 100
                "sort": "metadata_modified desc",
                "fq": "groups:*",
            },
            timeout=90,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code != 200:
            return None
        body = r.json()
        results = (body.get("result") or {}).get("results") or []
        disasters = []
        for pkg in results:   # full result set, no slice
            groups = pkg.get("groups") or []
            if not groups:
                continue
            # HDX groups have country-code in 'name' as ISO3 lowercase
            iso3 = (groups[0].get("name") or "").upper()
            if not iso3 or len(iso3) != 3:
                continue
            coords = cc.coords_for_iso3(iso3)
            if not coords:
                continue
            disasters.append({
                "id": pkg.get("id"),
                "name": pkg.get("title", "")[:120],
                "description": (pkg.get("notes") or "")[:300],
                "date": pkg.get("metadata_modified", ""),
                "country_name": groups[0].get("title", ""),
                "country_iso3": iso3,
                "lat": coords[0],
                "lon": coords[1],
                "url": f"https://data.humdata.org/dataset/{pkg.get('name', '')}",
            })
        return {
            "source": "HDX (ReliefWeb v1 decommissioned, v2 needs approved appname)",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(disasters),
            "disasters": disasters,
        }
    except Exception as e:
        print(f"[reliefweb] error: {e}")
        return None


register(LAYER, fetch)
