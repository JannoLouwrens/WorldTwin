// dossier.js — full multi-source intelligence dossier for any country.
//
// Combines 8 caches into one tabbed panel:
//   * world_bank      — gdp, gdppc, life, internet, military, urban, co2/cap, ...
//   * imf_data        — inflation, debt, growth forecast
//   * country_culture — religion + ethnicity (with family classification)
//   * country_relations — blocs, allies, enemies
//   * country_resources — top 5 exports/imports + main partners
//   * country_deep_dive — water stress, food security, energy mix
//   * pulse_mode      — composite risk score breakdown
//   * maddison_history — historical GDPpc (mini sparkline)
//
// Press Escape to close. Replaces the old country-card / intel-card
// for any "click on country surface" path.
(function(){
  let _el = null;

  function ensure() {
    if (_el) return _el;
    const el = document.createElement('div');
    el.id = 'twDossier';
    Object.assign(el.style, {
      position: 'fixed', top: '120px', right: '16px',
      width: '380px', maxHeight: 'calc(100vh - 340px)',
      background: 'linear-gradient(180deg, rgba(20,28,48,0.96), rgba(14,19,32,0.96))',
      border: '1px solid rgba(76,194,255,0.30)',
      borderRadius: '14px',
      backdropFilter: 'blur(16px)',
      boxShadow: '0 20px 60px rgba(0,0,0,0.6)',
      color: '#f5f7fa',
      font: '12px Inter, sans-serif',
      zIndex: 110,
      display: 'none',
      overflow: 'hidden',
    });
    document.body.appendChild(el);
    _el = el;
    return el;
  }

  function fmtN(n, d = 1) {
    if (n == null || !Number.isFinite(n)) return '—';
    if (Math.abs(n) >= 1e12) return (n/1e12).toFixed(d) + 'T';
    if (Math.abs(n) >= 1e9)  return (n/1e9).toFixed(d)  + 'B';
    if (Math.abs(n) >= 1e6)  return (n/1e6).toFixed(d)  + 'M';
    if (Math.abs(n) >= 1e3)  return (n/1e3).toFixed(d)  + 'K';
    return n.toFixed(d);
  }
  function pctStr(v) { return v == null ? '—' : v.toFixed(1) + '%'; }
  function get(cache, path) {
    const c = window._cacheStore?.get(cache);
    if (!c) return undefined;
    return path.split('.').reduce((a, k) => (a == null ? a : a[k]), c);
  }
  function wbVal(iso3, key) {
    // World Bank indicator keys contain dots (NY.GDP.MKTP.CD), so we can't
    // dot-split them. Read directly.
    return window._cacheStore?.get('world_bank')?.countries?.[iso3]?.[key]?.value;
  }

  // Inline mini sparkline (SVG) for a series of [year, value] pairs.
  function sparkline(series, w, h) {
    if (!series || series.length < 2) return '';
    // Filter out non-finite y values BEFORE indexing — otherwise the first sample
    // could be NaN, producing an invalid SVG path that starts with 'L' not 'M'.
    const clean = (series || []).filter(s => Array.isArray(s) && Number.isFinite(s[1]));
    if (clean.length < 2) return '';
    const ys = clean.map(s => s[1]);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const pad = (yMax - yMin) * 0.05 || 1;
    const norm = v => h - ((v - yMin + pad) / (yMax - yMin + pad * 2)) * h;
    const path = clean.map((s, i) => {
      const x = (i / (clean.length - 1)) * w;
      return `${i ? 'L' : 'M'}${x.toFixed(1)} ${norm(s[1]).toFixed(1)}`;
    }).join(' ');
    return `
      <svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="display:block">
        <path d="${path}" fill="none" stroke="#4cc2ff" stroke-width="1.5" stroke-linejoin="round"/>
      </svg>`;
  }

  function build(iso3) {
    const intel = {};
    intel.iso3 = iso3;

    // Identity
    const polys = window.Mapmode?.polygonsByIso3?.() || {};
    const p = polys[iso3] || {};
    intel.name = p.name || p.admin || iso3;
    intel.continent = p.continent;
    intel.subregion = p.subregion;
    intel.income = p.income_grp;
    intel.pop_polygon = p.pop;

    // Snapshot — World Bank
    intel.gdp = wbVal(iso3, 'NY.GDP.MKTP.CD');
    intel.gdpPc = wbVal(iso3, 'NY.GDP.PCAP.CD');
    intel.population = wbVal(iso3, 'SP.POP.TOTL');
    intel.life = wbVal(iso3, 'SP.DYN.LE00.IN');
    intel.internet = wbVal(iso3, 'IT.NET.USER.ZS');
    intel.urban = wbVal(iso3, 'SP.URB.TOTL.IN.ZS');
    intel.military = wbVal(iso3, 'MS.MIL.XPND.GD.ZS');
    intel.co2pc = wbVal(iso3, 'EN.ATM.CO2E.PC');
    intel.renewable = wbVal(iso3, 'EG.ELC.RNEW.ZS');

    // IMF — inflation, debt, GDP growth forecast
    const imfRow = window._cacheStore?.get('imf_data')?.countries?.[iso3];
    intel.inflation = imfRow?.PCPIPCH?.value;
    intel.debt = imfRow?.GGXWDG_NGDP?.value;
    intel.growth = imfRow?.NGDP_RPCH?.value;

    // Culture
    const cc = window._cacheStore?.get('country_culture')?.countries?.[iso3];
    intel.religion = cc?.religion?.label;
    intel.religionFamily = cc?.religion?.family;
    intel.ethnicity = cc?.ethnicity?.label;
    intel.ethnicityFamily = cc?.ethnicity?.family;

    // Relations
    const rel = window._cacheStore?.get('country_relations')?.by_country?.[iso3];
    intel.blocs = rel?.blocs || [];
    intel.blocPrimary = rel?.bloc_primary;
    intel.blocColor = rel?.bloc_color;
    intel.allies = rel?.allies || [];
    intel.enemies = rel?.enemies || [];

    // Resources / dependencies
    const res = window._cacheStore?.get('country_resources')?.countries?.[iso3];
    intel.exports = res?.top_exports?.slice(0, 5) || [];
    intel.imports = res?.top_imports?.slice(0, 5) || [];
    intel.tradePartners = res?.top_partners?.slice(0, 5) || [];

    // Deep dive
    const dd = window._cacheStore?.get('country_deep_dive')?.countries?.[iso3];
    intel.water = dd?.water?.baseline_water_stress;
    intel.foodIPC = dd?.food?.ipc_phase;
    intel.energyMix = dd?.energy;

    // Pulse — composite risk
    const p2 = window._cacheStore?.get('pulse_mode')?.countries?.[iso3];
    intel.composite = p2?.composite;
    intel.risks = p2 ? {
      conflict: p2.conflict, hazard: p2.natural_hazard, energy: p2.energy,
      food: p2.food, displacement: p2.displacement,
    } : null;

    // Historical sparkline (GDPpc since available)
    const md = window._cacheStore?.get('maddison_history');
    if (md?.countries) {
      for (const ent in md.countries) {
        if (md.countries[ent].iso3 === iso3) {
          intel.historicalGdpPc = md.countries[ent].series?.filter(r => r[1] != null);
          break;
        }
      }
    }
    return intel;
  }

  function render(iso3) {
    const el = ensure();
    const d = build(iso3);

    const blocChips = (d.blocs || []).map(b =>
      `<span style="background:${d.blocColor || 'rgba(255,255,255,0.06)'};color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;letter-spacing:0.04em">${b}</span>`
    ).join(' ');

    const stat = (label, value, sublabel) => `
      <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:8px 10px">
        <div style="font-size:9.5px;color:#8c95aa;letter-spacing:0.12em;text-transform:uppercase">${label}</div>
        <div style="font-size:14px;font-weight:600;color:#f5f7fa;margin-top:2px;font-feature-settings:'tnum' 1">${value}</div>
        ${sublabel ? `<div style="font-size:10px;color:#b8c1d1;margin-top:1px">${sublabel}</div>` : ''}
      </div>`;

    const partnersChips = (arr) => (arr || []).slice(0, 5).map(p =>
      `<span style="background:rgba(76,194,255,0.10);color:#7dd3fc;padding:2px 8px;border-radius:6px;font-size:10px;border:1px solid rgba(76,194,255,0.25)">${p}</span>`
    ).join(' ') || '<span style="color:#6b7790;font-style:italic">—</span>';

    const exportsList = (d.exports || []).slice(0, 5).map(e =>
      `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
        <span style="color:#b8c1d1">${e.commodity_name || e.name || e}</span>
        <span style="color:#f5f7fa;font-feature-settings:'tnum' 1">${e.value_usd ? '$' + fmtN(e.value_usd) : ''}</span>
      </div>`
    ).join('') || '<div style="color:#6b7790;font-style:italic">No data</div>';

    const importsList = (d.imports || []).slice(0, 5).map(e =>
      `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.05)">
        <span style="color:#b8c1d1">${e.commodity_name || e.name || e}</span>
        <span style="color:#f5f7fa;font-feature-settings:'tnum' 1">${e.value_usd ? '$' + fmtN(e.value_usd) : ''}</span>
      </div>`
    ).join('') || '<div style="color:#6b7790;font-style:italic">No data</div>';

    const riskBars = d.risks ? Object.entries(d.risks).map(([k, v]) => {
      if (v == null) return '';
      const pct = Math.round(Math.min(100, v * 100));
      const color = v >= 0.7 ? '#dc2626' : v >= 0.5 ? '#ef4444' : v >= 0.3 ? '#f97316' : v >= 0.15 ? '#facc15' : '#22c55e';
      return `<div style="margin:4px 0">
        <div style="display:flex;justify-content:space-between;font-size:10px;color:#b8c1d1;margin-bottom:2px"><span>${k}</span><span style="color:${color};font-weight:600">${pct}%</span></div>
        <div style="height:5px;background:rgba(255,255,255,0.05);border-radius:3px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color}"></div></div>
      </div>`;
    }).join('') : '<div style="color:#6b7790;font-style:italic">No risk data</div>';

    const compositeColor = d.composite == null ? '#6b7790'
      : d.composite >= 70 ? '#dc2626'
      : d.composite >= 50 ? '#ef4444'
      : d.composite >= 30 ? '#f97316'
      : d.composite >= 15 ? '#facc15' : '#22c55e';

    el.innerHTML = `
      <div style="padding:14px 16px 10px;border-bottom:1px solid rgba(255,255,255,0.07);position:sticky;top:0;background:rgba(20,28,48,0.96);backdrop-filter:blur(16px);z-index:2">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-size:18px;font-weight:700;letter-spacing:-0.01em">${d.name}</div>
            <div style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase;margin-top:2px">${d.iso3} · ${d.continent || ''} · ${d.subregion || ''}</div>
          </div>
          <button id="twDossierClose" style="background:none;border:0;color:#b8c1d1;font-size:22px;cursor:pointer;padding:0;line-height:1">×</button>
        </div>
        <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px">${blocChips}</div>
      </div>

      <div style="padding:14px 16px;overflow-y:auto;max-height:calc(100vh - 410px)">

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
          ${stat('GDP', d.gdp != null ? '$' + fmtN(d.gdp, 1) : '—', d.growth != null ? `${d.growth >= 0 ? '+' : ''}${d.growth.toFixed(1)}% growth` : '')}
          ${stat('GDP/cap', d.gdpPc != null ? '$' + fmtN(d.gdpPc, 0) : '—', d.income || '')}
          ${stat('Population', fmtN(d.population || d.pop_polygon, 1), d.urban != null ? `${d.urban.toFixed(0)}% urban` : '')}
          ${stat('Life expectancy', d.life != null ? d.life.toFixed(1) + ' yr' : '—')}
          ${stat('Inflation', pctStr(d.inflation), d.debt != null ? `Debt: ${d.debt.toFixed(0)}% GDP` : '')}
          ${stat('Internet', pctStr(d.internet), d.military != null ? `Mil: ${d.military.toFixed(2)}% GDP` : '')}
        </div>

        ${(d.religion || d.ethnicity) ? `
        <div style="margin-bottom:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px">
          ${stat('Religion', d.religionFamily || '—', d.religion || '')}
          ${stat('Ethnicity', d.ethnicityFamily || '—', d.ethnicity || '')}
        </div>` : ''}

        ${d.composite != null ? `
        <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:8px;padding:10px;margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase">Composite risk</span>
            <span style="color:${compositeColor};font-weight:700;font-size:18px">${Math.round(d.composite)}</span>
          </div>
          ${riskBars}
        </div>` : ''}

        ${d.exports.length || d.imports.length ? `
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Top exports / imports</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
            <div>
              <div style="font-size:9.5px;color:#22c55e;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:3px">↗ Exports</div>
              ${exportsList}
            </div>
            <div>
              <div style="font-size:9.5px;color:#f97316;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:3px">↘ Imports</div>
              ${importsList}
            </div>
          </div>
        </div>` : ''}

        ${d.tradePartners.length ? `
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Top trade partners</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px">${partnersChips(d.tradePartners)}</div>
        </div>` : ''}

        ${(d.allies.length || d.enemies.length) ? `
        <div style="margin-bottom:10px">
          <div style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Geopolitics</div>
          <div style="font-size:11px;color:#b8c1d1">
            <div><b style="color:#22c55e">Allies (${d.allies.length}):</b> ${d.allies.slice(0, 12).join(' · ') || '—'}${d.allies.length > 12 ? ' …' : ''}</div>
            ${d.enemies.length ? `<div style="margin-top:4px"><b style="color:#ef4444">Tensions (${d.enemies.length}):</b> ${d.enemies.join(' · ')}</div>` : ''}
          </div>
        </div>` : ''}

        ${d.historicalGdpPc?.length > 5 ? `
        <div style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span style="font-size:10px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase">GDP/cap since ${d.historicalGdpPc[0][0]}</span>
            <span style="font-size:10px;color:#b8c1d1">${d.historicalGdpPc.length} samples</span>
          </div>
          <div style="background:rgba(0,0,0,0.25);padding:6px;border-radius:6px">${sparkline(d.historicalGdpPc, 340, 60)}</div>
        </div>` : ''}

      </div>
    `;
    el.style.display = 'block';
    document.getElementById('twDossierClose').onclick = hide;
  }

  // Track currently shown country for compare-mode shift-click
  let _currentIso3 = null;
  function show(iso3, opts) {
    opts = opts || {};
    if (opts.compare && _currentIso3 && _currentIso3 !== iso3) {
      renderCompare(_currentIso3, iso3);
      return;
    }
    _currentIso3 = iso3;
    render(iso3);
  }
  function hide() {
    if (_el) _el.style.display = 'none';
    _currentIso3 = null;
  }

  // ============================================================
  // Compare two countries side-by-side
  // ============================================================
  function renderCompare(isoA, isoB) {
    const el = ensure();
    const a = build(isoA), b = build(isoB);
    el.style.width = '720px';

    function statRow(label, valA, valB, fmt) {
      const fA = fmt && valA != null ? fmt(valA) : (valA != null ? valA : '—');
      const fB = fmt && valB != null ? fmt(valB) : (valB != null ? valB : '—');
      const winner = (typeof valA === 'number' && typeof valB === 'number')
        ? (valA > valB ? 'a' : valA < valB ? 'b' : 'tie') : null;
      return `<div style="display:grid;grid-template-columns:1fr 90px 1fr;gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
        <div style="text-align:right;font-feature-settings:'tnum' 1;color:${winner === 'a' ? '#22c55e' : '#cfe6ff'}">${fA}</div>
        <div style="text-align:center;font-size:9.5px;color:#8c95aa;letter-spacing:0.1em;text-transform:uppercase">${label}</div>
        <div style="text-align:left;font-feature-settings:'tnum' 1;color:${winner === 'b' ? '#22c55e' : '#cfe6ff'}">${fB}</div>
      </div>`;
    }

    el.innerHTML = `
      <div style="padding:14px 16px 10px;border-bottom:1px solid rgba(255,255,255,0.07);position:sticky;top:0;background:rgba(20,28,48,0.96);z-index:2">
        <div style="display:flex;justify-content:space-between;align-items:flex-start">
          <div style="text-align:right;flex:1">
            <div style="font-size:14px;font-weight:700">${a.name}</div>
            <div style="font-size:10px;color:#8c95aa">${a.iso3} · ${a.continent || ''}</div>
          </div>
          <div style="margin:0 16px;font-size:11px;color:#4cc2ff;letter-spacing:0.14em;text-transform:uppercase;font-weight:700">vs</div>
          <div style="flex:1">
            <div style="font-size:14px;font-weight:700">${b.name}</div>
            <div style="font-size:10px;color:#8c95aa">${b.iso3} · ${b.continent || ''}</div>
          </div>
          <button id="twDossierClose" style="background:none;border:0;color:#b8c1d1;font-size:22px;cursor:pointer;padding:0 0 0 12px;line-height:1">×</button>
        </div>
      </div>
      <div style="padding:14px 16px;overflow-y:auto;max-height:calc(100vh - 410px)">
        ${statRow('GDP',         a.gdp,         b.gdp,        v => '$' + fmtN(v, 1))}
        ${statRow('GDP/capita',  a.gdpPc,       b.gdpPc,      v => '$' + fmtN(v, 0))}
        ${statRow('Population',  a.population,  b.population, v => fmtN(v, 1))}
        ${statRow('Life exp.',   a.life,        b.life,       v => v.toFixed(1) + ' yr')}
        ${statRow('Inflation',   a.inflation,   b.inflation,  v => v.toFixed(1) + '%')}
        ${statRow('Debt %GDP',   a.debt,        b.debt,       v => v.toFixed(0) + '%')}
        ${statRow('Internet',    a.internet,    b.internet,   v => v.toFixed(0) + '%')}
        ${statRow('Urban',       a.urban,       b.urban,      v => v.toFixed(0) + '%')}
        ${statRow('Military',    a.military,    b.military,   v => v.toFixed(2) + '%')}
        ${statRow('CO₂/cap',     a.co2pc,       b.co2pc,      v => v.toFixed(1) + ' t')}
        ${statRow('Renewable',   a.renewable,   b.renewable,  v => v.toFixed(0) + '%')}
        ${statRow('Risk score',  a.composite,   b.composite,  v => v.toFixed(0))}
        ${statRow('Religion',    a.religionFamily,  b.religionFamily,  v => String(v))}
        ${statRow('Ethnicity',   a.ethnicityFamily, b.ethnicityFamily, v => String(v))}
        ${statRow('Bloc',        a.blocPrimary, b.blocPrimary, v => String(v))}
        ${statRow('Allies',      a.allies?.length, b.allies?.length, v => String(v))}
        ${statRow('Enemies',     a.enemies?.length, b.enemies?.length, v => String(v))}
        <div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);font-size:10.5px;color:#8c95aa;letter-spacing:0.1em;text-transform:uppercase">Top exports</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:6px;font-size:11px">
          <div>${a.exports.slice(0, 5).map(e => `<div style="color:#b8c1d1;padding:2px 0">${e.commodity_name || e.name || e}</div>`).join('') || '<div style="color:#6b7790">—</div>'}</div>
          <div>${b.exports.slice(0, 5).map(e => `<div style="color:#b8c1d1;padding:2px 0">${e.commodity_name || e.name || e}</div>`).join('') || '<div style="color:#6b7790">—</div>'}</div>
        </div>
      </div>
    `;
    el.style.display = 'block';
    document.getElementById('twDossierClose').onclick = () => {
      hide();
      el.style.width = '380px';   // restore single-country width
    };
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') hide();
  });

  window.showDossier = show;
  window.hideDossier = hide;
})();
