// historical-wars.js — render major wars (1400→present) as pulsing markers
// during the years they were active.
//
// Reads cache `brecke_wars`. Each event has start/end years + lat/lon +
// fatality band + confidence. We show a war whenever the scrubber year is
// within [start, end]. Marker size = log(fatalities), colour = confidence.
(function(){
  let _data = null;
  let _entities = [];
  let _unsub = null;

  // Confidence → colour
  const CONF_COLOUR = { high: '#ef4444', medium: '#f97316', low: '#facc15' };

  function clearAll() {
    if (window.viewer && _entities.length) {
      for (const e of _entities) {
        try { window.viewer.entities.remove(e); } catch (_) {}
      }
    }
    _entities = [];
  }

  function paintForYear(year) {
    if (!_data?.events) return;
    clearAll();
    const active = _data.events.filter(e => year >= e.start && year <= e.end);
    let i = 0;
    for (const ev of active) {
      const colour = CONF_COLOUR[ev.confidence] || '#94a3b8';
      // Scale by log of average fatalities (50k → 4, 10M → 8, 70M → 11)
      const avg = (ev.fatalities_low + ev.fatalities_high) / 2;
      const size = Math.max(5, Math.min(18, Math.log10(Math.max(1, avg)) - 3));
      const phase = (i * 0.7) % (Math.PI * 2);
      const ent = window.viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat),
        point: {
          pixelSize: new Cesium.CallbackProperty(() => {
            const t = (Math.sin((window._animT || 0) * 1.2 + phase) + 1) / 2;
            return size + t * 4;
          }, false),
          color: new Cesium.CallbackProperty(() => {
            const t = (Math.sin((window._animT || 0) * 1.2 + phase) + 1) / 2;
            return Cesium.Color.fromCssColorString(colour).withAlpha(0.55 + 0.4 * t);
          }, false),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.7),
          outlineWidth: 1.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        name: ev.name,
        description: `<b>${ev.name}</b><br>` +
          `${ev.start}–${ev.end} (${ev.duration_years}y)<br>` +
          `Region: ${ev.region}<br>` +
          `Fatalities: ${(ev.fatalities_low/1e6).toFixed(2)}M – ${(ev.fatalities_high/1e6).toFixed(2)}M<br>` +
          `Confidence: ${ev.confidence}<br>` +
          `Source: Brecke + COW + UCDP composite`,
        properties: { historical_war: true, war_name: ev.name },
      });
      _entities.push(ent);
      i++;
    }
    console.log(`[historical-wars] ${active.length} active wars at ${window.Clock.label(year)}`);
  }

  async function render() {
    if (!_data) {
      try {
        const r = await (window.fetchCache ? window.fetchCache('brecke_wars') : fetch('/api/cache/brecke_wars.json').then(r => r.json()));
        if (!r?.events) {
          console.warn('[historical-wars] cache not available');
          return;
        }
        _data = r;
        if (window.Scrubber && r.year_range) {
          window.Scrubber.registerLayer('historical_wars', r.year_range, '#ef4444');
        }
      } catch (e) {
        console.warn('[historical-wars] load failed', e);
        return;
      }
    }
    if (_unsub) _unsub();
    _unsub = window.Clock && window.Clock.subscribe(year => paintForYear(year));
  }

  function clear() {
    if (_unsub) { _unsub(); _unsub = null; }
    if (window.Scrubber) window.Scrubber.unregisterLayer('historical_wars');
    clearAll();
  }

  function waitAndRegister() {
    if (!window.LAYERS) { setTimeout(waitAndRegister, 100); return; }
    window.LAYERS.historical_wars = { render, clear };
  }
  waitAndRegister();
})();
