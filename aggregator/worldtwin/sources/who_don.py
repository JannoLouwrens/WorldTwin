"""WHO Disease Outbreak News — ongoing global disease outbreaks.

Free RSS feed with geocoded disease alerts. Covers epidemics, emerging
infectious diseases, and WHO-verified outbreak reports per country.
"""
import re
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from ..models import LayerMeta
from ..registry import register
from . import _comtrade_common as cc


LAYER = LayerMeta(
    id="who_don",
    name="WHO Disease Outbreak News",
    category="health",
    kind="points",
    source="World Health Organization — Disease Outbreak News",
    source_url="https://www.who.int/feeds/entity/csr/don/en/rss.xml",
    license="CC BY-NC-SA 3.0 IGO",
    refresh_s=21600,  # 6h
    initial_delay_s=120,
    max_staleness_s=30 * 86400,  # WHO posts DONs on an irregular cadence
    description="Ongoing global disease outbreaks with WHO verification.",
    requires_key=False,
    enabled=True,
)


async def fetch(client: httpx.AsyncClient):
    try:
        # PRIMARY: the JSON API, explicitly ordered newest-first. Without
        # $orderby the API serves oldest-first from 1997, so the layer
        # presented 2025-02 as "current" outbreak news (MASTER_PLAN §4
        # health/who_don; verified 2026-09-28: top item is the 2026-09-25
        # Ebola/Bundibugyo DRC entry).
        r = await client.get(
            "https://www.who.int/api/news/diseaseoutbreaknews",
            params={
                "$orderby": "PublicationDateAndTime desc",
                "$top": "50",
                "$format": "json",
            },
            timeout=45,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code == 200:
            data = r.json()
            items = data.get("value") or data.get("items") or []
            outbreaks = []
            for item in items:
                title = item.get("Title") or item.get("title", "")
                desc = item.get("ShortDescription") or item.get("description", "")
                date = item.get("PublicationDateAndTime") or item.get("pubDate", "")
                url = item.get("ItemDefaultUrl") or item.get("link", "")
                # Try to infer country from title
                country_iso3 = _infer_country(title)
                coords = cc.coords_for_iso3(country_iso3) if country_iso3 else None
                outbreaks.append({
                    "title": title,
                    "description": desc[:400],
                    "date": date,
                    "url": url if url.startswith("http") else f"https://www.who.int{url}",
                    "country_iso3": country_iso3,
                    "lat": coords[0] if coords else None,
                    "lon": coords[1] if coords else None,
                })
            outbreaks = [o for o in outbreaks if o["lat"] is not None]
            # Newest first — WHO APIs sometimes return oldest-first
            outbreaks.sort(key=lambda o: (o.get("date") or ""), reverse=True)
            return {
                "source": "WHO DON (JSON API)",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": len(outbreaks),
                "outbreaks": outbreaks,
            }

        # FALLBACK: legacy RSS feed (undated ordering, may lag the API).
        r = await client.get(
            "https://www.who.int/feeds/entity/csr/don/en/rss.xml",
            timeout=45,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        outbreaks = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            date = (item.findtext("pubDate") or "").strip()
            country_iso3 = _infer_country(title)
            coords = cc.coords_for_iso3(country_iso3) if country_iso3 else None
            outbreaks.append({
                "title": title,
                "description": re.sub(r"<[^>]+>", "", desc)[:400],
                "date": date,
                "url": link,
                "country_iso3": country_iso3,
                "lat": coords[0] if coords else None,
                "lon": coords[1] if coords else None,
            })

        outbreaks = [o for o in outbreaks if o.get("lat") is not None]
        # Newest first — RSS pubDate ordering can drift; force descending
        outbreaks.sort(key=lambda o: (o.get("date") or ""), reverse=True)
        return {
            "source": "WHO DON RSS",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(outbreaks),
            "outbreaks": outbreaks,
        }
    except Exception as e:
        print(f"[who_don] error: {e}")
        return None


# WHO titles use formal UN names; COUNTRY_COORDS uses short names ("DR
# Congo", "UAE") that never appear in them. Aliases below map the formal
# spellings WHO actually prints. Matching is LONGEST-WINS across aliases and
# the table together — "Democratic Republic of the Congo" contains both
# "Congo" and "Republic of the Congo" as substrings, and a first-match scan
# geocoded the 2026 DRC Ebola outbreak to COG (observed 2026-09-28).
_WHO_NAME_ALIASES = {
    "democratic republic of the congo": "COD",
    "republic of the congo": "COG",
    "united republic of tanzania": "TZA",
    "united arab emirates": "ARE",
    "united states of america": "USA",
    "united kingdom of great britain and northern ireland": "GBR",
    "syrian arab republic": "SYR",
    "iran (islamic republic of)": "IRN",
    "islamic republic of iran": "IRN",
    "lao people's democratic republic": "LAO",
    "republic of korea": "KOR",
    "democratic people's republic of korea": "PRK",
    "viet nam": "VNM",
    "russian federation": "RUS",
    "côte d'ivoire": "CIV",
    "cote d'ivoire": "CIV",
    "bolivia (plurinational state of)": "BOL",
    "venezuela (bolivarian republic of)": "VEN",
    "republic of moldova": "MDA",
    "türkiye": "TUR",
    "czechia": "CZE",
}


def _infer_country(text: str) -> str:
    """Scan text for a country name, return ISO3. Longest match wins."""
    if not text:
        return ""
    text_lower = text.lower()
    best_iso3, best_len = "", 0
    for alias, iso3 in _WHO_NAME_ALIASES.items():
        if len(alias) > best_len and alias in text_lower:
            best_iso3, best_len = iso3, len(alias)
    for m49, rec in cc.COUNTRY_COORDS.items():
        lat, lon, iso3, name = rec
        if name and len(name) > best_len and name.lower() in text_lower:
            best_iso3, best_len = iso3, len(name)
    return best_iso3


register(LAYER, fetch)
