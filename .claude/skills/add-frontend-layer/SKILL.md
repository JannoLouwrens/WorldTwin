---
name: add-frontend-layer
description: Wire a new layer, choropleth mapmode, or mode into the WorldTwin CesiumJS frontend by editing config.json and adding a renderer in layers.js / mapmodes-data.js / modes.js. Use when asked to display a new layer, add a mapmode, or add a mode preset to the globe.
---

# Add a frontend layer / mapmode / mode

The frontend is modular vanilla JS in `frontend/`. `config.json` is the single
source of truth; `index.html` loads modules in a fixed order. Read the
"Frontend" and "Globals" sections of `ARCHITECTURE.md` before wiring, and
`GUI_LAYOUT.md` for panel placement. No build step — edit, deploy, reload.

## A new LAYER (a toggleable overlay)

1. Add an entry to `config.json` `layers[]`: `id` (must equal the cache id and
   the backend `LayerMeta.id`), envelope/`kind`, renderer name, style, and which
   `modes` it belongs to.
2. If it uses a standard `kind`, the generic renderer handles it — **no JS**.
3. For a bespoke look, add a `render`/`clear` pair in `layers.js` (core) or
   `layers2.js` (secondary), registered into `window.LAYERS`. Use the `batch()`
   helper to add many entities, and read data via `window.fetchCache(id)` /
   `window._cacheStore`.

## A new MAPMODE (a choropleth colouring of countries)

Register in `mapmodes-data.js` and add to `config.json` `mapmodes_catalog`:

```js
window.Mapmode.register({
  id: "my_index",
  name: "My Index",
  colorFn: (iso3) => {                 // return a hex string or null
    const v = getDataCache("my_source")?.countries?.[iso3]?.value;
    return v == null ? null : rampColor(v);
  },
  legend: [...], icon: "…",
});
```

**Never set per-entity colours** (1620 polygons/frame kills the framerate). The
engine reads `window.MAPMODE_COLORS` via a `CallbackProperty`; your `colorFn`
populates that map, the engine paints. For World Bank data, **never
`path.split('.')`** — indicator ids contain dots; index as
`cache.countries[iso3][indicatorId]`.

## A new MODE (a preset bundle of layers)

Add an entry to `MODES{}` in `modes.js`: the `layers` to enable, the `legend`,
and a `describe` string. Modes are just curated layer bundles surfaced on the
bottom bar.

## Traps (these have bitten)

- **Never `await` inside `batch()`** — it corrupts the `suspendEvents` /
  `resumeEvents` nesting. Fetch first, then `batch()` to render.
- The **preloader is not awaited** on boot; heavy layers lazy-fetch on toggle —
  don't assume a cache is present, call `await window.fetchCache(id)`.
- ISO3 lookups use a fallback chain (`ADM0_A3` → `ISO_A3` → …) — reuse the
  existing helper, don't reinvent country matching.
- Time-aware layers must register with `window.Scrubber` so scrubbing the
  timeline drives them.

## Deploy & verify

Use `/deploy-frontend`. Bump `?v=BUILD_ID` in `index.html` if you changed
`config.json` ids. Verify with chrome-devtools: globe renders, **0 console
errors**, the new layer/mapmode/mode actually shows.
