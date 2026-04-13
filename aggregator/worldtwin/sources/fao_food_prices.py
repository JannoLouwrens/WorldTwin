"""FAO Food Price Index — monthly, global.

Free. World food prices cereals/oils/dairy/meat/sugar + FAOSTAT food price
index for major countries.
"""
from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register


LAYER = LayerMeta(
    id="fao_food_prices",
    name="FAO Food Price Index",
    category="economy",
    kind="raw",
    source="FAO",
    source_url="https://www.fao.org/worldfoodsituation/foodpricesindex/en/",
    license="Free with attribution",
    refresh_s=86400 * 7,
    initial_delay_s=385,
    description="FAO monthly world food price index (cereals, oils, dairy, meat, sugar) — recession/food-security signal.",
    requires_key=False,
)


async def fetch(client: httpx.AsyncClient):
    # FAO publishes the index as a CSV here; graceful fallback if URL moves
    urls = [
        "https://www.fao.org/images/worldfoodsituationlibraries/default-document-library/food_price_indices_data_apr26.csv",
        "https://www.fao.org/fileadmin/templates/worldfood/Reports_and_docs/Food_price_indices_data.csv",
    ]
    for url in urls:
        try:
            r = await client.get(url, timeout=45, headers={"User-Agent": "WorldTwin/1.0"})
            if r.status_code != 200:
                continue
            # FAO files vary in format — keep raw text, client can parse
            return {
                "source": "FAO Food Price Index",
                "fetched": datetime.now(timezone.utc).isoformat(),
                "count": 1,
                "raw_csv": r.text[:50000],
                "url": url,
            }
        except Exception:
            continue
    # No luck — return a stub so the layer registers as empty but present
    return {
        "source": "FAO Food Price Index",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": 0,
        "note": "FAO CSV endpoint moved; manual update required",
    }


register(LAYER, fetch)
