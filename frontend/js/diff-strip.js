// diff-strip.js — "Since you last looked" persistent diff strip.
//
// On first load: snapshots key signals to localStorage.
// On every subsequent load: compares now vs snapshot, surfaces meaningful
// deltas as clickable items in a single horizontal strip mounted at the
// top of the viewport (just under the masthead/header).
//
// Diff sources (all already cached):
//   * fred macros — count of series moving > 2σ since last visit
//   * ucdp_ged — new conflict events
//   * gdacs_events — new active hazards
//   * nhc_cyclones — storms formed/dissipated
//   * who_don — new disease outbreaks
//   * pulse_mode.top_concerning — countries that newly entered the top-5
//   * gemini_narrative.fetched — when the council last spoke
//
// Each item is clickable → flies the camera to the location (if it has
// one), activates the relevant mapmode, opens the Data Inspector.
(function(){
  const SNAP_KEY = 'tw_diff_snapshot_v1';
  const LAST_KEY = 'tw_diff_last_seen_v1';

  // Snapshot helpers
  function snapshotNow() {
    const cs = window._cacheStore;
    if (!cs) return null;
    const fred = cs.get('fred')?.series || {};
    const macroNow = {};
    for (const k of Object.keys(fred)) {
      macroNow[k] = fred[k]?.latest ?? null;
    }
    const pulse = cs.get('pulse_mode')?.top_concerning?.slice(0, 8).map(c => c.iso3) || [];
    return {
      t: Date.now(),
      macros: macroNow,
      pulse_top: pulse,
      ucdp_count: (cs.get('ucdp_ged')?.events || []).length,
      gdacs_count: (cs.get('gdacs_events')?.events || []).length,
      cyclone_names: (cs.get('nhc_cyclones')?.storms || []).map(s => s.name).filter(Boolean),
      who_titles: (cs.get('who_don')?.outbreaks || []).slice(0, 30).map(o => o.title || o.disease).filter(Boolean),
      narrative_fetched: cs.get('gemini_narrative')?.fetched || null,
    };
  }

  function loadSnapshot() {
    try { return JSON.parse(localStorage.getItem(SNAP_KEY) || 'null'); }
    catch { return null; }
  }
  function saveSnapshot(snap) {
    try { localStorage.setItem(SNAP_KEY, JSON.stringify(snap)); } catch {}
  }

  function fmtSince(t) {
    if (!t) return 'just now';
    const ms = Date.now() - t;
    const m = Math.floor(ms / 60000);
    if (m < 1) return 'moments ago';
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    const d = Math.floor(h / 24);
    return `${d}d ago`;
  }

  // Compare two snapshots, return list of diff items: { kind, label, value, path?, focus?, source }
  function computeDiff(prev, now) {
    const items = [];
    if (!prev || !now) return items;

    // Macros >2σ — approximated as |Δ| > 1% for daily, > 2.5% for monthly
    let macroMoves = 0;
    const movers = [];
    for (const k of Object.keys(now.macros)) {
      const a = prev.macros[k], b = now.macros[k];
      if (a == null || b == null) continue;
      if (a === 0) continue;
      const pct = (b - a) / Math.abs(a) * 100;
      if (Math.abs(pct) >= 1.0) {
        macroMoves++;
        movers.push({ k, pct, b });
      }
    }
    if (macroMoves > 0) {
      movers.sort((x, y) => Math.abs(y.pct) - Math.abs(x.pct));
      const top = movers[0];
      items.push({
        kind: 'markets',
        label: `${macroMoves} markets moved`,
        value: `${top.k} ${top.pct >= 0 ? '+' : ''}${top.pct.toFixed(2)}%`,
        source: 'FRED',
        path: `macros[?label=${top.k}].latest`,
      });
    }

    // New conflict events
    const ucdpDelta = now.ucdp_count - prev.ucdp_count;
    if (ucdpDelta > 0) {
      items.push({
        kind: 'conflict',
        label: 'new conflict events',
        value: `+${ucdpDelta}`,
        source: 'UCDP',
      });
    }

    // GDACS hazards
    const gdacsDelta = now.gdacs_count - prev.gdacs_count;
    if (gdacsDelta !== 0) {
      items.push({
        kind: 'hazard',
        label: gdacsDelta > 0 ? 'new active hazards' : 'hazards resolved',
        value: `${gdacsDelta > 0 ? '+' : ''}${gdacsDelta}`,
        source: 'GDACS',
      });
    }

    // Cyclones — formed / dissipated
    const prevSet = new Set(prev.cyclone_names);
    const nowSet = new Set(now.cyclone_names);
    const formed = now.cyclone_names.filter(n => !prevSet.has(n));
    const dissipated = prev.cyclone_names.filter(n => !nowSet.has(n));
    if (formed.length) {
      items.push({ kind: 'cyclone', label: 'cyclone formed', value: formed[0], source: 'NHC' });
    }
    if (dissipated.length) {
      items.push({ kind: 'cyclone', label: 'cyclone dissipated', value: dissipated[0], source: 'NHC' });
    }

    // WHO — new outbreaks
    const prevWHO = new Set(prev.who_titles);
    const newWHO = now.who_titles.filter(t => !prevWHO.has(t));
    if (newWHO.length) {
      items.push({
        kind: 'health',
        label: 'new disease outbreak',
        value: newWHO[0].length > 50 ? newWHO[0].slice(0, 50) + '…' : newWHO[0],
        source: 'WHO',
      });
    }

    // Pulse top-5 — countries newly entering the worst-5
    const prevPulse = new Set(prev.pulse_top.slice(0, 5));
    const newWorst = now.pulse_top.slice(0, 5).filter(iso => !prevPulse.has(iso));
    if (newWorst.length) {
      items.push({
        kind: 'pulse',
        label: 'newly concerning',
        value: newWorst.join(', '),
        source: 'Pulse',
      });
    }

    // Narrative refreshed?
    if (prev.narrative_fetched && now.narrative_fetched && prev.narrative_fetched !== now.narrative_fetched) {
      items.push({
        kind: 'council',
        label: 'council reconvened',
        value: 'new reading',
        source: 'WorldTwin',
      });
    }

    return items;
  }

  function render(prev, items) {
    let el = document.getElementById('twDiffStrip');
    if (!el) {
      el = document.createElement('div');
      el.id = 'twDiffStrip';
      el.className = 'tw-diff';
      document.body.appendChild(el);
    }

    const since = (prev && prev.t) ? fmtSince(prev.t) : 'first visit';
    if (!items.length) {
      const msg = (prev && prev.t)
        ? 'Quiet on every channel.'
        : 'Welcome — this strip will surface what changes between visits.';
      el.innerHTML = `
        <div class="tw-diff-eyebrow">Since you last looked · <span class="tw-diff-since">${since}</span></div>
        <div class="tw-diff-quiet">${msg}</div>`;
      el.classList.add('tw-diff-on');
      return;
    }
    el.innerHTML = `
      <div class="tw-diff-eyebrow">Since you last looked · <span class="tw-diff-since">${since}</span></div>
      <div class="tw-diff-items">
        ${items.map((it, i) => `
          <button class="tw-diff-item tw-diff-${it.kind}" data-idx="${i}">
            <span class="tw-diff-glyph">${glyphFor(it.kind)}</span>
            <span class="tw-diff-lbl">${escapeHtml(it.label)}</span>
            <span class="tw-diff-v">${escapeHtml(it.value)}</span>
            <span class="tw-diff-src">${escapeHtml(it.source)}</span>
          </button>`).join('')}
      </div>`;
    el.classList.add('tw-diff-on');

    // Wire clicks → Data Inspector
    el.querySelectorAll('.tw-diff-item').forEach((btn, i) => {
      btn.addEventListener('click', () => {
        const it = items[i];
        if (window.DataInspector?.open) {
          window.DataInspector.open({
            label: it.label,
            value: it.value,
            source: it.source,
            path: it.path || '',
            voice: 'Diff strip',
          });
        }
      });
    });
  }

  function glyphFor(kind) {
    return ({
      markets: '$', conflict: '⚔', hazard: '⚠', cyclone: '◷',
      health: '✚', pulse: '◉', council: '※',
    })[kind] || '·';
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  // Run after caches have populated
  function tick() {
    const now = snapshotNow();
    if (!now) { setTimeout(tick, 1500); return; }
    const prev = loadSnapshot();
    const items = computeDiff(prev, now);
    render(prev, items);
    // Update last-seen on EVERY render, but only update SNAPSHOT once user
    // explicitly dismisses (so the diff persists across reloads in one session)
    try { localStorage.setItem(LAST_KEY, String(Date.now())); } catch {}
    // First-ever visit: seed the snapshot so next visit has something to diff against
    if (!prev) saveSnapshot(now);
  }

  function commit() {
    const now = snapshotNow();
    if (now) saveSnapshot(now);
    const el = document.getElementById('twDiffStrip');
    if (el) el.classList.remove('tw-diff-on');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(tick, 4500));
  } else {
    setTimeout(tick, 4500);
  }

  window.DiffStrip = { tick, commit, snapshotNow };
})();
