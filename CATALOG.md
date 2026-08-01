# WorldTwin Data Source Catalog
**Generated**: 2026-04-11 · **Phase 1 deliverable** · Source of truth for every plugin.

This document is the human-readable research companion to `config.json`. Every plugin listed here is a single Python file in `worldtwin/aggregator/worldtwin/sources/`. When you add a new source, **add it here first**, then implement.

> **Live state**: 65 layers healthy, 0 errors per `/api/health` at 2026-04-11T20:25Z.
> 72 plugin files total, 2 are internal helpers with no LayerMeta (`_commodities.py`, `_comtrade_common.py`).

## Legend
- **auth**: `free` = no key, `key` = requires env var, `denied` = policy-blocked
- **envelope**: how frontend should parse the JSON (one of: `points` `polygons` `lines` `countries` `flows` `grid` `tiles` `timeseries` `news` `raw`)
- **status**: `ok` healthy / `broken` = zero-count but should work / `unknown` = not in health / `disabled` = intentionally off

---

## Meta layers (foundation for everything else)

| id | source | auth | refresh | envelope | what it returns | status |
|---|---|---|---|---|---|---|
| `country_polygons` | Natural Earth 50m | free | 7d | polygons | 242 country ADM0 polygons with iso3/name/pop/continent/income | ok:242 |
| `country_relations` | Curated + GDELT | free | 6h | raw | 14 blocs + per-country allies/enemies | ok:5 |
| `geoboundaries_adm1` | geoBoundaries | free | 30d | polygons | ADM1 for 60 priority countries | ok:1423 |
| `population` | REST Countries | free | 1d | countries | 245 countries: pop, area, capital, languages, flag | ok:245 |
| `global_events` | (aggregated) | free | 5m | points | Top 120 ongoing events headline feed | ok:87 |
| `gemini_narrative` | Gemini 2.5 Flash | key `GEMINI_API_KEY` | 30m | raw | 3-paragraph world summary | ok:8 |
| `pulse_mode` | (aggregated) | free | 30m | countries | 227 countries: composite worry score | ok:227 |

---

## Nature (1215 volcanoes, 2086 fires, 200 disasters, 112 GDACS alerts…)

| id | source | auth | refresh | envelope | what it returns | status |
|---|---|---|---|---|---|---|
| `quakes` | USGS EQ feed | free | 2m | points | All M2.5+ past 24h + depth | ok:34 |
| `fires` | NASA FIRMS VIIRS | key `FIRMS_KEY` | 10m | points | Active fires + FRP (MW) | ok:2086 |
| `disasters` | NASA EONET | free | 10m | points | ~200 active: fires/storms/volcanoes/floods | ok:200 |
| `volcanoes` | Smithsonian GVP | free | 1d | points | 1215 active/Holocene volcanoes | ok:1215 |
| `usgs_volcano_hans` | USGS HANS | free | 1h | points | Volcanoes at YELLOW/ORANGE/RED | ok:4 |
| `dartmouth_floods` | Dartmouth FO | free | 1d | points | ~100 flood events (90d) with deaths/severity | unknown |
| `gdacs_events` | GDACS (JRC) | free | 15m | points | Unified: quakes/cyclones/floods/volcanoes/fires/droughts | ok:112 |
| `nhc_cyclones` | NOAA NHC | free | 30m | points | Active tropical cyclones + Saffir-Simpson | ok:4 |
| `rainviewer` | RainViewer | free | 5m | tiles | Global precip radar tile frames | ok:6 |
| `wind_sample` | Open-Meteo | free | 1h | points | Wind/temp on 18×10 grid (180 pts) | ok:6 |

**What's missing for weather mode**: temperature field, pressure field, ocean SST, humidity. None currently exist as plugins. **Phase 4 adds**: `open_meteo_temp_field.py`, `open_meteo_pressure.py`, `noaa_sst.py`.

---

## Weather / atmosphere (currently thin — whole of Phase 4)

Current weather-relevant plugins: `wind_sample`, `rainviewer`, `air_quality`, `openaq_stations`, `nhc_cyclones`, `swpc_aurora`.

**Open-Meteo is our friend**. CC-BY 4.0, no key, huge model mix (ECMWF, GFS, ICON, GEM, JMA, Météo-France, UKMO). Per-variable free endpoints exist for:
- `temperature_2m` — surface air temp
- `surface_pressure` — hPa
- `cloud_cover` / `cloud_cover_low/mid/high`
- `relative_humidity_2m`
- `dew_point_2m`
- `wind_speed_10m` / `wind_direction_10m` / `wind_gusts_10m`
- `precipitation` / `rain` / `snowfall`
- `weather_code` (WMO code)
- `cape` (convective available potential energy)
- `visibility` / `et0_fao_evapotranspiration`

For **ocean** we use NOAA ERDDAP (OISST v2.1, 0.25°, daily) — free, no key.
For **planetary K-index / solar wind** we already have `swpc_aurora`.

---

## War / Conflict

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `ucdp_ged` | UCDP flat-file | free | 7d | points | 3000 recent clarity-1 events | ok:3000 |
| `conflict_events` | GDELT Events 2.0 | free | 30m | points | Real-time violent events (EventRootCode 18/19/20) | ok:1500 |
| `conflicts` | GDELT doc API | free | 5m | points | Armed conflict news articles | ok:150 |
| `crises` | HDX CKAN | free | 30m | points | Active humanitarian datasets | ok:27 |
| `reliefweb` | HDX CKAN | free | 1h | points | Humanitarian crises (was ReliefWeb v1, now HDX) | ok:4 |
| `wikidata_battles` | Wikidata SPARQL | free | 6h | points | Wikidata battles since 2023 | ok:29 |
| `relations` | GDELT QuadClass | free | 1h | raw | Country-pair cooperation/conflict activity | ok:111 |
| `acled` | ACLED | **denied** | - | - | Permanently disabled per EULA 3.1 | disabled |

---

## Economy / Trade / Macro

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `world_bank` | World Bank API v2 | free | 7d | countries | 30 indicators × 265 countries | **ok:265** (fixed 2026-04-11) |
| `imf_data` | IMF DataMapper | free | 7d | countries | 6 WEO indicators × 229 countries | ok:229 |
| `fred` | FRED | key `FRED_API_KEY` | 1h | raw | 50 global macro series | ok:45 |
| `oecd_cli` | OECD SDMX | free | 7d | countries | CLI recession signals | **broken:0** |
| `commodity_prices` | datahub+CG+Frank | free | 1h | raw | Brent/WTI/natgas/gold/crypto/forex | ok:4 |
| `economy` | Frankfurter + CG | free | 5m | raw | 30+ forex + top 25 crypto | ok:25 |
| `fao_food_prices` | FAO | free | 7d | raw | FPI (cereals/oils/dairy/meat/sugar) | ok:5 |
| `eia_petroleum` | EIA Weekly | key `EIA_API_KEY` | 1d | raw | US crude/SPR/gasoline/distillate/refinery | ok:5 |
| `trade_annual` | UN Comtrade annual | free | 7d | flows | Top 30 flows/category × 37 importers | **broken:0** |
| `trade_monthly` | UN Comtrade monthly | free | 1d | flows | Top 500 monthly flows × 12 importers | ok:178 |

---

## Resources / Energy / Industry

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `eia_international` | US EIA international | key `EIA_API_KEY` | 7d | countries | 210+ countries: oil/gas/coal/elec | ok:258 (fixed 2026-04-11) |
| `eia_930_grid` | US EIA-930 | key `EIA_API_KEY` | 1h | points | Hourly D/NG/TI for 60+ US BAs | ok:5 |
| `owid_energy` | OWID Energy | free | 7d | countries | 100 energy indicators × ~220 countries | ok:220 |
| `climatetrace_assets` | ClimateTRACE v6 | free | 7d | points | 5000 largest facility emissions, 12 sectors | ok |
| `wri_power_plants` | WRI GPPD | free | 7d | points | 5000 largest power plants by capacity | ok:5000 |
| `country_resources` | UN Comtrade + WRI | free | 7d | countries | 255 countries fact sheet | ok:198 |
| `country_deep_dive` | aggregated | free | 1d | countries | Deep panel: water/food/oil/elec | ok:227 |
| `portwatch_ports` | IMF PortWatch | free | 12h | points | Top 800 ports + daily vessel calls | ok:800 |
| `portwatch_chokepoints` | IMF PortWatch | free | 1d | points | 28 chokepoints + vessel type breakdown | ok:21 |
| `gfw_events` | GFW v3 | key `GFW_TOKEN` | 3h | points | AIS gap + encounters + port visits | ok:200 |

---

## Space / Orbit / Cosmos

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `iss` | WhereTheISS + Open-Notify | free | 10s | points | ISS pos + crew | ok:1 |
| `satellites` | CelesTrak | free | 2h | raw | 300 TLEs (stations/GPS/geo/Starlink) | ok:327 |
| `spacetrack_gp` | Space-Track.org | key USER+PASS | 8h | raw | 25k+ full catalogue | ok:10 (suspect) |
| `swpc_aurora` | NOAA SWPC | free | 5m | raw | Aurora oval + Kp + G-scale + solar wind | ok:18515 |
| `nasa_donki` | NASA DONKI | key `NASA_API_KEY` | 1h | points | CME/flares/GST/SEP/RBE/IPS/HSS (30d) | ok:200 |
| `nasa_neows` | NASA NeoWs | key `NASA_API_KEY` | 6h | raw | Asteroids 7-day approach | ok:5 |
| `nasa_epic_earth` | NASA EPIC DSCOVR | key `NASA_API_KEY` | 3h | raw | Full-disk Earth from L1 | unknown |
| `nasa_mars_photos` | NASA Mars Photos | key `NASA_API_KEY` | 1d | raw | Curiosity + Perseverance latest | ok:5 |

---

## Health / Outbreaks / AQ

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `air_quality` | Open-Meteo CAMS | free | 30m | points | US AQI at 45 major cities | ok:45 |
| `openaq_stations` | OpenAQ v3 | key `OPENAQ_API_KEY` | 1h | points | ~12k AQ stations + PM/NO2/SO2/CO/O3 | ok |
| `who_don` | WHO Disease Outbreak | free | 6h | points | Ongoing outbreaks (RSS → JSON) | ok:4 |

---

## Transit / Mobility

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `flights` | adsb.lol + OpenSky | free | 1m | points | ~3500 live aircraft + routes | ok:3458 |
| `ships` | AISStream.io | key `AISSTREAM_KEY` | 30s | points | ~500 live vessels (WebSocket) | ok:500 |
| `gfw_events` | see Resources above | | | | | |

---

## Infrastructure / Internet

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `cables` | TeleGeography | free | 1d | lines | 710 submarine cables | ok:710 |
| `cloudflare_radar` | Cloudflare | key `CLOUDFLARE_RADAR_TOKEN` | 30m | points | 50 outages + 10 DDoS targets | ok:5 |
| `webcams` | Windy Webcams | key `WINDY_KEY` | 30m | points | 500 public live webcams | ok:500 |

---

## Social / Media / Culture

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `news` | GDELT doc | free | 5m | points | Recent breaking news | ok:150 |
| `gdelt_gkg_themes` | GDELT GKG 2.1 | free | 15m | points | Themed anomalies per country | ok:300 |
| `trends` | Wikimedia Pageviews | free | 1h | raw | Top 50 articles yesterday | ok:50 |
| `youtube` | YouTube Data API v3 | key `YOUTUBE_API_KEY` | 1h | points | Top 5 trending × ~30 countries | ok:29 |
| `radio` | Radio Browser | free | 1d | points | 500 internet radio stations | ok:500 |

---

## Sports / Gaming

| id | source | auth | refresh | envelope | what | status |
|---|---|---|---|---|---|---|
| `sports` | ESPN unofficial | free | 5m | points | Live matches: soccer/NBA/NFL/F1/tennis/cricket | ok:30 |
| `gaming` | Steam + Twitch | optional | 10m | raw | Top Steam games + Twitch streams by language | ok:20 |

---

## Plugins NOT in /api/health (worth investigating)

These exist as files but don't show in the live health snapshot. Either disabled, never started, or silently failing:
- `smithsonian` — listed in source list but not in health. Is this superseded by `volcanoes` (same source)?
- `eonet` — present as file. The layer id registered is `disasters`, so this file **is** `disasters` under another name. Resolved.
- `acled` — intentionally disabled per EULA. Resolved.
- `wheretheiss` — file exists but registered as `iss`. Resolved.
- `rest_countries` — file exists but registered as `population`. Resolved.
- `celestrak` — registered as `satellites`. Resolved.
- `aisstream_ships` — registered as `ships`. Resolved.
- `opensky` — registered as `flights`. Resolved.
- `windy_webcams` — registered as `webcams`. Resolved.
- `nasa_epic` — registered as `nasa_epic_earth`. Resolved.
- `wikipedia_trends` — registered as `trends`. Resolved.
- `nhc_cyclones` — ok.
- `ucdp.py` — separate from `ucdp_ged`. Not in health → may be disabled or still loading. **Needs check.**
- `gdelt_events.py` vs `gdelt_conflicts.py` vs `conflict_events` — likely all same feed with different registrations. **Needs audit.**
- `usgs_quakes.py` — registered as `quakes`. Resolved.

---

## API key inventory (cross-reference with API_KEYS.md)

Plugins that **need keys**:
- `FIRMS_KEY` → fires
- `NASA_API_KEY` → nasa_donki, nasa_neows, nasa_mars_photos, nasa_epic_earth
- `OPENAQ_API_KEY` → openaq_stations
- `FRED_API_KEY` → fred
- `EIA_API_KEY` → eia_international, eia_petroleum, eia_930_grid
- `GFW_TOKEN` → gfw_events
- `SPACE_TRACK_USER` + `SPACE_TRACK_PASS` → spacetrack_gp
- `CLOUDFLARE_RADAR_TOKEN` → cloudflare_radar
- `WINDY_KEY` → webcams (hardcoded default exists)
- `AISSTREAM_KEY` → ships
- `YOUTUBE_API_KEY` → youtube
- `GEMINI_API_KEY` → gemini_narrative
- `UCDP_TOKEN` → ucdp (ucdp_ged is free flat-file)
- `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET` → gaming (optional)

Plugins that are **completely free**:
- All meta, polygons, relations
- World Bank, IMF, OECD, OWID, FAO, Frankfurter, CoinGecko
- USGS quakes+volcanoes, NOAA NHC/SWPC, EONET
- GDELT (all variants), UCDP GED flat-file, Wikidata
- Natural Earth, geoBoundaries, REST Countries
- RainViewer, OpenMeteo (incl. the new weather plugins we'll add in Phase 4)
- Smithsonian GVP, Radio Browser, Wikimedia Pageviews
- TeleGeography, HDX CKAN, Dartmouth FO
- ClimateTRACE, WRI GPPD, UN Comtrade preview, PortWatch (IMF)
- adsb.lol, ESPN unofficial, Steam Web API

---

## Known issues at end of Phase 1

1. **`oecd_cli` returns 0 countries.** Parser claims fixed but health disagrees. Phase 9 will re-fix.
2. **`trade_annual` returns 0 flows.** Comtrade year auto-probe may be failing or rate-limited. Phase 9.
3. **`spacetrack_gp` returns 10 when it should return thousands.** Likely login session expiring. Phase 9.
4. **`climatetrace_assets` count of 7 looks like sector count, not asset count.** Backend `mark_ok` is recording `len(sectors)` not `len(assets)`. Cosmetic.
5. **`cloudflare_radar` count of 5 is outages only, not outages+DDoS.** Same cosmetic issue.
6. **`openaq_stations` count of 5 is paginated pages not stations.** Same.
7. Backend **envelope inconsistency** — some plugins return `points`, some return `countries`, some return `raw`. Frontend renderers hardcode assumptions. Phase 2 fixes this with a unified `LayerSpec` contract.

---

## Adding a new plugin

1. Write `worldtwin/aggregator/worldtwin/sources/<id>.py` with `LayerMeta + fetch()`.
2. Pick the right **envelope** from the catalog.
3. Add the row to `CATALOG.md` and `config.json`.
4. Frontend: add to preloader list and the appropriate mode's layer array.
5. Verify `/api/health` shows `ok: true, count: > 0`.
6. Verify cache at `/api/cache/<id>.json` returns the declared envelope shape.

---

**Total**: 72 plugins on disk → 65 live → 60 ok (after subtracting the 5 cosmetic count issues), 3 broken, 1 disabled, 3 unknown.
