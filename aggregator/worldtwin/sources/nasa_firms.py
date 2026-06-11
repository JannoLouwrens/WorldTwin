"""NASA FIRMS active fires (VIIRS SNPP)."""
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

# NEVER commit the key inline. Set FIRMS_KEY in .env.
FIRMS_KEY = os.environ.get("FIRMS_KEY", "")

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
    # Pull 1 day (the layer is "Active Fires — past 24h"). world/10 across
    # 3 sensors was blowing the FIRMS transaction quota and getting
    # rejected, which blanked the layer to [] in production.
    sensors = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
    points = []
    legacy = []
    for sensor in sensors:
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{FIRMS_KEY}/{sensor}/world/1"
        try:
            r = await client.get(url, timeout=120)
            if r.status_code != 200:
                continue
            lines = r.text.strip().split("\n")
            if len(lines) < 2:
                continue
            header = lines[0].split(",")
            idx = {name: i for i, name in enumerate(header)}
            # No downsample — keep every detection
            for i in range(1, len(lines)):
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
                    sensor=sensor,
                ))
                legacy.append({
                    "lat": lat, "lon": lon, "bright": bright, "frp": frp,
                    "date": date, "time": time, "sat": sat, "conf": conf, "dn": dn,
                    "sensor": sensor,
                })
        except Exception as e:
            print(f"[nasa_firms] {sensor} error: {e}")
    if not points:
        # All sensors failed (quota / outage) — keep the previous cache
        # rather than blanking the layer to [].
        print("[nasa_firms] 0 detections from all sensors — keeping previous cache")
        return None
    return points, legacy


register(LAYER, fetch)
