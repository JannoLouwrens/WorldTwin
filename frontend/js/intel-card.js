// intel-card.js — Country Intelligence Card.
//
// When user clicks any country (in any mode), shows a rich intelligence panel
// combining data from ALL 75 sources into: risk radar, trends, peer comparison,
// dependencies, and alerts. Replaces the basic country card.
(function(){

  function riskLabel(v) {
    if (v >= 0.7) return ['Critical', '#dc2626'];
    if (v >= 0.5) return ['High', '#ef4444'];
    if (v >= 0.3) return ['Medium', '#f97316'];
    if (v >= 0.15) return ['Low', '#facc15'];
    return ['Minimal', '#22c55e'];
  }

  function riskBar(val, maxW) {
    const w = Math.max(2, Math.round(val * maxW));
    const [, color] = riskLabel(val);
    return `<div style="height:8px;width:${w}px;background:${color};border-radius:4px;display:inline-block;vertical-align:middle"></div>`;
  }

  function fmtNum(n) {
    if (n == null) return '—';
    if (Math.abs(n) >= 1e12) return (n / 1e12).toFixed(1) + 'T';
    if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return typeof n === 'number' ? n.toFixed(1) : String(n);
  }

  function trendIcon(t) {
    const map = {
      growing: '↗', slow_growth: '→', stagnant: '→', contracting: '↘',
      rising: '↗', declining: '↘', stable: '→', high: '⚠', moderate: '•', low: '·', none: '✓',
    };
    return map[t] || '?';
  }

  function buildIntelCard(iso3) {
    const intel = window._cacheStore && window._cacheStore.get('country_intel');
    if (!intel || !intel.countries) return null;
    const c = intel.countries[iso3];
    if (!c) return null;

    const s = c.snapshot || {};
    const r = c.risks || {};
    const t = c.trends || {};
    const deps = c.dependencies || {};
    const alerts = c.alerts || [];
    const peers = c.peers || [];
    const peerRank = c.peer_rank || {};

    // Risk radar
    const riskTypes = [
      ['Conflict', r.conflict], ['Hazard', r.natural_hazard], ['Energy', r.energy],
      ['Food', r.food], ['Displacement', r.displacement], ['Economy', r.economic_downturn],
      ['Climate', r.climate],
    ];
    const riskRows = riskTypes.map(([label, val]) => {
      const [lvl, col] = riskLabel(val || 0);
      return `<div class="ic-risk-row">
        <span class="ic-risk-label">${label}</span>
        ${riskBar(val || 0, 80)}
        <span class="ic-risk-lvl" style="color:${col}">${lvl}</span>
      </div>`;
    }).join('');

    // Composite score
    const [compLabel, compColor] = riskLabel(r.composite || 0);

    // Snapshot stats
    const stats = [
      ['GDP', fmtNum(s.gdp_usd) + (s.gdp_usd ? ' USD' : '')],
      ['GDP/cap', fmtNum(s.gdp_per_capita) + (s.gdp_per_capita ? ' USD' : '')],
      ['Population', fmtNum(s.population)],
      ['Growth', s.gdp_growth_pct != null ? s.gdp_growth_pct.toFixed(1) + '%' : '—'],
      ['Inflation', s.inflation_pct != null ? s.inflation_pct.toFixed(1) + '%' : '—'],
      ['Life exp', s.life_expectancy != null ? s.life_expectancy.toFixed(1) + ' yr' : '—'],
      ['Renewable', s.renewable_pct != null ? s.renewable_pct.toFixed(1) + '%' : '—'],
      ['CO₂/cap', s.co2_per_capita != null ? s.co2_per_capita.toFixed(1) + ' t' : '—'],
      ['Military', s.military_spend_pct != null ? s.military_spend_pct.toFixed(1) + '% GDP' : '—'],
      ['Internet', s.internet_pct != null ? s.internet_pct.toFixed(0) + '%' : '—'],
    ];
    if (s.electricity_price_eur) stats.push(['Elec price', s.electricity_price_eur.toFixed(0) + ' EUR/MWh']);
    if (s.generation_mw) stats.push(['Generation', (s.generation_mw / 1000).toFixed(1) + ' GW']);

    const statRows = stats.filter(([, v]) => v && v !== '—').map(([k, v]) =>
      `<div class="ic-stat"><span class="ic-stat-k">${k}</span><span class="ic-stat-v">${v}</span></div>`
    ).join('');

    // Trends
    const trendRows = Object.entries(t).map(([k, v]) =>
      `<span class="ic-trend">${trendIcon(v)} ${k}</span>`
    ).join(' ');

    // Peers
    let peerHtml = '';
    if (peers.length) {
      const peerNames = peers.filter(p => p !== iso3).slice(0, 4).join(', ');
      const rankRows = Object.entries(peerRank).map(([metric, data]) => {
        const label = metric.replace(/_/g, ' ');
        return `<span class="ic-peer-rank">${label}: #${data.rank}/${data.of}</span>`;
      }).join(' · ');
      peerHtml = `<div class="ic-section">
        <div class="ic-section-title">PEERS</div>
        <div class="ic-peer-list">${peerNames}</div>
        <div class="ic-peer-ranks">${rankRows}</div>
      </div>`;
    }

    // Dependencies
    let depHtml = '';
    const depParts = [];
    if (deps.trade_partners && deps.trade_partners.length) {
      depParts.push('Trade: ' + deps.trade_partners.join(', '));
    }
    if (deps.top_exports && deps.top_exports.length) {
      depParts.push('Exports: ' + deps.top_exports.slice(0, 3).join(', '));
    }
    if (deps.energy_imports && deps.energy_imports.length) {
      const eImports = deps.energy_imports.map(e => e.from + ' ' + (e.mw / 1000).toFixed(1) + 'GW').join(', ');
      depParts.push('Energy imports: ' + eImports);
    }
    if (deps.energy_exports && deps.energy_exports.length) {
      const eExports = deps.energy_exports.map(e => e.to + ' ' + (e.mw / 1000).toFixed(1) + 'GW').join(', ');
      depParts.push('Energy exports: ' + eExports);
    }
    if (depParts.length) {
      depHtml = `<div class="ic-section">
        <div class="ic-section-title">DEPENDENCIES</div>
        ${depParts.map(d => `<div class="ic-dep-row">${d}</div>`).join('')}
      </div>`;
    }

    // Alerts
    let alertHtml = '';
    if (alerts.length) {
      const sevIcons = { high: '🔴', medium: '🟡', low: '🟢', info: 'ℹ️' };
      alertHtml = `<div class="ic-section ic-alerts">
        <div class="ic-section-title">ALERTS</div>
        ${alerts.map(a => `<div class="ic-alert">${sevIcons[a.severity] || '•'} <b>${a.type}</b>: ${a.text}</div>`).join('')}
      </div>`;
    }

    // Global context
    const gc = intel.global_context || {};
    let globalLine = '';
    if (gc.temp_anomaly_c != null) {
      globalLine = `<div class="ic-global">Global temp anomaly: +${gc.temp_anomaly_c.toFixed(2)}°C (${gc.temp_anomaly_year}) · ${gc.total_conflict_events || 0} conflict events · ${gc.total_disaster_alerts || 0} disaster alerts</div>`;
    }

    return `
      <div class="ic-header">
        <div class="ic-country">${c.name}</div>
        <div class="ic-region">${c.subregion || c.region || ''}</div>
        <div class="ic-composite">Overall risk: <b style="color:${compColor}">${compLabel}</b> (${(r.composite * 100).toFixed(0)}%)</div>
      </div>
      <div class="ic-section">
        <div class="ic-section-title">RISK RADAR</div>
        ${riskRows}
      </div>
      <div class="ic-section">
        <div class="ic-section-title">SNAPSHOT</div>
        <div class="ic-stats">${statRows}</div>
      </div>
      <div class="ic-section">
        <div class="ic-section-title">TRENDS</div>
        <div class="ic-trends">${trendRows || '—'}</div>
      </div>
      ${peerHtml}
      ${depHtml}
      ${alertHtml}
      ${globalLine}
      <div class="ic-footer">Sources: World Bank · IMF · UCDP · GDACS · ENTSO-E · EIA · OWID · IDMC · FAO · Berkeley Earth · OECD · PortWatch</div>
    `;
  }

  // Inject styles
  function injectStyles() {
    if (document.getElementById('ic-styles')) return;
    const style = document.createElement('style');
    style.id = 'ic-styles';
    style.textContent = `
      #intelCard {
        position: fixed; top: 120px; right: 16px; width: 360px; max-height: 75vh;
        overflow-y: auto; background: rgba(8,12,24,0.94); backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
        box-shadow: 0 12px 48px rgba(0,0,0,0.6); color: #e8edf3;
        font: 12px 'Inter', system-ui, sans-serif; z-index: 146; display: none; padding: 0;
      }
      .ic-header { padding: 14px 16px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); }
      .ic-country { font-size: 16px; font-weight: 700; color: #fff; }
      .ic-region { font-size: 10px; color: #9ca3af; margin-top: 2px; }
      .ic-composite { margin-top: 6px; font-size: 11px; color: #cbd5e1; }
      .ic-section { padding: 10px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); }
      .ic-section-title { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.12em; color: #5eead4; margin-bottom: 6px; }
      .ic-risk-row { display: flex; align-items: center; gap: 8px; padding: 2px 0; font-size: 10px; }
      .ic-risk-label { width: 70px; color: #9ca3af; flex-shrink: 0; }
      .ic-risk-lvl { font-size: 9px; font-weight: 600; margin-left: auto; }
      .ic-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; }
      .ic-stat { display: flex; justify-content: space-between; font-size: 10px; padding: 2px 0; }
      .ic-stat-k { color: #9ca3af; }
      .ic-stat-v { color: #e8edf3; font-weight: 600; font-family: 'JetBrains Mono', monospace; }
      .ic-trends { font-size: 11px; color: #cbd5e1; }
      .ic-trend { margin-right: 8px; }
      .ic-peer-list { font-size: 10px; color: #cbd5e1; margin-bottom: 4px; }
      .ic-peer-ranks { font-size: 9px; color: #9ca3af; }
      .ic-peer-rank { margin-right: 6px; }
      .ic-dep-row { font-size: 10px; color: #cbd5e1; padding: 2px 0; }
      .ic-alerts { background: rgba(239,68,68,0.04); }
      .ic-alert { font-size: 10px; color: #cbd5e1; padding: 3px 0; line-height: 1.4; }
      .ic-global { padding: 8px 16px; font-size: 9px; color: #6b7280; background: rgba(0,0,0,0.2); }
      .ic-footer { padding: 8px 16px; font-size: 8px; color: #4b5563; }
      .ic-close { position: absolute; top: 10px; right: 12px; width: 24px; height: 24px; border: none;
        background: rgba(255,255,255,0.06); color: #fff; border-radius: 6px; cursor: pointer; font-size: 14px; }
      .ic-close:hover { background: rgba(255,255,255,0.12); }
    `;
    document.head.appendChild(style);
  }

  function ensureContainer() {
    let el = document.getElementById('intelCard');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'intelCard';
    document.body.appendChild(el);
    return el;
  }

  function showIntelCard(iso3) {
    injectStyles();
    const el = ensureContainer();
    const html = buildIntelCard(iso3);
    if (!html) {
      // Fall back to basic country card if no intel data
      if (window.showCountryCard) window.showCountryCard(iso3);
      return;
    }
    // Dismiss other popups
    if (window.dismissAllPopups) window.dismissAllPopups();
    el.innerHTML = '<button class="ic-close" title="Close">&times;</button>' + html;
    el.style.display = 'block';
    el.querySelector('.ic-close').addEventListener('click', () => el.style.display = 'none');
  }

  function hideIntelCard() {
    const el = document.getElementById('intelCard');
    if (el) el.style.display = 'none';
  }

  window.showIntelCard = showIntelCard;
  window.hideIntelCard = hideIntelCard;
})();
