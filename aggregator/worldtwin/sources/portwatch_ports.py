"""IMF PortWatch — daily port traffic for ~2000 ports worldwide."""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="portwatch_ports",
    name="Live Port Traffic (PortWatch/IMF)",
    category="resources",
    kind="points",
    source="IMF PortWatch",
    source_url="https://portwatch.imf.org/",
    license="CC BY 4.0",
    refresh_s=43200,
    initial_delay_s=180,
    units="ships",
    description="Top ports worldwide with latest daily vessel calls by type.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    try:
        # Pull the ports reference (lat/lon)
        rref = await client.get(
            "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0/query",
            params={"where": "1=1", "outFields": "*", "f": "json", "resultRecordCount": 2500},
            timeout=60,
        )
        rref.raise_for_status()
        ref = rref.json()
        port_ref = {}
        for f in ref.get("features", []):
            attrs = f["attributes"]
            geom = f.get("geometry") or {}
            portid = attrs.get("portid")
            if portid is None:
                continue
            port_ref[portid] = {
                "portname": attrs.get("portname", ""),
                "country": attrs.get("country", ""),
                "lat": geom.get("y") or attrs.get("lat"),
                "lon": geom.get("x") or attrs.get("lon"),
            }

        # Pull the latest daily port data
        rd = await client.get(
            "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query",
            params={
                "where": "1=1",
                "outFields": "*",
                "orderByFields": "date DESC",
                "resultRecordCount": 2000,
                "f": "json",
            },
            timeout=60,
        )
        rd.raise_for_status()
        feats = rd.json().get("features", [])
        if not feats:
            return None
        latest_date_ms = max(f["attributes"].get("date", 0) for f in feats)
        latest = [f["attributes"] for f in feats if f["attributes"].get("date") == latest_date_ms]

        ports: list[dict[str, Any]] = []
        for a in latest:
            pid = a.get("portid")
            r = port_ref.get(pid)
            if not r or not r.get("lat") or not r.get("lon"):
                continue
            ports.append({
                "portid": pid,
                "name": r["portname"],
                "country": r["country"],
                "lat": r["lat"],
                "lon": r["lon"],
                "n_total": a.get("n_total", 0),
                "n_container": a.get("n_container", 0),
                "n_dry_bulk": a.get("n_dry_bulk", 0),
                "n_tanker": a.get("n_tanker", 0),
                "n_general_cargo": a.get("n_general_cargo", 0),
                "n_roro": a.get("n_roro", 0),
                "capacity": a.get("capacity", 0),
            })
        ports.sort(key=lambda p: p.get("capacity", 0), reverse=True)
        ports = ports[:800]

        return {
            "source": "IMF PortWatch",
            "latest_date_ms": latest_date_ms,
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(ports),
            "ports": ports,
        }
    except Exception as e:
        print(f"[portwatch_ports] error: {e}")
        return None


register(LAYER, fetch)
