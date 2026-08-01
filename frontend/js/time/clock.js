// time/clock.js — single source of truth for "what year is the user looking at?"
//
// All historical layers (CO2 800k years back, borders 2000 BC, GDP 1 AD, etc.)
// subscribe to a single signed integer year (negative = BC, positive = AD).
//
// Why not use new Date(): JS Date is broken pre-100 AD on Windows and silently
// re-interprets 2-digit years. Cesium.JulianDate works fine but its ISO 8601
// extended form ("-002000-01-01T00:00:00Z") is the only safe deep-time path.
//
// API:
//   Clock.year                       → current signed year (read-only)
//   Clock.setYear(y)                 → set the global year, fires 'change'
//   Clock.subscribe(fn)              → fn(year) called on every change; returns unsubscribe
//   Clock.toJulianDate(y)            → Cesium.JulianDate at Jan 1 of year y
//   Clock.fromJulianDate(jd)         → signed integer year
//   Clock.toISO(y)                   → "-002000-01-01T00:00:00Z" (BC) or "2026-01-01T00:00:00Z"
//   Clock.fromISO(iso)               → signed integer year
//   Clock.label(y)                   → "2000 BC" / "476 AD" / "2026"
//   Clock.MIN_YEAR / MAX_YEAR        → -800000 / current real-world year
//   Clock.now()                      → current real-world year
(function(){
  const NOW = new Date().getUTCFullYear();
  const MIN_YEAR = -800000;
  const MAX_YEAR = NOW;

  let _year = NOW;             // current scrubber position
  const _subs = new Set();     // subscribers

  function setYear(y, opts) {
    y = Math.round(y);
    if (y < MIN_YEAR) y = MIN_YEAR;
    if (y > MAX_YEAR) y = MAX_YEAR;
    if (y === _year && !(opts && opts.force)) return;
    _year = y;
    // Mirror to a global so non-subscribing code can read the current year cheaply
    window.__CURRENT_YEAR__ = y;
    for (const fn of _subs) {
      try { fn(y); } catch (e) { console.warn('[clock] subscriber error', e); }
    }
  }

  function subscribe(fn) {
    _subs.add(fn);
    // Fire once immediately so subscribers don't have to wait for a change
    try { fn(_year); } catch (e) { /* noop */ }
    return () => _subs.delete(fn);
  }

  // ---- ISO 8601 extended (RFC 3339 §5.6 with leading sign for years > 4 digits) ----
  // Year 0 is "0000" (astronomical: 1 BC = year 0, 2 BC = year -1).
  // Historians prefer "no year zero" (1 BC → 1 AD). We use astronomical convention
  // internally; label() handles the historian-style display.
  function pad(n, w) { const s = String(Math.abs(Math.trunc(n))); return s.length >= w ? s : '0'.repeat(w - s.length) + s; }

  function toISO(y) {
    if (y >= 0 && y <= 9999) return `${pad(y, 4)}-01-01T00:00:00Z`;
    if (y < 0) return `-${pad(y, 6)}-01-01T00:00:00Z`;
    return `+${pad(y, 6)}-01-01T00:00:00Z`;
  }

  function fromISO(iso) {
    if (!iso) return NaN;
    const m = iso.match(/^([+-]?)(\d{4,6})-/);
    if (!m) return NaN;
    const sign = m[1] === '-' ? -1 : 1;
    return sign * parseInt(m[2], 10);
  }

  function toJulianDate(y) {
    if (typeof Cesium === 'undefined') return null;
    return Cesium.JulianDate.fromIso8601(toISO(y));
  }

  function fromJulianDate(jd) {
    if (!jd || typeof Cesium === 'undefined') return _year;
    const iso = Cesium.JulianDate.toIso8601(jd, 0);
    return fromISO(iso);
  }

  // Historian-style label. Year 0 shows as "1 BC".
  function label(y) {
    if (y === undefined) y = _year;
    if (y > 0) return `${y} AD`;
    if (y === 0) return '1 BC';
    return `${-y + 1} BC`;
  }

  // Debounced, integer-quantised version of setYear for high-frequency input
  // (drag scrubbing). Snaps to integer years to keep cache hits sane.
  let _rafPending = false;
  let _pendingYear = null;
  function setYearLive(y) {
    _pendingYear = Math.round(y);
    if (_rafPending) return;
    _rafPending = true;
    requestAnimationFrame(() => {
      _rafPending = false;
      if (_pendingYear !== null) setYear(_pendingYear);
      _pendingYear = null;
    });
  }

  // Note: window._animT is updated every frame by cesium-setup.js's preRender
  // hook (more accurate than this module's previous 100ms setInterval, which
  // was removed 2026-04-25 — two clocks fighting for the same global).

  // Public API
  window.Clock = {
    get year()       { return _year; },
    get MIN_YEAR()   { return MIN_YEAR; },
    get MAX_YEAR()   { return MAX_YEAR; },
    setYear, setYearLive, subscribe,
    toJulianDate, fromJulianDate, toISO, fromISO,
    label,
    now: () => NOW,
    isLive: () => _year === MAX_YEAR,
  };
  window.__CURRENT_YEAR__ = _year;
})();
