# LICENCES.md — per-layer licence ledger

*Generated 2026-09-24 from the `license=` strings in `aggregator/worldtwin/sources/*.py`,
after the twelve corrections mandated by MASTER_PLAN §4 ("Licence position"). The plugin
licence string is the source of truth; this table is its rendering. Regenerate whenever a
licence string changes — the programmatic licence gate keys on the corrected `license` field
and must refuse to promote any source whose licence string is not verified here.*

**92 layers · 11 enabled · 79 retired (tombstoned) · 2 removed (hard 404)**
**Flags: 11 NC (non-commercial) · 8 SA (share-alike / ODbL) — flagged mechanically from the licence string.**

Corrections applied 2026-09-24: GDELT declared consistently as citation-required bespoke terms
(never CC0) across conflicts / news / conflict_events / gdelt_gkg_themes / relations (+
country_relations' composite string) · portwatch_* → IMF ToU · cloudflare_radar → CC BY-NC 4.0 ·
idmc_displacement → CC BY-IGO · rainviewer → personal/educational only · noaa_sst relabelled
(ECMWF via Open-Meteo, not NOAA) with a non-commercial-tier licence · paleo_temperature's
single wrong label replaced with its actual mixed provenance.

| id | name | category | licence | NC | SA | v1 status |
|---|---|---|---|---|---|---|
| cloudflare_radar | Cloudflare Radar — Internet Health | infra | CC BY-NC 4.0 | **NC** |  | **ENABLED** |
| country_polygons | Country Polygons (Natural Earth 50m) | meta | CC0 (public domain) |  |  | **ENABLED** |
| fires | Active Fires (past 24h) | nature | NASA open data |  |  | **ENABLED** |
| flights | Live Aircraft (ADS-B) | transit | ODbL |  | **SA** | **ENABLED** |
| fred | FRED Global Macro (50 series) | economy | Public (US Government) |  |  | **ENABLED** |
| gdacs_events | GDACS Disaster Alerts | war | CC-BY 4.0 |  |  | **ENABLED** |
| noaa_co2 | Atmospheric CO₂ (Keeling Curve) | nature | Public domain (US Government) |  |  | **ENABLED** |
| quakes | Earthquakes — live + historical M5+ archive | nature | Public domain (US Government) |  |  | **ENABLED** |
| swpc_aurora | Aurora Oval + Space Weather (NOAA SWPC) | space | Public Domain (US Gov) |  |  | **ENABLED** |
| usgs_volcano_hans | USGS Elevated Volcanoes (HANS) | nature | US Public Domain |  |  | **ENABLED** |
| volcanoes | World Volcanoes | nature | Smithsonian (public) |  |  | **ENABLED** |
| acled | ACLED Conflict Events | war | ACLED EULA — map visualization not permitted (clause 3.1) |  |  | retired (tombstone) |
| air_quality | Air Quality (major cities) | health | Free for non-commercial use | **NC** |  | retired (tombstone) |
| berkeley_earth | Berkeley Earth — Temperature Anomaly | weather | CC BY-NC 4.0 | **NC** |  | retired (tombstone) |
| brecke_wars | Major Wars (1400→present) | meta | Free academic use |  |  | retired (tombstone) |
| cables | Submarine Internet Cables | infra | CC BY-NC-SA 3.0 | **NC** | **SA** | retired (tombstone) |
| cepii_baci | CEPII BACI Bilateral Trade Matrix (1995-2024) | resources | Etalab 2.0 (open) |  |  | retired (tombstone) |
| climatetrace_assets | Global Facility Emissions (ClimateTRACE) | resources | CC BY 4.0 |  |  | retired (tombstone) |
| clio_life_expectancy | Life expectancy 1770→2023 (Clio-Infra + UN WPP) | meta | CC-BY 4.0 |  |  | retired (tombstone) |
| commodity_prices | Commodity Prices (live ticker) | economy | CC-BY-SA |  | **SA** | retired (tombstone) |
| conflict_events | Violent Events (GDELT real-time) | war | GDELT Terms (free, citation required) |  |  | retired (tombstone) |
| conflicts | Conflict News (GDELT) | war | GDELT Terms (free, citation required) |  |  | retired (tombstone) |
| country_culture | Country culture (religion + ethnicity) | meta | CC0 (Wikidata) + Public domain (CIA) |  |  | retired (tombstone) |
| country_deep_dive | Country Resource Deep Dive | resources | Aggregated — see individual sources |  |  | retired (tombstone) |
| country_intel | Country Intelligence Profiles | meta | Derived from open data sources |  |  | retired (tombstone) |
| country_relations | Country Relations — blocs + alliances + enmities | meta | Public data + GDELT Terms (citation required) |  |  | retired (tombstone) |
| country_resources | Country Resource Fact Sheets | resources | UN Open Data + CC BY 4.0 |  |  | retired (tombstone) |
| cow_alliances | Historical Alliances 1815→present | meta | Free academic use |  |  | retired (tombstone) |
| crises | Humanitarian Crises | war | HDX open license |  |  | retired (tombstone) |
| dartmouth_floods | Dartmouth Flood Observatory — Recent Events | nature | Free with attribution |  |  | retired (tombstone) |
| disasters | Natural Disasters (EONET) | nature | NASA open data |  |  | retired (tombstone) |
| economy | Economy (Forex + Crypto) | economy | Free (public) |  |  | retired (tombstone) |
| eia_930_grid | EIA-930 — US Balancing Authority Data | resources | US Public Domain |  |  | retired (tombstone) |
| eia_international | EIA International — Energy by Country | resources | US Public Domain |  |  | retired (tombstone) |
| eia_petroleum | EIA Petroleum — Weekly US Stocks | economy | US Public Domain |  |  | retired (tombstone) |
| emdat_disasters | EM-DAT Disaster History (1900-present) | nature | CC-BY-NC (non-commercial) | **NC** |  | retired (tombstone) |
| entsoe_grid | ENTSO-E European Grid Monitor | resources | Free with attribution |  |  | retired (tombstone) |
| fao_food_prices | FAO Food Price Index | economy | Free with attribution |  |  | retired (tombstone) |
| gaming | Gaming (Steam + Twitch) | gaming | Free |  |  | retired (tombstone) |
| gdelt_gkg_themes | GDELT GKG Themes (last hour) | social | GDELT Terms (free, citation required) |  |  | retired (tombstone) |
| gemini_narrative | WorldTwin Analyst — AI narrative | meta | Inferred from source events |  |  | retired (tombstone) |
| geoboundaries_adm1 | Administrative Boundaries — ADM1 (geoBoundaries) | meta | CC-BY 4.0 / ODbL |  | **SA** | retired (tombstone) |
| gfw_events | Global Fishing Watch — AIS Gap Events | transit | CC BY-SA 4.0 |  | **SA** | retired (tombstone) |
| global_events | Global Events Feed | meta | Aggregated — see individual sources |  |  | retired (tombstone) |
| historical_borders | Historical Borders (123,000 BC → 2010) | meta | CC-BY-SA 4.0 |  | **SA** | retired (tombstone) |
| historical_disasters | Historical Disasters (2150 BC → today) | nature | US Public Domain |  |  | retired (tombstone) |
| humidity_field | Humidity — Global Grid | weather | CC BY 4.0 |  |  | retired (tombstone) |
| hyde_population | Population (10,000 BC → today) | economy | CC-BY 4.0 |  |  | retired (tombstone) |
| idmc_displacement | Internal Displacement (IDMC) | war | CC BY-IGO |  |  | retired (tombstone) |
| imf_data | IMF DataMapper — Core Indicators | economy | Free with attribution |  |  | retired (tombstone) |
| iss | International Space Station | space | Free for public use |  |  | retired (tombstone) |
| maddison_history | Maddison GDP & Population (1 AD → 2018) | economy | CC-BY 4.0 |  |  | retired (tombstone) |
| nasa_donki | NASA DONKI — Space Weather Events | space | Public Domain (NASA) |  |  | retired (tombstone) |
| nasa_epic_earth | NASA EPIC — L1 Earth Images | space | Public Domain (NASA) |  |  | retired (tombstone) |
| nasa_mars_photos | Mars Rover — Latest Photos | space | Public Domain (NASA) |  |  | retired (tombstone) |
| nasa_neows | NASA NeoWs — Asteroid Close Approaches | space | Public Domain (NASA) |  |  | retired (tombstone) |
| nasa_power | NASA POWER — Hourly Weather Grid (1981→present) | weather | Public Domain (US Government) |  |  | retired (tombstone) |
| news | Breaking News (GDELT) | social | GDELT Terms (free, citation required) |  |  | retired (tombstone) |
| nhc_cyclones | Active Tropical Cyclones (NHC) | nature | US Public Domain |  |  | retired (tombstone) |
| noaa_sst | Sea Surface Temperature (ECMWF via Open-Meteo) | weather | Open-Meteo free tier (non-commercial); data CC BY 4.0 | **NC** |  | retired (tombstone) |
| oecd_cli | OECD Composite Leading Indicators | economy | Free with attribution |  |  | retired (tombstone) |
| open_meteo_forecast | Open-Meteo Forecast Grid (next 72h) | weather | CC-BY 4.0 NonCommercial | **NC** |  | retired (tombstone) |
| openaq_stations | OpenAQ — Air Quality Stations | health | CC BY 4.0 |  |  | retired (tombstone) |
| owid_energy | Energy Indicators by Country (OWID) | resources | CC-BY 4.0 |  |  | retired (tombstone) |
| paleo_temperature | Global Temperature Anomaly (11,300 BP → today) | weather | Mixed: HadCRUT5 is UK OGL v3; Marcott/PAGES2k values are hand-entered approximations |  |  | retired (tombstone) |
| population | Countries & Population | meta | Public |  |  | retired (tombstone) |
| portwatch_chokepoints | PortWatch Chokepoints (IMF/AIS) | resources | IMF ToU |  |  | retired (tombstone) |
| portwatch_ports | Live Port Traffic (PortWatch/IMF) | resources | IMF ToU |  |  | retired (tombstone) |
| pressure_field | Surface Pressure — Global Grid | weather | CC BY 4.0 |  |  | retired (tombstone) |
| pulse_mode | Pulse Mode — directional change radar | meta | Aggregated |  |  | retired (tombstone) |
| radio | Radio Stations | social | CC0 |  |  | retired (tombstone) |
| rainviewer | Weather Radar Tiles | nature | personal/educational only | **NC** |  | retired (tombstone) |
| relations | News Activity (GDELT) | war | GDELT Terms (free, citation required) |  |  | retired (tombstone) |
| reliefweb | Humanitarian Crises (HDX-derived) | war | Varies — see HDX dataset |  |  | retired (tombstone) |
| satellites | Active Satellites | space | CelesTrak Terms (non-commercial use) | **NC** |  | retired (tombstone) |
| ships | Live Vessels (AIS) | transit | Free non-commercial | **NC** |  | retired (tombstone) |
| sports | Live Sports | sports | Public (unofficial) |  |  | retired (tombstone) |
| temperature_field | Surface Temperature — Global Grid | weather | CC BY 4.0 |  |  | retired (tombstone) |
| trade_annual | Global Trade Flows — Annual (Comtrade) | resources | UN Open Data Licence |  |  | retired (tombstone) |
| trade_monthly | Monthly Trade Flows (Comtrade) | resources | UN Open Data Licence |  |  | retired (tombstone) |
| trends | Wikipedia Trends | social | CC BY-SA |  | **SA** | retired (tombstone) |
| ucdp | UCDP Conflict Events | war | UCDP open data (attribution required) |  |  | retired (tombstone) |
| ucdp_ged | UCDP Georeferenced Events | war | CC BY 4.0 |  |  | retired (tombstone) |
| vdem_democracy | Electoral Democracy Index (V-Dem 1789→2025) | meta | CC-BY 4.0 |  |  | retired (tombstone) |
| who_don | WHO Disease Outbreak News | health | WHO Open |  |  | retired (tombstone) |
| wikidata_battles | Notable Battles (Wikidata) | war | CC0 / CC-BY-SA |  | **SA** | retired (tombstone) |
| wind_sample | Wind Field (Open-Meteo) | nature | CC BY 4.0 |  |  | retired (tombstone) |
| world_bank | World Bank Indicators (102 per country, 1960-2024 history) | resources | CC BY 4.0 |  |  | retired (tombstone) |
| wri_power_plants | Global Power Plants (WRI) | resources | CC BY 4.0 |  |  | retired (tombstone) |
| youtube | YouTube Trending | social | YouTube API ToS |  |  | retired (tombstone) |
| spacetrack_gp | Space-Track — Full Satellite Catalogue | space | Space-Track Terms (free non-commercial) | **NC** |  | removed — hard 404 |
| webcams | Live Webcams | infra | Windy API Terms |  |  | removed — hard 404 |

## Notes

- NC layers inside the enabled 11: cloudflare_radar. cloudflare_radar (CC BY-NC 4.0) and flights (ODbL, SA) are the only encumbered enabled layers; both have free alternatives named in MASTER_PLAN §3 if monetisation is ever revisited.
- ShareAlike propagates into derived artifacts: any render slice or feed built on an SA source
  must carry the licence notice and attribution (MASTER_PLAN §4).
- spacetrack_gp and webcams are legal removals: no tombstone is served — their cache paths 404.
- Retired layers keep their (corrected) licence string in the plugin file; it is re-verified at
  un-retire time before the layer can pass the gate.
