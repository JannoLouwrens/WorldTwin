// UI panels: legend strip, legend card, country card, commodity filter, ticker.
(function(){

  // ============= LEGEND STRIP =============
  function setLegendStrip(legend, describe) {
    const strip = document.getElementById('legendStrip');
    if (!legend) { strip.style.display = 'none'; return; }
    strip.style.display = 'flex';
    document.getElementById('lgLabel').textContent = legend.title;
    document.getElementById('lgMin').textContent = legend.min || '—';
    document.getElementById('lgMax').textContent = legend.max || '—';
    // Update ramp
    const ramp = DS.ramps[legend.ramp] || DS.ramps.heat;
    document.getElementById('lgRamp').style.background = 'linear-gradient(90deg, ' + ramp.join(', ') + ')';
    // Mode dot
    const mode = window.currentModeId ? window.currentModeId() : 'world';
    const hue = DS.modeHue[mode] || DS.modeHue.world;
    document.getElementById('lgDot').style.color = hue;
    document.getElementById('lgDot').style.background = hue;
    // Freshness — pick a sensible layer fetched_at to show
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

  // ============= COUNTRY CARD =============
  let _countryResourcesData = null;
  let _deepDiveData = null;
  async function loadCountryResources() {
    if (_countryResourcesData) return _countryResourcesData;
    const r = await fetch('/api/cache/country_resources.json');
    if (!r.ok) return null;
    _countryResourcesData = await r.json();
    return _countryResourcesData;
  }
  async function loadDeepDive() {
    if (_deepDiveData) return _deepDiveData;
    try {
      const r = await fetch('/api/cache/country_deep_dive.json');
      if (!r.ok) return null;
      _deepDiveData = await r.json();
      return _deepDiveData;
    } catch (_) { return null; }
  }

  function showCountryCard(iso3) {
    loadCountryResources().then(data => {
      if (!data || !data.countries || !data.countries[iso3]) {
        document.getElementById('ccName').textContent = iso3 || '—';
        document.getElementById('ccSub').textContent = 'No fact sheet available';
        document.getElementById('ccBody').innerHTML = '';
        document.getElementById('countryCard').classList.add('show');
        return;
      }
      const c = data.countries[iso3];
      document.getElementById('ccFlag').textContent = flagEmoji(iso3);
      document.getElementById('ccName').textContent = c.name;
      document.getElementById('ccSub').textContent = `ISO ${c.iso3} · M49 ${c.m49} · Year ${c.year}`;

      // KPIs: trade balance, exports, imports
      const balance = c.trade_balance_usd;
      const balColor = balance >= 0 ? '#34d399' : '#ef4444';
      let body = `
        <div class="cc-section">
          <div class="cc-section-title">Trade Balance ${c.year}</div>
          <div class="cc-kpis">
            <div class="cc-kpi"><div class="label">Exports</div><div class="value">$${DS.fmt(c.total_exports_usd)}</div></div>
            <div class="cc-kpi"><div class="label">Imports</div><div class="value">$${DS.fmt(c.total_imports_usd)}</div></div>
          </div>
          <div class="cc-kpi" style="grid-column:1/-1"><div class="label">Net Balance</div><div class="value" style="color:${balColor}">${balance >= 0 ? '+' : ''}$${DS.fmt(balance)}</div></div>
        </div>
      `;

      // Top exports
      const topExp = (c.top_exports || []).slice(0, 10);
      const maxExp = topExp[0]?.value_usd || 1;
      body += `
        <div class="cc-section">
          <div class="cc-section-title">Top Exports</div>
          <div class="cc-list">
            ${topExp.map(e => {
              const pct = e.value_usd / maxExp;
              const hue = DS.categoryHue[e.parent] || '#999';
              return `
                <div class="row">
                  <div class="swatch" style="background:${hue}"></div>
                  <div class="name">${e.category}</div>
                  <div class="val">$${DS.fmt(e.value_usd)}</div>
                </div>
                <div class="cc-bar"><div class="fill" style="width:${pct*100}%;background:${hue}"></div></div>
              `;
            }).join('')}
          </div>
        </div>
      `;

      // Top imports
      const topImp = (c.top_imports || []).slice(0, 10);
      const maxImp = topImp[0]?.value_usd || 1;
      body += `
        <div class="cc-section">
          <div class="cc-section-title">Top Imports</div>
          <div class="cc-list">
            ${topImp.map(e => {
              const pct = e.value_usd / maxImp;
              const hue = DS.categoryHue[e.parent] || '#999';
              return `
                <div class="row">
                  <div class="swatch" style="background:${hue}"></div>
                  <div class="name">${e.category}</div>
                  <div class="val">$${DS.fmt(e.value_usd)}</div>
                </div>
                <div class="cc-bar"><div class="fill" style="width:${pct*100}%;background:${hue}"></div></div>
              `;
            }).join('')}
          </div>
        </div>
      `;

      // Power mix
      if (c.power) {
        body += `
          <div class="cc-section">
            <div class="cc-section-title">Power Generation · ${c.power.total_mw.toFixed(0)} MW · ${c.power.plant_count} plants</div>
            <div class="cc-list fuel-list">
              ${c.power.mix.map(m => `
                <div class="row">
                  <div class="swatch" style="background:${DS.fuelHue[m.fuel.toLowerCase()] || '#6b7790'}"></div>
                  <div class="name">${m.fuel}</div>
                  <div class="val">${m.pct.toFixed(1)}%</div>
                </div>
              `).join('')}
            </div>
          </div>
        `;
      }

      // Deep dive — Electricity / Water / Food / Oil (async, loads after base render)
      body += `<div id="deepDivePlaceholder"></div>`;
      body += `<div class="cc-section"><div style="font-size:9px;opacity:0.4;">Sources: UN Comtrade, WRI Global Power Plant DB, OWID Energy, FEWS NET, WRI Aqueduct, ClimateTRACE</div></div>`;

      document.getElementById('ccBody').innerHTML = body;
      document.getElementById('countryCard').classList.add('show');

      // Load deep-dive asynchronously and append
      loadDeepDive().then(dd => {
        if (!dd) return;
        const dc = dd.countries && dd.countries[iso3];
        if (!dc) return;
        const ph = document.getElementById('deepDivePlaceholder');
        if (!ph) return;
        ph.innerHTML = renderDeepDive(dc);
      });
    });
  }

  function renderDeepDive(dd) {
    const e = dd.electricity || {};
    const w = dd.water || {};
    const f = dd.food || {};
    const o = dd.oil || {};
    const em = dd.emissions || {};
    let html = '';

    // Electricity
    if (e.generation_twh || e.fossil_share !== null) {
      const fossil = e.fossil_share != null ? e.fossil_share.toFixed(0) : '—';
      const renew = e.renewables_share != null ? e.renewables_share.toFixed(0) : '—';
      const nuclear = e.nuclear_share != null ? e.nuclear_share.toFixed(0) : '—';
      const carbon = e.carbon_intensity_gco2_kwh != null ? e.carbon_intensity_gco2_kwh.toFixed(0) : '—';
      html += `
        <div class="cc-section">
          <div class="cc-section-title">⚡ Electricity (${e.year || '—'})</div>
          <div class="cc-kpis">
            <div class="cc-kpi"><div class="label">Generation</div><div class="value">${e.generation_twh != null ? DS.fmt(e.generation_twh, 1) + ' TWh' : '—'}</div></div>
            <div class="cc-kpi"><div class="label">Carbon</div><div class="value">${carbon} g/kWh</div></div>
          </div>
          <div class="cc-list">
            <div class="row"><div class="swatch" style="background:#3b3b3b"></div><div class="name">Fossil</div><div class="val">${fossil}%</div></div>
            <div class="row"><div class="swatch" style="background:#22c55e"></div><div class="name">Renewables</div><div class="val">${renew}%</div></div>
            <div class="row"><div class="swatch" style="background:#5eead4"></div><div class="name">Nuclear</div><div class="val">${nuclear}%</div></div>
          </div>
          ${e.total_plants ? `<div style="font-size:10px;color:var(--text-lo);margin-top:6px">${e.total_plants} plants · ${DS.fmt(e.total_capacity_mw || 0)} MW installed</div>` : ''}
        </div>
      `;
    }

    // Water
    if (w.baseline_water_stress != null) {
      const s = w.baseline_water_stress;
      let hex = '#22c55e';
      if (s >= 4.5) hex = '#ef3b3b';
      else if (s >= 3.5) hex = '#fb923c';
      else if (s >= 2.5) hex = '#fbbf24';
      const pct = (s / 5) * 100;
      html += `
        <div class="cc-section">
          <div class="cc-section-title">💧 Water Stress</div>
          <div style="font-size:20px;font-weight:700;color:${hex}">${w.stress_description || '—'}</div>
          <div style="font-size:10px;color:var(--text-lo);margin-top:4px">Aqueduct baseline score: ${s.toFixed(1)} / 5</div>
          <div class="cc-bar" style="margin-top:6px"><div class="fill" style="width:${pct}%;background:${hex}"></div></div>
        </div>
      `;
    }

    // Food
    if (f.ipc_phase != null) {
      const p = f.ipc_phase;
      const phaseNames = { 1: 'None/Minimal', 2: 'Stressed', 3: 'Crisis', 4: 'Emergency', 5: 'Famine' };
      let hex = '#22c55e';
      if (p >= 4) hex = '#ef3b3b';
      else if (p >= 3) hex = '#fb923c';
      else if (p >= 2) hex = '#fbbf24';
      html += `
        <div class="cc-section">
          <div class="cc-section-title">🌾 Food Security</div>
          <div style="font-size:20px;font-weight:700;color:${hex}">Phase ${p} · ${phaseNames[p] || f.ipc_description || ''}</div>
          ${f.ipc_period ? `<div style="font-size:10px;color:var(--text-lo);margin-top:4px">${f.ipc_scenario || ''} ${f.ipc_period}</div>` : ''}
          <div style="font-size:10px;color:var(--text-lo);margin-top:6px">Source: FEWS NET · IPC classification</div>
        </div>
      `;
    }

    // Oil / primary energy
    if (o.primary_energy_twh || o.greenhouse_gas_emissions_mt) {
      html += `
        <div class="cc-section">
          <div class="cc-section-title">🛢 Energy & Emissions</div>
          <div class="cc-kpis">
            <div class="cc-kpi"><div class="label">Primary Energy</div><div class="value">${o.primary_energy_twh != null ? DS.fmt(o.primary_energy_twh, 0) + ' TWh' : '—'}</div></div>
            <div class="cc-kpi"><div class="label">GHG Emissions</div><div class="value">${o.greenhouse_gas_emissions_mt != null ? DS.fmt(o.greenhouse_gas_emissions_mt, 0) + ' Mt' : '—'}</div></div>
          </div>
        </div>
      `;
    }

    // ClimateTRACE sector breakdown
    if (em.total_tco2e && em.by_sector) {
      const sectors = Object.entries(em.by_sector).sort((a, b) => b[1] - a[1]).slice(0, 5);
      const max = em.total_tco2e;
      html += `
        <div class="cc-section">
          <div class="cc-section-title">🏭 ClimateTRACE emissions</div>
          <div class="cc-list">
            ${sectors.map(([s, v]) => {
              const pct = (v / max) * 100;
              return `
                <div class="row">
                  <div class="swatch" style="background:#fb923c"></div>
                  <div class="name">${s.replace(/-/g, ' ')}</div>
                  <div class="val">${DS.fmt(v, 1)} tCO2e</div>
                </div>
                <div class="cc-bar"><div class="fill" style="width:${pct}%;background:#fb923c"></div></div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    return html;
  }
  function hideCountryCard() { document.getElementById('countryCard').classList.remove('show'); }
  document.getElementById('ccClose').addEventListener('click', hideCountryCard);

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
  window.showCountryCard = showCountryCard;
  window.hideCountryCard = hideCountryCard;
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
