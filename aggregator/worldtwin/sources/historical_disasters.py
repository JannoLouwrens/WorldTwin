"""Historical natural-disaster events (2150 BC → present).

Three sources, all NOAA / Smithsonian, all public domain:
  * NOAA Significant Earthquake Database (2150 BC → present, ~6,000 events)
  * NOAA Global Historical Tsunami Database (2100 BC → present, ~2,500 events)
  * Smithsonian GVP Holocene volcanic eruptions (10,000 BC → present)

We page through the NOAA Hazel API and pull a Smithsonian eruption export;
each event is normalised into a common shape: { kind, year, lat, lon, label,
deaths, magnitude, source }. The frontend filters by current scrubber year.

Output envelope:
  {
    "events": [
       { "kind": "eq"|"tsu"|"vol", "year": int, "lat": float, "lon": float,
         "label": "...", "deaths": int|None, "mag": float|None, "source_id": str },
       ...
    ],
    "year_range": [ya, yb],
    "counts": { "eq": int, "tsu": int, "vol": int }
  }
"""
import asyncio

import httpx

from ..models import LayerMeta
from ..registry import register

NOAA_EQ_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/earthquakes"
NOAA_TSU_URL = "https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/tsunamis/events"
GVP_URL = "https://volcano.si.edu/database/list_volcano_holocene_excel.cfm"  # not used directly; kept as ref
GVP_JSON = (
    "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows"
    "?service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:Smithsonian_VOTW_Holocene_Eruptions"
    "&outputFormat=application/json&srsName=EPSG:4326"
)

LAYER = LayerMeta(
    id="historical_disasters",
    name="Historical Disasters (2150 BC → today)",
    category="nature",
    kind="points",
    source="NOAA NCEI + Smithsonian GVP",
    source_url="https://www.ngdc.noaa.gov/hazard/",
    license="US Public Domain",
    refresh_s=86400 * 7,
    initial_delay_s=180,
    units="events",
    description=(
        "Significant earthquakes (2150 BC+), tsunamis (2100 BC+) and Holocene "
        "volcanic eruptions (10,000 BC+). Filterable by year via the time scrubber."
    ),
)


async def _page_noaa(client: httpx.AsyncClient, base_url: str, kind: str) -> list[dict]:
    out: list[dict] = []
    page = 1
    while True:
        try:
            # NOAA Hazel rejects itemsPerPage > 200 (verified — 1000 was the
            # reason this cache never wrote).
            r = await client.get(base_url, params={"page": page, "itemsPerPage": 200}, timeout=60)
            if r.status_code != 200:
                break
            data = r.json()
        except Exception:
            break
        items = data.get("items") or []
        if not items:
            break
        for it in items:
            year = it.get("year")
            lat = it.get("latitude")
            lon = it.get("longitude")
            if year is None or lat is None or lon is None:
                continue
            try:
                year = int(year)
            except (ValueError, TypeError):
                continue
            label_parts = []
            loc = it.get("locationName") or it.get("country")
            if loc:
                label_parts.append(str(loc))
            mag = it.get("eqMagnitude") or it.get("magnitude")
            if mag:
                label_parts.append(f"M{mag}")
            out.append({
                "kind": kind,
                "year": year,
                "lat": float(lat),
                "lon": float(lon),
                "label": " — ".join(label_parts) or kind,
                "deaths": it.get("deaths"),
                "mag": float(mag) if mag else None,
                "source_id": str(it.get("id", "")),
            })
        if page >= data.get("totalPages", 1):
            break
        page += 1
        if page > 40:
            break  # safety — NOAA quakes are ~6,200 = 32 pages at 200/page
    return out


async def _fetch_volcanoes(client: httpx.AsyncClient) -> list[dict]:
    out: list[dict] = []
    try:
        r = await client.get(GVP_JSON, timeout=120)
        if r.status_code != 200:
            return out
        data = r.json()
    except Exception:
        return out
    for f in data.get("features", []) or []:
        props = f.get("properties") or {}
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = coords[0], coords[1]
        # GVP WFS property names are underscored (verified live):
        # Volcano_Name, StartDateYear, ExplosivityIndexMax, Eruption_Number.
        year = props.get("StartDateYear") or props.get("EruptionStartYear") or props.get("StartYear")
        if year is None:
            continue
        try:
            year = int(year)
        except (ValueError, TypeError):
            continue
        vei = props.get("ExplosivityIndexMax") or props.get("ExplosivityIndex")
        name = props.get("Volcano_Name") or props.get("VolcanoName") or "Volcano"
        out.append({
            "kind": "vol",
            "year": year,
            "lat": float(lat),
            "lon": float(lon),
            "label": f"{name}" + (f" — VEI {vei}" if vei else ""),
            "deaths": None,
            "mag": float(vei) if vei else None,
            "source_id": str(props.get("Eruption_Number") or props.get("Volcano_Number")
                             or props.get("EruptionNumber") or ""),
        })
    return out


async def fetch(client: httpx.AsyncClient):
    eq_task = _page_noaa(client, NOAA_EQ_URL, "eq")
    tsu_task = _page_noaa(client, NOAA_TSU_URL, "tsu")
    vol_task = _fetch_volcanoes(client)
    eq, tsu, vol = await asyncio.gather(eq_task, tsu_task, vol_task)

    events = eq + tsu + vol
    if not events:
        return None

    # Sort by year — frontend can binary-search a year window
    events.sort(key=lambda e: e["year"])
    years = [e["year"] for e in events]
    counts = {"eq": len(eq), "tsu": len(tsu), "vol": len(vol)}

    v1 = {
        "events": events,
        "year_range": [years[0], years[-1]],
        "counts": counts,
        "total": len(events),
    }
    return v1, v1


register(LAYER, fetch)
