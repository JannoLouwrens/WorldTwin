// UI panels: legend strip, legend card, country card, commodity filter, ticker.
(function(){

  // ============= LEGEND STRIP =============
  function setLegendStrip(legend, describe) {
    const strip = document.getElementById('legendStrip');
    if (!legend) { strip.style.display = 'none'; return; }
    strip.style.display = 'flex';
    document.getElementById('lgLabel').textContent = legend.title;

    const rampEl = document.getElementById('lgRamp');
    const minEl = document.getElementById('lgMin');
    const maxEl = document.getElementById('lgMax');

    if (legend.categorical && Array.isArray(legend.swatches)) {
      // Categorical: render colored dots + labels, hide min/max
      minEl.textContent = '';
      maxEl.textContent = '';
      rampEl.style.background = 'transparent';
      rampEl.style.width = 'auto';
      rampEl.style.display = 'flex';
      rampEl.style.flexWrap = 'wrap';
      rampEl.style.gap = '8px';
      rampEl.innerHTML = legend.swatches.map(s =>
        '<span style="display:inline-flex;align-items:center;gap:4px;font-size:10px;color:var(--text-md);white-space:nowrap">' +
          '<span style="width:10px;height:10px;border-radius:50%;background:' + s.color + ';box-shadow:0 0 4px ' + s.color + '80;flex-shrink:0"></span>' +
          '<span>' + s.label + '</span>' +
        '</span>'
      ).join('');
    } else {
      // Continuous: gradient bar + min/max labels
      minEl.textContent = legend.min || '—';
      maxEl.textContent = legend.max || '—';
      rampEl.innerHTML = '';
      rampEl.style.display = 'block';
      rampEl.style.width = '200px';
      rampEl.style.height = '8px';
      rampEl.style.borderRadius = '4px';
      const ramp = DS.ramps[legend.ramp] || DS.ramps.bad;
      rampEl.style.background = 'linear-gradient(90deg, ' + ramp.join(', ') + ')';
    }

    // Mode dot
    const mode = window.currentModeId ? window.currentModeId() : 'world';
    const hue = DS.modeHue[mode] || DS.modeHue.world;
    document.getElementById('lgDot').style.color = hue;
    document.getElementById('lgDot').style.background = hue;
    // Freshness
    updateFreshness();
  }
  async function updateFreshness() {
    try {
      const r = await fetch('/api/health');
      if (!r.ok) return;
      const d = await r.json();
      const layers = d.layers || {};
      // Find most recent fetch among any layer
      let latest = 0;
      Object.values(layers).forEach(l => {
        if (l.last_fetch) {
          const t = new Date(l.last_fetch).getTime();
          if (t > latest) latest = t;
        }
      });
      if (latest > 0) {
        document.getElementById('lgFreshness').textContent = DS.fmtRelTime(new Date(latest).toISOString());
      }
    } catch (_) {}
  }
  setInterval(updateFreshness, 30000);

  // ============= KPI ROW =============
  async function updateKpiRow(modeId) {
    const row = document.getElementById('kpiRow');
    row.innerHTML = '';
    try {
      const r = await fetch('/api/health');
      const d = await r.json();
      const layers = d.layers || {};
      let items = [];
      if (modeId === 'world') {
        items = [
          ['Quakes (2h)', layers.quakes?.count || 0],
          ['Fires (10 min)', layers.fires?.count || 0],
          ['Flights', layers.flights?.count || 0],
          ['Ships', layers.ships?.count || 0],
          ['News themes', layers.gdelt_gkg_themes?.count || 0],
        ];
      } else if (modeId === 'nature') {
        items = [
          ['Quakes', layers.quakes?.count || 0],
          ['Fires', layers.fires?.count || 0],
          ['Volcanoes', layers.volcanoes?.count || 0],
          ['Disasters', layers.disasters?.count || 0],
        ];
      } else if (modeId === 'war') {
        items = [
          ['UCDP events', layers.ucdp_ged?.count || 0],
          ['Battles (Wikidata)', layers.wikidata_battles?.count || 0],
          ['Conflict events (GDELT)', layers.conflict_events?.count || 0],
          ['GKG themes', layers.gdelt_gkg_themes?.count || 0],
        ];
      } else if (modeId === 'economy' || modeId === 'resources') {
        items = [
          ['Trade flows', layers.trade_annual?.count || 0],
          ['Chokepoints', layers.portwatch_chokepoints?.count || 0],
          ['Power plants', layers.wri_power_plants?.count || 0],
          ['Countries', layers.country_resources?.count || 0],
        ];
      } else if (modeId === 'space') {
        items = [
          ['Satellites', layers.satellites?.count || 0],
          ['Aurora (active pts)', layers.swpc_aurora?.count || 0],
        ];
      } else if (modeId === 'social') {
        items = [
          ['GKG themes', layers.gdelt_gkg_themes?.count || 0],
          ['Wikipedia trends', layers.trends?.count || 0],
          ['News velocity', layers.news?.count || 0],
        ];
      }
      items.forEach(([lbl, val]) => {
        const el = document.createElement('div');
        el.className = 'kpi';
        el.innerHTML = `${lbl} <strong>${DS.fmt(val,0)}</strong>`;
        row.appendChild(el);
      });
    } catch (_) {}
  }

  // ============= LOADING INDICATOR =============
  function showLoading(show, text='LOADING') {
    const el = document.getElementById('loading');
    if (show) {
      document.getElementById('loadingText').textContent = text;
      el.classList.add('show');
    } else {
      el.classList.remove('show');
    }
  }

  // ============= LEGEND CARD =============
  function showLegendCard(title, bodyHtml) {
    document.getElementById('lcTitle').textContent = title;
    document.getElementById('lcBody').innerHTML = bodyHtml;
    document.getElementById('legendCard').classList.add('show');
  }
  function hideLegendCard() { document.getElementById('legendCard').classList.remove('show'); }
  document.getElementById('lcClose').addEventListener('click', hideLegendCard);

  // NOTE: Old country card (showCountryCard / hideCountryCard) was removed
  // 2026-04-25 — superseded by dossier.js which composes 8 caches into one panel.

  // ============= COUNTRY CARD (REMOVED) =============

  // ============= COMMODITY FILTER =============
  let _commoditiesData = null;
  async function loadCommodities() {
    if (_commoditiesData) return _commoditiesData;
    // Read from trade_annual payload which bundles categories & commodities
    const r = await fetch('/api/cache/trade_annual.json');
    if (!r.ok) return null;
    const d = await r.json();
    _commoditiesData = { categories: d.categories || [], commodities: d.commodities || [] };
    return _commoditiesData;
  }

  async function showCommodityFilter() {
    const panel = document.getElementById('commodityPanel');
    const cats = document.getElementById('cpCats');
    const data = await loadCommodities();
    if (!data) {
      panel.innerHTML = '<h3>Filter by Resource</h3><div style="color:var(--text-lo);font-size:11px">Trade data not yet loaded…</div>';
      panel.classList.add('show');
      return;
    }
    cats.innerHTML = '';
    data.categories.forEach(cat => {
      const catCommodities = data.commodities.filter(c => c.category === cat.id);
      if (!catCommodities.length) return;
      const block = document.createElement('div');
      block.className = 'cp-cat';
      block.innerHTML = `
        <div class="cp-cat-head"><span class="dot" style="color:${cat.color};background:${cat.color}"></span>${cat.name}</div>
        <div class="cp-items">${catCommodities.map(c => `<div class="cp-item" data-commodity="${c.id}">${c.name}</div>`).join('')}</div>
      `;
      cats.appendChild(block);
    });
    // Bind click handlers
    cats.querySelectorAll('.cp-item').forEach(el => {
      el.addEventListener('click', () => {
        document.querySelectorAll('.cp-item, .cp-all').forEach(x => x.classList.remove('active'));
        el.classList.add('active');
        const commodity = el.dataset.commodity;
        window.LAYERS.trade_annual.render(commodity);
      });
    });
    document.getElementById('cpAll').addEventListener('click', () => {
      document.querySelectorAll('.cp-item, .cp-all').forEach(x => x.classList.remove('active'));
      document.getElementById('cpAll').classList.add('active');
      window.LAYERS.trade_annual.render(null);
    });
    // Search filter
    document.getElementById('cpSearch').addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      cats.querySelectorAll('.cp-item').forEach(el => {
        el.style.display = el.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
    panel.classList.add('show');
  }
  function hideCommodityFilter() { document.getElementById('commodityPanel').classList.remove('show'); }

  // ============= TICKER STRIP =============
  async function showTicker() {
    const strip = document.getElementById('tickerStrip');
    const inner = document.getElementById('tickerInner');
    try {
      const r = await fetch('/api/cache/commodity_prices.json');
      if (!r.ok) { strip.classList.remove('show'); return; }
      const d = await r.json();
      const items = d.items || [];
      if (!items.length) { strip.classList.remove('show'); return; }
      // Build ticker repeating 2x so it loops smoothly
      const build = () => items.map(it => `
        <span class="ticker-item">
          <span class="sym">${it.symbol}</span>
          <span class="px">$${DS.fmt(it.price, 2)}</span>
          <span class="unit">${it.unit}</span>
        </span>
      `).join('');
      inner.innerHTML = build() + build();
      strip.classList.add('show');
    } catch (_) { strip.classList.remove('show'); }
  }
  function hideTicker() { document.getElementById('tickerStrip').classList.remove('show'); }

  // ============= EXPORT =============
  window.setLegendStrip = setLegendStrip;
  window.updateKpiRow = updateKpiRow;
  window.showLoading = showLoading;
  window.showCommodityFilter = showCommodityFilter;
  window.hideCommodityFilter = hideCommodityFilter;
  window.showTicker = showTicker;
  window.hideTicker = hideTicker;
  window.showLegendCard = showLegendCard;
  window.hideLegendCard = hideLegendCard;

  // ============= NARRATIVE STRIP (Gemini analyst) =============
  async function refreshNarrative() {
    try {
      const r = await fetch('/api/cache/gemini_narrative.json?_=' + Date.now());
      if (!r.ok) return;
      const d = await r.json();
      const text = document.getElementById('narrativeText');
      if (text && d.today) text.textContent = d.today;
      const body = document.getElementById('neBody');
      if (body) {
        body.innerHTML = `
          <h4>Today at a Glance</h4>
          <p>${(d.today || '—').replace(/</g, '&lt;')}</p>
          <h4>Biggest Risk</h4>
          <p>${(d.biggest_risk || '—').replace(/</g, '&lt;')}</p>
          <h4>Trend of the Week</h4>
          <p>${(d.trend_of_week || '—').replace(/</g, '&lt;')}</p>
          <p style="font-size:9px;color:var(--text-lo);margin-top:14px;text-align:right">Generated by Gemini 2.5 Flash · Updated ${DS.fmtRelTime(d.fetched)}</p>
        `;
      }
    } catch (e) { console.warn('[narrative]', e); }
  }
  setInterval(refreshNarrative, 300000);
  setTimeout(refreshNarrative, 4000);
  document.getElementById('narrativeText')?.addEventListener('click', () => {
    document.getElementById('narrativeExpanded')?.classList.add('show');
  });
  document.getElementById('neClose')?.addEventListener('click', () => {
    document.getElementById('narrativeExpanded')?.classList.remove('show');
  });

  // ============= EVENTS TICKER =============
  async function refreshEventsTicker() {
    try {
      const r = await fetch('/api/cache/global_events.json?_=' + Date.now());
      if (!r.ok) return;
      const d = await r.json();
      const events = d.events || [];
      if (!events.length) return;
      const inner = document.getElementById('etInner');
      if (!inner) return;
      // Render twice for seamless loop
      const build = () => events.slice(0, 40).map(e => {
        const sev = Math.max(1, Math.min(5, e.severity || 1));
        const ago = DS.fmtRelTime(e.time);
        const title = (e.title || '').replace(/</g, '&lt;').slice(0, 120);
        return `
          <span class="et-item" data-lat="${e.lat || 0}" data-lon="${e.lon || 0}">
            <span class="sev sev-${sev}"></span>
            <span class="type">${(e.type || '').toUpperCase()}</span>
            <span>${title}</span>
            <span class="ago">${ago}</span>
          </span>
        `;
      }).join('');
      inner.innerHTML = build() + build();
      // Click-to-fly
      inner.querySelectorAll('.et-item').forEach(el => {
        el.addEventListener('click', () => {
          const lat = parseFloat(el.dataset.lat);
          const lon = parseFloat(el.dataset.lon);
          if (!isNaN(lat) && !isNaN(lon) && lat && lon && window.viewer) {
            window.viewer.camera.flyTo({
              destination: Cesium.Cartesian3.fromDegrees(lon, lat, 2500000),
              duration: 2.5,
              easingFunction: Cesium.EasingFunction.QUINTIC_IN_OUT,
            });
          }
        });
      });
    } catch (e) { console.warn('[ticker]', e); }
  }
  setInterval(refreshEventsTicker, 120000);  // every 2 min
  setTimeout(refreshEventsTicker, 2500);

  // ============= PULSE PANEL =============
  async function refreshPulsePanel() {
    try {
      const r = await fetch('/api/cache/pulse_mode.json?_=' + Date.now());
      if (!r.ok) return;
      const d = await r.json();
      const list = document.getElementById('pulseList');
      if (!list) return;
      const countries = d.top_concerning || [];
      list.innerHTML = countries.slice(0, 30).map(c => {
        const s = c.composite || 0;
        let hex = '#22c55e', bg = 'rgba(34,197,94,0.15)';
        if (s >= 70) { hex = '#ef3b3b'; bg = 'rgba(239,59,59,0.2)'; }
        else if (s >= 50) { hex = '#fb923c'; bg = 'rgba(251,146,60,0.18)'; }
        else if (s >= 30) { hex = '#fbbf24'; bg = 'rgba(251,191,36,0.15)'; }
        const flag = window.flagEmoji ? window.flagEmoji(c.iso3) : '';
        return `
          <div class="pp-row">
            <span class="flag">${flag}</span>
            <span class="name">${c.name || c.iso3}</span>
            <span class="score" style="background:${bg};color:${hex}">${s}</span>
          </div>
        `;
      }).join('') || '<div style="color:var(--text-lo);font-size:11px">No data yet…</div>';
    } catch (e) { console.warn('[pulse]', e); }
  }
  setInterval(refreshPulsePanel, 300000);
  setTimeout(refreshPulsePanel, 3000);
  window.refreshPulsePanel = refreshPulsePanel;

  // ============= DIAGNOSTICS PANEL =============
  let _diagOpen = false;
  function toggleDiagnostics() {
    _diagOpen = !_diagOpen;
    const el = document.getElementById('diagnostics');
    if (el) el.style.display = _diagOpen ? 'block' : 'none';
    if (_diagOpen) updateDiagnostics();
  }
  async function updateDiagnostics() {
    const body = document.getElementById('diagBody');
    if (!body) return;
    const lines = [];
    lines.push('Cesium: ' + (window.Cesium ? Cesium.VERSION || 'loaded' : 'MISSING'));
    lines.push('Base imagery: ' + (window._baseLayerName || '?'));
    lines.push('Night overlay: ' + (window._nightLayer ? 'VIIRS Black Marble' : 'none'));
    lines.push('Terrain: ' + (viewer?.terrainProvider ? 'active' : 'none'));
    lines.push('Entities: ' + (viewer?.entities?.values?.length ?? '?'));
    lines.push('Active mode: ' + (window.currentModeId ? window.currentModeId() : '?'));
    lines.push('Design system: ' + (window.DS ? 'OK' : 'MISSING'));
    lines.push('Layers registered: ' + (window.LAYERS ? Object.keys(window.LAYERS).length : '?'));
    lines.push('Wind canvas: ' + (window.WindCanvas ? 'OK' : 'MISSING'));
    lines.push('Planet engine: ' + (window.Planets ? 'OK' : 'MISSING'));
    // Probe /api/health
    try {
      const r = await fetch('/api/health');
      if (r.ok) {
        const d = await r.json();
        const layers = d.layers || {};
        const okCount = Object.values(layers).filter(l => l.ok).length;
        const errCount = Object.values(layers).filter(l => !l.ok).length;
        lines.push('');
        lines.push('Backend: ' + okCount + ' layers OK, ' + errCount + ' err');
        // List errors
        Object.entries(layers).forEach(([k, v]) => {
          if (!v.ok) lines.push('  ✗ ' + k + ': ' + (v.error || '').slice(0, 40));
        });
      } else {
        lines.push('Backend: /api/health ' + r.status);
      }
    } catch (e) { lines.push('Backend: FAIL ' + e.message); }
    body.innerHTML = lines.map(l => l.replace(/</g, '&lt;')).join('<br>');
  }
  document.addEventListener('keydown', (e) => {
    if (e.key === 'd' || e.key === 'D') {
      // Don't fire if the user is typing in an input
      if (document.activeElement && ['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) return;
      toggleDiagnostics();
    }
  });
  document.getElementById('diagClose')?.addEventListener('click', toggleDiagnostics);
  window.updateDiagnostics = updateDiagnostics;
  window.toggleDiagnostics = toggleDiagnostics;

  // ============= FLAG HELPER =============
  function flagEmoji(iso3) {
    // Fallback: ISO3 → ISO2 lookup for common countries
    const iso2map = {
      USA:'US',CHN:'CN',DEU:'DE',JPN:'JP',IND:'IN',GBR:'GB',FRA:'FR',ITA:'IT',KOR:'KR',NLD:'NL',
      RUS:'RU',BRA:'BR',CAN:'CA',AUS:'AU',MEX:'MX',SAU:'SA',ARE:'AE',TUR:'TR',CHE:'CH',ESP:'ES',
      PRT:'PT',GRC:'GR',POL:'PL',SWE:'SE',NOR:'NO',DNK:'DK',FIN:'FI',BEL:'BE',AUT:'AT',IRL:'IE',
      ZAF:'ZA',NGA:'NG',EGY:'EG',KEN:'KE',ETH:'ET',GHA:'GH',MAR:'MA',TUN:'TN',DZA:'DZ',UKR:'UA',
      IRN:'IR',IRQ:'IQ',ISR:'IL',QAT:'QA',KWT:'KW',SGP:'SG',MYS:'MY',THA:'TH',VNM:'VN',IDN:'ID',
      PHL:'PH',TWN:'TW',HKG:'HK',PAK:'PK',BGD:'BD',NZL:'NZ',ARG:'AR',CHL:'CL',PER:'PE',COL:'CO',
      VEN:'VE',CUB:'CU',DOM:'DO',HND:'HN',GTM:'GT',SLV:'SV',CRI:'CR',PAN:'PA',URY:'UY',PRY:'PY',
      BOL:'BO',ECU:'EC',
    };
    const cc = iso2map[iso3];
    if (!cc) return '🏳️';
    return String.fromCodePoint(...cc.split('').map(c => 0x1F1E6 - 65 + c.charCodeAt(0)));
  }
  window.flagEmoji = flagEmoji;

})();
