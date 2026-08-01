# WorldTwin — Master Plan

*Written 2026-08-01. Supersedes VISION.md D1–D8 where they conflict. Every number in this document was measured on the live box unless marked as an estimate.*

---

## 1. The decision

**WorldTwin becomes Earth Record: a dated, sourced daily record of what Earth's public instruments reported — published as a brief, explorable as a globe.**

The one-sentence promise, to be used verbatim on every surface:

> **What the instruments said. Dated, sourced, and never quietly fixed.**

The paragraph, also verbatim:

> Earth Record publishes what Earth's public instruments reported today — earthquakes, storms, fires, aircraft, internet outages, aurora — as a dated daily brief and a live globe. Every number carries its source and the minute it was fetched. Nothing here is generated. When a source goes dark we say so on the front page, by name. Yesterday's brief stays exactly as it was published, and if we correct it we publish the correction beside it.

Who it is for, in priority order:

1. **Feed-reader-native world-watchers** who follow events but distrust headlines. Reachable at zero budget through RSS, self-hosted-dashboard communities, and one Show HN. They select on exactly the attribute this product has.
2. **Journalists, OSINT and open researchers** who need a citable dated source. Small in volume, decisive for credibility, and the only audience that generates inbound links.
3. **Self-hosted dashboard builders** (Glance has 36.1k stars and a `custom-api` widget; none of the 20 listed personal dashboards has a world-data widget). Highest return frequency of any audience, and the cheapest to serve — Caddy already emits the exact artifact they consume.

Explicitly **never**: emergency responders (Watch Duty owns this with 70+ human verifiers and push; a missed alert is worse than no alert), traders and commodity desks (need SLAs and licensed data), defence analysts (Dataminr's $40–100k/yr buys indemnity this cannot offer), and educators-as-classroom-mode (NASA Worldview already ships a free NASA-branded date slider with classroom permalinks and GIF export). **This revises VISION.md D8, which ranked educators as beachhead #1. That ranking was wrong.**

Breadth is the *proof*, not the promise. Ninety-two feeds on one free ARM box is a credibility artifact and a launch story. It is not a product claim, because it is now a weekend-buildable commodity — worldashboard.com, earthstatus.live and liveearthviewer.com all advertise the same thing and have literally zero measurable traffic.

**The differentiator is the record, and the honesty is the method that makes the record trustworthy.** Provenance alone is table stakes: Our World in Data, Google Data Commons and Zoom.earth all cite their sources. What nobody publishes is a dated, cross-domain record of what the whole board said on a given day, with the failures named.

---

## 2. Reality check

### What is true today

- The site is live at `https://worldtwin.duckdns.org/worldtwin/` (Cesium client) and `/worldtwin/v2/` (MapLibre client). HTTPS works via Caddy's own Let's Encrypt.
- The best decision in the codebase is that Caddy serves `/api/cache/*` directly off disk. This is why a six-day total backend outage was invisible to visitors. **Every architectural decision below is constrained by preserving that property.**
- 92 auto-discovered plugins. `/v1/layers` reports 88; `/api/health` reports 82. Six enabled layers — gdacs_events, imf_data, population, portwatch_ports, satellites, ucdp — are *absent* from health rather than red, because `scheduler.py:33-36` returns before `mark_ok`/`mark_error` when a plugin swallows its exception and returns `None`. 72 of 92 plugins use `return None` as their failure path.
- `/api/health` returns a hardcoded `"ok": True` (`server.py:797-804`) and that is what the v2 client polls every 30 seconds to drive its "honest freshness indicator."
- `gdacs_events` is **default-on** in the v2 client and was last fetched 2026-07-26 against a 15-minute TTL — 602× overdue — while the freshness chip reads green because it takes the *maximum* fetch time across all layers.
- Nine layers report `ok: true` while more than 72 hours past their refresh. `oecd_cli` serves scrambled 1976–1990 data as a recession signal. `fao_food_prices` has served March 2018 since a month-stamped URL started 404ing. `world_bank` has 7 silently empty indicators that vary run to run (a 90-second timeout against measured 50–61s responses).
- `pulse_mode` ranks Zambia and Angola as the two most concerning countries on Earth (composite 100/100) from a single fire subscore computed over a 5°×5° cell around the country centroid. Zero of 227 countries have 4 or 5 of its 5 subscores.
- `gemini_narrative` publishes "US Fed funds moved +830.77% over ~12 months" for a ten-year move, and two of its three paragraphs are empty strings, because `ai_narrative.py:125` hardcodes the window instead of reading the series' timestamps.
- History store: 55.93 GB SQLite, 3.8 GB WAL, retention gated off because VACUUM needs the live size free alongside the original and only ~44 GB is available. 96% of it is an EAV observations table serving three static sparklines. Snapshots — the part that implements "replayable" — cost ~2.8 GB.
- Snapshots run 2026-06-11 to 2026-08-01: 68,083 rows, 87 layers, **46 distinct days**. Six days are missing (2026-07-25, and 07-27 through 07-31 — the outage).
- The box writes ~107 GB/day to `/data`, sits at 65–74% iowait with `b=5`, and the aggregator cgroup reads 99.98% of `memory.max` — which is 2.3 GB of reclaimable page cache, not risk. Real anon headroom is ~2.36 GB, verified by allocating 400 MB inside the container without an OOM.
- **The Caddy container has `memory.max = 128 MiB` and idles at 54.63 MiB.** It is the sole TLS terminator and router for company-lakeside, company-sportsstock, company-bergen, company-kayakco, jj-app, admin and searxng.
- There is no access log anywhere. No analytics. Zero GitHub stars. Every claim about traffic is a guess.
- Measured maintainer capacity: 64 commits across **9 distinct working days in 111 calendar days**, with gaps of 11, 21, 24 and 50 days. Within a session, throughput is very high — the entire v2 client (18 files, 3,845 lines) landed in a 75-minute commit span. **The binding constraint is session arrival, not hours of work.**

### What should be killed

| Kill | Why |
|---|---|
| `/api/cache/spacetrack_gp.json` | 15,029,198 bytes of raw GP/TLE from a **suspended** Space-Track account, publicly downloadable, under a User Agreement and PL 108-136 that restrict redistribution. Live breach. Delete today. |
| `/api/cache/webcams.json` | 690 KB of Windy's registry, whose terms read "Redistribution of any part of the API or the included data to any third party is forbidden," with the required credits actively hidden by `display:none !important`. Live breach. Delete today. |
| `gaming` | `steam_twitch.py:25-41` maps a stream's **language** to a city and plots viewers there. Spanish → Madrid, Arabic → Riyadh. Fabricated geography rendered as fact. |
| `youtube` | Pins a video to a capital city. Also stores Non-Authorized Data indefinitely against a 30-day Developer Policy cap, because the prune never runs. |
| `sports` | Undocumented private ESPN endpoint, no ToS grant, no licence; the exposure is ESPN's upstream rights contracts. Already broken (11 of 34 events geocoded, all scheduled). |
| `global_events` GKG points | Renders GDELT theme codes as "Armedconflict surging in US" at 14 decimal places of stated precision, scattered across Kansas. |
| `pulse_mode` composite | A WorldTwin-authored risk score averaging whichever subscores happen to exist. Bermuda and Nauru rank globally "most concerning" for burning diesel. |
| `gemini_narrative` | Its own largest output is a checkable falsehood on the front door. Templates write the brief better, cheaper, and match the stated voice ("no editor, no opinions"). |
| The Cesium client as a development target | 44 global-namespace IIFEs, `setTimeout` load-order retries, a 4,037-line CSS file with three successive "APPLE-CLEAN" repair passes, ~25 MB before first paint, and most of the live charter violations. Freeze, do not delete. |
| The WorldTwin name | `worldtwin.app` is a live competitor in the same category already outranking the real site on the brand query; `.com` is on Afternic at aftermarket pricing; `duckdns.org` is on IPFire's malware DBL and blocked by corporate and school DNS filters; and "twin" means *simulation* — the opposite of a product whose founding act was disabling the satellites layer rather than shipping fabricated positions. |

---

## 3. Product definition

### v1 is three artifacts

1. **`/brief/YYYY-MM-DD`** — a static dated page, permanent, machine-readable twin, RSS feed, archive index. This is the product and the return loop.
2. **The globe at `/`** — the MapLibre client, 8–12 honest layers, ≤4 on screen at a time.
3. **`/status` and `/charter`** — the doctrine and the full 92-row ledger with explicit states.

### In scope

- 16 plugins enabled. Up to 12 render on the globe; 2 are brief-only feeds (`noaa_co2`, `fred`). Locked core: **quakes, fires, gdacs_events, volcanoes, flights, swpc_aurora, cloudflare_radar (outages)**, plus `country_polygons` as base geometry. Candidates admitted one at a time as each clears the gate: **nhc_cyclones, cables, portwatch_chokepoints, ucdp, who_don**. `usgs_volcano_hans` folds its alert level into `volcanoes`.
- The admission gate is a criterion, not a number. A layer enters only when it (a) has a free shape slot in its family, (b) declares `max_staleness_s` and passes it, (c) has a licence string verified in `docs/LICENCES.md`, (d) has a `mark_error` path. **Launch at ≥8. Cap at 12.** The registry cap is 15, which is cognitive, not chromatic.
- The daily brief: five items, template-generated, deterministic, exception-led.
- Per-layer honest freshness expressed on the marks themselves, not only in a chip.
- URL-as-state carrying camera and selection.
- A daily off-Oracle git push of the brief archive.
- One 1200×630 PNG per day serving as brief hero, `og:image` and share card.

### Explicitly out, and published as out on `/charter#not-in-this-version`

| Out | Why |
|---|---|
| The 800,000 BC time scrubber | Needs `historical_borders` split from a 25.65 MB gz monolith into 53 files and `geoboundaries_adm1` split and simplified from 33.3 MB gz, plus per-point provenance flags. Deep time is a different product. |
| Country choropleths | Needs `country_polygons` quantized and `world_bank` split from 6.52 MB gz into a 0.18 MB gz latest-manifest. Stage 9. |
| The AI narrative, anywhere | Retired. The positioning says "Nothing here is generated"; keeping a generated page on the same domain is a self-refutation on the front door. |
| The 10-planet selector, Mars photos | Off-mission and already unreachable in v2. |
| Per-country dossiers | v1 ships the Detail card plus a table view. |
| Search | Unnecessary below ~40 layers. |
| Accounts, saved views beyond the URL | No. |
| Push, alerts, SLAs | Never. |
| `/on/YYYY-MM-DD` replay | Stage 9, gated on 90 days of unbroken archive commits. Do not solicit citation for a permalink you cannot guarantee. |

### Monetisation

**Free of charge for v1 and v2.** Donations only (Ko-fi / GitHub Sponsors) plus a "how this is funded and licensed" page. No ads, no subscription, no paid API, no B2B tier.

This is a *decision with a stated review trigger*, not an eternal invariant — because the licence denominator that justifies it is shrinking. Today ~22 of 92 layers plus the CARTO basemap forbid commercial use, and a single ad unit meets the CC BY-NC definition. But v1 is 12 layers, and the source work below removes NC ties on independent grounds (webcams dropped, rainviewer retired, the Open-Meteo family retired, berkeley_earth → GISTEMP, noaa_sst → NOAA CRW). Of the 12 core layers only four are NC-encumbered, each with a free alternative.

**Review trigger:** re-examine only if (a) `docs/LICENCES.md` shows zero NC dependencies in the rendering path, AND (b) measured traffic exceeds 50,000 sessions/month. Below that, ad revenue is $20–80/month against a licence risk that switches a quarter of the product off. Grants are the funding path with real expected value (NLnet €5k–50k, Sovereign Tech Fund €50k minimum), and both hard-require an OSI licence — which is why open-sourcing properly is a v1 task and grant applications are a v2 one.

---

## 4. Source strategy

### The tier table — all 92 plugins

**Tiers:** `LIVE` = enabled in v1. `RETIRE` = `enabled=False` + `retired_reason`, plugin file kept, un-retire stage named. `TOMB` = disabled and rendered on `/status` as a visible refusal. `DROP` = delete the plugin and hard-404 the cache route.

**Flags:** NC non-commercial · SA share-alike · LEGAL active ship risk · PRIV privacy-adjacent.

**Retirement is a one-line flag flip.** `scheduler.py:147` already skips worker creation for disabled layers, so retiring stops the fetch, the bytes and the semaphore slot at zero cost and is trivially reversible. It is not deletion: the file, the parser and the licence string stay, and the fix listed in the Action column is applied *at un-retire time*, in the stage that needs it — never before launch.

#### nature

| id | v1 | action | flags |
|---|---|---|---|
| quakes | **LIVE** | Demote the weekly 36-request 1990+ backfill to a one-shot seed + current-year tail | |
| fires | **LIVE** | `refresh_s` 600→3600 (FIRMS global NRT is ~3 h latent, so 10-min polling cannot surface newer data); drop MODIS_NRT; emit render slice; emit `fires_daily.` per-country aggregate for the brief median | |
| gdacs_events | **LIVE** | Swap the dead JSON API for `https://www.gdacs.org/xml/rss_7d.xml` via stdlib `xml.etree` (~40 lines). Every field the parser reads is present; the feed declares `<copyright>public domain</copyright>` | |
| volcanoes | **LIVE** | `refresh_s` 86400→604800 (static catalogue); delete the fallback that fetches then `return None`; fold `usgs_volcano_hans` alert level in | |
| usgs_volcano_hans | **LIVE** (merged) | Vendor a vnum→lat/lon table (1,196 rows, ~30 KB) — it silently zeroes if `volcanoes.json` fails | |
| nhc_cyclones | **LIVE** (candidate) | Read `movementDir`/`movementSpeed` not `movement` (always `""`); add JTWC RSS for W.Pac/IO/S.Hem; drop the false cone claim | |
| disasters (eonet) | RETIRE → stage 9 | Delete `limit=5000` (ships 5,000 of 19,221); `refresh_s` 600→3600 | |
| historical_disasters | RETIRE → stage 9 | Cleanest licence/value ratio in the set (20,157 events, 2150 BC→now, PD). Core once the scrubber ships | |
| emdat_disasters | RETIRE → stage 9 | Pin the 301 targets; read named type columns — `next(k for k in row…)` picks "Droughts", so `types` holds 238 **country names** and deaths/affected are null | NC |
| rainviewer | RETIRE | `max_zoom` 6→10 (tiles verified 200 at z10 — it blanks exactly when you zoom into a storm); correct licence to "personal/educational only" | NC |
| wind_sample | DROP | Fold `windspeed_10m,winddirection_10m` into `temperature_field`'s batch at zero quota cost | NC |
| noaa_co2 | **LIVE** (brief-only) | Split three cadences (daily/monthly/never); vendor the 50 KB 2015 EPICA composite. 72→2 req/day. Stop plotting 49 stations with `value: null` | |
| dartmouth_floods | DROP | `FloodArchive.txt` HTTP 404 — file removed, not an outage. GDACS RSS fills the flood gap | |

#### weather

| id | v1 | action | flags |
|---|---|---|---|
| temperature_field | RETIRE | On un-retire: `refresh_s` 1800→3600, absorb wind + `dew_point_2m` | NC |
| humidity_field | DROP | 99% redundant — same 135 coords, `relative_humidity_2m` already in `temperature_field` | |
| pressure_field | DROP | 100% redundant — byte-identical coords, `surface_pressure` **and** `cloud_cover` already in `temperature_field` | |
| open_meteo_forecast | RETIRE | Correctly throttled. Fix docstring drift ("10°×10° lattice, ~600 points" vs 60 cities) | NC |
| air_quality | RETIRE | Batch 45 cities into one multi-coordinate call (idiom exists at `open_meteo_temp.py:43`); replace the bare `except: pass` that drops 8 cities | NC |
| noaa_sst | RETIRE → replace | → NOAA Coral Reef Watch 5 km (genuinely NOAA, PD, raster). The id is a provenance lie — it is ECMWF via Open-Meteo | NC |
| berkeley_earth | RETIRE → replace | → NASA GISTEMP v4 / NOAA NCEI GlobalTemp (PD). Annual summary ends 2024 and reports `ok=true` | NC |
| nasa_power | RETIRE | `end = now-4d, start = now-6d`; drop `ALLSKY_SFC_SW_DWN` from hourly (0 of 367,200 records). 25 MB→~5 MB cache | |
| paleo_temperature | RETIRE → stage 9 | 40 of 214 points are hand-typed literals incl. one the source calls "Approximation". Add per-point `provenance`; pull real Marcott/PAGES2k from NOAA NCEI | |

#### war

| id | v1 | action | flags |
|---|---|---|---|
| ucdp | **LIVE** (candidate) | → `gedevents/26.01.26.06` candidate (verified, 10,051 events), drop the 180-day `StartDate` that returns `TotalCount=0` against an annual release, probe the version string. Keep `low/best/high`, `where_prec`, `date_prec`, `event_clarity`, `n_sources` — all currently discarded | |
| ucdp_ged | RETIRE → stage 9 | ged251→**ged261** (verified live, +32,050 events of 2025). Rendered window is 3,000 events from Nov–Dec 2024 wearing a present-tense name | |
| conflict_events (gdelt) | RETIRE → stage 10 | Rename `severity`→`media_attention` (it is computed from mention count); distinct mark shape from all fatality layers; absorb `relations` into one hourly 24 h download | |
| relations | DROP | Fetches the **same** `*.export.CSV.zip` files as `conflict_events`. −2,300 req/day, −105 MB/day | |
| idmc_displacement | RETIRE → stage 10 | → HDX per-country `<iso3>-idmc-idu-events` CSVs: real lat/lon, `qualifier` and `locations_accuracy` precision flags. Licence CC BY-NC-SA 3.0 IGO → **CC BY-IGO** | |
| wikidata_battles | RETIRE | `P585 UNION P580` (29→45 events). Reframe as "notable named battles with articles" | |
| acled | **TOMB** | EULA 8 Jul 2025 forbids making licensed content "available through Licensee's own dashboard." No hobbyist tier. All 246 HDX mirror datasets are `license_id=hdx-other`. Render on `/status` as a visible refusal with the clause quoted | LEGAL |
| conflicts | DROP | 150 points, all lat=0/lon=0, unmappable; duplicate of `news`; DOC API measured 429 on 2 of 3 requests | |
| crises | DROP → replace | Renders CKAN catalogue **metadata** as 351 crises ("Grenada — CERF Allocations") dated by `metadata_modified`, at 274 MB/day. Replacement is INFORM Severity Index (stage 10) | |
| reliefweb | DROP → replace | v1 is HTTP 410 permanently; current layer draws 964 country-centroid dots from catalogue rows at 756 MB/day. Replacement is ReliefWeb v2 (stage 10) | |

#### economy

| id | v1 | action | flags |
|---|---|---|---|
| fred | **LIVE** (brief-only) | Best-run source here. 5 of 50 series fail silently (health=45) — log them. Absorbs `commodity_prices`, `eia_petroleum` and the OECD CLI series | |
| imf_data | RETIRE → stage 9 | **Not dead.** `www.imf.org` 403s behind Akamai; `api.imf.org` is behind Azure App Gateway and returned 200 / 633,935 bytes / 210 countries from this exact IP. Rewrite with stdlib ElementTree, refresh 6-monthly | |
| world_bank | RETIRE → stage 9 | timeout 90→180 s, concurrency 3→2; delete `IC.BUS.EASE.XQ` (Doing Business discontinued 2021); split `world_bank_latest.json` (0.18 MB gz) + lazy per-indicator (~55 KB gz) | |
| hyde_population | RETIRE → stage 9 | Clean. Becomes a choropleth mode | |
| maddison_history | RETIRE → stage 9 | Repoint to the OWID grapher CSV — it reads `owid/owid-datasets`, **archived 2025-04-14**, pinned to MPD 2020 while MPD 2023 exists. Will never error, will never update | |
| oecd_cli | DROP → fred | Live layer serves USA 1976-11..1990-09 **non-monotonic** as a recession signal with `ok=true`. Take CLI from FRED, which already works | |
| fao_food_prices | RETIRE | Scrape the current filename off the index page (the month-stamped URL 404s and falls through to a frozen 2018 file at HTTP 200). Add `max_staleness_s` | NC |
| economy | RETIRE | Split: crypto 300 s, forex 21600 s. Frankfurter is ECB reference published once per working day — ~287 of 288 forex calls/day are waste | NC |
| commodity_prices | DROP | Brent/WTI/natgas/gold all duplicate FRED; CoinGecko+Frankfurter calls duplicate `economy`. Gold cached at "2026-06" from a monthly CSV polled hourly | SA |
| eia_petroleum | DROP | FRED already carries WCESTUS1 etc. | |

#### resources

| id | v1 | action | flags |
|---|---|---|---|
| cables | **LIVE** (candidate) | Quantize coords to 4 dp (halves 250 KB gz); validate FeatureCollection >100 features before writing (undocumented internal endpoint, no fallback); **carry the CC BY-NC-SA attribution on the cache endpoint** — it is currently re-served byte-identically with attribution stripped and `ACAO: *` | NC SA LEGAL |
| portwatch_chokepoints | **LIVE** (candidate) | 7 of 28 names do not exist upstream; 7 real ones silently dropped incl. **Kerch, Bering, Bohai, Magellan**. `page_size` 2000→1000 (pagination is dead: 752 of 77,389 rows). Best info-per-byte layer here at 12 KB gz | |
| country_polygons | **LIVE** (base) | Quantize to 3 dp (848→576 KB gz, ~110 m — invisible at 40 km/px); serve NE **110m** at world zoom; stamp `disputed`/`claimants`; add `ne_50m_admin_0_breakaway_disputed_areas` | |
| portwatch_ports | RETIRE | Four one-liners: `outSR=4326` (all 800 ports carry Web Mercator **metres** in lat/lon), `portcalls_*` field names (all traffic = 0), `page_size` 1000, drop `orderByFields=date DESC` (47.4 s → 0.72 s) | |
| climatetrace_assets | RETIRE | Un-hardcode `year=2024`; **strip the Thumbnail field — it republishes Earthrise Media's Mapbox token**, 850 KB / 20% of payload; stratified per-sector quota | |
| wri_power_plants | RETIRE | Label the **2020 vintage** (upstream frozen since 2021); ETag/quarterly not weekly 12 MB; stratify top-5000 by fuel — currently 1,710 gas + 1,708 coal but 65 solar | |
| entsoe_grid | RETIRE | Bidding-zone EICs for DE/IT/NO/SE/DK/IE (6 of 19 prices are 0); take the **latest** price not the first; exclude consumption series. Licence is ToU, not CC | NC? |
| eia_930_grid | RETIRE | Bake 51 BA coords from Esri Living Atlas (anonymous, WGS84) and delete the frontend table; 59 of 74 respondents sit at 0,0. `length=100000` silently caps at 5,000 | |
| owid_energy | RETIRE → stage 9 | Split latest-year from history before any client uses it (538 KB gz vs a 374 KB gz shell) | |
| country_deep_dive | RETIRE → stage 9 | Import the full WRI Aqueduct 4.0 country table (63 hardcoded → ~180); emit an explicit `coverage` object | |
| country_resources | RETIRE | Verify the Comtrade half's terms — "UN Open Data + CC BY 4.0" is the least-verified licence claim in the set | |
| trade_annual | RETIRE | Use the COMTRADE_KEY that is present and unused; `maxRecords` 50→500 (10× data, same request count); refresh weekly→annual | |
| trade_monthly | DROP | 864 req/**day** for 174 flows at a 4–7 month lag | |
| eia_international | DROP | ~70% duplicative with `owid_energy`; `crude_oil_consumption` silently dead | |
| cepii_baci | **TOMB** | Never succeeded once (cache `count:0`, `/data/cache/_baci/` empty) and caused the six-day outage. The zip is 287 MB, not 2–3 GB; the bomb is `year_flows` at 555 B/row × ~10.6M rows ≈ **5.9 GB for one year**, so the proposed streaming fix would not have prevented it. Replacement is IMF IMTS on `api.imf.org` | |

#### space

| id | v1 | action | flags |
|---|---|---|---|
| swpc_aurora | **LIVE** | `mark_error` when the aurora product fails (Kp/solar-wind keep the envelope non-empty, so it reports `ok=true` with no oval). PD, keyless, 44 KB gz, 5-min cadence, sequential field — consumes no categorical hue and fills the polar gap every other layer leaves empty | |
| satellites (celestrak) | RETIRE | Order matters: (1) `mark_error`, (2) stop downloading the full starlink group to discard 97% via `sats[::step]` (~60 MB/day → <2 MB/day), (3) **then** email CelesTrak to delist 129.151.191.74. TCP to :443 and :80 both drop — we earned the firewall | NC |
| iss | RETIRE | Crew → `ll.thespacedevs.com/2.2.0/expedition/`. The globe reads "ISS · 9 crew" listing **Expedition 71 from mid-2024**. Position 10 s→60 s (8,640 req/day for one dot to a hobby endpoint) | |
| nasa_donki | RETIRE | → `kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/{FLR,CMEAnalysis,GST,SEP,RBE,IPS,HSS}` — all 7 verified 200, identical schema, **keyless**. Not a map layer: every event is written at 0,0 | |
| nasa_epic_earth | RETIRE | The model plugin — already migrated off the dead proxy and calls `mark_error` before every `return None`. Copy this idiom into `celestrak.py` | |
| nasa_neows | RETIRE | → JPL SBDB CAD API, one query replacing a 200-page `/neo/browse` walk that re-downloads the same 4,000 of ~38,000 NEOs daily | |
| spacetrack_gp | **DROP + delete cache file today** | Account suspended, plugin never ran once, 15,029,198 bytes still publicly downloadable | LEGAL |
| nasa_mars_photos | DROP | Off-charter; v2 has no planet selector so it is already unreachable | |

#### transit

| id | v1 | action | flags |
|---|---|---|---|
| flights | **LIVE** | Primary → `api.airplanes.live/v2/point/{lat}/{lon}/{nm}` (measured London 762 vs adsb.lol 54; **New York 1089 vs 0**), adsb.fi secondary, OpenSky OAuth2 fallback. Accept HTTP **201** on routeset (`!= 200` discards every route — `routes:{}` in the live cache). Per-region failure counter in the envelope. Aggregate only: no tail-number search, no owner lookup, no searchable per-aircraft history | NC PRIV |
| ships | RETIRE | Replace the world bbox with 8–12 boxes over the chokepoints we already have coords for (4.74 GB/day → ~0.2), and **prune inside the WS ingest loop** — `_prune_stale` currently runs only behind the 8-way semaphore that `gfw_events` holds for 31 minutes | NC? |
| gfw_events | RETIRE → stage 10 | Read `ev['gap']['durationHours']` (nested — every event ships 0); keep `gap.intentionalDisabling`; filter to intentional disabling and 3 h→24 h. `count:30000` is 3×10-page truncation against a real total of 79,899 — label it. Intentional disabling must be attributed to GFW, never asserted in our voice | NC SA LEGAL |

#### social

| id | v1 | action | flags |
|---|---|---|---|
| gdelt_gkg_themes | RETIRE | `csv.field_size_limit(10_000_000)` — the 131,072 default is crashing ~8% of fetches, confirmed in the live log; 15→30 min | |
| news | RETIRE | kind `points`→`raw` (0 of 250 have coords); 300→900 s | |
| trends | RETIRE | 3600→21600 s: it polls an **immutable previous-day file** 24×/day. Label it "English Wikipedia" | |
| radio | DROP | Ordered by clickcount — a popularity chart, not a census | |
| youtube | DROP | Fabricated coordinates + ToS caps Non-Authorized Data storage at 30 days while retention is off | LEGAL |

#### health

| id | v1 | action | flags |
|---|---|---|---|
| who_don | **LIVE** (candidate) | `?$orderby=PublicationDateAndTime desc&$top=50&$format=json` — verified returning 2026-08-01 Ebola/DRC, reported as the largest Ebola outbreak ever in the DRC. Today it serves 1997–2025 with newest 2025-02-01 as current outbreak news | NC SA |
| openaq_stations | RETIRE | The description is false: it fetches `/v3/locations` — station metadata, zero readings. Rename to the monitoring **network** and refresh 3600→604800 s | |
| air_quality | (see weather) | | NC |

#### infra

| id | v1 | action | flags |
|---|---|---|---|
| cloudflare_radar | **LIVE** | Outages only — split DDoS off (share-of-total % has no location semantics). Use existing country centroids instead of the 82-entry dict that drops Saint Lucia, Guam and **every multi-country event** (40% loss, biased to the big ones). Licence → **CC BY-NC 4.0**; 1800→21600 s | NC |
| cables | (see resources) | | NC SA LEGAL |
| webcams | **DROP + unpublish today** | | LEGAL |

#### meta

| id | v1 | action | flags |
|---|---|---|---|
| country_polygons | (see resources) | | |
| country_intel | RETIRE → stage 9 | **Promote it later.** It ships `_sanity_warnings` naming its own rejections (Sudan debt 865.87% caught and nulled) — the charter working exactly as designed | |
| brecke_wars | RETIRE → stage 9 | The honesty exemplar — `fatalities_low/high` + confidence tag + explicit uncertainty note. Correct "~80"→63; add as-of dates to the 4 hardcoded ongoing wars; relabel source as curated, not COW | |
| vdem_democracy | RETIRE → stage 9 | Read the version from the data — LayerMeta asserts "V-Dem v14" while OWID serves whatever is current | |
| clio_life_expectancy | RETIRE → stage 9 | Clean | |
| historical_borders | RETIRE → stage 9 | Split into 53 per-snapshot files (~1.13 MB raw median vs a 25.65 MB gz monolith fetched to paint **one** year). ~70× cut, no new tooling | SA |
| geoboundaries_adm1 | RETIRE → stage 9 | Split per country + mapshaper Visvalingam ~5%. Canada alone is 26 MB raw for 13 provinces | |
| country_culture | RETIRE | 127 of ~195 countries. Render the missing third as explicitly unknown. Fix the fake `worldtwin.local` UA | |
| country_relations | RETIRE | Distinguish inferred (GDELT ratio) from asserted (bloc) edges | |
| cow_alliances | RETIRE | Relabel source: it is a hardcoded dict, not COW. Hardcoded end-year 2026 needs a calendar reminder | |
| population | DROP → replace | v3.1 dead 70 days serving 245 countries with no staleness surfaced. Replace with vendored `mledoze/countries` (ODbL) + population from `world_bank` `SP.POP.TOTL`, which is dated and citable. Zero calls, zero key, cannot go silently stale | SA |
| global_events | RETIRE | Drop the synthetic GKG coordinates. The PortWatch half is good — keep it on un-retire | |
| pulse_mode | **TOMB** | Delete the WorldTwin-authored composite. If revived, adopt INFORM Risk Index by name and version, and expose the five dimensions separately with explicit `n/5` | |
| gemini_narrative | **DROP** | Retired entirely. See §3 | |

#### gaming / sports

| id | v1 | action | flags |
|---|---|---|---|
| gaming | DROP | Fabricated geography | |
| sports | DROP | No licence; ESPN's upstream rights contracts are the real exposure | LEGAL |

**Totals: 16 LIVE · 3 TOMB · 41 RETIRE · 32 DROP.** Registry count stays 92 on `/status` (retired and dropped both render, with reasons and dates); the scheduler starts ~16 workers, not ~89.

### The six dead and two silently stale — resolved

| Layer | Was | Fix | Verified |
|---|---|---|---|
| gdacs_events | HTTP 500 on the JSON API | `rss_7d.xml` + `xml.etree`, ~40 lines | Feed returns 200 in 1.8–6.7 s with every field the parser reads |
| imf_data | HTTP 403 (Akamai blocks Oracle IPs) | `api.imf.org` SDMX 2.1 — a different edge, Azure App Gateway | 200 / 633,935 B / 210 countries / 10,023 obs from this box, no key |
| ucdp | Layer bug, not upstream | Drop the 180-day `StartDate`; use the GED Candidate dataset | `gedevents/26.01.26.06` = 10,051 events, 11 pages |
| population | restcountries v3.1 deprecated | Vendor `mledoze/countries` + `world_bank SP.POP.TOTL` | Zero network calls afterwards |
| acled | EULA denial | Tombstone with the clause quoted. Protests/riots remain a **declared, visible gap** | EULA §3.1, 8 Jul 2025 |
| spacetrack_gp | Account suspended | Drop. Delete the 15 MB public file | User Agreement + PL 108-136 |
| satellites (stale since Apr 27) | IP firewalled by CelesTrak | `mark_error` → stop the 97% waste → then request delisting, in that order | TCP :443 and :80 both drop silently from this box |
| trade (stale since Apr 11) | Orphan cache file, no registry entry | 404-gate; the layer is dropped | Caught only by file-vs-manifest reconciliation |

### Corrected polling cadences

| Layer | Now | Real upstream rate | → | Saved |
|---|---|---|---|---|
| fires | 600 s | ~3 h NRT latency | 3600 s | 1.7 GB/day in, 240 MB/day history |
| ships | world bbox WS | — | 8–12 chokepoint bboxes | 4.5 GB/day |
| reliefweb | 3600 s | catalogue churn | dropped | 756 MB/day |
| crises | 1800 s | catalogue churn | dropped | 274 MB/day |
| gdelt_gkg_themes | 900 s | 15 min | 1800 s | 142 MB/day |
| relations | 3600 s | same files as conflict_events | dropped | 105 MB/day, 2,300 req/day |
| openaq_stations | 3600 s | weeks | 604800 s | 124 MB/day, 617 req/day |
| pressure + humidity_field | 1800 s | duplicate | deleted | 12,960 weighted calls/day |
| trade_monthly | 86400 s | monthly, 4–7 mo lag | dropped | 864 req/day |
| iss | 10 s (crew too) | crew ~5×/year | 60 s / 3600 s | 7,200 req/day |
| nasa_neows | 200-page walk | catalogue weekly | JPL CAD, 1 req | 200 req/day |
| noaa_co2 | 3600 s × 3 files | daily / monthly / never | split + vendor | 70 req/day |
| cloudflare_radar | 1800 s | ~2×/week, curated | 21600 s | 1,300 req/month |
| imf_data | 604800 s | 2×/year | 2592000 s | 26× |

Combined with retirement of the long tail: **≈7 GB/day of inbound and ≈26,000 upstream calls/day removed with no information loss.**

### Licence position

**Blocks monetisation (NC):** cables · cloudflare_radar · gfw_events · rainviewer · who_don · the entire Open-Meteo family · airplanes.live · CoinGecko keyless · celestrak · entsoe_grid (ToU, unverified).
**Copyleft (SA):** cables · historical_borders · gfw_events · vendored mledoze (ODbL) · adsb.lol (ODbL).
**Twelve wrong strings to correct:** GDELT is declared four different ways across five layers — `CC0` on conflicts/news is the dangerous one, because it tells downstream users they may strip the citation GDELT requires. Also portwatch_* "CC BY 4.0"→IMF ToU · cloudflare_radar "Free with attribution"→CC BY-NC 4.0 · idmc "CC BY-NC-SA 3.0 IGO"→CC BY-IGO · rainviewer "Free"→personal/educational · noaa_sst is not NOAA · paleo_temperature mixes three licences under one wrong label.
**Clean for commercial use:** all NASA/NOAA/USGS/EIA (PD) · UCDP, World Bank, OWID, Climate TRACE, WRI GPPD, geoBoundaries gbOpen, INFORM, IDMC (CC BY) · Natural Earth (CC0) · GDELT (bespoke, citation required).

**ShareAlike propagates into our derived artifacts.** The render slice for `cables` is a *derivative*, not a redistribution, so the served slice must carry the CC BY-NC-SA notice and the attribution text — as must any future embed or feed catalogue built on an SA source. The programmatic licence gate must key on the *corrected* `license` field, and must refuse to promote any source whose licence string has not been verified in `docs/LICENCES.md`.

**Borders:** disclose the method, hatch the disputes, build no point-of-view switcher. Natural Earth is explicitly *de facto* and splits Taiwan, Somaliland, W. Sahara, Kosovo and N. Cyprus as separate features; geoBoundaries gbOpen gives territory disputed between two states to **both** as deliberately overlapping polygons. We render both and reconcile neither. Stamp `disputed:true`/`claimants`/`dispute_note` on the ~8–10 contested features, add `ne_50m_admin_0_breakaway_disputed_areas`, and put one sentence in the UI: *"Borders shown de facto per Natural Earth; contested areas hatched."* NE's 31 POV variants exist only at 1:10m — adopting them means moving the whole base layer to a much larger file, maintaining 31 of them, and owning a political configuration surface. The hatch gets ~90% of the honesty for ~2% of the work.

### Recommended additions — frozen until v1 ships

New sources are added **only in a week where the stale list is empty.** In priority order: (1) **ReliefWeb API v2** (free approved appname via one Google Form, ~15 min — highest value per minute in the whole plan); (2) **INFORM Severity Index** via HDX (cc-by, monthly); (3) **IDMC IDU events** (cc-by-igo, geocoded, with built-in precision flags); (4) **NOAA Coral Reef Watch 5 km SST** (PD, removes an NC tie); (5) **NASA GISTEMP v4** (PD, removes another); (6) **JTWC RSS** (PD, 4.9 KB — W.Pacific/Indian/S.Hemisphere cyclones, where most storms and most affected people are); (7) **IODA** (second internet-outage source, better licence); (8) **api.imf.org** beyond WEO (IMTS, PCPS, CPI); (9) **Elexon BMRS** (restores GB, lost from entsoe_grid post-Brexit); (10) **GVP Weekly Volcanic Activity RSS**.

---

## 5. Backend and data architecture

### Target shape

One process, a static contract, three lifecycle tiers. No new always-on service, no new Python dependency, no bind-mount change, no container recreation.

### The delivery contract

`/data/cache/v1/manifest.json`, written **atomically inside `cache.write_envelope`'s commit path** — never a directory scan, because a scan is structurally one cycle stale. Served today at `/api/cache/v1/manifest.json` via the existing Caddy handler, which already has `precompressed gzip`, CORS and disk-serving. Measured shape: ~92 entries, ~45 KB raw / ~10 KB gz.

```json
{ "manifest_version": 1,
  "generated_at": "2026-08-01T17:50:06Z",
  "generator": "worldtwin-aggregator/<git-sha>",
  "envelope_version": 1,
  "counts": { "total": 92, "live": 16, "stale": 2, "dead": 3, "retired": 41, "dropped": 30 },
  "layers": [ {
    "id": "fires", "name": "...", "category": "nature", "kind": "points",
    "data_path": "$",
    "state": "ok",
    "state_detail": null,
    "fetched_at": "...", "expires_at": "...", "refresh_s": 3600,
    "max_staleness_s": 21600,
    "data_period": ["2026-07-31T00:00Z", "2026-08-01T18:00Z"],
    "last_success_at": "...", "stale_since": null,
    "count": 156101,
    "source": { "name": "NASA FIRMS (VIIRS SNPP)", "url": "https://firms.modaps.eosdis.nasa.gov/api/area/" },
    "license": { "id": "PD-NASA", "name": "NASA open data", "url": "...",
                 "commercial_use": true, "attribution_required": true,
                 "share_alike": false, "attribution": "NASA FIRMS/LANCE" },
    "representations": [
      { "rel": "full",   "url": "fires.json",        "bytes": 28407933, "bytes_gz": 2608184, "count": 156101, "lossy": false },
      { "rel": "render", "url": "fires.render.json", "bytes": 230305,   "bytes_gz": 68135,
        "mode": "bins", "cell_deg": 0.25, "shown": 10749, "lossy": true,
        "selection": "0.25 degree density bins, area-weighted; 10,749 cells of 156,101 detections" } ] } ] }
```

Rules that make this a contract rather than a catalogue:

- **All URLs are relative to the manifest**, so a GitHub Pages mirror or any future CDN works unmodified.
- **`state` is computed, never asserted:** `now > expires_at + grace` for fetch age, **and** `now - max(data_period) > max_staleness_s` for data age. Both are needed and they are orthogonal — verified 2026-08-01, `fao_food_prices` and `oecd_cli` were fetched at 12:59Z with `expires_at` 162 h in the future, so a fetch-age-only rule scores both `ok` while they serve March 2018 and scrambled 1976–1990 data. `max_staleness_s` ships as **one defaulted field in `models.py`**, populated opportunistically for the ~10 layers with a known data-age hazard. It is not 92 plugin edits.
- **`retired` is a first-class state** carried with a plain-English reason, excluded from the error budget, and shipped in the same commit that makes failures visible — otherwise the healthy count drops from 81 to ~75 and reads as a regression.
- **The manifest is the only document that must be fresh.** `generated_at` older than 3× `min(refresh_s)` ⇒ the client renders "aggregator down" rather than trusting the contents. That is the one place a reader may use an age heuristic, because there is nothing behind it to ask.
- **Not in v1:** sha256 per representation (a full re-read per write for a property no client checks), bbox, props sub-schemas, deprecated_props maps, content-addressed immutable URLs.

### The counts ledger

`/data/cache/v1/counts.json` — a per-layer daily count ledger written from the envelope's own `count` at commit time. In-memory dict seeded from the file at boot; last successful value of the day wins so a day freezes once it closes; a layer that failed gets **no entry, never a zero**. Last 90 days, ~25 KB gz; a nightly cron appends closed days to `counts/YYYY.json`.

This exists because both the sparkline and the brief's 7-day median were specified against data that does not exist. Verified: `observations` decomposes per *entity* (`fires.-0.079_-77.654_2026-06-25_204`), `history.py:194-197` refuses to decompose fires at all (`rows_added=0` on every recent snapshot), the fires snapshot blob is a bare list with no `count` key, and the real endpoint is `GET /api/history/series/{source_id}` with no `metric` or `days` parameter. **Nothing in the client or the brief may ever call `/api/history/*`.**

### Making failure impossible to hide

The fix is in the scheduler, not the plugins. `scheduler.py:33-36` returns before any status mark when `fetch()` returns `None`; 72 of 92 plugins use that path. One ~40-line change to one file converts all 72 from invisible to red with **zero plugin edits**:

- `result is None` → `cache.mark_error(id, "fetch returned None — kept previous cache", elapsed)`.
- Split `_FETCH_SEM(8)` into `NET_SEM(16)` around `await reg.fetch(client)` only and `CPU_SEM(2)` around the serialise/compress/write tail. Move `t0` inside the acquire — `quakes` currently reports 163 s elapsed for a 10 KB payload because it measures queue time.
- Run `sanity.sweep_and_tag` **once** and hand the swept payload to both writers. Verified: `_sanity_warnings` appears in 1 legacy file and **0 of 92 v1 files** — the new client is the one consuming un-sanitised values.
- Persist `cache._status` to `/cache/v1/_status.json` on every mark, seed at boot, with a durable `last_success_at`.

### Nightly audit invariants

Replace the hand-maintained 18-name allowlist with five assertions over the manifest:

- **A.** `manifest.counts.total == len(registry.all_layers())` — note **`all_layers()`, not `all_metas()`**; `registry.py:47-51` filters `all_metas()` to enabled layers, so comparing against it hard-fails every night the moment anything is retired.
- **B.** Every layer with state in (stale, dead) is named in the email with `stale_since` and `last_success_at`.
- **C.** Every representation over `LayerMeta.max_bytes` (default 2 MB) is flagged. `fires` grew 85,224 → 156,101 points across four measurements in this audit alone and nothing noticed.
- **D.** Every file in `/data/cache/v1/*.json` has a manifest entry — this is what catches the four orphans (spacetrack_gp, trade, country_exports, cepii_baci) that no health check can see because they are not layers. **Scoped to `v1/*.json`, explicitly excluding `/data/cache/brief/`.**
- **E.** `counts.json` has yesterday's entry for every layer whose manifest state is `ok`.
- **F.** `/data` free space > 30 GB, **root free space > 4 GB**, and the newest file in `/data/cache/brief` is under 72 h old.

### Write amplification

Measured: aggregator cgroup `wbytes` = 107 GB/day, `rbytes` = 45.5 GB/day at 93.6 read IOPS vs 24.6 write IOPS. Of the writes, history.sqlite is ~95 GB/day and all cache JSON is ~12 GB/day.

- **Delete the `.data.json` write.** 92 files, 361 MB of near-byte-identical duplicates (`geoboundaries_adm1.json` 95,233,659 B vs `.data.json` 95,233,270 B) that no checked-in frontend reads.
- **`os.fsync` + `posix_fadvise(DONTNEED)`** in `_atomic_write` for files over 1 MB, after rename, on both the `.json` and the `.gz`. ~10 layers, ~1,500 fsyncs/day rather than 16,821.
- **`HISTORY_POLICY`** dict: `none` for rainviewer (archives tile pointers that 404 within hours) and iss (46% of snapshot rows, a deterministic function of a TLE); `daily` for fires (2.4 MB/day compressed, 0.88 GB/year — it is default-on and a time-machine layer, so `none` would leave it with no archive at all); `full` for flights, ships, country_intel, cloudflare_radar; `latest` for everything else.
- **Make the WAL actually checkpoint.** It is 3.8 GB against a 20 MB `wal_autocheckpoint` threshold, i.e. it is not checkpointing at all, because long-lived readers hold it back. Add an explicit periodic `wal_checkpoint(PASSIVE)` and audit for long readers. Do **not** raise `wal_autocheckpoint` above 5000 or `mmap_size` above 256 MB.

**Acceptance is split three ways, because total cgroup `wbytes` cannot move more than ~10% from cache work:** (a) bytes attributable to `/data/cache` fall from ~12 GB/day to under 3 GB/day, computed per layer as `file_size × writes_per_day`; (b) `memory.stat file` falls below 700 MB within an hour with `rbytes/day` unchanged — if not, revert **the fadvise only**, never the `.data.json` deletion or the fires cadence; (c) WAL bytes written per hour, measured over a 6 h window, falls at least 50% against the 453 KB/s baseline.

### The fate of the 52 GB history store

**Copy-forward rebuild to ~2.0 GB. Never `DELETE` + `VACUUM`.** VACUUM needs the live size free alongside the original: 56 GB required, 44 GB available. It cannot run, which is why retention is gated off. Copy-forward peaks at ~58 GB of 100 and is genuinely reversible.

**Snapshots are the archive, not overhead.** Measured: 68,097 snapshots / 87 layers; every snapshot = 2.84 GB compressed; one-per-UTC-day = 0.44 GB. The 49 GB win is the `observations` EAV table and its four indexes — 112.8M rows existing to serve three static sparklines whose combined row count is ~0.05% of the table. Keeping the daily archive moves the target from 1.5 GB to ~2.0 GB; dropping to "newest per layer" would save 0.44 GB of a 54 GB reduction **and delete the differentiator** — 1,911 quakes snapshots, 718 fires, 228 gdacs_events.

Snapshot retention follows the graduated rule `history.compact()` already implements at `history.py:1421-1467`: all snapshots <7 d; newest per 6 h for 7–30 d; newest per UTC day for 30 d–1 y; newest per week for 1–5 y; newest per month beyond. **That rule is the retention window published in the charter.**

Observations keep only the 11 curated prefixes, with `value_json` dropped (~20 GB, and redundant against the snapshot blob), `idx_obs_observed` and `idx_obs_fetched` dropped (~8 GB, read by nothing), `WITHOUT ROWID` (~9.5 GB of redundant autoindex), and `fetched_at` as INTEGER epoch. `idx_snap_layer_time` is retained — the at-or-before seek and the coverage rollup both depend on it.

**Query form is mandatory and load-bearing.** `WHERE source_id >= :p AND source_id < :p_hi` gives `SEARCH TABLE observations USING COVERING INDEX`. `WHERE source_id LIKE 'prefix%'` degrades to `SCAN TABLE observations` — a full 112.8M-row pass, eleven times over. Assert the query plan in a self-test before the copy runs.

**Rejected: DuckDB / Parquet / pyarrow.** ≥125 MB RAM per thread inside a 3 GiB cap shared with ~90 fetch tasks, recent releases shipped without manylinux aarch64 wheels, and both real query patterns are point/range seeks on a small key — a B-tree's home turf and a columnar engine's worst case. `requirements.txt` stays at four lines and v1 adds **zero** new Python dependencies.

### Plugin isolation

- `aggregator/worldtwin/fetchhelpers.py:stream_to_file(client, url, dest, max_bytes)` using `client.stream` + `shutil.copyfileobj`; peak ~64 KB.
- The shared `httpx.AsyncClient` gets a default body ceiling so an unbounded `r.content` read **raises** rather than allocating. This, not the cepii_baci rewrite, is the structural fix.
- `LayerMeta.heavy: bool` routes ~5 bulk layers to a host-cron one-shot: `docker run --rm --name wt-oneshot-<id> --memory=768m --cpus=1 …`. A kernel-enforced cgroup **outside** the aggregator's limit, so one plugin structurally cannot kill the service. **Never grant the aggregator the Docker socket** — root-equivalent on a box with four paying tenants.

### Endpoint changes

`/v1/layers`, `/v1/categories`, `/v1/schema`, `/v1/health`, `/api/health` become thin readers of `manifest.json`. `/v1/layers/{id}`, `/v1/layers/{id}/data` and `/api/{layer}` are deleted — pure duplication of files Caddy already serves. `/api/history/sources` returns 400 without `prefix` (today it does `GROUP BY source_id` over a 49 GB table, unauthenticated, publicly routed). `/api/history/coverage` becomes a static nightly file (measured: did not return within 30 s from localhost). `/api/history/snapshot/{layer}` caps decompression at 8 MB with `zlib.decompressobj(max_length=…)` — a 2.3 MB fires blob expands to ~25 MB, and concurrent requests are a memory-amplification vector.

---

## 6. Frontend architecture and visualisation

### Stack — closed

MapLibre GL 5.24 globe + React 19 + TypeScript + Tailwind 4 + Vite 6. Bundle floor is 275 KB gz (MapLibre is 78% of the JS); everything added is measured against that floor.

**No deck.gl.** It adds 145–238 KB gz (+40–65% shell) for a problem that does not exist — the fires blocker was never fill rate, it was 2.64 MB of transfer and a ~0.5 s `JSON.parse`. Its `IconLayer` is also broken on MapLibre globe projection (visgl#9554, open since Mar 2025), and globe-plus-shape-marks is precisely our configuration. **Trigger rule, written into AGENTS.md:** adopt deck.gl only when a single layer must draw >50,000 marks the user can actually see, or when GPU aggregation, arcs or 3D extrusion is required. Migration is additive (`MapboxOverlay` on the same Map), so deferring costs nothing.

Also rejected: Cesium (1.72 MB gz = 4.7× the whole shell, repaints continuously), globe.gl (500 KB gz with three.js bundled), Kepler.gl (npm `latest` is an alpha *application*), Mapbox GL v3 (licence, not capability).

### Rendering strategy per data class

| Class | Strategy |
|---|---|
| Points, n ≤ 3,000 | Ship `{id}.json` with props intact. Covers ~30 of 43 point layers; median ~13 KB gz. |
| Points, 3,000 < n, gz ≤ 120 KB | `{id}.render.json` mode `points`: lean `[[lat,lon,v,t],…]` rows. |
| Points, over budget | `{id}.render.json` mode `bins`: **area-weighted** density grid, adaptive cell size 0.1° → 0.25° → 0.5° until gz ≤ 120 KB. |
| Polygons (country_polygons) | GeoJSON, quantized to 3 dp, NE 110m at world zoom. 848 → ~300 KB gz. PMTiles is *not* warranted at 242 features — Protomaps' own threshold is "more than a few megabytes." |
| Raster fields (aurora) | Sequential colour ramp, consumes no categorical hue. |
| Raw / non-spatial | Never on the globe. Document surfaces only. |

**One derived artifact per point layer, ever.** `render.py` is called from the single `write_envelope` call site (`scheduler.py:70`) and inherits the existing atomic tmp+rename and gzip sidecar. Backend's `SummarySpec`/`{id}.summary.json` and sources' columnar reshape of `fires.json` are both **struck** — the reshape breaks `api.ts extractPoints()`, the manifest's `data_path` contract and the legacy client, to reach 1.10 MB gz against the render slice's measured 68 KB. `RENDER_CAP` in `api.ts:11-15` is deleted entirely.

**The global view of a large layer is an AGGREGATE, not a top-K sample.** Top-4,000-by-FRP leaves marks in 1,335 of 22,779 occupied cells — 5.9% of burning area — and systematically erases small agricultural burns across India, the Sahel and SE Asia. A 0.25° grid covers 100% of occupied area at 68 KB gz. Stating a number does not undo hiding 94% of the phenomenon.

**But an unweighted lat/lon grid is itself a false claim.** A 0.25° cell is ~773 km² at the equator and ~193 km² at 70°N, so a boreal fire front reads 2–4× denser than an equivalent equatorial one — and fire season in the boreal north is exactly when this layer is most looked at. **Weight every bin by `cos(lat)`** and label the units honestly: *"Wildfire detection density (area-weighted) · 0.25° cells · 10,749 cells · 156,101 detections."* Cell size, cell count and true total are read from the payload, never hardcoded.

### The colour system, and how it scales to 15 layers

**Three categorical hues is a permanent, empirically-verified cap**, not a preference. Re-validated against the real surface `#0d1117` with `--pairs all` (the correct pairlist for a map, where any two marks can be adjacent): `#3987e5` / `#d95926` / `#199e70` **PASS** at worst CVD ΔE 9.4 (deutan) and worst normal-vision ΔE 20.9. Seven candidate fourth hues spanning amber, violet, purple, cyan, magenta and indigo were tested and **every one fails** the CVD floor and/or the hard normal-vision floor of 15. No re-ordering moves this, and secondary encoding explicitly cannot excuse a normal-vision failure.

Hue is assigned to **family**, never to layer. Three families: **EARTH** `#d95926` (heat) · **HUMAN** `#199e70` · **MOTION** `#3987e5`.

Each family gets a validated 5-step sequential ramp whose **middle step is the family hue**, so magnitude never introduces a hue:

```
MOTION  #184f95 #256abf #3987e5 #6da7ec #9ec5f4   (light-end contrast 2.34:1)
EARTH   #8f3517 #b4491f #d95926 #e8834f #f4b48a   (2.42:1)
HUMAN   #116a4a #158460 #199e70 #4dbd95 #8fd8bd   (2.87:1)
```

Six steps **fails** adjacent-ΔL at 0.049 against a 0.06 floor. Five is computed, not chosen. Magnitude rides on **radius first**, ramp second, because a ramp's light end fights bright imagery (Sahara, ice, cloud) no matter how it validates against a flat surface.

**The scaling answer is focus/context: the registry holds 15, the screen holds 4.**

- **1 FOCUSED layer:** shape mark ≥14 px, full family hue, glow, magnitude on radius reinforced by the family ramp, direct labels on the top 8 marks, legend with units and the `n`/`shown` line.
- **≤3 CONTEXT layers, at most one per family:** 5 px circle, family hue at 0.55 opacity, no shape, no glow, no label, still tappable.
- Enforced in the toggle reducer, not in guidance. Turning on a second layer in a family replaces the first, and the sheet says why.

This is *provable* rather than usually-fine: the all-pairs floor binds only among marks of equal visual weight, and the context stratum is exactly three dots in the three validated hues. The focused layer separates by size, luminance, shape and glow — channels not subject to ΔE. Twelve simultaneously-toggleable equal-weight layers is not an answer: shape discrimination needs a ≥12 px mark, and twelve shaped marks at 7 px on a 390 px phone is a blob.

**Focus dims the world:** focusing a magnitude layer drops basemap `raster-brightness-max` 0.82→0.5 and saturation −0.12→−0.35. One `setPaintProperty`; it fixes the ramp-vs-imagery conflict and reads as attention.

Shape carries identity within a family: circle / triangle / diamond / square, floor 12 px, ceiling ~2,000 points (236 B/pt as a symbol vs 28 B/pt as a circle, and globe projection loses MapLibre's symbol placement fast path entirely — `VerticalPerspectiveTransform.getFastPathSimpleProjectionMatrix` returns `undefined`).

**Texture has exactly one meaning:** 45° hatch at 8% white = NO DATA. Never grey — grey reads as low on a ramp.

**The status palette** (`#0ca30c`/`#fab219`/`#ec835a`/`#d03b3b`) is reserved for state, never a series, and **always accompanied by the literal word**. The four status colours *fail* as a categorical set on this surface (deutan `#d03b3b`↔`#0ca30c` ΔE 4.1), which is by design and means GDACS alert level must be encoded by ring count plus the word "Orange", never by colour alone — today the client paints every GDACS event one yellow regardless of level.

### Performance budgets

| Budget | Value | Enforced by |
|---|---|---|
| Cold shell + first layer | ≤500 KB gz | CI check on build output |
| Any `{id}.render.json.gz` | ≤120 KB | nightly_audit assertion C |
| Any single layer payload | ≤ the shell (374 KB gz) | manifest `max_bytes` |
| Main-thread block on layer toggle | ≤100 ms | Playwright throttled profile |
| Marks on screen | ≤4 layers | toggle reducer unit test |
| Idle GPU work | zero | grep rule: no `map.triggerRepaint()` inside a rAF loop |

Mobile GPU settings: `pixelRatio: coarse ? min(dpr,2) : dpr` (a DPR-3 phone renders 9× the fragments of DPR-1 on a style that is almost pure fill rate), `maxTileCacheSize: 60`, `fadeDuration: 0`, `raster-fade-duration: 0`, `powerPreference: 'low-power'` on coarse pointers. Source options on every `addSource`: `{ maxzoom: 6, buffer: 0, tolerance: 1 }` — MapLibre's defaults (maxzoom 18, buffer 128 px) make geojson-vt eagerly subdivide 155k points and duplicate every edge point for no benefit.

Delivery: `Cache-Control: public, max-age=31536000, immutable` on hashed assets and `no-cache` on `index.html` — this is a **live blank-page bug**, not just a slowdown, because `emptyOutDir: true` deletes previous hashed chunks on deploy and a heuristically-cached `index.html` then 404s its module script. Build emits `.zst` (level 19) and `.gz` (level 9) sidecars; `file_server { precompressed zstd gzip }`. Drop `cache: 'no-store'` from `api.ts` — Caddy already emits correct ETag and Last-Modified, so a returning visitor gets a ~200-byte 304 instead of megabytes.

---

## 7. Design and UX

### Information architecture: three surfaces, forever

Written into AGENTS.md as an invariant **with the numbers attached**, because "keep it simple" is not enforceable in code review and "which of the three surfaces does this attach to?" is.

- **S1 — The Sheet + The Plane.** The only control surface. Bottom on phone, 380 px left rail on desktop. Never hides.
- **S2 — The Detail.** Transient, one card, never two.
- **S3 — The Read.** Full-screen document over a desaturated globe: brief, charter, status ledger, table view.

Any new feature attaches to one of the three or does not ship. The old client did not fail from bad taste; it failed from accretion — 20 fixed panels, five documented collisions, seven competing navigation systems.

**One mode axis with two positions, derived from the data's own `kind` field, not an invented taxonomy:** `[Events | Places]`. Events = point marks on imagery (43 layers are `kind: points`). Places = one choropleth (4 are `kind: countries`). **Places is stage 9** — shipping a segmented control with a dead half is worse than shipping neither.

### The honesty UX

This is the product, so it is primary content, not a footnote.

**Freshness is per-layer, in TTL multiples, expressed on the marks.** `overdue = (now − fetched_at) / (expires_at − fetched_at)`; fresh ≤1×, late 1–3×, stale >3×, with a 6 h floor so scheduler queue lag never reads as a break. A flat 24-hour rule fails both ways — it flags 30-day-TTL historical layers at hour 25 and clears a 1-minute-TTL flights layer at 23 hours. TTL-relative at 3× correctly catches 11 layers including gdacs at 602×.

The badge derives from the **worst state among currently-rendered layers**, computed from the envelopes the client already parsed. Never from any aggregate endpoint — `/api/health` is backend memory state seeded from disk mtimes at scheduler start, so a layer that has not fetched since restart simply vanishes from it.

**Stale marks render as a hollow, stroke-only variant of their shape** (`icon-{id}-stale`, `icon-opacity: 0.55`). Marks are never hidden. Silence is displayed as silence.

**A separate header counter reads `16 / 92 sources reporting`**, with one static sentence beside it and a link: *"Sources that stopped reporting are named, with the reason — see the list."* A number that goes down when things break is the most persuasive honesty signal available, and it is free. The counter's source moves once (from `/api/health` to `manifest.counts`) and the badge derivation never changes.

**The Provenance disclosure** — one component, expanding in place inside Detail, always the same rows in the same order: WHERE (source → upstream link) · WHEN measured (the data's own date) · WHEN fetched (ours) · EXPECTED NEXT · HOW · CHECKS ("passed 3 bounds checks, 0 values nulled") · RAW (`quakes.json · 3 KB ↗`). Separating the data's own date from our fetch date is the highest-credibility row and the aggregator already stores both. RAW costs one anchor tag because the file is already static.

**HOW is one of five words**, with matching mark treatment: `measured` | `reported` = solid fill · `modelled` | `reconstructed` = 60% fill + 1 px dashed ring · `machine-written` = **never rendered on the globe**, document only.

**Gaps are rendered, never grey and never absent.** Choropleth nulls get the 45° hatch, and the legend's last chip reads literally `▨ no data · N countries` with N computed at render. Zero and no-reading are visibly different sentences: *"0 conflict events recorded in 24 h (UCDP)"* versus *"no reading — source silent since 26 Jul."*

### Visual direction

The entire beauty budget goes to two surfaces: broadsheet typography on the brief, and a restrained globe with one generated hero image per day. **No third visual system, ever.** What makes the globe look expensive is fewer marks, not more.

**Basemap.** NASA GIBS Blue Marble shaded relief + bathymetry stays as the permanent base layer and is never swapped out, so any upstream failure degrades to today's exact appearance rather than holes in the planet. `VIIRS_Black_Marble` replaces `VIIRS_CityLights_2012` (verified 200, 73 KB at z3). Labels move from CARTO — whose free basemap terms cover grantees only, which WorldTwin is not — to GIBS `Reference_Labels` at `GoogleMapsCompatible_Level9` (verified 200, 6,550 B, keyless, same CDN). *Note for whoever implements: `Reference_Labels_15m` at Level13 404s at every tile tested; use Level9 and lower client `maxZoom` 12→10 to match.* Mirror GIBS z0–z4 (~341 tiles/layer, ~25 MB) into `/home/opc/worldtwin/weather/tiles/` — already bind-mounted read-only into Caddy, so no Caddyfile edit — with GIBS as the z5–8 fallback. This converts ~385 ms-per-tile CloudFront misses into ~1.5 ms local reads on exactly the tiles that gate first paint.

**Light is the depth cue.** A ~45-line solar-position function produces a 361-vertex night-hemisphere GeoJSON, filled `#05070b` at 0.45, recomputed on a **60-second `setInterval` + `source.setData`** — never a rAF loop, never `triggerRepaint`. Draw the city-lights raster *above* it so lights appear only on the night side, replacing the current flat 0.16→0.42 ramp everywhere. This is the single largest perceived-quality jump available, it is computed truth rather than decoration, and it costs nothing at rest. An idle MapLibre map does zero GPU work — that is a battery advantage we currently have and can destroy in one commit.

**Starfield:** delete the opaque `space` background layer, let the canvas composite, and put a fixed radial-gradient + tiled-dot div behind the map container. Zero bytes, zero GPU. (three.js would cost 79 KB gz to draw dots.)

**Bloom:** rejected. There is no MapLibre post-processing path; the only route costs the entire deck.gl dependency. Treat "we want bloom" as a signal to tune the existing circle-blur glow.

**Layer ordering bug:** add every `-glow` layer in one pass, then every symbol layer in a second. They currently interleave, so fires' blurred circles paint over the quake and disaster marks — undermining the entire shape-encoding scheme.

**Label opacity:** start the ramp at `fitZoom + 0.8` rather than a fixed z1.8. Desktop fitZoom is 2.4–2.85, so labels currently sit 24–41% opaque at rest, visible in the shipped screenshot as country names across the globe.

**Typography:** system sans, zero bytes. Five sizes only — 28/17/13/11/10 px. `font-variant-numeric: tabular-nums slashed-zero` on every timestamp, count and coordinate (never on the 28 px hero — proportional figures there). Numbers that do not jitter when they tick is most of the "instrument" feeling. Any text over imagery gets `surface/82` + `backdrop-blur(8px)` + a hairline, or it lives in the plane — measured, `ink-muted` over bright desert imagery is 1.54:1.

### Motion

Constants, not vibes. `easeTo` 700 ms `cubic-bezier(0.22,0.61,0.36,1)` for mark taps (never `flyTo`); sheet 240 ms; mark entry 260 ms; at most 5 pulse rings, 2 cycles each, only for new M≥5.0 quakes.

**Never animate:** the freshness chip, timestamps, the terminator (snap), layer visibility on zoom, or anything on data refresh — hold the previous render and swap GeoJSON in place. An animated trust signal reads as marketing; a skeleton flash on refetch is the documented anti-pattern that makes a live dashboard feel unreliable.

Under `prefers-reduced-motion`: rotation off, rings off, sheet becomes a 120 ms fade, camera becomes `jumpTo`, plus a visible "flat map" toggle switching projection to mercator — rotational vection on a globe is the actual nausea trigger and the media query is under-set on Android.

### Accessibility

- `touchPitch: false` plus `m.touchZoomRotate.disableRotation()` — today a pinch silently twists the bearing and touch users get no compass and no way back to north.
- One transparent hit layer per source: `circle-radius: ['max', ['get','px'], 22]`, `circle-opacity: 0`, bound to a single nearest-feature handler over a padded `queryRenderedFeatures`. Fixes 6 px fire marks (WCAG 2.5.8 wants 24 px) and cross-layer click races together.
- `bottom-[max(1rem,env(safe-area-inset-bottom))]` on the Layers control and Detail; `py-3` on the primary button (~44 px). Today they sit at 16 px and 12 px, inside the iOS home-indicator gesture zone.
- Drop `maximum-scale=1` from `index.html` (WCAG 1.4.4).
- **Table view** at `?read=table&layer={id}` plus a `T` shortcut: plain `<table>`, tabular-nums, sortable sticky headers, `<caption>` carrying the provenance sentence, Download JSON straight to the static cache file. One ~120-line component satisfies never-colour-alone, raw-is-one-click-away, and the journalist use case simultaneously.
- Visually-hidden roving-`tabindex` `<ul>` of the focused layer's top 50 marks; Enter opens the same Detail card and `easeTo`s the camera. `aria-hidden` the canvas; one `aria-live="polite"` region; shortcuts L / T / Esc / ?.

### What the non-globe 40% of a phone screen does

Measured, the globe is currently 40% of a 390×844 viewport, dead-centred, with ~30% dead space above **and** below. That is not restraint; it is an unfinished layout.

```
 56 px  HEADER      wordmark left · "16/92 sources · 4m" right
548 px  GLOBE       y=56→604, map.setPadding({bottom:240}),
                    fitZoom raised ~log2(1.18) so the limb bleeds off both sides
 40 px  SEAM        gradient surface→transparent; the planet dissolves, never a hard cut
240 px  THE PLANE   never hides:
          44 px  THE CLAIM   "156,101 fire detections · last 24 h"  (tabular-nums)
                              11 px beneath: "shown as 10,749 area-weighted cells of 0.25°"
          76 px  THE RECORD  40 px hand-rolled SVG polyline sparkline (~40 lines, no chart
                              library) from /api/cache/v1/counts.json, today's point marked.
                              Days with no entry are GAPS, never zero. Under 30 days present:
                              draw what exists and print "record since YYYY-MM-DD".
         120 px  THE STRIP   horizontally scrolling layer chips (focused expanded, context
                              small), then "Layers 4 · today ▾"
        footer    "NASA FIRMS · measured · fetched 8m ago · raw ↗"
```

Desktop ≥1024 rotates the same three regions: `setPadding({left:380})`, Sheet as a fixed 380 px left rail, Detail as a 400 px right card. **Never floating panels over the globe centre.**

The plane answers "what am I looking at, how many, since when, from whom" without a tap. Every element is computed from data already loaded. The sparkline is the replayable record — the one capability nobody else has — put above the fold.

---

## 8. The staged plan

### Capacity and sequencing — measured, not assumed

Measured from `git log` on `/home/opc/worldtwin`, 2026-04-13 → 2026-08-01: **64 commits across 9 distinct working days in 111 calendar days.** Gaps of 11, 21, 24 and 50 days. Session arrival rate: one working day per 12.3 calendar days. The most recent gap is the longest.

Measured throughput **within** a session: 2026-04-26 landed 158 files / 13,924 insertions in a 13-hour span; 2026-08-01 landed the entire v2 client in a 75-minute commit span; 2026-06-11/12 landed two multi-agent audit sweeps (59 confirmed fixes) plus SGP4 propagation plus security hardening in ~11 hours.

**Therefore all effort below is denominated in SESSIONS** (one session = one 6–13 h burst day). No stage states a duration in weeks or evenings. A stage sized at 1 session is not a promise it lands within 12 days; it is a statement that it fits in one arrival. **Plan for 3 sessions per quarter and be pleased by more.** Total v1 (Stages 0–7) is ~11 sessions ≈ 4–5 months at observed cadence.

### The absence contract — the 60-day rule

Measured worst-case maintainer gap is 50 days. **Every surface this plan adds must be safe unattended for 60 days with zero human intervention.**

- `build_brief.py` must never publish a partial or throwing brief. On any exception it writes nothing, leaves yesterday's `index.html` in place, and appends to `/data/cache/brief/_failures.log`. A missing brief is honest; a broken brief on the front door is not.
- If an item's source layer is stale or dead, the brief **renders the item as dark with the reason**. It does not silently drop it and never substitutes a different source. "What went dark" is the one section that must still work when everything else has.
- If the brief has not generated for 3 consecutive days, `/brief/` shows a dated banner: *"This record has not updated since <date>. The maintainer has not been reached."* — generated by the same cron from the previous run's timestamp, so it fires without anyone present.
- `brief_card.mjs` is best-effort: a failed render falls back to the last good PNG and must never block the text brief.
- No cron added by this plan may write to `history.sqlite`, exceed one minute of one core, or grow `/data` by more than 10 MB/month unattended.

**Every stage acceptance block carries this clause:** *"…and the surfaces this stage adds remain correct, or visibly and honestly dark, after 60 days with no maintainer intervention."*

**And every stage carries STOP-SAFE:** *"If all work halts immediately after this stage, no surface makes a claim it cannot support AND no control silently does nothing."*

### Integration contract — read before writing any code

Four domain plans specified overlapping work on the same five files. **No plan writes a file it does not own.**

| File | Owner |
|---|---|
| `models.py` (LayerMeta) | backend |
| `cache.py` write_envelope + manifest + counts | backend |
| `scheduler.py` `_run_one` | backend |
| `render.py` + render-slice schema | frontend |
| `app/src/lib/api.ts`, `layers/registry.ts`, `lib/freshness.ts` | frontend |
| `/home/opc/openclaw-platform/Caddyfile` (**the live file**) | frontend |
| `sources/*.py` (endpoints, cadence, licence strings) | sources |
| `/brief/*`, hostname, robots/sitemap/OG, README/LICENSE | product |

**Caddy: three edits total across the whole plan**, each applied as `docker exec caddy caddy validate --config <copy>` then `docker exec caddy caddy reload`. The invariant that protects the tenants is **never recreate and never restart**, not "never more than one reload" — a reload is config-only, graceful and in-process; a recreate or daemon restart SIGKILLs every tenant.

- **The live file is `/home/opc/openclaw-platform/Caddyfile` (155 lines, bind-mounted at `/etc/caddy/Caddyfile`).** `/home/opc/worldtwin/deploy/` contains only a 1,785-byte TLS snippet. Editing it changes nothing.
- **`handle /api/cache/*` is declared TWICE** (default `:80` block and the `worldtwin.duckdns.org` block). Every cache-control change must land in both or the bare-IP path silently keeps `max-age=10`.
- **No change may add, remove or alter a bind mount, port, or any field in `openclaw-platform/docker-compose.yml`.** If a change appears to require one, the change is wrong. Reroute onto `/data/cache` (ro, host-writable, already mounted at `/srv/cache`) or the `caddy-data` named volume (rw, `/data` in-container, backed by `/var/oled` — 15 GB at 4%).
- **No `root` directive may ever point at `/data` or `/config`.** Inside the container those are Caddy's own volumes holding the ACME account key and `worldtwin.duckdns.org`'s certificate private key. Every WorldTwin root must be `/srv/cache`, `/srv/weather` or `/srv/weatherwiz`.

---

### Stage 0 — Stop the bleeding, stop the lying

**Goal:** every claim on the live site becomes checkable-true, no live legal exposure remains, and a front-page moment cannot hurt the paying tenants. Ships as two commits.

**Why now:** two of these are present-tense breaches, one is a scheduled corruption hazard that fires next Sunday, and the honesty work is the precondition for every claim the product makes.

#### Commit 0a — Safety (changes nothing a visitor sees)

- Delete `/data/cache/v1/spacetrack_gp.json` (15,029,198 B) and `webcams.json` (169,857 B); hard-404 both routes. Verified serving HTTP 200 today.
- 404-gate the two remaining orphan cache files (`trade.json`, `country_exports.json`) — no registry entry, >200 days stale, publicly downloadable.
- **Maintenance lock.** In `scripts/mem_watchdog.sh`, immediately after `set -euo pipefail` and **before** the down-detection branch, honour `/home/opc/worldtwin/.maintenance` with a **90-minute expiry**. The expiry is load-bearing: a forgotten lock must never permanently disable the only thing that recovers the aggregator. Every script that stops the container takes it with `trap 'rm -f "$LOCK"' EXIT INT TERM`.
- **Fix the pre-existing race in `scripts/wal_truncate.sh`** (Sundays 03:43): it stops the aggregator for a stated 1–5 minutes while the watchdog restarts it within 120 s. The watchdog's down-detection branch was added 2026-08-01 and this has not yet fired.
- Add a `HEALTHCHECK` to the aggregator service (`curl -fsS http://localhost:8090/api/health`, interval 60 s, retries 3). Verified `<nil>` today — which is why `unless-stopped` never re-fired during the six-day outage.
- **Raise the Caddy container memory cap from 128 MiB to 512 MiB** with `docker update --memory 512m --memory-swap 512m caddy` (cgroup v2, zero-downtime, no recreate), then persist it in the compose file. It idles at 54.63 MiB — ~73 MiB of headroom is roughly 1,000–1,800 concurrent TLS connections in Go, and an HN spike at ~6 connections per visitor OOM-kills the shared ingress. **This is the single highest-value containment change available and it depends on no third party.**
- Add `cpus: 2.0` to the aggregator service. No container on this box has any CPU limit today.
- `mem_watchdog.sh` reads `anon` from cgroup `memory.stat` instead of the `docker stats` percentage.
- `/api/history/sources` returns 400 without `prefix`. `/api/history/coverage` becomes a static nightly file. Cap `/api/history/snapshot` decompression at 8 MB.
- `fires` `refresh_s` 600→3600. `ships` world bbox → 8–12 chokepoint boxes, `_prune_stale` moved into the WS ingest loop.
- **Caddy Edit 1** (one validated reload, applied to **both** `/api/cache/*` blocks): asset `Cache-Control` immutable + `no-cache` on index.html; `file_server { precompressed zstd gzip }`; `/beacon` 204; cache TTL 60 s realtime / 900 s rest replacing `max-age=10`; junk-path 404s; `@notget` 405; and the access log —
  ```
  log { output file /data/logs/worldtwin.json { roll_size 20MiB roll_keep 6 roll_keep_for 720h }
        format filter { wrap json fields {
          request>remote_ip ip_mask { ipv4 24 ipv6 48 }
          request>headers>Cookie delete
          request>headers>Authorization delete } } }
  ```
  Into the **caddy-data named volume**, not `/var/log` (which is the container's ephemeral writable layer on the 83%-full root) and not stdout (the json-file driver caps at 3×10 MB shared with every tenant). `User-Agent` must survive the filter — it is the entire subscriber measurement — and the query filter must not apply to `/beacon`.
- Add `5 * * * * /home/opc/worldtwin/scripts/log_rollup.sh` — **hourly**, reading via `docker exec caddy cat`, appending a compact per-day aggregate to `/data/cache/v1/_traffic/YYYY-MM-DD.tsv`. Hourly because the rolled window holds ~85k requests and a launch spike can roll it inside a day.
- **`scripts/backfill_brief_facts.py`** — one-shot, offline, read-only (`mode=ro`, `PRAGMA query_only=1`). For each of the 46 days present in `snapshots`, select the last snapshot per brief layer using an **indexed range predicate** (never `substr()`), decompress one payload at a time, derive brief items 1–4, write `/data/cache/brief/facts/YYYY-MM-DD.json` (~5 KB/day, ~250 KB total). Measured: ~105 s total, one connection, 30 MB peak, +10.6 MB WAL. Runs after the licence-string corrections, never before.
- **Blocking guard:** add an explicit refusal to the top of `scripts/history_prune.sh` and `scripts/history_rebuild.py` — exit 1 if `/data/cache/brief/facts/` is empty. `history_prune.sh` defaults `SNAPSHOT_KEEP_DAYS=7` and would delete 39 of the 46 days.

#### Commit 0b — Honesty at the source (visible)

- `scheduler.py _run_one`: `mark_error` on `result is None`; `NET_SEM(16)`/`CPU_SEM(2)` split; `t0` inside the acquire; `sanity.sweep_and_tag` once, feeding both writers.
- One `models.py` dataclass edit adding all defaulted fields at once: `max_staleness_s`, `retired_reason`, `heavy`, `max_bytes`, `history_policy`, `summary`, `family`, `provenance`. Envelope gains `data_period`, `coverage`, `truncated`, `vintage`, `license_url`.
- **Retire the long tail:** flip `enabled=False` + `retired_reason` on every plugin outside the 16-layer LIVE set. No file deletions. Verify: `docker logs aggregator | grep '[scheduler] started'` drops from ~89 workers to ~16.
- **Tombstones, not silent deletion.** For every retired or dropped layer write a tombstone envelope in place of its cache file: `{id, name, category, state:'retired', retired_on, reason, source, license, count:0, data:[]}`. Verified necessity: `weather/js/layer-browser.js` lists 10 of them as named toggles out of 65 (one, `commodity_prices`, is `default:true`), and `weather/preloader.js:36-42` swallows a 404 with `results.fail++` and no UI path — so deletion alone converts 10 named front-door controls into silent no-ops. **Exception: `spacetrack_gp.json` and `webcams.json` are hard 404s, never tombstones** — a tombstone carries metadata only, which is exactly what those two may not serve.
- One-line render change in `weather/js/layer-browser.js`: a layer whose envelope carries `state:'retired'` shows its reason inline and its toggle is disabled, not absent. **This is the only edit made to the Cesium client in the entire plan**, and it exists so the client can be abandoned at `/legacy/` in an honest state rather than a mute one.
- `gdacs_events` → `rss_7d.xml` via `xml.etree`.
- Correct the twelve licence strings; write `docs/LICENCES.md` enumerating every NC and SA layer.
- Frontend freshness rewrite (once, and it survives Stage 2 unchanged): `expiresAt` on `LoadedLayer`; `lib/freshness.ts`; badge from the worst rendered layer; hollow stale marks at 0.55 opacity; `gdacs_events` `on:false` until the RSS fix is verified, `volcanoes` `on:true`; source counter with its context sentence; `/api/health` poll gated on `document.visibilityState` and raised 30 s→120 s.
- Retire the four fabricated-geography surfaces (`gaming`, `youtube`, `global_events` GKG points, `pulse_mode.top_concerning`).

**Files:** `aggregator/worldtwin/{scheduler,cache,models,server,history}.py`, `sources/*` (flag flips + gdacs + licence strings), `scripts/{mem_watchdog.sh,wal_truncate.sh,backfill_brief_facts.py,log_rollup.sh,history_prune.sh}`, `app/src/{lib/api.ts,lib/freshness.ts,components/Freshness.tsx,components/GlobeMap.tsx,layers/registry.ts,App.tsx}`, `weather/js/layer-browser.js`, `/home/opc/openclaw-platform/Caddyfile`, both compose files.

**Acceptance:** No public URL serves `spacetrack_gp.json` or `webcams.json`. `curl -I` on a cache file returns `max-age≥60` and an ETag; on a hashed asset, `immutable`. `/data/logs/worldtwin.json` exists and the hourly rollup produces a dated TSV. Scheduler reports ~16 workers. Toggling all 65 old-client layers shows every one either rendering data or stating why it does not. With `gdacs_events` manually enabled, the badge shows amber/red and the sheet row states the age in days. `/data/cache/brief/facts/` contains 46 files. `docker inspect caddy` shows `memory.max` 512 MiB and `RestartCount` unchanged. **STOP-SAFE and 60-day clauses hold.**

**Effort:** 2 sessions. **Risk:** the healthy count visibly drops from 81 to ~16 live + 41 retired — mitigated by shipping tombstones and the counter context sentence in the *same* commit. **Unblocks:** everything.

---

### Stage 1 — Pilot: the smallest honest brief (the falsification test)

**Goal:** find out in three weeks, not twelve months, whether anyone returns to a template-generated instrument log.

**Why now:** the retention thesis is the plan's least-supported claim and was originally scheduled six stages deep, behind a rename and a URL-state refactor. Verified 2026-08-01: all five brief items and the "what went dark" scan are computable today from `/data/cache/v1` envelopes with stdlib alone, and `/home/opc/worldtwin/weather` is **already** bind-mounted into Caddy at `/srv/weather` and served at `/worldtwin*` — so the pilot publishes with no ingress change at all.

**Tasks:**
- Optional but recommended (~$130 one-time): register the domain now (see Stage 3) and add the hostname, so the pilot is not measured through a DNSBL-blocked host. Skipping this biases the denominator downward in exactly the audience under test.
- `scripts/build_brief.py` v0, stdlib only. **Reads static files only** — `/data/cache/v1/manifest.json` (or raw envelopes pre-Stage-2), the per-layer envelopes, and previous briefs. **Never `/api/health`, `/v1/*` or `/api/history/*`** — all of those are `handle /api/* { reverse_proxy aggregator:8090 }` and 502 when the aggregator dies. Writes to `/home/opc/worldtwin/weather/brief/`. Cron `35 6 * * *`.
- All five items, with the window label derived from each series' own first/last timestamps.
- Deep links use the layers-only URL the client already writes (`/worldtwin/v2/?layers=quakes`). No hero card; `og:image` points at a static committed PNG.
- Backfill the 46 dated briefs from `facts/`, plus 6 explicit gap pages for 2026-07-25 and 07-27..31 naming the cepii_baci outage, with 07-26 marked partial.
- Post to **recoverable channels only**: r/selfhosted, lobste.rs, two or three RSS-reader and self-hosted-dashboard communities, with the Glance `custom-api` snippet. **Reserve Show HN, r/dataisbeautiful and the Bellingcat toolkit for Stage 7** — they are effectively single-use and must not be spent on a prototype.

**Acceptance:** 14 consecutive briefs generated unattended. `feed.xml` validates as RSS 2.0 and contains **only forward-dated items** — the 46 backfilled briefs appear in `/brief/archive` and the sitemap, never in the feed. The archive index shows 46 dated entries and 6 named gaps on day one.

**The decision, pre-committed and asymmetric** (a weekend generator on a DNS-filtered host with no share card is a weak negative and a strong positive):

| Result | Action |
|---|---|
| ≥25% day-14 return **or** ≥100 subscribers | Thesis supported. Execute Stages 2–7 as written. |
| 10–25% return | Alive but unproven. Run Stages 2–3 only (name + shareable link), reissue the pilot on the real domain with a card, re-measure. |
| <10% return **and** <30 subscribers, on a pilot reaching ≥200 distinct visitors | Hard negative. Stage 10's vertical becomes the plan, at ~10 sessions saved. |
| <200 distinct visitors reached | **NO RESULT, not a negative.** The channel failed, not the product. Re-run on the real domain. |

A confounded null must never kill the thesis — that failure mode costs more than the one the pilot exists to prevent.

**Effort:** 1 session + 21 days of waiting. **Unblocks:** the decision to spend the next 9 sessions.

---

### Stage 2 — The contract

**Goal:** the delivery contract exists as a static artifact, the counts ledger starts filling, and the box stops writing 9 GB/day it does not need to.

**Tasks:** `cache.write_manifest()` (atomic, inside the commit path, gzip sidecar); `cache.write_counts()`; delete the `.data.json` write and `rm` the 361 MB of existing duplicates; `fsync` + `posix_fadvise` for files >1 MB; `HISTORY_POLICY` + `history_min_interval_s`; periodic `wal_checkpoint(PASSIVE)`; `max_bytes` and `bytes`/`bytes_gz` in the manifest; delete `/v1/layers/{id}`, `/v1/layers/{id}/data`, `/api/{layer}`; rewrite `nightly_audit.py` against assertions A–F; repoint the source counter at `manifest.counts` and delete the `/api/health` poll (badge derivation untouched); domain-expiry check via stdlib socket to `whois.nic.<tld>:43`.

**Acceptance:** `manifest.json` under 15 KB gz listing all 92 entries including the four with no registry entry. `manifest.counts.stale + .dead` names exactly the layers past `expires_at + grace` **or** past `max_staleness_s`. `counts.json` under 60 KB gz with an entry for every layer that fetched yesterday and none for any that did not. **Take the maintenance lock, stop the aggregator, confirm `manifest.json` still serves off disk with an unchanged `generated_at` and the client renders "aggregator down" rather than green.** Cache-attributable writes under 3 GB/day; `memory.stat file` under 700 MB; WAL growth per hour down ≥50%.

**Effort:** 1 session. **Unblocks:** Stage 4's brief, Stage 5's render slices, Stage 8's rebuild gate.

---

### Stage 3 — The front door

**Goal:** a name that can be typed, a root that is the good client, and three public artifacts stating the doctrine and the failures.

**Tasks:**
- **Register `earthrecord.org` for the maximum 10-year term** (~$130 one-time, ~$13/yr) with registrar auto-renew and registrar-lock. Fallback `theworldrecord.org`. **Not `groundtruth.earth`:** GroundTruth (groundtruth.com, formerly xAd) is an active, funded US location-data company; "ground truth" is the most generic term of art in remote sensing and ML labelling, so it is unownable as a brand query; and it *overclaims* — "ground truth" means verified reference data, and this product explicitly does not verify anything, it relays instrument output with provenance attached. That is the same category of claim as "twin". `.earth` is also a premium TLD at ~$45–90/yr renewal versus ~$13 for `.org`.
- **Point it at Cloudflare's free nameservers at registration time, grey-clouded (DNS-only).** Steady state is origin-direct: no Cloudflare in the request path, Caddy keeps its own Let's Encrypt, real client IPs preserved. Before leaving this stage verify: zone Active, **Universal SSL Active** (cold-zone issuance takes up to 15 min and cannot be done under load), SSL mode **Full (strict)** (never Flexible — it loops against Caddy's HTTPS redirect), **A-record TTL 300 s**, and one rehearsal (orange-cloud, curl root + one cache file, grey-cloud again). This turns the emergency mitigation into a single toggle instead of an hours-long NS migration under load. `worldtwin.duckdns.org` cannot be protected at all — it is a leaf A record inside DuckDNS's zone with no NS and no SOA.
- Configure `trusted_proxies static <Cloudflare ranges>` + `client_ip_headers CF-Connecting-IP` **now**, while inert. Without it the emergency toggle logs every visitor as a Cloudflare edge IP and destroys the launch cohort during the exact window it measures.
- **Caddy Edit 2:** new hostname block, `/legacy/` with `X-Robots-Tag: noindex`. **No 301.** `worldtwin.duckdns.org` keeps serving 200 forever as a free, never-expiring hot standby, with `rel=canonical` pointing at the new host from both hostnames. The plan's own premise is that renaming is cheap because there are zero backlinks — which means there is no link equity for a 301 to consolidate, and duckdns accrues none on a public suffix. The redirect's only remaining function is duplicate-content prevention, which canonical handles. Keeping both live costs two lines and preserves a fallback that cannot lapse during a 50-day absence.
- Move v2 to the site root; Cesium client to `/legacy/` with a one-line banner and a **frozen-on date**: *"Frozen <date>. Layers below this line stopped updating on that date."*
- Build `/charter` (the five rules, verbatim, plus "Not in this version" and the archive's stated retention window) and `/status` (all 92 registered plugins from the manifest, counts rendered as `{live} live · {stale} stale · {retired} retired · {dead} dead`).
- **Never hard-code a source count anywhere.** `editor_probe.sh` asserts no digit-plus-"live" string exists in any committed template. Verified 2026-08-01 the true tuple was 82/5/0/5, not the 82/8/2 previously written.
- `og:title`, `og:description`, `og:image`, `twitter:card`, canonical. Real `robots.txt` and `sitemap.xml`; unknown paths return an actual 404 (today `/nonexistent-page-xyz` returns HTTP 200 with a zero-byte body).
- `README.md`: delete "Platform code is private", delete the bare-IP demo link, add **LICENSE (AGPL-3.0)**, push the actual live frontend. **Audit the repo's own licence while doing it:** vendored `mledoze/countries` is ODbL and cannot be relicensed under AGPL — record third-party data licences in a `THIRD-PARTY.md` rather than asserting AGPL over the whole tree.
- **Rotate the Cesium Ion access token.** `weather/js/cesium-setup.js:13` and `weather/js/time/cesium-setup.js:13` hardcode a live billable JWT, both tracked in the public repo. Since `/legacy/` stays live the token must keep working — so rotate it into an untracked config file, not a tracked one, and revoke the old.

**Acceptance:** Pasting the root URL into Slack renders a card with an image. `/status` lists every plugin with an explicit state and no omissions, with counts read from the manifest. `/nonexistent-page` returns 404. Four public surfaces agree on one source count, none of which is hard-coded. The old duckdns URL returns 200 with a canonical. Killing DNS for the new domain leaves the site fully reachable. A whois expiry figure appears in the nightly audit. The repo builds the live site from what is in it, and `git log -p` shows no live Ion token.

**Effort:** 1 session. **Risk:** ACME on the shared ingress — mitigated because the four tenants hold **zero certificates** (they are served over plain HTTP on the bare-IP block; Caddy's store contains only `worldtwin.duckdns.org`), and LE limits are per registered domain.

---

### Stage 4 — The brief, finished

**Goal:** the return loop is complete, permanent, deep-linked, and backed up off this box.

**Tasks:**
- **Caddy Edit 3:** briefs move to `/data/cache/brief/` — **inside the existing `/data/cache → /srv/cache:ro` mount**, so no mount is added and the ingress is never recreated. Verified: host-side subdirectories created under `/data/cache` appear inside the container immediately.
  ```
  handle /brief* {
      root * /srv/cache          # → /data/cache/brief/…
      file_server { precompressed gzip }
      @dated path_regexp ^/brief/[0-9]{4}-[0-9]{2}-[0-9]{2}
      header @dated Cache-Control "public, max-age=86400"
      @live not path_regexp ^/brief/[0-9]{4}-[0-9]{2}-[0-9]{2}
      header @live Cache-Control "public, max-age=1800"
  }
  ```
  **Never `immutable`.** That directive is only safe on content-addressed URLs and `/brief/2026-08-01` is not one. The caching win is nil (a 4 ms sendfile inside a 10 TB free egress allowance — the same ground on which this plan rejects a CDN) and the cost is a year-long uncorrectable window.
- `app/src/lib/urlState.ts`: serialise `{layers, cam:"lat,lon,zoom,bearing,pitch", sel:"<layerId>:<pointId>"}`; `history.pushState` debounced 400 ms on camera idle; parse on boot. "Copy link to this view" beside the freshness chip. Upgrade brief deep links to use it.
- `scripts/brief_card.mjs` adapted from `shoot-globe.mjs`. **Cron `20 6 * * *` — before the brief, not after.** Measured on this box: 36.3 s wall, ~14 CPU-seconds total across the Chromium tree at `nice -n 19`, peak node RSS 218 MB, because the 35 s settle is idle wait and an idle MapLibre map does zero GPU work. Wrap in `flock -n … timeout 300`.
- `build_brief.py` **must `stat` the day's card before emitting any reference to it.** If absent: omit the `<img>`, set `"card": null`, render *"Globe card not generated for this date."* A dated brief may never reference an asset that did not exist at write time.
- `scripts/archive_push.sh` — ~30 lines, no new dependency. `git init` once in `/data/cache/brief`; after the brief, commit and push to a second GitHub repo (`earthrecord-archive`). Cron `45 6 * * *`. git is installed and GitHub SSH from this box is verified working, but the existing key is a **deploy key** scoped to one repo — generate one new deploy key (5 min). **This is the mechanism behind "byte-stable forever."** A public commit history also makes a silently-edited past brief a visible diff, so "never quietly fixed" becomes checkable by a third party rather than asserted. Sizing: ~280 KB/day ≈ 100 MB/yr against GitHub's 1 GB soft warning ≈ 8–10 years.
- Publish the "use this in your dashboard" doc with a copy-paste Glance `custom-api` config and a **stated polling contract** (min 15 min, use the `.gz` sidecar, honour `Cache-Control`).

**Brief content spec — six sections, template-driven, no model:**

> **0. PIPELINE STATE (masthead, always rendered).** `now − max(fetched_at)` across all envelopes, and `now − manifest.generated_at`. If nothing has been written in over an hour the brief **leads** with: *"The aggregator has not written since <ts> (<N>h ago). The observations below are the last on record, not today's."* A frozen `generated_at` is the detector, never the claim.
>
> **1. Largest quake in 24 h** — M, place, depth, USGS, deep link.
> **2. Highest active GDACS alert** — level, type, country, population exposed.
> **3. VIIRS fire detections in 24 h** against the layer's own 7-day median from `counts.json`. **No country breakdown in v1** — FIRMS points carry no country, and attributing by centroid or grid cell would reproduce the exact `pulse_mode` defect this plan retires.
> **4. Instrument of the day** — rotating pool: internet outage (Cloudflare Radar), aurora Kp (SWPC), chokepoint transits (PortWatch), CO₂ ppm (NOAA), Brent (FRED). **Window label derived from the series' own first/last timestamps, never hardcoded.**
> **5. "What went dark" / "What came back"** — a 24-hour **delta**, never cumulative, computed by diffing today's per-layer state against the state recorded in **yesterday's brief JSON on disk**. The previous brief is the state store and it lives outside the aggregator, so an outage surfaces on day 1 as the whole board flipping dark and on every following day as "still dark since <ts>." The JSON gains `came_back` beside `went_dark`, so the front page can never become an append-only obituary.
>
> **WINDOWING (every item):** each item is filtered against the observation's own `observed_at` against a hard cutoff from host wall clock. **If zero observations fall inside the window, the item publishes the absence by name** — *"Largest quake in 24 h: no observation; the USGS feed has not updated since 2026-07-26T10:59Z (6 d)."*
>
> **EXCEPTION-LED HEADLINE:** items 1–4 are a roster and a roster is boring by construction. The brief's *lede* is whatever crossed a stated threshold in the last 24 h (M7+, GDACS red, a national-scale internet outage, a source going dark, a fire count >2σ from its own median). **On a day when nothing crossed a line, the lede says so:** *"Nothing crossed a threshold today."* That is more charter-honest than five filler entries and it protects the one asset a feed has — the reader's willingness to open it.

**Brief JSON shape (the citable unit):**
```json
{"date":"2026-08-01","generated_at":"2026-08-01T06:35:11Z",
 "window_start":"2026-07-31T06:35Z","window_end":"2026-08-01T06:35Z",
 "generator":"build_brief/1.2","card":"/brief/card/2026-08-01.png",
 "pipeline":{"manifest_generated_at":"...","newest_fetch_at":"...","stale":false},
 "sources_live":16,"sources_total":92,
 "items":[{"kind":"largest_quake","in_window":true,
   "headline":"M6.1 — 88 km SSE of Hihifo, Tonga","value":6.1,"units":"Mw",
   "observed_at":"2026-08-01T03:14:22Z","source":"USGS",
   "source_url":"https://earthquake.usgs.gov/...","license":"Public domain",
   "cache":"/api/cache/v1/quakes.json",
   "view":"/?layers=quakes&cam=-16.2,-173.9,4&sel=quakes:us7000abcd"}],
 "went_dark":[{"id":"gdacs_events","since":"2026-07-26T10:59:56Z","reason":"upstream HTTP 500"}],
 "came_back":[],
 "corrections":[]}
```

`window_start`/`window_end` are mandatory: a 06:35 UTC regeneration covering the prior 24 h means `/brief/2026-08-01` mostly describes 31 July, and journalists are the stated secondary audience.

**Acceptance:** 14 consecutive briefs under 300 KB including the card. Every item carries source, `source_url` and `observed_at`. **The dated JSON is the citable record and its `items` array is append-only** — a claim is never altered in place, only superseded by an entry appended to `corrections` carrying `issued_at`, the original value and the reason (charter rule 4: *"corrections add to history, they don't erase it"*). Corrections publish to `feed.xml` as their own items and index at `/brief/corrections`. The dated HTML is a **rendering** of that JSON and may be re-generated at any time — which is what makes the first template bugfix survivable. **Outage dry run, added to `editor_probe.sh`:** stop the aggregator container alone, run `build_brief.py`, confirm it exits 0 and publishes a brief whose masthead states the pipeline is down, whose items each report absence rather than a stale value, and whose "what went dark" names every layer. `git -C /data/cache/brief log --oneline` shows one commit per day with no gaps and no force-pushes; killing `/data` does not lose the archive. A link opened on a second device lands on the identical camera, layer set and selected feature.

**Effort:** 2 sessions.

---

### Stage 5 — The client: render contract, encoding, composition

**Goal:** the phone stops downloading 2.6 MB to draw 4,000 marks, twelve layers become expressible without a failing colour pair, and the dead 60% of a phone screen becomes the other half of every claim.

**Tasks:** `aggregator/worldtwin/render.py` (`LEAN_GZ_BUDGET = 120_000`, adaptive binning, **`cos(lat)` area weighting**), one added call in `write_envelope`; per-layer `fields` declaration so the tap path is self-sufficient; `app/src/lib/renderSlice.ts` with 404 fallback; delete `RENDER_CAP`; `layers/families.ts` with the three hues and three validated ramps (paste the validator command and PASS output as a comment); registry expanded to ≤15 with `family`, `mark`, `provenance`, `magnitudeField`; toggle reducer enforcing 1 focused / ≤3 context / ≤1 per family; focus/context render split; basemap dim on focus; glow-then-symbol two-pass ordering; source options; `sync()` per-layer diffing; GDACS alert by ring count + word; 45° hatch as the single NO DATA texture; the 240 px Plane with claim / sparkline / strip / provenance footer; `Provenance.tsx`; desktop `setPadding({left:380})`; typography pass; label-opacity fix.

**Acceptance:** `fires.render.json.gz` under 120 KB (measured 68,135 B at 0.25°); the client's fires request transfers under 120 KB; no `RENDER_CAP` reference remains; the legend prints `cell_deg`, `shown` and `n` read from the payload, and states area-weighting. `node scripts/validate_palette.js` on the family hues (`--pairs all`) and each ramp (`--ordinal`) passes in CI and the build fails if not. A unit test asserts the reducer can never produce two context layers of the same family or more than four active. `shoot-globe.mjs` under Xvfb at 390×844 and 1440×900 shows no dead band above or below the globe, the limb cropped at both sides on phone, zero place labels at rest, focused marks brighter and larger than every context dot, and no glow painted over a shape. The sparkline renders from `counts.json`; `grep '/api/history' app/src` returns zero matches; a layer with a 4-day record renders 4 points and the "record since" line.

**Effort:** 3 sessions.

---

### Stage 6 — Beauty, touch, accessibility, table

**Goal:** a lit planet instead of a texture-mapped ball; every mark hittable; every value readable without colour or hover.

**Tasks:** terminator (60 s interval, no rAF); city lights above it; Black Marble swap; GIBS `Reference_Labels` replacing CARTO + `maxZoom` 12→10 + Credits update; CSS starfield; vignette 46%→52%; GIBS z0–z4 mirror into `weather/tiles/` (**check `df -h /` first — root is at 83% with 5.1 GB free**); ~15 KB AVIF poster inlined with `fetchpriority=high`, faded on first `idle`; MapLibre code-split behind `await import()` with `modulepreload`; mobile GPU settings; `touchPitch:false` + `disableRotation()`; transparent hit layers; safe-area insets; drop `maximum-scale=1`; `Table.tsx`; hidden mark list + shortcuts; motion constants.

**Acceptance:** A screenshot under Xvfb shows a visible terminator with city lights only on the night side and no labels at rest. `grep -r 'triggerRepaint' app/src` returns no match inside a rAF loop. LCP resolves to the poster image, not a text pill; pre-paint JS compile is ~213 KB rather than 1.27 MB. Every mark type is tappable at 390×844 with a 22 px effective target, verified by a Playwright tap at the mark's edge. Tab reaches the mark list; Enter opens Detail. Pinch-zoom does not change bearing. `df -h /` unchanged within noise after the tile mirror.

**Effort:** 2 sessions. **Root-disk guardrail:** `/home/opc/.cache` already holds 1,023 MB of Playwright browsers (two Chromium installs — `npx playwright install` does not remove prior versions) plus 159 MB of node_modules, on a filesystem with 5.1 GB free. Add root free space to the nightly audit (assertion F) and delete stale Playwright versions before adding tiles.

---

### Stage 7 — Full launch

**Goal:** reach the three audiences that would actually return and get a real cohort.

**Launch gate, checked the morning of the post:**
1. `docker inspect` confirms Caddy's cap is 512 MiB.
2. The Cloudflare zone is Active with Universal SSL Active, Full (strict), TTL 300, and the orange-cloud rehearsal has been performed at least once.
3. `trusted_proxies` is live.
4. Frontend asset `precompressed` + `Cache-Control` are live (Stage 0a) — this is a **hard predecessor**, because without `precompressed` on `/worldtwin*` Caddy compresses every shell asset per request, taking CPU directly from the tenants' agents.
5. A one-line runbook exists somewhere reachable from a phone: *"orange-cloud the A record; if the origin still saturates, enable Under Attack mode."*

**Tasks:** Show HN and r/dataisbeautiful, leading with the constraint-and-honesty story ("92 data feeds on one free ARM box, and a status page that tells you which ones are broken"); the Bellingcat toolkit submission in their own schema with **Limitations filled honestly** (one free-tier box, no SLA, dead upstreams named, conflict data is weekly not live); the dashboard-widget doc to self-hosted communities; a Ko-fi / GitHub Sponsors link and a "how this is funded and licensed" page.

**Measurement — three numbers, never summed:**

- **SUBSCRIBERS (feed side).** Never count IP+UA pairs: cloud readers poll once per feed from a rotating pool and carry the real count in the User-Agent, so pairs both under-count (one Feedly poller = N humans) and over-count (one poller = many pairs across a week). Report two components: `declared` = sum of the integer matching `/(\d+)\s+subscribers/i` in the UA across named cloud readers, deduped on the reader's identity token, max seen in window; `independent` = non-declaring pollers that fetched `feed.xml` on ≥3 distinct days. Publish as *"N declared subscribers across M cloud readers + K independent pollers,"* with the caveat that `declared` is self-reported by a third party and includes their inactive accounts. **Summing the two into one figure is the exact error this project exists to refuse.** Target at 90 days: `declared + independent ≥ 300` AND `independent ≥ 40`.
- **RETURN (browser side).** Never repeat IPs — mobile CGNAT collapses thousands of users onto one address while residential DHCP rotates one user across many, so a repeat-IP rate measures carrier topology. Use a first-party cohort id on `/beacon`: a random 16-byte id in localStorage, sent as `/beacon?v=<id>&d=<yyyy-mm-dd>`, expired after 90 days, **suppressed when `?notrack` is present or `navigator.globalPrivacyControl` is true**, and described in one sentence on the funding page. No cookie, no third party, and **less personally identifying than the raw IPs this plan previously intended to store**. `day14_return` = share of ids first seen on day D emitting any beacon on D+10..D+17. Do **not** substitute "returning pollers" — a feed reader keeps polling long after the human stops opening the folder, so poller retention has a floor near 100% and would confirm the thesis regardless of truth.
- **READING.** Requests for `/brief/YYYY-MM-DD` from browser UAs within 48 h of publication, as a ratio to `declared + independent`. The only number showing a subscription is read rather than merely retained.

**The one number that decides the thesis: `day14_return`.** It may only be evaluated once a launch cohort contains **≥200 first-seen beacon ids**; below that N the answer is "not yet measurable" and the correct action is a second launch attempt, never a pivot. Then: ≥25% keeps the loop; 10–25% means the loop works for a narrower audience and the next move is distribution, not architecture; below 10% after two launch attempts that each cleared the N gate, narrow to Stage 10's vertical.

**Guardrails, replacing the useless egress alarm** (measured egress is ~50 GB/month against a 10 TB allowance — a 2 TB alarm is 40× above any reachable ceiling and is decoration): an **iowait / queue-depth alarm on `/dev/sdb`**, a **Caddy p99-latency check against a tenant route**, aggregator anon RSS under 2 GiB, `/data` free above 30 GB, root free above 4 GB. No tenant container restarts and Caddy's `RestartCount` unchanged across the launch window; if Caddy exceeds 60% of its raised cap, throw the proxy toggle immediately rather than watching.

**Effort:** 1 session + launch day.

---

### Stage 8 — The history rebuild and the citable archive

**Goal:** 56 GB → ~2.0 GB, keeping full forensic replay and every layer's dated record.

**Gate:** Stage 2's `HISTORY_POLICY` verified by a **6-hour WAL-growth measurement**, down ≥50% from the 453 KB/s baseline — **not** by "48 h of flat `page_count`," which is satisfied *today* on a store burning 39 GB/day, because `wal_autocheckpoint=5000` is defeated by long readers and the main file only grows at checkpoint.

**Tasks:** `scripts/history_rebuild.py` with `WITHOUT ROWID` tables, bounded resumable batches each in its own short read transaction (never one long-lived ATTACH), progress output, a resume table, a wall-clock deadline and a `/data` free-space floor; the mandatory range-predicate query form with an asserted query plan; the graduated snapshot rule for **every** layer; observations for the trimmed curated prefix list (drop `economy.` — the one prefix that would not finish counting — and `commodity_prices.`, which is dropped anyway); `CREATE INDEX` and `PRAGMA integrity_check` **with the aggregator up**; repeated narrowing delta passes until one completes in under 30 s; `scripts/wal_truncate.sh` immediately before the swap.

**The swap, under the maintenance lock:** stop the aggregator alone and **assert** it is not running; `wal_checkpoint(TRUNCATE)` on the old DB and **assert `history.sqlite-wal` is 0 bytes** (non-zero means a writer is still attached — abort); close the builder connection and run `wal_checkpoint(TRUNCATE)` + `PRAGMA journal_mode=DELETE` on the new file so it arrives with **no sibling `-wal`/`-shm`**; then swap the **full file set**:
```
mv history.sqlite      history.sqlite.OLD
rm -f history.sqlite-wal history.sqlite-shm
mv history-new.sqlite  history.sqlite
ls history.sqlite-wal history.sqlite-shm 2>/dev/null && exit 1
```
A SQLite `-wal` carries no database-identity binding (same page_size 4096), and `server.py:165` runs `wal_checkpoint(TRUNCATE)` at boot inside `lifespan()` — so a stale 3.8 GB WAL left beside the newly-renamed file **will be replayed into it**. That is silent corruption executed deliberately by the aggregator at startup. Make the boot truncate conditional on `wal > 512 MB` and move it to a post-startup background task so it can never block uvicorn accepting.

**Before deleting `history.sqlite.OLD`:** dump the `snapshots` table alone to `/data/history/snapshots-preprune.sqlite` (2.84 GB, all 68,097 rows). It is the only copy of the 11 Jun – 1 Aug 2026 seed record. Delete it only after the replay probe passes — not on a timer. Push a gzipped copy off-Oracle first if the discarded observations are ever likely to be regretted; if not, **record in `/charter` which date range of decomposed observations was destroyed and when**. That is a one-way door and it deserves an explicit decision, not a default.

**Acceptance:** `history.sqlite` under 2.5 GB. `PRAGMA integrity_check` returns ok. `/api/history/series/{maddison_history,vdem_democracy,clio_life_expectancy}.USA` each return >50 rows (added as a probe to `v2-smoke.mjs`). **Replay probe:** for each of quakes, gdacs_events, volcanoes, flights, swpc_aurora, `/api/history/snapshot/{id}?at=<each of the 46 pre-rebuild dates>` returns a payload whose `fetched_at` falls on the requested UTC day for at least 40 of them — and the 6 outage dates still return 404, because the gap is part of the record. `history.sqlite.OLD` is self-contained (its WAL was checkpointed to zero), verified by starting the aggregator once against it before deletion. `df /data` shows >90 GB free.

**Effort:** 1.5 sessions build + a **3–8 minute** serving window (dominated by the old-file checkpoint; not the 2 minutes originally estimated, and not the 20–45 the naive ordering would have cost). Static cache files keep serving throughout.

---

### Stage 9 — The crawlable corpus and the citable archive

**Goal:** turn the static-JSON architecture into the only growth engine a zero-budget data site has, and open the archive backwards.

**Tasks:** generate `/source/<id>` pages at build time from the manifest with `schema.org/Dataset` JSON-LD, live freshness, real licence text, upstream failure history and a deep link into the globe (~92 pages; Google confirmed Dataset markup still supported in 2026, deployed on 10K–100K domains); publish the snapshot retention rule verbatim in `/charter` as the archive's window; **then** build `/on/YYYY-MM-DD` on `/api/history/snapshot` with a copy-citation button, stating both boundaries on the page — the archive begins 11 Jun 2026 (earlier dates return a page saying so, never an empty globe) and 26–31 Jul 2026 is a named gap with the reason; `/embed` (one layer, deep-linked, fixed height, provenance chip and attribution baked in, no tracking); the `Places` register with `country_polygons` simplified via `npx mapshaper -simplify 15% keep-shapes -filter-fields iso3 -o precision=0.001` (848 → ~183 KB gz; **must be mapshaper** — hand-rolled RDP cracked shared borders and silently dropped 15 of 242 countries), choropleth joined by a data-driven `match` rebuilt only on measure change plus `promoteId:'iso3'` + `setFeatureState` for hover, never a per-frame callback; the 90-day time machine reading a nightly-precomputed `_coverage.json` built from `SELECT DISTINCT layer_id, SUBSTR(fetched_at,1,10) FROM snapshots` (index-only, 0.1 s), user-initiated only, no auto-play, with a 1 px status-warning border reading "viewing 26 Jul — not live"; the feed catalogue for Datawrapper/Flourish users **gated programmatically on the corrected licence field**, with SA sources carrying their notice; extract the aggregator as a standalone open-source provenance-preserving aggregation framework and apply to NLnet's successor call and the Sovereign Tech Fund.

**Gate on `/on/`:** do not ship the copy-citation button, and do not solicit citation as a success metric, until the archive mirror has **≥90 days of unbroken daily commits**. Publish `/charter#permanence` stating where the second copy lives, what happens to `/brief` URLs if this box dies, and the retention window. A citation you invited and then broke damages the citer's published work, not just yours.

**Effort:** 3–4 sessions.

---

### Stage 10 — Later: the one vertical worth being best in the world at

**Cross-source disaster corroboration** — one event shown through GDACS, EONET, FIRMS, USGS, ReliefWeb and IDMC simultaneously, with the disagreements between them displayed rather than reconciled.

Recover ReliefWeb v2 (free approved appname via one Google Form); replace `crises` with INFORM Severity; upgrade `idmc_displacement` to the geocoded IDU feed; build an event-correlation view keyed on time+place showing each source's own figure, own timestamp and own precision flag side by side; **never reconcile — show the spread**; fatality figures always render with UCDP's low/best/high band, never `best` alone; rename GDELT `severity` to `media_attention` and give attention-scaled and fatality-scaled marks **different shapes** so size is never read as deaths across both.

**Acceptance:** a single named disaster opens and shows ≥4 independent sources with visibly different numbers, each attributed and timestamped, and a plain sentence explaining why they differ.

**Effort:** 2–3 sessions. **Only if Stage 7 metrics justify it — or immediately, if the pilot returned a hard negative.**

---

## 9. Decisions register

| # | Decision | Reason | Rejected |
|---|---|---|---|
| D1 | The product is a dated, sourced daily record, published as a brief, explorable as a globe | Breadth is a weekend-buildable commodity with zero traffic; the one thing a clone cannot fabricate is a multi-year dated record with an honest failure log | "Live world dashboard" (indistinguishable from the clone tier); "provenance-first" (table stakes at OWID/Data Commons/Zoom.earth); "digital twin" (owned by DestinE and NVIDIA Earth-2, and means simulation) |
| D2 | The archive ships as a **publication** — static dated files — with the history store as an input, used exactly once, offline | 56 GB store with retention gated off; but the argument is against a *query surface*, not a *read source*. One offline read costs 105 s and yields 46 dated days at launch | Shipping SQLite replay in v1; dropping the archive claim; starting the moat at day zero when 46 days exist |
| D3 | The retention loop is the Daily Brief plus RSS, tested in a pilot **before** the rename and the URL refactor | A globe is a spike object (nullschool: 438 HN points once, 2–21 on every repost). The thesis is the plan's weakest claim and was scheduled last | Email newsletter (a daily obligation one person cannot sustain); push/alerts (Watch Duty's moat is 70+ human verifiers) |
| D4 | No LLM anywhere. `gemini_narrative` is deleted, not moved to `/narrative` | It publishes "+830.77% over ~12 months" for a ten-year move and ships two of three paragraphs empty. Keeping a generated page while the positioning says "Nothing here is generated" is a self-refutation on the front door | Gemini Flash at 6 h with the window fix (~$1.30/mo, affordable, still one more thing that can quietly lie); self-hosting (4 cores shared with four paying tenants) |
| D5 | "What went dark" is a permanent daily **delta** with a matching "came back", cumulative only on `/status` where `retired` is a dated tombstone excluded from the failure count | No competitor does this. Bidirectional and delta-scoped is what stops it becoming a monotonic obituary at the measured ~1.0 external break/month | Burying failures on `/status` only (a page nobody visits is not a differentiator); a cumulative front-page list |
| D6 | Rename to **earthrecord.org**, 10-year term, Cloudflare free NS grey-clouded, **no 301** — duckdns stays live with `rel=canonical` | worldtwin.app is a live competitor already outranking the real site; duckdns is on IPFire's DBL and blocked by school/corporate filters; "twin" means simulation. Zero backlinks means zero equity for a 301 to move, so the 301 buys nothing while making a paid, expiring name a single point of failure for a maintainer who goes dark for 50 days | groundtruth.earth (active company GroundTruth/xAd; generic term of art, unrankable; and it overclaims verification — same error as "twin"); worldtwin.org/.earth (keeps a name that contradicts the product); paying aftermarket for .com |
| D7 | v2 becomes the root; the Cesium client freezes at `/legacy/` with a dated banner, noindex, and exactly one code change ever | It is where "too complicated" lives — 7 competing navigation systems, 4,037-line CSS with three repair passes, ~25 MB before first paint, and most of the live charter violations | Deleting it (loses the scrubber and dossiers as future assets); porting features across before launch |
| D8 | 16 plugins enabled; 8–12 on the globe by **criterion**, capped at 12; registry cap 15; ≤4 on screen | Retiring the long tail is the only thing that actually reduces maintenance surface — v1 scoping the *render* surface alone changes nothing. `scheduler.py:147` makes retirement a one-line reversible flag flip | Porting the 70-toggle set; keeping 76 plugins fetching to feed a frozen client; deleting the long tail (throws away code stages 9–10 reuse) |
| D9 | Free of charge for v1/v2, with a **stated review trigger**, not an eternal invariant | ~22 of 92 layers plus the CARTO basemap forbid commercial use today — but v1 is 12 layers and the source work removes NC ties on independent grounds. Calling it an invariant guarantees nobody re-examines it when the constraint dissolves | Ads ($20–80/mo at unreachable traffic, worst risk/reward on the board); paid API (barred simultaneously by Comtrade, EM-DAT, Windy, YouTube, OpenSky, CelesTrak); B2B/SLA (endangers other people's customers) |
| D10 | AGPL-3.0 + third-party licence file + push the live frontend + rotate the Ion token | NLnet and Sovereign Tech Fund both hard-require OSI licences; the current posture blocks the only funding path with meaningful EV, to protect code with 0 stars. A live billable Ion JWT sits in a public repo whose prominence this plan is about to raise | Staying closed; asserting AGPL over vendored ODbL data; journalism/climate grants (fund stories, not platform maintenance) |
| D11 | Exactly 3 categorical hues, permanently. Identity beyond 3 comes from focus state and mark shape | Re-validated on the real surface with `--pairs all`: 3 pass at worst CVD ΔE 9.4; all 7 candidate 4th hues fail the CVD floor and/or the hard normal-vision floor of 15, which secondary encoding explicitly cannot excuse | A 4th/5th hue with secondary encoding; 12 simultaneously-toggleable equal-weight layers (needs ≥12 px marks; unreadable on a 390 px phone) |
| D12 | Large layers render as an **area-weighted aggregate**, not a top-K sample; one derived artifact per layer (`{id}.render.json`) | Top-4,000-by-FRP covers 5.9% of occupied cells and erases small agricultural burns; the grid covers 100% at 68 KB. But unweighted lat/lon bins overstate boreal density by 1/cos(lat) — the same class of confident-wrong number | Client-side top-K (downloads 2.6 MB to show 2.6%); backend `SummarySpec`; sources' columnar reshape (breaks three consumers to reach 1.10 MB against 68 KB); binary transport (within ±10% of gzipped JSON) |
| D13 | Stay on MapLibre; write the deck.gl trigger rule into AGENTS.md | MapLibre is already 78% of the JS; deck.gl adds 145–238 KB gz for a problem that is transfer and parse, not fill rate, and its IconLayer is broken on globe projection (visgl#9554) | deck.gl now; Cesium (4.7× the shell); globe.gl; Kepler.gl (alpha application); Mapbox v3 (licence) |
| D14 | The sparkline and the brief median read `counts.json`, a static ledger written at commit time — never `/api/history/*` | Verified: no per-layer count series exists, `history.py:194-197` refuses fires entirely, the snapshot blob has no `count` key, and the specified endpoint shape does not exist. The count is free at envelope-write time | Deriving from observations (a long-lived reader on 112.8M rows); decompressing 717 fires snapshots (~18.6 GB of inflation); backfilling the ledger (cosmetic head start for a sustained reader) |
| D15 | Copy-forward rebuild keeping the **graduated snapshot rule for every layer**; never DELETE+VACUUM | VACUUM needs 56 GB free against 44 GB. "Newest snapshot per layer" saves 0.44 GB of a 54 GB reduction and deletes 1,911 quakes / 718 fires / 228 gdacs snapshots — the differentiator, three stages before shipping it | DELETE+VACUUM; newest-per-layer; DuckDB/Parquet (≥125 MB/thread, missing aarch64 wheels, wrong engine for point seeks) |
| D16 | Briefs to `/data/cache/brief`, access log to the `caddy-data` volume, three validated Caddy **reloads** total | Both paths land inside mounts that already exist, so no bind mount is added and the sole ingress is never recreated. `/var/log` lands on the container's ephemeral layer on an 83%-full root; `root * /data` would serve Caddy's ACME store | A new bind mount + `docker compose up -d caddy`; `output stdout` (json-file capped at 3×10 MB, shared with every tenant); "exactly one Caddy change" as the safety property |
| D17 | Dated briefs are `max-age=86400`, never `immutable`; the JSON is append-only with a `corrections` array; the HTML is a re-renderable view | `immutable` is only safe on content-addressed URLs, buys nothing at a 4 ms sendfile, and costs a year-long uncorrectable window. The charter *mandates* corrections ("corrections add to history, they don't erase it") — the byte-stability criterion contradicted the rule it existed to enforce | `max-age=31536000, immutable`; "byte-identical forever" as an acceptance criterion |
| D18 | Metrics are UA-parsed declared subscribers + independent pollers + a first-party cohort id, with an N≥200 gate | IP+UA pairs have no monotone relationship to subscribers; repeat-IP retention measures carrier topology; poller retention has a floor near 100% and would confirm the thesis regardless of truth. And a perfect metric still fires on noise at N=12 | IP+UA pairs; repeat browser IPs; returning pollers; an analytics container (no headroom) |
| D19 | Off-Oracle daily `git push` of the brief archive, before any citation is solicited | The dominant failure mode for an Always Free tenancy is account reclamation, which takes OCI block-volume backups and object storage with it — so the copy must be off-**Oracle**, not merely off-volume. A public commit history additionally makes byte-stability third-party verifiable | OCI backups/object storage (same tenancy); R2/B2 (durability without verifiability, and a new credential store) |
| D20 | Cloudflare **DNS from day one, grey-clouded**; proxying is a toggle, never the steady state | duckdns is a public suffix and can never be delegated, so the "one-hour contingency" was false. Proxying without pre-configured `trusted_proxies` destroys the launch cohort during the only window that generates it | Cloudflare proxying as steady state; a CDN (10 TB free egress, 4 ms origin, no access log to size it); a second Oracle VM (Always Free is home-region only) |
| D21 | Effort is denominated in **sessions**; the four stage-0s collapse into one; the brief ships in session 3, not session 6 | Measured: 9 working days in 111, one arrival per 12.3 days, but an entire React client in a 75-minute commit span. Session arrival is the constraint, not hours — and the four plans triple-counted the same `mark_error` fix | Hours/weeks/evenings (a cadence never once achieved); summing four plans' estimates (inflated ~1/3 by duplication) |
| D22 | Borders: hatch-and-disclose, no POV switcher | NE's 31 variants exist only at 1:10m — adopting them means a much larger base file, 31 maintained files, and owning a political configuration surface. The hatch gets ~90% of the honesty for ~2% of the work | NE POV variants; silently picking a side; reconciling NE's de-facto splits against geoBoundaries' deliberate overlaps |
| D23 | The launch story is the constraint and the honesty; **not** the ADS-B precedent | The cited "constituency picks worse coverage for cleaner provenance" is a misreading — the ADS-B split was about ownership after the JETNET acquisition, and migration went to comparable-or-better feeds. This plan's own source work switches *away* from adsb.lol precisely because worse coverage asserts absence as fact | Using the ADS-B schism as evidence; treating the honesty wedge as proven rather than as the hypothesis the pilot tests |

---

## 10. Risks and mitigations

**R1 — The project stalls between Stage 0 and Stage 3, leaving the site strictly worse than doing nothing.** Given 21/24/50-day gaps this is the modal trajectory. *Mitigation:* Stage 0 is split so all visitor-visible honesty work (0b) ships with tombstones, an explanatory counter sentence, and the retired-state rendering in the same commit. Every stage carries STOP-SAFE, verified by toggling all 65 old-client layers and asserting each either renders data or states why not.

**R2 — A wedged container that `docker rm -f` cannot clear.** `/var/log/wt-mem-watchdog.log` records exactly this on 2026-07-26, and the only known fix (`systemctl restart docker`) SIGKILLs every tenant. *Mitigation:* the daemon has not restarted since 2026-06-11 and `RestartCount` is 0, so the July wedge resolved without it — it is a transient containerd race under memory pressure, not a permanent state. The real gap was the reporting blind spot (`docker stats` reports an exited container as 0.00%), already closed by the down-detection branch. Add the container HEALTHCHECK, `--name` every one-shot so it is findable and reapable, `flock -n` + `timeout` on every new cron, and schedule one-shots at 07:10+, never inside the 06:15–06:45 window.

**R3 — The measurement apparatus takes down the tenants during the only event that produces data.** *Mitigation:* the log lives in the `caddy-data` volume on `/var/oled` (15 GB at 4%), not root; hard-bounded at 20 MiB × 6 rolls; the hourly rollup persists a durable aggregate independent of rotation; Caddy's cap is raised to 512 MiB before launch. Root free space is a nightly assertion.

**R4 — Success is the failure mode.** One Caddy process, 4 shared cores at 65–74% iowait, four paying tenants, no rate limiting (stock `caddy:2-alpine` has no `rate_limit` module and adding one means rebuilding the sole ingress). *Mitigation:* the memory cap raise is the primary containment and depends on nobody being awake; the Cloudflare toggle is the secondary and is pre-provisioned with SSL already Active; static cache serving is a 4 ms sendfile; the expensive surface is the proxied history endpoints, guarded in Python in Stage 0a. Post Show HN yourself, at a time you choose, and stay at the keyboard for four hours — but every mitigation must survive an unattended repost.

**R5 — Break rate outruns repair rate and `/status` becomes a public decay counter.** Measured genuine external breaks are ~1.0/month (not the 5.4 claimed — 9 of 20 "stale" files are 30-day-cadence historical layers not yet due, and two are orphans that never broke). *Mitigation:* a **standing 2 h/week upstream-repair budget, before any new source**; a layer unrepaired after 8 weeks is reclassified `retired` with a public reason and leaves the error budget; the brief section is a bidirectional 24-hour delta; no new source is added in a week where the stale list is non-empty.

**R6 — The brief is boring by construction and subscribers stop opening it.** A median day is an M5 nobody felt, a nine-day-old GDACS orange, a fire count within noise, and an empty "what went dark" if Stage 0 worked. *Mitigation:* the lede is exception-led against stated thresholds, and a quiet day publishes "nothing crossed a threshold today" — more charter-honest than five filler entries. This is precisely what the pilot measures, and the decision rule distinguishes "format is wrong" (10–25%, fix distribution and presentation) from "subject is wrong" (<10%, pivot to the vertical).

**R7 — The honesty wedge may simply not exist at consumer scale.** The claimed ADS-B precedent is a misreading, and "three of our sources broke yesterday" reads to a new visitor as unreliability, not as rigour — that reframe only lands for someone who already trusts the project. *Mitigation:* treat honesty as the *method*, not the promise; lead with the record. Show per-layer state at the point of use so a quakes user sees quakes are live, and reserve the full ledger for `/status`. The pilot tests the wedge for one session instead of ten.

**R8 — The 60-day absence publishes something wrong every morning to a permanent archive.** *Mitigation:* the absence contract, the masthead pipeline state, per-item windowing that publishes absence by name, the 3-day dated banner, and the outage dry run as a standing test in `editor_probe.sh`.

**R9 — Silent SQLite corruption during the rebuild.** Two independent mechanisms: the watchdog resurrecting the aggregator mid-swap, and a stale 3.8 GB `-wal` being replayed into the new file by the boot checkpoint. *Mitigation:* the maintenance lock with a 90-minute fail-safe expiry; assert-not-running; assert WAL is zero bytes before proceeding; three-file swap with a post-swap sidecar assertion; `snapshots-preprune.sqlite` kept until the replay probe passes; `.OLD` verified bootable before deletion.

**R10 — Total loss of the box.** No rclone, no aws/oci CLI, no snapshots; the only "backup" on the machine is `cp jj.db` to the same disk. Always Free A1.Flex capacity is routinely unobtainable on re-provision. *Mitigation:* the daily off-Oracle archive push (R19 above) is a Stage 4 acceptance criterion and gates all citation solicitation. History is explicitly demoted to an input, so its loss costs the v2 replay feature, not the v1 promise.

**R11 — GDPR exposure from raw-IP retention and unbounded aircraft tracks, while applying to EU public funders.** *Mitigation:* no metric derives from a raw client IP; `ip_mask /24` in the log filter; the cohort id is first-party, expiring, and respects GPC; `flights` stays aggregate with no owner joins and no searchable history; a privacy paragraph on the funding page before any grant application.

**R12 — ShareAlike propagates into derived artifacts and the licence gate keys on a field the audit found wrong in twelve places.** *Mitigation:* correct all twelve strings in Stage 0b before anything derived ships; add `share_alike` and `attribution` as machine-readable manifest fields; render slices of SA sources carry the notice; the feed catalogue gate refuses any source whose licence is not verified in `docs/LICENCES.md`.

**R13 — Upstream access revocation.** ACLED denied under EULA, IMF blocks the hosting IP range, Space-Track suspended, CelesTrak firewalled the IP. Promoting the caches as a public feed increases exposure across all sources at once. *Mitigation:* the tombstone pattern makes every refusal a visible, dated fact rather than a hidden gap; the licence gate is programmatic; `satellites` fixes its own 97% waste *before* requesting delisting, in that order.

**R14 — Grants arrive, then stop.** NLnet projects run 1–12 months; STF investments are project-scoped. *Mitigation:* spend grant money only on one-time work that permanently reduces operating burden (the rebuild, watchdog coverage, the v2 migration completing) — never on recurring costs. The $0/month baseline must remain survivable.

**R15 — Root disk fills.** 30 GB at 83% with 5.1 GB free; `/var/lib/containerd` is 7.6 GB *on root* despite `Docker Root Dir` reporting `/var/oled/docker`; Playwright already occupies 1.02 GB across two Chromium installs and `npx playwright install` does not remove prior versions. *Mitigation:* nightly assertion F; delete stale Playwright versions before adding the GIBS tile mirror; everything new goes to `/data`.

**R16 — Traffic measurement reveals a very small number and momentum collapses.** *Mitigation:* frame it correctly — the project has never been marketed, sits on a DNSBL-blocked host, has 0 stars, and its own repo omits the live frontend. Low traffic measures distribution, not quality. The N≥200 gate means a small number is explicitly "no result", not a verdict.

---

## 11. Open questions for the owner

Only the ones that genuinely change the work. Each carries a recommendation, so silence defaults to something sensible.

**Q1 — The name.** Recommendation: **earthrecord.org**, 10-year term, ~$130 one-time. `groundtruth.earth` is rejected (active company, generic term of art, and it overclaims verification the same way "twin" overclaims simulation); `worldtwin.*` is rejected (live competitor already outranking the real site, DNSBL-blocked current host, and "twin" contradicts the founding act of disabling a layer rather than faking it). **If you keep WorldTwin anyway**, take `worldtwin.org`, accept that the brand SERP is permanently ceded to `worldtwin.app`, and invest only in long-tail `/source/` SEO. The cost of deciding later rises monotonically once the RSS feed URL and the first dated permalinks exist in other people's readers and citations — which is Stage 4. **Decide by Stage 3.**

**Q2 — Which candidate layers make v1.** Recommendation: admit them in this order as each clears the gate — `nhc_cyclones` (fills the cyclone gap GDACS alone cannot), `cloudflare_radar` outages (the most genuinely state-of-the-world signal in the catalogue and almost nobody visualises it), `portwatch_chokepoints` (best info-per-byte layer at 12 KB gz), `cables` (the most visually distinctive layer in the whole catalogue, but NC+SA), `who_don`, `ucdp`. Launch at 8; stop at 12. **Silence = ship the locked 7 + country_polygons and add candidates opportunistically.**

**Q3 — Do you want the pilot at all, or straight to the full build?** Recommendation: **run the pilot.** It costs one session and 21 days of waiting and it tests the only claim in this document that could invalidate nine subsequent sessions. **Silence = run it.**

**Q4 — What happens to the 49 GB of decomposed observations at Stage 8.** They are unrecoverable — no upstream can re-serve them. Recommendation: **accept the loss and record the destroyed date range in `/charter`.** They exist to serve three static sparklines whose source datasets are all fully downloadable from upstream. **If you want them kept**, budget an extra session and ~5 GB of off-Oracle storage for a gzipped dump before the swap. **Silence = accept and record.**

**Q5 — Do you want `/legacy/` alive at all after Stage 3?** Keeping it costs one code change (the retired-state renderer), a frozen-on banner, and keeping the Cesium Ion token live and rotated. Recommendation: **keep it frozen through Stage 9**, then retire it once `Places` ships and it holds no capability v2 lacks. **If you would rather cut it now**, you save the token rotation and the layer-browser edit, and lose the deep-time scrubber and dossiers as future porting references. **Silence = freeze, retire at Stage 9.**

**Q6 — Grant applications: aggregator-as-framework, or WorldTwin-as-product?** Recommendation: **aggregator-as-framework**, at Stage 9. Sovereign Tech Fund funds "open digital base technologies" — libraries, protocols, tooling — not end-user applications, so the globe is not a fit but a provenance-preserving public-data aggregation framework plausibly is. At ~1-in-10 acceptance, two €50k applications per year is ~€10k/yr expected value, an order of magnitude above every commercial path assessed. It is also 40–60 hours per application and must follow, not precede, the artifacts a reviewer would actually read (`/charter`, `/status`, the brief archive). **Silence = defer to Stage 9 and apply as a framework.**

**Q7 — Are you willing to spend ~$130 once and ~$13/yr, and nothing else?** That is the entire recurring cost in this plan: one domain, ten years, Cloudflare free tier, Oracle Always Free, GitHub free. No CDN, no analytics service, no LLM API, no paid data. Recommendation: **yes** — the domain is load-bearing for reachability, for the emergency mitigation, and for the citation corpus. **If the answer is no**, the plan still works on `worldtwin.duckdns.org`, but you lose the school/corporate audience entirely, you have no possible blast-radius containment for a front-page moment, and the first dated permalink you publish is on an address you do not control.