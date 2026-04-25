// time-awareness-ui.js — surface "this layer cares about the timeline" in the UI.
//
// (a) Adds `data-time-aware="true"` to layer toggles and mapmode buttons that
//     subscribe to the Clock. CSS uses these attrs to dim non-time-aware
//     entries when the scrubber is away from Live.
// (b) Adds `body[data-scrubbed-past="true"]` whenever Clock.year < MAX_YEAR
//     so CSS can apply the dim treatment globally.
//
// The set of time-aware ids is captured here as the canonical truth — change
// this list when wiring a new layer to Clock.subscribe.
(function(){
  // ---- Canonical lists ----
  // Layer ids that respond to the timeline scrubber (verified via grep of
  // Clock.subscribe / window.__CURRENT_YEAR__ across frontend/js/).
  const TIME_AWARE_LAYERS = new Set([
    'noaa_co2',
    'historical_borders',
    'historical_disasters',
    'historical_wars',          // Brecke + COW + UCDP, 1400→present
    'paleo_temperature',
  ]);
  // Mapmode ids that re-paint on Clock change (from mapmodes-data.js — the
  // ones registered with `{ timeAware: true }`).
  const TIME_AWARE_MAPMODES = new Set([
    // Economic — full time series
    'gdp',            // World Bank 1960-now
    'gdp_pc',         // WB + Maddison Project (1 AD → 2018) fallback
    'population',     // WB + HYDE 3.3 (10,000 BC → 2023) fallback
    'inflation',      // IMF 1980-now
    'debt',           // World Bank 1960-now
    // Society
    'life',           // WB 1960-now (+ Clio-Infra to 1500 in Phase 5)
    'urban',          // World Bank 1960-now
    'internet',       // World Bank 1990-now
    // Environment
    'co2',            // World Bank 1960-now
    'renewable',      // OWID 1985-now
    // Threats
    'military',       // World Bank 1960-now
    // Politics
    'democracy',      // V-Dem 1789-2025
    'political',      // COW historical alliances pre-2009 + curated blocs modern
  ]);

  function tagToggles() {
    // Layer toggles use data-layer (not data-id like the layer browser)
    document.querySelectorAll('#layerToggles .lt-btn').forEach(btn => {
      const id = btn.dataset.layer;
      btn.dataset.timeAware = TIME_AWARE_LAYERS.has(id) ? 'true' : 'false';
      if (TIME_AWARE_LAYERS.has(id) && !btn.querySelector('.lt-clock')) {
        const c = document.createElement('span');
        c.className = 'lt-clock';
        c.textContent = '⏱';
        c.title = 'Time-aware: changes with the timeline scrubber';
        c.style.cssText = 'margin-left:3px;color:#a855f7;font-size:9px;opacity:.85';
        btn.appendChild(c);
      }
    });
    document.querySelectorAll('.mmbar .mmbar-btn').forEach(btn => {
      const id = btn.dataset.mm;
      btn.dataset.timeAware = TIME_AWARE_MAPMODES.has(id) ? 'true' : 'false';
    });
  }

  // Lazy-load heavy historical caches the first time the scrubber leaves Live.
  const LAZY_HISTORICAL = [
    'vdem_democracy',
    'brecke_wars',
    'clio_life_expectancy',
    'cow_alliances',
    'historical_borders',
    'historical_disasters',
  ];
  let _lazyLoaded = false;

  async function lazyLoadHistorical() {
    if (_lazyLoaded) return;
    _lazyLoaded = true;
    if (!window.fetchCache) return;
    showToast('Loading historical data…');
    const promises = LAZY_HISTORICAL.map(async (id) => {
      try {
        const data = await window.fetchCache(id);
        if (data && window.Mapmode && window.Mapmode.setDataCache) {
          window.Mapmode.setDataCache(id, data);
        }
      } catch (e) { /* fail silently */ }
    });
    await Promise.all(promises);
    if (window.Mapmode && window.Mapmode.repaint) window.Mapmode.repaint();
    showToast('Historical data ready · scrub freely', 2000);
  }

  function showToast(msg, ms) {
    let t = document.getElementById('twTimeToast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'twTimeToast';
      Object.assign(t.style, {
        position: 'fixed', top: '70px', left: '50%', transform: 'translateX(-50%)',
        zIndex: 200, background: 'rgba(168,85,247,0.18)',
        border: '1px solid rgba(168,85,247,0.4)',
        color: '#f5f7fa', padding: '7px 14px', borderRadius: '8px',
        font: '11px Inter, sans-serif', letterSpacing: '0.06em',
        backdropFilter: 'blur(14px)', boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
        opacity: '0', transition: 'opacity .3s ease', pointerEvents: 'none',
      });
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(t._h);
    t._h = setTimeout(() => { t.style.opacity = '0'; }, ms || 3000);
  }

  function updateScrubberState() {
    if (!window.Clock) return;
    const isPast = window.Clock.year !== window.Clock.MAX_YEAR;
    document.body.dataset.scrubbedPast = isPast ? 'true' : 'false';
    // First scrub away from Live → fetch historical caches
    if (isPast && !_lazyLoaded) lazyLoadHistorical();
  }

  function init() {
    // Tag now + on every DOM mutation in the bars (since they're built async)
    tagToggles();
    const lt = document.getElementById('layerToggles');
    const mm = document.getElementById('mmbar');
    if (lt) new MutationObserver(tagToggles).observe(lt, { childList: true });
    if (mm) new MutationObserver(tagToggles).observe(mm, { childList: true });

    // Subscribe to Clock for the dim toggle
    if (window.Clock) {
      updateScrubberState();
      window.Clock.subscribe(updateScrubberState);
    } else {
      setTimeout(init, 200);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 100);
  }

  // Expose so console / debugging can probe
  window.TimeAwareLayers = TIME_AWARE_LAYERS;
  window.TimeAwareMapmodes = TIME_AWARE_MAPMODES;
})();
