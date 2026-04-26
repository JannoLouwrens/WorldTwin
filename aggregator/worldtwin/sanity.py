"""sanity.py — single point of truth for "what is a plausible value for X".

Catches bugs like:
  - "BTC dropped 42% in 24h" (was a unit error: ratio×100 instead of percent)
  - "XRP -113% in 24h" (mathematically impossible for a price)
  - "Copper +36% today" (was a 12-month change mislabelled as recent)

Anywhere a numeric field is exposed to a consumer (the LLM, the briefing UI,
the dossier, a mapmode), pass it through `check(field, value)` first. Returns
either the value (if plausible) or `None` (if it failed sanity), and logs the
violation so we can grep for them.

Usage:
    from worldtwin.sanity import check, summarise
    safe = check("change_24h_pct", -113.0)   # → None, prints WARN
    safe = check("change_24h_pct", -0.42)    # → -0.42

Field rules are intentionally PERMISSIVE — a real anomaly (a crypto pumped
1000% in a day) should still pass. We only flag values that violate physical
or definitional limits (a percentage ≤ -100, a ship count > 50000, etc.).
"""
from __future__ import annotations
import math
from typing import Any, Callable, Iterable

# (field_name, lo, hi, unit_note) — None on either bound means unbounded.
# A value outside [lo, hi] is rejected.
RULES: dict[str, tuple[float | None, float | None, str]] = {
    # ---- Financial percentages ----
    "change_24h_pct":   (-99.0,    100000.0, "Crypto/equity 24h % change. Below -99% means price went negative (impossible)."),
    "change_7d_pct":    (-99.0,    100000.0, "7-day % change."),
    "pct_change":       (-99.0,    100000.0, "Generic % change. Should be paired with pct_change_over."),
    "inflation_pct":    (-50.0,     50000.0, "Inflation %. Hyperinflation tops out around 30000%/yr historically."),
    "debt_pct_gdp":     (0.0,         500.0, "Public debt as % of GDP. Japan ~250% is the global record."),
    "growth_pct":       (-50.0,        50.0, "Real GDP growth %/yr. Outside ±50% means data corruption."),
    "unemployment_pct": (0.0,         100.0),
    "renewable_pct":    (0.0,         100.0),
    "internet_pct":     (0.0,         100.0),
    "urban_pct":        (0.0,         100.0),
    "military_pct_gdp": (0.0,         100.0),
    "yield_pct":        (-10.0,        50.0, "Bond yield. Negative possible (Japan); >50% means hyperinflation defaults."),

    # ---- Prices ----
    "price_usd":        (0.0,    1_000_000.0, "Crypto/commodity price in USD."),
    "brent_oil_usd":    (10.0,        300.0, "Brent crude price. <$10 means data corrupt; $300 is wartime peak."),
    "wti_oil_usd":      (10.0,        300.0),
    "natgas_usd":       (0.5,         100.0, "Henry Hub $/MMBtu."),
    "copper_usd_t":     (1000.0,    25000.0, "Copper $/tonne."),
    "wheat_usd_t":      (50.0,      1000.0,  "Wheat $/tonne."),

    # ---- Volatility / yields ----
    "vix":              (5.0,         100.0, "VIX. Below 5 means data corrupt; above 100 means pandemic-grade panic."),
    "fed_funds_pct":    (-1.0,         25.0, "US Fed funds rate."),
    "kp_index":         (0.0,           9.0, "Geomagnetic Kp index. Capped at 9 by definition."),

    # ---- Counts / quantities ----
    "ship_count":       (0,        50000,  "Daily vessel count at a chokepoint. Hormuz peak is ~250."),
    "earthquake_mag":   (0.0,         10.5, "Richter scale. Above 9.5 has never been recorded."),
    "fatality_count":   (0,      10_000_000, "Single-event fatalities."),
    "event_severity":   (0,           10,   "Severity 0-10 scale."),

    # ---- Population / GDP ----
    "population":       (0,        2_000_000_000, "Country population. China ~1.4B is the cap."),
    "gdp_usd":          (0,    100_000_000_000_000, "GDP in USD. World ~$110T is the cap."),
    "gdp_per_capita":   (0,        500_000, "GDP/capita. Monaco/Liechtenstein peak ~$200k."),
    "life_expectancy":  (0,         130,   "Life expectancy years. Capped near 90 in reality."),

    # ---- Forex ----
    "fx_rate":          (0.0,      100000.0, "FX rate. Reasonable bounds."),
}


# --- Logging — accumulate violations so we can summarise per-fetch
_violations: list[dict] = []


def _record(field: str, value: Any, reason: str) -> None:
    _violations.append({"field": field, "value": value, "reason": reason})
    print(f"[sanity] REJECTED {field}={value!r}: {reason}")


def reset() -> None:
    _violations.clear()


def violations() -> list[dict]:
    return list(_violations)


def summarise() -> str:
    if not _violations:
        return "[sanity] all values plausible"
    return f"[sanity] {len(_violations)} rejections: " + ", ".join(
        f"{v['field']}={v['value']!r}" for v in _violations[:10]
    )


def check(field: str, value: Any) -> Any:
    """Return value if plausible, None otherwise.

    Unknown fields pass through unchanged (don't break callers). Known fields
    are bounded by RULES.
    """
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return value
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        _record(field, value, "non-finite")
        return None
    rule = RULES.get(field)
    if rule is None:
        return value
    lo, hi = rule[0], rule[1]
    if lo is not None and value < lo:
        _record(field, value, f"below lower bound {lo}")
        return None
    if hi is not None and value > hi:
        _record(field, value, f"above upper bound {hi}")
        return None
    return value


def check_dict(d: dict, fields: dict[str, str]) -> dict:
    """Apply check to multiple fields of a dict in one go.

    `fields` maps `dict_key → rule_field_name`. Returns a new dict with rejected
    values set to None.

        check_dict({"price": 77000, "ch": -113}, {"price": "price_usd", "ch": "change_24h_pct"})
        → {"price": 77000, "ch": None}  (ch fails rule, price passes)
    """
    out = dict(d)
    for k, rule_name in fields.items():
        out[k] = check(rule_name, out.get(k))
    return out


# ============================================================
# Auto-sweep — applied to every cache write so impossible values
# never reach the dashboard. Maps common field names to rules.
# Conservative: only fields that are unambiguous get checked
# (we don't want to silently null a legitimate field that happens
# to share a name).
# ============================================================
AUTO_SWEEP_KEYS: dict[str, str] = {
    # Crypto — economy.crypto[].* and similar
    "price_usd":              "price_usd",
    "current_price":          "price_usd",
    "change_24h":             "change_24h_pct",
    "change_24h_pct":         "change_24h_pct",
    "price_change_percentage_24h": "change_24h_pct",
    "change_7d":              "change_7d_pct",
    "change_7d_pct":          "change_7d_pct",
    # FRED-ish
    "vix":                    "vix",
    "yield_pct":              "yield_pct",
    "fed_funds_pct":          "fed_funds_pct",
    "inflation_pct":          "inflation_pct",
    "debt_pct_gdp":           "debt_pct_gdp",
    "growth_pct":             "growth_pct",
    "unemployment_pct":       "unemployment_pct",
    # Earthquakes
    "mag":                    "earthquake_mag",
    "magnitude":              "earthquake_mag",
    # Counts
    "ship_count":             "ship_count",
    "n_total":                "ship_count",
    "fatalities":             "fatality_count",
    "fatalities_estimated":   "fatality_count",
    "best":                   "fatality_count",
    "deaths_total":           "fatality_count",
    "kp":                     "kp_index",
    "Kp":                     "kp_index",
    # Pcts
    "renewable_pct":          "renewable_pct",
    "internet_pct":           "internet_pct",
    "urban_pct":              "urban_pct",
    "military_pct_gdp":       "military_pct_gdp",
    # Demographics
    "life_expectancy":        "life_expectancy",
    "life_exp":               "life_expectancy",
}


def auto_sweep(payload, depth: int = 0, max_depth: int = 8) -> tuple[object, list[dict]]:
    """Recursively walk a JSON-serialisable structure, applying auto-sweep rules.

    Returns (new_payload, list_of_warnings). Warnings record which key-path was
    rejected so the Inspector can surface them to the user.

    Doesn't mutate; returns a deep-ish copy of the modified branches.
    """
    warnings: list[dict] = []
    new_payload = _sweep_walk(payload, [], warnings, depth=depth, max_depth=max_depth)
    return new_payload, warnings


def _sweep_walk(node, path: list, warnings: list[dict], depth: int, max_depth: int):
    if depth > max_depth:
        return node
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            new_path = path + [str(k)]
            rule = AUTO_SWEEP_KEYS.get(k)
            if rule and isinstance(v, (int, float)):
                checked = check(rule, v)
                if checked is None and v is not None:
                    warnings.append({
                        "path": ".".join(new_path),
                        "key": k,
                        "rule": rule,
                        "value": v,
                    })
                out[k] = checked
            else:
                out[k] = _sweep_walk(v, new_path, warnings, depth + 1, max_depth)
        return out
    if isinstance(node, list):
        return [_sweep_walk(v, path + [str(i)], warnings, depth + 1, max_depth)
                for i, v in enumerate(node)]
    return node


def sweep_and_tag(payload):
    """Run auto_sweep on a top-level dict cache payload and ATTACH the warnings
    as a `_sanity_warnings` field so the UI/Inspector can surface them.

    If the payload isn't a dict, returns it unchanged. If there are no
    warnings, no field is added (clean caches stay clean).
    """
    if not isinstance(payload, dict):
        return payload
    swept, warnings = auto_sweep(payload)
    if warnings:
        swept["_sanity_warnings"] = {
            "count": len(warnings),
            "rejections": warnings[:20],   # cap to avoid bloating the cache
            "note": "Values listed here failed sanity bounds and were nulled. The Inspector surfaces this; the LLM is told to avoid them.",
        }
    return swept
