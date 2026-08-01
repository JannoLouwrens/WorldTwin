// time/cache.js — century-bucketed LRU for historical layer data.
//
// Most historical datasets are too big to load entirely client-side
// (HYDE 3.3 gridded population is gigabytes). The aggregator slices them
// into per-century buckets keyed by (layer_id, century), and this cache
// fetches buckets lazily.
//
// API:
//   TimeCache.bucketForYear(y)       → integer century key (e.g. 1500 for 1547, -1500 for -1432)
//   TimeCache.get(layerId, year)     → Promise<bucket data> (cached after first fetch)
//   TimeCache.getRange(layerId, ya, yb)  → Promise<bucket[]> for all buckets covering a year range
//   TimeCache.preload(layerId, years)→ fire-and-forget warmup for a list of years
//   TimeCache.size()                 → diagnostic
//
// Bucketing strategy: 100-year buckets back to 1900, then 500-year, then
// 5000-year for deep paleo. This keeps bucket count bounded (~50 total
// for a layer covering 800,000 BC → 2026) while still providing fine
// granularity in the data-rich modern era.
(function(){
  const MAX_BUCKETS = 30;        // LRU eviction threshold per layer
  const _store = new Map();      // `${layerId}::${bucket}` → { data, lastUsed }
  const _inflight = new Map();   // `${layerId}::${bucket}` → Promise

  function bucketForYear(y) {
    if (y >= 1900) return Math.floor(y / 100) * 100;       // 100-year, 1900+
    if (y >= -3000) return Math.floor(y / 500) * 500;      // 500-year, -3000..1900
    return Math.floor(y / 5000) * 5000;                    // 5000-year, deep paleo
  }

  function bucketsCovering(ya, yb) {
    const out = new Set();
    out.add(bucketForYear(ya));
    out.add(bucketForYear(yb));
    // Walk 100yr increments between (rough; we only need bucket keys, so this is fine)
    let step = 100;
    if (ya < -3000 || yb < -3000) step = 5000;
    else if (ya < 1900 || yb < 1900) step = 500;
    for (let y = ya; y <= yb; y += step) out.add(bucketForYear(y));
    return [...out].sort((a, b) => a - b);
  }

  async function _fetchBucket(layerId, bucket) {
    const key = `${layerId}::${bucket}`;
    if (_store.has(key)) {
      const e = _store.get(key);
      e.lastUsed = Date.now();
      return e.data;
    }
    if (_inflight.has(key)) return _inflight.get(key);

    const url = `/api/cache/${encodeURIComponent(layerId)}_${bucket}.json`;
    const p = fetch(url)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        _store.set(key, { data, lastUsed: Date.now() });
        _evict(layerId);
        _inflight.delete(key);
        return data;
      })
      .catch(e => {
        console.warn(`[time-cache] failed ${url}:`, e);
        _inflight.delete(key);
        return null;
      });
    _inflight.set(key, p);
    return p;
  }

  function _evict(layerId) {
    const layerKeys = [..._store.keys()].filter(k => k.startsWith(layerId + '::'));
    if (layerKeys.length <= MAX_BUCKETS) return;
    layerKeys.sort((a, b) => _store.get(a).lastUsed - _store.get(b).lastUsed);
    const drop = layerKeys.slice(0, layerKeys.length - MAX_BUCKETS);
    for (const k of drop) _store.delete(k);
  }

  async function get(layerId, year) {
    return _fetchBucket(layerId, bucketForYear(year));
  }

  async function getRange(layerId, ya, yb) {
    const buckets = bucketsCovering(ya, yb);
    return Promise.all(buckets.map(b => _fetchBucket(layerId, b)));
  }

  function preload(layerId, years) {
    const buckets = new Set(years.map(bucketForYear));
    for (const b of buckets) _fetchBucket(layerId, b);
  }

  window.TimeCache = {
    bucketForYear, bucketsCovering, get, getRange, preload,
    size: () => _store.size,
    has: (layerId, year) => _store.has(`${layerId}::${bucketForYear(year)}`),
  };
})();
