// time/scrubber.js — non-linear historical timeline widget.
//
// Rendered as a fixed-bottom strip. Click anywhere or drag the handle to
// scrub time. Calls Clock.setYearLive() during drag, Clock.setYear() on commit.
//
// Why non-linear: linearly mapping 800,000 BC → 2026 means ~99.7% of the
// timeline is the Pleistocene, leaving the entirety of recorded history
// crammed into the right 0.3%. We use a piecewise-log axis: deep paleo
// gets compressed, BC gets a fair slice, AD gets the most pixels.
//
// Layout: era labels above, axis with ticks, scrubber handle, layer
// availability band underneath (dim bars showing where each enabled
// layer has data).
//
// API:
//   Scrubber.mount('#timeline')           → attach to a host element
//   Scrubber.registerLayer(id, [ya, yb])  → add an availability band
//   Scrubber.unregisterLayer(id)
//   Scrubber.setVisible(bool)
//
// Reads window.Clock for the global year.
(function(){

  // Era anchors with explicit pixel weights. Each segment claims a fraction
  // of the visible width proportional to its weight.
  // year_min, year_max, weight, label
  const ERAS = [
    [-800000, -10000, 6,  'Pleistocene'],
    [-10000,  -3000,  10, 'Neolithic'],
    [-3000,   -500,   12, 'Bronze · Iron'],
    [-500,    500,    14, 'Classical'],
    [500,     1500,   16, 'Medieval'],
    [1500,    1800,   14, 'Early Modern'],
    [1800,    1945,   14, 'Industrial'],
    [1945,    new Date().getUTCFullYear(), 14, 'Contemporary'],
  ];

  const TOTAL_WEIGHT = ERAS.reduce((s, e) => s + e[2], 0);

  function yearToFrac(year) {
    let acc = 0;
    for (const [ya, yb, w] of ERAS) {
      if (year <= ya) return acc / TOTAL_WEIGHT;
      if (year >= yb) { acc += w; continue; }
      const localT = (year - ya) / (yb - ya);
      return (acc + localT * w) / TOTAL_WEIGHT;
    }
    return 1;
  }

  function fracToYear(frac) {
    let target = frac * TOTAL_WEIGHT;
    let acc = 0;
    for (const [ya, yb, w] of ERAS) {
      if (target <= acc + w) {
        const localT = (target - acc) / w;
        return Math.round(ya + localT * (yb - ya));
      }
      acc += w;
    }
    return ERAS[ERAS.length - 1][1];
  }

  // Tick positions for each era — generated once at mount.
  function generateTicks() {
    const ticks = [];
    // Major ticks: era boundaries
    for (const [ya, , , label] of ERAS) {
      ticks.push({ year: ya, frac: yearToFrac(ya), major: true, label: Clock.label(ya), eraLabel: label });
    }
    ticks.push({ year: ERAS[ERAS.length - 1][1], frac: 1, major: true, label: Clock.label(ERAS[ERAS.length - 1][1]) });
    // Minor ticks within each era
    for (const [ya, yb] of ERAS) {
      const span = yb - ya;
      let step;
      if (span <= 200)         step = 25;
      else if (span <= 1000)   step = 100;
      else if (span <= 3000)   step = 250;
      else if (span <= 10000)  step = 1000;
      else                     step = 100000;
      for (let y = Math.ceil(ya / step) * step; y < yb; y += step) {
        if (y === ya) continue;
        ticks.push({ year: y, frac: yearToFrac(y), major: false });
      }
    }
    return ticks;
  }

  let _root = null;
  let _axis = null;
  let _handle = null;
  let _yearLabel = null;
  let _eraLabel = null;
  let _bands = null;
  const _layerBands = new Map();   // layerId → { range:[ya,yb], color }
  let _dragging = false;
  let _ready = false;

  function ensureCSS() {
    if (document.getElementById('scrubber-css')) return;
    const css = document.createElement('style');
    css.id = 'scrubber-css';
    css.textContent = `
.tw-scrubber {
  position: fixed; left: 16px; right: 16px; bottom: 14px;
  z-index: 95;
  background: var(--glass, rgba(14,19,32,0.86));
  border: 1px solid var(--border, rgba(255,255,255,0.07));
  border-radius: var(--r-md, 12px);
  backdrop-filter: var(--blur, blur(14px));
  box-shadow: var(--shadow-md, 0 8px 32px rgba(0,0,0,0.5));
  padding: 10px 14px 8px 14px;
  font-family: 'Inter', system-ui, sans-serif;
  user-select: none;
  transition: transform .25s ease, opacity .25s ease;
}
.tw-scrubber.hidden { transform: translateY(120%); opacity: 0; pointer-events: none; }
.tw-scrubber-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 6px;
}
.tw-scrubber-year {
  font-size: 18px; font-weight: 600; color: var(--text-hi, #f5f7fa);
  font-feature-settings: "tnum" 1;
  letter-spacing: 0.02em;
}
.tw-scrubber-era {
  font-size: 11px; color: var(--text-md, #b8c1d1); text-transform: uppercase;
  letter-spacing: 0.12em;
}
.tw-scrubber-controls {
  display: flex; gap: 6px;
}
.tw-scrubber-btn {
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border, rgba(255,255,255,0.08));
  color: var(--text-md, #b8c1d1);
  border-radius: 6px; padding: 3px 8px; font-size: 11px; cursor: pointer;
  font-family: inherit;
}
.tw-scrubber-btn:hover { background: rgba(255,255,255,0.12); color: var(--text-hi, #fff); }
.tw-scrubber-btn.live { border-color: #4cc2ff; color: #4cc2ff; }
.tw-axis {
  position: relative; height: 26px;
  background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
  border-radius: 4px;
  cursor: pointer;
}
.tw-tick {
  position: absolute; top: 0; bottom: 0; width: 1px;
  background: rgba(255,255,255,0.08);
}
.tw-tick.major { background: rgba(255,255,255,0.22); width: 1px; }
.tw-tick-label {
  position: absolute; bottom: -16px; transform: translateX(-50%);
  font-size: 9.5px; color: var(--text-lo, #6b7790);
  font-feature-settings: "tnum" 1; white-space: nowrap;
}
.tw-handle {
  position: absolute; top: -3px; bottom: -3px; width: 3px;
  background: #4cc2ff;
  box-shadow: 0 0 12px rgba(76,194,255,0.85), 0 0 4px rgba(76,194,255,1);
  pointer-events: none;
  border-radius: 2px;
  transition: left 0.06s linear;
}
.tw-handle::after {
  content: ''; position: absolute;
  left: 50%; top: -8px; transform: translateX(-50%);
  width: 0; height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 6px solid #4cc2ff;
}
.tw-bands {
  position: relative; height: 14px; margin-top: 22px;
  border-radius: 4px;
  background: rgba(0,0,0,0.18);
  overflow: hidden;
}
.tw-band {
  position: absolute; top: 1px; bottom: 1px;
  border-radius: 2px;
  opacity: 0.55;
}
.tw-band-empty {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 9.5px; color: var(--text-lo, #6b7790);
  letter-spacing: 0.06em; text-transform: uppercase;
  pointer-events: none;
}
.tw-era-strip {
  position: relative; height: 14px;
  display: flex; margin-bottom: 4px;
  font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em;
}
.tw-era-cell {
  display: flex; align-items: center; justify-content: center;
  color: var(--text-lo, #6b7790);
  border-right: 1px solid rgba(255,255,255,0.05);
}
.tw-era-cell:last-child { border-right: 0; }
`;
    document.head.appendChild(css);
  }

  function build(host) {
    ensureCSS();
    if (typeof host === 'string') host = document.querySelector(host);
    if (!host) {
      host = document.createElement('div');
      host.id = 'timeline';
      document.body.appendChild(host);
    }
    host.innerHTML = '';
    _root = document.createElement('div');
    _root.className = 'tw-scrubber';
    _root.innerHTML = `
      <div class="tw-scrubber-head">
        <div>
          <div class="tw-scrubber-year" id="twYear">—</div>
          <div class="tw-scrubber-era" id="twEra">—</div>
        </div>
        <div class="tw-scrubber-controls">
          <button class="tw-scrubber-btn" data-go="-100">‹‹ 100y</button>
          <button class="tw-scrubber-btn" data-go="-10">‹ 10y</button>
          <button class="tw-scrubber-btn" data-go="-1">‹</button>
          <button class="tw-scrubber-btn" data-go="1">›</button>
          <button class="tw-scrubber-btn" data-go="10">10y ›</button>
          <button class="tw-scrubber-btn" data-go="100">100y ››</button>
          <button class="tw-scrubber-btn live" data-live="1">● Live</button>
          <button class="tw-scrubber-btn" data-hide="1" title="Hide timeline (T to toggle)">✕</button>
        </div>
      </div>
      <div class="tw-era-strip" id="twEraStrip"></div>
      <div class="tw-axis" id="twAxis">
        <div class="tw-handle" id="twHandle"></div>
      </div>
      <div class="tw-bands" id="twBands">
        <div class="tw-band-empty">No layers selected — pick a layer to see availability</div>
      </div>
    `;
    host.appendChild(_root);

    _axis = _root.querySelector('#twAxis');
    _handle = _root.querySelector('#twHandle');
    _yearLabel = _root.querySelector('#twYear');
    _eraLabel = _root.querySelector('#twEra');
    _bands = _root.querySelector('#twBands');

    // Era cells
    const eraStrip = _root.querySelector('#twEraStrip');
    for (const [ya, yb, w, label] of ERAS) {
      const cell = document.createElement('div');
      cell.className = 'tw-era-cell';
      cell.style.flex = w;
      cell.textContent = label;
      cell.title = `${Clock.label(ya)} → ${Clock.label(yb)}`;
      eraStrip.appendChild(cell);
    }

    // Ticks
    const ticks = generateTicks();
    for (const t of ticks) {
      const el = document.createElement('div');
      el.className = 'tw-tick' + (t.major ? ' major' : '');
      el.style.left = (t.frac * 100) + '%';
      _axis.appendChild(el);
      if (t.major && t.label) {
        const lbl = document.createElement('div');
        lbl.className = 'tw-tick-label';
        lbl.style.left = (t.frac * 100) + '%';
        lbl.textContent = t.label;
        _axis.appendChild(lbl);
      }
    }

    // Drag/click
    function pickYearFromEvent(e) {
      const r = _axis.getBoundingClientRect();
      const x = (e.clientX !== undefined ? e.clientX : e.touches[0].clientX) - r.left;
      const frac = Math.max(0, Math.min(1, x / r.width));
      return fracToYear(frac);
    }
    _axis.addEventListener('mousedown', e => {
      _dragging = true;
      Clock.setYear(pickYearFromEvent(e));
    });
    window.addEventListener('mousemove', e => {
      if (!_dragging) return;
      Clock.setYearLive(pickYearFromEvent(e));
    });
    window.addEventListener('mouseup', () => { _dragging = false; });
    _axis.addEventListener('touchstart', e => { _dragging = true; Clock.setYear(pickYearFromEvent(e)); }, { passive: true });
    window.addEventListener('touchmove', e => { if (_dragging) Clock.setYearLive(pickYearFromEvent(e)); }, { passive: true });
    window.addEventListener('touchend', () => { _dragging = false; });

    // Step buttons
    _root.querySelectorAll('[data-go]').forEach(b => {
      b.addEventListener('click', () => {
        Clock.setYear(Clock.year + parseInt(b.dataset.go, 10));
      });
    });
    _root.querySelector('[data-live]').addEventListener('click', () => Clock.setYear(Clock.MAX_YEAR));
    _root.querySelector('[data-hide]').addEventListener('click', () => setVisible(false));

    // Keyboard
    document.addEventListener('keydown', e => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
      if (e.key === 't' || e.key === 'T') setVisible(_root.classList.contains('hidden'));
      if (e.key === 'ArrowLeft' && (e.shiftKey || e.metaKey || e.ctrlKey)) {
        Clock.setYear(Clock.year - (e.shiftKey ? 10 : 1));
      }
      if (e.key === 'ArrowRight' && (e.shiftKey || e.metaKey || e.ctrlKey)) {
        Clock.setYear(Clock.year + (e.shiftKey ? 10 : 1));
      }
    });

    Clock.subscribe(year => {
      if (!_handle) return;
      const f = yearToFrac(year);
      _handle.style.left = (f * 100) + '%';
      if (_yearLabel) _yearLabel.textContent = Clock.label(year) + (year === Clock.MAX_YEAR ? ' · Live' : '');
      if (_eraLabel) {
        const era = ERAS.find(([ya, yb]) => year >= ya && year <= yb);
        _eraLabel.textContent = era ? era[3] : '';
      }
    });

    _ready = true;
  }

  function renderBands() {
    if (!_bands) return;
    _bands.innerHTML = '';
    if (_layerBands.size === 0) {
      const e = document.createElement('div');
      e.className = 'tw-band-empty';
      e.textContent = 'No layers selected — pick a layer to see availability';
      _bands.appendChild(e);
      return;
    }
    let i = 0;
    const palette = ['#4cc2ff', '#7ad7ff', '#ff8c2a', '#ef3b3b', '#f4c84a', '#a76bff', '#34d399', '#7c8cff', '#ec4899', '#84cc16'];
    for (const [layerId, info] of _layerBands) {
      const [ya, yb] = info.range;
      const fa = yearToFrac(ya);
      const fb = yearToFrac(yb);
      const band = document.createElement('div');
      band.className = 'tw-band';
      band.style.left = (fa * 100) + '%';
      band.style.width = ((fb - fa) * 100) + '%';
      band.style.background = info.color || palette[i % palette.length];
      band.title = `${layerId} — ${Clock.label(ya)} → ${Clock.label(yb)}`;
      _bands.appendChild(band);
      i++;
    }
  }

  function registerLayer(id, range, color) {
    if (!Array.isArray(range) || range.length !== 2) return;
    _layerBands.set(id, { range, color });
    renderBands();
  }
  function unregisterLayer(id) {
    _layerBands.delete(id);
    renderBands();
  }
  function setVisible(v) {
    if (!_root) return;
    if (v) _root.classList.remove('hidden');
    else _root.classList.add('hidden');
  }

  function mount(host) {
    if (_ready) return;
    build(host);
    Clock.setYear(Clock.year, { force: true });   // initial paint
  }

  window.Scrubber = {
    mount, registerLayer, unregisterLayer, setVisible,
    yearToFrac, fracToYear,
    eras: () => ERAS.map(e => e.slice()),
  };
})();
