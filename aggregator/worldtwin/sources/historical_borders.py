"""Historical political borders — aourednik/historical-basemaps.

37 world snapshots from 123,000 BC → 2010 AD. CC-BY-SA per repo. Each snapshot
is a GeoJSON FeatureCollection of polygon entities (kingdoms, empires, polities)
with a `NAME` (or similar) property. We download all snapshots in parallel, tag
each feature with its snapshot year, and concatenate into a single timeline
feature collection so the frontend can filter by year.

Output envelope:
  {
    "snapshots": [year_signed_int, ...],     # sorted, e.g. -123000, -10000, ..., 2010
    "features_by_year": { "-2000": [...], "1500": [...] },   # FeatureCollection.features per snapshot
    "name_property": "NAME",                  # which prop holds the polity name
  }

Frontend uses `features_by_year[currentSnapshotKey]` to repaint borders when
the scrubber crosses a snapshot boundary. Snapshots ARE the resolution: between
1500 and 1530 we just show the 1500 snapshot until the year ticks past 1530.
"""
import asyncio

import httpx

from ..models import LayerMeta
from ..registry import register

BASE = "https://raw.githubusercontent.com/aourednik/historical-basemaps/master/geojson/world_{slug}.geojson"

# (year_signed, slug) — slug maps to the file name
SNAPSHOTS = [
    (-123000, "bc123000"),
    (-10000,  "bc10000"),
    (-8000,   "bc8000"),
    (-5000,   "bc5000"),
    (-4000,   "bc4000"),
    (-3000,   "bc3000"),
    (-2000,   "bc2000"),
    (-1500,   "bc1500"),
    (-1000,   "bc1000"),
    (-700,    "bc700"),
    (-500,    "bc500"),
    (-400,    "bc400"),
    (-323,    "bc323"),
    (-300,    "bc300"),
    (-200,    "bc200"),
    (-100,    "bc100"),
    (-1,      "bc1"),
    (100, "100"), (200, "200"), (300, "300"), (400, "400"),
    (500, "500"), (600, "600"), (700, "700"), (800, "800"),
    (900, "900"), (1000, "1000"), (1100, "1100"), (1200, "1200"),
    (1279, "1279"), (1300, "1300"), (1400, "1400"), (1492, "1492"),
    (1500, "1500"), (1530, "1530"), (1600, "1600"), (1650, "1650"),
    (1700, "1700"), (1715, "1715"), (1783, "1783"), (1800, "1800"),
    (1815, "1815"), (1880, "1880"), (1900, "1900"), (1914, "1914"),
    (1920, "1920"), (1930, "1930"), (1938, "1938"), (1945, "1945"),
    (1960, "1960"), (1994, "1994"), (2000, "2000"), (2010, "2010"),
]

LAYER = LayerMeta(
    id="historical_borders",
    name="Historical Borders (123,000 BC → 2010)",
    category="meta",
    kind="polygons",
    source="aourednik/historical-basemaps",
    source_url="https://github.com/aourednik/historical-basemaps",
    license="CC-BY-SA 4.0",
    refresh_s=86400 * 30,
    initial_delay_s=120,
    units="polygons",
    description=(
        "52 world political-borders snapshots from 123,000 BC to 2010 AD, "
        "sourced from the aourednik historical-basemaps community project "
        "(CC-BY-SA). The frontend snaps to the nearest snapshot at-or-before "
        "the current scrubber year."
    ),
)


def _normalise_props(props: dict) -> dict:
    """Pick the first non-empty name field across the various conventions."""
    for k in ("NAME", "name", "NAME_EN", "SUBJECTO", "SUBJECT"):
        v = props.get(k)
        if v:
            return {"name": str(v), **{kk: vv for kk, vv in props.items() if kk != k}}
    return {"name": "—", **props}


async def _fetch_one(client: httpx.AsyncClient, year: int, slug: str):
    url = BASE.format(slug=slug)
    try:
        r = await client.get(url, timeout=60)
        if r.status_code != 200:
            return year, None
        data = r.json()
        feats = data.get("features") or []
        out = []
        for f in feats:
            geom = f.get("geometry")
            if not geom:
                continue
            out.append({
                "type": "Feature",
                "geometry": geom,
                "properties": _normalise_props(f.get("properties") or {}),
            })
        return year, out
    except Exception:
        return year, None


async def fetch(client: httpx.AsyncClient):
    # Cap concurrency so we don't hammer GitHub raw
    sem = asyncio.Semaphore(6)

    async def _one(y, s):
        async with sem:
            return await _fetch_one(client, y, s)

    results = await asyncio.gather(*[_one(y, s) for y, s in SNAPSHOTS])

    features_by_year: dict[str, list] = {}
    snapshots: list[int] = []
    total = 0
    for year, feats in results:
        if feats is None:
            continue
        features_by_year[str(year)] = feats
        snapshots.append(year)
        total += len(feats)

    if not snapshots:
        return None

    snapshots.sort()
    v1_data = {
        "snapshots": snapshots,
        "features_by_year": features_by_year,
        "name_property": "name",
        "total_features": total,
        "snapshot_count": len(snapshots),
    }
    return v1_data, v1_data


register(LAYER, fetch)
