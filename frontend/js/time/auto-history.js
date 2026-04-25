// time/auto-history.js — auto-render historical layers when the scrubber
// crosses into the pre-modern era. Removes them again when scrubbing back
// to Live, so the modern view stays clean and uncluttered.
//
// Triggers:
//   year < 1900  → render historical_borders + historical_disasters
//   year >= 1900 → keep historical_disasters (it includes 20th century events)
//                  but only show historical_borders when era === 'antique'
//   year == MAX_YEAR (Live) → clear both
//
// Shows a brief toast each time a layer auto-loads/unloads so the user
// understands why things appeared.
(function(){
  let _bordersLoaded = false;
  let _disastersLoaded = false;
  let _toastEl = null;

  function ensureToast() {
    if (_toastEl) return _toastEl;
    const t = document.createElement('div');
    t.className = 'tw-history-toast';
    Object.assign(t.style, {
      position: 'fixed', top: '120px', left: '50%', transform: 'translateX(-50%)',
      zIndex: 90,
      background: 'rgba(14,19,32,0.92)',
      border: '1px solid rgba(76,194,255,0.4)',
      color: '#cfe6ff',
      padding: '10px 18px',
      borderRadius: '10px',
      font: '12px Inter, sans-serif',
      letterSpacing: '0.04em',
      backdropFilter: 'blur(14px)',
      boxShadow: '0 6px 24px rgba(0,0,0,0.5)',
      opacity: '0',
      transition: 'opacity .35s ease',
      pointerEvents: 'none',
      maxWidth: '600px',
      textAlign: 'center',
    });
    document.body.appendChild(t);
    _toastEl = t;
    return t;
  }
  function toast(msg, ms) {
    const t = ensureToast();
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._hideT);
    t._hideT = setTimeout(() => { t.style.opacity = '0'; }, ms || 3500);
  }

  async function autoLoad(year) {
    if (!window.LAYERS) return;
    const isLive = (year === window.Clock.MAX_YEAR);
    const wantBorders = !isLive && year < 1900;
    const wantDisasters = !isLive;

    // Borders
    if (wantBorders && !_bordersLoaded) {
      try {
        if (window.LAYERS.historical_borders?.render) {
          await window.LAYERS.historical_borders.render();
          _bordersLoaded = true;
          toast(`Historical borders enabled — viewing ${window.Clock.label(year)}`);
        }
      } catch (e) { console.warn('[auto-history] borders render failed', e); }
    } else if (!wantBorders && _bordersLoaded) {
      try {
        window.LAYERS.historical_borders?.clear?.();
        _bordersLoaded = false;
        if (isLive) toast('Welcome back to ' + window.Clock.label(year));
      } catch (_) {}
    }

    // Disasters — keep loaded for any year that's not Live
    if (wantDisasters && !_disastersLoaded) {
      try {
        if (window.LAYERS.historical_disasters?.render) {
          await window.LAYERS.historical_disasters.render();
          _disastersLoaded = true;
        }
      } catch (e) { console.warn('[auto-history] disasters render failed', e); }
    } else if (!wantDisasters && _disastersLoaded) {
      try {
        window.LAYERS.historical_disasters?.clear?.();
        _disastersLoaded = false;
      } catch (_) {}
    }
  }

  window.autoLoadHistoricalLayers = autoLoad;
})();
