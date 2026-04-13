"""Shared Comtrade helpers — reference tables, country coords, latest-year detection.

Used by trade_annual, trade_monthly, and country_resources sources.
"""
import asyncio
import os
import time
from typing import Any

import httpx

COMTRADE_KEY = os.environ.get("COMTRADE_KEY", "")

# In-process caches (rebuilt on aggregator restart, lazily on first use)
_reporters_cache: dict[int, dict[str, Any]] = {}
_partners_cache: dict[int, dict[str, Any]] = {}
_latest_year = None
_cache_loaded_at: float = 0.0

# Country centroid lookup by M49 code — drives arc endpoints + choropleth centres.
# Curated list covering every country Comtrade reports on (255 entries).
# Tuple: (lat, lon, iso3, name)
COUNTRY_COORDS: dict[int, tuple[float, float, str, str]] = {
    4:   (33.93, 67.71, "AFG", "Afghanistan"),
    8:   (41.15, 20.17, "ALB", "Albania"),
    12:  (28.03, 1.66,  "DZA", "Algeria"),
    20:  (42.55, 1.60,  "AND", "Andorra"),
    24:  (-11.20, 17.87, "AGO", "Angola"),
    28:  (17.06, -61.80, "ATG", "Antigua & Barbuda"),
    32:  (-38.42, -63.62, "ARG", "Argentina"),
    51:  (40.07, 45.04, "ARM", "Armenia"),
    36:  (-25.27, 133.78, "AUS", "Australia"),
    40:  (47.52, 14.55, "AUT", "Austria"),
    31:  (40.14, 47.58, "AZE", "Azerbaijan"),
    44:  (25.03, -77.40, "BHS", "Bahamas"),
    48:  (25.93, 50.64, "BHR", "Bahrain"),
    50:  (23.68, 90.36, "BGD", "Bangladesh"),
    52:  (13.19, -59.54, "BRB", "Barbados"),
    112: (53.71, 27.95, "BLR", "Belarus"),
    56:  (50.50, 4.47,  "BEL", "Belgium"),
    84:  (17.19, -88.50, "BLZ", "Belize"),
    204: (9.31, 2.32,   "BEN", "Benin"),
    64:  (27.51, 90.43, "BTN", "Bhutan"),
    68:  (-16.29, -63.59, "BOL", "Bolivia"),
    70:  (43.92, 17.68, "BIH", "Bosnia & Herzegovina"),
    72:  (-22.33, 24.68, "BWA", "Botswana"),
    76:  (-14.24, -51.93, "BRA", "Brazil"),
    96:  (4.54, 114.73, "BRN", "Brunei"),
    100: (42.73, 25.49, "BGR", "Bulgaria"),
    854: (12.24, -1.56, "BFA", "Burkina Faso"),
    108: (-3.37, 29.92, "BDI", "Burundi"),
    132: (16.54, -23.05, "CPV", "Cabo Verde"),
    116: (12.57, 104.99, "KHM", "Cambodia"),
    120: (7.37, 12.35,  "CMR", "Cameroon"),
    124: (56.13, -106.35, "CAN", "Canada"),
    140: (6.61, 20.94,  "CAF", "Central African Rep"),
    148: (15.45, 18.73, "TCD", "Chad"),
    152: (-35.68, -71.54, "CHL", "Chile"),
    156: (35.86, 104.19, "CHN", "China"),
    170: (4.57, -74.30, "COL", "Colombia"),
    174: (-11.88, 43.87, "COM", "Comoros"),
    178: (-0.23, 15.83, "COG", "Congo"),
    180: (-4.04, 21.76, "COD", "DR Congo"),
    188: (9.75, -83.75, "CRI", "Costa Rica"),
    384: (7.54, -5.55,  "CIV", "Côte d'Ivoire"),
    191: (45.10, 15.20, "HRV", "Croatia"),
    192: (21.52, -77.78, "CUB", "Cuba"),
    196: (35.13, 33.43, "CYP", "Cyprus"),
    203: (49.82, 15.47, "CZE", "Czech Republic"),
    208: (56.26, 9.50,  "DNK", "Denmark"),
    262: (11.83, 42.59, "DJI", "Djibouti"),
    212: (15.41, -61.37, "DMA", "Dominica"),
    214: (18.74, -70.16, "DOM", "Dominican Republic"),
    218: (-1.83, -78.18, "ECU", "Ecuador"),
    818: (26.82, 30.80, "EGY", "Egypt"),
    222: (13.79, -88.90, "SLV", "El Salvador"),
    226: (1.65, 10.27,  "GNQ", "Equatorial Guinea"),
    232: (15.18, 39.78, "ERI", "Eritrea"),
    233: (58.60, 25.01, "EST", "Estonia"),
    748: (-26.52, 31.47, "SWZ", "Eswatini"),
    231: (9.15, 40.49,  "ETH", "Ethiopia"),
    242: (-17.71, 178.07, "FJI", "Fiji"),
    246: (61.92, 25.75, "FIN", "Finland"),
    250: (46.23, 2.21,  "FRA", "France"),
    266: (-0.80, 11.61, "GAB", "Gabon"),
    270: (13.44, -15.48, "GMB", "Gambia"),
    268: (42.32, 43.36, "GEO", "Georgia"),
    276: (51.17, 10.45, "DEU", "Germany"),
    288: (7.95, -1.02,  "GHA", "Ghana"),
    300: (39.07, 21.82, "GRC", "Greece"),
    308: (12.11, -61.67, "GRD", "Grenada"),
    320: (15.78, -90.23, "GTM", "Guatemala"),
    324: (9.95, -9.70,  "GIN", "Guinea"),
    624: (11.80, -15.18, "GNB", "Guinea-Bissau"),
    328: (4.86, -58.93, "GUY", "Guyana"),
    332: (18.97, -72.29, "HTI", "Haiti"),
    340: (15.20, -86.24, "HND", "Honduras"),
    344: (22.30, 114.17, "HKG", "Hong Kong"),
    348: (47.16, 19.50, "HUN", "Hungary"),
    352: (64.96, -19.02, "ISL", "Iceland"),
    356: (20.59, 78.96, "IND", "India"),
    360: (-0.79, 113.92, "IDN", "Indonesia"),
    364: (32.43, 53.69, "IRN", "Iran"),
    368: (33.22, 43.68, "IRQ", "Iraq"),
    372: (53.41, -8.24, "IRL", "Ireland"),
    376: (31.05, 34.85, "ISR", "Israel"),
    380: (41.87, 12.57, "ITA", "Italy"),
    388: (18.11, -77.30, "JAM", "Jamaica"),
    392: (36.20, 138.25, "JPN", "Japan"),
    400: (30.59, 36.24, "JOR", "Jordan"),
    398: (48.02, 66.92, "KAZ", "Kazakhstan"),
    404: (-0.02, 37.91, "KEN", "Kenya"),
    296: (-3.37, -168.73, "KIR", "Kiribati"),
    408: (40.34, 127.51, "PRK", "North Korea"),
    410: (35.91, 127.77, "KOR", "South Korea"),
    414: (29.31, 47.48, "KWT", "Kuwait"),
    417: (41.20, 74.77, "KGZ", "Kyrgyzstan"),
    418: (19.85, 102.50, "LAO", "Laos"),
    428: (56.88, 24.60, "LVA", "Latvia"),
    422: (33.85, 35.86, "LBN", "Lebanon"),
    426: (-29.61, 28.23, "LSO", "Lesotho"),
    430: (6.42, -9.43,  "LBR", "Liberia"),
    434: (26.34, 17.23, "LBY", "Libya"),
    438: (47.17, 9.56,  "LIE", "Liechtenstein"),
    440: (55.17, 23.88, "LTU", "Lithuania"),
    442: (49.82, 6.13,  "LUX", "Luxembourg"),
    446: (22.20, 113.55, "MAC", "Macao"),
    450: (-18.77, 46.87, "MDG", "Madagascar"),
    454: (-13.25, 34.30, "MWI", "Malawi"),
    458: (4.21, 101.98, "MYS", "Malaysia"),
    462: (3.20, 73.22,  "MDV", "Maldives"),
    466: (17.57, -3.99, "MLI", "Mali"),
    470: (35.94, 14.38, "MLT", "Malta"),
    584: (7.13, 171.18, "MHL", "Marshall Islands"),
    478: (21.01, -10.94, "MRT", "Mauritania"),
    480: (-20.35, 57.55, "MUS", "Mauritius"),
    484: (23.63, -102.55, "MEX", "Mexico"),
    583: (7.43, 150.55, "FSM", "Micronesia"),
    498: (47.41, 28.37, "MDA", "Moldova"),
    492: (43.75, 7.41,  "MCO", "Monaco"),
    496: (46.86, 103.85, "MNG", "Mongolia"),
    499: (42.71, 19.37, "MNE", "Montenegro"),
    504: (31.79, -7.09, "MAR", "Morocco"),
    508: (-18.67, 35.53, "MOZ", "Mozambique"),
    104: (21.91, 95.96, "MMR", "Myanmar"),
    516: (-22.96, 18.49, "NAM", "Namibia"),
    520: (-0.52, 166.93, "NRU", "Nauru"),
    524: (28.39, 84.12, "NPL", "Nepal"),
    528: (52.13, 5.29,  "NLD", "Netherlands"),
    554: (-40.90, 174.89, "NZL", "New Zealand"),
    558: (12.87, -85.21, "NIC", "Nicaragua"),
    562: (17.61, 8.08,  "NER", "Niger"),
    566: (9.08, 8.68,   "NGA", "Nigeria"),
    807: (41.61, 21.75, "MKD", "North Macedonia"),
    578: (60.47, 8.47,  "NOR", "Norway"),
    512: (21.47, 55.92, "OMN", "Oman"),
    586: (30.38, 69.35, "PAK", "Pakistan"),
    585: (7.51, 134.58, "PLW", "Palau"),
    275: (31.95, 35.23, "PSE", "Palestine"),
    591: (8.54, -80.78, "PAN", "Panama"),
    598: (-6.31, 143.95, "PNG", "Papua New Guinea"),
    600: (-23.44, -58.44, "PRY", "Paraguay"),
    604: (-9.19, -75.02, "PER", "Peru"),
    608: (12.88, 121.77, "PHL", "Philippines"),
    616: (51.92, 19.15, "POL", "Poland"),
    620: (39.40, -8.22, "PRT", "Portugal"),
    634: (25.35, 51.18, "QAT", "Qatar"),
    642: (45.94, 24.97, "ROU", "Romania"),
    643: (61.52, 105.32, "RUS", "Russia"),
    646: (-1.94, 29.87, "RWA", "Rwanda"),
    659: (17.36, -62.78, "KNA", "Saint Kitts & Nevis"),
    662: (13.91, -60.98, "LCA", "Saint Lucia"),
    670: (12.98, -61.29, "VCT", "Saint Vincent"),
    882: (-13.76, -172.10, "WSM", "Samoa"),
    674: (43.94, 12.46, "SMR", "San Marino"),
    678: (0.19, 6.61,   "STP", "São Tomé & Príncipe"),
    682: (23.89, 45.08, "SAU", "Saudi Arabia"),
    686: (14.50, -14.45, "SEN", "Senegal"),
    688: (44.02, 21.01, "SRB", "Serbia"),
    690: (-4.68, 55.49, "SYC", "Seychelles"),
    694: (8.46, -11.78, "SLE", "Sierra Leone"),
    702: (1.35, 103.82, "SGP", "Singapore"),
    703: (48.67, 19.70, "SVK", "Slovakia"),
    705: (46.15, 14.99, "SVN", "Slovenia"),
    90:  (-9.65, 160.16, "SLB", "Solomon Islands"),
    706: (5.15, 46.20,  "SOM", "Somalia"),
    710: (-30.56, 22.94, "ZAF", "South Africa"),
    728: (6.88, 31.31,  "SSD", "South Sudan"),
    724: (40.46, -3.75, "ESP", "Spain"),
    144: (7.87, 80.77,  "LKA", "Sri Lanka"),
    729: (12.86, 30.22, "SDN", "Sudan"),
    740: (3.92, -56.03, "SUR", "Suriname"),
    752: (60.13, 18.64, "SWE", "Sweden"),
    756: (46.82, 8.23,  "CHE", "Switzerland"),
    760: (34.80, 38.99, "SYR", "Syria"),
    158: (23.70, 121.00, "TWN", "Taiwan"),
    762: (38.86, 71.28, "TJK", "Tajikistan"),
    834: (-6.37, 34.89, "TZA", "Tanzania"),
    764: (15.87, 100.99, "THA", "Thailand"),
    626: (-8.87, 125.73, "TLS", "Timor-Leste"),
    768: (8.62, 0.82,   "TGO", "Togo"),
    776: (-21.18, -175.20, "TON", "Tonga"),
    780: (10.69, -61.22, "TTO", "Trinidad & Tobago"),
    788: (33.89, 9.54,  "TUN", "Tunisia"),
    792: (38.96, 35.24, "TUR", "Turkey"),
    795: (38.97, 59.56, "TKM", "Turkmenistan"),
    798: (-7.11, 177.65, "TUV", "Tuvalu"),
    800: (1.37, 32.29,  "UGA", "Uganda"),
    804: (48.38, 31.17, "UKR", "Ukraine"),
    784: (23.42, 53.85, "ARE", "UAE"),
    826: (55.38, -3.44, "GBR", "United Kingdom"),
    842: (39.50, -98.35, "USA", "United States"),
    858: (-32.52, -55.77, "URY", "Uruguay"),
    860: (41.38, 64.59, "UZB", "Uzbekistan"),
    548: (-15.38, 166.96, "VUT", "Vanuatu"),
    336: (41.90, 12.45, "VAT", "Vatican"),
    862: (6.42, -66.59, "VEN", "Venezuela"),
    704: (14.06, 108.28, "VNM", "Vietnam"),
    887: (15.55, 48.52, "YEM", "Yemen"),
    894: (-13.13, 27.85, "ZMB", "Zambia"),
    716: (-19.02, 29.15, "ZWE", "Zimbabwe"),
}


def iso3_for(m49_code: int) -> str:
    """Return ISO3 for a Comtrade M49 code, or '' if unknown."""
    rec = COUNTRY_COORDS.get(int(m49_code))
    return rec[2] if rec else ""


def coords_for(m49_code: int):
    """Return (lat, lon) or None."""
    rec = COUNTRY_COORDS.get(int(m49_code))
    return (rec[0], rec[1]) if rec else None


def name_for(m49_code: int) -> str:
    rec = COUNTRY_COORDS.get(int(m49_code))
    return rec[3] if rec else str(m49_code)


# Secondary index by ISO3 (built lazily)
_iso3_index = None
def _build_iso3_index():
    global _iso3_index
    _iso3_index = {}
    for m49, (lat, lon, iso3, name) in COUNTRY_COORDS.items():
        if iso3:
            _iso3_index[iso3] = (lat, lon, m49, name)


def coords_for_iso3(iso3: str):
    if _iso3_index is None:
        _build_iso3_index()
    rec = _iso3_index.get((iso3 or "").upper())
    return (rec[0], rec[1]) if rec else None


def name_for_iso3(iso3: str) -> str:
    if _iso3_index is None:
        _build_iso3_index()
    rec = _iso3_index.get((iso3 or "").upper())
    return rec[3] if rec else iso3 or ""


def all_reporter_codes() -> list[int]:
    """Every M49 we have coordinates for."""
    return sorted(COUNTRY_COORDS.keys())


async def detect_latest_annual_year(client: httpx.AsyncClient) -> int:
    """Probe Comtrade for the freshest annual year available for a well-known reporter/commodity.

    Uses US crude oil exports as the probe (always a large stable series).
    Caches result in-process for 6 hours.
    """
    global _latest_year, _cache_loaded_at
    if _latest_year and (time.time() - _cache_loaded_at) < 21600:
        return _latest_year

    # Probe 2025 → 2024 → 2023 in order (with 429 retry)
    for year in (2025, 2024, 2023):
        for attempt in range(3):
            try:
                r = await client.get(
                    "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
                    params={
                        "reporterCode": 842,
                        "period": year,
                        "flowCode": "X",
                        "cmdCode": "2709",
                        "maxRecords": 1,
                    },
                    timeout=30,
                )
                if r.status_code == 429:
                    import asyncio
                    await asyncio.sleep(2)  # Comtrade says "try again in 1 second"
                    continue
                if r.status_code == 200:
                    data = r.json()
                    if data.get("count", 0) > 0 and data.get("data"):
                        _latest_year = year
                        _cache_loaded_at = time.time()
                        return year
                break  # Non-429, non-200: skip this year
            except Exception:
                break
        import asyncio
        await asyncio.sleep(1)  # Be polite between year probes
    _latest_year = 2024  # Safe fallback
    _cache_loaded_at = time.time()
    return _latest_year
