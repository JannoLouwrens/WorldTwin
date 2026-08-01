"""Typed models for the v1 API envelope and standard data shapes.

Every layer response follows the same envelope. Clients only ever need to
understand 7 data shapes (`kind`): points, flows, regions, timeseries,
tiles, scalar, raw.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Layer metadata — describes a layer WITHOUT its data
# ---------------------------------------------------------------------------

Category = Literal[
    "nature",     # weather, quakes, fires, volcanoes, disasters
    "war",        # conflicts, crises, violence
    "economy",    # GDP, forex, crypto, indicators
    "resources",  # trade, commodities, energy, flows
    "gaming",     # Steam, Twitch, esports
    "sports",     # live matches, F1, olympics
    "social",     # news, trends, wiki, social media
    "space",      # ISS, satellites, planets, aurora
    "transit",    # flights, ships, trains
    "infra",      # cables, cams, power, pipelines
    "health",     # disease, pollution, mortality
    "meta",       # API stats, world totals
]

Kind = Literal[
    "points",      # [{id, lat, lon, value?, label?, popup?, props?}]
    "flows",       # [{from: {lat,lon,name}, to: {lat,lon,name}, value?, label?, props?}]
    "regions",     # [{iso3, value, label?, props?}]
    "timeseries",  # [{t, v, label?}]
    "tiles",       # {url_template, min_zoom, max_zoom, attribution}
    "scalar",      # {value, label?, props?}
    "raw",         # passthrough (legacy / un-normalized)
]


@dataclass
class LayerMeta:
    """Metadata for a single layer — what it is, where it comes from,
    how often it refreshes, and what shape of data to expect."""

    id: str                             # e.g. "quakes"
    name: str                           # e.g. "Earthquakes (M2.5+)"
    category: Category
    kind: Kind
    source: str                         # "USGS", "NASA FIRMS", etc.
    source_url: str                     # canonical source link
    license: str = "see source"
    refresh_s: int = 600                # default 10 min
    initial_delay_s: int = 0            # to stagger startup
    units: str = ""
    description: str = ""
    requires_key: bool = False          # true if an env var must be set
    key_env: str = ""                   # which env var, for documentation
    enabled: bool = True

    def public(self) -> dict[str, Any]:
        """Serializable view for /v1/layers."""
        d = asdict(self)
        # don't leak internal fields
        return d


# ---------------------------------------------------------------------------
# Envelope — every /v1/layers/{id} response looks like this
# ---------------------------------------------------------------------------

@dataclass
class Envelope:
    id: str
    name: str
    category: str
    kind: str
    source: str
    source_url: str
    license: str
    fetched_at: str          # ISO 8601 UTC
    expires_at: str          # ISO 8601 UTC
    units: str
    count: int
    data: Any                # shape depends on kind

    @classmethod
    def build(cls, meta: LayerMeta, data: Any, fetched_at: str, expires_at: str) -> "Envelope":
        if isinstance(data, dict) and data.get("type") == "FeatureCollection":
            count = len(data.get("features", []))
        elif isinstance(data, dict) and isinstance(data.get("features"), list):
            count = len(data["features"])
        elif isinstance(data, dict) and isinstance(data.get("flows"), list):
            count = len(data["flows"])
        elif isinstance(data, dict) and isinstance(data.get("articles"), list):
            count = len(data["articles"])
        elif isinstance(data, dict) and isinstance(data.get("events"), list):
            count = len(data["events"])
        elif isinstance(data, dict) and isinstance(data.get("pairs"), list):
            count = len(data["pairs"])
        elif isinstance(data, dict) and isinstance(data.get("series"), dict):
            count = len(data["series"])
        elif isinstance(data, dict) and isinstance(data.get("countries"), dict):
            count = len(data["countries"])
        elif isinstance(data, dict) and isinstance(data.get("top"), list):
            count = len(data["top"])
        elif isinstance(data, dict) and isinstance(data.get("webcams"), list):
            count = len(data["webcams"])
        elif isinstance(data, dict) and isinstance(data.get("crew"), list):
            # iss has iss+crew dict — only count it if the position is present
            iss = data.get("iss")
            count = 1 if isinstance(iss, dict) and "lat" in iss and "lon" in iss else 0
        elif isinstance(data, dict) and isinstance(data.get("matches"), list):
            count = len(data["matches"])
        elif isinstance(data, dict) and isinstance(data.get("topGames"), list):
            count = len(data["topGames"])
        elif isinstance(data, dict) and isinstance(data.get("crypto"), list):
            count = len(data["crypto"])
        elif isinstance(data, dict) and isinstance(data.get("chokepoints"), list):
            count = len(data["chokepoints"])
        elif isinstance(data, dict) and isinstance(data.get("ports"), list):
            count = len(data["ports"])
        elif isinstance(data, dict) and isinstance(data.get("battles"), list):
            count = len(data["battles"])
        elif isinstance(data, dict) and isinstance(data.get("pulses"), list):
            count = len(data["pulses"])
        elif isinstance(data, dict) and isinstance(data.get("items"), list):
            count = len(data["items"])
        elif isinstance(data, dict) and isinstance(data.get("plants"), list):
            count = len(data["plants"])
        elif isinstance(data, dict) and isinstance(data.get("images"), list):
            count = len(data["images"])
        elif isinstance(data, dict) and isinstance(data.get("rovers"), dict):
            count = sum(
                len(rv.get("photos") or [])
                for rv in data["rovers"].values()
                if isinstance(rv, dict)
            )
        elif isinstance(data, dict) and isinstance(data.get("countries"), dict):
            count = len(data["countries"])
        elif isinstance(data, dict) and isinstance(data.get("aurora"), dict):
            count = data["aurora"].get("count", 1)
        elif isinstance(data, dict) and isinstance(data.get("data"), list):
            count = len(data["data"])
        elif isinstance(data, list):
            count = len(data)
        elif isinstance(data, dict):
            # Unknown dict shape: len(data) (= number of top-level keys) is
            # always >0 and defeats the scheduler's empty-clobber guard. Use
            # the largest nested list/dict instead — 0 when all are empty —
            # and fall back to 1 only for pure-scalar dicts (kind='scalar').
            nested = [v for v in data.values() if isinstance(v, (list, dict))]
            count = max((len(v) for v in nested), default=0) if nested else 1
        else:
            try:
                count = len(data) if hasattr(data, "__len__") else 1
            except TypeError:
                count = 1
        return cls(
            id=meta.id,
            name=meta.name,
            category=meta.category,
            kind=meta.kind,
            source=meta.source,
            source_url=meta.source_url,
            license=meta.license,
            fetched_at=fetched_at,
            expires_at=expires_at,
            units=meta.units,
            count=count,
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        # NOT dataclasses.asdict(): that recursively deep-copies the entire
        # payload graph (~hundreds of MB for bulk layers like ucdp_ged) on
        # every fetch. Shallow copy shares the data reference — downstream
        # only serializes it, never mutates it.
        return dict(self.__dict__)


# ---------------------------------------------------------------------------
# Shape helpers — use these in sources to produce normalized records
# ---------------------------------------------------------------------------

def point(
    lat: float,
    lon: float,
    *,
    id: str | None = None,
    value: float | None = None,
    label: str | None = None,
    popup: str | None = None,
    **props: Any,
) -> dict[str, Any]:
    """Build a normalized point record for kind='points'."""
    out: dict[str, Any] = {"lat": float(lat), "lon": float(lon)}
    if id is not None:
        out["id"] = str(id)
    if value is not None:
        out["value"] = value
    if label is not None:
        out["label"] = label
    if popup is not None:
        out["popup"] = popup
    if props:
        out["props"] = props
    return out


def flow(
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
    *,
    value: float | None = None,
    label: str | None = None,
    from_name: str | None = None,
    to_name: str | None = None,
    **props: Any,
) -> dict[str, Any]:
    """Build a normalized flow (arc) record for kind='flows'."""
    out: dict[str, Any] = {
        "from": {"lat": float(from_lat), "lon": float(from_lon)},
        "to": {"lat": float(to_lat), "lon": float(to_lon)},
    }
    if from_name is not None:
        out["from"]["name"] = from_name
    if to_name is not None:
        out["to"]["name"] = to_name
    if value is not None:
        out["value"] = value
    if label is not None:
        out["label"] = label
    if props:
        out["props"] = props
    return out


def region(iso3: str, value: Any, *, label: str | None = None, **props: Any) -> dict[str, Any]:
    """Build a normalized region record for kind='regions' (for choropleth)."""
    out: dict[str, Any] = {"iso3": iso3, "value": value}
    if label is not None:
        out["label"] = label
    if props:
        out["props"] = props
    return out


def timeseries_point(t: str, v: Any, *, label: str | None = None) -> dict[str, Any]:
    out = {"t": t, "v": v}
    if label is not None:
        out["label"] = label
    return out
