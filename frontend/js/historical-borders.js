// historical-borders.js — render aourednik historical world maps as a
// time-snapped polygon overlay.
//
// The aggregator ships a payload of 52 snapshots between 123,000 BC and
// 2010 AD. We pick the nearest snapshot at-or-before the current Clock
// year, build Cesium polygons for it, and crossfade when the year crosses
// a snapshot boundary.
//
// Each polity polygon gets a deterministic colour from a stable hash of
// its name so the same empire stays the same colour across snapshots.
//
// Registers as window.LAYERS.historical_borders.
(function(){
  let _data = null;             // raw aggregator payload
  let _snapshots = [];          // sorted list of snapshot years
  let _currentSnapshotYear = null;
  let _entities = [];
  let _unsub = null;

  // Stable polity-name → colour hash. Same name → same colour everywhere.
  const PALETTE = [
    '#ef4444', '#f97316', '#f59e0b', '#eab308', '#84cc16', '#22c55e',
    '#10b981', '#14b8a6', '#06b6d4', '#0ea5e9', '#3b82f6', '#6366f1',
    '#8b5cf6', '#a855f7', '#d946ef', '#ec4899', '#f43f5e', '#64748b',
    '#7c3aed', '#0891b2', '#15803d', '#b91c1c', '#a16207', '#9333ea',
  ];
  function colourFor(name) {
    if (!name) return '#475569';
    let h = 0;
    for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
    return PALETTE[Math.abs(h) % PALETTE.length];
  }

  function snapshotForYear(year) {
    if (!_snapshots.length) return null;
    // Most-recent snapshot at-or-before y
    let chosen = _snapshots[0];
    for (const s of _snapshots) {
      if (s <= year) chosen = s; else break;
    }
    return chosen;
  }

  function clearEntities() {
    if (window.viewer && _entities.length) {
      for (const e of _entities) {
        try { window.viewer.entities.remove(e); } catch (_) {}
      }
    }
    _entities = [];
  }

  function paintSnapshot(year) {
    if (!_data || !_data.features_by_year) return;
    const snap = snapshotForYear(year);
    if (snap === null || snap === _currentSnapshotYear) return;
    _currentSnapshotYear = snap;
    clearEntities();
    const feats = _data.features_by_year[String(snap)] || [];
    let added = 0;
    for (const f of feats) {
      const geom = f.geometry;
      const name = (f.properties && f.properties.name) || '—';
      const colour = colourFor(name);
      if (!geom) continue;
      const addPoly = (rings) => {
        if (!rings || !rings[0] || rings[0].length < 3) return;
        const flat = [];
        for (const [lon, lat] of rings[0]) flat.push(lon, lat);
        const ent = window.viewer.entities.add({
          name: `${name} (${window.Clock.label(snap)})`,
          polygon: {
            hierarchy: new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(flat)),
            material: Cesium.Color.fromCssColorString(colour).withAlpha(0.55),
            outline: true,
            outlineColor: Cesium.Color.WHITE.withAlpha(0.45),
            outlineWidth: 1,
            height: 0,
          },
          description: `<b>${name}</b><br>Snapshot: ${window.Clock.label(snap)}<br>Source: aourednik historical-basemaps`,
          properties: { historical_borders: true, snapshot_year: snap, polity_name: name },
        });
        _entities.push(ent);
        added++;
      };
      if (geom.type === 'Polygon')        addPoly(geom.coordinates);
      else if (geom.type === 'MultiPolygon') for (const p of geom.coordinates) addPoly(p);
    }
    console.log(`[historical-borders] painted ${added} polities for ${window.Clock.label(snap)}`);
  }

  async function render() {
    if (!_data) {
      try {
        const r = await (window.fetchCache ? window.fetchCache('historical_borders') : fetch('/api/cache/historical_borders.json').then(r => r.json()));
        if (!r || !r.snapshots) {
          console.warn('[historical-borders] cache not available yet');
          return;
        }
        _data = r;
        _snapshots = r.snapshots.slice().sort((a, b) => a - b);
        if (window.Scrubber) {
          window.Scrubber.registerLayer('historical_borders', [_snapshots[0], _snapshots[_snapshots.length - 1]], '#a855f7');
        }
      } catch (e) {
        console.warn('[historical-borders] load failed', e);
        return;
      }
    }
    if (_unsub) _unsub();
    _unsub = window.Clock && window.Clock.subscribe(year => paintSnapshot(year));
  }

  function clear() {
    if (_unsub) { _unsub(); _unsub = null; }
    if (window.Scrubber) window.Scrubber.unregisterLayer('historical_borders');
    clearEntities();
    _currentSnapshotYear = null;
  }

  function waitAndRegister() {
    if (!window.LAYERS) { setTimeout(waitAndRegister, 100); return; }
    window.LAYERS.historical_borders = { render, clear };
  }
  waitAndRegister();
})();
