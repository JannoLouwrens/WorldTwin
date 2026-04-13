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

  async function preload(ids, progressCb) {
    ids = ids || DEFAULT_PRELOAD;
    const total = ids.length;
    let done = 0;
    const results = { ok: 0, fail: 0 };
    const tasks = ids.map(async (id) => {
      try {
        const r = await fetch(`/api/cache/${id}.json`);
        if (r.ok) {
          const d = await r.json();
          window._cacheStore.set(id, d);
          results.ok++;
        } else {
          results.fail++;
        }
      } catch (_) {
        results.fail++;
      }
      done++;
      progressCb && progressCb(done, total, id);
    });
    await Promise.all(tasks);
    return results;
  }

  // Monkey-patch fetchCache if it exists — prefer the preloaded store
  const originalFetchCache = window.fetchCache;
  window.fetchCache = async function(id) {
    if (window._cacheStore.has(id)) {
      return window._cacheStore.get(id);
    }
    if (originalFetchCache) {
      const d = await originalFetchCache(id);
      if (d) window._cacheStore.set(id, d);
      return d;
    }
    try {
      const r = await fetch(`/api/cache/${id}.json?_=${Date.now()}`);
      if (!r.ok) return null;
      const d = await r.json();
      window._cacheStore.set(id, d);
      return d;
    } catch (_) { return null; }
  };

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
