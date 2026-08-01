# WorldTwin — Architecture & Cache Index

Single source of truth. Last refreshed 2026-04-25 after the cleanup pass.

## Layout

```
WorldTwin/
├── aggregator/                  # FastAPI scheduler + ~83 plugins → JSON caches
│   └── worldtwin/
│       ├── scheduler.py
│       ├── server.py
│       ├── registry.py
│       ├── models.py            # LayerMeta + helpers
│       └── sources/             # one Python file per plugin
├── frontend/
│   ├── index.html               # ONE entrypoint, loads ~32 JS modules in order
│   ├── config.json              # frontend-side metadata mirror
│   └── js/
│       ├── time/                # time-foundation modules
│       └── *.js                 # one module per concern (no mega files)
└── scripts/                     # validation tooling (visual-diff, screenshots)
```

## Aggregator — the data layer

### Plugin contract
Each `sources/*.py`:
1. `LAYER = LayerMeta(id=..., refresh_s=..., requires_key=..., key_env=...)`
2. `async def fetch(client) -> dict | tuple[dict, dict]`
3. `register(LAYER, fetch)` at module level

The scheduler imports every non-`_` file in `sources/`, runs `fetch()` on schedule, writes return value to `CACHE_DIR/{id}.json`, and serves it at `GET /api/cache/{id}.json`.

**Disable a plugin**: `enabled=False` in `LayerMeta`, or rename file with leading `_`.

### Cache index — what each cache answers

| id | source | shape | feeds frontend |
|---|---|---|---|
| `acled` | ACLED (paid) | events | DISABLED |
| `air_quality` | Open-Meteo | array(42 cities) | layers.js air_quality |
| `cables` | TeleGeography | geojson(710) | connections.js |
| `climatetrace_assets` | ClimateTRACE | points(5000) | layers2.js |
| `cloudflare_radar` | Cloudflare | outages | ai_narrative digest |
| `commodity_prices` | CoinGecko | items + crypto | ai_narrative |
| `conflict_events` | GDELT | events(1500) | layers2.js |
| `conflicts` | GDELT news | articles | layers2.js news |
| `country_culture` | Wikidata + Pew | countries(127) | mapmode religion/ethnicity, dossier |
| `country_deep_dive` | composite | countries(227) | mapmode water/food, dossier |
| `country_intel` | composite | countries | mapmode-card builders (NOT dossier — dossier reads source caches direct) |
| `country_polygons` | Natural Earth | geojson(242) | mapmode base layer |
| `country_relations` | curated + GDELT | by_country(147) | mapmode political, dossier, hover allies |
| `country_resources` | composite | countries(198) | dossier exports/imports + centroid lookup |
| `crises` | HDX | array | layers2.js |
| `disasters` | NASA EONET | events(200) | layers2.js |
| `economy` | CoinGecko | forex + crypto | briefing, ai_narrative |
| `eia_930_grid` | EIA 930 | by_ba | layers2.js US grid |
| `eia_international` | EIA | countries(258) | (no renderer — opt) |
| `eia_petroleum` | EIA | latest + history | ai_narrative |
| `entsoe_grid` | ENTSO-E | by_country | layers2.js EU grid |
| `fao_food_prices` | FAO | csv | ai_narrative |
| `fires` | NASA FIRMS | array(2160) | layers.js |
| `flights` | adsb.lol | states | layers.js |
| `fred` | St Louis Fed | series(30+) | briefing KPIs, ai_narrative |
| `gaming` | Steam + Twitch | top games | layers2.js |
| `gdacs_events` | GDACS | events(44) | layers.js, ai_narrative |
| `gdelt_gkg_themes` | GDELT GKG | themes | ai_narrative |
| `geoboundaries_adm1` | geoBoundaries | shapes | mapmode-card province lookup |
| `gfw_events` | Global Fishing Watch | events(200) | layers2.js, ai_narrative |
| `global_events` | composite | events(83) | events-pulse.js, briefing, ai_narrative |
| `historical_borders` | aourednik | snapshots(53) | historical-borders.js |
| `historical_disasters` | NOAA + Smithsonian | events | historical-events.js |
| `humidity_field` | Open-Meteo | grid | layers2.js |
| `hyde_population` | OWID | countries(238) | mapmode population_history |
| `idmc_displacement` | IDMC | (verify) | TODO: wire or retire |
| `imf_data` | IMF | countries(229) | mapmode inflation/debt, dossier, ai_narrative |
| `iss` | wheretheiss | iss + crew | layers.js |
| `maddison_history` | OWID | countries(178) | mapmode gdp_pc_history, dossier sparkline |
| `nasa_donki` | NASA DONKI | events(200) | ai_narrative |
| `nasa_mars_photos` | NASA | rovers | (no renderer — opt) |
| `nasa_neows` | NASA | hazardous | layers2.js asteroids |
| `news` | GDELT | articles | layers2.js |
| `nhc_cyclones` | NOAA NHC | storms | layers.js, ai_narrative |
| `noaa_co2` | NOAA GML + EPICA | stations + 800kyr series | layers2.js + scrubber |
| `noaa_sst` | NOAA OISST | grid | layers2.js |
| `oecd_cli` | OECD | countries(22) | ai_narrative |
| `openaq_stations` | OpenAQ v3 | by_country | layers2.js |
| `owid_energy` | OWID | countries(220) | mapmode renewable, energy-viz |
| `paleo_temperature` | Marcott + PAGES2k + HadCRUT5 | series | (briefing KPI possible) |
| `population` | REST Countries | array(245) | basic facts lookup |
| `portwatch_chokepoints` | IMF PortWatch | chokepoints(21) | layers.js, briefing, ai_narrative |
| `portwatch_ports` | IMF PortWatch | ports(800) | layers2.js |
| `pressure_field` | Open-Meteo | grid | layers2.js |
| `pulse_mode` | composite | countries(227) | mapmode pulse, briefing, ai_narrative |
| `quakes` | USGS | features(42) | layers.js, ai_narrative |
| `radio` | Radio Browser | array(500) | layers2.js |
| `rainviewer` | RainViewer | tiles | layers.js |
| `relations` | composite | countries(135) | LEGACY (use country_relations) |
| `reliefweb` | HDX | disasters | layers2.js, ai_narrative |
| `satellites` | CelesTrak | array(323) | layers.js |
| `ships` | AISStream | array(500) | layers.js |
| `spacetrack_gp` | Space-Track | catalog | layers2.js |
| `sports` | ESPN | matches | layers2.js |
| `swpc_aurora` | NOAA SWPC | aurora + Kp | layers.js, ai_narrative |
| `temperature_field` | Open-Meteo | grid | layers2.js |
| `trade_annual` | UN Comtrade | flows(483) | connections.js trade arcs |
| `trade_monthly` | UN Comtrade | flows(128) | TODO: monthly mode |
| `trends` | composite | top | (no renderer — opt) |
| `ucdp` | UCDP API | events | layers2.js |
| `ucdp_ged` | UCDP-GED | events(3000) | layers.js, ai_narrative |
| `usgs_volcano_hans` | USGS HANS | volcanoes | layers2.js |
| `volcanoes` | Smithsonian GVP | features(1215) | layers2.js |
| `webcams` | Windy | webcams | layers2.js |
| `who_don` | WHO DON | outbreaks | layers2.js, ai_narrative |
| `wikidata_battles` | Wikidata SPARQL | battles | layers2.js, ai_narrative |
| `wind_sample` | Open-Meteo | grid | wind-canvas.js |
| `world_bank` | World Bank WDI | countries(265) × indicators | mapmode (most), dossier, briefing |
| `wri_power_plants` | WRI GPPD | by_country(167) | layers2.js |
| `youtube` | YouTube | countries(29) | layers2.js |
| `gemini_narrative` | **AI narrative** | digest + 3 paragraphs | briefing.js |

**Hard rule for cache reads:** World Bank indicator IDs contain dots (`NY.GDP.MKTP.CD`). Never `path.split('.')`. Always `cache.countries[iso3][indicatorId]`.

## Frontend — the visualization layer

### Module load order (index.html)

Time foundation MUST come before Cesium-aware modules:

```
js/time/clock.js          # signed-int year ↔ JulianDate
js/time/cache.js          # century-bucketed LRU
js/time/series.js         # HistoricalSeries interpolator
js/time/scrubber.js       # bottom timeline widget
js/time/auto-history.js   # auto-load historical layers when scrubbing
js/icons.js
js/design.js              # CSS vars + design tokens
js/pickcard.js            # universal click-card
js/cesium-setup.js        # buildEarthViewer + atmosphere + era imagery
js/wind-canvas.js
js/preloader.js
js/planets.js             # Earth/Mars/etc switcher
js/layers.js              # core renderers (~30)
js/layers2.js             # phase-3 orphan plugin renderers (~20)
js/historical-borders.js  # 53-snapshot polity overlay
js/historical-events.js   # 2150 BC+ disasters
js/connections.js         # trade arcs + cables + ally radial lines
js/dossier.js             # multi-source country deep-dive
js/events-pulse.js        # global_events globe markers
js/briefing.js            # bottom-left World Briefing panel
js/hover-tooltip.js       # value-on-hover tooltip
js/onboarding.js          # first-visit overlay
js/mapmode.js             # EU4-style choropleth engine
js/mapmodes-data.js       # 19 mapmode definitions
js/mapmode-bar.js
js/event-glyphs.js
js/war-hotspots.js
js/energy-viz.js
js/mapmode-card.js        # per-mapmode deep-dive (uses country_intel)
js/layer-browser.js       # right-side unified browser
js/layer-toggles.js
js/modes.js               # bottom mode preset bar
js/ui.js                  # legend strip, KPI row, ticker
js/app.js                 # boot, click/hover handlers
```

### Globals — the inter-module contract

| Global | Owner | Purpose |
|---|---|---|
| `window.viewer` | cesium-setup.js | Cesium.Viewer instance |
| `window.Clock` | time/clock.js | year sub/set, JulianDate helpers, ISO 8601 BC support |
| `window.Scrubber` | time/scrubber.js | mount, registerLayer, setVisible |
| `window.TimeCache` | time/cache.js | bucketForYear, get, getRange, preload |
| `window.HistoricalSeries` | time/series.js | constructor for interpolated series |
| `window.LAYERS` | layers.js / layers2.js | { id: { render, clear } } |
| `window._cacheStore` | preloader.js | Map of cacheId → JSON |
| `window.fetchCache(id)` | preloader.js | async loader |
| `window.Mapmode` | mapmode.js | register, activate, hoverCountry, list, current, repaint |
| `window.MAPMODE_COLORS` | mapmode.js | { iso3: hex } — read every frame |
| `window.MAPMODE_HIGHLIGHT` | mapmode.js | { iso3: hex } — hover overlay |
| `window.Connections` | connections.js | renderTradeFlows, renderCables, renderHoverLines |
| `window.showDossier(iso3, opts?)` | dossier.js | open multi-source country panel |
| `window.showMapmodeCard(iso3)` | mapmode-card.js | per-mapmode card |
| `window.showOnboarding()` | onboarding.js | reopen welcome overlay |
| `window.Briefing` | briefing.js | build, show, hide |
| `window.EventsPulse` | events-pulse.js | render, clear |
| `window.activateMode(modeId)` | modes.js | switch preset bundle |
| `window.Planets` | planets.js | switchToBody, currentBody |
| `window.swapBaseForYear(year)` | cesium-setup.js | era-aware base imagery swap |
| `window.autoLoadHistoricalLayers(year)` | time/auto-history.js | toggle borders/disasters by year |

## LLM — single point of AI

There is **ONE** AI call in the system: `aggregator/worldtwin/sources/ai_narrative.py`.

- Builds a 22-section digest from caches (chokepoints, macros, conflict, hazards, disease, space weather, internet, dark vessels, battles, commodities, food, oil, crises, IMF inflation/debt, OECD CLI, double-trouble countries, ...)
- Calls **Gemini 2.5 Pro** (free tier on `GEMINI_API_KEY`)
- Falls back to Gemini 2.5 Flash if Pro fails
- Falls back to Claude Sonnet 4.6 (via OpenRouter, only if `OPENROUTER_API_KEY` is set)
- Cache id `gemini_narrative` (legacy id, kept for frontend compat)
- Frontend reads via `briefing.js`, displays alongside ground-truth strip pulled directly from caches

**To swap the model**: change the model string in the `_call_*` functions. Output schema unchanged.

**To add data to the LLM**: add a new section in `_build_digest()`, pre-compute deltas/extremes, append to the prompt's `AVAILABLE DIGEST SECTIONS` list, and the citation rule will pick it up automatically.

## Deploy workflow

Server: Oracle Cloud `129.151.191.74`. SSH key: `Solo/ssh-key-2026-02-08.key`.

```
# Frontend JS file
scp -i $KEY local.js opc@129.151.191.74:/home/opc/worldtwin/weather/js/local.js

# Aggregator plugin
scp -i $KEY plugin.py opc@129.151.191.74:/home/opc/worldtwin/aggregator/worldtwin/sources/plugin.py
ssh -i $KEY opc@129.151.191.74 "cd /home/opc/worldtwin && sudo docker compose restart aggregator"
```

**Frontend has NO build step.** Edit JS, scp, hard-reload. Done.

## What's NOT in the project (intentional)

- No bundler, no transpiler, no React/Vue/Svelte
- No backend database — every cache is a JSON file on disk
- No user accounts — single-tenant globe
- No authentication
- No git history of historical analytics

## Open issues

- `idmc_displacement` writes a cache but no frontend reads it. Wire or retire.
- `trade_monthly` has 128 monthly flows; `connections.js` only renders annual. Add toggle.
- `dartmouth_floods` upstream is dead (404). Disable + remove from registry.
- `acled` disabled (paid). Leave file for future re-enable.
