# WorldTwin

🌍 **Live demo:** **http://129.151.191.74/worldtwin/**

> ⚠️ **Active development.** Things break. Some data sources rate-limit on the free tier (you'll see "no data right now" toasts when that happens). The deployment runs on a single Oracle Cloud ARM free-tier box — expect occasional restarts and slow cold boots. Bugs and rough edges are expected. The full timeline (800,000 BC → 2026), 15 mapmodes, and 65 layer toggles all work; the polish is ongoing.

**Real-time 3D global intelligence platform.**

75 data sources. 261 country profiles. 15 analytical mapmodes. Cross-source risk analysis. Live on a CesiumJS globe.

## What it does

WorldTwin aggregates open data from governments, UN agencies, satellites, and research institutions into a single interactive 3D globe. Click any country to see its intelligence profile — risk scores, economic snapshot, energy mix, trade dependencies, peer comparison, and alerts — all derived from cross-referencing multiple independent data sources.

## Architecture

```
frontend/          CesiumJS static app (no build step)
  index.html       Single-page app with inline CSS
  js/              22 JavaScript modules
  config.json      Single source of truth for all layers

aggregator/        FastAPI data aggregation service
  worldtwin/
    sources/       75 Python plugins (one per data source)
    server.py      REST API + health endpoint
    scheduler.py   Per-plugin refresh scheduler
    registry.py    Plugin auto-discovery
    cache.py       JSON disk cache

docker-compose.yml  Container orchestration
.env               API keys (not committed)
```

## Data Sources (75 plugins)

| Tier | Sources | Examples |
|------|---------|----------|
| 🥇 Gold (5) | Government/UN policy-grade | World Bank, IMF, USGS, UN Comtrade, FAO |
| 🥈 Silver (14) | Professional analysis | NASA FIRMS, UCDP, NOAA SWPC, GDACS, ENTSO-E, IDMC |
| 🥉 Bronze (5) | Context/entertainment | ESPN, Radio Browser, Windy Webcams |

32 sources need NO API key. 11 keys required for the rest (all free tier).

See [DATA_TRUST_ASSESSMENT.md](DATA_TRUST_ASSESSMENT.md) for reliability analysis of every source.

## Modes (13)

World · Weather · Nature · War · Economy · Energy · Resources · Health · Gaming · Sports · Social · Space · Pulse

## Mapmodes (15)

Political Blocs · GDP · Population · GDP/capita · Inflation · Military · Water Stress · Food Security · CO₂ · Renewable Energy · Internet · Life Expectancy · Urban · Debt · Pulse Risk

Each mapmode has a deep-dive card with relevant metrics, peer comparison, and source attribution.

## Key Features

- **Country Intelligence Engine**: Cross-references all 75 sources into per-country risk profiles (conflict, energy, food, displacement, economic, climate)
- **EU Grid Monitor**: Real-time generation by fuel type + cross-border energy flows for 19 European countries (ENTSO-E)
- **US Grid Monitor**: Hourly demand/generation for 60+ balancing authorities (EIA-930)
- **EU4-style Mapmodes**: 242 country polygons colored by any of 15 indicators, with hover alliance highlights
- **Energy Visualization**: Per-country fuel mix bars, cross-border flow arcs, renewable % coloring
- **Universal Click Cards**: Every data point shows source, date, trust tier, and related context

## Running locally

```bash
cp .env.example .env
# Fill in API keys

docker compose up -d
# Frontend at http://localhost/weather/
# API health at http://localhost/api/health
```

## Server

Oracle Cloud ARM free tier · 4 OCPU · 22 GB RAM · Oracle Linux 9.7

## Documentation

- [CATALOG.md](CATALOG.md) — Every plugin with source/auth/refresh/status
- [API_REFERENCE_VERIFIED.md](API_REFERENCE_VERIFIED.md) — Live-verified data counts
- [DATA_TRUST_ASSESSMENT.md](DATA_TRUST_ASSESSMENT.md) — Reliability + bias analysis per source
- [ARCHITECTURE.md](ARCHITECTURE.md) — System design + cleanup history
- [INTELLIGENCE_LAYER_PLAN.md](INTELLIGENCE_LAYER_PLAN.md) — Cross-source analysis design
- [GUI_LAYOUT.md](GUI_LAYOUT.md) — UI panel positioning audit

## License

Data sources retain their original licenses (see CATALOG.md). Platform code is private.
