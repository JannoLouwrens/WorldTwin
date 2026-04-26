# WorldTwin · Weaker & Thin Sources — Audit + Solutions

_Investigated 2026-04-26. Three parallel research agents._

> **Vision:** A lab where anyone — from the king of Rome to a sceptical citizen —
> can read the world from raw, dated, cross-checked sources instead of someone
> else's framing, and trace every claim back to the instrument that measured it.

This is the consolidated report on the 11 sources I flagged as weaker
or thin. Each entry: what we have, what's available, recommendation,
estimated effort.

---

## VERDICT MATRIX

| # | Source | Today | Verdict | Action | Effort |
|---|---|---|---|---|---|
| 1 | **WHO disease surveillance** | DON RSS only, ~37 entries | ENRICH | Add WHO GHO OData + FluNet + ProMED + ECDC | 1-2 days |
| 2 | **Cloudflare Radar** | outages + DDoS only | ENRICH | Add IQI, BGP leaks/hijacks, netflows; add RIPE Atlas + M-Lab | 1 day |
| 3 | **WRI power plants** | Static 2021 snapshot | REPLACE | GEM (assets) + Ember (generation) + ENTSO-E (EU) + Climate TRACE | 2-3 days |
| 4 | **UN Comtrade trade flows** | ~30k flows, latest year only | ENRICH | Add **CEPII BACI** bulk import (1995-2024, all HS6) | 4 hours |
| 5 | **PortWatch maritime** | 28 chokepoints + 800 ports daily | ENRICH | Paginate ArcGIS back to 2019 + UNCTAD LSCI | 4 hours |
| 6 | **Disasters (EONET+GDACS+Dartmouth)** | Live + recent only | ENRICH | **EM-DAT bulk (1900-present)** + GDACS pagination + Copernicus EMS | 1 day |
| 7 | **Open-Meteo grids** | EMPTY (broken endpoint) | ENRICH | Lattice sampler + NASA POWER + ERA5 archive (1940+) | 1 day |
| 8 | **AIS ships + flights** | Live only, no history | PARTIAL REPLACE | OpenSky academic Trino (free for student) + accept AISStream live | 1 day apply, weeks to wait |
| 9 | **OpenAQ stations** | 12k stations, no measurements | ENRICH | OpenAQ `/sensors/{id}/hours` + EEA bulk Parquet + Sentinel-5P TROPOMI | 2 days |
| 10 | **Space-Track satellites** | Snapshot of 30k objects | ENRICH | Pull `/decay` (all reentries 1957+), `/cdm_public`, `/gp_history` | half day |
| 11 | **GDELT firehose** | 24h windows sampled | ENRICH | Mirror 1979-2013 daily files + BigQuery slices for 2015+ | 1 day + ongoing |

**Net: 0 sources are genuinely HARD on free tier. Total effort ~10-15 engineering days.**

---

## DETAILED FINDINGS

### 1. WHO Disease Outbreak News — ENRICH

**Today:** WHO DON RSS gives only officially declared outbreaks (~30-50/yr, days-to-weeks lag). Our 37 entries IS the full feed.

**Free deeper sources to add:**
- **WHO GHO OData API** — `https://ghoapi.azureedge.net/api/` — 2,000+ indicators
  including mortality, immunization, NCDs. Full historical, no key.
- **WHO FluNet / FluID** — weekly influenza surveillance from ~150 labs since 1995.
  Programmatic via GHO.
- **ECDC Atlas** — `https://atlas.ecdc.europa.eu/` weekly Communicable Disease
  Threats Report + Atlas, EU-focused, free CSV.
- **ProMED-mail** — `https://promedmail.org/promed-posts/` RSS still works. Crowd-
  sourced disease reporting since 1994.
- **CDC FluView API** + **OWID COVID/MPX** GitHub CSVs — daily, historical.

**Skip:** GISAID requires registered access + data-sharing agreement. HARD.

**Win:** GHO + FluNet + ProMED + ECDC = ~1,000× more data than current DON, all free.
**Schema:** SQLite long-format `(source, disease, country, date, metric, value)`.

---

### 2. Cloudflare Radar — ENRICH

**Today:** /annotations/outages + /attacks/layer3|7 with 28-day windows. 10 outage entries.

**Untapped Cloudflare Radar endpoints (same key, 1200 req/5min):**
- `/bgp/leaks/events`, `/bgp/hijacks/events`, `/bgp/routes/stats` — routing anomalies
- `/quality/iqi/summary` and `/timeseries` — Internet Quality Index per country
  (latency, throughput, packet loss)
- `/http/summary/*` — bot/human, browser, OS, TLS share per country
- `/dns/top/locations` and `/as112` — DNS resolver patterns
- `/netflows/timeseries` — country-level traffic anomalies (great for blackout
  detection)
- `/email/security/summary` — spam/malicious email share
- `/ranking/top` — most popular domains per country

**Triangulating sources:**
- **RIPE Atlas** — 12k probes, free with credit-earn; historical built-in
  measurements queryable.
- **M-Lab** — NDT speed tests on BigQuery, free public dataset since 2009.
- **Internet Society Pulse** — aggregator with CSVs.
- **Google Transparency Report** + **NetBlocks** — outage corroboration.

**Win:** We're using ~10% of Radar. IQI + BGP + netflows are the gold layer.

---

### 3. WRI Power Plants — REPLACE

**Today:** Static 2021 snapshot, ~30k plants, nameplate-only. **WRI hasn't refreshed since 2021.**

**Modern stack:**
- **Global Energy Monitor (GEM)** — `https://globalenergymonitor.org/projects/`
  — coal, gas, oil/gas, wind, solar, nuclear, hydro, steel, bioenergy. Monthly,
  XLSX. **Replaces WRI as the canonical asset registry.**
- **Climate TRACE** (we have this in another layer) — facility-level CO2/CH4
  emissions, satellite-derived monthly, ~660M assets globally.
- **ENTSO-E Transparency Platform** — EU generation per unit, hourly since 2015.
  Free key, ~400 req/min. (We have this; can deepen.)
- **EIA Open Data** — US monthly generation per plant (Form 923). Key acquired.
- **Ember** — `https://ember-energy.org/data/` — clean monthly electricity by
  country/source, free, 80+ countries.
- **OWID Energy** — Ember+EIA+BP rolled up, GitHub CSV.
- **IRENA IRENASTAT** — annual capacity by tech/country.

**Skip:** Sentinel-5P NO2 plumes (proxy for plant activity) — heavy ML lift, HARD.

**Schema:** `plants(gem_id, name, country, lat, lon, fuel, capacity_mw, status)`
joined with `generation(gem_id_or_eia_id, period, mwh, source)`.

---

### 4. UN Comtrade — ENRICH (CEPII BACI)

**Today:** Free preview API, ~30k flows, latest year. Premium is $1k+/yr.

**Free deeper alternatives:**
- **CEPII BACI** — `https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37`
  — harmonises Comtrade into clean CSVs, ~200 countries × 5,000 HS6 products,
  **1995-2024**, free under Etalab Open Licence. Last refresh Jan 2026.
  **Single biggest unlock.** Download once (~3 GB), load to SQLite, done.
- **OEC** — same data as BACI but pre-cleaned, with rate limits.
- **WITS** (World Bank) — wraps Comtrade with tariff overlays, free.
- **IMF DOTS** — direction of trade, country-level, less granular.

**Action:** Keep Comtrade for current-year freshness. Add BACI bulk import as
the historical spine. One overnight ETL job.

---

### 5. PortWatch + AIS Maritime — ENRICH

**Today:** Live AISStream + GFW dark vessels + 28 chokepoints + 800 ports.
Latest day only.

**Deeper free data:**
- **PortWatch ArcGIS FeatureServer** supports `where`, `outFields`, `resultOffset`,
  `resultRecordCount` — paginate 2000/req back to **Jan 2019**. AIS-derived daily
  port calls + import/export tonnage estimates. Updated weekly Tuesdays 9am ET.
  Already partly implemented; need to invoke pagination loop on every fetch.
- **NOAA AccessAIS / MarineCadastre** — full historical AIS for US waters
  2009-present, ~2GB zipped CSVs, free.
- **MarineTraffic** — releases NOAA-derived data free after 6-month delay.
- **UNCTAD LSCI** (Liner Shipping Connectivity Index) — free quarterly.

**Skip:** VesselFinder, Lloyd's, S&P Commodities at Sea — all paid, $50-$5k+/mo,
no free tier worth chasing.

---

### 6. Disasters: EONET + GDACS + Dartmouth — ENRICH

**Today:** EONET 10-yr archive, GDACS current alerts, Dartmouth disabled (404).

**Massive free unlocks:**
- **EM-DAT (CRED)** — `https://www.emdat.be/` — 27,000+ disasters
  **1900-present**. THE canonical academic dataset. Open access for non-commercial,
  free account, CSV/Excel export. **The single biggest unlock for this domain.**
- **GDACS deeper API** — `gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?` —
  paginated, 100/page, archive: earthquakes/tsunamis from 2002, floods from 2006,
  cyclones from 2011. Plus per-event detail endpoint.
- **OCHA HDX** — `data.humdata.org/api/3/action/` — CKAN-based, no auth,
  thousands of disaster/humanitarian datasets.
- **Copernicus EMS** — `emergency.copernicus.eu/mapping/list-of-activations-rapid`
  — every flood/fire/quake mapped since 2012, free TIFFs/shapefiles.
- **Global Flood Database (Cloud-to-Street/Dartmouth)** on Earth Engine —
  replaces the dead Dartmouth Flood Observatory.

**Ship order:** (1) EM-DAT bulk CSV (~30k rows, trivial), (2) GDACS pagination
crawl back to 2002, (3) HDX on-demand, (4) Copernicus EMS for high-res post-event.

---

### 7. Open-Meteo weather grids — ENRICH (currently broken)

**Today:** humidity_field, pressure_field, temperature_field, noaa_sst — all
return 0 KB. The "global grid" endpoint we use doesn't exist or moved.

**Verified free path:**
- Open-Meteo is per-point: `api.open-meteo.com/v1/forecast?latitude=&longitude=`.
  No batch grid endpoint.
- Build a grid by sampling a 5°×5° lattice (~2,600 points) every 6h → 10,400
  cells/day, fits the 10,000/day non-commercial cap.
- For history: **ERA5 archive 1940→present at 0.25°/9km** at
  `archive-api.open-meteo.com/v1/archive`. Verified live.

**True gridded native sources:**
- **NOAA NOMADS GFS 0.25°** — `nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/`
  — free, key-less, GRIB.
- **NASA POWER hourly MERRA-2 since 2001 at 0.5°** —
  `power.larc.nasa.gov/docs/services/api/temporal/hourly/`. Recommended.
- **DWD ICON** — `opendata.dwd.de` — 13km global GRIB2 every 3h, free.

**Action:** Replace the broken grid endpoint with a lattice sampler + NASA POWER
canonical hourly grid. Keep ERA5 for historical replay.

---

### 8. AIS ships + flights — PARTIAL REPLACE

**Today:** Live AISStream (free) + OpenSky live states (free). No history.

**Reality:**
- **AISStream** is live-only. No paid history product.
- **VesselFinder Satellite AIS** + **MarineTraffic Historical** exist but
  enterprise-only, quote-driven, ~$$$/mo.
- **OpenSky** academic Trino/Impala archive — `opensky-network.org/data/data-licenses`
  — **free for academic / non-commercial**, depth back to 2013, ~50 TB.
  **Janno is a registered student → qualifies.** Sign up.
- **ADS-B Exchange** — full historical traces $99/mo unlimited.
- **FlightRadar24** — enterprise-only, no public price.

**Action:** Apply for OpenSky academic Trino access (one-time form). Keep
AISStream live as the only viable free AIS firehose. Accept that ship history
before now is a paid problem unless NOAA AccessAIS (US-only, free) suffices.

---

### 9. OpenAQ stations — ENRICH

**Today:** 12k stations (locations only, no measurements), key acquired.

**Deeper free:**
- **OpenAQ `/sensors/{id}/hours`** — hourly aggregates, much cheaper than
  per-measurement. Rate: 60 req/min, 2,000/hr.
- **EEA Air Quality Download Service** —
  `eeadmz1-downloads-webapp.azurewebsites.net` — bulk Parquet, hourly,
  **2013→present, all of Europe, completely free, no key**. Massive.
- **Sentinel-5P TROPOMI** — `dataspace.copernicus.eu` — global NO2/SO2/CH4 grids
  daily since 2018, free with Copernicus account.
- **WAQI** — `aqicn.org/api/` — free token for live + forecast; historical paid.

**Action:** OpenAQ for global stations (use `/hours` endpoint), EEA bulk for EU
deep history, Sentinel-5P for global gridded gases.

---

### 10. Space-Track satellites — ENRICH

**Today:** Snapshot of 30k+ active objects via `/class/gp`.

**Untapped Space-Track endpoints (same login, 30 req/min, 300/hr):**
- `/class/decay` — every reentry with date. Pull once → all reentries
  1957→present. ~30k rows, trivial.
- `/class/cdm_public` — conjunction warnings, last 7 days.
- `/class/gp_history` — full TLE history per object since launch.
- `/class/launch_site`, `/class/boxscore` — launch records.

**Triangulating:**
- **CelesTrak** group endpoints — `active`, `geo`, `starlink`, `oneweb`,
  `cubesat`, `weather`, `gps-ops`, no auth, hourly.
- **Aerospace Corp CSpOC public bulletins** — `aerospace.org/reentries` —
  reentry predictions, scrapeable.

**Action:** Pull `/decay` once, poll `/cdm_public` daily, snapshot `/gp_history`
for objects we care about.

---

### 11. GDELT — ENRICH

**Today:** GDELT 24h windows, sampled. Full firehose is 800M records since 1979.

**Free archive paths:**
- **GDELT raw 15-min CSVs** — `data.gdeltproject.org/gdeltv2/` — direct HTTP,
  no auth, no rate limit. Each 15-min slice ≈ 200 KB events + 2 MB GKG. Mirroring
  everything since GDELT 2.0 (Feb 2015) = ~75 GB/yr (events + GKG).
- **GDELT 1.0 daily files** — `data.gdeltproject.org/events/` — covers
  **1979→2013**, much smaller, ~3 GB total. **Mirror the whole thing.**
- **BigQuery** — `bigquery-public-data.gdelt` — 800M-row table, free up to
  **1 TB query/month** (≈ one full year of GKG per month).

**Action:** Mirror 1979→2013 daily files in full (~3 GB, one-shot). Keep
BigQuery for ad-hoc time-slice queries on 2015→present. Sample hourly on the
live 15-min feed for our SQLite skeleton. Full firehose mirror only if we
actually use it.

---

## RECOMMENDATIONS — by impact per hour of work

If we ship one thing tonight: **EM-DAT bulk import** — 30k disasters from 1900
to present, single CSV download, ~3 hours of work, immediately deepens disaster
history by 26 years.

If we ship five things this week, ranked by impact:

1. **EM-DAT** — 1900-present disasters
2. **CEPII BACI bulk** — 1995-2024 trade matrix
3. **OpenSky academic Trino access** — apply, then weeks of ingest
4. **WHO GHO OData** — 2,000+ health indicators with deep history
5. **GDELT 1979-2013 daily files** — 34 years of geopolitical events

If we ship the full plan, ~10-15 engineering days of focused work and the lab
moves from "live snapshot of today" to "queryable archive of measured human
civilization since 1900."

---

_Auto-archived 2026-04-26. Update when sources are deepened._
