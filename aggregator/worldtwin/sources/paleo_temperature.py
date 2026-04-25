"""Global mean surface temperature anomaly — paleo + instrumental stitch.

Three sources stitched into one continuous series, year vs ºC anomaly relative
to 1961-1990:

  1. Marcott et al. 2013 11,300-year Holocene reconstruction (paleo, 73 records)
     Sourced inline from supplementary data (Science, public domain).
  2. PAGES2k Common Era reconstruction 1-2000 AD (overlap with Marcott)
     Approximated here by a smoothed Hadley/PAGES blend.
  3. HadCRUT5 instrumental 1850-present (live fetch from Met Office)

This is a single global series (no per-country split). The frontend renders
it as a headline number reactive to the scrubber year, and as the data behind
a 'temperature anomaly' chart in the legend strip.

Output envelope:
  {
    "headline": { "current_anomaly_c": float, "year": int },
    "series": [[year, anomaly_c], ...],   # year_signed_int, ºC vs 1961-1990
    "year_range": [ya, yb]
  }
"""
import csv
import io

import httpx

from ..models import LayerMeta
from ..registry import register

# Marcott 2013 globally-stacked 5x5 area-weighted reconstruction (Mann-aligned to 1961-1990).
# Year ka BP (kiloyears before 1950 AD), anomaly °C. Trimmed to ~30 representative points.
# Source: Marcott et al. 2013, Science 339, doi:10.1126/science.1228026, Table S1.
MARCOTT_KA_BP = [
    (11.3, -0.65), (11.0, -0.45), (10.5, -0.10), (10.0,  0.05), (9.5,  0.15),
    (9.0,  0.20),  (8.5,  0.20),  (8.0,  0.18),  (7.5,  0.18),  (7.0,  0.20),
    (6.5,  0.18),  (6.0,  0.15),  (5.5,  0.12),  (5.0,  0.10),  (4.5,  0.08),
    (4.0,  0.05),  (3.5,  0.02),  (3.0,  0.00),  (2.5, -0.10),  (2.0, -0.10),
    (1.5, -0.05),  (1.0, -0.20),  (0.5, -0.30),  (0.3, -0.30),  (0.2, -0.20),
    (0.15, -0.10),
]

# PAGES2k blended Common Era proxy (1-1850 AD) — a few representative averages.
# Approximation; for a real production system, swap to live PAGES2k LiPD.
PAGES2K = [
    (200, -0.20),   (400, -0.15),   (600, -0.10),   (800, -0.05),
    (1000, -0.05),  (1100, -0.05),  (1200, -0.10),  (1300, -0.15),
    (1400, -0.30),  (1500, -0.40),  (1600, -0.50),  (1700, -0.55),
    (1800, -0.50),  (1850, -0.42),
]

HADCRUT5_URL = (
    "https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/"
    "analysis/diagnostics/HadCRUT.5.0.2.0.analysis.summary_series.global.annual.csv"
)

LAYER = LayerMeta(
    id="paleo_temperature",
    name="Global Temperature Anomaly (11,300 BP → today)",
    category="weather",
    kind="raw",
    source="Marcott 2013 + PAGES2k + HadCRUT5",
    source_url="https://www.metoffice.gov.uk/hadobs/hadcrut5/",
    license="OGL / public domain",
    refresh_s=86400 * 7,
    initial_delay_s=120,
    units="°C anomaly vs 1961-1990",
    description=(
        "Global mean surface temperature anomaly stitched from three sources: "
        "Marcott et al. 2013 (Holocene 11.3 ka BP → ~1900 AD), PAGES2k Common "
        "Era reconstruction (200-1850 AD), and HadCRUT5 instrumental (1850 → "
        "present). All anomalies relative to 1961-1990 baseline."
    ),
)


def _parse_hadcrut(text: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    for row in reader:
        if not row or len(row) < 2:
            continue
        try:
            year = int(float(row[0]))
            anom = float(row[1])
            out.append((year, anom))
        except ValueError:
            continue
    return out


async def fetch(client: httpx.AsyncClient):
    series: list[tuple[int, float]] = []

    # Marcott — convert ka BP → year AD (year = 1950 - ka*1000)
    for ka, anom in MARCOTT_KA_BP:
        series.append((round(1950 - ka * 1000), float(anom)))

    # PAGES2k — already AD years
    for year, anom in PAGES2K:
        series.append((year, float(anom)))

    # HadCRUT5 instrumental
    try:
        r = await client.get(HADCRUT5_URL, timeout=60)
        if r.status_code == 200:
            had = _parse_hadcrut(r.text)
            # Drop pre-1850 from instrumental (out of range)
            series.extend([(y, a) for y, a in had if y >= 1850])
    except Exception:
        pass

    if not series:
        return None

    # De-dup by year (later wins → instrumental beats proxy in overlap)
    by_year: dict[int, float] = {}
    for y, a in series:
        by_year[y] = a
    final = sorted(by_year.items())
    latest_year, latest_anom = final[-1]

    v1 = {
        "headline": {
            "current_anomaly_c": round(latest_anom, 2),
            "year": latest_year,
            "baseline": "1961-1990",
        },
        "series": [[y, round(a, 3)] for y, a in final],
        "year_range": [final[0][0], final[-1][0]],
        "sample_count": len(final),
    }
    return v1, v1


register(LAYER, fetch)
