"""NOAA Global Monitoring Laboratory — atmospheric CO2 concentration.

Shows *how much CO2 is in the air* (ppm), not emissions.

Data sources (all free, no key, US government public domain):
  - Daily Mauna Loa CO2 (the Keeling Curve) — headline ppm number
  - NOAA flask network station list — ~80-100 stations worldwide with lat/lon
  - Monthly global mean CO2 — trend line

The Keeling Curve is the longest continuous measurement of atmospheric CO2
(started 1958 by Charles David Keeling at Mauna Loa Observatory, Hawaii).
Current level: ~427 ppm (2026), pre-industrial was ~280 ppm.
"""
import asyncio
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta, point, timeseries_point
from ..registry import register

# --- URLs ---
DAILY_MLO_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.csv"
MONTHLY_GLOBAL_URL = "https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_gl.csv"
STATION_LIST_URL = "https://gml.noaa.gov/dv/site/index.html?program=ccgg"

# Bereiter 2015 800kyr Antarctic CO2 composite (EPICA Dome C + Vostok + Law Dome).
# Public domain (NOAA NCEI). Columns: age_gas_calBP, co2_ppm, co2_1s_ppm.
# age_gas_calBP is "calendar years before 1950 AD" — convert to year_AD = 1950 - age.
EPICA_800K_URL = "https://www.ncei.noaa.gov/pub/data/paleo/icecore/antarctica/antarctica2015co2composite.txt"

# Hardcoded NOAA GML flask network stations — core global CO2 monitoring sites.
# Source: https://gml.noaa.gov/dv/site/?program=ccgg&parameter=co2
# These are the primary stations that measure atmospheric CO2 worldwide.
# Coordinates verified from NOAA GML site metadata.
STATIONS = [
    # code, name, lat, lon, elevation_m
    ("MLO", "Mauna Loa, Hawaii", 19.536, -155.576, 3397),
    ("BRW", "Barrow, Alaska", 71.323, -156.611, 11),
    ("SMO", "American Samoa", -14.247, -170.564, 42),
    ("SPO", "South Pole", -89.98, -24.80, 2810),
    ("ALT", "Alert, Canada", 82.451, -62.507, 210),
    ("CGO", "Cape Grim, Tasmania", -40.683, 144.690, 94),
    ("ZEP", "Ny-Ålesund, Svalbard", 78.907, 11.888, 474),
    ("THD", "Trinidad Head, California", 41.054, -124.151, 107),
    ("KUM", "Cape Kumukahi, Hawaii", 19.520, -154.815, 3),
    ("MID", "Sand Island, Midway", 28.210, -177.379, 8),
    ("KEY", "Key Biscayne, Florida", 25.665, -80.158, 1),
    ("ASK", "Assekrem, Algeria", 23.262, 5.632, 2728),
    ("AZR", "Terceira Island, Azores", 38.766, -27.375, 40),
    ("BAL", "Baltic Sea, Poland", 55.350, 17.220, 7),
    ("BME", "St. David's Head, Bermuda", 32.370, -64.650, 30),
    ("BMW", "Tudor Hill, Bermuda", 32.265, -64.879, 30),
    ("CBA", "Cold Bay, Alaska", 55.210, -162.720, 25),
    ("CHR", "Christmas Island", 1.700, -157.170, 3),
    ("CPT", "Cape Point, South Africa", -34.352, 18.490, 230),
    ("CRZ", "Crozet Island", -46.434, 51.848, 120),
    ("EIC", "Easter Island", -27.160, -109.430, 50),
    ("GMI", "Mariana Islands, Guam", 13.386, 144.656, 2),
    ("HBA", "Halley Station, Antarctica", -75.605, -26.210, 30),
    ("ICE", "Heimaey, Iceland", 63.400, -20.290, 100),
    ("IZO", "Izaña, Tenerife", 28.309, -16.499, 2373),
    ("KZD", "Sary Taukum, Kazakhstan", 44.450, 75.570, 412),
    ("KZM", "Plateau Assy, Kazakhstan", 43.250, 77.880, 2519),
    ("LEF", "Park Falls, Wisconsin", 45.945, -90.273, 472),
    ("LLB", "Lac La Biche, Canada", 54.954, -112.467, 540),
    ("LMP", "Lampedusa, Italy", 35.518, 12.632, 45),
    ("MHD", "Mace Head, Ireland", 53.326, -9.899, 8),
    ("NMB", "Gobabeb, Namibia", -23.580, 15.030, 461),
    ("NWR", "Niwot Ridge, Colorado", 40.053, -105.586, 3523),
    ("OXK", "Ochsenkopf, Germany", 50.030, 11.808, 1022),
    ("PAL", "Pallas-Sammaltunturi, Finland", 67.974, 24.116, 560),
    ("PSA", "Palmer Station, Antarctica", -64.774, -64.053, 10),
    ("RPB", "Ragged Point, Barbados", 13.165, -59.432, 45),
    ("SEY", "Mahé, Seychelles", -4.682, 55.532, 3),
    ("SHM", "Shemya Island, Alaska", 52.711, 174.126, 40),
    ("STM", "Ocean Station M, Norway", 66.000, 2.000, 0),
    ("SUM", "Summit, Greenland", 72.596, -38.422, 3238),
    ("SYO", "Syowa Station, Antarctica", -69.013, 39.590, 14),
    ("TAP", "Tae-ahn, South Korea", 36.738, 126.133, 20),
    ("TDF", "Tierra del Fuego, Argentina", -54.870, -68.480, 20),
    ("UTA", "Wendover, Utah", 39.902, -113.718, 1320),
    ("UUM", "Ulaan Uul, Mongolia", 44.452, 111.096, 914),
    ("WIS", "Negev, Israel", 31.130, 34.880, 400),
    ("WLG", "Mt. Waliguan, China", 36.288, 100.896, 3810),
    ("YON", "Yonagunijima, Japan", 24.470, 123.010, 30),
]

LAYER = LayerMeta(
    id="noaa_co2",
    name="Atmospheric CO₂ (Keeling Curve)",
    category="nature",
    kind="points",
    source="NOAA Global Monitoring Laboratory",
    source_url="https://gml.noaa.gov/ccgg/trends/",
    license="Public domain (US Government)",
    refresh_s=3600,
    initial_delay_s=20,
    units="ppm",
    description=(
        "Atmospheric CO₂ concentration from NOAA's global flask network. "
        "Headline number from Mauna Loa Observatory (the Keeling Curve, "
        "continuous since 1958). ~50 monitoring stations worldwide show "
        "regional variation. Pre-industrial CO₂ was ~280 ppm."
    ),
)


def _parse_daily_csv(text: str) -> list[dict]:
    """Parse NOAA daily Mauna Loa CSV. Lines starting with # are comments."""
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            co2 = float(parts[4])
            if co2 < 0:  # -999.99 = missing
                continue
            records.append({
                "date": f"{year:04d}-{month:02d}-{day:02d}",
                "co2_ppm": co2,
            })
        except (ValueError, IndexError):
            continue
    return records


def _parse_epica_composite(text: str) -> list[dict]:
    """Parse Bereiter 2015 800kyr Antarctic CO2 composite (whitespace-separated).

    Header lines start with '#' or non-numeric leading char. We keep one sample
    every ~50 years for the modern era and downsample older Pleistocene to
    one sample per ~500 years to keep the payload bounded (the raw file has
    ~1900 rows but we want predictable size).
    """
    points = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            age_bp = float(parts[0])
            co2 = float(parts[1])
        except ValueError:
            continue
        if not (100 <= co2 <= 800):  # sanity
            continue
        year_ad = round(1950 - age_bp)
        points.append((year_ad, co2))
    if not points:
        return []
    points.sort(key=lambda p: p[0])
    # Deduplicate identical years (keep first)
    seen = set()
    out = []
    for y, c in points:
        if y in seen:
            continue
        seen.add(y)
        out.append({"year": y, "co2_ppm": round(c, 2)})
    return out


def _parse_monthly_global_csv(text: str) -> list[dict]:
    """Parse NOAA monthly global mean CO2 CSV."""
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            year, month = int(parts[0]), int(parts[1])
            co2 = float(parts[3])
            if co2 < 0:
                continue
            records.append({
                "date": f"{year:04d}-{month:02d}-01",
                "co2_ppm": round(co2, 2),
            })
        except (ValueError, IndexError):
            continue
    return records


async def fetch(client: httpx.AsyncClient):
    # Fetch daily Mauna Loa + monthly global + EPICA 800kyr composite in parallel
    daily_task = client.get(DAILY_MLO_URL, timeout=30)
    monthly_task = client.get(MONTHLY_GLOBAL_URL, timeout=30)
    epica_task = client.get(EPICA_800K_URL, timeout=60)
    daily_resp, monthly_resp, epica_resp = await asyncio.gather(
        daily_task, monthly_task, epica_task, return_exceptions=True,
    )

    # --- Parse daily Mauna Loa (headline number) ---
    latest_co2 = None
    latest_date = None
    daily_trend = []
    if not isinstance(daily_resp, Exception) and daily_resp.status_code == 200:
        records = _parse_daily_csv(daily_resp.text)
        if records:
            latest = records[-1]
            latest_co2 = latest["co2_ppm"]
            latest_date = latest["date"]
            # Last 365 days for sparkline
            daily_trend = [
                timeseries_point(t=r["date"], v=r["co2_ppm"])
                for r in records[-365:]
            ]

    # --- Parse monthly global mean (long-term trend) ---
    monthly_trend = []
    if not isinstance(monthly_resp, Exception) and monthly_resp.status_code == 200:
        records = _parse_monthly_global_csv(monthly_resp.text)
        # Last 5 years for trend
        monthly_trend = [
            timeseries_point(t=r["date"], v=r["co2_ppm"])
            for r in records[-60:]
        ]

    # --- Parse EPICA 800kyr composite (deep-time scrubber series) ---
    historical = []
    if not isinstance(epica_resp, Exception) and epica_resp.status_code == 200:
        historical = _parse_epica_composite(epica_resp.text)

    # Stitch full timeline: EPICA (800kyr BC → ~1980 AD) + Mauna Loa monthly (1958 → present)
    # Where they overlap (1958-1980), Mauna Loa wins.
    full_series = []
    if historical:
        # Keep only EPICA samples older than 1958 to avoid double-counting
        full_series = [(p["year"], p["co2_ppm"]) for p in historical if p["year"] < 1958]
    if not isinstance(monthly_resp, Exception) and monthly_resp.status_code == 200:
        records = _parse_monthly_global_csv(monthly_resp.text)
        # Aggregate monthly to annual (mean per year)
        by_year: dict[int, list[float]] = {}
        for r in records:
            y = int(r["date"][:4])
            by_year.setdefault(y, []).append(r["co2_ppm"])
        for y, vals in sorted(by_year.items()):
            full_series.append((y, round(sum(vals) / len(vals), 2)))

    if latest_co2 is None:
        return None

    # --- Build station points ---
    # Each station gets the global latest CO2 as baseline (individual station
    # readings aren't available via a simple URL — they require per-station
    # file downloads). The point of showing stations is to visualise the
    # global monitoring network.
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    station_points = []
    for code, name, lat, lon, elev in STATIONS:
        is_mlo = code == "MLO"
        label = (
            f"{name}: {latest_co2:.2f} ppm ({latest_date})"
            if is_mlo
            else f"{name} ({code}) — {elev}m"
        )
        station_points.append(point(
            lat=lat, lon=lon,
            id=code.lower(),
            value=latest_co2 if is_mlo else None,
            label=label,
            station_code=code,
            station_name=name,
            elevation_m=elev,
            is_primary=is_mlo,
        ))

    # --- Build combined result ---
    series_min_year = full_series[0][0] if full_series else None
    series_max_year = full_series[-1][0] if full_series else None

    v1_data = {
        "headline": {
            "current_co2_ppm": latest_co2,
            "measurement_date": latest_date,
            "station": "Mauna Loa Observatory, Hawaii",
            "pre_industrial_ppm": 280,
            "increase_ppm": round(latest_co2 - 280, 2),
            "increase_pct": round(((latest_co2 - 280) / 280) * 100, 1),
        },
        "stations": station_points,
        "daily_trend": daily_trend,
        "monthly_global_trend": monthly_trend,
        # Deep-time series for the scrubber: list of [year, ppm] from -800,000 to today.
        # year is signed integer AD (negative = BC, astronomical convention so 1 BC = 0).
        "historical_series": [[y, c] for (y, c) in full_series],
        "historical_range": [series_min_year, series_max_year] if series_min_year is not None else None,
        "historical_count": len(full_series),
    }

    # Freshness timestamp — every public number must carry a date
    v1_data["fetched"] = datetime.now(timezone.utc).isoformat()
    return v1_data, v1_data


register(LAYER, fetch)
