# WorldTwin Architecture — current state & cleanup plan

**Generated**: 2026-04-11 · **Phase 1 deliverable**

## Infrastructure (physical / cloud)

- **Cloud**: Oracle Cloud Infrastructure, ARM free tier
- **Server**: 129.151.191.74 — Oracle Linux 9.7 aarch64, 4 OCPU, 22 GB RAM
- **Disk**: 30 GB root + 15 GB `/var/oled` (Docker storage)
- **User**: `opc`
- **SSH key**: `C:\Users\DELL\Documents\My Work\GitHub\Solo\ssh-key-2026-02-08.key`

## Two projects on one host (kept separate)

```
/home/opc/
├── openclaw-platform/          ← customer AI-agent platform (10 containers)
│   ├── docker-compose.yml       (aggregator NOT here anymore, post Phase SEPARATE)
│   ├── Caddyfile                (shared edge proxy, handles /weather* too)
│   ├── cache        → SYMLINK → /home/opc/worldtwin/cache
│   └── weather/                 (frontend static files — STILL LIVES HERE, dirt)
│       ├── index.html
│       └── js/*.js
└── worldtwin/                   ← WorldTwin globe, own compose
    ├── docker-compose.yml
    ├── .env                     (21 API keys, chmod 600)
    ├── aggregator/
    │   ├── Dockerfile
    │   └── worldtwin/           (Python package)
    │       ├── __main__.py      (uvicorn entry)
    │       ├── server.py        (FastAPI app, 13 routes)
    │       ├── registry.py      (plugin auto-discovery via pkgutil)
    │       ├── scheduler.py     (one asyncio task per plugin)
    │       ├── cache.py         (JSON disk + health mark)
    │       ├── models.py        (LayerMeta dataclass, Envelope builder)
    │       └── sources/         (72 plugin files, one LayerMeta each)
    └── cache/                   (JSON files written by scheduler, mounted into aggregator)
```

## Docker compose — two stacks, one shared network

**openclaw-platform/docker-compose.yml** runs:
- `caddy` (2-alpine) — edge reverse proxy, ports 80/443. Mounts `./Caddyfile`, `./weather`→`/srv/weather`, `./cache`→`/srv/cache` (the cache is a symlink into worldtwin).
- `admin` (custom Python) — company provisioning dashboard
- `qdrant`, `mem0-api` — shared memory layer for customer agents
- 10 × `company-*` containers — isolated OpenClaw instances, one per customer

**worldtwin/docker-compose.yml** runs:
- `aggregator` (custom Python) — the FastAPI plugin service. Attached to `openclaw-platform_frontend` external network so Caddy can proxy to it.

**Shared**:
- `openclaw-platform_frontend` Docker network (defined in openclaw-platform compose, marked external in worldtwin compose)

**This is correct separation.** ✅ Two independent compose files, two independent `.env` files, two independent image builds. A `docker compose down` in worldtwin does not touch OpenClaw containers.

## Caddy routing

```caddyfile
:80 {
    handle /weather*     { root * /srv/weather; uri strip_prefix /weather; file_server }
    handle /api/cache/*  { uri strip_prefix /api/cache; root * /srv/cache; file_server }
    handle /api/*        { reverse_proxy aggregator:8090 }
    handle /v1/cache/*   { uri strip_prefix /v1/cache; root * /srv/cache/v1; file_server }
    handle /v1/*         { reverse_proxy aggregator:8090 }
    # plus ~14 CORS /proxy/* passthroughs (opensky, gdelt, worldbank, ucdp, blitzortung, ...)
}
```

Frontend fetches fall into three buckets:
1. **`/api/cache/<id>.json`** → direct static serve from `/srv/cache` (millisecond latency)
2. **`/api/<endpoint>`** → dynamic proxy to aggregator (for /api/health, etc.)
3. **`/proxy/<vendor>/<path>`** → CORS-friendly passthrough to external APIs (used for live sub-minute data like OpenSky when direct CORS fails)

## Backend plugin pattern

```python
# sources/<id>.py
from ..models import LayerMeta
from ..registry import register

LAYER = LayerMeta(
    id="my_layer",
    name="Human Name",
    category="nature",            # see CATALOG.md for category list
    kind="raw",                   # raw / points / polygons / countries / ...
    source="Upstream name",
    source_url="https://...",
    license="CC BY 4.0",
    refresh_s=3600,               # how often to re-fetch
    initial_delay_s=30,           # boot offset
    description="...",
    requires_key=False,
    key_env=None,
    enabled=True,
)

async def fetch(client: httpx.AsyncClient):
    r = await client.get("https://upstream")
    return {"source": "...", "count": N, "items": [...]}

register(LAYER, fetch)
```

**Auto-discovery**: `registry.autodiscover()` uses `pkgutil.iter_modules` to import every `sources/*.py` at startup. Plugin self-registers at import time. Zero boilerplate beyond the three pieces above.

**Scheduler**: `scheduler.start_all()` kicks off one asyncio task per plugin. Each task is a loop `sleep(initial_delay_s); while True: fetch; sleep(refresh_s - elapsed)`. All share one `httpx.AsyncClient`.

**Cache**: `cache.write_envelope` writes normalized v1 envelope to `/cache/v1/<id>.json`. `cache.write_legacy` writes the raw legacy shape to `/cache/<id>.json`. `cache.mark_ok` / `mark_error` update `/cache/_health.json`.

## Frontend static files

```
weather/
├── index.html         (1265 lines, includes all CSS inline in a <style> block)
└── js/                (17 files, all loaded as <script src>)
    ├── icons.js       — inline SVG icons
    ├── design.js      — color ramps, point radius math
    ├── cesium-setup.js — FIRST creates the viewer (Earth, static config)
    ├── wind-canvas.js — earth.nullschool-style wind particle animation
    ├── preloader.js   — parallel fetch of 25 cache files with progress bar
    ├── planets.js     — 10-body registry, destroy+rebuild viewer for switches
    ├── layers.js      — 19 renderers (quakes/fires/cables/...) — 767 lines of per-layer code
    ├── mapmode.js     — EU4-style choropleth engine (polygons + ColorMaterialProperty)
    ├── mapmodes-data.js — 15 mapmode definitions (each with colorFn + legend)
    ├── mapmode-bar.js — top strip UI for mapmode buttons
    ├── event-glyphs.js — SVG→canvas billboard factory + 7 glyph renderers
    ├── war-hotspots.js — UCDP+GDACS-derived pulsing red country borders
    ├── layer-browser.js — right-side slide-in layer toggle panel
    ├── modes.js       — 11 mode definitions + activateMode loop
    ├── ui.js          — narrative strip + pulse panel + country card + diagnostics
    └── app.js         — click/hover handlers + boot wiring
```

No build step. No modules. Everything uses `window.*` globals. Cesium is loaded from CDN.

## Architecture verdict — current

| Aspect | State | Notes |
|---|---|---|
| Compose-level isolation | ✅ Clean | WorldTwin ≠ OpenClaw |
| Backend plugin pattern | ✅ Clean | LayerMeta + fetch + register, auto-discovered |
| Cache layer | ✅ Clean | JSON on disk, served static through Caddy |
| Secrets management | ✅ Clean | Single .env, chmod 600, never in git |
| Shared network | ✅ Clean | One named external network |
| **Frontend lives in wrong repo** | ❌ Dirt | `openclaw-platform/weather/` should be `worldtwin/frontend/` |
| **No API contract** | ❌ Missing | Plugins invent their own JSON shapes |
| **Layers.js is 767 lines of copy-paste** | ⚠ Smell | Per-layer `addEntity` calls, no abstraction |
| **Two parallel worlds** (modes vs mapmodes) | ⚠ Smell | Different cache access, different click handlers |
| **No envelope schema enforcement** | ❌ Missing | Frontend hardcodes shape assumptions |
| **No chrome grid** | ❌ Dirt | 20 fixed-position panels, z-indices 70→1000 |
| **Dead code on disk** | ⚠ Smell | `modes.js.bak.j_fix`, `world_bank.py.bak`, `*.disabled` |
| **First-boot Earth race** | ❌ Bug | cesium-setup.js vs planets.js both want to init Earth |
| **Backend/frontend schema drift** | ❌ Dirt | Plugins rename ids over time, frontend lags |

## Target architecture — after Phases 2-10

### 1. Move frontend into WorldTwin repo

```
/home/opc/worldtwin/
├── docker-compose.yml        (now includes a caddy-worldtwin service? OR keep shared edge)
├── .env
├── config.json              ← SINGLE SOURCE OF TRUTH
├── aggregator/               (unchanged)
└── frontend/                 ← NEW home for static files
    ├── index.html
    └── js/...
```

Caddy's `/weather*` handle mounts `/home/opc/worldtwin/frontend` → `/srv/worldtwin-frontend`.

The `openclaw-platform/weather` directory is deleted. Symlink `openclaw-platform/cache` removed.

### 2. Single boot path for Earth

- Delete the hand-rolled viewer setup in `cesium-setup.js`.
- `planets.js` owns the viewer. `switchToBody('earth')` is called on boot AND on planet round-trip.
- `activateMode('world')` is called from `planets.js` onReady, never from preloader directly.

### 3. Unified LayerSpec contract

```js
// config.json is fetched once at boot
window.CONFIG = await (await fetch('/weather/config.json')).json();

// layers.js becomes a dispatch table
const RENDERERS = {
  points: renderPoints,
  glyphs: renderGlyphs,
  polylines: renderPolylines,
  polygons: renderPolygons,
  arcs: renderArcs,
  grid: renderField,
  tiles: renderTileLayer,
  news_ticker: renderTickerPanel,
  country_card_data: attachCountryCard,
  tle_propagator: propagateTLEs,
  wind_canvas: runWindCanvas,
  aurora_ring: drawAuroraRing,
  meteor_ring: drawMeteorRing,
  mapmode_source: registerAsMapmode,
};

function renderLayer(layerId) {
  const spec = window.CONFIG.layers.find(l => l.id === layerId);
  if (!spec) return;
  const data = cache.get(layerId);
  const fn = RENDERERS[spec.renderer];
  fn(data, viewer, spec);
}
```

Five or six generic helpers replace 767 lines of layers.js.

### 4. One click handler

```js
// app.js
viewer.screenSpaceEventHandler.setInputAction((click) => {
  const picked = viewer.scene.pick(click.position);
  if (picked?.id?.properties?.getValue) {
    const props = picked.id.properties.getValue(viewer.clock.currentTime);
    showPickCard(props);              // universal card
    return;
  }
  // Else: country hit test
  const iso3 = findCountryAt(click.position);
  if (iso3) showCountryCard(iso3);    // mapmode mode: show value card
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);
```

### 5. Chrome grid (see GUI_LAYOUT.md)

Five divs: `#chromeTop`, `#chromeLeft`, `#chromeRight`, `#chromeBottom`, `#overlays`. All panels become children.

### 6. Schema enforcement

`registry.py` validates at register time that the plugin's declared `envelope` matches what `fetch()` returns on first successful run. Mismatch → error logged, plugin disabled.

---

## Post-cleanup verdict

| Aspect | State |
|---|---|
| Compose-level isolation | ✅ |
| Plugin pattern | ✅ |
| Cache layer | ✅ |
| Secrets | ✅ |
| Shared network | ✅ |
| Frontend location | ✅ (moved to worldtwin/frontend) |
| API contract | ✅ (config.json) |
| Frontend layer abstraction | ✅ (6 helpers) |
| Boot path | ✅ (single path) |
| Click handler | ✅ (single handler) |
| Chrome grid | ✅ (5 regions) |
| Schema enforcement | ✅ (register-time validation) |
| Dead code | ✅ (deleted in Phase 2) |

---

## Dev loop going forward

1. **Edit locally** under `C:\Users\DELL\Documents\My Work\GitHub\Solo\new_plugins\_worldtwin_snapshot\` (mirror of server state).
2. **Diff + sync** via rsync (`ssh ... "rsync ..."`). Never `sed`/heredoc on the server directly.
3. **Restart aggregator** via `docker compose restart aggregator` in worldtwin dir.
4. **Verify** via `/api/health` and Puppeteer smoke test from inside alpine-chrome container, URL `http://caddy/weather/`.
5. **Pull screenshots** to `/tmp/shots/` → local for review.
6. **Do not patch production files with inline bash** unless it's a one-character fix AND you've tested the grep-match locally first.
