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
    const { label = '—', value = '—', source = '', path = '', voice = '', data_date = '', cache: cacheOverride = '' } = detail || {};
    // Allow callers (esp. openCache) to bypass SOURCE_MAP and supply a cache
    // name directly. Without this, openCache('iss', ...) lost the cache
    // because no SOURCE_MAP entry maps source==='' to cache:'iss'.
    const meta = cacheOverride
      ? { cache: cacheOverride, url: SOURCE_MAP[source]?.url || '' }
      : (SOURCE_MAP[source] || { cache: null, url: '' });
    const cacheData = meta.cache ? window._cacheStore?.get(meta.cache) : null;
    const digestRoot = window._cacheStore?.get('gemini_narrative')?.digest;
    const resolved = path ? resolvePath(digestRoot, path) : null;
    const history = findHistory(digestRoot, path);

    const fetchedAt = window._cacheStore?.get(meta.cache)?.fetched
                   || window._cacheStore?.get('gemini_narrative')?.fetched
                   || '—';

    // Compute trust tier — green if fetched in last 6h, yellow if 6-48h, red if older or null
    const fetchedDate = fetchedAt && fetchedAt !== '—' ? new Date(fetchedAt) : null;
    const ageMs = fetchedDate && !isNaN(fetchedDate) ? (Date.now() - fetchedDate.getTime()) : null;
    let tier = 'red', tierLabel = 'unknown freshness', tierDetail = 'no fetch timestamp';
    if (ageMs !== null) {
      const hours = Math.round(ageMs / 3.6e6);
      if (hours < 6)        { tier = 'green';  tierLabel = 'fresh';     tierDetail = `fetched ${hours}h ago`; }
      else if (hours < 48)  { tier = 'yellow'; tierLabel = 'recent';    tierDetail = `fetched ${hours}h ago`; }
      else                  { tier = 'red';    tierLabel = 'stale';     tierDetail = `fetched ${Math.round(hours/24)}d ago`; }
    }
    const todayUtc = new Date().toISOString().slice(0, 10);
    el.innerHTML = `
      <div class="tw-inspector-scrim"></div>
      <div class="tw-inspector-card">
        <div class="tw-inspector-head">
          <div class="tw-inspector-eyebrow">Data Inspector</div>
          <button class="tw-inspector-close" id="twInspectorClose" aria-label="Close inspector">×</button>
        </div>
        <div class="tw-inspector-trust tw-trust-${tier}" title="${escapeHtml(tierDetail)}">
          <span class="tw-trust-dot"></span>
          <span class="tw-trust-lbl">${escapeHtml(tierLabel)}</span>
          <span class="tw-trust-detail">${escapeHtml(tierDetail)}</span>
          <span class="tw-trust-today">TODAY ${todayUtc}</span>
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
          <div class="tw-inspector-row-lbl">Data date</div>
          <div class="tw-inspector-row-v">${data_date ? `<code>${escapeHtml(data_date)}</code> <span style="color:var(--brass);font-style:italic;font-size:9px;margin-left:6px">when this was measured / published</span>` : '<em>unknown</em>'}</div>
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

        <div class="tw-inspector-section tw-triangulation" id="twTriangulationSlot">
          <!-- Filled in by triangulate() if a concept matches this claim -->
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

        ${meta.cache ? `
        <div class="tw-inspector-section tw-time-travel" id="twTimeTravelSection">
          <div class="tw-inspector-section-lbl">Time travel · trace this back through history</div>
          <div class="tw-tt-row">
            <label class="tw-tt-lbl">View this layer at:</label>
            <input type="datetime-local" id="twTravelAt" class="tw-tt-input" value="${escapeHtml(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0,16))}" />
            <button id="twTravelGo" class="tw-tt-btn">Replay snapshot</button>
          </div>
          <div id="twTravelOut" class="tw-tt-out"></div>
          <div class="tw-tt-row">
            <button id="twSeriesLoad" class="tw-tt-btn tw-tt-btn-ghost">Load full history of this value</button>
            <span class="tw-tt-hint">→ /api/history/sources?prefix=${escapeHtml(meta.cache)}.</span>
          </div>
          <div id="twSeriesOut" class="tw-tt-series"></div>
        </div>` : ''}

        <div class="tw-inspector-section">
          <div class="tw-inspector-section-lbl">Raw JSON · this path</div>
          <pre class="tw-inspector-pre">${escapeHtml(fmtJson(resolved?.value ?? '(unresolved)'))}</pre>
        </div>

        ${cacheData?._sanity_warnings ? `
        <div class="tw-inspector-section tw-inspector-sanity">
          <div class="tw-inspector-section-lbl tw-inspector-sanity-lbl">Sanity warnings · ${cacheData._sanity_warnings.count} rejection${cacheData._sanity_warnings.count === 1 ? '' : 's'} this fetch</div>
          <div class="tw-inspector-sanity-note">${escapeHtml(cacheData._sanity_warnings.note || '')}</div>
          <div class="tw-inspector-sanity-list">
            ${(cacheData._sanity_warnings.rejections || []).slice(0, 8).map(r => `
              <div class="tw-inspector-sanity-row">
                <code>${escapeHtml(r.path)}</code> = <code class="tw-inspector-sanity-v">${escapeHtml(String(r.value))}</code>
                <span class="tw-inspector-sanity-rule">violates rule: ${escapeHtml(r.rule)}</span>
              </div>`).join('')}
          </div>
        </div>` : ''}

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

    // Async triangulation — fires AFTER the inspector is rendered so the user
    // gets immediate feedback. Updates the slot in-place when external
    // sources resolve.
    triangulate(meta.cache, path);

    // Wire the time-travel section. Vision: trace every claim back to the
    // instrument that measured it — at any past moment.
    if (meta.cache) wireTimeTravel(meta.cache, path, label);
  }

  // ============================================================
  // TIME TRAVEL — query /api/history/* and replay any past moment.
  // ============================================================
  async function wireTimeTravel(cacheName, path, claimLabel) {
    const goBtn = document.getElementById('twTravelGo');
    const atIn  = document.getElementById('twTravelAt');
    const out   = document.getElementById('twTravelOut');
    const sBtn  = document.getElementById('twSeriesLoad');
    const sOut  = document.getElementById('twSeriesOut');

    if (goBtn && atIn && out) {
      const replay = async (at) => {
        out.innerHTML = `<div class="tw-tt-loading">Querying ${at ? `snapshot at ${escapeHtml(at)}` : 'latest snapshot'}…</div>`;
        try {
          const r = await fetch(`/api/history/snapshot/${encodeURIComponent(cacheName)}` + (at ? `?at=${encodeURIComponent(at)}` : ''));
          if (r.status === 404) {
            out.innerHTML = at
              ? `<div class="tw-tt-empty">No snapshot at-or-before ${escapeHtml(at)} for this layer — the history store may not reach back that far.
                  <button id="twTravelLatest" class="tw-tt-btn tw-tt-btn-ghost">Replay latest snapshot instead</button></div>`
              : `<div class="tw-tt-empty">No snapshots stored yet for this layer.</div>`;
            document.getElementById('twTravelLatest')?.addEventListener('click', () => replay(''));
            return;
          }
          if (!r.ok)            { out.innerHTML = `<div class="tw-tt-err">Snapshot fetch failed: HTTP ${r.status}</div>`; return; }
          const snap = await r.json();
          // Resolve the SAME path against the historical payload — so the user
          // sees what THIS specific value was at that moment.
          const past = path ? resolvePath(snap.payload, path) : null;
          out.innerHTML = `
            <div class="tw-tt-snap-meta">
              snapshot fetched <code>${escapeHtml(snap.fetched_at)}</code>
              · ${snap.payload_kb} kB · ${snap.rows_added || 0} obs decomposed
            </div>
            ${path ? `<div class="tw-tt-past-claim">
              <span class="tw-tt-past-lbl">${escapeHtml(claimLabel || path)} at this moment:</span>
              <code class="tw-tt-past-v">${escapeHtml(fmtVal(past?.value))}</code>
            </div>` : ''}
            <pre class="tw-inspector-pre tw-tt-pre">${escapeHtml(fmtJson(snap.payload, 2400))}</pre>`;
        } catch (e) {
          out.innerHTML = `<div class="tw-tt-err">Snapshot fetch error: ${escapeHtml(String(e))}</div>`;
        }
      };
      goBtn.addEventListener('click', () => replay(atIn.value ? new Date(atIn.value).toISOString() : ''));
    }

    if (sBtn && sOut) {
      sBtn.addEventListener('click', async () => {
        sOut.innerHTML = `<div class="tw-tt-loading">Searching source_ids with prefix <code>${escapeHtml(cacheName)}.</code>…</div>`;
        try {
          const r = await fetch(`/api/history/sources?prefix=${encodeURIComponent(cacheName)}.&limit=50`);
          if (!r.ok) { sOut.innerHTML = `<div class="tw-tt-err">Sources fetch failed: HTTP ${r.status}</div>`; return; }
          const j = await r.json();
          if (!j.sources || j.sources.length === 0) {
            sOut.innerHTML = `<div class="tw-tt-empty">No decomposed series found for <code>${escapeHtml(cacheName)}</code>. The plugin probably stores its data in a shape the decomposer doesn't unpack.</div>`;
            return;
          }
          sOut.innerHTML = `
            <div class="tw-tt-section-lbl">${j.sources.length} series under <code>${escapeHtml(cacheName)}.*</code> (click to render)</div>
            <div class="tw-tt-source-list">
              ${j.sources.map(s => `<button class="tw-tt-source-btn" data-sid="${escapeHtml(s.source_id)}">
                <span class="tw-tt-sid">${escapeHtml(s.source_id.slice(cacheName.length + 1))}</span>
                <span class="tw-tt-srows">${s.count.toLocaleString()} obs</span>
                <span class="tw-tt-sspan">${escapeHtml(String(s.observed_min || '').slice(0,10))} → ${escapeHtml(String(s.observed_max || '').slice(0,10))}</span>
              </button>`).join('')}
            </div>
            <div id="twSparkOut" class="tw-tt-spark-out"></div>`;
          sOut.querySelectorAll('.tw-tt-source-btn').forEach(b => {
            b.addEventListener('click', () => loadSeriesAndRender(b.dataset.sid, document.getElementById('twSparkOut')));
          });
          // Auto-render the first one — usually what the user wants
          if (j.sources[0]) loadSeriesAndRender(j.sources[0].source_id, document.getElementById('twSparkOut'));
        } catch (e) {
          sOut.innerHTML = `<div class="tw-tt-err">Sources fetch error: ${escapeHtml(String(e))}</div>`;
        }
      });
    }
  }

  async function loadSeriesAndRender(sourceId, target) {
    if (!target) return;
    target.innerHTML = `<div class="tw-tt-loading">Loading series for <code>${escapeHtml(sourceId)}</code>…</div>`;
    try {
      const r = await fetch(`/api/history/series/${encodeURIComponent(sourceId)}?limit=400`);
      if (!r.ok) { target.innerHTML = `<div class="tw-tt-err">Series fetch failed: HTTP ${r.status}</div>`; return; }
      const j = await r.json();
      // First-pass: rows with value_num (the common case — FRED, CO2, etc.)
      let rows = (j.rows || []).filter(x => typeof x.value_num === 'number')
                                .sort((a,b) => (a.observed_at < b.observed_at ? -1 : 1));
      // Fallback: many decomposers stash the numeric in meta.{altitude_km,
      // value, lat, lon, magnitude, ...}. Try to lift one of those if
      // value_num is null. Lets us chart ISS altitude, satellite alt, etc.
      if (rows.length < 2) {
        const metaKeys = ['altitude_km','value','magnitude','severity','count','lat','lon','price','speed_kms'];
        for (const mk of metaKeys) {
          const lifted = (j.rows || []).filter(x => x.meta && typeof x.meta[mk] === 'number')
                                        .map(x => ({...x, value_num: x.meta[mk]}))
                                        .sort((a,b) => (a.observed_at < b.observed_at ? -1 : 1));
          if (lifted.length >= 2) {
            target.innerHTML = `<div class="tw-tt-section-lbl">charting <code>meta.${escapeHtml(mk)}</code> (no top-level value_num)</div>` + renderSparkline(sourceId, lifted);
            return;
          }
        }
        target.innerHTML = `<div class="tw-tt-empty">Series has ${rows.length} numeric points — too few to chart. (Total rows: ${j.count}). The decomposer stores this layer's data as text/json, not numeric.</div>`;
        return;
      }
      target.innerHTML = renderSparkline(sourceId, rows);
    } catch (e) {
      target.innerHTML = `<div class="tw-tt-err">Series fetch error: ${escapeHtml(String(e))}</div>`;
    }
  }

  function renderSparkline(sourceId, rows) {
    const W = 540, H = 120, PAD = 22;
    const xs = rows.map(r => r.observed_at);
    const ys = rows.map(r => r.value_num);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const yRange = yMax - yMin || 1;
    const n = rows.length;
    const path = rows.map((r, i) => {
      const x = PAD + (W - 2*PAD) * (i / (n - 1 || 1));
      const y = H - PAD - (H - 2*PAD) * ((r.value_num - yMin) / yRange);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
    const last = rows[rows.length - 1];
    const first = rows[0];
    const delta = last.value_num - first.value_num;
    const deltaPct = first.value_num !== 0 ? (delta / Math.abs(first.value_num)) * 100 : null;
    return `
      <div class="tw-tt-spark-head">
        <span class="tw-tt-spark-name"><code>${escapeHtml(sourceId)}</code></span>
        <span class="tw-tt-spark-stat">n=${n} · ${escapeHtml(String(xs[0]).slice(0,10))} → ${escapeHtml(String(xs[xs.length-1]).slice(0,10))}</span>
        <span class="tw-tt-spark-stat">range ${fmtNum(yMin)} → ${fmtNum(yMax)}</span>
        ${deltaPct != null ? `<span class="tw-tt-spark-delta tw-tt-${delta >= 0 ? 'up':'down'}">${delta >= 0 ? '▲' : '▼'} ${Math.abs(deltaPct).toFixed(1)}%</span>` : ''}
      </div>
      <svg viewBox="0 0 ${W} ${H}" class="tw-tt-svg" xmlns="http://www.w3.org/2000/svg">
        <rect x="0" y="0" width="${W}" height="${H}" fill="rgba(8,12,18,0.55)"/>
        <line x1="${PAD}" y1="${H-PAD}" x2="${W-PAD}" y2="${H-PAD}" stroke="rgba(176,196,219,0.18)" stroke-width="0.6"/>
        <line x1="${PAD}" y1="${PAD}" x2="${PAD}" y2="${H-PAD}" stroke="rgba(176,196,219,0.18)" stroke-width="0.6"/>
        <text x="${PAD}" y="${PAD-6}" fill="rgba(176,196,219,0.55)" font-size="9" font-family="monospace">${fmtNum(yMax)}</text>
        <text x="${PAD}" y="${H-PAD+12}" fill="rgba(176,196,219,0.55)" font-size="9" font-family="monospace">${fmtNum(yMin)}</text>
        <path d="${path}" fill="none" stroke="rgba(110,231,255,0.92)" stroke-width="1.5" stroke-linejoin="round"/>
        <circle cx="${(PAD + (W-2*PAD)).toFixed(1)}" cy="${(H - PAD - (H-2*PAD) * ((last.value_num - yMin)/yRange)).toFixed(1)}" r="2.4" fill="rgba(255,210,80,0.95)"/>
      </svg>
      <div class="tw-tt-spark-foot">
        latest <code>${fmtNum(last.value_num)}</code> at <code>${escapeHtml(String(last.observed_at).slice(0,10))}</code>
        · fetched <code>${escapeHtml(String(last.fetched_at).slice(0,19))}</code>
      </div>`;
  }

  // Triangulate the opened claim against alternative sources defined in
  // window.ConceptMap. Renders into #twTriangulationSlot.
  async function triangulate(cacheName, path) {
    const slot = document.getElementById('twTriangulationSlot');
    if (!slot || !window.ConceptMap) return;
    const concept = window.ConceptMap.findConcept(cacheName, path);
    if (!concept) {
      slot.innerHTML = '';
      return;
    }
    // Show loading immediately
    slot.innerHTML = `
      <div class="tw-inspector-section-lbl">Triangulation · ${escapeHtml(concept.label)}</div>
      <div class="tw-tri-loading">Fetching alternative sources…</div>`;

    // Resolve cached sources first
    const rows = [];
    for (const src of concept.sources) {
      const cd = window._cacheStore?.get(src.cache);
      const val = window.ConceptMap.resolvePath(cd, src.path);
      rows.push({ name: src.name, value: typeof val === 'number' ? val : null,
                  display: val == null ? '—' : (typeof val === 'number' ? fmtNum(val) : String(val)) });
    }
    // Fetch external sources in parallel
    const externalPromises = (concept.external || []).map(async ext => {
      try {
        const v = await fetchExternal(ext);
        return { name: ext.name, value: v, display: v == null ? '—' : fmtNum(v) };
      } catch (e) {
        return { name: ext.name, value: null, display: 'fetch failed', error: String(e) };
      }
    });
    const externalRows = await Promise.all(externalPromises);
    rows.push(...externalRows);

    // Compute pairwise tier badges relative to the first cached value (anchor)
    const anchor = rows.find(r => r.value != null)?.value;
    const tiered = rows.map(r => ({
      ...r,
      tier: anchor != null && r.value != null
        ? window.ConceptMap.tierFor(r.value, anchor, concept.tolerance)
        : 'unknown',
    }));
    const allGreen = tiered.length >= 2 && tiered.every(r => r.tier === 'green' || r.value == null);
    const anyRed = tiered.some(r => r.tier === 'red');
    const headerTier = anyRed ? 'red' : allGreen ? 'green' : 'yellow';

    slot.innerHTML = `
      <div class="tw-inspector-section-lbl">
        Triangulation · ${escapeHtml(concept.label)}
        <span class="tw-tri-badge tw-tri-${headerTier}">${headerTier === 'green' ? 'sources agree' : headerTier === 'yellow' ? 'close' : 'sources diverge'}</span>
      </div>
      <div class="tw-tri-table">
        ${tiered.map(r => `
          <div class="tw-tri-row tw-tri-row-${r.tier}">
            <span class="tw-tri-dot"></span>
            <span class="tw-tri-name">${escapeHtml(r.name)}</span>
            <span class="tw-tri-val">${escapeHtml(r.display)}${concept.unit ? ' ' + escapeHtml(concept.unit) : ''}</span>
          </div>`).join('')}
      </div>
      <div class="tw-tri-note">tolerance: ${concept.tolerance.pct ? `±${concept.tolerance.pct}%` : `±${concept.tolerance.abs}${concept.unit ? ' ' + concept.unit : ''}`}</div>`;
  }

  function fmtNum(v) {
    if (typeof v !== 'number') return String(v);
    if (Math.abs(v) >= 100) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return v.toFixed(Math.abs(v) < 1 ? 4 : 2);
  }

  // Fetch one external source per its definition. Currently supports JSON +
  // simple property path (e.g. "lastPrice", "bitcoin.usd") and CSV last-numeric
  // (NOAA Mauna Loa).
  async function fetchExternal(ext) {
    if (ext.extract === 'csv_last_co2') {
      const r = await fetch(ext.url);
      const txt = await r.text();
      for (const line of txt.split('\n').reverse()) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const parts = trimmed.split(',').map(s => s.trim());
        if (parts.length >= 5) {
          const v = parseFloat(parts[4]);
          if (Number.isFinite(v) && v > 0) return v;
        }
      }
      return null;
    }
    const r = await fetch(ext.url);
    if (!r.ok) return null;
    const j = await r.json();
    if (ext.extract === 'features.length') return (j.features || []).length;
    // Dot-path extract
    let cur = j;
    for (const part of String(ext.extract || '').split('.')) {
      if (cur == null) return null;
      cur = cur[part];
    }
    if (typeof cur === 'string' && /^-?\d+(\.\d+)?$/.test(cur)) return parseFloat(cur);
    return cur;
  }

  function openCache(cacheName, path) {
    open({
      label: cacheName,
      value: '—',
      source: Object.keys(SOURCE_MAP).find(k => SOURCE_MAP[k].cache === cacheName) || '',
      cache: cacheName,    // explicit override so the time-travel section always shows
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
