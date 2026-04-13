"""ESPN unofficial public API — live sports scoreboards."""
import asyncio

import httpx

from ..models import LayerMeta, point
from ..registry import register

LEAGUES = [
    ("soccer/eng.1",       "Premier League",  "soccer"),
    ("soccer/esp.1",       "La Liga",         "soccer"),
    ("soccer/ita.1",       "Serie A",         "soccer"),
    ("soccer/ger.1",       "Bundesliga",      "soccer"),
    ("soccer/fra.1",       "Ligue 1",         "soccer"),
    ("soccer/uefa.champions", "UCL",          "soccer"),
    ("basketball/nba",     "NBA",             "basketball"),
    ("football/nfl",       "NFL",             "football"),
    ("baseball/mlb",       "MLB",             "baseball"),
    ("hockey/nhl",         "NHL",             "hockey"),
    ("racing/f1",          "Formula 1",       "f1"),
    ("tennis/atp",         "ATP Tour",        "tennis"),
    ("cricket/all",        "Cricket",         "cricket"),
]

CITY_COORDS = {
    "London": (51.5, -0.1), "Madrid": (40.4, -3.7), "Manchester": (53.5, -2.2),
    "Liverpool": (53.4, -3.0), "Barcelona": (41.4, 2.2), "Milan": (45.5, 9.2),
    "Rome": (41.9, 12.5), "Munich": (48.1, 11.6), "Berlin": (52.5, 13.4),
    "Paris": (48.9, 2.3), "Lyon": (45.8, 4.8), "Amsterdam": (52.4, 4.9),
    "Lisbon": (38.7, -9.1), "Istanbul": (41.0, 29.0), "New York": (40.7, -74.0),
    "Boston": (42.4, -71.1), "Los Angeles": (34.1, -118.2), "Chicago": (41.9, -87.6),
    "Miami": (25.8, -80.2), "Dallas": (32.8, -96.8), "Houston": (29.8, -95.4),
    "Atlanta": (33.7, -84.4), "Philadelphia": (40.0, -75.2), "Detroit": (42.3, -83.0),
    "Toronto": (43.7, -79.4), "Montreal": (45.5, -73.6), "Vancouver": (49.3, -123.1),
    "Mexico City": (19.4, -99.1), "Sao Paulo": (-23.5, -46.6), "Rio de Janeiro": (-22.9, -43.2),
    "Buenos Aires": (-34.6, -58.4), "Tokyo": (35.7, 139.7), "Osaka": (34.7, 135.5),
    "Seoul": (37.6, 127.0), "Sydney": (-33.9, 151.2), "Melbourne": (-37.8, 145.0),
    "Monaco": (43.7, 7.4), "Dubai": (25.2, 55.3), "Doha": (25.3, 51.5),
    "Singapore": (1.3, 103.8), "Mumbai": (19.1, 72.9), "Delhi": (28.6, 77.2),
    "Johannesburg": (-26.2, 28.0), "Cape Town": (-33.9, 18.4),
    "Seattle": (47.6, -122.3), "Phoenix": (33.4, -112.1), "Denver": (39.7, -105.0),
    "Minneapolis": (45.0, -93.3), "Tampa": (27.9, -82.5), "Orlando": (28.5, -81.4),
}

LAYER = LayerMeta(
    id="sports",
    name="Live Sports",
    category="sports",
    kind="points",
    source="ESPN (unofficial public endpoints)",
    source_url="https://site.api.espn.com/apis/site/v2/sports/",
    license="Public (unofficial)",
    refresh_s=300,
    initial_delay_s=34,
    description="Live scores and schedules from football, soccer, basketball, F1, tennis, cricket and more.",
)


async def fetch(client: httpx.AsyncClient):
    matches = []
    sem = asyncio.Semaphore(6)

    async def fetch_league(path: str, name: str, sport: str):
        async with sem:
            try:
                r = await client.get(
                    f"https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard",
                    timeout=20,
                )
                if r.status_code != 200:
                    return
                data = r.json()
                for event in (data.get("events") or [])[:15]:
                    try:
                        comp = (event.get("competitions") or [{}])[0]
                        competitors = comp.get("competitors", [])
                        if len(competitors) < 2:
                            continue
                        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
                        venue = comp.get("venue") or {}
                        addr = venue.get("address") or {}
                        city = addr.get("city", "")
                        status = (event.get("status") or {}).get("type") or {}
                        matches.append({
                            "league": name,
                            "sport": sport,
                            "home": ((home.get("team") or {}).get("displayName")) or "?",
                            "away": ((away.get("team") or {}).get("displayName")) or "?",
                            "homeScore": home.get("score", ""),
                            "awayScore": away.get("score", ""),
                            "venue": venue.get("fullName", "") or city,
                            "city": city,
                            "country": addr.get("country", ""),
                            "state": status.get("name", ""),
                            "completed": status.get("completed", False),
                            "date": event.get("date", ""),
                        })
                    except Exception:
                        continue
            except Exception:
                pass

    await asyncio.gather(*[fetch_league(p, n, s) for p, n, s in LEAGUES])

    points = []
    legacy_matches = []
    for m in matches:
        coords = CITY_COORDS.get(m.get("city", ""))
        if not coords:
            continue
        lat, lon = coords
        m["lat"] = lat
        m["lon"] = lon
        legacy_matches.append(m)
        points.append(point(
            lat=lat, lon=lon,
            label=f"{m['home']} {m['homeScore']}-{m['awayScore']} {m['away']}",
            league=m["league"],
            sport=m["sport"],
            home=m["home"], away=m["away"],
            home_score=m["homeScore"], away_score=m["awayScore"],
            venue=m["venue"], city=m["city"],
            state=m["state"], completed=m["completed"],
        ))

    legacy = {
        "source": "ESPN",
        "matches": legacy_matches,
        "total": len(matches),
        "geocoded": len(legacy_matches),
    }
    return points, legacy


register(LAYER, fetch)
