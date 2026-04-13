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
    license="WHO Open",
    refresh_s=21600,  # 6h
    initial_delay_s=120,
    description="Ongoing global disease outbreaks with WHO verification.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    try:
        r = await client.get(
            "https://www.who.int/feeds/entity/csr/don/en/rss.xml",
            timeout=45,
            headers={"User-Agent": "WorldTwin/1.0"},
        )
        if r.status_code != 200:
            # Fallback: HTML page scrape of /emergencies/disease-outbreak-news
            r = await client.get(
                "https://www.who.int/api/news/diseaseoutbreaknews",
                timeout=45,
                headers={"User-Agent": "WorldTwin/1.0"},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            items = data.get("value") or data.get("items") or []
            outbreaks = []
            for item in items[:50]:
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
            return {
                "source": "WHO DON (JSON API)",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": len(outbreaks),
                "outbreaks": outbreaks,
            }

        # RSS path
        root = ET.fromstring(r.text)
        items = root.findall(".//item")
        outbreaks = []
        for item in items[:50]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            desc = (item.findtext("description") or "").strip()
            date = (item.findtext("pubDate") or "").strip()
            country_iso3 = ""
            coords = None
            # Scan the text for a country name match
            title_lower = title.lower()
            for m49, rec in cc.COUNTRY_COORDS.items():
                lat, lon, iso3, name = rec
                if name and name.lower() in title_lower:
                    coords = (lat, lon)
                    country_iso3 = iso3
                    break
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
        return {
            "source": "WHO DON RSS",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": len(outbreaks),
            "outbreaks": outbreaks,
        }
    except Exception as e:
        print(f"[who_don] error: {e}")
        return None


def _infer_country(text: str) -> str:
    """Naive: scan text for a country name, return ISO3."""
    if not text:
        return ""
    text_lower = text.lower()
    for m49, rec in cc.COUNTRY_COORDS.items():
        lat, lon, iso3, name = rec
        if name and name.lower() in text_lower:
            return iso3
    return ""


register(LAYER, fetch)
