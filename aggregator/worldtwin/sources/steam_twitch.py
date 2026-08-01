"""Steam Web API (top games by concurrent players) + optional Twitch Helix streams."""
import asyncio
import os

import httpx

from ..models import LayerMeta, point
from ..registry import register

TWITCH_ID = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")

TOP_APPIDS = [
    (730, "Counter-Strike 2"), (570, "Dota 2"), (578080, "PUBG"),
    (440, "Team Fortress 2"), (271590, "GTA V"), (252490, "Rust"),
    (1172470, "Apex Legends"), (1086940, "Baldur's Gate 3"),
    (1599340, "Lost Ark"), (359550, "Rainbow Six Siege"),
    (238960, "Path of Exile"), (236390, "War Thunder"),
    (394360, "Hearts of Iron IV"), (892970, "Valheim"),
    (1569040, "Football Manager 2024"), (1245620, "ELDEN RING"),
    (2358720, "Black Myth: Wukong"), (1091500, "Cyberpunk 2077"),
    (2073850, "THE FINALS"), (381210, "Dead by Daylight"),
]

LANG_GEO = {
    "en": (51.5, -0.1, "English"),
    "es": (40.4, -3.7, "Spanish"),
    "pt": (-23.5, -46.6, "Portuguese"),
    "ko": (37.6, 127.0, "Korean"),
    "ru": (55.8, 37.6, "Russian"),
    "de": (52.5, 13.4, "German"),
    "fr": (48.9, 2.3, "French"),
    "ja": (35.7, 139.7, "Japanese"),
    "zh": (31.2, 121.5, "Chinese"),
    "it": (41.9, 12.5, "Italian"),
    "pl": (52.2, 21.0, "Polish"),
    "tr": (41.0, 29.0, "Turkish"),
    "th": (13.8, 100.5, "Thai"),
    "ar": (24.7, 46.7, "Arabic"),
    "nl": (52.4, 4.9, "Dutch"),
}

LAYER = LayerMeta(
    id="gaming",
    name="Gaming (Steam + Twitch)",
    category="gaming",
    kind="raw",  # mixed: top games list + optional regional viewer points
    source="Steam Web API + Twitch Helix (optional)",
    source_url="https://api.steampowered.com/",
    license="Free",
    refresh_s=600,
    initial_delay_s=32,
    description="Top Steam games by concurrent players + Twitch live streams aggregated by language region.",
)


async def fetch(client: httpx.AsyncClient):
    # 1. Steam current-player counts
    sem = asyncio.Semaphore(5)
    top_games = []

    async def fetch_game(appid: int, name: str):
        async with sem:
            try:
                r = await client.get(
                    "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
                    params={"appid": appid},
                    timeout=15,
                )
                if r.status_code == 200:
                    players = r.json().get("response", {}).get("player_count", 0)
                    if players:
                        top_games.append({
                            "appid": appid,
                            "name": name,
                            "players": players,
                            "store": f"https://store.steampowered.com/app/{appid}/",
                        })
            except Exception:
                pass

    await asyncio.gather(*[fetch_game(a, n) for a, n in TOP_APPIDS])
    top_games.sort(key=lambda x: x["players"], reverse=True)

    # 2. Twitch regional aggregation (optional)
    regions = []
    total_streams = 0
    total_viewers = 0
    if TWITCH_ID and TWITCH_SECRET:
        try:
            tok = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": TWITCH_ID,
                    "client_secret": TWITCH_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=15,
            )
            if tok.status_code == 200:
                token = tok.json().get("access_token", "")
                if token:
                    sr = await client.get(
                        "https://api.twitch.tv/helix/streams",
                        params={"first": 100},
                        headers={"Authorization": f"Bearer {token}", "Client-Id": TWITCH_ID},
                        timeout=15,
                    )
                    if sr.status_code == 200:
                        streams = sr.json().get("data", [])
                        total_streams = len(streams)
                        total_viewers = sum(s.get("viewer_count", 0) for s in streams)
                        by_lang: dict[str, dict] = {}
                        for s in streams:
                            lang = s.get("language", "?")
                            if lang not in by_lang:
                                by_lang[lang] = {"viewers": 0, "count": 0, "topGame": ""}
                            by_lang[lang]["viewers"] += s.get("viewer_count", 0)
                            by_lang[lang]["count"] += 1
                            if not by_lang[lang]["topGame"]:
                                by_lang[lang]["topGame"] = s.get("game_name", "")
                        for lang, info in by_lang.items():
                            if lang in LANG_GEO:
                                lat, lon, lname = LANG_GEO[lang]
                                regions.append({
                                    "code": lang, "name": lname,
                                    "lat": lat, "lon": lon,
                                    "viewers": info["viewers"],
                                    "streams": info["count"],
                                    "topGame": info["topGame"],
                                })
                        regions.sort(key=lambda r: r["viewers"], reverse=True)
        except Exception:
            pass

    legacy = {
        "source": "Steam" + (" + Twitch" if TWITCH_ID else ""),
        "totalPlayers": sum(g["players"] for g in top_games),
        "topGames": top_games,
        "regions": regions,
        "totalStreams": total_streams,
        "totalViewers": total_viewers,
    }
    # v1: same shape — this is a 'raw' kind since gaming has mixed data
    return legacy, legacy


register(LAYER, fetch)
