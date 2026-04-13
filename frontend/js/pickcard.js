// pickcard.js — Phase 2 scaffolding for Phase 8.
//
// Every layer renderer should eventually set `entity.properties.pickcard` to
// a normalized props object like:
//
//   {
//     title: 'Wildfire',
//     source_name: 'NASA FIRMS',
//     source_url: 'https://firms.modaps.eosdis.nasa.gov/',
//     fetched_at: '2026-04-11T19:54:05Z',
//     event_date: '2026-04-11T14:22:00Z',
//     location: 'São Paulo, Brazil',
//     values: [
//       { label: 'FRP',        value: '42 MW',         hint: 'Fire radiative power' },
//       { label: 'Confidence', value: 'high' },
//       { label: 'Satellite',  value: 'Suomi NPP' }
//     ],
//     category_color: '#ef4444'
//   }
//
// window.showPickCard(props) renders it in a floating card. One source of truth
// for click UX across 60+ renderers. Every card has date + source — always.
(function(){

  function fmt(dt) {
    if (!dt) return '—';
    try {
      const d = new Date(dt);
      if (isNaN(d.getTime())) return String(dt);
      return d.toISOString().replace('T', ' ').replace('Z', ' UTC').slice(0, 19);
    } catch { return String(dt); }
  }

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderPickCard(props) {
    const p = props || {};
    const color = p.category_color || 'var(--accent, #5eead4)';
    const vals = Array.isArray(p.values) ? p.values : [];

    const rows = vals.map(v => `
      <div class="pc-row">
        <div class="pc-row-label">${esc(v.label)}</div>
        <div class="pc-row-value">${esc(v.value)}</div>
      </div>
    `).join('');

    const sourceLine = p.source_url
      ? `<a href="${esc(p.source_url)}" target="_blank" rel="noopener">${esc(p.source_name || 'Source')} →</a>`
      : esc(p.source_name || '—');

    return `
      <div class="pc-head" style="border-left:3px solid ${color};">
        <div class="pc-title">${esc(p.title || 'Details')}</div>
        ${p.location ? `<div class="pc-location">${esc(p.location)}</div>` : ''}
      </div>
      <div class="pc-body">${rows}</div>
      <div class="pc-foot">
        <div class="pc-date-row">
          <div class="pc-date-label">Event</div>
          <div class="pc-date-value">${fmt(p.event_date)}</div>
        </div>
        <div class="pc-date-row">
          <div class="pc-date-label">Fetched</div>
          <div class="pc-date-value">${fmt(p.fetched_at)}</div>
        </div>
        <div class="pc-source">${sourceLine}</div>
      </div>
    `;
  }

  // Inject container + styles once
  function ensureContainer() {
    let el = document.getElementById('pickCard');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'pickCard';
    el.style.cssText = `
      position: fixed;
      top: 120px;
      right: 16px;
      width: 320px;
      max-height: 60vh;
      overflow-y: auto;
      background: rgba(12, 16, 28, 0.92);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255,255,255,0.12);
      border-radius: 10px;
      box-shadow: 0 10px 40px rgba(0,0,0,0.55);
      color: #e8edf3;
      font: 12px 'Inter', system-ui, sans-serif;
      z-index: 145;
      display: none;
      padding: 0;
    `;
    document.body.appendChild(el);

    // Inject styles for the inner layout
    const style = document.createElement('style');
    style.textContent = `
      #pickCard .pc-head { padding: 12px 14px 8px; }
      #pickCard .pc-title { font-size: 13px; font-weight: 700; color: #fff; }
      #pickCard .pc-location { font-size: 10px; color: #9ca3af; margin-top: 2px; }
      #pickCard .pc-body { padding: 8px 14px; border-top: 1px solid rgba(255,255,255,0.06); }
      #pickCard .pc-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 11px; }
      #pickCard .pc-row-label { color: #9ca3af; }
      #pickCard .pc-row-value { color: #e8edf3; font-weight: 600; }
      #pickCard .pc-foot { padding: 10px 14px; border-top: 1px solid rgba(255,255,255,0.06); background: rgba(0,0,0,0.2); }
      #pickCard .pc-date-row { display: flex; justify-content: space-between; font-size: 10px; color: #9ca3af; margin-bottom: 4px; }
      #pickCard .pc-date-value { font-family: 'JetBrains Mono', ui-monospace, monospace; color: #cbd5e1; }
      #pickCard .pc-source { margin-top: 6px; font-size: 11px; }
      #pickCard .pc-source a { color: #5eead4; text-decoration: none; }
      #pickCard .pc-source a:hover { text-decoration: underline; }
      #pickCard .pc-close {
        position: absolute; top: 8px; right: 10px;
        width: 22px; height: 22px; border: none;
        background: rgba(255,255,255,0.08); color: #fff;
        border-radius: 4px; cursor: pointer; font-size: 14px;
        line-height: 20px; padding: 0;
      }
      #pickCard .pc-close:hover { background: rgba(255,255,255,0.16); }
    `;
    document.head.appendChild(style);
    return el;
  }

  window.showPickCard = function(props) {
    const el = ensureContainer();
    el.innerHTML = '<button class="pc-close" title="Close">×</button>' + renderPickCard(props);
    el.style.display = 'block';
    el.querySelector('.pc-close').addEventListener('click', () => el.style.display = 'none');
  };

  window.hidePickCard = function() {
    const el = document.getElementById('pickCard');
    if (el) el.style.display = 'none';
  };

  // Convenience for renderers to build pickcard properties as a Cesium PropertyBag
  // so Cesium .properties.pickcard.getValue() returns the plain object we want.
  window.toPickCardProps = function(props) {
    return new Cesium.ConstantProperty(props);
  };

})();
