"""NASA DONKI — Space Weather Events (90-day lookback).
Previous version used 30 days which often produced 0 events during quiet sun.
Widened to 90 days so the cache always has recent-ish events.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
import httpx
from ..models import LayerMeta
from ..registry import register

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")

LAYER = LayerMeta(
    id="nasa_donki",
    name="NASA DONKI — Space Weather Events",
    category="space",
    kind="points",
    source="NASA DONKI",
    source_url="https://api.nasa.gov/DONKI/",
    license="Public Domain (NASA)",
    refresh_s=3600,
    initial_delay_s=40,
    description="CME, solar flares, GST, SEP, radiation belt, interplanetary shock, high-speed stream (90-day lookback).",
    requires_key=True,
    key_env="NASA_API_KEY",
    enabled=bool(NASA_API_KEY),
)

EVENT_TYPES = [
    ("CME", "CMEAnalysis"),
    ("FLR", "FLR"),
    ("GST", "GST"),
    ("SEP", "SEP"),
    ("RBE", "RBE"),
    ("IPS", "IPS"),
    ("HSS", "HSS"),
]


async def fetch(client: httpx.AsyncClient):
    if not NASA_API_KEY:
        return None
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=90)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    sem = asyncio.Semaphore(3)
    all_events = []

    async def _fetch_type(code, endpoint):
        async with sem:
            try:
                # Retry up to 3 times — DONKI backend has intermittent 503s
                r = None
                for attempt in range(3):
                    r = await client.get(
                        f"https://api.nasa.gov/DONKI/{endpoint}",
                        params={"startDate": start_str, "endDate": end_str, "api_key": NASA_API_KEY},
                        timeout=30,
                    )
                    if r.status_code == 503:
                        await asyncio.sleep(5)  # wait and retry
                        continue
                    break
                if not r or r.status_code != 200:
                    print(f"[nasa_donki] {code}: HTTP {r.status_code if r else 'no response'}")
                    return
                data = r.json()
                if not isinstance(data, list):
                    return
                for ev in data[:100]:
                    severity = 1
                    if code == "CME":
                        speed = ev.get("speed") or ev.get("speed_kms") or 0
                        if isinstance(speed, str):
                            try: speed = float(speed)
                            except: speed = 0
                        if speed > 1500: severity = 5
                        elif speed > 1000: severity = 4
                        elif speed > 600: severity = 3
                        elif speed > 300: severity = 2
                    elif code == "FLR":
                        cls = (ev.get("classType") or "")[:1]
                        severity = {"X": 5, "M": 4, "C": 3, "B": 2}.get(cls, 1)
                    elif code == "GST":
                        kp_list = ev.get("allKpIndex") or []
                        max_kp = 0
                        for k in kp_list:
                            kp = k.get("kpIndex", 0) if isinstance(k, dict) else 0
                            if isinstance(kp, (int, float)) and kp > max_kp:
                                max_kp = kp
                        severity = min(5, max(1, int(max_kp) - 3))

                    all_events.append({
                        "type": code,
                        "start": ev.get("startTime") or ev.get("beginTime") or ev.get("eventTime", ""),
                        "end": ev.get("endTime") or ev.get("peakTime", ""),
                        "severity": severity,
                        "lat": 0,
                        "lon": 0,
                        "detail": str(ev.get("note") or ev.get("classType") or ev.get("type", ""))[:200],
                        "link": ev.get("link", ""),
                    })
            except Exception as e:
                print(f"[nasa_donki] {code}: {e}")

    await asyncio.gather(*[_fetch_type(c, e) for c, e in EVENT_TYPES])
    all_events.sort(key=lambda x: x.get("start", ""), reverse=True)

    by_type = {}
    for ev in all_events:
        by_type.setdefault(ev["type"], []).append(ev)

    return {
        "source": "NASA DONKI",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(all_events),
        "lookback_days": 90,
        "by_type": {k: len(v) for k, v in by_type.items()},
        "events": all_events[:200],
    }


register(LAYER, fetch)
