// raw-mode.js — "Trust nobody, including me" mode.
//
// Vision: A lab where anyone — from the king of Rome to a sceptical
// citizen — can read the world from raw, dated, cross-checked sources
// instead of someone else's framing, and trace every claim back to the
// instrument that measured it.
//
// Press Alt+R to toggle. In raw mode every prose element is hidden:
//   - Council voice headlines + reading text (the LLM's framing)
//   - World Briefing AI summary paragraph
//   - Top-of-screen narrative ticker
//   - Hover tooltip's qualitative labels (kept the numbers, hide the prose)
//
// Citations, KPI numbers, ground-truth chips, the pollution inset, the
// hover tooltip's value+date+source row, and the Inspector ALL stay
// visible. The user is reading numbers, not narrative.
//
// A persistent indicator pill in the top-right shows when RAW MODE is on
// so the user is never confused about which version they're looking at.
(function(){
  let _on = false;

  function ensureIndicator() {
    let el = document.getElementById('twRawIndicator');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'twRawIndicator';
    el.className = 'tw-raw-indicator';
    el.innerHTML = `
      <span class="tw-raw-dot"></span>
      <span class="tw-raw-lbl">RAW MODE</span>
      <span class="tw-raw-meta">prose hidden · numbers + dates + sources only</span>
      <span class="tw-raw-kbd">Alt+R</span>`;
    document.body.appendChild(el);
    return el;
  }

  function setMode(on) {
    _on = !!on;
    document.body.classList.toggle('tw-raw', _on);
    const el = ensureIndicator();
    el.classList.toggle('tw-raw-indicator-on', _on);
  }

  function toggle() { setMode(!_on); }

  // Persist across reloads (localStorage)
  try {
    if (localStorage.getItem('tw_raw_mode') === '1') {
      setTimeout(() => setMode(true), 600);
    }
  } catch {}

  document.addEventListener('keydown', (e) => {
    // Alt+R toggles. Avoid intercepting when the user is typing in an input.
    if (e.altKey && (e.key === 'r' || e.key === 'R')) {
      const a = document.activeElement;
      if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA')) return;
      e.preventDefault();
      toggle();
      try { localStorage.setItem('tw_raw_mode', _on ? '1' : '0'); } catch {}
    }
  });

  // Programmatic API
  window.RawMode = { setMode, toggle, isOn: () => _on };

  // Mount the indicator on load so its CSS positioning is correct,
  // even before the user toggles
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureIndicator);
  } else {
    ensureIndicator();
  }
})();
