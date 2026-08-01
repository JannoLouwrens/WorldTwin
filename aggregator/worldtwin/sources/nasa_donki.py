"""NASA DONKI — Space Weather Events (full 2010→present archive on first run).

On first run (no marker file) we pull the full DONKI archive back to 2010
in 6-month chunks — 7 event types × ~30 chunks = ~210 requests, takes
~30 minutes. The events land in the History Store via decompose; the
marker file `/cache/.donki_backfill_done` records that we did it.

Subsequent fetches (every 24h) only pull the last ~30 days so we hit ~7
API calls instead of ~210 per refresh — way under the 1000/hr NASA quota
and easy on the network. The History Store keeps the deep history because
INSERT OR IGNORE on (source_id, observed_at, fetched_at) is idempotent.
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx
from ..models import LayerMeta
from ..registry import register

NASA_API_KEY = os.environ.get("NASA_API_KEY", "")
MARKER = Path(os.environ.get("CACHE_DIR", "/cache")) / ".donki_backfill_done"

LAYER = LayerMeta(
    id="nasa_donki",
    name="NASA DONKI — Space Weather Events",
    category="space",
    kind="points",
    source="NASA DONKI",
    source_url="https://api.nasa.gov/DONKI/",
    license="Public Domain (NASA)",
    refresh_s=86400,        # was 3600 — full 2010+ archive is heavier; daily refresh is plenty
    initial_delay_s=40,
    description="CME, solar flares, GST, SEP, radiation belt, interplanetary shock, high-speed stream — FULL DONKI archive 2010 → present, paginated in 6-month chunks.",
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
    # First run: deep backfill 2010 → present. Subsequent runs: last 30 days.
    if MARKER.exists():
        start_dt = end - timedelta(days=30)
        mode = "incremental"
    else:
        start_dt = datetime(2010, 1, 1, tzinfo=timezone.utc)
        mode = "deep_backfill"
    print(f"[nasa_donki] {mode}: {start_dt.date()} → {end.date()}")

    def _chunks(start_dt, end_dt, days=180):
        c = start_dt
        while c < end_dt:
            n = min(c + timedelta(days=days), end_dt)
            yield c.strftime("%Y-%m-%d"), n.strftime("%Y-%m-%d")
            c = n

    sem = asyncio.Semaphore(3)
    all_events = []
    failed_chunks = 0

    async def _fetch_chunk(code, endpoint, start_str, end_str):
        nonlocal failed_chunks
        async with sem:
            try:
                r = None
                for attempt in range(3):
                    r = await client.get(
                        f"https://api.nasa.gov/DONKI/{endpoint}",
                        params={"startDate": start_str, "endDate": end_str, "api_key": NASA_API_KEY},
                        timeout=45,
                    )
                    if r.status_code == 503:
                        await asyncio.sleep(5)
                        continue
                    break
                if not r or r.status_code != 200:
                    failed_chunks += 1
                    return
                data = r.json()
                if not isinstance(data, list):
                    failed_chunks += 1
                    return
                for ev in data:
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
                failed_chunks += 1
                print(f"[nasa_donki] {code} {start_str}..{end_str}: {e}")

    tasks = []
    for code, endpoint in EVENT_TYPES:
        for s, e in _chunks(start_dt, end):
            tasks.append(_fetch_chunk(code, endpoint, s, e))
    await asyncio.gather(*tasks)
    all_events.sort(key=lambda x: x.get("start", ""), reverse=True)

    # An empty result with failed chunks is an upstream outage (e.g. DONKI
    # 503), not a quiet sun — raise so the scheduler marks the layer errored
    # and keeps the previous cache instead of caching "0 events" as success.
    if not all_events and failed_chunks:
        raise RuntimeError(
            f"all {failed_chunks}/{len(tasks)} chunks failed or returned no "
            f"events — DONKI likely down; keeping previous cache"
        )

    by_type = {}
    for ev in all_events:
        by_type.setdefault(ev["type"], []).append(ev)

    # Mark deep backfill done so future runs only do incremental — but only
    # if the backfill actually fetched something; otherwise an outage during
    # the first run would permanently skip the 2010+ archive.
    if mode == "deep_backfill" and all_events:
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(datetime.now(timezone.utc).isoformat())
            print(f"[nasa_donki] backfill complete; {MARKER} written")
        except Exception as e:
            print(f"[nasa_donki] failed to write marker: {e}")

    return {
        "source": "NASA DONKI",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(all_events),
        "mode": mode,
        "window_start": start_dt.date().isoformat(),
        "window_end": end.date().isoformat(),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "events": all_events[:200],
    }


register(LAYER, fetch)
