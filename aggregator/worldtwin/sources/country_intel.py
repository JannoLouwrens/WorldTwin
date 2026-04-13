"""Country Intelligence Profiles — cross-source analysis engine.

Reads every other cached layer and computes a structured intelligence profile
per country: snapshot, trends, risk scores, peer comparison, dependencies, alerts.

This is the analytical backbone of WorldTwin. Raw data → actionable intelligence.
"""
import json
import math
import os
from datetime import datetime, timezone
from typing import Any

from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="country_intel",
    name="Country Intelligence Profiles",
    category="meta",
    kind="raw",
    source="WorldTwin cross-source analysis",
    source_url="internal",
    license="Derived from open data sources",
    refresh_s=1800,
    initial_delay_s=180,  # wait for other plugins to populate first
    description="Per-country intelligence: snapshot, trends, risks, peers, dependencies, alerts.",
    requires_key=False,
)

CACHE_DIR = os.environ.get("CACHE_DIR", "/cache")


def _load(layer_id: str):
    """Load a cached layer file."""
    try:
        return json.load(open(os.path.join(CACHE_DIR, f"{layer_id}.json")))
    except Exception:
        return None


def _wb_val(wb_countries: dict, iso3: str, indicator: str):
    """Get latest World Bank indicator value for a country."""
    c = wb_countries.get(iso3, {})
    ind = c.get(indicator, {})
    if isinstance(ind, dict):
        return ind.get("value")
    return None


def _safe_float(v, default=0):
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


# Peer groups by region + income level
PEER_GROUPS = {
    "NORDICS": ["NOR", "SWE", "DNK", "FIN", "ISL"],
    "WESTERN_EU": ["DEU", "FRA", "GBR", "NLD", "BEL", "AUT", "CHE", "IRL"],
    "SOUTHERN_EU": ["ESP", "ITA", "PRT", "GRC"],
    "EASTERN_EU": ["POL", "CZE", "HUN", "ROU", "BGR"],
    "NORTH_AMERICA": ["USA", "CAN"],
    "LATIN_AMERICA": ["BRA", "MEX", "ARG", "COL", "CHL", "PER"],
    "EAST_ASIA": ["CHN", "JPN", "KOR", "TWN"],
    "SOUTHEAST_ASIA": ["IDN", "THA", "VNM", "PHL", "MYS", "SGP"],
    "SOUTH_ASIA": ["IND", "BGD", "PAK", "LKA"],
    "MIDDLE_EAST": ["SAU", "ARE", "ISR", "TUR", "IRQ", "IRN"],
    "NORTH_AFRICA": ["EGY", "MAR", "DZA", "TUN", "LBY"],
    "WEST_AFRICA": ["NGA", "GHA", "SEN", "CIV"],
    "EAST_AFRICA": ["KEN", "ETH", "TZA", "UGA", "RWA"],
    "SOUTHERN_AFRICA": ["ZAF", "BWA", "NAM", "MOZ"],
    "OCEANIA": ["AUS", "NZL"],
}

# Reverse lookup: iso3 → peer group
_PEER_MAP = {}
for group, members in PEER_GROUPS.items():
    for m in members:
        _PEER_MAP[m] = members


async def fetch(client):
    """Cross-reference all cached layers into per-country intelligence profiles."""

    # Load all source caches
    wb = _load("world_bank") or {}
    wb_c = wb.get("countries", {})
    imf = _load("imf_data") or {}
    imf_c = imf.get("countries", {})
    owid = _load("owid_energy") or {}
    owid_c = owid.get("countries", {})
    entsoe = _load("entsoe_grid") or {}
    entsoe_c = entsoe.get("countries", {})
    entsoe_flows = entsoe.get("flows", [])
    ucdp = _load("ucdp_ged") or {}
    ucdp_events = ucdp.get("events", ucdp.get("items", []))
    if isinstance(ucdp_events, list) is False:
        ucdp_events = []
    idmc = _load("idmc_displacement") or {}
    idmc_c = idmc.get("countries", {})
    gdacs = _load("gdacs_events") or {}
    gdacs_events = gdacs.get("events", gdacs.get("features", []))
    if not isinstance(gdacs_events, list):
        gdacs_events = []
    fao = _load("fao_food_prices") or {}
    who = _load("who_don") or {}
    who_events = who.get("outbreaks", who.get("items", []))
    if not isinstance(who_events, list):
        who_events = []
    openaq = _load("openaq_stations") or {}
    berkeley = _load("berkeley_earth") or {}
    oecd = _load("oecd_cli") or {}
    oecd_c = oecd.get("countries", {})
    comtrade = _load("country_resources") or {}
    comtrade_c = comtrade.get("countries", {})
    portwatch = _load("portwatch_chokepoints") or {}
    pw_items = portwatch.get("chokepoints", portwatch.get("items", []))
    if not isinstance(pw_items, list):
        pw_items = []
    pulse = _load("pulse_mode") or {}
    pulse_c = pulse.get("countries", {})
    deep = _load("country_deep_dive") or {}
    deep_c = deep.get("countries", {})
    population = _load("population")
    pop_by_iso3 = {}
    if isinstance(population, list):
        for p in population:
            iso3 = p.get("cca3", "")
            if iso3:
                pop_by_iso3[iso3] = p

    # Count UCDP events per country
    ucdp_by_country = {}
    for ev in ucdp_events:
        if isinstance(ev, dict):
            c = ev.get("country", "") or ev.get("country_name", "")
            iso = ev.get("country_id", "") or ev.get("iso3", "")
            if not iso and c:
                # Try to find ISO3 from name
                for k, v in pop_by_iso3.items():
                    if v.get("name", {}).get("common", "").lower() == c.lower():
                        iso = k
                        break
            if iso:
                ucdp_by_country[iso] = ucdp_by_country.get(iso, 0) + 1

    # Count GDACS events per country (rough — GDACS has country names not ISO3)
    gdacs_by_country = {}
    for ev in gdacs_events:
        if isinstance(ev, dict):
            cname = ev.get("country", ev.get("countryname", ""))
            if cname:
                gdacs_by_country[cname] = gdacs_by_country.get(cname, 0) + 1

    # ENTSO-E flow aggregation per country
    entsoe_imports = {}
    entsoe_exports = {}
    for flow in entsoe_flows:
        f = flow.get("from", "")
        t = flow.get("to", "")
        mw = abs(flow.get("mw", 0))
        entsoe_exports.setdefault(f, []).append({"to": t, "mw": mw})
        entsoe_imports.setdefault(t, []).append({"from": f, "mw": mw})

    # Berkeley Earth latest
    be_latest = berkeley.get("latest", {})
    be_trend = berkeley.get("trend_5yr_vs_prev_5yr")

    # Build profiles
    profiles = {}
    all_iso3s = set(wb_c.keys()) | set(owid_c.keys()) | set(pop_by_iso3.keys())

    for iso3 in all_iso3s:
        if len(iso3) != 3:
            continue

        pop_entry = pop_by_iso3.get(iso3, {})
        name = pop_entry.get("name", {}).get("common", "") or iso3
        latlng = pop_entry.get("latlng", [0, 0])
        region = pop_entry.get("region", "")
        subregion = pop_entry.get("subregion", "")

        # === SNAPSHOT ===
        snapshot = {
            "gdp_usd": _wb_val(wb_c, iso3, "NY.GDP.MKTP.CD"),
            "gdp_growth_pct": _wb_val(wb_c, iso3, "NY.GDP.MKTP.KD.ZG"),
            "gdp_per_capita": _wb_val(wb_c, iso3, "NY.GDP.PCAP.CD"),
            "population": _wb_val(wb_c, iso3, "SP.POP.TOTL"),
            "inflation_pct": _wb_val(wb_c, iso3, "FP.CPI.TOTL.ZG"),
            "unemployment_pct": _wb_val(wb_c, iso3, "SL.UEM.TOTL.ZS"),
            "debt_pct_gdp": _wb_val(wb_c, iso3, "GC.DOD.TOTL.GD.ZS"),
            "military_spend_pct": _wb_val(wb_c, iso3, "MS.MIL.XPND.GD.ZS"),
            "life_expectancy": _wb_val(wb_c, iso3, "SP.DYN.LE00.IN"),
            "internet_pct": _wb_val(wb_c, iso3, "IT.NET.USER.ZS"),
            "co2_per_capita": _wb_val(wb_c, iso3, "EN.GHG.CO2.PC.CE.AR5"),
            "renewable_pct": None,
        }

        # OWID renewable
        owid_entry = owid_c.get(iso3, {})
        if isinstance(owid_entry, dict):
            latest = owid_entry.get("latest", owid_entry)
            if isinstance(latest, dict):
                snapshot["renewable_pct"] = latest.get("renewables_share_elec") or latest.get("renewables_pct")

        # ENTSO-E real-time (override for EU countries)
        iso2_candidates = [iso3[:2]]  # rough ISO3→ISO2
        for iso2, edata in entsoe_c.items():
            if isinstance(edata, dict) and edata.get("name", "").lower()[:4] == name.lower()[:4]:
                snapshot["renewable_pct"] = edata.get("renewable_pct", snapshot["renewable_pct"])
                snapshot["electricity_price_eur"] = edata.get("price_eur_mwh")
                snapshot["generation_mw"] = edata.get("total_generation_mw")
                snapshot["load_mw"] = edata.get("load_mw")
                break

        # IMF forecasts
        imf_entry = imf_c.get(iso3, {})
        if isinstance(imf_entry, dict):
            snapshot["imf_gdp_forecast"] = imf_entry.get("NGDPDPC", {}).get("value") if isinstance(imf_entry.get("NGDPDPC"), dict) else None
            snapshot["imf_inflation_forecast"] = imf_entry.get("PCPIPCH", {}).get("value") if isinstance(imf_entry.get("PCPIPCH"), dict) else None

        # === RISK SCORES (0-1) ===
        risks = {}

        # Conflict risk
        conflict_events = ucdp_by_country.get(iso3, 0)
        risks["conflict"] = min(1.0, conflict_events / 200)

        # Natural hazard
        # Count GDACS events mentioning this country name
        hazard_count = sum(v for k, v in gdacs_by_country.items() if name.lower() in k.lower())
        risks["natural_hazard"] = min(1.0, hazard_count / 10)

        # Energy vulnerability
        renew = _safe_float(snapshot.get("renewable_pct"), 50)
        price = _safe_float(snapshot.get("electricity_price_eur"), 50)
        risks["energy"] = min(1.0, max(0, (1 - renew / 100) * 0.5 + (price / 200) * 0.5))

        # Food insecurity
        deep_entry = deep_c.get(iso3, {})
        food_phase = None
        if isinstance(deep_entry, dict):
            food_data = deep_entry.get("food", {})
            if isinstance(food_data, dict):
                food_phase = food_data.get("ipc_phase")
        risks["food"] = min(1.0, _safe_float(food_phase, 0) / 5)

        # Displacement
        idmc_entry = idmc_c.get(iso3, {})
        total_disp = _safe_float(idmc_entry.get("latest_total") if isinstance(idmc_entry, dict) else 0)
        pop_total = _safe_float(snapshot.get("population"), 1e7)
        disp_ratio = total_disp / pop_total if pop_total > 0 else 0
        risks["displacement"] = min(1.0, disp_ratio * 10)

        # Economic downturn
        cli_val = None
        for oecd_key in [iso3, iso3[:2], iso3.upper()]:
            oecd_points = oecd_c.get(oecd_key, [])
            if isinstance(oecd_points, list) and oecd_points:
                cli_val = oecd_points[-1].get("value")
                break
        if cli_val and cli_val < 100:
            risks["economic_downturn"] = min(1.0, (100 - cli_val) / 5)
        else:
            gdp_g = _safe_float(snapshot.get("gdp_growth_pct"), 2)
            risks["economic_downturn"] = max(0, min(1.0, (2 - gdp_g) / 6))

        # Climate risk
        co2 = _safe_float(snapshot.get("co2_per_capita"), 4)
        risks["climate"] = min(1.0, co2 / 20)

        # Air quality
        risks["air_quality"] = 0.2  # default — upgrade with OpenAQ per-country aggregation

        # Composite risk score
        weights = {"conflict": 0.2, "natural_hazard": 0.15, "energy": 0.15,
                    "food": 0.15, "displacement": 0.1, "economic_downturn": 0.1,
                    "climate": 0.1, "air_quality": 0.05}
        composite = sum(risks.get(k, 0) * w for k, w in weights.items())
        risks["composite"] = round(composite, 3)

        # === TRENDS ===
        trends = {}
        gdp_g = _safe_float(snapshot.get("gdp_growth_pct"))
        if gdp_g > 2:
            trends["economy"] = "growing"
        elif gdp_g > 0:
            trends["economy"] = "slow_growth"
        elif gdp_g > -2:
            trends["economy"] = "stagnant"
        else:
            trends["economy"] = "contracting"

        if conflict_events > 50:
            trends["conflict"] = "high"
        elif conflict_events > 10:
            trends["conflict"] = "moderate"
        elif conflict_events > 0:
            trends["conflict"] = "low"
        else:
            trends["conflict"] = "none"

        # === PEER COMPARISON ===
        peers = _PEER_MAP.get(iso3, [])
        peer_data = {}
        if peers:
            for metric, indicator in [
                ("gdp_per_capita", "NY.GDP.PCAP.CD"),
                ("life_expectancy", "SP.DYN.LE00.IN"),
                ("co2_per_capita", "EN.GHG.CO2.PC.CE.AR5"),
            ]:
                vals = []
                for p in peers:
                    v = _wb_val(wb_c, p, indicator)
                    if v is not None:
                        vals.append((p, v))
                if vals:
                    vals.sort(key=lambda x: -x[1])
                    rank = next((i + 1 for i, (k, _) in enumerate(vals) if k == iso3), None)
                    peer_data[metric] = {"rank": rank, "of": len(vals)}

        # === DEPENDENCIES ===
        dependencies = {}
        # Trade partners
        cr = comtrade_c.get(iso3, {})
        if isinstance(cr, dict):
            partners = cr.get("top_partners", [])
            if isinstance(partners, list):
                dependencies["trade_partners"] = [p.get("iso3", "") for p in partners[:5] if isinstance(p, dict)]
            exports = cr.get("top_exports", [])
            if isinstance(exports, list):
                dependencies["top_exports"] = [e.get("name", "") for e in exports[:5] if isinstance(e, dict)]

        # Energy imports (ENTSO-E)
        for iso2, edata in entsoe_c.items():
            if isinstance(edata, dict) and edata.get("name", "").lower()[:4] == name.lower()[:4]:
                imports = entsoe_imports.get(iso2, [])
                if imports:
                    dependencies["energy_imports"] = sorted(imports, key=lambda x: -x["mw"])[:5]
                exports_list = entsoe_exports.get(iso2, [])
                if exports_list:
                    dependencies["energy_exports"] = sorted(exports_list, key=lambda x: -x["mw"])[:5]
                break

        # === ALERTS ===
        alerts = []
        if risks.get("conflict", 0) > 0.5:
            alerts.append({"severity": "high", "type": "conflict",
                           "text": f"{conflict_events} conflict events recorded (UCDP). Elevated violence."})
        if risks.get("energy", 0) > 0.6:
            alerts.append({"severity": "medium", "type": "energy",
                           "text": f"Energy vulnerability high. Renewable: {renew:.0f}%. Price: {price:.0f} EUR/MWh."})
        if risks.get("food", 0) > 0.4:
            alerts.append({"severity": "high", "type": "food",
                           "text": f"Food insecurity phase {food_phase}/5 (FEWS NET)."})
        if risks.get("displacement", 0) > 0.3:
            alerts.append({"severity": "high", "type": "displacement",
                           "text": f"{int(total_disp):,} internally displaced (IDMC). {disp_ratio*100:.1f}% of population."})
        if risks.get("economic_downturn", 0) > 0.5:
            alerts.append({"severity": "medium", "type": "economic",
                           "text": f"Economic downturn signal. GDP growth: {gdp_g:.1f}%."})

        # Only include countries with at least some data
        has_data = snapshot.get("gdp_usd") is not None or snapshot.get("population") is not None
        if not has_data:
            continue

        profiles[iso3] = {
            "iso3": iso3,
            "name": name,
            "lat": latlng[0] if len(latlng) > 1 else 0,
            "lon": latlng[1] if len(latlng) > 1 else 0,
            "region": region,
            "subregion": subregion,
            "snapshot": {k: v for k, v in snapshot.items() if v is not None},
            "risks": risks,
            "trends": trends,
            "peers": peers[:5],
            "peer_rank": peer_data,
            "dependencies": dependencies,
            "alerts": alerts,
        }

    # Global context
    global_context = {
        "temp_anomaly_c": be_latest.get("anomaly_c") if isinstance(be_latest, dict) else None,
        "temp_anomaly_year": be_latest.get("year") if isinstance(be_latest, dict) else None,
        "temp_trend_5yr": be_trend,
        "total_countries_profiled": len(profiles),
        "total_conflict_events": len(ucdp_events),
        "total_disaster_alerts": len(gdacs_events),
    }

    return {
        "source": "WorldTwin Intelligence Engine",
        "fetched": datetime.now(timezone.utc).isoformat(),
        "count": len(profiles),
        "global_context": global_context,
        "countries": profiles,
    }


register(LAYER, fetch)
