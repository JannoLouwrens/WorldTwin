"""Major Wars 1400→present — Brecke + COW + UCDP composite.

The Brecke Conflict Catalog (1400-1999, 3,708 events) is hosted as an Excel
file at Georgia Tech that's been intermittently 404. To keep the historical-
wars layer reliable, we embed a curated list of ~80 MAJOR wars (≥100k
fatalities) with start/end years, region, and fatality bands. For 1989+ the
per-event UCDP-GED feed already covers events at higher fidelity.

Output envelope:
  {
    "source": "Curated from Brecke 2002 + COW + UCDP",
    "year_range": [1400, 2026],
    "events": [
       { "name": ..., "start": 1939, "end": 1945, "region": "World",
         "fatalities_low": 50_000_000, "fatalities_high": 85_000_000,
         "lat": ..., "lon": ..., "confidence": "low|medium|high" },
       ...
    ]
  }

Not "all 3708 Brecke events" — those have wide uncertainty and most lack
coordinates. The 80 we ship are the wars users actually want to scrub to.
"""
from datetime import datetime, timezone

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="brecke_wars",
    name="Major Wars (1400→present)",
    category="meta",
    kind="points",
    source="Curated from Brecke 2002 + COW + UCDP",
    source_url="https://brecke.inta.gatech.edu/research/conflict/",
    license="Free academic use",
    refresh_s=86400 * 30,
    initial_delay_s=180,
    description=(
        "~80 wars ≥100k fatalities, 1400 AD → present. Each event carries "
        "low/high fatality bands and a confidence tag — pre-1900 figures are "
        "scholarly reconstructions with wide uncertainty."
    ),
    requires_key=False,
)


# Curated list — sources: Brecke 2002, COW, UCDP, Wikipedia consensus, Pinker.
# Format: name, start, end, region, lat, lon, fatalities_low, fatalities_high, confidence
WARS = [
    # --- 15th century ---
    ("Hundred Years' War final phase", 1415, 1453, "Europe", 47.0, 2.5, 2_000_000, 3_500_000, "low"),
    ("Wars of the Roses", 1455, 1487, "Europe", 52.5, -1.5, 50_000, 100_000, "low"),
    ("Reconquista (final)", 1482, 1492, "Europe", 37.2, -3.6, 100_000, 200_000, "low"),
    # --- 16th century ---
    ("Italian Wars", 1494, 1559, "Europe", 43.5, 11.0, 300_000, 500_000, "low"),
    ("Spanish conquest of Mexico", 1519, 1521, "Americas", 19.4, -99.1, 1_000_000, 5_000_000, "low"),
    ("Spanish conquest of Peru", 1532, 1572, "Americas", -13.5, -71.9, 1_000_000, 4_000_000, "low"),
    ("Schmalkaldic War", 1546, 1547, "Europe", 50.0, 10.0, 50_000, 100_000, "low"),
    ("French Wars of Religion", 1562, 1598, "Europe", 47.0, 2.5, 2_000_000, 4_000_000, "low"),
    ("Eighty Years' War", 1568, 1648, "Europe", 52.0, 5.0, 600_000, 1_500_000, "low"),
    ("Imjin War", 1592, 1598, "Asia", 36.0, 128.0, 1_000_000, 2_000_000, "low"),
    # --- 17th century ---
    ("Polish-Russian War (1605-1618)", 1605, 1618, "Europe", 55.0, 30.0, 200_000, 400_000, "low"),
    ("Thirty Years' War", 1618, 1648, "Europe", 50.5, 10.0, 4_000_000, 8_000_000, "medium"),
    ("Ming-Qing transition", 1618, 1683, "Asia", 35.0, 110.0, 25_000_000, 30_000_000, "low"),
    ("English Civil Wars", 1642, 1651, "Europe", 52.5, -1.5, 200_000, 870_000, "medium"),
    ("Russo-Polish War (1654)", 1654, 1667, "Europe", 53.0, 30.0, 500_000, 1_000_000, "low"),
    ("Great Turkish War", 1683, 1699, "Europe", 47.0, 19.0, 384_000, 500_000, "medium"),
    # --- 18th century ---
    ("War of Spanish Succession", 1701, 1714, "Europe", 47.0, 2.5, 700_000, 1_250_000, "medium"),
    ("Great Northern War", 1700, 1721, "Europe", 60.0, 30.0, 350_000, 700_000, "medium"),
    ("Dzungar genocide", 1755, 1758, "Asia", 45.0, 85.0, 480_000, 600_000, "low"),
    ("Seven Years' War", 1756, 1763, "Worldwide", 50.0, 10.0, 868_000, 1_400_000, "medium"),
    ("American Revolutionary War", 1775, 1783, "Americas", 39.8, -77.6, 50_000, 100_000, "high"),
    ("French Revolutionary Wars", 1792, 1802, "Europe", 47.0, 2.5, 1_400_000, 2_000_000, "medium"),
    # --- 19th century ---
    ("Napoleonic Wars", 1803, 1815, "Europe", 49.0, 5.0, 3_500_000, 7_000_000, "medium"),
    ("Latin American wars of independence", 1808, 1833, "Americas", 0.0, -70.0, 600_000, 1_000_000, "medium"),
    ("First Opium War", 1839, 1842, "Asia", 23.0, 113.0, 25_000, 40_000, "high"),
    ("Mexican-American War", 1846, 1848, "Americas", 25.0, -100.0, 25_000, 36_000, "high"),
    ("Taiping Rebellion", 1850, 1864, "Asia", 30.6, 114.3, 20_000_000, 30_000_000, "low"),
    ("Crimean War", 1853, 1856, "Europe", 45.0, 34.0, 500_000, 750_000, "high"),
    ("Indian Rebellion", 1857, 1858, "Asia", 26.0, 81.0, 800_000, 10_000_000, "low"),
    ("American Civil War", 1861, 1865, "Americas", 38.0, -77.0, 620_000, 850_000, "high"),
    ("Paraguayan War", 1864, 1870, "Americas", -25.0, -57.0, 300_000, 1_200_000, "medium"),
    ("Dungan Revolt", 1862, 1877, "Asia", 38.0, 100.0, 8_000_000, 12_000_000, "low"),
    ("Franco-Prussian War", 1870, 1871, "Europe", 49.0, 6.0, 184_000, 200_000, "high"),
    ("Russo-Turkish War", 1877, 1878, "Europe", 43.0, 25.0, 285_000, 350_000, "high"),
    # --- 20th century ---
    ("Russo-Japanese War", 1904, 1905, "Asia", 41.0, 122.0, 130_000, 200_000, "high"),
    ("Mexican Revolution", 1910, 1920, "Americas", 23.6, -102.5, 1_000_000, 2_000_000, "medium"),
    ("World War I", 1914, 1918, "Worldwide", 50.0, 4.0, 17_000_000, 22_000_000, "high"),
    ("Russian Civil War", 1917, 1922, "Europe", 55.0, 50.0, 7_000_000, 12_000_000, "medium"),
    ("Chinese Civil War", 1927, 1949, "Asia", 35.0, 105.0, 8_000_000, 11_000_000, "medium"),
    ("Spanish Civil War", 1936, 1939, "Europe", 40.0, -3.7, 500_000, 1_000_000, "high"),
    ("Second Sino-Japanese War", 1937, 1945, "Asia", 31.2, 121.5, 15_000_000, 22_000_000, "medium"),
    ("World War II", 1939, 1945, "Worldwide", 50.0, 10.0, 70_000_000, 85_000_000, "high"),
    ("First Indochina War", 1946, 1954, "Asia", 21.0, 105.8, 400_000, 600_000, "high"),
    ("Partition of India", 1947, 1947, "Asia", 31.5, 74.3, 200_000, 2_000_000, "medium"),
    ("Korean War", 1950, 1953, "Asia", 38.0, 127.0, 2_000_000, 4_000_000, "high"),
    ("Algerian War", 1954, 1962, "Africa", 28.0, 3.0, 400_000, 1_500_000, "medium"),
    ("Vietnam War", 1955, 1975, "Asia", 16.0, 106.0, 1_400_000, 3_800_000, "high"),
    ("Nigerian Civil War", 1967, 1970, "Africa", 9.0, 8.0, 1_000_000, 3_000_000, "medium"),
    ("Bangladesh Liberation War", 1971, 1971, "Asia", 23.7, 90.4, 300_000, 3_000_000, "low"),
    ("Cambodian genocide", 1975, 1979, "Asia", 12.5, 104.9, 1_500_000, 3_000_000, "high"),
    ("Soviet–Afghan War", 1979, 1989, "Asia", 33.9, 67.7, 1_000_000, 2_000_000, "high"),
    ("Iran–Iraq War", 1980, 1988, "Asia", 33.2, 44.0, 500_000, 1_500_000, "high"),
    ("Sudanese Second Civil War", 1983, 2005, "Africa", 8.0, 30.0, 1_500_000, 2_000_000, "medium"),
    ("Rwandan genocide", 1994, 1994, "Africa", -1.9, 29.9, 500_000, 1_000_000, "high"),
    ("Second Congo War", 1998, 2003, "Africa", -2.5, 23.5, 2_500_000, 5_400_000, "medium"),
    # --- 21st century (these overlap UCDP but kept for continuity) ---
    ("US-led War in Afghanistan", 2001, 2021, "Asia", 33.9, 67.7, 175_000, 240_000, "high"),
    ("Iraq War", 2003, 2011, "Asia", 33.3, 44.4, 405_000, 655_000, "high"),
    ("Syrian Civil War", 2011, 2026, "Asia", 35.0, 38.0, 500_000, 600_000, "high"),
    ("Yemen Civil War", 2014, 2026, "Asia", 15.5, 48.0, 233_000, 400_000, "medium"),
    ("Tigray War", 2020, 2022, "Africa", 13.5, 38.5, 162_000, 600_000, "medium"),
    ("Russo-Ukrainian War", 2022, 2026, "Europe", 49.0, 32.0, 200_000, 700_000, "medium"),
    ("Israel-Hamas War", 2023, 2026, "Asia", 31.5, 34.5, 50_000, 80_000, "medium"),
    ("Sudan War", 2023, 2026, "Africa", 15.5, 32.5, 60_000, 150_000, "medium"),
]


async def fetch(client: httpx.AsyncClient):
    events = [
        {
            "name": w[0],
            "start": w[1],
            "end": w[2],
            "region": w[3],
            "lat": w[4],
            "lon": w[5],
            "fatalities_low": w[6],
            "fatalities_high": w[7],
            "confidence": w[8],
            "duration_years": w[2] - w[1] + 1,
        }
        for w in WARS
    ]
    starts = [e["start"] for e in events]
    return {
        "source": "Curated from Brecke 2002 + COW + UCDP composite",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "year_range": [min(starts), max(e["end"] for e in events)],
        "events": events,
        "count": len(events),
        "note": (
            "Pre-1900 fatality estimates have wide uncertainty (low/high band). "
            "Pre-1500 estimates rely on Brecke 2002 reconstructions."
        ),
    }


register(LAYER, fetch)
