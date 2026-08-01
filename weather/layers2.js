// layers2.js — Phase 3: orphan plugin renderers.
//
// 55 backend plugins previously had no frontend wiring. This file adds a
// renderer for each orphan that belongs on the globe, using the pattern
// established by event-glyphs.js (SVG→canvas billboards) and by layers.js
// (point markers with description HTML).
//
// All renderers here follow the same shape:
//   1. clearLayer(id)
//   2. fetch cache via window.fetchCache(id) — uses preloader store first
//   3. filter + limit
//   4. addEntity per item with description (universal pickcard props coming in Phase 8)
//   5. register in window.LAYERS[id]
//
// Reads config.json for styling hints if present.
(function(){

  // Re-use event-glyphs.js's makeGlyph if it's still in module scope
  // (not exported — so we re-roll a minimal version here)
  const GLYPH_CACHE = {};
  function makeGlyph(svgPath, color, size = 28) {
    const key = `${svgPath}|${color}|${size}`;
    if (GLYPH_CACHE[key]) return GLYPH_CACHE[key];
    const canvas = document.createElement('canvas');
    canvas.width = size; canvas.height = size;
    const ctx = canvas.getContext('2d');
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

  // Extended glyph path library
  const P = {
    plane:    'M22 16v-2l-8.5-5V3.5a1.5 1.5 0 0 0-3 0V9L2 14v2l8.5-2.5V19L8 20.5V22l4-1 4 1v-1.5L13.5 19v-5.5z',
    anchor:   'M12 2a2 2 0 0 1 2 2c0 .74-.4 1.38-1 1.72V8h3v2h-3v7.82A5 5 0 0 0 17 13h-2a3 3 0 0 1-6 0H7a5 5 0 0 0 4 4.82V10H8V8h3V5.72A2 2 0 0 1 10 4a2 2 0 0 1 2-2z',
    camera:   'M9 3L7.17 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3.17L15 3H9zm3 5a5 5 0 1 1 0 10 5 5 0 0 1 0-10z',
    play:     'M8 5v14l11-7z',
    virus:    'M12 2v2a4 4 0 0 1 4 4h2a6 6 0 0 0-6-6zm0 4a4 4 0 0 0-4 4H6a6 6 0 0 1 6-6zM3 11h2a7 7 0 0 0 7 7v2a9 9 0 0 1-9-9zm16 0h2a9 9 0 0 1-9 9v-2a7 7 0 0 0 7-7z',
    globe_dot:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 2c4.4 0 8 3.6 8 8h-4a4 4 0 0 0-4-4V4z',
    drop:     'M12 2s8 9 8 14a8 8 0 0 1-16 0c0-5 8-14 8-14z',
    bolt:     'M13 2L3 14h7l-1 8 10-12h-7z',
    tv:       'M3 5h18v12H3zm2 14h14v2H5zM7 7h10v8H7z',
    grid:     'M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z',
    broadcast:'M4 12a8 8 0 0 1 16 0M7 12a5 5 0 0 1 10 0M10 12a2 2 0 0 1 4 0M12 14v8',
    siren:    'M7 18v-6a5 5 0 0 1 10 0v6zM5 21h14M12 2v3',
    volcano:  'M12 3 2 21h20z',
    swords:   'M14.5 17.5 3 6l3-3 11.5 11.5zM19 3l2 2-3 3-2-2zM5 19l2 2 3-3-2-2z',
    news:     'M3 4h18v16H3zM7 8h10v2H7zm0 4h10v2H7zm0 4h6v2H7z',
  };

  // ============================================================
  // Country name/code → lat/lon lookup (from preloaded population cache)
  // ============================================================
  let _countryLookup = null;
  function getCountryCoords(nameOrCode) {
    if (!nameOrCode) return null;
    if (!_countryLookup) {
      _countryLookup = {};
      const pop = window._cacheStore && window._cacheStore.get('population');
      if (Array.isArray(pop)) {
        pop.forEach(c => {
          if (!c.latlng || c.latlng.length < 2) return;
          const [lat, lon] = c.latlng;
          if (c.cca2) _countryLookup[c.cca2.toUpperCase()] = [lat, lon];
          if (c.cca3) _countryLookup[c.cca3.toUpperCase()] = [lat, lon];
          if (c.name?.common) _countryLookup[c.name.common.toUpperCase()] = [lat, lon];
          if (c.name?.official) _countryLookup[c.name.official.toUpperCase()] = [lat, lon];
        });
      }
    }
    return _countryLookup[String(nameOrCode).toUpperCase()] || null;
  }

  // ============================================================
  // Shared helpers — use the LIVE window.viewer (post-rebuild safe)
  // ============================================================
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

  async function getCache(id) {
    if (window._cacheStore && window._cacheStore.has(id)) return window._cacheStore.get(id);
    if (window.fetchCache) return await window.fetchCache(id);
    try {
      const r = await fetch(`/api/cache/${id}.json?_=${Date.now()}`);
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }

  // Pickcard wrapper: every entity gets standard properties so the universal
  // click handler in app.js can show the unified card in Phase 8.
  function pc(props) {
    const bag = new Cesium.PropertyBag();
    bag.addProperty('pickcard', new Cesium.ConstantProperty(props));
    return bag;
  }

  function fmtISO(dt) {
    if (!dt) return null;
    try { return new Date(dt).toISOString(); } catch { return String(dt); }
  }

  // ============================================================
  // VOLCANOES (Smithsonian GVP) — 1215 red triangles
  // ============================================================
  async function renderVolcanoes() {
    clearLayer('volcanoes');
    const d = await getCache('volcanoes');
    if (!d) return;
    const features = d.features || d.volcanoes || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(features)) return;
    const glyph = makeGlyph(P.volcano, '#dc2626', 18);
    features.slice(0, 1500).forEach(v => {
      const coords = v.geometry?.coordinates || (v.lat != null ? [v.lon, v.lat] : null);
      if (!coords || coords.length < 2) return;
      const [lon, lat] = coords;
      const props = v.properties || v;
      addEntity('volcanoes', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: {
          image: glyph,
          scale: 0.7,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        name: props.name || props.volcano || 'Volcano',
        properties: pc({
          title: props.name || props.volcano || 'Volcano',
          source_name: 'Smithsonian GVP',
          source_url: 'https://volcano.si.edu/volcano.cfm?vn=' + (props.volcano_num || ''),
          fetched_at: fmtISO(d.fetched),
          event_date: null,
          location: props.country || '',
          values: [
            { label: 'Country',   value: props.country || '—' },
            { label: 'Elevation', value: (props.elevation || '—') + (props.elevation ? ' m' : '') },
            { label: 'Type',      value: props.primary_volcano_type || '—' },
            { label: 'Last eruption', value: props.last_eruption || '—' },
          ],
          category_color: '#dc2626',
        }),
        description: `<b>${props.name || 'Volcano'}</b><br>${props.country || ''}<br>Elev: ${props.elevation || '—'} m<br>Type: ${props.primary_volcano_type || '—'}`,
      });
    });
  }

  // ============================================================
  // WHO DON — disease outbreak news
  // ============================================================
  async function renderWhoDon() {
    clearLayer('who_don');
    const d = await getCache('who_don');
    if (!d) return;
    const items = d.items || d.events || d.outbreaks || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.virus, '#f59e0b', 28);
    items.slice(0, 60).forEach(it => {
      if (it.lat == null || it.lon == null) return;
      addEntity('who_don', {
        position: Cesium.Cartesian3.fromDegrees(it.lon, it.lat),
        billboard: { image: glyph, scale: 0.8, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: it.title || 'WHO Outbreak',
        properties: pc({
          title: it.title || 'Disease Outbreak',
          source_name: 'WHO Disease Outbreak News',
          source_url: it.url || 'https://www.who.int/emergencies/disease-outbreak-news',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(it.date || it.pubDate || it.published),
          location: it.country || it.location || '',
          values: [
            { label: 'Country', value: it.country || '—' },
            { label: 'Published', value: it.date || it.pubDate || '—' },
          ],
          category_color: '#f59e0b',
        }),
        description: `<b>${it.title}</b><br>${it.country || ''}<br>${(it.description || '').slice(0, 240)}<br><a href="${it.url}" target="_blank">WHO →</a>`,
      });
    });
  }

  // ============================================================
  // AIR QUALITY — 45 major cities
  // ============================================================
  async function renderAirQuality() {
    clearLayer('air_quality');
    const d = await getCache('air_quality');
    if (!d) return;
    const items = d.cities || d.items || d.features || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    function aqiColor(aqi) {
      if (aqi == null) return '#94a3b8';
      if (aqi <= 50) return '#10b981';
      if (aqi <= 100) return '#facc15';
      if (aqi <= 150) return '#f97316';
      if (aqi <= 200) return '#ef4444';
      if (aqi <= 300) return '#a21caf';
      return '#7f1d1d';
    }
    items.forEach(it => {
      const lat = it.lat ?? it.latitude;
      const lon = it.lon ?? it.longitude;
      if (lat == null || lon == null) return;
      const aqi = it.us_aqi ?? it.aqi ?? it.value;
      addEntity('air_quality', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        point: {
          pixelSize: 12,
          color: Cesium.Color.fromCssColorString(aqiColor(aqi)),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.8),
          outlineWidth: 1.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        name: it.city || 'AQ City',
        properties: pc({
          title: it.city || 'Air quality',
          source_name: 'Open-Meteo CAMS',
          source_url: 'https://open-meteo.com/en/docs/air-quality-api',
          fetched_at: fmtISO(d.fetched),
          location: `${it.city || ''}${it.country ? ', ' + it.country : ''}`,
          values: [
            { label: 'US AQI', value: aqi != null ? String(aqi) : '—' },
            { label: 'PM2.5', value: it.pm2_5 != null ? it.pm2_5.toFixed(1) + ' µg/m³' : '—' },
            { label: 'PM10',  value: it.pm10 != null ? it.pm10.toFixed(1) + ' µg/m³' : '—' },
            { label: 'NO₂',   value: it.nitrogen_dioxide != null ? it.nitrogen_dioxide.toFixed(1) + ' µg/m³' : '—' },
            { label: 'O₃',    value: it.ozone != null ? it.ozone.toFixed(1) + ' µg/m³' : '—' },
          ],
          category_color: aqiColor(aqi),
        }),
        description: `<b>${it.city}</b> AQI ${aqi}<br>PM2.5: ${it.pm2_5 || '—'}`,
      });
    });
  }

  // ============================================================
  // CLOUDFLARE RADAR — outages + DDoS
  // ============================================================
  async function renderCloudflareRadar() {
    clearLayer('cloudflare_radar');
    const d = await getCache('cloudflare_radar');
    if (!d) return;
    const outages = d.outages || [];
    const ddos = d.ddos_targets || d.ddos || [];
    const glyphO = makeGlyph(P.bolt, '#ef4444', 26);
    const glyphD = makeGlyph(P.bolt, '#f59e0b', 26);
    outages.forEach(o => {
      if (o.lat == null || o.lon == null) return;
      addEntity('cloudflare_radar', {
        position: Cesium.Cartesian3.fromDegrees(o.lon, o.lat),
        billboard: { image: glyphO, scale: 0.75, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: 'Internet outage',
        properties: pc({
          title: 'Internet outage',
          source_name: 'Cloudflare Radar',
          source_url: 'https://radar.cloudflare.com/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(o.start_date || o.start),
          location: o.location_name || o.country || '',
          values: [
            { label: 'Country',  value: o.location_name || o.country || '—' },
            { label: 'ASNs',     value: (o.asns || []).join(', ') || '—' },
            { label: 'Scope',    value: o.scope || o.event_type || '—' },
            { label: 'Started',  value: o.start_date || '—' },
            { label: 'Ended',    value: o.end_date || 'ongoing' },
          ],
          category_color: '#ef4444',
        }),
        description: `<b>Outage</b> ${o.location_name || ''}`,
      });
    });
    ddos.forEach(t => {
      if (t.lat == null || t.lon == null) return;
      addEntity('cloudflare_radar', {
        position: Cesium.Cartesian3.fromDegrees(t.lon, t.lat),
        billboard: { image: glyphD, scale: 0.75, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: 'DDoS target',
        properties: pc({
          title: 'DDoS target',
          source_name: 'Cloudflare Radar',
          source_url: 'https://radar.cloudflare.com/',
          fetched_at: fmtISO(d.fetched),
          location: t.country || '',
          values: [
            { label: 'Country', value: t.country || '—' },
            { label: 'Rank',    value: t.rank || '—' },
          ],
          category_color: '#f59e0b',
        }),
      });
    });
  }

  // ============================================================
  // PORTWATCH PORTS — top 800 ports with daily vessel calls
  // ============================================================
  async function renderPortwatchPorts() {
    clearLayer('portwatch_ports');
    const d = await getCache('portwatch_ports');
    if (!d) return;
    const items = d.ports || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.anchor, '#06b6d4', 22);
    items.slice(0, 800).forEach(p => {
      if (p.lat == null || p.lon == null) return;
      addEntity('portwatch_ports', {
        position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat),
        billboard: { image: glyph, scale: 0.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: p.port || p.name || 'Port',
        properties: pc({
          title: p.port || p.name || 'Port',
          source_name: 'IMF PortWatch',
          source_url: 'https://portwatch.imf.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(p.date || p.latest_date),
          location: p.country || '',
          values: [
            { label: 'Country',   value: p.country || '—' },
            { label: 'Vessels/day', value: (p.vessels_total || p.vessels || '—') + '' },
            { label: 'Capacity DWT',value: (p.capacity_dwt || '—') + '' },
          ],
          category_color: '#06b6d4',
        }),
      });
    });
  }

  // ============================================================
  // DISASTERS (EONET) — 200 active natural events
  // ============================================================
  async function renderDisasters() {
    clearLayer('disasters');
    const d = await getCache('disasters');
    if (!d) return;
    const items = d.events || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const byCat = {
      'wildfires':   { glyph: P.volcano, color: '#ef4444' },
      'severeStorms':{ glyph: P.cyclone, color: '#a855f7' },
      'volcanoes':   { glyph: P.volcano, color: '#dc2626' },
      'floods':      { glyph: P.drop,    color: '#3b82f6' },
      'drought':     { glyph: P.drop,    color: '#f59e0b' },
      'seaLakeIce':  { glyph: P.drop,    color: '#06b6d4' },
      'earthquakes': { glyph: P.bolt,    color: '#facc15' },
      'dustHaze':    { glyph: P.bolt,    color: '#a16207' },
      'manmade':     { glyph: P.bolt,    color: '#94a3b8' },
      'default':     { glyph: P.siren,   color: '#f97316' },
    };
    items.slice(0, 300).forEach(ev => {
      const cat = (ev.categories && ev.categories[0]?.id) || ev.category || 'default';
      const style = byCat[cat] || byCat.default;
      const glyph = makeGlyph(style.glyph, style.color, 26);
      const geom = ev.geometry && ev.geometry[ev.geometry.length - 1];
      const lat = ev.lat ?? (geom && geom.coordinates && geom.coordinates[1]);
      const lon = ev.lon ?? (geom && geom.coordinates && geom.coordinates[0]);
      if (lat == null || lon == null) return;
      addEntity('disasters', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.75, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: ev.title || 'Natural event',
        properties: pc({
          title: ev.title || 'Natural event',
          source_name: 'NASA EONET',
          source_url: ev.link || 'https://eonet.gsfc.nasa.gov/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(geom && geom.date),
          location: '',
          values: [
            { label: 'Category',  value: cat },
            { label: 'Sources',   value: (ev.sources || []).map(s => s.id).join(', ') || '—' },
          ],
          category_color: style.color,
        }),
        description: `<b>${ev.title}</b><br>Category: ${cat}`,
      });
    });
  }

  // ============================================================
  // EIA-930 GRID — US balancing authorities
  // Backend writes lat=0/lon=0 for all BAs; frontend-side centroid lookup.
  // ============================================================
  const BA_COORDS = {
    CISO: [36.78, -119.42], ERCO: [31.48, -99.25], PJM:  [39.95, -76.88],
    MISO: [41.74, -93.87],  NYIS: [42.95, -75.52], ISNE: [42.35, -71.07],
    BPAT: [45.60, -122.56], PACW: [45.52, -122.68], PACE: [40.76, -111.89],
    AZPS: [33.45, -112.07], PSCO: [39.74, -104.99], SWPP: [35.47, -97.51],
    SOCO: [33.74, -84.39],  TVA:  [35.04, -85.32], FPL:  [25.78, -80.19],
    DUK:  [35.23, -80.84],  LDWP: [34.05, -118.24], NEVP: [36.17, -115.14],
    IID:  [33.08, -115.52], SPA:  [36.83, -92.98], WACM: [40.42, -104.66],
    WAUW: [46.87, -103.89], AVA:  [47.66, -117.43], AEC:  [30.70, -88.04],
    AECI: [38.07, -94.04],  GVL:  [29.65, -82.32], HST:  [21.31, -157.86],
    NSB:  [41.27, -76.00],  SCEG: [33.99, -81.04],  SRP: [33.45, -111.93],
    TEC:  [27.95, -82.46],  YAD:  [35.97, -80.00],  TIDC:[37.73, -121.43],
    TPWR: [47.25, -122.44], CPLE: [35.77, -78.64],  CPLW: [35.77, -78.64],
    BANC: [39.52, -121.56], BPAT_: [45.60, -122.56], SEC: [25.00, -80.00],
  };

  async function renderEia930() {
    clearLayer('eia_930_grid');
    const d = await getCache('eia_930_grid');
    if (!d) return;
    const byBa = d.by_ba || d.bas || d.balancing_authorities || {};
    const glyph = makeGlyph(P.grid, '#14b8a6', 24);
    Object.values(byBa).forEach(ba => {
      const code = ba.ba || ba.code;
      const coords = (ba.lat && ba.lon && ba.lat !== 0) ? [ba.lat, ba.lon] : BA_COORDS[code];
      if (!coords) return;
      const [lat, lon] = coords;
      addEntity('eia_930_grid', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.7, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: ba.name || code || 'US BA',
        properties: pc({
          title: ba.name || code,
          source_name: 'US EIA-930',
          source_url: 'https://www.eia.gov/electricity/gridmonitor/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(ba.latest_period),
          location: 'United States',
          values: [
            { label: 'BA code',          value: code || '—' },
            { label: 'Demand (MW)',      value: ba.D || '—' },
            { label: 'Generation (MW)',  value: ba.NG || '—' },
            { label: 'Interchange (MW)', value: ba.TI || '—' },
            { label: 'Forecast (MW)',    value: ba.DF || '—' },
          ],
          category_color: '#14b8a6',
        }),
      });
    });
  }

  // ============================================================
  // CONFLICT EVENTS (GDELT Events 2.0 real-time) — 1500 violent events
  // ============================================================
  async function renderConflictEvents() {
    clearLayer('conflict_events');
    const d = await getCache('conflict_events');
    if (!d) return;
    const items = d.events || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.swords, '#ef4444', 20);
    items.slice(0, 1500).forEach(ev => {
      if (ev.lat == null || ev.lon == null) return;
      if (ev.lat === 0 && ev.lon === 0) return;
      addEntity('conflict_events', {
        position: Cesium.Cartesian3.fromDegrees(ev.lon, ev.lat),
        billboard: { image: glyph, scale: 0.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: ev.event_type || 'Violent event',
        properties: pc({
          title: ev.event_type || 'Violent event',
          source_name: 'GDELT Events 2.0',
          source_url: ev.source_url || 'https://gdeltproject.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(ev.date),
          location: (ev.country || '') + (ev.admin1 ? ', ' + ev.admin1 : ''),
          values: [
            { label: 'Actors',   value: (ev.actor1 || '?') + ' → ' + (ev.actor2 || '?') },
            { label: 'Country',  value: ev.country || '—' },
            { label: 'Mentions', value: String(ev.mentions || '—') },
            { label: 'Goldstein',value: ev.goldstein != null ? ev.goldstein.toFixed(1) : '—' },
          ],
          category_color: '#ef4444',
        }),
      });
    });
  }

  // ============================================================
  // NEWS (GDELT breaking) — geocoded via sourcecountry → centroid
  // GDELT doc API doesn't return lat/lon, so we map sourcecountry
  // to the country centroid from the population cache.
  // ============================================================
  async function renderNews() {
    clearLayer('news');
    const d = await getCache('news');
    if (!d) return;
    const items = d.articles || d.items || d.news || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.news, '#ec4899', 22);
    const seen = {};
    items.slice(0, 150).forEach(it => {
      let lat = it.lat ?? it.latitude;
      let lon = it.lon ?? it.longitude;
      if (lat == null || lon == null || (lat === 0 && lon === 0)) {
        const coords = getCountryCoords(it.sourcecountry || it.country);
        if (!coords) return;
        [lat, lon] = coords;
        // Jitter so markers don't stack perfectly
        const jk = (seen[it.sourcecountry] || 0);
        seen[it.sourcecountry] = jk + 1;
        lat += (jk % 5 - 2) * 0.8;
        lon += (Math.floor(jk / 5) % 3 - 1) * 0.8;
      }
      addEntity('news', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: (it.title || 'News').slice(0, 60),
        properties: pc({
          title: it.title || 'News article',
          source_name: it.domain || 'GDELT',
          source_url: it.url || 'https://api.gdeltproject.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(it.seendate || it.date || it.published),
          location: it.sourcecountry || '',
          values: [
            { label: 'Domain',  value: it.domain || '—' },
            { label: 'Country', value: it.sourcecountry || '—' },
            { label: 'Lang',    value: it.language || '—' },
          ],
          category_color: '#ec4899',
        }),
        description: `<b>${(it.title || '').slice(0, 80)}</b><br>${it.domain || ''}<br><a href="${it.url}" target="_blank">Open →</a>`,
      });
    });
  }

  // ============================================================
  // CONFLICTS (GDELT doc API armed conflict) — geocoded via sourcecountry
  // ============================================================
  async function renderConflicts() {
    clearLayer('conflicts');
    const d = await getCache('conflicts');
    if (!d) return;
    const items = d.articles || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.news, '#dc2626', 22);
    const seen = {};
    items.slice(0, 150).forEach(it => {
      let lat = it.lat ?? it.latitude;
      let lon = it.lon ?? it.longitude;
      if (lat == null || lon == null || (lat === 0 && lon === 0)) {
        const coords = getCountryCoords(it.sourcecountry || it.country);
        if (!coords) return;
        [lat, lon] = coords;
        const jk = (seen[it.sourcecountry] || 0);
        seen[it.sourcecountry] = jk + 1;
        lat += (jk % 5 - 2) * 0.8;
      }
      addEntity('conflicts', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: (it.title || 'Conflict news').slice(0, 60),
        properties: pc({
          title: it.title || 'Armed conflict news',
          source_name: it.domain || 'GDELT',
          source_url: it.url || 'https://gdeltproject.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(it.seendate || it.date),
          location: it.sourcecountry || '',
          values: [
            { label: 'Domain',  value: it.domain || '—' },
            { label: 'Country', value: it.sourcecountry || '—' },
          ],
          category_color: '#dc2626',
        }),
      });
    });
  }

  // ============================================================
  // CRISES (HDX humanitarian) — geocoded via country name
  // Shape: {data: [{name, country, description, ...}]} — no coords
  // ============================================================
  async function renderCrises() {
    clearLayer('crises');
    const d = await getCache('crises');
    if (!d) return;
    const items = d.data || d.items || d.crises || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.siren, '#f97316', 24);
    const seen = {};
    items.slice(0, 100).forEach(it => {
      let lat = it.lat;
      let lon = it.lon;
      if (lat == null || lon == null || (lat === 0 && lon === 0)) {
        const coords = getCountryCoords(it.country);
        if (!coords) return;
        [lat, lon] = coords;
        const jk = (seen[it.country] || 0);
        seen[it.country] = jk + 1;
        lat += (jk % 4 - 1.5) * 1.0;
      }
      addEntity('crises', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.7, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: (it.name || it.title || 'Crisis').slice(0, 60),
        properties: pc({
          title: it.name || it.title || 'Humanitarian dataset',
          source_name: 'HDX',
          source_url: 'https://data.humdata.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(it.date || it.last_modified || it.metadata_modified),
          location: it.country || '',
          values: [
            { label: 'Country', value: it.country || '—' },
            { label: 'Org',     value: it.organization?.title || it.org || '—' },
          ],
          category_color: '#f97316',
        }),
      });
    });
  }

  // ============================================================
  // RELIEFWEB (HDX-backed now) — geocoded via country name
  // Shape: {disasters: [{name, country, description, ...}]}
  // ============================================================
  async function renderReliefWeb() {
    clearLayer('reliefweb');
    const d = await getCache('reliefweb');
    if (!d) return;
    const items = d.disasters || d.items || d.articles || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.siren, '#fbbf24', 22);
    const seen = {};
    items.slice(0, 50).forEach(it => {
      let lat = it.lat;
      let lon = it.lon;
      if (lat == null || lon == null || (lat === 0 && lon === 0)) {
        // Try country field variations
        const cname = it.country || (it.groups && it.groups[0]?.title);
        const coords = getCountryCoords(cname);
        if (!coords) return;
        [lat, lon] = coords;
        const jk = (seen[cname] || 0);
        seen[cname] = jk + 1;
        lat += (jk % 3 - 1) * 1.2;
      }
      addEntity('reliefweb', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.6, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: (it.name || it.title || 'Humanitarian').slice(0, 60),
        properties: pc({
          title: it.name || it.title || 'Humanitarian',
          source_name: 'HDX (ReliefWeb)',
          source_url: 'https://data.humdata.org/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(it.date || it.metadata_modified),
          location: it.country || '',
          values: [
            { label: 'Country', value: it.country || '—' },
          ],
          category_color: '#fbbf24',
        }),
      });
    });
  }

  // ============================================================
  // YOUTUBE — top 5 trending × ~30 countries at capital coords
  // Shape: {countries: [{code, name, lat, lon, videos: [...]}]}
  // ============================================================
  async function renderYoutube() {
    clearLayer('youtube');
    const d = await getCache('youtube');
    if (!d) return;
    const countries = d.countries || [];
    const glyph = makeGlyph(P.play, '#ff0000', 24);
    countries.forEach(c => {
      if (c.lat == null || c.lon == null) return;
      const vids = c.videos || [];
      vids.slice(0, 5).forEach((v, i) => {
        // Jitter by index so multiple videos per country don't stack
        const latJ = c.lat + (i - 2) * 0.3;
        addEntity('youtube', {
          position: Cesium.Cartesian3.fromDegrees(c.lon, latJ),
          billboard: { image: glyph, scale: 0.55, disableDepthTestDistance: Number.POSITIVE_INFINITY },
          name: v.title || 'YouTube trending',
          properties: pc({
            title: v.title || 'YouTube trending',
            source_name: 'YouTube Data v3',
            source_url: v.url || (v.id ? `https://youtube.com/watch?v=${v.id}` : 'https://youtube.com/'),
            fetched_at: fmtISO(d.fetched),
            event_date: fmtISO(v.published || v.publishedAt),
            location: c.name || c.code || '',
            values: [
              { label: 'Channel', value: v.channel || '—' },
              { label: 'Views',   value: (v.views || '—') + '' },
              { label: 'Likes',   value: (v.likes || '—') + '' },
              { label: 'Country', value: c.name || '—' },
              { label: 'Rank',    value: '#' + (i + 1) },
            ],
            category_color: '#ff0000',
          }),
        });
      });
    });
  }

  // ============================================================
  // WEBCAMS (Windy) — 500 live camera pins
  // Shape: {webcams: [{title, location: {latitude, longitude, city, country}, ...}]}
  // ============================================================
  async function renderWebcams() {
    clearLayer('webcams');
    const d = await getCache('webcams');
    if (!d) return;
    const items = d.webcams || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.camera, '#06b6d4', 22);
    items.slice(0, 500).forEach(w => {
      const loc = w.location || {};
      const lat = loc.latitude ?? w.lat;
      const lon = loc.longitude ?? w.lon;
      if (lat == null || lon == null) return;
      const img = w.images?.current?.thumbnail || w.images?.current?.preview;
      addEntity('webcams', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.55, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: w.title || 'Webcam',
        properties: pc({
          title: w.title || 'Live webcam',
          source_name: 'Windy Webcams',
          source_url: w.player?.day || 'https://windy.com/webcams/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(w.lastUpdatedOn),
          location: (loc.city || '') + (loc.country ? ', ' + loc.country : ''),
          values: [
            { label: 'City',    value: loc.city || '—' },
            { label: 'Country', value: loc.country || '—' },
            { label: 'Region',  value: loc.region || '—' },
            { label: 'Views',   value: w.viewCount?.toLocaleString() || '—' },
            { label: 'Status',  value: w.status || 'active' },
          ],
          category_color: '#06b6d4',
        }),
        description: img
          ? `<img src="${img}" style="width:100%;margin-bottom:6px"><br><b>${w.title}</b><br>${loc.city || ''}, ${loc.country || ''}`
          : `<b>${w.title}</b>`,
      });
    });
  }

  // ============================================================
  // RADIO — 500 internet radio stations
  // ============================================================
  async function renderRadio() {
    clearLayer('radio');
    const d = await getCache('radio');
    if (!d) return;
    const items = d.stations || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const glyph = makeGlyph(P.broadcast, '#ec4899', 22);
    items.slice(0, 500).forEach(s => {
      const lat = s.lat ?? s.latitude ?? s.geo_lat;
      const lon = s.lon ?? s.longitude ?? s.geo_long;
      if (lat == null || lon == null) return;
      addEntity('radio', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: s.name || 'Radio station',
        properties: pc({
          title: s.name || 'Radio station',
          source_name: 'Radio Browser',
          source_url: s.url_resolved || s.url || s.homepage || 'https://www.radio-browser.info/',
          fetched_at: fmtISO(d.fetched),
          location: (s.country || '') + (s.state ? ', ' + s.state : ''),
          values: [
            { label: 'Country',  value: s.country || '—' },
            { label: 'Language', value: s.language || '—' },
            { label: 'Tags',     value: (s.tags || '').slice(0, 80) || '—' },
            { label: 'Bitrate',  value: s.bitrate ? s.bitrate + ' kbps' : '—' },
          ],
          category_color: '#ec4899',
        }),
      });
    });
  }

  // ============================================================
  // TEMPERATURE FIELD — global grid from Open-Meteo (Phase 4)
  // Each grid point becomes a coloured circle showing surface temp.
  // ============================================================
  async function renderTempField() {
    clearLayer('temperature_field');
    const d = await getCache('temperature_field');
    if (!d || !d.grid) return;
    function tempColor(t) {
      if (t == null) return '#94a3b8';
      if (t < -30) return '#1e3a5f';
      if (t < -15) return '#2563eb';
      if (t < 0)   return '#38bdf8';
      if (t < 10)  return '#06b6d4';
      if (t < 20)  return '#22c55e';
      if (t < 30)  return '#facc15';
      if (t < 40)  return '#f97316';
      return '#dc2626';
    }
    d.grid.forEach(pt => {
      if (pt.lat == null || pt.lon == null) return;
      const t = pt.temp_c;
      addEntity('temperature_field', {
        position: Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat),
        point: {
          pixelSize: 18,
          color: Cesium.Color.fromCssColorString(tempColor(t)).withAlpha(0.7),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.3),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: t != null ? t.toFixed(0) + '°' : '—',
          font: '600 9px Inter',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 12000000),
        },
        name: `${t != null ? t.toFixed(1) : '—'}°C`,
        properties: pc({
          title: 'Surface temperature',
          source_name: 'Open-Meteo',
          source_url: 'https://open-meteo.com/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(pt.time),
          location: `${pt.lat}°, ${pt.lon}°`,
          values: [
            { label: 'Temp',     value: t != null ? t.toFixed(1) + ' °C' : '—' },
            { label: 'Feels',    value: pt.feels_c != null ? pt.feels_c.toFixed(1) + ' °C' : '—' },
            { label: 'Humidity', value: pt.humidity != null ? pt.humidity + ' %' : '—' },
            { label: 'Pressure', value: pt.pressure_hpa != null ? pt.pressure_hpa.toFixed(0) + ' hPa' : '—' },
            { label: 'Cloud',    value: pt.cloud_pct != null ? pt.cloud_pct + ' %' : '—' },
          ],
          category_color: tempColor(t),
        }),
      });
    });
  }

  // ============================================================
  // RAINVIEWER — precipitation radar overlay tiles (Phase 4)
  // Adds a Cesium imagery layer from the latest RainViewer radar frame.
  // ============================================================
  async function renderRainviewer() {
    clearLayer('rainviewer');
    const d = await getCache('rainviewer');
    if (!d) return;
    // RainViewer returns { host, radar: { past: [{path, time}], nowcast: [...] } }
    // or { generated, host, radar: {past: [...]}, satellite: {...} }
    const host = d.host || 'https://tilecache.rainviewer.com';
    const frames = d.radar?.past || d.past || [];
    if (!frames.length) return;
    // Use the latest frame
    const latest = frames[frames.length - 1];
    if (!latest || !latest.path) return;
    try {
      const tileUrl = `${host}${latest.path}/256/{z}/{x}/{y}/2/1_1.png`;
      const provider = new Cesium.UrlTemplateImageryProvider({
        url: tileUrl,
        minimumLevel: 0,
        maximumLevel: 8,
        credit: 'RainViewer',
      });
      const layer = window.viewer.imageryLayers.addImageryProvider(provider);
      layer.alpha = 0.65;
      // Track this imagery layer so clearLayer can remove it
      if (!window._layerEntities) window._layerEntities = {};
      window._layerEntities['rainviewer'] = [layer];
    } catch (e) {
      console.warn('[layers2] rainviewer imagery failed:', e);
    }
  }

  // Override clearLayer for rainviewer since it's an imagery layer, not entities
  const _origClearRainviewer = clearLayer;
  function clearRainviewer() {
    const arr = window._layerEntities && window._layerEntities['rainviewer'];
    if (arr && arr.length) {
      arr.forEach(item => {
        try {
          if (item instanceof Cesium.ImageryLayer) {
            window.viewer.imageryLayers.remove(item);
          } else {
            window.viewer.entities.remove(item);
          }
        } catch (_) {}
      });
    }
    if (window._layerEntities) window._layerEntities['rainviewer'] = [];
  }

  // ============================================================
  // SPORTS (ESPN) — live match venue pins
  // Shape: {matches: [{sport, league, home, away, status, lat, lon, ...}]}
  //    OR  {events: [...]}
  // ============================================================
  async function renderSports() {
    clearLayer('sports');
    const d = await getCache('sports');
    if (!d) return;
    const items = d.matches || d.events || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(items)) return;
    const colors = {
      soccer: '#22c55e', basketball: '#f97316', football: '#3b82f6',
      'formula-1': '#ef4444', tennis: '#facc15', cricket: '#a855f7',
    };
    items.forEach(m => {
      let lat = m.lat ?? m.latitude;
      let lon = m.lon ?? m.longitude;
      if (lat == null || lon == null) {
        const coords = getCountryCoords(m.country || m.venue_country);
        if (!coords) return;
        [lat, lon] = coords;
      }
      const sport = m.sport || m.league || 'sports';
      const color = colors[sport.toLowerCase()] || '#94a3b8';
      const glyph = makeGlyph(P.tv, color, 24);
      addEntity('sports', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: 0.7, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: (m.name || `${m.home || '?'} vs ${m.away || '?'}`).slice(0, 60),
        properties: pc({
          title: m.name || `${m.home || '?'} vs ${m.away || '?'}`,
          source_name: 'ESPN',
          source_url: m.url || 'https://www.espn.com/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(m.date || m.start_time),
          location: m.venue || m.city || '',
          values: [
            { label: 'Sport',  value: sport },
            { label: 'League', value: m.league || '—' },
            { label: 'Score',  value: m.score || m.status || '—' },
            { label: 'Venue',  value: m.venue || '—' },
          ],
          category_color: color,
        }),
      });
    });
  }

  // ============================================================
  // PRESSURE FIELD — global grid from Open-Meteo (Phase 4+)
  // ============================================================
  async function renderPressureField() {
    clearLayer('pressure_field');
    const d = await getCache('pressure_field');
    if (!d || !d.grid) return;
    function pressColor(p) {
      if (p == null) return '#94a3b8';
      if (p < 990) return '#3b82f6';   // deep low
      if (p < 1000) return '#60a5fa';  // low
      if (p < 1010) return '#a5b4fc';  // normal-low
      if (p < 1020) return '#fde68a';  // normal-high
      if (p < 1030) return '#f97316';  // high
      return '#dc2626';                // very high
    }
    d.grid.forEach(pt => {
      if (pt.lat == null || pt.lon == null) return;
      const p = pt.pressure_hpa;
      addEntity('pressure_field', {
        position: Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat),
        point: {
          pixelSize: 14,
          color: Cesium.Color.fromCssColorString(pressColor(p)).withAlpha(0.6),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.3),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: p != null ? p.toFixed(0) : '—',
          font: '500 8px Inter',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -12),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 10000000),
        },
        name: p != null ? p.toFixed(0) + ' hPa' : '—',
        properties: pc({
          title: 'Surface Pressure',
          source_name: 'Open-Meteo',
          source_url: 'https://open-meteo.com/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(pt.time),
          location: pt.lat + '°, ' + pt.lon + '°',
          values: [
            { label: 'Pressure', value: p != null ? p.toFixed(1) + ' hPa' : '—' },
            { label: 'Cloud',    value: pt.cloud_pct != null ? pt.cloud_pct + '%' : '—' },
          ],
          category_color: pressColor(p),
        }),
      });
    });
  }

  // ============================================================
  // SEA SURFACE TEMPERATURE — NOAA/Open-Meteo Marine
  // ============================================================
  async function renderSST() {
    clearLayer('noaa_sst');
    const d = await getCache('noaa_sst');
    if (!d || !d.grid) return;
    function sstColor(t) {
      if (t == null) return '#94a3b8';
      if (t < 0)  return '#1e3a8a';
      if (t < 5)  return '#2563eb';
      if (t < 10) return '#0ea5e9';
      if (t < 15) return '#06b6d4';
      if (t < 20) return '#14b8a6';
      if (t < 25) return '#22c55e';
      if (t < 28) return '#facc15';
      if (t < 30) return '#f97316';
      return '#dc2626';
    }
    d.grid.forEach(pt => {
      if (pt.lat == null || pt.lon == null) return;
      const t = pt.sst_c;
      addEntity('noaa_sst', {
        position: Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat),
        point: {
          pixelSize: 16,
          color: Cesium.Color.fromCssColorString(sstColor(t)).withAlpha(0.7),
          outlineColor: Cesium.Color.fromCssColorString('#0077be').withAlpha(0.4),
          outlineWidth: 2,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: t != null ? t.toFixed(0) + '°' : '—',
          font: '600 9px Inter',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -14),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 12000000),
        },
        name: 'SST ' + (t != null ? t.toFixed(1) + '°C' : '—'),
        properties: pc({
          title: 'Sea Surface Temperature',
          source_name: 'Open-Meteo Marine',
          source_url: 'https://open-meteo.com/en/docs/marine-weather-api',
          fetched_at: fmtISO(d.fetched),
          location: pt.lat + '°, ' + pt.lon + '°',
          values: [
            { label: 'SST',      value: t != null ? t.toFixed(1) + ' °C' : '—' },
            { label: 'Current',  value: pt.current_velocity != null ? pt.current_velocity.toFixed(2) + ' m/s' : '—' },
            { label: 'Direction',value: pt.current_direction != null ? pt.current_direction.toFixed(0) + '°' : '—' },
          ],
          category_color: sstColor(t),
        }),
      });
    });
  }

  // ============================================================
  // HUMIDITY FIELD — global grid from Open-Meteo
  // ============================================================
  async function renderHumidity() {
    clearLayer('humidity_field');
    const d = await getCache('humidity_field');
    if (!d || !d.grid) return;
    function humColor(h) {
      if (h == null) return '#94a3b8';
      if (h < 20) return '#f97316';  // very dry
      if (h < 40) return '#facc15';  // dry
      if (h < 60) return '#22c55e';  // comfortable
      if (h < 80) return '#3b82f6';  // humid
      return '#6366f1';              // very humid
    }
    d.grid.forEach(pt => {
      if (pt.lat == null || pt.lon == null) return;
      const h = pt.humidity_pct;
      addEntity('humidity_field', {
        position: Cesium.Cartesian3.fromDegrees(pt.lon, pt.lat),
        point: {
          pixelSize: 14,
          color: Cesium.Color.fromCssColorString(humColor(h)).withAlpha(0.6),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.3),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        label: {
          text: h != null ? h + '%' : '',
          font: '500 8px Inter',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -12),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 10000000),
        },
        name: h != null ? h + '% RH' : 'Humidity',
        properties: pc({
          title: 'Relative Humidity',
          source_name: 'Open-Meteo',
          source_url: 'https://open-meteo.com/',
          fetched_at: fmtISO(d.fetched),
          event_date: fmtISO(pt.time),
          location: pt.lat + ', ' + pt.lon,
          values: [
            { label: 'Humidity', value: h != null ? h + ' %' : '' },
            { label: 'Dew point', value: pt.dew_point_c != null ? pt.dew_point_c.toFixed(1) + ' C' : '' },
            { label: 'Temp', value: pt.temp_c != null ? pt.temp_c.toFixed(1) + ' C' : '' },
          ],
          category_color: humColor(h),
        }),
      });
    });
  }

  // ============================================================
  // ENTSO-E European Grid — generation, load, price per country
  // ============================================================
  async function renderEntsoe() {
    clearLayer('entsoe_grid');
    const d = await getCache('entsoe_grid');
    if (!d || !d.countries) return;
    const countries = d.countries;
    function priceColor(p) {
      if (p == null || p === 0) return '#94a3b8';
      if (p < 30)  return '#22c55e';  // cheap
      if (p < 60)  return '#facc15';  // moderate
      if (p < 100) return '#f97316';  // expensive
      if (p < 200) return '#ef4444';  // very expensive
      return '#dc2626';               // crisis
    }
    Object.values(countries).forEach(c => {
      if (c.lat == null || c.lon == null) return;
      const gen = c.total_generation_mw || 0;
      const load = c.load_mw || 0;
      const price = c.price_eur_mwh || 0;
      const renew = c.renewable_pct || 0;
      const fuel = c.fuel_mix || {};
      const glyph = makeGlyph(P.bolt, priceColor(price), 28);
      addEntity('entsoe_grid', {
        position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat),
        billboard: { image: glyph, scale: 0.85, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        label: {
          text: gen > 0 ? (gen/1000).toFixed(1) + 'GW' : '',
          font: '700 10px Inter',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -18),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 8000000),
        },
        name: c.name + ' Grid',
        properties: pc({
          title: c.name + ' — European Grid',
          source_name: 'ENTSO-E Transparency Platform',
          source_url: 'https://transparency.entsoe.eu/',
          fetched_at: fmtISO(d.fetched),
          location: c.name,
          values: [
            { label: 'Generation',   value: gen > 0 ? (gen/1000).toFixed(1) + ' GW' : '—' },
            { label: 'Load',         value: load > 0 ? (load/1000).toFixed(1) + ' GW' : '—' },
            { label: 'Price',        value: price > 0 ? price.toFixed(1) + ' EUR/MWh' : '—' },
            { label: 'Renewable %',  value: renew > 0 ? renew.toFixed(1) + '%' : '—' },
            { label: 'Solar',        value: fuel.solar ? Math.round(fuel.solar) + ' MW' : '—' },
            { label: 'Wind',         value: fuel.wind ? Math.round(fuel.wind) + ' MW' : '—' },
            { label: 'Nuclear',      value: fuel.nuclear ? Math.round(fuel.nuclear) + ' MW' : '—' },
            { label: 'Gas',          value: fuel.gas ? Math.round(fuel.gas) + ' MW' : '—' },
            { label: 'Coal',         value: fuel.coal ? Math.round(fuel.coal) + ' MW' : '—' },
            { label: 'Hydro',        value: fuel.hydro ? Math.round(fuel.hydro) + ' MW' : '—' },
          ],
          category_color: priceColor(price),
        }),
      });
    });
  }

  // ============================================================
  // UCDP API — 5000 academic conflict events (2024+, Gold-tier)
  // Data shape: {events: [{lat,lon,value,label,popup,props:{side_a,side_b,country,...}}]}
  // ============================================================
  async function renderUcdpApi() {
    clearLayer('ucdp');
    const d = await getCache('ucdp');
    if (!d) return;
    const events = d.events || d.items || (Array.isArray(d) ? d : []);
    if (!Array.isArray(events)) return;
    const glyph = makeGlyph(P.swords, '#ef4444', 22);
    events.slice(0, 3000).forEach(ev => {
      const lat = parseFloat(ev.lat);
      const lon = parseFloat(ev.lon);
      if (!lat || !lon || (lat === 0 && lon === 0)) return;
      const props = ev.props || {};
      const deaths = parseInt(props.total_deaths || ev.value || 0);
      const sizeScale = Math.max(0.4, Math.min(1.2, deaths / 50));
      addEntity('ucdp', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        billboard: { image: glyph, scale: sizeScale, disableDepthTestDistance: Number.POSITIVE_INFINITY },
        name: ev.label || (props.side_a + ' vs ' + props.side_b) || 'UCDP event',
        properties: pc({
          title: props.conflict_name || ev.label || 'UCDP Conflict Event',
          source_name: 'UCDP (Uppsala University)',
          source_url: 'https://ucdp.uu.se/',
          fetched_at: fmtISO(d.fetched || d.source),
          event_date: fmtISO(props.date_start),
          location: (props.country || '') + (props.adm_1 ? ', ' + props.adm_1 : ''),
          values: [
            { label: 'Conflict', value: props.conflict_name || '—' },
            { label: 'Dyad', value: props.dyad_name || '—' },
            { label: 'Side A', value: props.side_a || '—' },
            { label: 'Side B', value: props.side_b || '—' },
            { label: 'Fatalities', value: String(deaths) },
            { label: 'Deaths (A)', value: props.deaths_a || '0' },
            { label: 'Deaths (B)', value: props.deaths_b || '0' },
            { label: 'Civilians', value: props.deaths_civ || '0' },
            { label: 'Date', value: props.date_start || '—' },
            { label: 'Country', value: props.country || '—' },
            { label: 'Source', value: (props.source_article || '').slice(0, 80) || '—' },
          ],
          category_color: '#ef4444',
        }),
        description: '<b>' + (props.dyad_name || ev.label || '') + '</b><br>' +
          (props.country || '') + ' · ' + (props.date_start || '') + '<br>' +
          'Fatalities: <b>' + deaths + '</b> (A:' + (props.deaths_a||0) + ' B:' + (props.deaths_b||0) + ' Civ:' + (props.deaths_civ||0) + ')<br>' +
          '<small>Source: UCDP GED API (CC BY 4.0) · Uppsala University</small>',
      });
    });
  }

  // ============================================================
  // Register every renderer into window.LAYERS
  // ============================================================
  // ============================================================
  // CO2 — Atmospheric CO₂ (Mauna Loa Keeling Curve + EPICA 800kyr composite)
  // Time-aware: scrub from 800,000 BC (~180 ppm during glacials) → 2026 (~430 ppm).
  // ============================================================
  let _co2Series = null;          // HistoricalSeries
  let _co2DataCache = null;       // cached raw aggregator response
  let _co2Unsub = null;           // Clock subscription
  async function renderCO2() {
    clearLayer('noaa_co2');
    if (_co2Unsub) { _co2Unsub(); _co2Unsub = null; }
    const d = await getCache('noaa_co2');
    if (!d) return;
    _co2DataCache = d;

    // Build the 800kyr→present series for time-aware lookup
    if (window.HistoricalSeries && Array.isArray(d.historical_series)) {
      _co2Series = new window.HistoricalSeries(d.historical_series, { interp: 'linear' });
      if (window.Scrubber && d.historical_range) {
        window.Scrubber.registerLayer('noaa_co2', d.historical_range, '#ff5050');
      }
    } else {
      _co2Series = null;
    }

    function ppmAt(year) {
      if (_co2Series) {
        const v = _co2Series.at(year);
        if (v != null) return v;
      }
      return (d.headline && d.headline.current_co2_ppm) || 0;
    }
    function originAt(year) {
      // Provenance label so the user knows whether they're looking at ice-core
      // proxy data or instrumental measurements.
      if (year < 1958) return 'EPICA / Antarctic ice-core composite (Bereiter 2015)';
      return 'Mauna Loa Observatory · NOAA GML';
    }

    const stations = d.stations || [];
    const primaryEntities = [];   // entities whose label updates on time-scrub

    stations.forEach(s => {
      const isPrimary = s.props && s.props.is_primary;
      const code = (s.props && s.props.station_code) || s.id || '';
      const sName = (s.props && s.props.station_name) || code;
      const elev = (s.props && s.props.elevation_m) || 0;
      const sz = isPrimary ? 20 : 10;
      const color = isPrimary ? '#ff5050' : '#7dd3fc';

      // Reactive label text — re-evaluated every frame from window.__CURRENT_YEAR__
      const labelText = isPrimary
        ? new Cesium.CallbackProperty(() => {
            const y = window.__CURRENT_YEAR__ || (new Date().getUTCFullYear());
            return ppmAt(y).toFixed(1) + ' ppm';
          }, false)
        : undefined;

      const ent = addEntity('noaa_co2', {
        position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat),
        point: {
          pixelSize: sz,
          color: Cesium.Color.fromCssColorString(color).withAlpha(isPrimary ? 0.95 : 0.7),
          outlineColor: Cesium.Color.WHITE.withAlpha(isPrimary ? 0.8 : 0.4),
          outlineWidth: isPrimary ? 3 : 1.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        label: isPrimary ? {
          text: labelText,
          font: 'bold 13px Inter,sans-serif',
          fillColor: Cesium.Color.fromCssColorString('#ff5050'),
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          outlineColor: Cesium.Color.BLACK.withAlpha(0.7),
          outlineWidth: 2,
          pixelOffset: new Cesium.Cartesian2(0, -sz - 6),
          showBackground: true,
          backgroundColor: Cesium.Color.BLACK.withAlpha(0.5),
          backgroundPadding: new Cesium.Cartesian2(4, 2),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        } : undefined,
        name: isPrimary ? 'CO₂' : sName + ' (' + code + ')',
        properties: pc({
          title: isPrimary ? 'Atmospheric CO₂ — Keeling Curve + ice core' : sName + ' (' + code + ')',
          source_name: 'NOAA Global Monitoring Laboratory',
          source_url: 'https://gml.noaa.gov/ccgg/trends/',
          values: isPrimary ? [
            { label: 'Live data', value: 'scrub timeline at bottom' },
            { label: 'Range', value: '800,000 BC → today' },
            { label: 'Pre-industrial', value: '~280 ppm' },
          ] : [
            { label: 'Station', value: sName },
            { label: 'Code', value: code },
            { label: 'Elevation', value: elev + ' m' },
          ],
          category_color: color,
        }),
        description: isPrimary
          ? `<b>Mauna Loa Observatory</b><br>Scrub the timeline at the bottom to see CO₂ from 800,000 BC to present.<br>Pre-industrial: 280 ppm. Today: ${(d.headline?.current_co2_ppm || 0).toFixed(2)} ppm.`
          : `<b>${sName}</b> (${code})<br>Elevation: ${elev}m`,
      });
      if (isPrimary) primaryEntities.push(ent);
    });

    // Subscribe to time changes — update description text on the primary station
    // and refresh any open mapmode card / pickcard that references CO2.
    _co2Unsub = window.Clock && window.Clock.subscribe(year => {
      const v = ppmAt(year);
      const above = v - 280;
      for (const ent of primaryEntities) {
        ent.description = `<b>Atmospheric CO₂: ${v.toFixed(2)} ppm</b> in ${window.Clock.label(year)}<br>${above >= 0 ? '+' : ''}${above.toFixed(1)} ppm vs pre-industrial<br>Source: ${originAt(year)}`;
      }
    });
  }

  function registerAll() {
    if (!window.LAYERS) { setTimeout(registerAll, 100); return; }
    window.LAYERS.volcanoes          = { render: renderVolcanoes,        clear: () => clearLayer('volcanoes') };
    window.LAYERS.who_don            = { render: renderWhoDon,           clear: () => clearLayer('who_don') };
    window.LAYERS.air_quality        = { render: renderAirQuality,       clear: () => clearLayer('air_quality') };
    window.LAYERS.cloudflare_radar   = { render: renderCloudflareRadar,  clear: () => clearLayer('cloudflare_radar') };
    window.LAYERS.portwatch_ports    = { render: renderPortwatchPorts,   clear: () => clearLayer('portwatch_ports') };
    window.LAYERS.disasters          = { render: renderDisasters,        clear: () => clearLayer('disasters') };
    window.LAYERS.eia_930_grid       = { render: renderEia930,           clear: () => clearLayer('eia_930_grid') };
    window.LAYERS.conflict_events    = { render: renderConflictEvents,   clear: () => clearLayer('conflict_events') };
    window.LAYERS.news               = { render: renderNews,             clear: () => clearLayer('news') };
    window.LAYERS.conflicts          = { render: renderConflicts,        clear: () => clearLayer('conflicts') };
    window.LAYERS.crises             = { render: renderCrises,           clear: () => clearLayer('crises') };
    window.LAYERS.reliefweb          = { render: renderReliefWeb,        clear: () => clearLayer('reliefweb') };
    window.LAYERS.youtube            = { render: renderYoutube,          clear: () => clearLayer('youtube') };
    window.LAYERS.webcams            = { render: renderWebcams,          clear: () => clearLayer('webcams') };
    window.LAYERS.radio              = { render: renderRadio,            clear: () => clearLayer('radio') };
    window.LAYERS.sports             = { render: renderSports,           clear: () => clearLayer('sports') };
    window.LAYERS.temperature_field  = { render: renderTempField,        clear: () => clearLayer('temperature_field') };
    window.LAYERS.rainviewer         = { render: renderRainviewer,       clear: clearRainviewer };
    window.LAYERS.pressure_field     = { render: renderPressureField,    clear: () => clearLayer('pressure_field') };
    window.LAYERS.noaa_sst           = { render: renderSST,             clear: () => clearLayer('noaa_sst') };
    window.LAYERS.humidity_field     = { render: renderHumidity,         clear: () => clearLayer('humidity_field') };
    window.LAYERS.entsoe_grid       = { render: renderEntsoe,           clear: () => clearLayer('entsoe_grid') };
    window.LAYERS.ucdp              = { render: renderUcdpApi,          clear: () => clearLayer('ucdp') };
    window.LAYERS.noaa_co2           = { render: renderCO2,              clear: () => clearLayer('noaa_co2') };
    console.log('[layers2] registered', Object.keys(window.LAYERS).length, 'total renderers');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(registerAll, 300));
  } else {
    setTimeout(registerAll, 300);
  }
})();
