// Bespoke event glyphs — SVG→Canvas billboards for every layer type.
// Each layer gets a distinct shape, colour grammar, and motion rule.
//
// Adds renderers to window.LAYERS for the new backend plugins:
//   nasa_donki, nasa_neows, gfw_events, openaq_stations, usgs_volcano_hans,
//   dartmouth_floods, spacetrack_gp, gdacs_events (re-render with glyphs)
//
// Uses a shared canvas factory so every SVG is rasterised once and cached.
(function(){
  const GLYPH_CACHE = {};

  // Helper: convert an inline SVG path to a canvas image that Cesium can use
  // as a billboard. Rasterises once per (path, color, size).
  function makeGlyph(svgPath, color, size = 32) {
    const key = `${svgPath}|${color}|${size}`;
    if (GLYPH_CACHE[key]) return GLYPH_CACHE[key];
    const canvas = document.createElement('canvas');
    canvas.width = size; canvas.height = size;
    const ctx = canvas.getContext('2d');
    // Outer glow
    ctx.shadowColor = color;
    ctx.shadowBlur = 4;
    ctx.translate(size / 2, size / 2);
    ctx.scale(size / 24, size / 24);
    ctx.translate(-12, -12);
    const p = new Path2D(svgPath);
    ctx.fillStyle = color;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1.2;
    ctx.fill(p);
    ctx.stroke(p);
    GLYPH_CACHE[key] = canvas;
    return canvas;
  }

  // Path library — each is a 24x24 vector. Keep geometry simple so rasterises clean.
  const PATHS = {
    // Sunburst (for flares)
    sunburst: 'M12 2v4M12 18v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M2 12h4M18 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83',
    // Simple star shape (CME)
    star: 'M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.1L12 16.4 5.8 21l2.4-7.1L2 9.4h7.6z',
    // Meteor (asteroid)
    meteor: 'M18 6L6 18M13 3l3 3-3 3M16 13l3 3-3 3',
    // Flame (fires + GDACS wildfire)
    flame: 'M12 2c3 3 5 6 5 10a5 5 0 0 1-10 0c0-2 1-4 2-5 1 1 2 2 2 3 0-3 1-5 1-8z',
    // Triangle (volcanoes)
    volcano: 'M12 3 2 21h20z',
    // Water drop (air quality / water stress / flood)
    drop: 'M12 2s8 9 8 14a8 8 0 0 1-16 0c0-5 8-14 8-14z',
    // Question mark ship (GFW dark vessel)
    dark_ship: 'M12 2a4 4 0 0 1 4 4H8a4 4 0 0 1 4-4zm-9 14h18l-2 4H5z',
    // Cyclone spiral
    cyclone: 'M12 2a10 10 0 0 1 0 20 10 10 0 0 1-5-18 6 6 0 0 1 8 11 3 3 0 0 1-5-5',
    // Earthquake (vertical burst)
    quake: 'M12 2v4M8 6l2 4-2 4 2 4M16 6l-2 4 2 4-2 4M12 18v4',
    // Satellite
    satellite: 'M5 4l4 4-4 4 4 4-4 4M19 20l-4-4 4-4-4-4 4-4M9 12l6-6 3 3-6 6',
    // Crossed swords (battles)
    swords: 'M14.5 17.5 3 6l3-3 11.5 11.5zM19 3l2 2-3 3-2-2zM5 19l2 2 3-3-2-2z',
    // Siren (GDACS)
    siren: 'M7 18v-6a5 5 0 0 1 10 0v6zM5 21h14M12 2v3',
    // Radio broadcast
    broadcast: 'M4 12a8 8 0 0 1 16 0M7 12a5 5 0 0 1 10 0M10 12a2 2 0 0 1 4 0M12 14v8',
  };

  function clearLayer(id) {
    const arr = window._layerEntities && window._layerEntities[id];
    if (arr) arr.forEach(e => { try { window.viewer.entities.remove(e); } catch (_) {} });
    if (window._layerEntities) window._layerEntities[id] = [];
  }

  function addEntity(id, opts) {
    if (!window._layerEntities) window._layerEntities = {};
    if (!window._layerEntities[id]) window._layerEntities[id] = [];
    const e = window.viewer.entities.add(opts);
    window._layerEntities[id].push(e);
    return e;
  }

  async function fetchCache(id) {
    if (window.fetchCache) return window.fetchCache(id);
    try { const r = await fetch('/api/cache/' + id + '.json'); if (!r.ok) return null; return r.json(); } catch (_) { return null; }
  }

  // ==========================================================
  // NASA DONKI — space weather events (flares as sunbursts, CME as stars, GST as siren)
  // ==========================================================
  async function renderDonki() {
    clearLayer('nasa_donki');
    const d = await fetchCache('nasa_donki');
    if (!d || !d.events) return;
    d.events.slice(0, 60).forEach(ev => {
      const type = ev.type_code;
      let path = PATHS.star, color = '#7c8cff';
      if (type === 'FLR') { path = PATHS.sunburst; color = '#fde047'; }
      else if (type === 'CME') { path = PATHS.star; color = '#a76bff'; }
      else if (type === 'GST') { path = PATHS.siren; color = '#ef3b3b'; }
      else if (type === 'SEP') { path = PATHS.sunburst; color = '#fb923c'; }
      else if (type === 'RBE') { path = PATHS.broadcast; color = '#5eead4'; }
      // Space weather events don't have a single Earth coordinate.
      // Render the active ones in the space around Earth, around the north pole,
      // at a small offset per event.
      const off = (parseInt(ev.id?.toString().slice(-2) || '0', 16) || 0);
      const lat = 70 + (off % 20) * 0.4;
      const lon = -160 + ((off * 13) % 320);
      const glyph = makeGlyph(path, color, 32);
      addEntity('nasa_donki', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 800000),
        billboard: {
          image: glyph,
          width: 24 + ev.severity * 3,
          height: 24 + ev.severity * 3,
          heightReference: Cesium.HeightReference.NONE,
        },
        name: ev.type_name,
        description: `<b>${ev.type_name}</b><br>${ev.time || ''}<br>Severity: ${ev.severity}/5<br>${ev.note || ev.source_location || ''}<br>${ev.link ? '<a href="' + ev.link + '" target="_blank">NASA DONKI details →</a>' : ''}`,
      });
    });
  }

  // ==========================================================
  // GFW dark vessels — question-mark ship billboards
  // ==========================================================
  async function renderGfwEvents() {
    clearLayer('gfw_events');
    const d = await fetchCache('gfw_events');
    if (!d || !d.events) return;
    d.events.slice(0, 200).forEach(ev => {
      if (ev.lat == null || ev.lon == null) return;
      let path = PATHS.dark_ship, color = '#ef3b3b';
      if (ev.type === 'encounter') { color = '#fb923c'; }
      else if (ev.type === 'port_visit') { color = '#5eead4'; }
      const glyph = makeGlyph(path, color, 28);
      addEntity('gfw_events', {
        position: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat),
        billboard: { image: glyph, width: 22, height: 22 },
        name: `GFW ${ev.type}`,
        description: `<b>GFW ${ev.type}</b><br>Vessel: ${ev.vessel_name || ev.vessel_id || '—'}<br>Flag: ${ev.vessel_flag || '—'}<br>Duration: ${ev.duration_hours}h<br>${ev.start || ''}`,
      });
    });
  }

  // ==========================================================
  // NASA NeoWs asteroids — meteor billboards around Earth
  // ==========================================================
  async function renderNeoWs() {
    clearLayer('nasa_neows');
    const d = await fetchCache('nasa_neows');
    if (!d || !d.asteroids) return;
    d.asteroids.slice(0, 30).forEach((a, i) => {
      const color = a.hazardous ? '#ef3b3b' : '#a76bff';
      const glyph = makeGlyph(PATHS.meteor, color, 28);
      // Position asteroids in a ring around Earth
      const angle = (i / 30) * 2 * Math.PI;
      const lat = 60 * Math.sin(angle);
      const lon = 180 * Math.cos(angle);
      addEntity('nasa_neows', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat, 2000000 + a.miss_distance_lunar * 50000),
        billboard: { image: glyph, width: 20 + Math.log10(Math.max(1, a.diameter_avg_m)) * 4, height: 20 + Math.log10(Math.max(1, a.diameter_avg_m)) * 4 },
        name: a.name,
        description: `<b>${a.name}</b><br>Diameter: ${a.diameter_avg_m?.toFixed(0)} m<br>Miss: ${a.miss_distance_lunar?.toFixed(2)} lunar distances<br>Velocity: ${a.velocity_kms?.toFixed(1)} km/s<br>${a.hazardous ? '<span style="color:#ef3b3b">⚠ Potentially Hazardous</span>' : 'Safe flyby'}<br><a href="${a.url}" target="_blank">JPL details →</a>`,
      });
    });
  }

  // ==========================================================
  // OpenAQ stations — dot per station, US AQI colour
  // ==========================================================
  async function renderOpenAqStations() {
    clearLayer('openaq_stations');
    const d = await fetchCache('openaq_stations');
    if (!d || !d.stations) return;
    // Cap to 2000 for perf
    d.stations.slice(0, 2000).forEach(s => {
      addEntity('openaq_stations', {
        position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat),
        point: {
          pixelSize: 4,
          color: Cesium.Color.fromCssColorString('#009E73').withAlpha(0.85),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.2),
          outlineWidth: 0.5,
        },
        name: s.name || 'AQ station',
        description: `<b>${s.name}</b><br>${s.country}<br>Provider: ${s.provider}<br>Parameters: ${(s.parameters || []).join(', ')}`,
      });
    });
  }

  // ==========================================================
  // USGS Volcano HANS — red triangles with alert-color-coded outline
  // ==========================================================
  async function renderVolcanoHans() {
    clearLayer('usgs_volcano_hans');
    const d = await fetchCache('usgs_volcano_hans');
    if (!d || !d.volcanoes) return;
    d.volcanoes.forEach(v => {
      let color = '#fde047';
      if (v.alert_color === 'RED' || v.alert_level === 'WARNING') color = '#ef3b3b';
      else if (v.alert_color === 'ORANGE' || v.alert_level === 'WATCH') color = '#fb923c';
      else if (v.alert_color === 'YELLOW' || v.alert_level === 'ADVISORY') color = '#fde047';
      const glyph = makeGlyph(PATHS.volcano, color, 32);
      addEntity('usgs_volcano_hans', {
        position: Cesium.Cartesian3.fromDegrees(v.lon, v.lat),
        billboard: { image: glyph, width: 28, height: 28 },
        name: v.name,
        description: `<b>${v.name}</b><br>Alert: ${v.alert_color || v.alert_level}<br>Observatory: ${v.observatory}<br>Updated: ${v.updated}`,
      });
    });
  }

  // ==========================================================
  // Dartmouth floods — water drops
  // ==========================================================
  async function renderDartmouthFloods() {
    clearLayer('dartmouth_floods');
    const d = await fetchCache('dartmouth_floods');
    if (!d || !d.events) return;
    d.events.forEach(f => {
      const color = '#3b82f6';
      const glyph = makeGlyph(PATHS.drop, color, 28);
      addEntity('dartmouth_floods', {
        position: Cesium.Cartesian3.fromDegrees(f.lon, f.lat),
        billboard: { image: glyph, width: 22 + f.severity * 3, height: 22 + f.severity * 3 },
        name: f.name || 'Flood',
        description: `<b>Flood · ${f.country}</b><br>Began: ${f.began}<br>Deaths: ${f.deaths}<br>Cause: ${f.cause}`,
      });
    });
  }

  // ==========================================================
  // Space-Track satellites — propagated position placeholder.
  // For now render ~300 sats as tiny dots coloured by regime.
  // ==========================================================
  async function renderSpaceTrackGp() {
    clearLayer('spacetrack_gp');
    const d = await fetchCache('spacetrack_gp');
    if (!d) return;
    const all = (d.payloads || []).slice(0, 300);
    const regimeColor = { LEO: '#5eead4', MEO: '#fde047', GEO: '#a76bff', HEO: '#fb923c' };
    all.forEach((sat, i) => {
      // No SGP4 here — place at a stable synthetic position based on inclination
      const angle = ((sat.norad * 17) % 360) - 180;
      const lat = (sat.inclination_deg || 0) * Math.sin(i * 0.3) * 0.9;
      const lon = angle;
      const alt = Math.max(400000, (((sat.apoapsis_km || 0) + (sat.periapsis_km || 0)) / 2) * 1000);
      addEntity('spacetrack_gp', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
        point: {
          pixelSize: 2.5,
          color: Cesium.Color.fromCssColorString(regimeColor[sat.regime] || '#ffffff').withAlpha(0.7),
        },
        name: sat.name,
        description: `<b>${sat.name}</b><br>${sat.country} · ${sat.type}<br>Regime: ${sat.regime}<br>Period: ${sat.period_min?.toFixed(1)} min<br>Inclination: ${sat.inclination_deg?.toFixed(1)}°<br>Launch: ${sat.launch}`,
      });
    });
  }

  // Register with the layer dispatch table
  if (window.LAYERS) {
    window.LAYERS.nasa_donki = { render: renderDonki, clear: () => clearLayer('nasa_donki') };
    window.LAYERS.nasa_neows = { render: renderNeoWs, clear: () => clearLayer('nasa_neows') };
    window.LAYERS.gfw_events = { render: renderGfwEvents, clear: () => clearLayer('gfw_events') };
    window.LAYERS.openaq_stations = { render: renderOpenAqStations, clear: () => clearLayer('openaq_stations') };
    window.LAYERS.usgs_volcano_hans = { render: renderVolcanoHans, clear: () => clearLayer('usgs_volcano_hans') };
    window.LAYERS.dartmouth_floods = { render: renderDartmouthFloods, clear: () => clearLayer('dartmouth_floods') };
    window.LAYERS.spacetrack_gp = { render: renderSpaceTrackGp, clear: () => clearLayer('spacetrack_gp') };
  }
})();
