"""NASA FIRMS active fires (VIIRS SNPP)."""
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

FIRMS_KEY = os.environ.get("FIRMS_KEY", "REDACTED_FIRMS_KEY")

LAYER = LayerMeta(
    id="fires",
    name="Active Fires (past 24h)",
    category="nature",
    kind="points",
    source="NASA FIRMS (VIIRS SNPP)",
    source_url="https://firms.modaps.eosdis.nasa.gov/api/area/",
    license="NASA open data",
    refresh_s=600,
    initial_delay_s=6,
    units="fire radiative power (MW)",
    description="Active fire detections from VIIRS satellite in the past 24 hours.",
    requires_key=True,
    key_env="FIRMS_KEY",
)


async def fetch(client: httpx.AsyncClient):
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/VIIRS_SNPP_NRT/world/1"
    r = await client.get(url, timeout=60)
    r.raise_for_status()
    lines = r.text.strip().split("\n")
    if len(lines) < 2:
        return [], []
    header = lines[0].split(",")
    idx = {name: i for i, name in enumerate(header)}
    step = max(1, len(lines) // 2000)
    points = []
    legacy = []  # old format: list of dicts with short keys
    for i in range(1, len(lines), step):
        cols = lines[i].split(",")
        if len(cols) < len(header):
            continue
        try:
            lat = float(cols[idx.get("latitude", 0)])
            lon = float(cols[idx.get("longitude", 1)])
            bright = float(cols[idx.get("bright_ti4", 2)]) if idx.get("bright_ti4") is not None else 0
            frp_str = cols[idx.get("frp", 12)] if idx.get("frp") is not None else "0"
            frp = float(frp_str) if frp_str else 0
            date = cols[idx.get("acq_date", 5)] if idx.get("acq_date") is not None else ""
            time = cols[idx.get("acq_time", 6)] if idx.get("acq_time") is not None else ""
            sat = cols[idx.get("satellite", 7)] if idx.get("satellite") is not None else ""
            conf = cols[idx.get("confidence", 9)] if idx.get("confidence") is not None else ""
            dn = cols[idx.get("daynight", 13)] if idx.get("daynight") is not None else ""
        except (ValueError, IndexError):
            continue
        points.append(point(
            lat=lat, lon=lon,
            value=frp,
            label=f"{frp:.1f} MW",
            bright_k=bright, date=date, time=time, sat=sat, conf=conf, dn=dn,
        ))
        legacy.append({
            "lat": lat, "lon": lon, "bright": bright, "frp": frp,
            "date": date, "time": time, "sat": sat, "conf": conf, "dn": dn,
        })
    return points, legacy


register(LAYER, fetch)
