# WorldTwin Intelligence Layer — Technical Plan

**The problem**: 75 data sources shown as dots on a globe. Breadth without depth.
**The solution**: A cross-source analysis engine that turns raw data into actionable insights.

---

## Architecture: Three new components

### 1. Country Intelligence Profile (backend: `country_intel.py`)

A new aggregator plugin that, for every country, computes a structured intelligence profile by reading ALL other cached layers. Runs every 30 minutes.

**Output per country** (keyed by ISO3):
```json
{
  "iso3": "NLD",
  "name": "Netherlands",
  
  "snapshot": {
    "gdp_usd": 1.09e12,
    "gdp_growth_pct": 0.8,
    "population": 17.5e6,
    "inflation_pct": 2.4,
    "unemployment_pct": 3.6,
    "debt_pct_gdp": 48.5,
    "military_spend_pct": 1.8,
    "life_expectancy": 82.3,
    "internet_pct": 95.2,
    "co2_per_capita": 8.1
  },
  
  "trends": {
    "gdp_direction": "stable",        // computed from WB time series
    "conflict_trend": "declining",     // UCDP last 3 years
    "displacement_trend": "stable",    // IDMC year-over-year
    "renewable_trend": "rising",       // OWID 10-year history
    "temperature_anomaly_trend": "rising"  // Berkeley Earth
  },
  
  "risks": {
    "conflict_proximity": 0.1,         // 0-1, based on UCDP events within 1000km
    "natural_hazard_exposure": 0.3,    // based on GDACS alerts, quakes, floods nearby
    "supply_chain_disruption": 0.4,    // based on PortWatch chokepoint dependency
    "energy_vulnerability": 0.7,       // gas dependency + price level from ENTSO-E
    "food_insecurity": 0.1,            // FAO + FEWS NET
    "pandemic_risk": 0.2,              // WHO DON outbreaks nearby
    "air_quality_concern": 0.3,        // OpenAQ measurements
    "climate_risk": 0.4,               // temp anomaly + CO2 + flood exposure
    "economic_downturn": 0.2,          // OECD CLI + IMF forecast
    "cyber_vulnerability": 0.15        // Cloudflare Radar outages
  },
  
  "peers": ["BEL", "DNK", "DEU", "GBR", "FRA"],  // similar GDP/region
  "peer_rank": {
    "gdp_per_capita": 3,    // rank among 5 peers
    "renewable_pct": 5,     // worst among peers!
    "life_expectancy": 2,
    "conflict_risk": 1      // safest
  },
  
  "dependencies": {
    "top_trade_partners": ["DEU", "BEL", "GBR", "FRA", "CHN"],
    "energy_imports_from": ["NOR", "GBR", "DEU"],  // ENTSO-E flows
    "chokepoint_exposure": ["Suez", "Gibraltar", "English Channel"],
    "critical_commodities": ["natural_gas", "crude_oil", "machinery"]
  },
  
  "alerts": [
    {"severity": "medium", "type": "energy", "text": "NL renewable % (1.6%) is lowest among EU peers. Electricity price 123 EUR/MWh — 3x above Spain."},
    {"severity": "low", "type": "economic", "text": "OECD CLI at 100.2 — stable, no recession signal."},
    {"severity": "info", "type": "climate", "text": "Global temp anomaly +1.4°C vs baseline. NL flood risk elevated due to sea level."}
  ]
}
```

**Data sources used per profile**:
- World Bank (30 indicators) → snapshot + trends
- IMF (6 indicators) → forecasts
- OWID Energy → renewable trend
- ENTSO-E → energy price, mix, imports
- EIA International → oil/gas/coal/elec
- UCDP + GDELT → conflict proximity
- IDMC → displacement
- GDACS + USGS + EONET → natural hazard exposure
- FAO + FEWS NET → food security
- WHO DON → pandemic risk
- OpenAQ → air quality
- Berkeley Earth → climate trend
- Comtrade → trade dependencies
- PortWatch → chokepoint exposure
- Cloudflare Radar → cyber vulnerability
- OECD CLI → recession signal

### 2. Anomaly Detection Engine (backend: `anomalies.py`)

Watches ALL layers for sudden changes. Fires when a metric deviates significantly from its baseline.

**What it detects**:
- Trade flow collapse (Comtrade monthly drops >30% vs 12-month average)
- Conflict spike (UCDP events in a country >2x baseline)
- Price shock (ENTSO-E electricity or commodity prices >2σ above 30-day mean)
- Displacement surge (IDMC new displacement >2x previous year)
- Natural disaster cluster (GDACS alerts within 500km of each other within 48h)
- AIS anomaly (PortWatch chokepoint traffic drops >20%)
- Grid stress (ENTSO-E load > generation = importing, price spike)

**Output**: array of anomaly events with severity, affected countries, data sources that detected it, and a human-readable explanation.

### 3. Frontend: Country Deep Card (replaces current country click)

When user clicks any country, instead of the current basic card, show:

```
┌─────────────────────────────────────────┐
│ 🇳🇱 NETHERLANDS                     [×] │
├─────────────────────────────────────────┤
│ RISK RADAR           [low|med|high]     │
│ ■■□□□ Conflict      ■■■■□ Energy       │
│ ■□□□□ Food          ■■■□□ Climate      │
│ ■■□□□ Economic      ■□□□□ Cyber        │
├─────────────────────────────────────────┤
│ TRENDS (5 year)                         │
│ GDP ↗ +0.8%  Renewable ↗ +12%          │
│ CO2 ↘ -3%    Conflict ↘ declining      │
├─────────────────────────────────────────┤
│ PEER COMPARISON (vs BEL DNK DEU GBR)   │
│ GDP/cap: #3  Renewable: #5 (worst!)    │
│ Life exp: #2  Safety: #1 (best)        │
├─────────────────────────────────────────┤
│ DEPENDENCIES                            │
│ Energy: imports from NOR (3.2GW),       │
│         GBR (1.1GW), DEU (263MW)       │
│ Trade: DEU 22%, BEL 13%, GBR 9%       │
│ Chokepoints: Suez, Gibraltar, Channel   │
├─────────────────────────────────────────┤
│ ⚠ ALERTS                               │
│ • Energy: NL renewable 1.6% — lowest   │
│   in EU. Price 123 EUR/MWh (3x Spain)  │
│ • Economic: OECD CLI stable at 100.2   │
├─────────────────────────────────────────┤
│ 📊 FULL DATA  │  📈 TRENDS  │  🔗 DEPS │
└─────────────────────────────────────────┘
```

### 4. Global Anomaly Ticker (replaces current events ticker)

Instead of just "Tropical Cyclone SINLAKU-26 4d ago" repeated, show cross-source intelligence:

```
⚡ EU grid stress: DE importing 15.7GW (load > generation). Price spike across 8 markets.
🚢 Suez traffic -12% vs 30-day avg. 3 oil tankers diverted Cape route. Brent +$2.
⚔️ Sudan: UCDP events 3x baseline this month. IDMC reports 3.8M new displaced.
🌡️ Global temp anomaly +1.43°C — highest April on Berkeley Earth record.
```

Each of these is generated by the anomaly engine, not hardcoded.

---

## Implementation Priority

| Phase | What | Effort | Impact |
|---|---|---|---|
| **1** | `country_intel.py` — compute profiles for all countries | 1 session | Enables everything else |
| **2** | Frontend: Country Intelligence Card | 1 session | Transforms the click experience |
| **3** | `anomalies.py` — cross-source anomaly detection | 1 session | Powers the smart ticker |
| **4** | Frontend: Intelligence Ticker | 0.5 session | Replaces dumb headline ticker |
| **5** | User context layer (input location/industry → personalized view) | 1 session | The business product |

## What makes this different from "just showing data"

1. **CROSS-REFERENCING**: No other free tool combines UCDP conflict + IDMC displacement + FAO food prices + ENTSO-E energy prices + PortWatch shipping in one view per country. Each source alone is available elsewhere. The combination is the moat.

2. **TREND DETECTION**: We have World Bank time series (5+ years), OWID energy (10 years), Berkeley Earth (75 years), UCDP (3 years). We can compute whether things are getting better or worse — most dashboards show only current state.

3. **DEPENDENCY MAPPING**: Comtrade shows WHO trades with WHO. ENTSO-E shows WHO imports electricity from WHO. PortWatch shows WHICH chokepoints matter. Combined: "Your supply chain depends on 3 countries and 2 chokepoints."

4. **RISK SCORING**: Not a single number — a multi-dimensional radar chart where each axis is backed by a GOLD/SILVER tier source with documented methodology. "Your energy risk is HIGH because: ENTSO-E shows 1.6% renewable (data: real-time, trust: GOLD), electricity price 123 EUR/MWh (data: real-time, trust: GOLD), gas dependency from OWID at 62% (data: annual, trust: SILVER)."

5. **PROVENANCE**: Every number in the intelligence card links back to its source, shows its trust tier, and explains the methodology. This is what makes it trustworthy — not hiding where the numbers come from, but showing it proudly.

---

## The business model this enables

- **Free tier**: Globe + all layers + basic country click = what we have now
- **Pro tier**: Intelligence cards + anomaly alerts + peer comparison + trend analysis = the intelligence layer
- **Enterprise tier**: Personalized view (your location, your industry, your supply chain) + API access + custom alerts

The data is free. The intelligence is the product.
