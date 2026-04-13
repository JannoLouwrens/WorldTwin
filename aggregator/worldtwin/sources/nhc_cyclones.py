"""NHC — active Atlantic + Eastern/Central Pacific tropical cyclones.

NOAA public domain. Current storms with forecast tracks and cone of uncertainty.
Updates every 3-6h during active storms.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="nhc_cyclones",
    name="Active Tropical Cyclones (NHC)",
    category="nature",
    kind="points",
    source="NOAA National Hurricane Center",
    source_url="https://www.nhc.noaa.gov/CurrentStorms.json",
    license="US Public Domain",
    refresh_s=1800,  # 30 min
    initial_delay_s=45,
    units="knots / kts",
    description=(
        "Active tropical cyclones in the Atlantic, East Pacific, and Central "
        "Pacific. Includes current position, max wind, pressure, movement, and "
        "Saffir-Simpson category."
    ),
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://www.nhc.noaa.gov/CurrentStorms.json",
            timeout=30,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code != 200:
            return {
                "source": "NOAA NHC",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": 0,
                "storms": [],
                "note": f"HTTP {r.status_code}",
            }
        data = r.json()
        storms = data.get("activeStorms") or data.get("storms") or []

        out = []
        for s in storms:
            try:
                lat = float(s.get("latitudeNumeric") or 0)
                lon = float(s.get("longitudeNumeric") or 0)
            except (ValueError, TypeError):
                continue
            if lat == 0 and lon == 0:
                continue
            try:
                wind_kts = float(s.get("intensity") or 0)
            except (ValueError, TypeError):
                wind_kts = 0
            # Saffir-Simpson
            cat = "TD"
            if wind_kts >= 137: cat = "Cat5"
            elif wind_kts >= 113: cat = "Cat4"
            elif wind_kts >= 96:  cat = "Cat3"
            elif wind_kts >= 83:  cat = "Cat2"
            elif wind_kts >= 64:  cat = "Cat1"
            elif wind_kts >= 34:  cat = "TS"
            out.append({
                "id": s.get("id") or s.get("binNumber"),
                "name": s.get("name", ""),
                "basin": s.get("binNumber", ""),
                "lat": lat,
                "lon": lon,
                "wind_kts": wind_kts,
                "pressure_mb": s.get("pressure") or s.get("minimumPressure"),
                "movement": s.get("movement", ""),
                "category": cat,
                "last_update": s.get("lastUpdate", ""),
                "classification": s.get("classification", ""),
            })

        return {
            "source": "NOAA NHC",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(out),
            "storms": out,
        }
    except Exception as e:
        print(f"[nhc_cyclones] error: {e}")
        return None


register(LAYER, fetch)
