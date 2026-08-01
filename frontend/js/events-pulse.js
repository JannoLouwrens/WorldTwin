// events-pulse.js — render the 83 global_events on the globe as
// pulsing severity-scaled markers tied to the scrolling ticker.
//
// Each event is a billboard + ripple ellipse that pulses on a sine wave.
// Hovering shows title + source. Clicking opens the source URL.
(function(){
  let _entities = [];
  let _ticker = null;

  function clearAll() {
    if (!window.viewer) return;
    for (const e of _entities) { try { window.viewer.entities.remove(e); } catch (_) {} }
    _entities = [];
  }

  function severityColor(s) {
    if (s >= 7) return '#ef4444';
    if (s >= 5) return '#f97316';
    if (s >= 3) return '#facc15';
    return '#7dd3fc';
  }

  async function render() {
    clearAll();
    const data = window._cacheStore?.get('global_events');
    const events = data?.events || [];
    const TYPES = {
      news: '📰', conflict: '⚔', hazard: '⚠', economic: '$', health: '🦠', space: '🛰',
    };
    let i = 0;
    for (const ev of events) {
      if (!Number.isFinite(ev.lat) || !Number.isFinite(ev.lon)) continue;
      const color = severityColor(ev.severity);
      const phase = (i * 0.7) % (Math.PI * 2);    // stagger pulses
      // Pulsing inner dot
      const ent = window.viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat, 0),
        point: {
          pixelSize: new Cesium.CallbackProperty(() => {
            const t = (Math.sin((window._animT || 0) * 1.5 + phase) + 1) / 2;
            return 4 + (ev.severity || 1) * 0.8 + t * 4;
          }, false),
          color: new Cesium.CallbackProperty(() => {
            const t = (Math.sin((window._animT || 0) * 1.5 + phase) + 1) / 2;
            return Cesium.Color.fromCssColorString(color).withAlpha(0.5 + t * 0.4);
          }, false),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.7),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        properties: {
          pickcard: {
            getValue: () => ({
              title: ev.title || 'Event',
              subtitle: (ev.type || '') + ' · severity ' + (ev.severity || 1),
              source_name: ev.source || '',
              source_url: ev.url || '',
              values: [
                { label: 'Time', value: ev.time?.slice(0, 16) || '—' },
                { label: 'Country', value: ev.country || '—' },
                { label: 'Severity', value: String(ev.severity || 1) + ' / 10' },
              ],
            }),
          },
          event_pulse: true,
          event_id: ev.id,
        },
        description: `<b>${ev.title || 'Event'}</b><br>${ev.source || ''}<br>${ev.url ? `<a href="${ev.url}" target="_blank">Source →</a>` : ''}`,
      });
      _entities.push(ent);
      i++;
    }
    console.log(`[events-pulse] ${_entities.length} events on globe`);
  }

  function clear() { clearAll(); }

  function waitAndRegister() {
    if (!window.LAYERS) { setTimeout(waitAndRegister, 100); return; }
    window.LAYERS.global_events = { render, clear };
  }
  waitAndRegister();

  window.EventsPulse = { render, clear };
})();
