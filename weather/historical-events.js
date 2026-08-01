// historical-events.js — render NOAA + Smithsonian historical disasters
// (earthquakes, tsunamis, volcanic eruptions) filtered by the scrubber year.
//
// Reads cache `historical_disasters`. Filters events to a window
// [year - WINDOW, year + WINDOW] so the user sees what was happening "around"
// the current year. Window scales with era density: wider for ancient times
// (sparse data), tighter for modern (dense).
//
// Each event renders as a colored point with a kind glyph and a deaths-scaled
// halo. Click → infobox with full event description.
//
// Registers as window.LAYERS.historical_disasters.
(function(){
  let _data = null;
  let _entities = [];
  let _unsub = null;
  let _lastWindowKey = null;

  const KIND_COLOUR = { eq: '#f97316', tsu: '#06b6d4', vol: '#ef4444' };
  const KIND_LABEL  = { eq: 'Earthquake', tsu: 'Tsunami', vol: 'Volcanic eruption' };

  function windowForYear(year) {
    if (year < -1000) return 1000;       // ±1000 yr around ancient times
    if (year < 1500)  return 100;
    if (year < 1900)  return 25;
    return 5;
  }

  function clearEntities() {
    if (window.viewer && _entities.length) {
      for (const e of _entities) {
        try { window.viewer.entities.remove(e); } catch (_) {}
      }
    }
    _entities = [];
  }

  function paintWindow(year) {
    if (!_data || !_data.events) return;
    const w = windowForYear(year);
    const lo = year - w, hi = year + w;
    const key = `${lo}::${hi}`;
    if (key === _lastWindowKey) return;
    _lastWindowKey = key;
    clearEntities();

    // Binary-search to find first event >= lo
    const evs = _data.events;
    let i = 0, j = evs.length;
    while (i < j) { const m = (i + j) >> 1; if (evs[m].year < lo) i = m + 1; else j = m; }
    let count = 0;
    for (let k = i; k < evs.length; k++) {
      const e = evs[k];
      if (e.year > hi) break;
      const colour = KIND_COLOUR[e.kind] || '#94a3b8';
      const sz = 4 + Math.min(8, (e.mag || 4));
      const ent = window.viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(e.lon, e.lat),
        point: {
          pixelSize: sz,
          color: Cesium.Color.fromCssColorString(colour).withAlpha(0.85),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.5),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        name: `${KIND_LABEL[e.kind] || e.kind}: ${e.label}`,
        description: `<b>${KIND_LABEL[e.kind] || e.kind}</b><br>${e.label}<br>Year: ${window.Clock.label(e.year)}` +
          (e.deaths ? `<br>Deaths: ${e.deaths.toLocaleString()}` : '') +
          (e.mag ? `<br>${e.kind === 'vol' ? 'VEI' : 'Magnitude'}: ${e.mag}` : '') +
          `<br>Source: ${e.kind === 'vol' ? 'Smithsonian GVP' : 'NOAA NCEI'}`,
        properties: { historical_event: true, kind: e.kind, year: e.year },
      });
      _entities.push(ent);
      count++;
      if (count > 1500) break;   // safety
    }
    console.log(`[historical-events] ${count} events in ${window.Clock.label(lo)} → ${window.Clock.label(hi)}`);
  }

  async function render() {
    if (!_data) {
      try {
        const r = await (window.fetchCache ? window.fetchCache('historical_disasters') : fetch('/api/cache/historical_disasters.json').then(r => r.json()));
        if (!r || !r.events) {
          console.warn('[historical-events] cache not available yet');
          return;
        }
        _data = r;
        if (window.Scrubber && r.year_range) {
          window.Scrubber.registerLayer('historical_disasters', r.year_range, '#f97316');
        }
      } catch (e) {
        console.warn('[historical-events] load failed', e);
        return;
      }
    }
    if (_unsub) _unsub();
    _unsub = window.Clock && window.Clock.subscribe(year => paintWindow(year));
  }

  function clear() {
    if (_unsub) { _unsub(); _unsub = null; }
    if (window.Scrubber) window.Scrubber.unregisterLayer('historical_disasters');
    clearEntities();
    _lastWindowKey = null;
  }

  function waitAndRegister() {
    if (!window.LAYERS) { setTimeout(waitAndRegister, 100); return; }
    window.LAYERS.historical_disasters = { render, clear };
  }
  waitAndRegister();
})();
