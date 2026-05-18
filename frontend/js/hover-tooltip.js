// hover-tooltip.js — small floating tooltip that shows the country name and
// the active mapmode's value when the user hovers a country polygon.
//
// Listens for the `mapmode_hover` CustomEvent emitted by mapmode.js.
// Reads the corresponding mapmode metadata (legend, value formatter) to
// produce a clean per-country readout.
(function(){
  let _el = null;
  let _lastIso3 = null;
  let _mouseX = 0, _mouseY = 0;

  function ensureEl() {
    if (_el) return _el;
    const t = document.createElement('div');
    t.className = 'tw-hover-tooltip';
    Object.assign(t.style, {
      position: 'fixed',
      pointerEvents: 'none',
      zIndex: 100,
      background: 'rgba(14,19,32,0.94)',
      border: '1px solid rgba(255,255,255,0.18)',
      borderRadius: '8px',
      padding: '8px 12px',
      font: '11px Inter, sans-serif',
      letterSpacing: '0.02em',
      color: '#f5f7fa',
      backdropFilter: 'blur(14px)',
      boxShadow: '0 6px 24px rgba(0,0,0,0.5)',
      maxWidth: '240px',
      transition: 'opacity .14s ease',
      opacity: '0',
      left: '0px',
      top: '0px',
    });
    document.body.appendChild(t);
    _el = t;
    return t;
  }

  // Resolve a mapmode value into a printable string for the active mapmode.
  function formatValue(detail) {
    if (!detail) return '';
    const { iso3, mode, value } = detail;
    // Look up the actual numeric value from cache for this mapmode
    const mapmodes = (window.Mapmode?.list?.() || []);
    const mm = mapmodes.find(m => m.id === mode);
    const legendTitle = mm?.legend?.title || mode;

    // Try to read the underlying value from caches
    const wb = window._cacheStore?.get('world_bank');
    const imf = window._cacheStore?.get('imf_data');
    const dd = window._cacheStore?.get('country_deep_dive');
    const cc = window._cacheStore?.get('country_culture');
    const md = window._cacheStore?.get('maddison_history');
    const hp = window._cacheStore?.get('hyde_population');
    const rel = window._cacheStore?.get('country_relations');

    const fmtBig = v => {
      if (v == null) return '—';
      if (Math.abs(v) >= 1e12) return (v/1e12).toFixed(2) + ' T';
      if (Math.abs(v) >= 1e9)  return (v/1e9).toFixed(2)  + ' B';
      if (Math.abs(v) >= 1e6)  return (v/1e6).toFixed(2)  + ' M';
      if (Math.abs(v) >= 1e3)  return (v/1e3).toFixed(2)  + ' k';
      return String(v);
    };

    const lookups = {
      gdp:         () => '$' + fmtBig((wb?.countries?.[iso3]?.['NY.GDP.MKTP.CD'] || {}).value),
      gdp_pc:      () => '$' + fmtBig((wb?.countries?.[iso3]?.['NY.GDP.PCAP.CD'] || {}).value),
      population:  () => fmtBig((wb?.countries?.[iso3]?.['SP.POP.TOTL'] || {}).value),
      inflation:   () => {
        const v = imf?.countries?.[iso3]?.PCPIPCH?.value;
        return v == null ? '—' : v.toFixed(1) + ' %';
      },
      military:    () => {
        const v = (wb?.countries?.[iso3]?.['MS.MIL.XPND.GD.ZS'] || {}).value;
        return v == null ? '—' : v.toFixed(2) + ' % GDP';
      },
      water_stress: () => {
        const v = dd?.countries?.[iso3]?.water?.baseline_water_stress;
        return v == null ? '—' : v.toFixed(2);
      },
      food: () => {
        const v = dd?.countries?.[iso3]?.food?.ipc_phase;
        return v == null ? '—' : 'IPC phase ' + v;
      },
      co2: () => {
        const v = (wb?.countries?.[iso3]?.['EN.ATM.CO2E.PC'] || {}).value;
        return v == null ? '—' : v.toFixed(2) + ' t/yr';
      },
      renewable: () => {
        const v = (wb?.countries?.[iso3]?.['EG.ELC.RNEW.ZS'] || {}).value;
        return v == null ? '—' : v.toFixed(1) + ' %';
      },
      internet: () => {
        const v = (wb?.countries?.[iso3]?.['IT.NET.USER.ZS'] || {}).value;
        return v == null ? '—' : v.toFixed(1) + ' %';
      },
      life: () => {
        const v = (wb?.countries?.[iso3]?.['SP.DYN.LE00.IN'] || {}).value;
        return v == null ? '—' : v.toFixed(1) + ' yr';
      },
      urban: () => {
        const v = (wb?.countries?.[iso3]?.['SP.URB.TOTL.IN.ZS'] || {}).value;
        return v == null ? '—' : v.toFixed(1) + ' %';
      },
      debt: () => {
        const v = imf?.countries?.[iso3]?.GGXWDG_NGDP?.value;
        return v == null ? '—' : v.toFixed(1) + ' % GDP';
      },
      religion:  () => cc?.countries?.[iso3]?.religion?.family || '—',
      ethnicity: () => cc?.countries?.[iso3]?.ethnicity?.family || '—',
      political: () => {
        const r = rel?.by_country?.[iso3];
        return r ? (r.bloc_primary || (r.blocs || []).join(', ') || '—') : '—';
      },
      gdp_pc_history: () => {
        if (!md) return '—';
        const yr = window.__CURRENT_YEAR__;
        for (const ent in md.countries) {
          if (md.countries[ent].iso3 === iso3) {
            const series = md.countries[ent].series;
            let row = null;
            for (const r of series) { if (r[0] <= yr) row = r; else break; }
            return row && row[1] != null ? '$' + fmtBig(row[1]) : '—';
          }
        }
        return '—';
      },
      population_history: () => {
        if (!hp) return '—';
        const yr = window.__CURRENT_YEAR__;
        const bucket = hp.countries?.[iso3];
        if (!bucket) return '—';
        let row = null;
        for (const r of bucket.series) { if (r[0] <= yr) row = r; else break; }
        return row && row[1] != null ? fmtBig(row[1]) : '—';
      },
      pulse: () => {
        const c = window._cacheStore?.get('pulse_mode')?.countries?.[iso3];
        return c?.composite != null ? c.composite.toFixed(0) + ' / 100' : '—';
      },
    };

    const fn = lookups[mode];
    return { label: legendTitle, value: fn ? fn() : '—' };
  }

  // Provenance hint for the active mapmode + scrubber year. Italicised when
  // the source is a scholarly reconstruction (pre-1900 V-Dem, pre-1500 Maddison).
  function provenance(mode, year) {
    const isPast = window.Clock && year < window.Clock.MAX_YEAR;
    if (!isPast) return null;
    const reconstruction = year < 1900;
    const sources = {
      gdp: 'World Bank WDI', gdp_pc: year < 1960 ? 'Maddison Project 2020' : 'World Bank WDI',
      population: year < 2023 ? 'HYDE 3.3 + UN WPP' : 'World Bank WDI',
      inflation: 'IMF WEO', debt: 'World Bank WDI',
      life: year < 1960 ? 'Clio-Infra + UN' : 'World Bank WDI',
      urban: 'World Bank WDI', internet: 'World Bank WDI',
      co2: 'World Bank WDI', renewable: 'OWID Energy',
      military: 'World Bank WDI', democracy: 'V-Dem v14',
      political: year < 2009 ? 'COW (curated)' : 'WorldTwin curated blocs',
    };
    const src = sources[mode];
    if (!src) return null;
    return { src, year, reconstruction };
  }

  function show(detail) {
    if (!detail) { hide(); return; }
    const t = ensureEl();
    const { iso3, name, mode } = detail;
    const fmt = formatValue(detail);
    const swatch = (window.MAPMODE_COLORS || {})[iso3] || '#94a3b8';
    const prov = window.Clock ? provenance(mode, window.Clock.year) : null;
    // Provenance now ALWAYS shows even at Live — surface "today" + the
    // mapmode's source name so the user knows when the data was measured.
    const todayUtc = new Date().toISOString().slice(0, 10);
    const liveSrc = ({
      gdp: 'World Bank WDI', gdp_pc: 'World Bank WDI', population: 'World Bank WDI',
      inflation: 'IMF WEO', debt: 'World Bank WDI', life: 'World Bank WDI',
      urban: 'World Bank WDI', internet: 'World Bank WDI', co2: 'World Bank WDI',
      pollution: 'World Bank WDI', renewable: 'OWID Energy', military: 'World Bank WDI',
      democracy: 'V-Dem v14', political: 'WorldTwin curated blocs',
      religion: 'WorldTwin curated', ethnicity: 'WorldTwin curated',
      pulse: 'WorldTwin pulse composite', water_stress: 'WRI Aqueduct', food: 'IPC',
    })[mode];
    const provHtml = prov
      ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);font-size:10px;color:#c9a86b${prov.reconstruction ? ';font-style:italic' : ''}">
           ${window.Clock.label(prov.year)} · ${prov.src}${prov.reconstruction ? ' · reconstruction' : ''} <span style="color:#8c95aa;margin-left:6px">today: ${todayUtc}</span>
         </div>`
      : (liveSrc ? `<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.08);font-size:10px;color:#c9a86b">
           ${liveSrc} · today ${todayUtc}
         </div>` : '');
    // Causal summary — top trade partner + ally/enemy counts. Surfaces
    // what the causal-lines arcs are showing without clicking each arc.
    const ta = window._cacheStore?.get('trade_annual');
    const flows = ta?.flows || [];
    let topPartnerName = null, topPartnerVal = 0, topPartnerKind = null;
    for (const f of flows) {
      const v = f.value_usd || 0;
      if (f.from_iso3 === iso3 && v > topPartnerVal) { topPartnerVal = v; topPartnerName = f.to_name; topPartnerKind = 'export'; }
      if (f.to_iso3 === iso3 && v > topPartnerVal) { topPartnerVal = v; topPartnerName = f.from_name; topPartnerKind = 'import'; }
    }
    const rel2 = window._cacheStore?.get('country_relations');
    const r2 = rel2?.by_country?.[iso3];
    const allyCount = r2?.allies?.length || 0;
    const enemyCount = r2?.enemies?.length || 0;
    const blocs = (r2?.blocs || []).slice(0, 3).join(' · ');

    let causalHtml = '';
    if (topPartnerName || allyCount || enemyCount) {
      const lines = [];
      if (topPartnerName && topPartnerVal > 0) {
        const symbol = topPartnerKind === 'export' ? '→' : '←';
        const color = topPartnerKind === 'export' ? '#ffb547' : '#00d4ff';
        lines.push(`<span style="color:${color}">${symbol} ${topPartnerName}</span> $${(topPartnerVal/1e9).toFixed(1)}B`);
      }
      if (allyCount || enemyCount) {
        const parts = [];
        if (allyCount)  parts.push(`<span style="color:#5fbf7d">${allyCount} allies</span>`);
        if (enemyCount) parts.push(`<span style="color:#d94747">${enemyCount} adversaries</span>`);
        lines.push(parts.join(' · '));
      }
      if (blocs) lines.push(`<span style="color:#c9a86b;font-style:italic">${blocs}</span>`);
      causalHtml = `<div style="margin-top:6px;padding-top:6px;border-top:1px dotted rgba(255,230,195,0.18);font-size:10px;letter-spacing:0.02em;color:#cfe6ff">${lines.join('<br>')}</div>`;
    }

    t.innerHTML = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <div style="width:10px;height:10px;border-radius:2px;background:${swatch};border:1px solid rgba(255,255,255,0.3)"></div>
        <div style="font-weight:600;color:#f5f7fa">${name}</div>
        <div style="opacity:0.5;font-size:10px;letter-spacing:0.06em">${iso3}</div>
      </div>
      <div style="display:flex;justify-content:space-between;gap:14px;color:#b8c1d1">
        <span>${fmt.label || ''}</span>
        <span style="color:#f5f7fa;font-weight:600;font-feature-settings:'tnum' 1">${fmt.value || ''}</span>
      </div>
      ${causalHtml}
      ${provHtml}`;
    t.style.opacity = '1';
    place();
  }
  function hide() {
    if (!_el) return;
    _el.style.opacity = '0';
    _lastIso3 = null;
  }
  function place() {
    if (!_el) return;
    const w = _el.offsetWidth, h = _el.offsetHeight;
    let x = _mouseX + 16;
    let y = _mouseY + 16;
    if (x + w > window.innerWidth - 8)  x = _mouseX - w - 16;
    if (y + h > window.innerHeight - 8) y = _mouseY - h - 16;
    _el.style.left = x + 'px';
    _el.style.top  = y + 'px';
  }

  document.addEventListener('mousemove', e => {
    _mouseX = e.clientX; _mouseY = e.clientY;
    place();
    // Auto-hide if mouse leaves the globe canvas (over a panel instead).
    // We don't fire mapmode_hover for non-globe areas, so the tooltip would
    // otherwise stick at its last position — looks broken.
    const tgt = e.target;
    if (tgt && tgt !== document.body && tgt.tagName !== 'CANVAS') {
      hide();
    }
  });
  // Also hide when mouse leaves the window entirely
  document.addEventListener('mouseleave', () => hide());
  window.addEventListener('mapmode_hover', (e) => {
    const detail = e.detail;
    if (!detail) { hide(); return; }
    if (detail.iso3 === _lastIso3) return;
    _lastIso3 = detail.iso3;
    show(detail);
  });
})();
