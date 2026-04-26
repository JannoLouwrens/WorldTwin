#!/usr/bin/env python3
"""WorldTwin · Source Dossier Generator

Walks every plugin in aggregator/worldtwin/sources/, extracts the LayerMeta
metadata (id, name, category, source, source_url, license, refresh_s,
description), fetches its live cache from the production server, computes
freshness + scope, and writes one markdown dossier per source to
docs/sources/<id>.md.

Then writes docs/sources/INDEX.md sorting all sources by scope and freshness
so the lab's coverage is visible at a glance.

Vision: A lab where anyone — from the king of Rome to a sceptical citizen —
can read the world from raw, dated, cross-checked sources instead of someone
else's framing, and trace every claim back to the instrument that measured it.

Run from the repo root:
    python3 scripts/generate_source_dossiers.py
"""
from __future__ import annotations
import ast
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCES_DIR = REPO_ROOT / "aggregator" / "worldtwin" / "sources"
DOCS_DIR = REPO_ROOT / "docs" / "sources"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

CACHE_BASE = "http://129.151.191.74/api/cache"


# ---- Plugin meta extraction (AST, no execution) ----

def extract_layer_meta(py_text: str) -> dict | None:
    """Pull the LayerMeta(...) constructor args from a plugin source file
    using AST parsing. Returns a dict or None if no LayerMeta found."""
    try:
        tree = ast.parse(py_text)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "LayerMeta":
            meta = {}
            for kw in node.keywords:
                meta[kw.arg] = _ast_to_value(kw.value)
            return meta
    return None


def _ast_to_value(node):
    """Resolve an AST node to its Python value when possible. Falls back
    to source text for things like f-strings or function calls."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string — flatten to a textual representation
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                parts.append("{...}")
        return "".join(parts)
    if isinstance(node, ast.Name):
        return f"<{node.id}>"
    if isinstance(node, ast.Attribute):
        return ast.unparse(node)
    if isinstance(node, ast.Call):
        return ast.unparse(node)
    if isinstance(node, ast.BinOp):
        try:
            return ast.literal_eval(node)
        except Exception:
            return ast.unparse(node)
    try:
        return ast.literal_eval(node)
    except Exception:
        return ast.unparse(node)


def extract_module_docstring(py_text: str) -> str:
    try:
        tree = ast.parse(py_text)
        return ast.get_docstring(tree) or ""
    except SyntaxError:
        return ""


# ---- Cache scope computation ----

def fetch_cache(layer_id: str) -> dict | None:
    """Fetch a layer's live cache JSON from the production server."""
    url = f"{CACHE_BASE}/{layer_id}.json"
    req = urllib.request.Request(url, headers={"User-Agent": "WorldTwin-DossierGen/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return None


def hours_since(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        ts = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def compute_scope(cache: dict | None) -> dict:
    """Walk a cache payload and report what's actually inside.

    Heuristically detects: country count, event count, points count, time
    range from any [year, value] series, top-level keys, payload size.
    """
    out = {
        "country_count": None,
        "event_count": None,
        "point_count": None,
        "feature_count": None,
        "history_year_min": None,
        "history_year_max": None,
        "top_keys": [],
        "payload_kb": None,
        "fetched": None,
        "sample_first": None,
    }
    if cache is None:
        return out
    try:
        out["payload_kb"] = round(len(json.dumps(cache, default=str)) / 1024, 1)
    except Exception:
        pass
    if not isinstance(cache, dict):
        return out

    out["fetched"] = cache.get("fetched")
    out["top_keys"] = list(cache.keys())[:25]

    # Country-style caches
    if isinstance(cache.get("countries"), dict):
        out["country_count"] = len(cache["countries"])
        for iso, val in cache["countries"].items():
            if isinstance(val, dict):
                out["sample_first"] = {iso: list(val.keys())[:8]}
                break
    # Event-style caches
    for k in ("events", "outbreaks", "battles", "disasters", "storms", "alerts",
              "asteroids", "headlines", "items", "stations", "ports", "chokepoints",
              "facilities", "plants", "samples", "cables", "themes", "concerns",
              "tracks", "stories", "videos", "tweets", "channels", "schedules",
              "matches", "outages", "trips", "ships", "flights", "satellites",
              "powerplants"):
        if isinstance(cache.get(k), list):
            out["event_count"] = max(out["event_count"] or 0, len(cache[k]))
    # GeoJSON features
    if isinstance(cache.get("features"), list):
        out["feature_count"] = len(cache["features"])
    # Points / flows arrays
    for k in ("points", "flows", "trades", "edges"):
        if isinstance(cache.get(k), list):
            out["point_count"] = max(out["point_count"] or 0, len(cache[k]))

    # History year span detection — any list of [year, value] pairs
    def _scan_for_years(node, depth=0):
        if depth > 6:
            return
        if isinstance(node, list) and len(node) >= 2:
            ys = []
            for row in node[:200]:
                if isinstance(row, (list, tuple)) and len(row) >= 2 and isinstance(row[0], (int, float)):
                    ys.append(int(row[0]))
            if len(ys) >= 5:
                lo, hi = min(ys), max(ys)
                if out["history_year_min"] is None or lo < out["history_year_min"]:
                    out["history_year_min"] = lo
                if out["history_year_max"] is None or hi > out["history_year_max"]:
                    out["history_year_max"] = hi
        if isinstance(node, dict):
            # `history` dicts keyed by year string
            if "history" in node and isinstance(node["history"], dict):
                ys = []
                for k in list(node["history"].keys())[:200]:
                    try:
                        ys.append(int(k))
                    except (ValueError, TypeError):
                        pass
                if len(ys) >= 5:
                    lo, hi = min(ys), max(ys)
                    if out["history_year_min"] is None or lo < out["history_year_min"]:
                        out["history_year_min"] = lo
                    if out["history_year_max"] is None or hi > out["history_year_max"]:
                        out["history_year_max"] = hi
            for v in list(node.values())[:50]:
                _scan_for_years(v, depth + 1)
        elif isinstance(node, list):
            for v in node[:50]:
                _scan_for_years(v, depth + 1)
    _scan_for_years(cache)

    return out


# ---- Trust tier ----

def trust_tier(hours: float | None) -> str:
    if hours is None:
        return "?"
    if hours < 6:
        return "🟢 fresh"
    if hours < 48:
        return "🟡 recent"
    return "🔴 stale"


def _refresh_s_num(meta: dict) -> float:
    """AST sometimes resolves arithmetic literals (60*5) to a string via
    unparse. Coerce safely; default 0."""
    rs = meta.get("refresh_s")
    if isinstance(rs, (int, float)):
        return float(rs)
    if isinstance(rs, str):
        try:
            return float(eval(rs, {"__builtins__": {}}, {}))
        except Exception:
            return 0.0
    return 0.0


def relevance_label(meta: dict, scope: dict, hours: float | None) -> str:
    """One-word tag for what kind of source this is — helps the index sort."""
    if meta.get("category") == "meta":
        return "meta/derived"
    if scope.get("country_count", 0) and scope["country_count"] > 100:
        return "global · per-country"
    if scope.get("history_year_min") is not None and (
        scope.get("history_year_max", 0) - scope.get("history_year_min", 0) > 100):
        return "deep-history series"
    if scope.get("event_count", 0) and scope["event_count"] > 0:
        return "live events stream"
    if _refresh_s_num(meta) and _refresh_s_num(meta) < 300:
        return "real-time feed"
    return "global · snapshot"


# ---- Dossier rendering ----

def render_dossier(layer_id: str, plugin_path: Path, meta: dict, doc: str,
                   cache: dict | None, scope: dict) -> str:
    fetched = scope.get("fetched")
    h = hours_since(fetched)
    tier = trust_tier(h)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    refresh_s = meta.get("refresh_s")
    refresh_num = _refresh_s_num(meta)
    refresh_human = "?"
    if refresh_num > 0:
        if refresh_num < 60:           refresh_human = f"{int(refresh_num)} s"
        elif refresh_num < 3600:       refresh_human = f"{round(refresh_num / 60)} min"
        elif refresh_num < 86400:      refresh_human = f"{round(refresh_num / 3600)} h"
        else:                          refresh_human = f"{round(refresh_num / 86400)} d"

    history_str = "—"
    if scope.get("history_year_min") is not None:
        history_str = f"{scope['history_year_min']} → {scope['history_year_max']}"

    scope_lines = []
    if scope.get("country_count"):
        scope_lines.append(f"- **Countries covered:** {scope['country_count']}")
    if scope.get("event_count"):
        scope_lines.append(f"- **Event/record count:** {scope['event_count']}")
    if scope.get("feature_count"):
        scope_lines.append(f"- **GeoJSON features:** {scope['feature_count']}")
    if scope.get("point_count"):
        scope_lines.append(f"- **Points / flows:** {scope['point_count']}")
    if scope.get("history_year_min") is not None:
        scope_lines.append(f"- **Time range:** {history_str}")
    if scope.get("payload_kb"):
        scope_lines.append(f"- **Cache payload size:** {scope['payload_kb']} KB")
    scope_block = "\n".join(scope_lines) or "_no data in cache_"

    top_keys = ", ".join(f"`{k}`" for k in scope.get("top_keys", [])[:15])

    lines = [
        f"# {meta.get('name') or layer_id}",
        "",
        f"`{layer_id}` · category: **{meta.get('category', '?')}** · {relevance_label(meta, scope, h)} · {tier}",
        "",
        f"_Audited {today} UTC._",
        "",
        "## Source",
        "",
        f"- **Provider:** {meta.get('source', '?')}",
        f"- **Source URL:** {meta.get('source_url', '?')}",
        f"- **License:** {meta.get('license', '?')}",
        f"- **Plugin:** [`{plugin_path.name}`]({_relpath(plugin_path)})",
        f"- **Refresh cadence:** every {refresh_human} (refresh_s = `{refresh_s}`)",
        f"- **Initial delay:** {meta.get('initial_delay_s', '?')} s",
        f"- **Requires API key:** {meta.get('requires_key', False)}{(' · ' + meta.get('key_env', '')) if meta.get('key_env') else ''}",
        f"- **Enabled:** {meta.get('enabled', True)}",
        "",
        "## Description",
        "",
        f"{meta.get('description', '_(no description)_')}",
        "",
        "## Live cache scope (now)",
        "",
        scope_block,
        "",
        f"- **Last fetched:** `{fetched or '—'}` ({f'{h:.1f}h ago' if h is not None else 'unknown'})",
        f"- **Top-level keys:** {top_keys or '_(empty)_'}",
        "",
        "## Trust tier",
        "",
        f"{tier} — based on freshness only. Cross-check requires manual triangulation",
        "via the Inspector or scripts/nightly_audit.py.",
        "",
        "## Relevance to vision",
        "",
        _relevance_note(layer_id, meta, scope),
        "",
        "---",
        "",
        "_This file is auto-generated by `scripts/generate_source_dossiers.py`._",
        "_Run that script to refresh._",
    ]
    return "\n".join(lines)


def _relpath(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _relevance_note(layer_id: str, meta: dict, scope: dict) -> str:
    """Short human-written framing of why this source matters to the lab."""
    NOTES = {
        "fred": "30+ macro time-series — the market temperature of the world economy.",
        "imf_data": "229 countries' inflation, debt, growth, unemployment. The fiscal vital signs.",
        "world_bank": "WB WDI: 261 economies × dozens of indicators × 60+ years of history. The bedrock economic dataset.",
        "vdem_democracy": "176 countries scored on electoral democracy 1789→present. The political vital signs.",
        "ucdp_ged": "Up to 5000 georeferenced conflict events. UCDP is the gold standard for academic conflict data.",
        "gdacs_events": "Active hazard alerts — drought, storm, flood. Refreshed continuously.",
        "noaa_co2": "Mauna Loa CO2 + 800k-yr EPICA paleo composite. The instrument of climate.",
        "paleo_temperature": "Marcott + PAGES2k + HadCRUT5 stitched. Global temperature anomaly across the Holocene.",
        "portwatch_chokepoints": "Live AIS-based vessel counts at 21 strategic chokepoints. Trade flow lifeblood.",
        "ai_narrative": "The Council & narrative — built on top of every other source. Vision-critical.",
        "pulse_mode": "Composite risk score per country. Surfaces 'where to worry' at a glance.",
        "country_relations": "Curated bloc memberships + GDELT-derived ally/enemy graph. Powers Causal Lines.",
        "country_resources": "Per-country trade fact sheet from UN Comtrade.",
        "trade_annual": "Bilateral commodity flows. Powers the Causal Lines export/import arcs.",
        "maddison_history": "Maddison Project: GDPpc back to 1 AD. Long-arc economic history.",
        "hyde_population": "HYDE 3.3 historical population, -10000 → 2023. Long-arc demographics.",
        "quakes": "USGS earthquakes M2.5+ past 24h. Tectonic real-time.",
        "nhc_cyclones": "Active tropical cyclones. The atmosphere's loudest signal.",
        "who_don": "WHO Disease Outbreak News. Slow-signal health surveillance.",
        "country_culture": "Curated religion + ethnicity per country.",
        "country_polygons": "Natural Earth admin-0 polygons. The map's geometry.",
        "historical_borders": "Time-aware border polygons -123000 BC → 2010 AD.",
        "historical_disasters": "Named historical disasters from antiquity to present.",
        "historical_wars": "Brecke + COW + UCDP wars stitched together — the long view of conflict.",
        "brecke_wars": "Brecke catalog — wars 1400 → present. Pre-COW historical conflict.",
        "cow_alliances": "Correlates of War alliance treaties 1815 → 2009. Historical bloc graph.",
        "clio_life_expectancy": "Clio-Infra + Riley life expectancy 1500 → 2023. Long-arc human welfare.",
    }
    return NOTES.get(layer_id, "_Vision relevance not yet annotated._")


# ---- Index page ----

def render_index(rows: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    by_tier = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r)
    counts = {k: len(v) for k, v in by_tier.items()}

    rows_sorted = sorted(rows, key=lambda r: (
        # GREEN first, then YELLOW, RED, unknown
        {"🟢 fresh": 0, "🟡 recent": 1, "🔴 stale": 2, "?": 3}.get(r["tier"], 9),
        -(r.get("scope_size", 0)),
    ))

    lines = [
        "# WorldTwin · Source Dossier Index",
        "",
        f"_{len(rows)} plugins audited · {today} UTC_",
        "",
        "**Vision:** A lab where anyone — from the king of Rome to a sceptical citizen —",
        "can read the world from raw, dated, cross-checked sources instead of someone",
        "else's framing, and trace every claim back to the instrument that measured it.",
        "",
        "## Trust tier summary",
        "",
        f"- 🟢 fresh (<6h): **{counts.get('🟢 fresh', 0)}**",
        f"- 🟡 recent (6-48h): **{counts.get('🟡 recent', 0)}**",
        f"- 🔴 stale (>48h or no timestamp): **{counts.get('🔴 stale', 0)}**",
        f"- ❓ no cache reachable: **{counts.get('?', 0)}**",
        "",
        "## All sources, ranked",
        "",
        "| Tier | Source | Category | Scope | Refresh | History | Plugin |",
        "|------|--------|----------|-------|---------|---------|--------|",
    ]
    for r in rows_sorted:
        scope_bits = []
        if r.get("country_count"):  scope_bits.append(f"{r['country_count']} countries")
        if r.get("event_count"):    scope_bits.append(f"{r['event_count']} events")
        if r.get("feature_count"):  scope_bits.append(f"{r['feature_count']} features")
        if r.get("point_count"):    scope_bits.append(f"{r['point_count']} pts")
        scope_str = " · ".join(scope_bits) or "—"

        history_str = "—"
        if r.get("history_year_min") is not None:
            history_str = f"{r['history_year_min']} → {r['history_year_max']}"

        refresh_human = "?"
        rs_raw = r.get("refresh_s")
        if isinstance(rs_raw, (int, float)):
            rs = float(rs_raw)
        elif isinstance(rs_raw, str):
            try: rs = float(eval(rs_raw, {"__builtins__": {}}, {}))
            except Exception: rs = 0.0
        else:
            rs = 0.0
        if rs > 0:
            if rs < 60:        refresh_human = f"{int(rs)}s"
            elif rs < 3600:    refresh_human = f"{round(rs/60)}m"
            elif rs < 86400:   refresh_human = f"{round(rs/3600)}h"
            else:              refresh_human = f"{round(rs/86400)}d"

        lines.append(f"| {r['tier']} | [{r['layer_id']}]({r['layer_id']}.md) | "
                     f"{r['category']} | {scope_str} | {refresh_human} | {history_str} | "
                     f"`{r['plugin']}` |")

    lines.append("")
    lines.append("_Auto-generated by `scripts/generate_source_dossiers.py`._")
    return "\n".join(lines)


# ---- Main ----

def main() -> int:
    plugins = sorted([p for p in SOURCES_DIR.glob("*.py")
                      if not p.name.startswith("_") and p.name != "__init__.py"])
    print(f"[gen] auditing {len(plugins)} plugins → {DOCS_DIR}")
    rows = []
    for p in plugins:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[gen] skip {p.name}: {e}")
            continue
        meta = extract_layer_meta(text) or {}
        if not meta.get("id"):
            # Some plugins (like ai_narrative) use computed ids; try filename
            meta["id"] = p.stem
        layer_id = meta["id"]

        cache = fetch_cache(layer_id)
        scope = compute_scope(cache)
        h = hours_since(scope.get("fetched"))
        tier = trust_tier(h)

        dossier = render_dossier(layer_id, p, meta, extract_module_docstring(text), cache, scope)
        out_path = DOCS_DIR / f"{layer_id}.md"
        out_path.write_text(dossier, encoding="utf-8")

        rows.append({
            "layer_id": layer_id,
            "plugin": p.name,
            "category": meta.get("category", "?"),
            "tier": tier,
            "refresh_s": meta.get("refresh_s"),
            **scope,
            "scope_size": (scope.get("country_count") or 0) + (scope.get("event_count") or 0)
                        + (scope.get("feature_count") or 0) + (scope.get("point_count") or 0),
        })
        cc = scope.get('country_count')
        ec = scope.get('event_count')
        h0 = scope.get('history_year_min')
        h1 = scope.get('history_year_max')
        print(f"  · {layer_id:35} {tier:12} {meta.get('category', '?'):10} "
              f"countries={cc if cc is not None else '   -'} "
              f"events={ec if ec is not None else '    -'} "
              f"history={h0}→{h1}")

    # Write index
    (DOCS_DIR / "INDEX.md").write_text(render_index(rows), encoding="utf-8")
    print(f"[gen] wrote {len(rows)} dossiers + INDEX.md → {DOCS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
