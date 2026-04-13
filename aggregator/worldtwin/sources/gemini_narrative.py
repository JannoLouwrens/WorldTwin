"""Gemini world narrative — every 30 min, summarise top 30 events into 3 paragraphs.

Calls Gemini via the REST API (no SDK dep) using GEMINI_API_KEY.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))


LAYER = LayerMeta(
    id="gemini_narrative",
    name="WorldTwin Analyst — Gemini narrative",
    category="meta",
    kind="raw",
    source="Gemini 2.5 Flash",
    source_url="https://generativelanguage.googleapis.com/",
    license="Inferred from source events",
    refresh_s=1800,
    initial_delay_s=405,
    description="Three-paragraph summary of the world: today at a glance, biggest risk, trend of the week.",
    requires_key=True,
    key_env="GEMINI_API_KEY",
    enabled=bool(GEMINI_API_KEY),
)


def _read_cache(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


async def fetch(client: httpx.AsyncClient):
    if not GEMINI_API_KEY:
        return None

    events = _read_cache("global_events") or {}
    pulse = _read_cache("pulse_mode") or {}
    gdacs = _read_cache("gdacs_events") or {}

    top_events = (events.get("events") or [])[:30]
    top_concerning = (pulse.get("top_concerning") or [])[:10]
    top_hazards = (gdacs.get("events") or [])[:8]

    # Compact prompt
    prompt = (
        "You are a global intelligence analyst writing for a 3D world-state dashboard.\n"
        "Write exactly 3 short paragraphs (~60 words each), with NO headings, NO preamble, and NO bullet points.\n\n"
        "Paragraph 1 — 'Today at a glance': what is happening in the world right now.\n"
        "Paragraph 2 — 'Biggest risk': what deserves urgent attention.\n"
        "Paragraph 3 — 'Trend of the week': directional signal or quiet deterioration.\n\n"
        f"Top 30 events (severity 1-5):\n{json.dumps(top_events, indent=1)[:4000]}\n\n"
        f"Top concerning countries (pulse radar):\n{json.dumps(top_concerning, indent=1)[:1500]}\n\n"
        f"Top active hazards (GDACS):\n{json.dumps(top_hazards, indent=1)[:1500]}\n\n"
        "Write only the 3 paragraphs."
    )

    try:
        r = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.45,
                    "maxOutputTokens": 900,
                },
            },
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[gemini_narrative] {r.status_code}: {r.text[:200]}")
            return None
        body = r.json()
        text = ""
        candidates = body.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            if parts:
                text = parts[0].get("text", "")
        if not text:
            return None

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        while len(paragraphs) < 3:
            paragraphs.append("")

        return {
            "source": "Gemini 2.5 Flash",
            "fetched": datetime.now(timezone.utc).isoformat(),
            "count": 3,
            "today": paragraphs[0],
            "biggest_risk": paragraphs[1],
            "trend_of_week": paragraphs[2],
            "raw": text,
            "input_events_count": len(top_events),
        }
    except Exception as e:
        print(f"[gemini_narrative] error: {e}")
        return None


register(LAYER, fetch)
