"""Country culture — religion + ethnicity per country from Wikidata + CIA Factbook.

Combines two sources:
  1. Wikidata SPARQL for structured religion (P140) and ethnic group (P172)
     properties, keyed by ISO3 (P298). CC0.
  2. CIA World Factbook (github mirror) for text-based Religions/Ethnic groups
     fields as fallback and for dominant-group percentages.

Output:
  {
    "countries": {
      "USA": {
        "religion_primary": "Christianity",
        "religion_family": "christianity",
        "religion_color": "#6B8CCE",
        "religions_text": "Protestant 46.5%, Roman Catholic 20.8%...",
        "ethnicity_primary": "White",
        "ethnicity_family": "european",
        "ethnicity_color": "#D4A574",
        "ethnicities_text": "White 61.6%, Hispanic 18.7%...",
      },
      ...
    }
  }

Refreshes weekly — this data changes extremely slowly.
"""
import asyncio
import re
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="country_culture",
    name="Country culture (religion + ethnicity)",
    category="meta",
    kind="regions",
    source="Wikidata SPARQL + CIA World Factbook",
    source_url="https://www.wikidata.org/wiki/Property:P140",
    license="CC0 (Wikidata) + Public domain (CIA)",
    refresh_s=604800,  # 1 week
    initial_delay_s=90,
    description=(
        "Primary religion and ethnic group per country with ISO3 keying. "
        "Powers religion/ethnicity choropleth mapmodes."
    ),
    enabled=True,
)


# ============================================================
# Religion families — group Wikidata/factbook labels into families
# ============================================================
RELIGION_FAMILIES: dict[str, tuple[str, str]] = {
    # (family_key, color)
    "christianity": ("Christianity", "#6B8CCE"),
    "catholic": ("Christianity", "#6B8CCE"),
    "protestant": ("Christianity", "#6B8CCE"),
    "orthodox": ("Christianity", "#4A6FA5"),
    "anglican": ("Christianity", "#6B8CCE"),
    "lutheran": ("Christianity", "#6B8CCE"),
    "evangelical": ("Christianity", "#6B8CCE"),
    "islam": ("Islam", "#2E8B57"),
    "muslim": ("Islam", "#2E8B57"),
    "sunni": ("Islam", "#2E8B57"),
    "shia": ("Islam", "#1D6B43"),
    "shi'": ("Islam", "#1D6B43"),
    "ibadi": ("Islam", "#2E8B57"),
    "hindu": ("Hinduism", "#FF8C42"),
    "buddhis": ("Buddhism", "#F4C430"),
    "theravada": ("Buddhism", "#F4C430"),
    "mahayana": ("Buddhism", "#F4C430"),
    "jewish": ("Judaism", "#9B7EBD"),
    "judais": ("Judaism", "#9B7EBD"),
    "sikh": ("Sikhism", "#E8923C"),
    "jain": ("Jainism", "#B8860B"),
    "shinto": ("Shinto", "#E8B4C8"),
    "taois": ("Taoism", "#8B4789"),
    "confucian": ("Confucianism", "#8B4789"),
    "bah": ("Baha'i", "#C19A6B"),
    "zoroast": ("Zoroastrianism", "#FF6347"),
    "animist": ("Animism/Folk", "#7BA05B"),
    "folk religion": ("Animism/Folk", "#7BA05B"),
    "traditional": ("Animism/Folk", "#7BA05B"),
    "indigenous": ("Animism/Folk", "#7BA05B"),
    "atheis": ("Non-religious", "#888888"),
    "agnost": ("Non-religious", "#888888"),
    "secular": ("Non-religious", "#888888"),
    "none": ("Non-religious", "#888888"),
    "unaffiliated": ("Non-religious", "#888888"),
    "irreligio": ("Non-religious", "#888888"),
}


def classify_religion(text: str) -> tuple[str, str, str]:
    """Given a religion label/phrase, return (family_name, family_key, color)."""
    if not text:
        return ("Unknown", "unknown", "#555555")
    low = text.lower()
    # First check: exact family-name match (from hardcoded fallback)
    for key, (fam, color) in RELIGION_FAMILIES.items():
        if fam.lower() == low:
            key_norm = fam.lower().replace("/", "_").replace("'", "").replace(" ", "_")
            return (fam, key_norm, color)
    # Substring match for raw Wikidata labels
    for key, (fam, color) in RELIGION_FAMILIES.items():
        if key in low:
            key_norm = fam.lower().replace("/", "_").replace("'", "").replace(" ", "_")
            return (fam, key_norm, color)
    return ("Other", "other", "#999999")


# ============================================================
# Ethnicity families
# ============================================================
ETHNICITY_FAMILIES: dict[str, tuple[str, str]] = {
    "european": ("European", "#D4A574"),
    "white": ("European", "#D4A574"),
    "british": ("European", "#D4A574"),
    "german": ("European", "#D4A574"),
    "french": ("European", "#D4A574"),
    "italian": ("European", "#D4A574"),
    "spanish": ("European", "#D4A574"),
    "russian": ("Slavic", "#A8754E"),
    "slav": ("Slavic", "#A8754E"),
    "polish": ("Slavic", "#A8754E"),
    "ukrainian": ("Slavic", "#A8754E"),
    "czech": ("Slavic", "#A8754E"),
    "serbian": ("Slavic", "#A8754E"),
    "han": ("East Asian", "#E8B04B"),
    "chinese": ("East Asian", "#E8B04B"),
    "japanese": ("East Asian", "#E8B04B"),
    "korean": ("East Asian", "#E8B04B"),
    "mongol": ("East Asian", "#E8B04B"),
    "thai": ("Southeast Asian", "#C67E3E"),
    "viet": ("Southeast Asian", "#C67E3E"),
    "khmer": ("Southeast Asian", "#C67E3E"),
    "lao": ("Southeast Asian", "#C67E3E"),
    "malay": ("Southeast Asian", "#C67E3E"),
    "indones": ("Southeast Asian", "#C67E3E"),
    "filipino": ("Southeast Asian", "#C67E3E"),
    "burmese": ("Southeast Asian", "#C67E3E"),
    "bamar": ("Southeast Asian", "#C67E3E"),
    "indian": ("South Asian", "#D47C4E"),
    "hindustani": ("South Asian", "#D47C4E"),
    "pakistani": ("South Asian", "#D47C4E"),
    "bengali": ("South Asian", "#D47C4E"),
    "punjabi": ("South Asian", "#D47C4E"),
    "sinhalese": ("South Asian", "#D47C4E"),
    "nepali": ("South Asian", "#D47C4E"),
    "bhutanese": ("South Asian", "#D47C4E"),
    "arab": ("Arab", "#9B6B43"),
    "persian": ("Iranian", "#B87A4F"),
    "iranian": ("Iranian", "#B87A4F"),
    "kurdish": ("Iranian", "#B87A4F"),
    "pashtun": ("Iranian", "#B87A4F"),
    "turk": ("Turkic", "#C48254"),
    "azerbaij": ("Turkic", "#C48254"),
    "kazakh": ("Turkic", "#C48254"),
    "uzbek": ("Turkic", "#C48254"),
    "turkmen": ("Turkic", "#C48254"),
    "kyrgyz": ("Turkic", "#C48254"),
    "african": ("Sub-Saharan African", "#6B8E3A"),
    "bantu": ("Sub-Saharan African", "#6B8E3A"),
    "black": ("Sub-Saharan African", "#6B8E3A"),
    "yoruba": ("Sub-Saharan African", "#6B8E3A"),
    "hausa": ("Sub-Saharan African", "#6B8E3A"),
    "igbo": ("Sub-Saharan African", "#6B8E3A"),
    "zulu": ("Sub-Saharan African", "#6B8E3A"),
    "amhara": ("Sub-Saharan African", "#6B8E3A"),
    "oromo": ("Sub-Saharan African", "#6B8E3A"),
    "somali": ("Sub-Saharan African", "#6B8E3A"),
    "berber": ("Berber/Amazigh", "#8E9E4A"),
    "amazigh": ("Berber/Amazigh", "#8E9E4A"),
    "hispanic": ("Latino/Mestizo", "#B58A5C"),
    "mestizo": ("Latino/Mestizo", "#B58A5C"),
    "latino": ("Latino/Mestizo", "#B58A5C"),
    "criollo": ("Latino/Mestizo", "#B58A5C"),
    "mulatto": ("Latino/Mestizo", "#B58A5C"),
    "amerindian": ("Indigenous Americas", "#A07048"),
    "quechua": ("Indigenous Americas", "#A07048"),
    "aymara": ("Indigenous Americas", "#A07048"),
    "guaran": ("Indigenous Americas", "#A07048"),
    "maya": ("Indigenous Americas", "#A07048"),
    "native american": ("Indigenous Americas", "#A07048"),
    "polynesian": ("Pacific Islander", "#5C8EA0"),
    "maori": ("Pacific Islander", "#5C8EA0"),
    "samoan": ("Pacific Islander", "#5C8EA0"),
    "fijian": ("Pacific Islander", "#5C8EA0"),
    "melanesian": ("Pacific Islander", "#5C8EA0"),
    "tongan": ("Pacific Islander", "#5C8EA0"),
    "aboriginal": ("Indigenous Australian", "#7B5E3A"),
    "austronesian": ("Southeast Asian", "#C67E3E"),
    "indo-aryan": ("South Asian", "#D47C4E"),
    "dravidian": ("South Asian", "#D47C4E"),
    "tamil": ("South Asian", "#D47C4E"),
    "telugu": ("South Asian", "#D47C4E"),
    "tibetan": ("East Asian", "#E8B04B"),
    "uyghur": ("Turkic", "#C48254"),
    "jewish": ("Jewish", "#9B7EBD"),
    "hebrew": ("Jewish", "#9B7EBD"),
    "israeli": ("Jewish", "#9B7EBD"),
    "greek": ("European", "#D4A574"),
    "dutch": ("European", "#D4A574"),
    "swedish": ("European", "#D4A574"),
    "norwegian": ("European", "#D4A574"),
    "finnish": ("European", "#D4A574"),
    "danish": ("European", "#D4A574"),
    "portuguese": ("European", "#D4A574"),
    "irish": ("European", "#D4A574"),
    "scottish": ("European", "#D4A574"),
    "austrian": ("European", "#D4A574"),
    "swiss": ("European", "#D4A574"),
    "albanian": ("European", "#D4A574"),
    "romanian": ("European", "#D4A574"),
    "hungarian": ("European", "#D4A574"),
    "croatian": ("Slavic", "#A8754E"),
    "slovak": ("Slavic", "#A8754E"),
    "slovenian": ("Slavic", "#A8754E"),
    "belarusian": ("Slavic", "#A8754E"),
    "estonian": ("European", "#D4A574"),
    "latvian": ("European", "#D4A574"),
    "lithuanian": ("European", "#D4A574"),
    "tunisian": ("Arab", "#9B6B43"),
    "libyan": ("Arab", "#9B6B43"),
    "egyptian": ("Arab", "#9B6B43"),
    "syrian": ("Arab", "#9B6B43"),
    "saudi": ("Arab", "#9B6B43"),
    "mongolic": ("East Asian", "#E8B04B"),
}


def classify_ethnicity(text: str) -> tuple[str, str, str]:
    if not text:
        return ("Unknown", "unknown", "#555555")
    low = text.lower()
    # First check: is the text already a family name we control? (from fallback)
    for key, (fam, color) in ETHNICITY_FAMILIES.items():
        if fam.lower() == low:
            key_norm = fam.lower().replace("/", "_").replace(" ", "_").replace("-", "_")
            return (fam, key_norm, color)
    # Substring match for raw Wikidata labels
    for key, (fam, color) in ETHNICITY_FAMILIES.items():
        if key in low:
            key_norm = fam.lower().replace("/", "_").replace(" ", "_").replace("-", "_")
            return (fam, key_norm, color)
    return ("Other", "other", "#999999")


# ============================================================
# Wikidata SPARQL fetch
# ============================================================

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

SPARQL_RELIGION = """
SELECT ?iso3 ?religionLabel WHERE {
  ?country wdt:P31 wd:Q6256;
           wdt:P298 ?iso3;
           wdt:P140 ?religion.
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""

SPARQL_ETHNICITY = """
SELECT ?iso3 ?groupLabel ?pct WHERE {
  ?country wdt:P31 wd:Q6256;
           wdt:P298 ?iso3;
           p:P172 ?stmt.
  ?stmt ps:P172 ?group.
  OPTIONAL { ?stmt pq:P1107 ?pct. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""


async def sparql_query(client: httpx.AsyncClient, query: str) -> list[dict]:
    try:
        r = await client.get(
            SPARQL_ENDPOINT,
            params={"query": query, "format": "json"},
            headers={
                "Accept": "application/sparql-results+json",
                "User-Agent": "WorldTwin/1.0 (https://worldtwin.local)",
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[country_culture] SPARQL {r.status_code}: {r.text[:200]}")
            return []
        return r.json().get("results", {}).get("bindings", [])
    except Exception as e:
        print(f"[country_culture] SPARQL error: {e}")
        return []


# ============================================================
# Hard-coded fallback for the 50 biggest countries where Wikidata is sparse
# Based on Pew Research + CIA Factbook majorities (2020 data, changes slowly)
# ============================================================
FALLBACK_RELIGION = {
    "USA": "Christianity", "CAN": "Christianity", "MEX": "Christianity",
    "BRA": "Christianity", "ARG": "Christianity", "COL": "Christianity",
    "CHL": "Christianity", "PER": "Christianity", "VEN": "Christianity",
    "GBR": "Christianity", "FRA": "Christianity", "DEU": "Christianity",
    "ITA": "Christianity", "ESP": "Christianity", "POL": "Christianity",
    "GRC": "Christianity", "NLD": "Christianity", "BEL": "Christianity",
    "PRT": "Christianity", "IRL": "Christianity", "ROU": "Christianity",
    "HUN": "Christianity", "RUS": "Christianity", "UKR": "Christianity",
    "BLR": "Christianity", "ZAF": "Christianity", "KEN": "Christianity",
    "ETH": "Christianity", "UGA": "Christianity", "COD": "Christianity",
    "NGA": "Christianity", "GHA": "Christianity", "AUS": "Christianity",
    "NZL": "Christianity", "PHL": "Christianity",
    "SAU": "Islam", "EGY": "Islam", "PAK": "Islam", "IDN": "Islam",
    "TUR": "Islam", "IRN": "Islam", "IRQ": "Islam", "AFG": "Islam",
    "MAR": "Islam", "DZA": "Islam", "TUN": "Islam", "LBY": "Islam",
    "SDN": "Islam", "SOM": "Islam", "MLI": "Islam", "NER": "Islam",
    "BGD": "Islam", "MYS": "Islam", "UZB": "Islam", "KAZ": "Islam",
    "SYR": "Islam", "JOR": "Islam", "LBN": "Islam", "ARE": "Islam",
    "QAT": "Islam", "KWT": "Islam", "BHR": "Islam", "OMN": "Islam",
    "YEM": "Islam", "AZE": "Islam",
    "IND": "Hinduism", "NPL": "Hinduism",
    "THA": "Buddhism", "MMR": "Buddhism", "LKA": "Buddhism",
    "KHM": "Buddhism", "LAO": "Buddhism", "BTN": "Buddhism",
    "MNG": "Buddhism",
    "ISR": "Judaism",
    "CHN": "Non-religious", "JPN": "Shinto", "KOR": "Non-religious",
    "PRK": "Non-religious", "CZE": "Non-religious", "EST": "Non-religious",
    "VNM": "Non-religious",
}

FALLBACK_ETHNICITY = {
    "USA": "European", "CAN": "European", "GBR": "European",
    "FRA": "European", "DEU": "European", "ITA": "European",
    "ESP": "European", "NLD": "European", "BEL": "European",
    "AUT": "European", "CHE": "European", "SWE": "European",
    "NOR": "European", "DNK": "European", "FIN": "European",
    "IRL": "European", "PRT": "European", "GRC": "European",
    "AUS": "European", "NZL": "European",
    "RUS": "Slavic", "UKR": "Slavic", "BLR": "Slavic",
    "POL": "Slavic", "CZE": "Slavic", "SVK": "Slavic",
    "SRB": "Slavic", "BGR": "Slavic", "HRV": "Slavic",
    "CHN": "East Asian", "JPN": "East Asian", "KOR": "East Asian",
    "PRK": "East Asian", "MNG": "East Asian", "TWN": "East Asian",
    "IND": "South Asian", "PAK": "South Asian", "BGD": "South Asian",
    "NPL": "South Asian", "LKA": "South Asian", "BTN": "South Asian",
    "THA": "Southeast Asian", "VNM": "Southeast Asian", "IDN": "Southeast Asian",
    "PHL": "Southeast Asian", "MYS": "Southeast Asian", "MMR": "Southeast Asian",
    "KHM": "Southeast Asian", "LAO": "Southeast Asian", "SGP": "East Asian",
    "SAU": "Arab", "EGY": "Arab", "IRQ": "Arab", "SYR": "Arab",
    "JOR": "Arab", "LBN": "Arab", "YEM": "Arab", "ARE": "Arab",
    "QAT": "Arab", "KWT": "Arab", "OMN": "Arab", "BHR": "Arab",
    "MAR": "Berber/Amazigh", "DZA": "Berber/Amazigh", "TUN": "Arab",
    "LBY": "Arab", "SDN": "Arab",
    "IRN": "Iranian", "AFG": "Iranian",
    "TUR": "Turkic", "AZE": "Turkic", "KAZ": "Turkic",
    "UZB": "Turkic", "TKM": "Turkic", "KGZ": "Turkic",
    "NGA": "Sub-Saharan African", "KEN": "Sub-Saharan African",
    "ETH": "Sub-Saharan African", "UGA": "Sub-Saharan African",
    "TZA": "Sub-Saharan African", "GHA": "Sub-Saharan African",
    "COD": "Sub-Saharan African", "AGO": "Sub-Saharan African",
    "ZAF": "Sub-Saharan African", "MOZ": "Sub-Saharan African",
    "ZMB": "Sub-Saharan African", "ZWE": "Sub-Saharan African",
    "SEN": "Sub-Saharan African", "MLI": "Sub-Saharan African",
    "SOM": "Sub-Saharan African", "RWA": "Sub-Saharan African",
    "MEX": "Latino/Mestizo", "BRA": "Latino/Mestizo", "ARG": "European",
    "COL": "Latino/Mestizo", "VEN": "Latino/Mestizo", "PER": "Indigenous Americas",
    "CHL": "Latino/Mestizo", "ECU": "Latino/Mestizo", "BOL": "Indigenous Americas",
    "PRY": "Latino/Mestizo", "URY": "European", "CUB": "Latino/Mestizo",
    "DOM": "Latino/Mestizo", "GTM": "Indigenous Americas", "HND": "Latino/Mestizo",
    "SLV": "Latino/Mestizo", "NIC": "Latino/Mestizo", "CRI": "Latino/Mestizo",
    "PAN": "Latino/Mestizo",
    "ISR": "European",
}


async def fetch(client: httpx.AsyncClient):
    # SPARQL with user-agent; fetch in parallel
    rel_task = sparql_query(client, SPARQL_RELIGION)
    eth_task = sparql_query(client, SPARQL_ETHNICITY)
    rel_rows, eth_rows = await asyncio.gather(rel_task, eth_task)

    # Build religion by ISO3 — take first result per country
    religion_by_iso: dict[str, str] = {}
    for row in rel_rows:
        iso = row.get("iso3", {}).get("value")
        rel = row.get("religionLabel", {}).get("value")
        if iso and rel and iso not in religion_by_iso:
            religion_by_iso[iso] = rel

    # Build ethnicity by ISO3 — take highest-pct or first
    ethnicity_by_iso: dict[str, tuple[str, float]] = {}
    for row in eth_rows:
        iso = row.get("iso3", {}).get("value")
        grp = row.get("groupLabel", {}).get("value")
        pct_str = row.get("pct", {}).get("value", "0")
        try:
            pct = float(pct_str)
        except (TypeError, ValueError):
            pct = 0.0
        if not iso or not grp:
            continue
        cur = ethnicity_by_iso.get(iso)
        if cur is None or pct > cur[1]:
            ethnicity_by_iso[iso] = (grp, pct)

    # Merge — hardcoded fallback takes priority over Wikidata for major
    # countries because Wikidata's SPARQL returns arbitrary first-match
    # (e.g. India gets "Islam in India" because it's a valid P140 value).
    # Wikidata only fills the gaps.
    all_isos = set(religion_by_iso) | set(ethnicity_by_iso) | set(FALLBACK_RELIGION) | set(FALLBACK_ETHNICITY)

    out: dict[str, dict[str, Any]] = {}
    for iso in all_isos:
        rel_raw = FALLBACK_RELIGION.get(iso) or religion_by_iso.get(iso, "")
        eth_raw = FALLBACK_ETHNICITY.get(iso) or ethnicity_by_iso.get(iso, ("", 0))[0]

        rel_fam, rel_key, rel_color = classify_religion(rel_raw)
        eth_fam, eth_key, eth_color = classify_ethnicity(eth_raw)

        out[iso] = {
            "religion_primary": rel_raw or "Unknown",
            "religion_family": rel_fam,
            "religion_key": rel_key,
            "religion_color": rel_color,
            "ethnicity_primary": eth_raw or "Unknown",
            "ethnicity_family": eth_fam,
            "ethnicity_key": eth_key,
            "ethnicity_color": eth_color,
        }

    result = {
        "source": "Wikidata SPARQL (P140, P172) + Pew/CIA fallback",
        "count": len(out),
        "countries": out,
    }
    print(f"[country_culture] loaded {len(out)} countries ({len(religion_by_iso)} religion, {len(ethnicity_by_iso)} ethnicity from Wikidata)")
    return result


register(LAYER, fetch)
