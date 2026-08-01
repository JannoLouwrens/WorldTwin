# WorldTwin — Data Trust & Reliability Assessment
**Compiled 2026-04-13** · Every source live-verified + academically researched.

This document answers: **"Can someone make real decisions based on WorldTwin data?"**

---

## Trust Tier System

| Tier | Meaning | Count |
|---|---|---|
| 🥇 **GOLD** | Used by governments for actual policy decisions. Peer-reviewed, institutionally backed. | 5 |
| 🥈 **SILVER** | Trusted by professionals for analysis. Published methodology. Known limitations documented. | 14 |
| 🥉 **BRONZE** | Useful context / entertainment. Verify independently before acting. | 5 |
| ⚠️ **CAUTION** | Known methodology issues. Use only as directional proxy, never as ground truth. | 1 (GDELT) |

---

## 🥇 GOLD TIER — Policy-grade data

### 1. World Bank WDI (265 countries × 30 indicators)
- **Producer**: World Bank (189 member countries)
- **Method**: Compiled from national statistical offices, UN agencies, IMF, WHO, ILO, FAO
- **Used by**: Every government, IMF Article IV consultations, World Bank lending decisions
- **Known gaps**: Sub-Saharan Africa worst statistical capacity. 21 of 34 fragile states in bottom 20%. Some African countries have no poverty survey in 10+ years. Data can be 1-3 years stale for developing nations.
- **Trust**: If WDI is missing data for a country, nobody has it.
- **Key critique**: Jerven (2013) "Poor Numbers" — seminal work on African data quality problems.

### 2. IMF DataMapper WEO (229 countries × 6 indicators)
- **Producer**: IMF (191 members)
- **Method**: Country teams + econometric models. Published April/October.
- **Used by**: Central banks, finance ministries, bond markets
- **Known gaps**: Systematic optimistic bias in 2-5 year GDP forecasts for developing countries. IMF forecasts align with lending programs (institutional incentive problem).
- **Trust**: GOLD for actuals, SILVER for forecasts. Use forecasts directionally, not as point estimates.
- **Key critique**: Blanchard & Leigh (2013) — IMF underestimated fiscal multipliers during austerity.

### 3. USGS Earthquake Hazards (65+ events/day, global)
- **Producer**: US Geological Survey (federal agency)
- **Method**: 7,100+ seismometers (ANSS) + global network partners. Automated + human review.
- **Used by**: ALL seismic hazard agencies, building codes worldwide
- **Known gaps**: Detection completeness varies: US covered to M2.0+, but Africa/Central Asia/deep ocean poorly instrumented. Position uncertainty 100m (dense networks) to 10s km (sparse).
- **Trust**: GOLD for M5.0+ globally. SILVER for M4.0-4.9 outside dense networks.

### 4. UN Comtrade (879+ bilateral flows)
- **Producer**: UN Statistics Division
- **Method**: Country self-reporting. Imports CIF, exports FOB (10-20% systematic asymmetry).
- **Used by**: WTO, UNCTAD, every trade economist
- **Known gaps**: Bilateral asymmetries are large. Informal/smuggled trade invisible. Reporting lag 1-24 months depending on country.
- **Trust**: GOLD for trends and major flows. SILVER for precise bilateral values. Always cross-check with mirror statistics.

### 5. FAO Food Price Index (monthly)
- **Producer**: UN FAO
- **Method**: Trade-weighted index of 24 commodities across cereals, dairy, meat, oils, sugar
- **Used by**: WFP, IFPRI, G20 agricultural market monitoring
- **Known gaps**: Measures INTERNATIONAL export prices only — transmission to domestic consumer prices is variable, especially in developing countries.
- **Trust**: GOLD for commodity price trends. CAUTION for inferring local food costs.

---

## 🥈 SILVER TIER — Professional analysis grade

### 6. NASA FIRMS (2,653 fire detections)
- **Method**: MODIS + VIIRS satellite thermal anomaly detection
- **Accuracy**: Only 16-26% overall detection rate. Small fires under canopy systematically missed. Low-confidence nighttime detections silently filtered.
- **Trust**: SILVER for fire PRESENCE detection. CAUTION for fire ABSENCE — lack of detection does NOT mean no fire.
- **Key paper**: Giglio et al. (2016)

### 7. UCDP Conflict Events (3,000 events)
- **Method**: Coded from news/NGO/academic sources. 25-death threshold for "armed conflict."
- **Accuracy**: Kosovo validation captured only ~33% of total fatalities. Information-dark zones (Eritrea, DPRK, Xinjiang) severely underreported.
- **Trust**: SILVER. Always treat fatality counts as LOWER BOUNDS.
- **Key paper**: Sundberg & Melander (2013)

### 8. NOAA SWPC Aurora/Space Weather (18k grid points)
- **Method**: WSA-Enlil physics model, DSCOVR/ACE L1 data, ground magnetometers
- **Accuracy**: 2025 study found forecasts "consistently outperformed by baseline models."
- **Trust**: SILVER for storm detection and alerts. BRONZE for flare prediction accuracy. Used operationally because there is no alternative.

### 9. GDACS Disaster Alerts (88 events)
- **Method**: Empirical algorithms: hazard magnitude × population exposure × coping capacity
- **Accuracy**: "Cannot always reliably predict humanitarian impact." Designed for speed, not precision.
- **Trust**: SILVER for sudden-onset disaster AWARENESS. Treat as triggers for investigation, not confirmed assessments.

### 10. Berkeley Earth Temperature (75 years)
- **Method**: 39,000 station records (largest network) + kriging interpolation
- **Trust**: SILVER (approaching GOLD). Included in IPCC AR6. Agrees with NASA GISS, NOAA, HadCRUT to within uncertainty bounds. 1,800+ citations.
- **Key paper**: Rohde et al. (2013)

### 11. OECD CLI (22 countries)
- **Method**: Country-specific component series (industrial production, stock prices, yield curves)
- **Known gaps**: G20 + Spain only. Academic studies show declining predictive power over time.
- **Trust**: SILVER for directional signals in OECD economies. CAUTION for point predictions.

### 12. IMF PortWatch (800 ports, 21 chokepoints)
- **Method**: AIS satellite tracking of ~90,000 ships + ML trade volume estimation
- **Known gaps**: AIS ≠ official trade stats. Measures vessel movement, not customs clearance.
- **Trust**: SILVER for trade DISRUPTION detection. BRONZE for trade VOLUME estimation.

### 13. IDMC Displacement (86 countries)
- **Method**: Multi-source: government data, UN agencies, NGOs, media
- **Known gaps**: Significant undercounting in inaccessible conflict zones. Afghanistan data "already outdated."
- **Trust**: SILVER. Treat as LOWER BOUNDS. Best available data on internal displacement.

### 14. Global Fishing Watch (200 events)
- **Method**: AIS vessel tracking + ML fishing behavior classification
- **Known gaps**: Covers only ~3% of world's 3.3M fishing vessels. Overestimates haul counts by up to 87% (2025 ICES study). Small-scale artisanal fisheries invisible.
- **Trust**: SILVER for large industrial vessel tracking. CAUTION for fishing effort quantification.

### 15. OpenAQ (12,000 stations, 110 countries)
- **Method**: Aggregates government reference monitors + low-cost sensors
- **Known gaps**: 36% of countries have NO air quality monitoring (~1 billion people). Mix of reference-grade and low-cost sensors not always labeled.
- **Trust**: SILVER for dense-network countries (US, EU, China). BRONZE for developing countries.

### 16. ClimateTRACE (5,000 facilities)
- **Method**: 300+ satellites, AI/ML trained on ground truth. Asset-level emissions.
- **Known gaps**: Shows oil & gas emissions 3× higher than national self-reports. Validation of full pipeline still developing.
- **Trust**: SILVER for relative comparisons. BRONZE for absolute emission quantities.

### 17. EIA International (258 countries)
- **Producer**: US Energy Information Administration
- **Trust**: SILVER. US government agency. Comprehensive energy data.

### 18. OWID Energy (220 countries)
- **Note**: Secondary aggregator (repackages BP/Energy Institute, EIA, Ember data)
- **Trust**: SILVER. Always cite the underlying provider, not OWID itself.

### 19. Open-Meteo Weather (135+ grid points)
- **Method**: Aggregates ECMWF, GFS, ICON, MeteoFrance, JMA models
- **Trust**: SILVER for current weather. BRONZE for historical analysis. Not a primary research source.

---

## ⚠️ CAUTION TIER

### 20. GDELT Project (1,321 events, 150 articles, 426 theme pulses)
- **Producer**: Individual researcher (Kalev Leetaru), not institutional
- **Method**: Automated NLP coding of news articles. Updates every 15 minutes.
- **CRITICAL PROBLEMS**:
  - **55% field accuracy** (45% of coded fields are WRONG)
  - **20% data redundancy** (same event counted from multiple articles)
  - **Massive Western/English-language bias**
  - UK Office for National Statistics published a formal data quality WARNING
  - Academic adoption is low; studies using it often rated "low quality"
- **What it actually measures**: MEDIA COVERAGE of events, NOT events themselves
- **Trust**: BRONZE for trend direction / media attention proxy. **NEVER use raw GDELT counts as ground truth for anything.**
- **WorldTwin recommendation**: Label as "Media attention heatmap" not "Conflict events"

---

## 🥉 BRONZE TIER — Context & engagement features

### 21. ESPN Sports (20 live matches)
- Unofficial scraped API. Can break without notice. Entertainment only.

### 22. Radio Browser (500 stations)
- Crowdsourced. ~30% broken streams. No QA process. Ambient feature.

### 23. Windy Webcams (500 cameras)
- Private API. Euro-centric. Wrong coordinates common. Visual context only.

### 24. Steam + Twitch Gaming (20 games)
- Limited to top titles. Twitch optional. Entertainment feature.

### 25. Wikipedia Trends (50 articles)
- Measures pageviews, not real-world importance. Cultural curiosity indicator.

---

## Geographic Coverage Reality Check

### Where we're STRONG (150+ countries, professional grade):
- **Economy**: World Bank (265), IMF (229), EIA Int'l (258), OWID (220), Comtrade (150+)
- **Weather**: Open-Meteo global grid, NOAA space weather, Berkeley Earth
- **Natural hazards**: USGS quakes (global), GDACS (global), NASA FIRMS fires (global)
- **Satellites/Space**: Space-Track (30k objects), CelesTrak, ISS

### Where we're MODERATE (50-150 countries):
- **Air quality**: OpenAQ (110 countries but 36% of nations have ZERO monitoring)
- **Emissions**: ClimateTRACE (54 countries with asset-level data)
- **Displacement**: IDMC (86 countries)
- **Ports/Trade**: PortWatch (62 countries), Comtrade monthly (27 importers)

### Where we're WEAK:
- **Conflict in closed societies**: UCDP captures ~33% of actual fatalities in data-dark zones
- **Sub-Saharan Africa**: Worst statistical capacity across almost every source
- **Small-scale fisheries**: GFW covers 3% of world's fishing fleet
- **Power grids outside US**: Only EIA-930 (US). ENTSO-E (EU) needs registration. No Asia/Africa grid data.
- **Domestic food prices**: FAO tracks international prices only, not what people actually pay in shops

### What's SYSTEMATICALLY INVISIBLE across ALL our sources:
1. **Informal economies** — not captured by any trade, GDP, or employment dataset
2. **Non-digitized populations** — people without phones/internet are invisible to most sensors
3. **State-censored regions** — DPRK, Eritrea, Xinjiang: data desert across all sources
4. **Sub-national inequality** — most data is country-level; province/city-level is sparse
5. **Future projections** — we show current state, not where things are heading (except IMF WEO forecasts and OECD CLI signals)

---

## What This Means for WorldTwin as a Decision Platform

### What we CAN credibly claim:
- "Here is what the world's best open data sources say about country X right now"
- "These 5 GOLD-tier indicators (WB, IMF, USGS, FAO, Comtrade) are the same data governments use"
- "This is where media attention is focused" (GDELT as attention proxy, NOT truth)
- "These fires/quakes/cyclones are confirmed by satellite/seismometer"
- "This trade disruption is detected by AIS vessel tracking"
- "This country's displacement crisis affects at least N people (lower bound)"

### What we CANNOT credibly claim (yet):
- "This is the complete picture of conflict in country X" — UCDP/GDELT both undercount
- "Air quality in city Y is safe" — many cities have no monitors
- "Country Z's emissions are exactly N tonnes" — ClimateTRACE vs self-reports differ 3×
- "This fishing effort data is accurate" — GFW sees 3% of fleet, overestimates 87%
- "Our GDP/trade forecast is reliable" — IMF has documented optimistic bias

### Architecture for trust — what WorldTwin MUST show:
Every data point on the globe should display:
1. **Source badge** — who produced this data (World Bank, USGS, GDELT...)
2. **Trust tier** — 🥇🥈🥉⚠️ icon
3. **Freshness** — "Updated 2 minutes ago" vs "Data from 2023"
4. **Coverage note** — "This source covers 265 countries" or "Limited to OECD members"
5. **Methodology one-liner** — "Satellite-detected thermal anomaly" or "Media article NLP coding"

This is what separates a serious platform from a visualization toy. The EU Copernicus EMS, INFORM Risk Index, and ACAPS do exactly this.

### The business insight layer (future):
When a user provides their location and company info, WorldTwin can derive insights by:

1. **Cross-referencing** their location against ALL layers simultaneously:
   - Natural hazard exposure (quakes, floods, cyclones, fire risk)
   - Supply chain disruption risk (PortWatch chokepoints, trade flow dependency)
   - Energy infrastructure (power plant mix, grid reliability)
   - Conflict proximity (UCDP events, GDACS alerts)
   - Economic context (GDP growth, inflation, unemployment)
   - Climate trajectory (Berkeley Earth anomaly, CO2 per capita)

2. **Confidence-weighted scoring**: weight GOLD sources higher than BRONZE. Flag when key indicators are missing for their region.

3. **Temporal comparison**: "Your country's water stress has increased 15% since 2020" (World Bank time series)

4. **Peer benchmarking**: "Compared to other [industry] companies in [region], your supply chain has [N] chokepoint dependencies"

**None of this requires new data** — it requires a smart query layer on top of what we already have. The 5 GOLD + 14 SILVER sources are sufficient for a credible v1.

---

## Recommended Next Steps

1. **Add trust badges to every layer in the UI** — pickcard already shows source name. Add the tier icon.
2. **Relabel GDELT layers** — "Media attention" not "Conflict events"
3. **Add coverage warnings** — when a user clicks a country with sparse data, show which indicators are missing
4. **Write a public methodology page** — link every data point to its source methodology
5. **Register for ENTSO-E** (EU grid) and **IDMC API** (richer displacement data) to fill the biggest remaining gaps
6. **Add ACAPS INFORM Risk Index** (free, CC BY) — this is the gold-standard composite risk score used by humanitarian agencies, and it would validate/complement our Pulse mode

---

*This assessment was built from peer-reviewed sources, official methodology documentation, and live verification of every cached dataset on the WorldTwin server.*
