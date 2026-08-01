// briefing.js — "World Briefing" panel: today's AI summary + macros + concerns.
//
// Composes 4 caches that previously had no UI surface:
//   * gemini_narrative   — Gemini 2.5 Flash daily summary (today / biggest_risk / trend_of_week)
//   * fred               — 30+ US/EU macro time series (oil, USD, VIX, Fed funds, ...)
//   * commodity_prices   — Brent, gold, etc. (extra commodity prices)
//   * pulse_mode.top_concerning — countries with highest composite risk
//
// Layout: fixed bottom-left, collapsible. Mini sparklines for each macro.
// Auto-refreshes every 30s from the live cache store.
(function(){
  let _el = null;
  let _collapsed = false;
  let _refreshT = null;

  function ensure() {
    if (_el) return _el;
    const el = document.createElement('div');
    el.id = 'twBriefing';
    el.className = 'tw-brief';
    document.body.appendChild(el);
    _el = el;
    return el;
  }

  function fmtPct(v) { return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
  function fmtN(n, d = 1) {
    if (n == null || !Number.isFinite(n)) return '—';
    if (Math.abs(n) >= 1e12) return (n/1e12).toFixed(d) + 'T';
    if (Math.abs(n) >= 1e9)  return (n/1e9).toFixed(d)  + 'B';
    if (Math.abs(n) >= 1e6)  return (n/1e6).toFixed(d)  + 'M';
    if (Math.abs(n) >= 1e3)  return (n/1e3).toFixed(d)  + 'K';
    return n.toFixed(d);
  }
  function spark(series, w, h, color) {
    if (!series || series.length < 2) return '';
    // Filter non-finite samples FIRST, then index from there. Otherwise the path
    // can start with 'L' which is invalid SVG (must start with 'M').
    const clean = (series || []).filter(s => s && Number.isFinite(s.v));
    if (clean.length < 2) return '';
    const ys = clean.map(s => s.v);
    const yMin = Math.min(...ys), yMax = Math.max(...ys);
    const pad = (yMax - yMin) * 0.05 || 0.001;
    const norm = v => h - ((v - yMin + pad) / (yMax - yMin + pad * 2)) * h;
    const path = clean.map((s, i) => {
      const x = (i / (clean.length - 1)) * w;
      return `${i ? 'L' : 'M'}${x.toFixed(1)} ${norm(s.v).toFixed(1)}`;
    }).join(' ');
    return `<svg width="${w}" height="${h}" style="display:block">
      <path d="${path}" fill="none" stroke="${color || '#4cc2ff'}" stroke-width="1.5" stroke-linejoin="round"/>
    </svg>`;
  }

  function getFRED(key) {
    return window._cacheStore?.get('fred')?.series?.[key];
  }

  // The 5 macros people actually want to see at a glance.
  function buildKPIs() {
    const oil  = getFRED('DCOILBRENTEU');     // Brent crude
    const vix  = getFRED('VIXCLS');           // Volatility
    const usd  = getFRED('DTWEXBGS');         // Trade-weighted USD
    const fed  = getFRED('FEDFUNDS');         // Fed funds rate
    const ten  = getFRED('DGS10');            // US 10Y yield
    const cards = [
      { label: 'Brent oil',       v: oil?.latest, unit: '$/bbl', s: oil?.series, c: '#f97316' },
      { label: 'VIX',             v: vix?.latest, unit: '',      s: vix?.series, c: '#facc15' },
      { label: 'Trade-wt USD',    v: usd?.latest, unit: '',      s: usd?.series, c: '#22c55e' },
      { label: 'Fed funds',       v: fed?.latest, unit: '%',     s: fed?.series, c: '#a855f7' },
      { label: 'US 10Y',          v: ten?.latest, unit: '%',     s: ten?.series, c: '#06b6d4' },
    ];
    return cards.map(card => {
      const last = card.s?.[card.s.length - 1]?.v;
      const first = card.s?.[0]?.v;
      const delta = (last != null && first != null) ? ((last - first) / Math.abs(first)) * 100 : null;
      const dCls = delta == null ? 'tw-d-flat' : delta >= 0 ? 'tw-d-up' : 'tw-d-dn';
      return `<div class="tw-kpi">
        <div class="tw-kpi-row">
          <div class="tw-kpi-lbl">${card.label}</div>
          <div class="tw-kpi-d ${dCls}">${delta == null ? '' : fmtPct(delta)}</div>
        </div>
        <div class="tw-kpi-v">${card.v != null ? card.v.toFixed(card.unit === '%' || card.label === 'VIX' ? 2 : 1) : '—'}<span class="tw-kpi-unit">${card.unit}</span></div>
        <div class="tw-kpi-spark">${spark(card.s, 90, 18, card.c)}</div>
      </div>`;
    }).join('');
  }

  function buildConcerns() {
    const pulse = window._cacheStore?.get('pulse_mode');
    const top = pulse?.top_concerning?.slice(0, 5) || [];
    if (!top.length) {
      // Fallback: derive from countries
      const countries = pulse?.countries || {};
      const sorted = Object.values(countries)
        .filter(c => c.composite != null)
        .sort((a, b) => b.composite - a.composite)
        .slice(0, 5);
      return sorted.map(c => ({
        iso3: c.iso3, name: c.name, composite: c.composite, trend: c.trend,
      }));
    }
    return top;
  }

  // "By the numbers" — pulls measured data directly from caches (never the LLM).
  // Provides ground-truth that the user can cross-check against the AI narrative.
  function buildGroundTruth() {
    const items = [];

    // Strait of Hormuz vs 30d avg (PortWatch)
    const pw = window._cacheStore?.get('portwatch_chokepoints');
    const hormuz = (pw?.chokepoints || []).find(c => /hormuz/i.test(c.name));
    if (hormuz?.n_total != null) items.push({ label: 'Hormuz', val: hormuz.n_total + ' ships', src: 'PortWatch' });
    const suez = (pw?.chokepoints || []).find(c => /suez|panama/i.test(c.name));
    if (suez?.n_total != null) items.push({ label: suez.name.split(' ')[0], val: suez.n_total + ' ships', src: 'PortWatch' });

    // Conflict 24h
    const dig = window._cacheStore?.get('gemini_narrative')?.digest;
    if (dig?.conflict_24h?.event_count != null) {
      items.push({ label: 'Conflict 24h', val: dig.conflict_24h.event_count + ' events · ~' + dig.conflict_24h.fatalities_estimated + ' deaths', src: 'UCDP' });
    }

    // Biggest quake
    const q = window._cacheStore?.get('quakes')?.features || [];
    const big = q.map(f => ({ mag: f.properties?.mag, place: f.properties?.place })).filter(x => x.mag != null).sort((a,b) => b.mag - a.mag)[0];
    if (big) items.push({ label: 'Biggest quake', val: 'M' + big.mag.toFixed(1), src: 'USGS' });

    // Active GDACS hazards
    const gd = window._cacheStore?.get('gdacs_events');
    if (gd?.events?.length != null) items.push({ label: 'Active hazards', val: String(gd.events.length), src: 'GDACS' });

    // Brent crude
    const oil = window._cacheStore?.get('fred')?.series?.DCOILBRENTEU;
    if (oil?.latest != null) items.push({ label: 'Brent', val: '$' + oil.latest.toFixed(1), src: 'FRED' });

    return items;
  }

  function build() {
    const el = ensure();
    const gem = window._cacheStore?.get('gemini_narrative');
    const today = gem?.today || gem?.raw?.split('\n\n')[0] || '';
    const concerns = buildConcerns();
    const kpis = buildKPIs();
    const truth = buildGroundTruth();

    el.innerHTML = `
      <div class="tw-brief-head" id="twBriefHead">
        <div class="tw-brief-headleft">
          <span class="tw-brief-pulse"></span>
          <span class="tw-brief-title">World Briefing</span>
          <span class="tw-brief-stamp">${gem?.fetched ? gem.fetched.slice(11, 16) + 'Z' : ''}</span>
        </div>
        <div class="tw-brief-toggle" id="twBriefToggle">${_collapsed ? '+' : '−'}</div>
      </div>
      <div id="twBriefBody" class="tw-brief-body${_collapsed ? ' tw-collapsed' : ''}">
        ${today ? `<div class="tw-brief-section tw-brief-summary"><div class="tw-brief-grouplabel">Today</div><div class="tw-brief-summarytext">${today}</div></div>` : ''}

        ${truth.length ? `<div class="tw-brief-section tw-brief-truth">
          <div class="tw-brief-grouplabel tw-brief-grouplabel-truth">By the numbers · ground truth</div>
          <div class="tw-brief-chips">${truth.map(t => `
            <span class="tw-chip"><span class="tw-chip-lbl">${t.label}:</span> <b class="tw-chip-v">${t.val}</b> <span class="tw-chip-src">${t.src}</span></span>`).join('')}</div>
        </div>` : ''}

        <div class="tw-brief-section tw-brief-kpis-wrap">
          <div class="tw-brief-grouplabel">Macros</div>
          <div class="tw-brief-kpis">${kpis}</div>
        </div>

        <div class="tw-brief-section tw-brief-concerns-wrap">
          <div class="tw-brief-headerrow">
            <div class="tw-brief-grouplabel">Most concerning</div>
            <div class="tw-brief-meta">${concerns.length} countries</div>
          </div>
          ${concerns.map(c => {
            const score = c.composite || 0;
            const sevCls = score >= 70 ? 'tw-sev-x' : score >= 50 ? 'tw-sev-h' : score >= 30 ? 'tw-sev-m' : score >= 15 ? 'tw-sev-l' : 'tw-sev-ok';
            return `<div class="tw-concern ${sevCls}" data-iso3="${c.iso3 || ''}">
              <div class="tw-concern-bar"><div class="tw-concern-fill" style="width:${Math.min(100, score)}%"></div></div>
              <div class="tw-concern-name">${c.name || c.iso3}</div>
              <div class="tw-concern-score">${score.toFixed(0)}</div>
              ${c.trend ? `<div class="tw-concern-trend tw-trend-${c.trend}">${c.trend === 'rising' ? '↑' : c.trend === 'ok' ? '·' : '↓'}</div>` : ''}
            </div>`;
          }).join('') || '<div class="tw-brief-empty">No data</div>'}
        </div>
      </div>
    `;

    el.querySelector('#twBriefHead').onclick = () => {
      _collapsed = !_collapsed;
      build();
    };
    el.querySelectorAll('.tw-concern').forEach(row => {
      row.onclick = (e) => {
        e.stopPropagation();
        const iso3 = row.dataset.iso3;
        if (iso3 && window.showDossier) window.showDossier(iso3);
      };
    });
  }

  function start() {
    build();
    if (_refreshT) clearInterval(_refreshT);
    _refreshT = setInterval(build, 30000);
  }

  // Wait for caches before first build
  function waitAndStart() {
    if (window._cacheStore?.get('gemini_narrative') || window._cacheStore?.get('fred') || window._cacheStore?.get('pulse_mode')) {
      start();
    } else {
      setTimeout(waitAndStart, 800);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(waitAndStart, 1500));
  } else {
    setTimeout(waitAndStart, 1500);
  }

  window.Briefing = { build, start, hide: () => _el && (_el.style.display = 'none'), show: () => _el && (_el.style.display = 'block') };
})();
