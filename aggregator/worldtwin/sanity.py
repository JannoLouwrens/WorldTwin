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
