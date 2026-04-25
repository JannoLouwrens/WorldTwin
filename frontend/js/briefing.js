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
    Object.assign(el.style, {
      position: 'fixed', left: '96px', bottom: '200px',
      width: '420px',
      background: 'linear-gradient(180deg, rgba(20,28,48,0.94), rgba(14,19,32,0.96))',
      border: '1px solid rgba(76,194,255,0.25)',
      borderRadius: '12px',
      backdropFilter: 'blur(16px)',
      boxShadow: '0 12px 36px rgba(0,0,0,0.55)',
      color: '#f5f7fa',
      font: '12px Inter, sans-serif',
      zIndex: 80,
      overflow: 'hidden',
    });
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
      const dColor = delta == null ? '#8c95aa' : delta >= 0 ? '#22c55e' : '#ef4444';
      return `<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:6px;padding:6px 8px;flex:1;min-width:0">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <div style="font-size:9px;color:#8c95aa;letter-spacing:0.1em;text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${card.label}</div>
          <div style="font-size:9px;color:${dColor};font-feature-settings:'tnum' 1">${delta == null ? '' : fmtPct(delta)}</div>
        </div>
        <div style="font-size:13px;font-weight:600;font-feature-settings:'tnum' 1;color:#f5f7fa">${card.v != null ? card.v.toFixed(card.unit === '%' || card.label === 'VIX' ? 2 : 1) : '—'}<span style="font-size:9px;color:#8c95aa;margin-left:2px">${card.unit}</span></div>
        <div style="margin-top:2px;height:18px">${spark(card.s, 90, 18, card.c)}</div>
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
      <div style="padding:9px 14px;border-bottom:1px solid rgba(255,255,255,0.08);display:flex;justify-content:space-between;align-items:center;cursor:pointer" id="twBriefHead">
        <div style="display:flex;align-items:center;gap:8px">
          <span style="width:8px;height:8px;border-radius:50%;background:#4cc2ff;box-shadow:0 0 10px rgba(76,194,255,0.7)"></span>
          <span style="font-weight:700;letter-spacing:0.06em;font-size:11px;text-transform:uppercase">World Briefing</span>
          <span style="color:#8c95aa;font-size:10px">${gem?.fetched ? gem.fetched.slice(11, 16) + 'Z' : ''}</span>
        </div>
        <div style="color:#8c95aa;font-size:14px" id="twBriefToggle">${_collapsed ? '▸' : '▾'}</div>
      </div>
      <div id="twBriefBody" style="display:${_collapsed ? 'none' : 'block'}">
        ${today ? `<div style="padding:10px 14px 8px;color:#cfe6ff;font-size:11.5px;line-height:1.5;border-bottom:1px solid rgba(255,255,255,0.05);font-style:italic">${today}</div>` : ''}

        ${truth.length ? `<div style="padding:7px 14px;border-bottom:1px solid rgba(255,255,255,0.05);background:rgba(34,197,94,0.04)">
          <div style="font-size:9px;color:#22c55e;letter-spacing:0.16em;text-transform:uppercase;font-weight:700;margin-bottom:4px">By the numbers · ground truth</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px">${truth.map(t => `
            <span style="font-size:10.5px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);padding:2px 7px;border-radius:5px;color:#cfe6ff;font-feature-settings:'tnum' 1">
              <span style="color:#8c95aa">${t.label}:</span> <b style="color:#f5f7fa">${t.val}</b> <span style="color:#6b7790;font-size:9px">${t.src}</span>
            </span>`).join('')}</div>
        </div>` : ''}

        <div style="padding:8px 12px 4px;display:flex;gap:5px;border-bottom:1px solid rgba(255,255,255,0.05)">${kpis}</div>

        <div style="padding:8px 14px 10px">
          <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:5px">
            <div style="font-size:9px;color:#8c95aa;letter-spacing:0.14em;text-transform:uppercase;font-weight:700">Most concerning</div>
            <div style="font-size:9px;color:#8c95aa">${concerns.length} countries</div>
          </div>
          ${concerns.map(c => {
            const score = c.composite || 0;
            const color = score >= 70 ? '#dc2626' : score >= 50 ? '#ef4444' : score >= 30 ? '#f97316' : score >= 15 ? '#facc15' : '#22c55e';
            return `<div style="display:flex;align-items:center;gap:8px;padding:3px 0;cursor:pointer" data-iso3="${c.iso3 || ''}" class="tw-brief-concern">
              <div style="width:30px;height:6px;background:rgba(255,255,255,0.06);border-radius:3px;overflow:hidden">
                <div style="width:${Math.min(100, score)}%;height:100%;background:${color}"></div>
              </div>
              <div style="font-weight:600;color:#f5f7fa;font-size:12px;flex:1">${c.name || c.iso3}</div>
              <div style="font-size:11px;color:${color};font-weight:600;font-feature-settings:'tnum' 1">${score.toFixed(0)}</div>
              ${c.trend ? `<div style="font-size:10px;color:${c.trend === 'rising' ? '#ef4444' : '#8c95aa'}">${c.trend === 'rising' ? '↑' : c.trend === 'ok' ? '·' : '↓'}</div>` : ''}
            </div>`;
          }).join('') || '<div style="color:#6b7790;font-style:italic;font-size:11px">No data</div>'}
        </div>
      </div>
    `;

    el.querySelector('#twBriefHead').onclick = () => {
      _collapsed = !_collapsed;
      build();
    };
    el.querySelectorAll('.tw-brief-concern').forEach(row => {
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
