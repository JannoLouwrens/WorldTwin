# WorldTwin GUI Layout Audit & Target

**Generated**: 2026-04-11 · **Phase 1 deliverable** · Current overlap diagnosis + target chrome grid.

## Current state — 20 fixed panels, ad-hoc z-indices, real collisions

Extracted from `weather/index.html` `<style>` block at 2026-04-11.

| Selector | z | Top | Bottom | Left | Right | W | H |
|---|---|---|---|---|---|---|---|
| `#globe` | - | 0 | - | 0 | - | 100% | 100% |
| `#boot` | 1000 | - | - | - | - | 100% | 100% |
| `.events-ticker` | **96** | **0** | - | 0 | 0 | - | **36** |
| `.mmbar` | **96** | **0** | - | 0 | 0 | - | **36** |
| `.narrative-strip` | 94 | 36 | - | 0 | 0 | - | 32 |
| `.modes` | **100** | **20** | - | 50% | - | 96% | - |
| `.kpi-row` | 75 | 72 | - | 16 | - | - | - |
| `.legend-card` | 80 | 90 | - | - | 16 | 300 | 70vh |
| `.body-card` | 86 | 90 | - | - | 16 | 260 | - |
| `#countryCard` | 85 | 90 | - | - | 16 | 340 | 82vh |
| `.commodity-panel` | 85 | 90 | - | 16 | - | 280 | 80vh |
| `.pulse-panel` | 85 | 112 | - | 16 | - | 300 | 80vh |
| `.planet-rail` | 90 | 50% | - | 12 | - | - | 80vh |
| `.legend-strip` (bottom) | 90 | - | 20 | 50% | - | 720 | - |
| `.help-btn` | 90 | - | 20 | 20 | - | 36 | 36 |
| `.loading` | 90 | - | 20 | - | 20 | - | - |
| `.narrative-expanded` | 145 | 68 | - | 50% | - | 700 | 60vh |
| `.layer-browser` | 140 | 60 | 60 | - | 12 | 340 | - |
| `#diagnostics` | 200 | - | 70 | 16 | - | 320 | 60vh |
| `.pick-card` (modal) | 500 | - | - | - | - | - | - |

## Confirmed collisions

### 🔴 Collision A — **MMBAR vs EVENTS-TICKER** (same z:96, same top:0, same h:36)
Both the mapmode bar and the events ticker occupy **top:0–36, full width, z-index 96**. Whichever renders last paints over the other. Only one can be visible at any time.

### 🔴 Collision B — **MODES bar cuts through top strip** (z:100, top:20)
`.modes` (the mode buttons strip) is at `top: 20px, height: natural` (~48px) so it covers **y:20–68**. It overlaps:
- events-ticker (y:0–36) → modes hides bottom half of ticker
- narrative-strip (y:36–68) → modes hides top half of narrative
- mmbar (y:0–36) → modes hides bottom half of mapmode buttons

### 🔴 Collision C — **Right rail panels stack at same position**
`.legend-card`, `.body-card`, `#countryCard` all at `top:90, right:16`. When two are visible they stack at the same origin. Max one is visible per mode so in practice it's mostly fine, but it's architectural dirt.

### 🔴 Collision D — **Left rail commodity vs pulse**
`.commodity-panel` top:90 h:80vh and `.pulse-panel` top:112 h:80vh both at `left:16`. The pulse panel sits INSIDE the commodity panel's box because 112 < 90+80vh. Only one is visible at a time but again, dirt.

### 🟡 Collision E — **KPI row vs commodity panel**
`.kpi-row` at top:72 left:16 is above where `.commodity-panel` starts (top:90). They can both be visible in the same mode (resources mode has commodity filter + KPI row). KPI row is ~30px tall so 72+30=102 clears 90 barely — cramped.

### 🟢 No collision
- `#diagnostics` (z:200) is high above everything else and bottom-left.
- `#layerBrowser` (z:140) is right rail modal, conditionally visible.
- `#boot` (z:1000) is a cover overlay, only shown at startup.
- `.pick-card` (z:500) is a modal, only one at a time.
- `.planet-rail` (left:12) is a different column from everything else.

---

## Target — Chrome Grid (5 regions, flex layout, no overlap)

```
╔═════════════════════════════════════════════════════════════╗
║ TOP STRIP           (3 rows, z:90-96, h:48+36+36=120)       ║
║   ┌─────────────────────────────────────────────────────┐   ║
║   │ Row 1: Narrative strip OR Events ticker            │   ║
║   │         (one or the other, not both)               │   ║
║   ├─────────────────────────────────────────────────────┤   ║
║   │ Row 2: Mapmode bar                                 │   ║
║   ├─────────────────────────────────────────────────────┤   ║
║   │ Row 3: Always-on toggles (flights/ships/radio/etc) │   ║
║   └─────────────────────────────────────────────────────┘   ║
║                                                             ║
║ ┌──────┐                                        ┌────────┐ ║
║ │LEFT  │          GLOBE (center fills)         │ RIGHT   │ ║
║ │RAIL  │                                       │ RAIL    │ ║
║ │      │                                       │         │ ║
║ │planet│                                       │legend   │ ║
║ │s     │                                       │card OR  │ ║
║ │      │                                       │country  │ ║
║ │      │                                       │card OR  │ ║
║ │      │                                       │commodity│ ║
║ │      │                                       │pulse    │ ║
║ │      │                                       │(STACKED)│ ║
║ └──────┘                                        └────────┘ ║
║                                                             ║
║ BOTTOM STRIP  (3 rows)                                      ║
║   ┌─────────────────────────────────────────────────────┐   ║
║   │ Row 1: KPI row (mode-specific stats)               │   ║
║   ├─────────────────────────────────────────────────────┤   ║
║   │ Row 2: Legend strip (active mode color ramp)       │   ║
║   ├─────────────────────────────────────────────────────┤   ║
║   │ Row 3: Mode strip (world/weather/nature/war/...)   │   ║
║   └─────────────────────────────────────────────────────┘   ║
║                                                             ║
║ OVERLAYS (modal, z:500+)                                    ║
║   Layer Browser / Diagnostics / Pick-card / Boot splash     ║
╚═════════════════════════════════════════════════════════════╝
```

## Implementation rules (Phase 7)

1. **All fixed panels become children of 3 wrapper divs**: `#chromeTop`, `#chromeLeft`, `#chromeRight`, `#chromeBottom`. No more loose `position: fixed` per panel.
2. **Each wrapper is `position: fixed` and uses `display: flex; flex-direction: column`** (top and bottom) or `flex-direction: row` (left/right rails).
3. **Only the wrapper has a z-index.** Children inherit stacking context.
4. **Overlays (layer browser, pick-card, diagnostics, boot)** keep their own fixed positioning and use z-index 500+.
5. **Right rail is a `<div>` that shows exactly one panel at a time** — body-card, country-card, legend-card, commodity-panel, pulse-panel. A single `activePanel` variable. When you want to show a new one, you hide the others first. Zero stacking.
6. **Narrative strip and events-ticker are mutually exclusive** — one slot in Row 1 of top strip, toggled by mode.
7. **Mapmode bar and always-on toggles are always visible** in Rows 2 and 3 of top strip.

## Target z-index table (after Phase 7)

| Wrapper | Children | z | Purpose |
|---|---|---|---|
| `#chromeTop` | narrative/ticker, mmbar, always-on | 90 | Top strip |
| `#chromeLeft` | planet rail | 85 | Left rail |
| `#chromeRight` | ONE OF legend/body/country/commodity/pulse | 85 | Right rail |
| `#chromeBottom` | kpi row, legend strip, mode strip | 90 | Bottom strip |
| `#layerBrowser` | (itself) | 140 | Right-side modal |
| `#diagnostics` | (itself) | 200 | Bottom-left modal |
| `#pickCard` | (itself) | 500 | Entity click modal |
| `#boot` | (itself) | 1000 | Startup cover |

## Test plan (Phase 7)

```js
// puppeteer overlap test
const rects = await page.evaluate(() => {
  return Array.from(document.querySelectorAll('[data-chrome-panel]'))
    .map(el => ({ id: el.id, r: el.getBoundingClientRect() }));
});
function overlap(a, b) {
  return !(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top);
}
for (let i = 0; i < rects.length; i++) {
  for (let j = i+1; j < rects.length; j++) {
    if (overlap(rects[i].r, rects[j].r)) {
      console.error('OVERLAP', rects[i].id, 'vs', rects[j].id);
    }
  }
}
```

Run at 1366×768, 1600×900, 1920×1080, 2560×1440. Must print zero `OVERLAP` lines.
