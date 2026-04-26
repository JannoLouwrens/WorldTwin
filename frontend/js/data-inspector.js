// data-inspector.js — global "drill into the data" overlay.
//
// Threads the user's vision: ANY claim, anywhere on the page, must be
// drillable to its source. Council citations, KPI sparklines, dossier
// numbers, hover-tooltip values — they all open this inspector with
// the same UX: cache name, raw JSON path, current value, source URL,
// fetch timestamp, and a 5-sample history if the cache stores series.
//
// Public API:
//   DataInspector.open({ label, value, source, path, voice? })
//   DataInspector.openCache(cacheName, jsonPointer?)
//   DataInspector.close()
//
// The inspector is non-modal — globe stays interactive, escape closes.
(function(){
  let _el = null;

  function ensureMount() {
    if (_el) return _el;
    const el = document.createElement('aside');
    el.id = 'twDataInspector';
    el.className = 'tw-inspector has-gnomons-4';
    el.setAttribute('aria-hidden', 'true');
    document.body.appendChild(el);
    el.addEventListener('click', (e) => {
      if (e.target.id === 'twInspectorClose' || e.target.classList.contains('tw-inspector-scrim')) {
        close();
      }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') close();
    });
    _el = el;
    return el;
  }

  // Resolve a JSON pointer like "chokepoints[0].ships_today" or
  // "macros[2].latest" against a cache object.
  function resolvePath(obj, path) {
    if (!obj || !path) return undefined;
    // Normalize: "a.b[0].c" → ["a","b","0","c"]
    const parts = String(path).replace(/\[(\w+)\]/g, '.$1').split('.').filter(Boolean);
    let cur = obj;
    const trail = [];
    for (const p of parts) {
      trail.push(p);
      if (cur == null) return { value: undefined, trail, found: false };
      cur = cur[p];
    }
    return { value: cur, trail, found: true };
  }

  // Map source name strings (the model writes these) to cache id + url.
  const SOURCE_MAP = {
    'PortWatch':   { cache: 'portwatch_chokepoints', url: 'https://portwatch.imf.org/' },
    'FRED':        { cache: 'fred',                  url: 'https://fred.stlouisfed.org/' },
    'UCDP':        { cache: 'ucdp_ged',              url: 'https://ucdp.uu.se/' },
    'GDACS':       { cache: 'gdacs_events',          url: 'https://www.gdacs.org/' },
    'USGS':        { cache: 'quakes',                url: 'https://earthquake.usgs.gov/' },
    'NHC':         { cache: 'nhc_cyclones',          url: 'https://www.nhc.noaa.gov/' },
    'Pulse':       { cache: 'pulse_mode',            url: 'internal — composite of multiple sources' },
    'WHO':         { cache: 'who_don',               url: 'https://www.who.int/emergencies/disease-outbreak-news' },
    'DONKI':       { cache: 'nasa_donki',            url: 'https://kauai.ccmc.gsfc.nasa.gov/DONKI/' },
    'SWPC':        { cache: 'swpc_aurora',           url: 'https://www.swpc.noaa.gov/' },
    'Cloudflare':  { cache: 'cloudflare_radar',      url: 'https://radar.cloudflare.com/' },
    'GFW':         { cache: 'gfw_events',            url: 'https://globalfishingwatch.org/' },
    'Wikidata':    { cache: 'wikidata_battles',      url: 'https://query.wikidata.org/' },
    'FAO':         { cache: 'fao_food_prices',       url: 'https://www.fao.org/worldfoodsituation/foodpricesindex/en/' },
    'EIA':         { cache: 'eia_petroleum',         url: 'https://www.eia.gov/' },
    'IMF':         { cache: 'imf_data',              url: 'https://data.imf.org/' },
    'OECD':        { cache: 'oecd_cli',              url: 'https://data.oecd.org/leadind/composite-leading-indicator-cli.htm' },
    'CoinGecko':   { cache: 'economy',               url: 'https://www.coingecko.com/' },
    'Binance':     { cache: 'economy',               url: 'https://www.binance.com/en/markets' },
    'NOAA':        { cache: 'noaa_co2',              url: 'https://gml.noaa.gov/ccgg/trends/' },
    'V-Dem':       { cache: 'vdem_democracy',        url: 'https://v-dem.net/' },
    'World Bank':  { cache: 'world_bank',            url: 'https://data.worldbank.org/' },
    'Comtrade':    { cache: 'country_resources',     url: 'https://comtradeplus.un.org/' },
  };

  function fmtVal(v) {
    if (v == null) return 'null';
    if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(4);
    if (typeof v === 'string') return v.length > 200 ? v.slice(0, 200) + '…' : v;
    if (Array.isArray(v)) return `[Array · ${v.length} items]`;
    if (typeof v === 'object') return '{Object · ' + Object.keys(v).length + ' keys}';
    return String(v);
  }
  function fmtJson(v, max = 1200) {
    try {
      const s = JSON.stringify(v, null, 2);
      return s.length > max ? s.slice(0, max) + '\n…[truncated]' : s;
    } catch { return String(v); }
  }
  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // Try to find a series of historical samples for this path.
  function findHistory(cache, path) {
    if (!cache || !path) return null;
    // For FRED-style series: path like "macros[2].latest" — the parent
    // typically has a .series array. Walk up one level.
    const parts = String(path).replace(/\[(\w+)\]/g, '.$1').split('.').filter(Boolean);
    if (parts.length < 2) return null;
    const parentPath = parts.slice(0, -1).join('.');
    const r = resolvePath(cache, parentPath);
    const parent = r?.value;
    if (parent && Array.isArray(parent.series)) {
      return parent.series.slice(-8).map(s => ({ t: s.t, v: s.v }));
    }
    if (parent && Array.isArray(parent.history)) {
      return parent.history.slice(-8);
    }
    return null;
  }

  function open(detail) {
    ensureMount();
    const el = _el;
    const { label = '—', value = '—', source = '', path = '', voice = '' } = detail || {};
    const meta = SOURCE_MAP[source] || { cache: null, url: '' };
    const cacheData = meta.cache ? window._cacheStore?.get(meta.cache) : null;
    const digestRoot = window._cacheStore?.get('gemini_narrative')?.digest;
    const resolved = path ? resolvePath(digestRoot, path) : null;
    const history = findHistory(digestRoot, path);

    const fetchedAt = window._cacheStore?.get(meta.cache)?.fetched
                   || window._cacheStore?.get('gemini_narrative')?.fetched
                   || '—';

    el.innerHTML = `
      <div class="tw-inspector-scrim"></div>
      <div class="tw-inspector-card">
        <div class="tw-inspector-head">
          <div class="tw-inspector-eyebrow">Data Inspector</div>
          <button class="tw-inspector-close" id="twInspectorClose" aria-label="Close inspector">×</button>
        </div>

        <div class="tw-inspector-claim">
          <div class="tw-inspector-claim-lbl">${escapeHtml(label)}</div>
          <div class="tw-inspector-claim-v">${escapeHtml(value)}</div>
          <div class="tw-inspector-claim-meta">
            <span class="tw-inspector-claim-src">${escapeHtml(source) || 'unknown source'}</span>
            ${voice ? `<span class="tw-inspector-claim-voice">cited by · ${escapeHtml(voice)}</span>` : ''}
          </div>
        </div>

        <div class="tw-inspector-row">
          <div class="tw-inspector-row-lbl">Cache</div>
          <div class="tw-inspector-row-v">${meta.cache ? `<code>${escapeHtml(meta.cache)}.json</code>` : '<em>unmapped</em>'}</div>
        </div>
        <div class="tw-inspector-row">
          <div class="tw-inspector-row-lbl">JSON path</div>
          <div class="tw-inspector-row-v"><code>${escapeHtml(path) || '—'}</code></div>
        </div>
        <div class="tw-inspector-row">
          <div class="tw-inspector-row-lbl">Resolved value</div>
          <div class="tw-inspector-row-v"><code>${escapeHtml(fmtVal(resolved?.value))}</code></div>
        </div>
        <div class="tw-inspector-row">
          <div class="tw-inspector-row-lbl">Source</div>
          <div class="tw-inspector-row-v">${meta.url
            ? `<a href="${escapeHtml(meta.url)}" target="_blank" rel="noopener">${escapeHtml(meta.url)} ↗</a>`
            : '—'}</div>
        </div>
        <div class="tw-inspector-row">
          <div class="tw-inspector-row-lbl">Fetched</div>
          <div class="tw-inspector-row-v"><code>${escapeHtml(fetchedAt)}</code></div>
        </div>

        ${history && history.length ? `
        <div class="tw-inspector-section">
          <div class="tw-inspector-section-lbl">Recent samples</div>
          <div class="tw-inspector-history">
            ${history.map(h => `<div class="tw-inspector-sample">
              <span class="tw-inspector-sample-t">${escapeHtml((h.t || h.year || '—').toString().slice(0, 10))}</span>
              <span class="tw-inspector-sample-v">${escapeHtml(fmtVal(h.v ?? h.value ?? h))}</span>
            </div>`).join('')}
          </div>
        </div>` : ''}

        <div class="tw-inspector-section">
          <div class="tw-inspector-section-lbl">Raw JSON · this path</div>
          <pre class="tw-inspector-pre">${escapeHtml(fmtJson(resolved?.value ?? '(unresolved)'))}</pre>
        </div>

        ${cacheData ? `
        <div class="tw-inspector-section">
          <div class="tw-inspector-section-lbl">Cache root · ${escapeHtml(meta.cache)} · top keys</div>
          <pre class="tw-inspector-pre">${escapeHtml(Object.keys(cacheData).map(k => '  ' + k).join('\n'))}</pre>
        </div>` : ''}

        <div class="tw-inspector-foot">
          <span class="tw-inspector-hint">Press <kbd>Esc</kbd> to close</span>
        </div>
      </div>`;
    el.classList.add('tw-inspector-open');
    el.setAttribute('aria-hidden', 'false');
  }

  function openCache(cacheName, path) {
    open({
      label: cacheName,
      value: '—',
      source: Object.keys(SOURCE_MAP).find(k => SOURCE_MAP[k].cache === cacheName) || '',
      path: path || '',
    });
  }

  function close() {
    if (!_el) return;
    _el.classList.remove('tw-inspector-open');
    _el.setAttribute('aria-hidden', 'true');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureMount);
  } else {
    ensureMount();
  }

  window.DataInspector = { open, openCache, close, SOURCE_MAP };
})();
