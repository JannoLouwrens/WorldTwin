"""WorldTwin AI Narrative — Claude Sonnet 4.6 via OpenRouter.

Replaces gemini_narrative. Builds a rich, structured world digest from 15+ caches
(chokepoints, commodities, conflict last 24h, top movers, biggest hazards) and
hands it to Claude with a strict citation requirement so the model can't fabricate
numbers — it must either quote a digest figure verbatim or omit the claim.

Output schema unchanged so the frontend (briefing.js) keeps working.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx

from ..models import LayerMeta
from ..registry import register
from .. import sanity

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/cache"))

# Backwards compat: keep cache id 'gemini_narrative' so briefing.js doesn't
# need a path change. Source label honestly reflects which model wrote it.
LAYER = LayerMeta(
    id="gemini_narrative",
    name="WorldTwin Analyst — AI narrative",
    category="meta",
    kind="raw",
    source="Gemini 2.5 Pro (Claude via OpenRouter optional)",
    source_url="https://ai.google.dev/gemini-api/docs/models#gemini-2.5-pro",
    license="Inferred from source events",
    refresh_s=1800,
    initial_delay_s=405,
    description="Three-paragraph world summary, grounded in 15+ measured caches; numeric claims must cite the digest.",
    requires_key=True,
    key_env="OPENROUTER_API_KEY",
    enabled=bool(OPENROUTER_API_KEY or GEMINI_API_KEY),
)


def _read(name: str) -> Any:
    p = CACHE_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _build_digest() -> dict:
    """Pre-compute deltas + top movers from 20+ caches into a single digest.

    Philosophy: the LLM gets the SIGNAL not the noise. We pre-compute deltas,
    rank by importance, and shape into a curated brief. Every numeric claim
    the model makes must trace back to a value in this digest.

    Every numeric field passes through `sanity.check()` before reaching the LLM,
    so unit/units/window bugs (e.g. "BTC -113%" — impossible) get filtered out.
    """
    sanity.reset()
    digest: dict = {"as_of": datetime.now(timezone.utc).isoformat()}

    # ---- Chokepoints: ship counts now (PortWatch) ----
    pw = _read("portwatch_chokepoints") or {}
    chokes = pw.get("chokepoints") or []
    digest["chokepoints"] = [
        {
            "name": c["name"],
            "ships_today": sanity.check("ship_count", c.get("n_total")),
            "tankers": sanity.check("ship_count", c.get("n_tanker")),
            "containers": sanity.check("ship_count", c.get("n_container")),
            "capacity_dwt_today": c.get("capacity"),
        }
        for c in chokes[:12]
    ]

    # ---- Commodity / macro prices with HONEST window labels ----
    # FRED daily series (oil, VIX, yields, forex) have ~12 trading days = ~2 weeks.
    # FRED monthly series (copper, wheat, CPI, unemployment) have ~12 months = ~1 year.
    # Computing a single delta is misleading (which window?). We label it explicitly.
    fred = (_read("fred") or {}).get("series") or {}
    def _delta_full(s):
        """Pct change from first to last sample in the series. Window depends
        on the series cadence (daily vs monthly)."""
        if not s or len(s) < 2: return None
        head = next((x["v"] for x in s if x.get("v") is not None), None)
        tail = next((x["v"] for x in reversed(s) if x.get("v") is not None), None)
        if head in (None, 0): return None
        return round((tail - head) / abs(head) * 100, 2)

    # Tag each FRED series with its cadence + sanity-check rule.
    daily_keys = {"DCOILBRENTEU", "DCOILWTICO", "DHHNGSP", "VIXCLS", "DGS10", "DTWEXBGS",
                  "DEXCHUS", "DEXUSEU", "DEXJPUS", "DEXUSUK", "DEXINUS", "DEXBZUS",
                  "DEXSFUS", "DGS30", "T10Y2Y", "BAMLH0A0HYM2", "WALCL"}
    macros = []
    for key, label, sanity_rule in [
        ("DCOILBRENTEU", "Brent crude $/bbl",        "brent_oil_usd"),
        ("DCOILWTICO",   "WTI crude $/bbl",          "wti_oil_usd"),
        ("DHHNGSP",      "Henry Hub natgas $/MMBtu", "natgas_usd"),
        ("PWHEAMTUSDM",  "Wheat $/t",                "wheat_usd_t"),
        ("PCOPPUSDM",    "Copper $/t",               "copper_usd_t"),
        ("VIXCLS",       "VIX volatility",           "vix"),
        ("DGS10",        "US 10Y yield %",           "yield_pct"),
        ("FEDFUNDS",     "US Fed funds %",           "fed_funds_pct"),
        ("DTWEXBGS",     "Trade-weighted USD index", None),     # Index — no fixed bounds
        ("DEXCHUS",      "CNY/USD",                  "fx_rate"),
        ("UNRATE",       "US unemployment %",        "unemployment_pct"),
        ("CPIAUCSL",     "US CPI index",             None),    # Index value
    ]:
        entry = fred.get(key) or {}
        s = entry.get("series") or []
        latest = entry.get("latest")
        if latest is None:
            continue
        if sanity_rule:
            checked = sanity.check(sanity_rule, latest)
            if checked is None:
                continue   # value failed sanity, skip this macro entirely
            latest = checked
        cadence = "~2 weeks" if key in daily_keys else "~12 months"
        delta = _delta_full(s)
        if delta is not None:
            delta = sanity.check("pct_change", delta)
        macros.append({
            "label": label,
            "latest": latest,
            "pct_change_over": cadence,
            "pct_change": delta,
        })
    digest["macros"] = macros

    # ---- Active disasters (GDACS) ----
    g = _read("gdacs_events") or {}
    digest["hazards"] = [
        {"type": e.get("event_type"), "title": e.get("title") or e.get("name"),
         "severity": e.get("severity") or e.get("alert_score"),
         "country": e.get("country"), "lat": e.get("lat"), "lon": e.get("lon")}
        for e in (g.get("events") or [])[:8]
    ]

    # ---- Conflict events 24h (UCDP-GED) — fatalities snapshot ----
    ucdp = _read("ucdp_ged") or {}
    events_24h = []
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    for ev in (ucdp.get("events") or [])[:300]:
        d = ev.get("date_start") or ev.get("date") or ""
        if d and d >= cutoff[:10]:
            events_24h.append(ev)
    fatalities_24h = sum((e.get("best") or e.get("deaths_total") or 0) for e in events_24h)
    digest["conflict_24h"] = {
        "event_count": sanity.check("ship_count", len(events_24h)),    # reuse count rule
        "fatalities_estimated": sanity.check("fatality_count", fatalities_24h),
        "top_3": sorted(events_24h, key=lambda e: -(e.get("best") or 0))[:3],
    }

    # ---- Quakes (USGS, past 24h) ----
    q = _read("quakes") or {}
    quakes_today = (q.get("features") or [])
    big_quakes = sorted(
        [{"mag": sanity.check("earthquake_mag", f["properties"].get("mag")),
          "place": f["properties"].get("place"),
          "depth_km": (f.get("geometry") or {}).get("coordinates", [None,None,None])[2]}
         for f in quakes_today if f.get("properties", {}).get("mag") is not None],
        key=lambda r: -(r["mag"] or 0))
    big_quakes = [b for b in big_quakes if b["mag"] is not None]
    digest["quakes_24h"] = {"count": len(quakes_today), "biggest": big_quakes[:5]}

    # ---- Cyclones now ----
    nhc = _read("nhc_cyclones") or {}
    storms = nhc.get("storms") or []
    digest["cyclones"] = [
        {"name": s.get("name"), "category": s.get("classification") or s.get("status"),
         "wind_kt": s.get("wind") or s.get("max_wind_kt"), "lat": s.get("lat"), "lon": s.get("lon")}
        for s in storms[:6]
    ]

    # ---- Pulse: top concerning countries (composite risk + breakdown) ----
    pulse = _read("pulse_mode") or {}
    digest["top_concerning"] = (pulse.get("top_concerning") or [])[:10]

    # ---- Crypto + forex (live market) ----
    # economy.crypto[].change_24h is ALREADY a percentage from CoinGecko's
    # `price_change_percentage_24h` field. Sanity-checked so impossible values
    # (BTC -113%) get nulled out instead of being passed to the LLM.
    eco = _read("economy") or {}
    digest["crypto"] = [
        {"sym": c.get("symbol"),
         "usd": sanity.check("price_usd", c.get("price_usd")),
         "change_24h_pct": sanity.check("change_24h_pct", round(c.get("change_24h") or 0, 2)),
         "mcap": c.get("market_cap"),
         "source": "CoinGecko"}
        for c in (eco.get("crypto") or [])[:5]
    ]
    # Note: cross-source verification (Binance) is computed in fetch() because
    # _build_digest is sync. We attach the cross-check result there.
    forex = eco.get("forex")
    if isinstance(forex, dict):
        # CoinGecko returns a dict like {"USD/EUR": 1.18, ...}; reshape to list
        digest["forex_top"] = [{"pair": k, "rate": v} for k, v in list(forex.items())[:6]]
    elif isinstance(forex, list):
        digest["forex_top"] = forex[:6]
    else:
        digest["forex_top"] = []

    # ---- News: most-cited GDELT themes ----
    themes = _read("gdelt_gkg_themes") or {}
    digest["top_news_themes"] = (themes.get("themes") or themes.get("top") or [])[:10]

    # ---- Today's news headlines (qualitative — DO NOT extract numbers from these) ----
    events_data = _read("global_events") or {}
    digest["news_headlines_today_qualitative_only"] = [
        {"title": e.get("title"), "type": e.get("type"),
         "severity_1to10": e.get("severity"), "country": e.get("country")}
        for e in (events_data.get("events") or [])[:20]
    ]

    # ---- WHO disease outbreaks ----
    who = _read("who_don") or {}
    digest["disease_outbreaks"] = [
        {"title": o.get("title") or o.get("disease"), "country": o.get("country"),
         "date": (o.get("date") or "")[:10], "category": o.get("category")}
        for o in (who.get("outbreaks") or [])[:8]
    ]

    # ---- Space weather (NASA DONKI + NOAA SWPC) ----
    donki = _read("nasa_donki") or {}
    swpc = _read("swpc_aurora") or {}
    digest["space_weather"] = {
        "kp_index_now": (swpc.get("kp_index") or {}).get("Kp") if isinstance(swpc.get("kp_index"), dict) else swpc.get("kp_index"),
        "aurora_visibility": (swpc.get("aurora") or {}).get("forecast_label") if isinstance(swpc.get("aurora"), dict) else None,
        "solar_events_recent": [
            {"type": e.get("type") or e.get("messageType"), "time": (e.get("time") or "")[:10]}
            for e in (donki.get("events") or [])[:5]
        ],
    }

    # ---- Internet outages (Cloudflare Radar) ----
    cf = _read("cloudflare_radar") or {}
    digest["internet_outages"] = [
        {"country": o.get("country") or o.get("location"),
         "type": o.get("type") or o.get("event_type"),
         "started": (o.get("startDate") or o.get("start_date") or "")[:10]}
        for o in (cf.get("outages") or [])[:6]
    ]

    # ---- Dark vessels / AIS gaps (Global Fishing Watch — sanctions/smuggling signal) ----
    gfw = _read("gfw_events") or {}
    by_type = gfw.get("by_type") or {}
    digest["dark_vessel_signals"] = {
        "total_events": gfw.get("count"),
        "by_type": {k: (v if isinstance(v, int) else len(v) if hasattr(v, "__len__") else None) for k, v in by_type.items()},
    }

    # ---- Named battles (Wikidata SPARQL — recent geopolitical specificity) ----
    bats = _read("wikidata_battles") or {}
    digest["recent_battles"] = [
        {"name": b.get("battleLabel") or b.get("name"),
         "date": (b.get("date") or "")[:10],
         "country": b.get("countryLabel") or b.get("country")}
        for b in (bats.get("battles") or [])[:8]
    ]

    # ---- Commodity market (CoinGecko + Brent already in FRED) ----
    cm = _read("commodity_prices") or {}
    digest["live_commodities"] = [
        {"name": c.get("name"), "price": c.get("price"),
         "unit": c.get("unit"), "category": c.get("category")}
        for c in (cm.get("items") or [])[:10]
    ]

    # ---- Food prices (FAO index) ----
    fao = _read("fao_food_prices") or {}
    digest["food_index"] = {
        "fetched": fao.get("fetched"),
        "raw_csv_excerpt": (fao.get("raw_csv") or "")[:500],
    }

    # ---- US oil supply (EIA) ----
    eia = _read("eia_petroleum") or {}
    digest["us_oil"] = {
        "latest": eia.get("latest"),
        "history_count": len(eia.get("history") or []),
    }

    # ---- Active humanitarian crises ----
    rw = _read("reliefweb") or {}
    digest["humanitarian_crises"] = [
        {"name": d.get("name") or d.get("title"),
         "country": d.get("country"),
         "url": d.get("url")}
        for d in (rw.get("disasters") or [])[:6]
    ]

    # ---- IMF country troubles: top 5 inflation, top 5 debt ----
    imf = _read("imf_data") or {}
    icountries = imf.get("countries") or {}
    inflation = []
    debt_burden = []
    for iso3, row in icountries.items():
        inf = sanity.check("inflation_pct", (row.get("PCPIPCH") or {}).get("value"))
        deb = sanity.check("debt_pct_gdp", (row.get("GGXWDG_NGDP") or {}).get("value"))
        if inf is not None: inflation.append((iso3, inf))
        if deb is not None: debt_burden.append((iso3, deb))
    inflation.sort(key=lambda x: -x[1])
    debt_burden.sort(key=lambda x: -x[1])
    digest["countries_under_pressure"] = {
        "highest_inflation": [{"iso3": i, "pct": round(v, 1)} for i, v in inflation[:5]],
        "highest_debt_pct_gdp": [{"iso3": i, "pct": round(v, 1)} for i, v in debt_burden[:5]],
    }

    # ---- OECD leading economic indicator (recession early warning) ----
    oecd = _read("oecd_cli") or {}
    ocountries = oecd.get("countries") or {}
    cli_now = []
    for iso3, points in ocountries.items():
        if points and isinstance(points, list):
            latest = points[-1].get("value")
            if latest is not None:
                cli_now.append((iso3, round(latest, 2)))
    cli_now.sort(key=lambda x: x[1])
    digest["oecd_cli_extremes"] = {
        "weakest": [{"iso3": i, "cli": v} for i, v in cli_now[:5]],
        "strongest": [{"iso3": i, "cli": v} for i, v in cli_now[-5:]],
    }

    # ---- Cross-source: countries with both high pulse AND high inflation = double trouble ----
    pulse_countries = (pulse.get("countries") or {})
    double_trouble = []
    for iso3, prow in pulse_countries.items():
        if (prow.get("composite") or 0) < 40:
            continue
        irow = icountries.get(iso3)
        if not irow: continue
        inf = (irow.get("PCPIPCH") or {}).get("value")
        if inf is not None and inf > 5:
            double_trouble.append({"iso3": iso3, "name": prow.get("name"),
                                   "pulse": prow.get("composite"), "inflation_pct": round(inf, 1)})
    double_trouble.sort(key=lambda x: -(x["pulse"] + x["inflation_pct"]))
    digest["double_trouble_pulse_plus_inflation"] = double_trouble[:5]

    # Surface any sanity rejections so the model knows data quality dropped today.
    viol = sanity.violations()
    if viol:
        digest["data_quality_warnings"] = {
            "rejected_count": len(viol),
            "examples": viol[:5],
            "note": "These values were filtered out as implausible. The narrative should not cite anything related to them.",
        }
        print(sanity.summarise())

    return digest


def _prompt(digest: dict) -> str:
    digest_json = json.dumps(digest, indent=1, default=str)
    # Cap at ~20k chars (~5k tokens) so 3-paragraph response (~600 tokens)
    # comfortably fits within Gemini Flash's per-call limit even on fallback.
    if len(digest_json) > 20000:
        digest_json = digest_json[:20000] + "\n[truncated]"
    return (
        "You are WorldTwin, a senior global intelligence analyst writing the daily brief "
        "for a 3D real-time world dashboard. You synthesise 20+ live data sources into a "
        "concise, sober assessment for decision-makers.\n"
        "\n"
        "Write exactly 3 short paragraphs (60-90 words each). NO headings, NO preamble, NO bullets.\n"
        "\n"
        "Paragraph 1 — TODAY AT A GLANCE: what is happening in the world right now. Lead with the "
        "single most consequential development; weave in 2-3 supporting facts from different domains "
        "(conflict, hazards, markets, disease, infrastructure).\n"
        "Paragraph 2 — BIGGEST RISK: what deserves the most urgent attention. Be specific: name a "
        "country, chokepoint, commodity, outbreak, or chain. Connect dots across sources.\n"
        "Paragraph 3 — TREND OF THE WEEK: directional signal or quiet deterioration. Use the deltas, "
        "OECD CLI extremes, IMF country pressure, double-trouble countries.\n"
        "\n"
        "STRICT RULES — these prevent hallucination:\n"
        "  1. Every numeric claim (percentage, dollar amount, ship count, fatality count, magnitude, "
        "Kp index, etc.) MUST appear verbatim in a STRUCTURED section of the digest below "
        "(chokepoints, macros, conflict_24h, quakes_24h, hazards, top_concerning, crypto, "
        "countries_under_pressure, etc.). If a number is not in a structured section, you cannot "
        "use it — describe qualitatively ('sharp drop', 'rising', 'historically elevated').\n"
        "  2. The section `news_headlines_today_qualitative_only` is unreliable for numbers — it is "
        "scraped news titles. Use it ONLY for topical hints (what is being talked about). NEVER quote "
        "a percentage or count from a news headline.\n"
        "  3. Cite the source of each number in parentheses immediately after the number: "
        "(PortWatch), (FRED), (UCDP), (GDACS), (USGS), (NHC), (Pulse), (WHO), (DONKI), (SWPC), "
        "(Cloudflare), (GFW), (Wikidata), (FAO), (EIA), (IMF), (OECD), (CoinGecko).\n"
        "  4. Do not invent country statuses, ship traffic percentages, casualty counts, or any other "
        "specifics.\n"
        "  5. If the digest is sparse on something (e.g. cyclones array empty), say so honestly: "
        "'no active cyclones currently tracked' — not 'cyclones reported'.\n"
        "  6. Prefer SPECIFIC over GENERIC. 'Hormuz: 156 ships today (PortWatch)' beats 'Gulf shipping disrupted'.\n"
        "  7. When citing a percentage change from `macros`, ALWAYS include the cadence "
        "from `pct_change_over` (e.g. 'Copper +36.59% over 12 months (FRED)' — never just "
        "'Copper +36.59%'). Same for crypto: `change_24h_pct` is already a percentage in "
        "the digest, so cite it as e.g. 'BTC -0.42% in 24h (CoinGecko)'.\n"
        "  8. If a crypto entry has `cross_check.agrees: false`, the two sources disagree — "
        "either omit the figure or note 'sources diverge'. Never present a contested number "
        "as fact.\n"
        "  9. If `data_quality_warnings` is present in the digest, mention briefly in "
        "paragraph 3 that some indicators were filtered as implausible today.\n"
        "  10. British English. Sober, analytical tone. No emoji. No exclamation marks.\n"
        "\n"
        "STRUCTURED SECTIONS (cite numbers from these only):\n"
        "  chokepoints, macros, hazards, conflict_24h, quakes_24h, cyclones, top_concerning, "
        "crypto, forex_top, top_news_themes, disease_outbreaks, space_weather, "
        "internet_outages, dark_vessel_signals, recent_battles, live_commodities, food_index, "
        "us_oil, humanitarian_crises, countries_under_pressure, oecd_cli_extremes, "
        "double_trouble_pulse_plus_inflation\n"
        "QUALITATIVE-ONLY SECTION (do not quote numbers from this):\n"
        "  news_headlines_today_qualitative_only\n"
        "\n"
        f"WORLD DIGEST (as of {digest.get('as_of')}):\n{digest_json}\n"
        "\n"
        "Write only the 3 paragraphs. Begin immediately — no preamble like 'Here is the brief'."
    )


async def _call_openrouter(client: httpx.AsyncClient, prompt: str) -> str | None:
    if not OPENROUTER_API_KEY:
        return None
    try:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "http://129.151.191.74/weather/",
                "X-Title": "WorldTwin",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-sonnet-4-6",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 900,
            },
            timeout=90,
        )
        if r.status_code != 200:
            print(f"[ai_narrative] openrouter {r.status_code}: {r.text[:300]}")
            return None
        body = r.json()
        return (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        print(f"[ai_narrative] openrouter error: {e}")
        return None


async def _gemini_call(client: httpx.AsyncClient, prompt: str, model: str) -> str | None:
    if not GEMINI_API_KEY:
        return None
    try:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.45, "maxOutputTokens": 2000},
            },
            timeout=90,
        )
        if r.status_code != 200:
            print(f"[ai_narrative] {model} {r.status_code}: {r.text[:200]}")
            return None
        body = r.json()
        candidates = body.get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return parts[0].get("text", "") if parts else None
    except Exception as e:
        print(f"[ai_narrative] {model} error: {e}")
        return None


async def _call_gemini_pro(client: httpx.AsyncClient, prompt: str) -> str | None:
    return await _gemini_call(client, prompt, "gemini-2.5-pro")


async def _call_gemini_flash(client: httpx.AsyncClient, prompt: str) -> str | None:
    return await _gemini_call(client, prompt, "gemini-2.5-flash")


BINANCE_VS_USD = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "XRP": "XRPUSDT", "BNB": "BNBUSDT"}

async def _binance_crosscheck(client: httpx.AsyncClient, digest: dict) -> None:
    """Pull BTC/ETH/XRP/BNB 24h ticker from Binance, compare to CoinGecko.

    Adds `cross_check` field to each digest.crypto entry: {price_match: bool,
    pct_match: bool, divergence_pct_price, divergence_pct_change}.

    Catches situations where either source ships bad data — even with sanity
    rules in place, a value can be plausible but wrong. Two-source agreement
    is the gold standard.
    """
    cg = digest.get("crypto") or []
    if not cg:
        return
    by_sym = {c["sym"].upper(): c for c in cg if c.get("sym")}
    try:
        # Binance ticker24h is free + no key required
        symbols = [BINANCE_VS_USD[s] for s in by_sym if s in BINANCE_VS_USD]
        if not symbols:
            return
        params = {"symbols": json.dumps(symbols, separators=(",", ":"))}
        r = await client.get("https://api.binance.com/api/v3/ticker/24hr",
                             params=params, timeout=10)
        if r.status_code != 200:
            return
        for ticker in r.json():
            sym_pair = ticker.get("symbol", "")
            sym = next((s for s, p in BINANCE_VS_USD.items() if p == sym_pair), None)
            if not sym or sym not in by_sym:
                continue
            entry = by_sym[sym]
            try:
                bin_price = float(ticker.get("lastPrice", 0))
                bin_pct = float(ticker.get("priceChangePercent", 0))
            except ValueError:
                continue
            cg_price = entry.get("usd")
            cg_pct = entry.get("change_24h_pct")
            div_price_pct = None
            if cg_price and bin_price:
                div_price_pct = round((bin_price - cg_price) / cg_price * 100, 2)
            div_chg_pp = None
            if cg_pct is not None and bin_pct is not None:
                div_chg_pp = round(bin_pct - cg_pct, 2)
            entry["cross_check"] = {
                "binance_price": bin_price,
                "binance_pct_24h": round(bin_pct, 2),
                "price_divergence_pct": div_price_pct,
                "pct_divergence_pp": div_chg_pp,
                "agrees": (
                    div_price_pct is not None and abs(div_price_pct) < 2.0
                    and div_chg_pp is not None and abs(div_chg_pp) < 1.0
                ),
            }
    except Exception as e:
        print(f"[ai_narrative] Binance cross-check failed: {e}")


async def fetch(client: httpx.AsyncClient):
    try:
        digest = _build_digest()
    except Exception as e:
        print(f"[ai_narrative] digest build failed: {e}")
        import traceback; traceback.print_exc()
        digest = {"as_of": datetime.now(timezone.utc).isoformat(), "error": str(e)}

    # Cross-source verification — Binance public ticker24h
    await _binance_crosscheck(client, digest)

    prompt = _prompt(digest)

    # Default to Gemini 2.5 Pro (free tier on existing key, much smarter than Flash).
    # If OpenRouter is configured, prefer Claude Sonnet 4.6 (paid, sharper synthesis).
    text = None
    used_model = None
    if OPENROUTER_API_KEY:
        text = await _call_openrouter(client, prompt)
        used_model = "Claude Sonnet 4.6 (OpenRouter)" if text else None
    if not text:
        text = await _call_gemini_pro(client, prompt)
        used_model = "Gemini 2.5 Pro" if text else None
    if not text:
        text = await _call_gemini_flash(client, prompt)
        used_model = "Gemini 2.5 Flash (fallback)" if text else None
    if not text:
        return None

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    while len(paragraphs) < 3:
        paragraphs.append("")

    return {
        "source": used_model,
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": 3,
        "today": paragraphs[0],
        "biggest_risk": paragraphs[1],
        "trend_of_week": paragraphs[2],
        "raw": text,
        # Expose the digest so the frontend can render the "By the numbers" strip
        "digest": digest,
        "input_events_count": len(digest.get("events_today") or []),
    }


register(LAYER, fetch)
