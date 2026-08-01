"""Smithsonian Global Volcanism Program — world volcanoes."""
import httpx

from ..models import LayerMeta, point
from ..registry import register

LAYER = LayerMeta(
    id="volcanoes",
    name="World Volcanoes",
    category="nature",
    kind="points",
    source="Smithsonian GVP",
    source_url="https://webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs",
    license="Smithsonian (public)",
    refresh_s=86400,
    initial_delay_s=22,
    description="Global volcanism database — Holocene and active volcanoes worldwide.",
)


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            LAYER.source_url,
            params={
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeName": "GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes",
                "outputFormat": "application/json",
            },
            timeout=60,
        )
        r.raise_for_status()
        geo = r.json()
    except Exception:
        # Fallback to USGS VHP aggregated endpoint
        r = await client.get(
            "https://volcanoes.usgs.gov/vsc/api/volcanoApi/volcanoesGVP",
            timeout=60,
        )
        r.raise_for_status()
        return None  # Skip if we can't get normalized data

    points = []
    for f in geo.get("features", []):
        props = f.get("properties") or {}
        # GeoServer WFS feature ids embed a per-request session token
        # ("...fid-5d14b8df_19eb5a3c1c5_-25c5"), so the decomposer minted
        # ~1,200 brand-new source_ids on every fetch and snapshot dedup never
        # matched this static catalogue. Rewrite with the stable Volcano_Number.
        vnum = str(props.get("Volcano_Number", ""))
        if vnum:
            f["id"] = vnum
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        points.append(point(
            lat=coords[1], lon=coords[0],
            id=str(props.get("Volcano_Number", "")),
            label=props.get("Volcano_Name", "Volcano"),
            value=props.get("Elevation"),
            country=props.get("Country"),
            type=props.get("Primary_Volcano_Type"),
            last_eruption=props.get("Last_Known_Eruption"),
            region=props.get("Region"),
            subregion=props.get("Subregion"),
        ))
    # WFS stamps every response with a fresh timeStamp — drop it so the
    # snapshot content hash stays stable between fetches of unchanged data.
    geo.pop("timeStamp", None)
    return points, geo


register(LAYER, fetch)
