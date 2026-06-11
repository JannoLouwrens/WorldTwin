// Boot preloader — parallel-fetch the top N cache files during boot splash
// so mode switches after boot become instant (data is already in memory).
(function(){
  const DEFAULT_PRELOAD = [
    'quakes', 'fires', 'gdacs_events', 'nhc_cyclones', 'cables',
    'flights', 'ships', 'iss', 'satellites', 'swpc_aurora',
    'trade_annual', 'country_resources', 'country_deep_dive',
    'portwatch_chokepoints', 'wri_power_plants',
    'ucdp_ged', 'wikidata_battles', 'gdelt_gkg_themes', 'global_events',
    'pulse_mode', 'commodity_prices', 'cloudflare_radar',
    'volcanoes', 'population', 'wind_sample'
  ];

  // Shared cache store. fetchCache (in layers.js) reads from here first.
  window._cacheStore = window._cacheStore || new Map();

  // Per-fetch hard cap so one slow upstream never stalls the splash.
  // The whole preload also has an outer wall-clock cap so the splash
  // always hides within a bounded time even if many fetches stall.
  // Per-fetch timeout is long enough that every healthy cache fetches
  // even on a slow connection — only a genuinely stuck request aborts.
  // The outer budget hides the splash on time; aborted fetches just mean
  // they'll be re-fetched on demand via fetchCache below.
  const PER_FETCH_TIMEOUT_MS = 30000;
  const TOTAL_PRELOAD_BUDGET_MS = 8000;

  async function preload(ids, progressCb) {
    ids = ids || DEFAULT_PRELOAD;
    const total = ids.length;
    let done = 0;
    const results = { ok: 0, fail: 0, timedOut: 0 };

    const fetchOne = async (id) => {
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), PER_FETCH_TIMEOUT_MS);
      try {
        const r = await fetch(`/api/cache/${id}.json`, { signal: ctrl.signal });
        if (r.ok) {
          const d = await r.json();
          window._cacheStore.set(id, d);
          results.ok++;
        } else {
          results.fail++;
        }
      } catch (e) {
        if (e && e.name === 'AbortError') results.timedOut++;
        else results.fail++;
      } finally {
        clearTimeout(to);
        done++;
        progressCb && progressCb(done, total, id);
      }
    };

    // Outer budget: race the full set against a wall clock so the splash
    // always proceeds. Layers that miss the budget keep loading in the
    // background and will populate _cacheStore when they arrive — every
    // fetchOne writes to the store on success regardless of the race.
    const all = Promise.all(ids.map(fetchOne));
    const budget = new Promise(res => setTimeout(res, TOTAL_PRELOAD_BUDGET_MS));
    await Promise.race([all, budget]);
    return results;
  }

  // NOTE: window.fetchCache is owned by layers.js (loads after this file) —
  // it is store-first against window._cacheStore with in-flight dedupe.
  // The monkey-patch that used to live here was dead code: layers.js
  // overwrote it at load time anyway.

  // Background refresh — every 2 minutes, re-fetch the fast-moving layers
  const FAST = ['quakes','flights','ships','iss','global_events','gdacs_events','wind_sample','commodity_prices','gdelt_gkg_themes'];
  setInterval(async () => {
    for (const id of FAST) {
      try {
        const r = await fetch(`/api/cache/${id}.json?_=${Date.now()}`);
        if (r.ok) window._cacheStore.set(id, await r.json());
      } catch (_) {}
    }
  }, 120000);

  window.Preloader = { preload, store: window._cacheStore };
})();
