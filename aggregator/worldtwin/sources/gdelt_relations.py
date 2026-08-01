"""GDELT-derived News Activity Index (NOT a diplomatic relations matrix).

## Why this is not a "relations" matrix anymore

The previous version of this module averaged the GDELT GoldsteinScale per
country pair and called the result a "diplomatic relations" score. That is
wrong for three reasons:

1. **GoldsteinScale is not a measured sentiment** — it is a static per-event-
   code lookup (see CAMEO.goldsteinscale.txt). Every event with CAMEO code
   193 gets -10.0 regardless of context. Averaging it weighted by mentions
   produces "what category of verbs did headlines use" — not "how friendly
   these two countries are".
2. **Actor1CountryCode is nationality, not event location** — an article
   about a Ghanaian diplomat meeting an Indonesian official in Geneva
   creates a (GHA, IDN) row even though nothing happened between those
   countries. CAMEO auto-coding is noisy enough that pair-level Goldstein
   averages are dominated by single-article artifacts.
3. **CAMEO country codes include regional codes** like AFR, EUR, WST, MEA,
   WSB, GZS, BAG. Treating them as ISO3 silently corrupts per-country
   aggregates.

Academic literature backs this up: Ward et al. (2013) "Comparing GDELT and
ICEWS Event Data" and Hammond & Weidmann (2014) "Using machine-coded event
data for the micro-level study of political violence" both note that
GDELT's auto-coding is noisy enough that pair-level political sentiment
requires heavy filtering to be useful, and that Goldstein means of
automatically-coded news are especially unreliable.

## What this module now computes

For each country pair (Actor1CountryCode → Actor2CountryCode):
- Count of distinct COOPERATIVE events (QuadClass 1 Verbal Coop + 2 Material Coop)
- Count of distinct CONFLICT events   (QuadClass 3 Verbal Conflict + 4 Material Conflict)
- Total distinct events

Pair "tone" = (coop - conflict) / total, range -1..+1. This is the ratio of
cooperation-coded vs conflict-coded news about the pair — an *honest*
measurement of "what kind of news" rather than a fake friendship index.

Per-country metrics use ActionGeo_CountryCode (where the event happened)
so the choropleth answers "how much conflict/cooperation news is *about*
this country's territory" — the thing GDELT can actually measure.

Thresholds (much stricter than before):
  - Pair needs >= 20 distinct events to appear in the matrix
  - Pair needs >= 40 distinct events to appear in top_hostile/top_friendly
  - Both actor codes must be in the COUNTRY whitelist (no regional codes)

Source: https://www.gdeltproject.org/data.html
CAMEO: https://www.gdeltproject.org/data/lookups/CAMEO.country.txt
Schema: https://raw.githubusercontent.com/linwoodc3/gdelt2HeaderRows/master/schema_csvs/GDELT_2.0_Events_Column_Labels_Header_Row_Sep2016.csv
"""
import asyncio
import io
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="relations",
    name="News Activity (GDELT)",
    category="war",
    kind="raw",
    source="GDELT Events 2.0 (QuadClass-based)",
    source_url="http://data.gdeltproject.org/gdeltv2/",
    license="GDELT Terms (free, attribution required)",
    refresh_s=3600,
    initial_delay_s=60,
    units="cooperation/conflict ratio (-1..+1)",
    description=(
        "Honest news-activity index computed from every GDELT-indexed event "
        "in the last 24 hours. For each country pair and each country we "
        "count distinct cooperative vs conflict events (QuadClass 1+2 vs "
        "3+4) and report the ratio. This is NOT a diplomatic relations "
        "matrix — GDELT's auto-coded Goldstein scale is too noisy at the "
        "pair level to support that claim — but it is a reliable measure "
        "of what kind of news is being written about each country."
    ),
)

# ---------- GDELT file layout ----------
FILES_PER_HOUR = 4
HOURS_TO_FETCH = 24
TOTAL_FILES = FILES_PER_HOUR * HOURS_TO_FETCH

# Verified column indices — see docstring
COL_ACTOR1_COUNTRY = 7
COL_ACTOR2_COUNTRY = 17
COL_EVENT_ROOT_CODE = 28
COL_QUAD_CLASS = 29
COL_GOLDSTEIN = 30
COL_NUM_MENTIONS = 31
COL_AVG_TONE = 34
COL_ACTIONGEO_COUNTRY = 53  # FIPS 2-letter (not CAMEO, not ISO3)

# QuadClass values: 1=Verbal Coop, 2=Material Coop, 3=Verbal Conflict, 4=Material Conflict
COOPERATION_QUADS = {"1", "2"}
CONFLICT_QUADS = {"3", "4"}

# ---------- CAMEO → ISO3 country whitelist ----------
# CAMEO uses 3-letter codes that mostly overlap with ISO3 but include many
# non-country region codes (AFR, EUR, WST, ...) and special administrative
# codes (WSB, GZS, BAG). We accept only real sovereign-state CAMEO codes
# that coincide with ISO3.
#
# Source: https://www.gdeltproject.org/data/lookups/CAMEO.country.txt
# Filtered to actual UN-recognised countries. ~195 entries.
CAMEO_COUNTRIES = {
    "AFG","ALB","DZA","AND","AGO","ATG","ARG","ARM","AUS","AUT","AZE",
    "BHS","BHR","BGD","BRB","BLR","BEL","BLZ","BEN","BTN","BOL","BIH",
    "BWA","BRA","BRN","BGR","BFA","BDI","CPV","KHM","CMR","CAN","CAF",
    "TCD","CHL","CHN","COL","COM","COG","COD","CRI","CIV","HRV","CUB",
    "CYP","CZE","DNK","DJI","DMA","DOM","ECU","EGY","SLV","GNQ","ERI",
    "EST","SWZ","ETH","FJI","FIN","FRA","GAB","GMB","GEO","DEU","GHA",
    "GRC","GRD","GTM","GIN","GNB","GUY","HTI","HND","HUN","ISL","IND",
    "IDN","IRN","IRQ","IRL","ISR","ITA","JAM","JPN","JOR","KAZ","KEN",
    "KIR","PRK","KOR","KWT","KGZ","LAO","LVA","LBN","LSO","LBR","LBY",
    "LIE","LTU","LUX","MDG","MWI","MYS","MDV","MLI","MLT","MHL","MRT",
    "MUS","MEX","FSM","MDA","MCO","MNG","MNE","MAR","MOZ","MMR","NAM",
    "NRU","NPL","NLD","NZL","NIC","NER","NGA","MKD","NOR","OMN","PAK",
    "PLW","PAN","PNG","PRY","PER","PHL","POL","PRT","QAT","ROU","RUS",
    "RWA","KNA","LCA","VCT","WSM","SMR","STP","SAU","SEN","SRB","SYC",
    "SLE","SGP","SVK","SVN","SLB","SOM","ZAF","SSD","ESP","LKA","SDN",
    "SUR","SWE","CHE","SYR","TWN","TJK","TZA","THA","TLS","TGO","TON",
    "TTO","TUN","TUR","TKM","TUV","UGA","UKR","ARE","GBR","USA","URY",
    "UZB","VUT","VAT","VEN","VNM","YEM","ZMB","ZWE",
}

# FIPS 2-letter → ISO3 for ActionGeo_CountryCode (needed for the choropleth).
# ActionGeo uses FIPS 10-4 country codes, which are different from CAMEO.
# Only the common ones — missing codes silently drop from the choropleth.
FIPS_TO_ISO3 = {
    "AF":"AFG","AL":"ALB","AG":"DZA","AN":"AND","AO":"AGO","AC":"ATG",
    "AR":"ARG","AM":"ARM","AS":"AUS","AU":"AUT","AJ":"AZE","BF":"BHS",
    "BA":"BHR","BG":"BGD","BB":"BRB","BO":"BLR","BE":"BEL","BH":"BLZ",
    "BN":"BEN","BT":"BTN","BL":"BOL","BK":"BIH","BC":"BWA","BR":"BRA",
    "BX":"BRN","BU":"BGR","UV":"BFA","BY":"BDI","CV":"CPV","CB":"KHM",
    "CM":"CMR","CA":"CAN","CT":"CAF","CD":"TCD","CI":"CHL","CH":"CHN",
    "CO":"COL","CN":"COM","CF":"COG","CG":"COD","CS":"CRI","IV":"CIV",
    "HR":"HRV","CU":"CUB","CY":"CYP","EZ":"CZE","DA":"DNK","DJ":"DJI",
    "DO":"DMA","DR":"DOM","EC":"ECU","EG":"EGY","ES":"SLV","EK":"GNQ",
    "ER":"ERI","EN":"EST","WZ":"SWZ","ET":"ETH","FJ":"FJI","FI":"FIN",
    "FR":"FRA","GB":"GAB","GA":"GMB","GG":"GEO","GM":"DEU","GH":"GHA",
    "GR":"GRC","GJ":"GRD","GT":"GTM","GV":"GIN","PU":"GNB","GY":"GUY",
    "HA":"HTI","HO":"HND","HU":"HUN","IC":"ISL","IN":"IND","ID":"IDN",
    "IR":"IRN","IZ":"IRQ","EI":"IRL","IS":"ISR","IT":"ITA","JM":"JAM",
    "JA":"JPN","JO":"JOR","KZ":"KAZ","KE":"KEN","KR":"KIR","KN":"PRK",
    "KS":"KOR","KU":"KWT","KG":"KGZ","LA":"LAO","LG":"LVA","LE":"LBN",
    "LT":"LSO","LI":"LBR","LY":"LBY","LS":"LIE","LH":"LTU","LU":"LUX",
    "MA":"MDG","MI":"MWI","MY":"MYS","MV":"MDV","ML":"MLI","MT":"MLT",
    "RM":"MHL","MR":"MRT","MP":"MUS","MX":"MEX","FM":"FSM","MD":"MDA",
    "MN":"MCO","MG":"MNG","MJ":"MNE","MO":"MAR","MZ":"MOZ","BM":"MMR",
    "WA":"NAM","NR":"NRU","NP":"NPL","NL":"NLD","NZ":"NZL","NU":"NIC",
    "NG":"NER","NI":"NGA","MK":"MKD","NO":"NOR","MU":"OMN","PK":"PAK",
    "PS":"PLW","PM":"PAN","PP":"PNG","PA":"PRY","PE":"PER","RP":"PHL",
    "PL":"POL","PO":"PRT","QA":"QAT","RO":"ROU","RS":"RUS","RW":"RWA",
    "SC":"KNA","ST":"LCA","VC":"VCT","WS":"WSM","SM":"SMR","TP":"STP",
    "SA":"SAU","SG":"SEN","RI":"SRB","SE":"SYC","SL":"SLE","SN":"SGP",
    "LO":"SVK","SI":"SVN","BP":"SLB","SO":"SOM","SF":"ZAF","OD":"SSD",
    "SP":"ESP","CE":"LKA","SU":"SDN","NS":"SUR","SW":"SWE","SZ":"CHE",
    "SY":"SYR","TW":"TWN","TI":"TJK","TZ":"TZA","TH":"THA","TT":"TLS",
    "TO":"TGO","TN":"TON","TD":"TTO","TS":"TUN","TU":"TUR","TX":"TKM",
    "TV":"TUV","UG":"UGA","UP":"UKR","AE":"ARE","UK":"GBR","US":"USA",
    "UY":"URY","UZ":"UZB","NH":"VUT","VT":"VAT","VE":"VEN","VM":"VNM",
    "YM":"YEM","ZA":"ZMB","ZI":"ZWE",
}


def _generate_file_urls(hours: int = HOURS_TO_FETCH) -> list[str]:
    urls = []
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    minute = (now.minute // 15) * 15
    now = now.replace(minute=minute) - timedelta(minutes=30)
    for i in range(hours * FILES_PER_HOUR):
        t = now - timedelta(minutes=15 * i)
        stamp = t.strftime("%Y%m%d%H%M%S")
        urls.append(f"http://data.gdeltproject.org/gdeltv2/{stamp}.export.CSV.zip")
    return urls


async def _download_and_parse(client: httpx.AsyncClient, url: str) -> list[dict]:
    try:
        r = await client.get(url, timeout=30)
        if r.status_code != 200:
            return []
        buf = io.BytesIO(r.content)
        with zipfile.ZipFile(buf) as zf:
            name = zf.namelist()[0]
            with zf.open(name) as f:
                raw = f.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    events = []
    for line in raw.splitlines():
        cols = line.split("\t")
        if len(cols) < 54:  # need through ActionGeo_CountryCode (col 53)
            continue
        a1 = cols[COL_ACTOR1_COUNTRY].strip()
        a2 = cols[COL_ACTOR2_COUNTRY].strip()
        quad = cols[COL_QUAD_CLASS].strip()
        root = cols[COL_EVENT_ROOT_CODE].strip()
        action_fips = cols[COL_ACTIONGEO_COUNTRY].strip()
        try:
            mentions = int(cols[COL_NUM_MENTIONS])
        except (ValueError, IndexError):
            continue
        events.append({
            "a1": a1,
            "a2": a2,
            "quad": quad,
            "root": root,
            "mentions": mentions,
            "action_fips": action_fips,
        })
    return events


async def fetch(client: httpx.AsyncClient):
    urls = _generate_file_urls(HOURS_TO_FETCH)
    sem = asyncio.Semaphore(8)

    async def bounded(url):
        async with sem:
            return await _download_and_parse(client, url)

    results = await asyncio.gather(*[bounded(u) for u in urls])
    all_events = []
    for batch in results:
        all_events.extend(batch)
    if not all_events:
        return None

    # ----- Per-pair counts (distinct events, not mention-weighted) -----
    pair_coop = defaultdict(int)
    pair_conflict = defaultdict(int)
    pair_total = defaultdict(int)
    pair_mentions = defaultdict(int)  # for ranking only

    for ev in all_events:
        a1, a2 = ev["a1"], ev["a2"]
        if not a1 or not a2 or a1 == a2:
            continue
        # Country whitelist — drops regional codes and non-country entries
        if a1 not in CAMEO_COUNTRIES or a2 not in CAMEO_COUNTRIES:
            continue
        key = (a1, a2)
        pair_total[key] += 1
        pair_mentions[key] += ev["mentions"]
        if ev["quad"] in COOPERATION_QUADS:
            pair_coop[key] += 1
        elif ev["quad"] in CONFLICT_QUADS:
            pair_conflict[key] += 1

    # Build pair matrix (>= 20 distinct events required)
    pairs = []
    MIN_PAIR_EVENTS = 20
    for key, total in pair_total.items():
        if total < MIN_PAIR_EVENTS:
            continue
        coop = pair_coop[key]
        conflict = pair_conflict[key]
        # Ratio in -1..+1; neutral/verbal events dilute toward 0
        ratio = (coop - conflict) / total
        pairs.append({
            "from": key[0],
            "to": key[1],
            "coop_events": coop,
            "conflict_events": conflict,
            "total_events": total,
            "total_mentions": pair_mentions[key],
            "ratio": round(ratio, 3),
        })

    # ----- Per-country metrics using ActionGeo (where events happened) -----
    # This is more honest than aggregating actor nationality: it answers
    # "how much coop/conflict news is about events *in* country X".
    country_coop = defaultdict(int)
    country_conflict = defaultdict(int)
    country_total = defaultdict(int)
    country_mentions = defaultdict(int)

    for ev in all_events:
        fips = ev["action_fips"]
        iso3 = FIPS_TO_ISO3.get(fips)
        if not iso3:
            continue
        country_total[iso3] += 1
        country_mentions[iso3] += ev["mentions"]
        if ev["quad"] in COOPERATION_QUADS:
            country_coop[iso3] += 1
        elif ev["quad"] in CONFLICT_QUADS:
            country_conflict[iso3] += 1

    countries = {}
    MIN_COUNTRY_EVENTS = 30
    for iso3, total in country_total.items():
        if total < MIN_COUNTRY_EVENTS:
            continue
        coop = country_coop[iso3]
        conflict = country_conflict[iso3]
        ratio = (coop - conflict) / total
        countries[iso3] = {
            "iso3": iso3,
            "coop_events": coop,
            "conflict_events": conflict,
            "total_events": total,
            "total_mentions": country_mentions[iso3],
            "ratio": round(ratio, 3),
        }

    # ----- Top lists (stricter threshold for visual lines) -----
    MIN_VISIBLE_PAIR = 40
    visible = [p for p in pairs if p["total_events"] >= MIN_VISIBLE_PAIR]

    # Rank hostile/friendly by ratio, but require a minimum number of
    # conflict (or coop) events so we don't promote single-article noise.
    hostile_candidates = [p for p in visible if p["conflict_events"] >= 15]
    friendly_candidates = [p for p in visible if p["coop_events"] >= 15]

    top_hostile = sorted(hostile_candidates, key=lambda p: p["ratio"])[:20]
    top_friendly = sorted(friendly_candidates, key=lambda p: -p["ratio"])[:20]
    top_volume = sorted(visible, key=lambda p: -p["total_events"])[:30]

    # Sort full pair list by total_events for the exported matrix
    pairs.sort(key=lambda p: -p["total_events"])

    payload = {
        "source": "GDELT Events 2.0 (QuadClass)",
        "window_hours": HOURS_TO_FETCH,
        "files_fetched": sum(1 for r in results if r),
        "total_events": len(all_events),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "methodology": (
            "Per-pair ratio = (coop_events - conflict_events) / total_events "
            "using GDELT QuadClass (1+2 coop, 3+4 conflict). Pair must have "
            f">= {MIN_PAIR_EVENTS} distinct events to appear, >= {MIN_VISIBLE_PAIR} "
            "to be visualised, and >= 15 events on the dominant side to be "
            "ranked as top hostile/friendly. Country codes filtered to a "
            "sovereign-state whitelist. Per-country ratio uses ActionGeo "
            "(where the event happened), not actor nationality."
        ),
        "pairs": pairs[:500],
        "pairs_full": pairs,    # full pair set → History Store
        "countries": countries,
        "top_hostile": top_hostile,
        "top_friendly": top_friendly,
        "top_volume": top_volume,
    }
    return payload, payload


register(LAYER, fetch)
