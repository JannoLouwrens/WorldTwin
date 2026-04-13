"""Economy — forex rates (Frankfurter) + crypto (CoinGecko)."""
import httpx

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="economy",
    name="Economy (Forex + Crypto)",
    category="economy",
    kind="raw",  # nested structure
    source="Frankfurter + CoinGecko",
    source_url="https://api.frankfurter.dev/v1/latest",
    license="Free (public)",
    refresh_s=300,
    initial_delay_s=36,
    description="Live forex rates (30+ currencies) and top 25 crypto by market cap.",
)


async def fetch(client: httpx.AsyncClient):
    result: dict = {"source": "Frankfurter + CoinGecko"}
    try:
        r = await client.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"base": "USD"},
            timeout=20,
        )
        if r.status_code == 200:
            result["forex"] = r.json()
    except Exception:
        pass
    try:
        r = await client.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd", "order": "market_cap_desc",
                "per_page": 25, "page": 1, "sparkline": "false",
            },
            timeout=20,
        )
        if r.status_code == 200:
            coins = r.json()
            result["crypto"] = [
                {
                    "id": c.get("id"), "symbol": c.get("symbol"),
                    "name": c.get("name"), "image": c.get("image"),
                    "price_usd": c.get("current_price"),
                    "market_cap": c.get("market_cap"),
                    "change_24h": c.get("price_change_percentage_24h"),
                    "volume": c.get("total_volume"),
                }
                for c in coins
            ]
    except Exception:
        pass
    try:
        r = await client.get("https://api.coingecko.com/api/v3/global", timeout=15)
        if r.status_code == 200:
            data = r.json().get("data", {})
            result["crypto_market_cap"] = data.get("total_market_cap", {}).get("usd")
            result["crypto_volume"] = data.get("total_volume", {}).get("usd")
            result["btc_dominance"] = data.get("market_cap_percentage", {}).get("btc")
    except Exception:
        pass
    if "forex" not in result and "crypto" not in result:
        return None
    return result, result


register(LAYER, fetch)
