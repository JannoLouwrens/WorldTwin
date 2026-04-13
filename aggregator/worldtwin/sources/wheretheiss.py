"""ISS position (WhereTheISS.at) + crew (Open Notify)."""
import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="iss",
    name="International Space Station",
    category="space",
    kind="points",
    source="WhereTheISS.at + Open Notify",
    source_url="https://wheretheiss.at/w/developer",
    license="Free for public use",
    refresh_s=10,
    initial_delay_s=0,
    units="altitude (km)",
    description="Live position of the ISS plus current crew manifest.",
)


async def fetch(client: httpx.AsyncClient):
    r = await client.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=15)
    r.raise_for_status()
    iss = r.json()

    crew = []
    try:
        r2 = await client.get("http://api.open-notify.org/astros.json", timeout=15)
        if r2.status_code == 200:
            crew_all = r2.json().get("people", [])
            crew = [p for p in crew_all if p.get("craft") == "ISS"]
    except Exception:
        pass

    points = [point(
        lat=iss.get("latitude", 0),
        lon=iss.get("longitude", 0),
        id="iss",
        value=iss.get("altitude"),
        label=f"ISS · {len(crew)} crew",
        altitude_km=iss.get("altitude"),
        velocity_kmh=iss.get("velocity"),
        visibility=iss.get("visibility"),
        crew=[{"name": p.get("name")} for p in crew],
    )]

    legacy = {"iss": iss, "crew": crew}
    return points, legacy


register(LAYER, fetch)
