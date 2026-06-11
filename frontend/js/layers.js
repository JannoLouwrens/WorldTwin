// Data layer loaders + renderers. Each layer has:
//   id, fetcher (path to cache), renderer (entities), clearer.
// Entities owned by a layer are stored in window._layerEntities[id] for cleanup.
(function(){
  window._layerEntities = {};
  // window._cacheStore (managed by preloader.js) is the canonical cache store.

  function getEntityGroup(id) {
    if (!window._layerEntities[id]) window._layerEntities[id] = [];
    return window._layerEntities[id];
  }
  function addEntity(id, e) {
    const arr = getEntityGroup(id);
    const ent = viewer.entities.add(e);
    arr.push(ent);
    return ent;
  }
  function clearLayer(id) {
    const arr = window._layerEntities[id] || [];
    arr.forEach(e => { try { viewer.entities.remove(e); } catch(_){} });
    window._layerEntities[id] = [];
  }

  // Canonical cache fetch: store-first (preloader fills window._cacheStore),
  // in-flight dedupe, write-through. This file loads AFTER preloader.js and
  // its window.fetchCache export used to overwrite the store-aware one with
  // a plain network fetch — world_bank.json (22 MB) was downloaded TWICE on
  // every boot. The preloader's 2-min background refresh keeps fast layers
  // current in the store.
  const _inflight = {};
  async function fetchCache(id) {
    const store = window._cacheStore;
    if (store && store.has(id)) return store.get(id);
    if (_inflight[id]) return _inflight[id];
    _inflight[id] = (async () => {
      try {
        const r = await fetch('/api/cache/' + id + '.json');
        if (!r.ok) return null;
        const d = await r.json();
        if (store) store.set(id, d);
        return d;
      } catch (e) {
        console.warn('fetch', id, 'failed', e);
        return null;
      } finally {
        delete _inflight[id];
      }
    })();
    return _inflight[id];
  }

  // ==================================================
  // QUAKES — USGS
  // ==================================================
  async function renderQuakes() {
    clearLayer('quakes');
    const d = await fetchCache('quakes');
    if (!d || !d.features) return;
    d.features.forEach(f => {
      const c = f.geometry && f.geometry.coordinates;
      if (!c) return;
      const [lon, lat, depth] = c;
      const mag = f.properties.mag || 0;
      const depthKm = depth || 0;
      const age = Date.now() - (f.properties.time || Date.now());
      const fresh = age < 3600 * 1000;
      // Size = sqrt(mag), colour = depth
      const radius = DS.pointRadius(Math.pow(10, mag), 1000);
      const t = Math.min(1, depthKm / 300);
      const hex = DS.sampleRamp('depth', t);
      addEntity('quakes', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat),
        point: {
          pixelSize: radius,
          color: DS.c(hex, fresh ? 1.0 : 0.7),
          outlineColor: DS.c('#ffffff', 0.6),
          outlineWidth: 1.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        name: f.properties.place || 'Quake',
        description: `<b>M${mag.toFixed(1)}</b> • ${depthKm.toFixed(0)} km deep<br>${f.properties.place || ''}<br><a href="${f.properties.url}" target="_blank">USGS details →</a>`,
      });
    });
  }

  // ==================================================
  // FIRES — NASA FIRMS
  // ==================================================
  async function renderFires() {
    clearLayer('fires');
    const d = await fetchCache('fires');
    if (!Array.isArray(d)) return;
    // Keep only top-frp 1500 to avoid overload
    const sorted = d.slice().sort((a,b) => (b.frp||0) - (a.frp||0)).slice(0, 1500);
    sorted.forEach(f => {
      if (!f.lat || !f.lon) return;
      const frp = f.frp || 0;
      const radius = DS.pointRadius(frp, 10);
      const hex = DS.sampleRamp('fire', Math.min(1, frp / 100));
      addEntity('fires', {
        position: Cesium.Cartesian3.fromDegrees(f.lon, f.lat),
        point: {
          pixelSize: radius,
          color: DS.c(hex, 0.92),
          outlineColor: DS.c('#ffffff', 0.15),
          outlineWidth: 0.5,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
        name: 'Wildfire',
        description: `Fire radiative power: ${frp.toFixed(1)} MW<br>Detected: ${f.date} ${f.time} UTC<br>Satellite: ${f.sat}`,
      });
    });
  }

  // ==================================================
  // CABLES — submarine cables (the 710-feature fix)
  // ==================================================
  async function renderCables() {
    clearLayer('cables');
    const d = await fetchCache('cables');
    if (!d || !d.features) return;
    d.features.forEach(f => {
      if (!f.geometry) return;
      const p = f.properties || {};
      const colour = DS.c('#5eead4', 0.7);
      function addLine(coords) {
        if (!coords || coords.length < 2) return;
        const positions = [];
        coords.forEach(c => { if (c && c.length >= 2) positions.push(c[0], c[1]); });
        if (positions.length < 4) return;
        addEntity('cables', {
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(positions),
            width: 1.4,
            material: new Cesium.PolylineDashMaterialProperty({
              color: colour,
              dashLength: 20,
            }),
            arcType: Cesium.ArcType.GEODESIC,
            clampToGround: false,
          },
          name: p.name || 'Submarine Cable',
          description: `<b>${p.name || 'Cable'}</b><br>${p.owners ? 'Owners: ' + p.owners + '<br>' : ''}${p.length ? 'Length: ' + p.length + '<br>' : ''}${p.rfs ? 'Ready: ' + p.rfs : ''}`,
        });
      }
      if (f.geometry.type === 'LineString') addLine(f.geometry.coordinates);
      else if (f.geometry.type === 'MultiLineString') f.geometry.coordinates.forEach(addLine);
    });
  }

  // ==================================================
  // PORTWATCH CHOKEPOINTS — live shipping pulses
  // ==================================================
  async function renderPortwatchChokepoints(filterCategory=null) {
    clearLayer('portwatch_chokepoints');
    const d = await fetchCache('portwatch_chokepoints');
    if (!d || !d.chokepoints) return;
    const median = 80;
    d.chokepoints.forEach(cp => {
      const radius = DS.pointRadius(cp.n_total, median, 6, 28);
      // Colour by dominant cargo type
      const types = [
        ['tanker', cp.n_tanker, '#E69F00'],
        ['container', cp.n_container, '#56B4E9'],
        ['dry_bulk', cp.n_dry_bulk, '#D55E00'],
        ['roro', cp.n_roro, '#CC79A7'],
        ['general_cargo', cp.n_general_cargo, '#009E73'],
      ];
      types.sort((a,b) => b[1] - a[1]);
      const dominant = types[0];
      addEntity('portwatch_chokepoints', {
        position: Cesium.Cartesian3.fromDegrees(cp.lon, cp.lat, 5000),
        point: {
          pixelSize: radius,
          color: window.pulseAlpha(DS.c(dominant[2]), 0.5, 1.0, 0.6),
          outlineColor: DS.c('#ffffff', 0.9),
          outlineWidth: 2,
        },
        label: {
          text: cp.name + '\n' + cp.n_total + ' ships',
          font: '600 10px Inter',
          fillColor: DS.c('#ffffff', 0.95),
          outlineColor: DS.c('#000000', 0.9),
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -radius - 4),
          showBackground: true,
          backgroundColor: DS.c('#000000', 0.55),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 30000000),
        },
        name: cp.name,
        description: `
          <b>${cp.name}</b><br>
          Total ships today: <b>${cp.n_total}</b><br>
          Total capacity: <b>${DS.fmt(cp.capacity)} DWT</b><br><br>
          🛢 Tanker: ${cp.n_tanker} (${DS.fmt(cp.capacity_tanker||0)})<br>
          📦 Container: ${cp.n_container} (${DS.fmt(cp.capacity_container||0)})<br>
          🚢 Dry bulk: ${cp.n_dry_bulk} (${DS.fmt(cp.capacity_dry_bulk||0)})<br>
          🚙 Roro: ${cp.n_roro} (${DS.fmt(cp.capacity_roro||0)})<br>
          📋 General: ${cp.n_general_cargo} (${DS.fmt(cp.capacity_general_cargo||0)})<br>
          <br><small>Source: IMF PortWatch (CC BY 4.0)</small>
        `,
      });
    });
  }

  // ==================================================
  // TRADE ANNUAL — commodity arcs, filterable
  // ==================================================
  async function renderTradeAnnual(commodityId=null, categoryId=null) {
    clearLayer('trade_annual');
    const d = await fetchCache('trade_annual');
    if (!d || !d.flows) return;

    let flows = d.flows;
    if (commodityId && commodityId !== 'all') {
      if (d.by_commodity && d.by_commodity[commodityId]) flows = d.by_commodity[commodityId];
      else flows = d.flows.filter(f => f.commodity === commodityId);
    } else if (categoryId) {
      flows = d.flows.filter(f => f.category === categoryId);
    }
    // Keep top 200 for render budget
    flows = flows.slice(0, 200);

    const maxVal = flows[0] ? flows[0].value_usd : 1;
    flows.forEach((f, i) => {
      const catHue = DS.categoryHue[f.category] || '#ffffff';
      const w = DS.arcWidth(f.value_usd, 1, 6);

      // Great-circle arc rendered as a polyline with 32 segments
      const positions = buildGreatCircle(f.from_lat, f.from_lon, f.to_lat, f.to_lon, 32);

      addEntity('trade_annual', {
        polyline: {
          positions: positions,
          width: w,
          material: new Cesium.PolylineGlowMaterialProperty({
            glowPower: 0.25,
            taperPower: 0.9,
            color: DS.c(catHue, 0.85),
          }),
          arcType: Cesium.ArcType.NONE,  // positions already include altitude
        },
        name: `${f.commodity_name}: ${f.from_name} → ${f.to_name}`,
        description: `
          <b>${f.commodity_name}</b><br>
          ${f.from_name} → ${f.to_name}<br>
          Value: <b>$${DS.fmt(f.value_usd)}</b> (${f.year})<br>
          HS code: ${f.hs}<br>
          <small>Source: UN Comtrade</small>
        `,
      });
    });
  }

  // Build positions array for a great-circle arc with altitude hump
  function buildGreatCircle(lat1, lon1, lat2, lon2, segments=32) {
    // Spherical interpolation via Cartesian3
    const cart1 = Cesium.Cartesian3.fromDegrees(lon1, lat1, 0);
    const cart2 = Cesium.Cartesian3.fromDegrees(lon2, lat2, 0);
    const surfaceDistance = Cesium.Cartesian3.distance(cart1, cart2);
    const maxAlt = Math.min(1200000, surfaceDistance * 0.14);
    const positions = [];
    for (let i = 0; i <= segments; i++) {
      const t = i / segments;
      // Lerp lon/lat
      const lat = lat1 + (lat2 - lat1) * t;
      // Longitude interpolation accounting for dateline
      let dLon = lon2 - lon1;
      if (dLon > 180) dLon -= 360;
      if (dLon < -180) dLon += 360;
      const lon = lon1 + dLon * t;
      // Parabolic altitude
      const alt = 4 * maxAlt * t * (1 - t);
      positions.push(Cesium.Cartesian3.fromDegrees(lon, lat, alt));
    }
    return positions;
  }
  window.buildGreatCircle = buildGreatCircle;

  // ==================================================
  // WRI POWER PLANTS
  // ==================================================
  async function renderWriPowerPlants(filterFuel=null) {
    clearLayer('wri_power_plants');
    const d = await fetchCache('wri_power_plants');
    if (!d || !d.plants) return;
    // Top 1000 for render budget
    const plants = d.plants.slice(0, 1000);
    plants.forEach(p => {
      if (filterFuel && p.fuel_canonical !== filterFuel) return;
      const hex = DS.fuelHue[p.fuel_canonical] || '#6b7790';
      const radius = DS.pointRadius(p.capacity_mw, 500, 2, 14);
      addEntity('wri_power_plants', {
        position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat),
        point: {
          pixelSize: radius,
          color: DS.c(hex, 0.85),
          outlineColor: DS.c('#ffffff', 0.25),
          outlineWidth: 0.5,
        },
        name: p.name,
        description: `
          <b>${p.name}</b><br>
          ${p.country_long}<br>
          Fuel: ${p.fuel}<br>
          Capacity: <b>${p.capacity_mw.toFixed(0)} MW</b><br>
          Commissioned: ${p.commissioned || '—'}<br>
          Owner: ${p.owner || '—'}
        `,
      });
    });
  }

  // ==================================================
  // UCDP GED conflict events
  // ==================================================
  async function renderUcdp() {
    clearLayer('ucdp_ged');
    const d = await fetchCache('ucdp_ged');
    if (!d || !d.events) return;
    d.events.slice(0, 500).forEach(e => {
      const radius = DS.pointRadius(e.best, 20, 3, 18);
      const hex = DS.sampleRamp('fire', Math.min(1, e.best / 200));
      addEntity('ucdp_ged', {
        position: Cesium.Cartesian3.fromDegrees(e.lon, e.lat),
        point: {
          pixelSize: radius,
          color: DS.c(hex, 0.9),
          outlineColor: DS.c('#ffffff', 0.4),
          outlineWidth: 1,
        },
        name: e.dyad_name || 'UCDP event',
        description: `
          <b>${e.dyad_name}</b><br>
          ${e.country} • ${e.date_start}<br>
          Best estimate: <b>${e.best}</b> fatalities (${e.low}-${e.high})<br>
          Side A: ${e.side_a}<br>
          Side B: ${e.side_b}<br>
          Conflict: ${e.conflict_name}<br>
          <small>Source: UCDP GED (CC BY 4.0)</small>
        `,
      });
    });
  }

  // ==================================================
  // WIKIDATA BATTLES
  // ==================================================
  async function renderWikidataBattles() {
    clearLayer('wikidata_battles');
    const d = await fetchCache('wikidata_battles');
    if (!d || !d.battles) return;
    d.battles.forEach(b => {
      addEntity('wikidata_battles', {
        position: Cesium.Cartesian3.fromDegrees(b.lon, b.lat, 8000),
        point: {
          pixelSize: 8,
          color: DS.c('#8b0000', 0.9),
          outlineColor: DS.c('#ffffff', 0.7),
          outlineWidth: 1,
        },
        name: b.name,
        description: `
          <b>${b.name}</b><br>
          Date: ${(b.date||'').slice(0,10)}<br>
          <a href="${b.article_url || b.wikidata_url}" target="_blank">Wikipedia →</a>
        `,
      });
    });
  }

  // ==================================================
  // AURORA OVAL (SWPC) — polygon ring at high latitude
  // ==================================================
  async function renderAuroraOval() {
    clearLayer('swpc_aurora');
    const d = await fetchCache('swpc_aurora');
    if (!d || !d.aurora || !d.aurora.points) return;
    // Render each nonzero point as a small glowing billboard.
    // Downsample again to keep entity count reasonable.
    const points = d.aurora.points.filter(p => p[2] > 5);  // only prob >5
    const stride = Math.max(1, Math.floor(points.length / 1500));
    for (let i = 0; i < points.length; i += stride) {
      const [lon, lat, prob] = points[i];
      if (Math.abs(lat) < 50) continue;  // only polar regions
      const lonNorm = lon > 180 ? lon - 360 : lon;
      const t = prob / 100;
      const hex = DS.sampleRamp(['#004d1a','#00a63c','#5eead4','#a7f3d0'], t);
      addEntity('swpc_aurora', {
        position: Cesium.Cartesian3.fromDegrees(lonNorm, lat, 100000),
        point: {
          pixelSize: 3 + t * 6,
          color: DS.c(hex, 0.3 + t * 0.5),
          outlineWidth: 0,
        },
      });
    }
  }

  // ==================================================
  // GDELT GKG themes
  // ==================================================
  async function renderGkgThemes() {
    clearLayer('gdelt_gkg_themes');
    const d = await fetchCache('gdelt_gkg_themes');
    if (!d || !d.pulses) return;
    d.pulses.slice(0, 150).forEach(p => {
      const radius = DS.pointRadius(p.count, 20, 4, 18);
      // Hue by theme family
      let hex = '#34d399';
      if (p.theme.startsWith('KILL') || p.theme.startsWith('WOUND') || p.theme.startsWith('TERROR') || p.theme.startsWith('MILITARY')) hex = '#ef3b3b';
      else if (p.theme.includes('DISASTER') || p.theme.includes('FLOOD') || p.theme.includes('EARTHQUAKE')) hex = '#fbbf24';
      else if (p.theme.includes('ECON_')) hex = '#f4c84a';
      else if (p.theme.includes('EPIDEMIC') || p.theme.includes('MEDICAL')) hex = '#a76bff';
      else if (p.theme.includes('PROTEST') || p.theme.includes('STRIKE') || p.theme.includes('RIOT')) hex = '#ff8c2a';
      addEntity('gdelt_gkg_themes', {
        position: Cesium.Cartesian3.fromDegrees(p.lon, p.lat, 5000),
        point: {
          pixelSize: radius,
          color: window.pulseAlpha(DS.c(hex), 0.4, 1.0, 0.5),
          outlineColor: DS.c('#ffffff', 0.3),
          outlineWidth: 0.8,
        },
        name: p.theme,
        description: `<b>${p.theme}</b> in ${p.country}<br>Mentions: ${p.count}<br>${p.sample_url ? '<a href="' + p.sample_url + '" target="_blank">Sample article →</a>' : ''}`,
      });
    });
  }

  // ==================================================
  // FLIGHTS — minimal fast render
  // ==================================================
  async function renderFlights() {
    clearLayer('flights');
    const d = await fetchCache('flights');
    // OpenSky API: { time, states: [[icao24, callsign, origin_country, time_pos,
    //   time_contact, lon, lat, baro_alt_m, on_ground, velocity_m/s, heading,
    //   vert_rate, sensors, geo_alt_m, squawk, spi, position_source], ...] }
    const states = d?.states;
    if (!Array.isArray(states)) return;
    const top = states.slice(0, 1500);
    top.forEach(s => {
      const lon = s[5], lat = s[6];
      if (typeof lon !== 'number' || typeof lat !== 'number') return;
      const altM = s[7] || 0;            // baro alt in metres
      const altFt = altM * 3.28084;
      const t = Math.min(1, altFt / 40000);
      const hex = DS.sampleRamp('altitude', t);
      const callsign = (s[1] || '').trim();
      const country = s[2] || '';
      const speedKts = s[9] ? Math.round(s[9] * 1.94384) : null;
      addEntity('flights', {
        position: Cesium.Cartesian3.fromDegrees(lon, lat, Math.min(15000, altM)),
        point: {
          pixelSize: 3,
          color: DS.c(hex, 0.9),
          outlineColor: DS.c('#ffffff', 0.2),
          outlineWidth: 0.5,
        },
        name: callsign || 'Flight',
        description: `Callsign: ${callsign || '—'}<br>Origin: ${country}<br>Alt: ${altFt.toLocaleString(undefined,{maximumFractionDigits:0})} ft<br>Speed: ${speedKts ?? '?'} kts`,
      });
    });
  }

  // ==================================================
  // SHIPS
  // ==================================================
  async function renderShips() {
    clearLayer('ships');
    const d = await fetchCache('ships');
    if (!d || !Array.isArray(d)) return;
    d.slice(0, 500).forEach(s => {
      if (!s.lat || !s.lon) return;
      addEntity('ships', {
        position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat),
        point: {
          pixelSize: 3,
          color: DS.c('#56B4E9', 0.9),
          outlineColor: DS.c('#ffffff', 0.2),
          outlineWidth: 0.5,
        },
        name: s.name || 'Ship',
      });
    });
  }

  // ==================================================
  // ISS
  // ==================================================
  async function renderISS() {
    clearLayer('iss');
    const d = await fetchCache('iss');
    if (!d || !d.iss) return;
    const i = d.iss;
    addEntity('iss', {
      position: Cesium.Cartesian3.fromDegrees(i.longitude, i.latitude, (i.altitude || 400) * 1000),
      point: {
        pixelSize: 14,
        color: DS.c('#ffffff', 1.0),
        outlineColor: DS.c('#5eead4', 0.9),
        outlineWidth: 3,
      },
      label: {
        text: 'ISS',
        font: '700 11px Inter',
        fillColor: DS.c('#ffffff'),
        outlineColor: DS.c('#000000', 0.9),
        outlineWidth: 2,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new Cesium.Cartesian2(0, -18),
      },
      name: 'International Space Station',
      description: `Alt: ${(i.altitude||0).toFixed(0)} km<br>Vel: ${(i.velocity||0).toFixed(0)} km/h<br>Crew: ${(d.crew || []).map(c => c.name).join(', ')}`,
    });
  }

  // ==================================================
  // SATELLITES
  // ==================================================
  async function renderSatellites() {
    clearLayer('satellites');
    // DISABLED: the previous implementation plotted Math.random() positions
    // — fake data presented as live satellites, which is the one thing a
    // "news source of actual data" can never do. Re-enable when real SGP4
    // propagation (satellite.js) or the Space-Track positions land.
    console.warn('[satellites] renderer disabled — no real position data yet (TLEs need SGP4)');
  }

  // ==================================================
  // PULSE MODE — apocalypse radar choropleth (country bubbles sized by composite)
  // ==================================================
  async function renderPulse() {
    clearLayer('pulse_mode');
    const d = await fetchCache('pulse_mode');
    if (!d || !d.countries) return;
    const entries = Object.values(d.countries);
    entries.forEach(c => {
      if (c.lat == null || c.lon == null) return;
      const s = c.composite || 0;
      // Color ramp: green→yellow→orange→red
      let hex = '#22c55e';
      if (s >= 70) hex = '#ef3b3b';
      else if (s >= 50) hex = '#fb923c';
      else if (s >= 30) hex = '#fbbf24';
      else if (s >= 15) hex = '#84cc16';
      const radius = 8 + (s / 100) * 22;
      addEntity('pulse_mode', {
        position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, 5000),
        point: {
          pixelSize: radius,
          color: DS.c(hex, 0.55 + (s/100) * 0.4),
          outlineColor: DS.c('#ffffff', 0.6),
          outlineWidth: 1.5,
        },
        name: c.name || c.iso3,
        description: `
          <b>${c.name || c.iso3}</b> · <span style="color:${hex}">Score ${s}/100</span><br>
          Trend: <b>${c.trend || '—'}</b><br>
          <hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:8px 0">
          💧 Water stress: ${c.details?.water_stress_label || '—'} (${c.details?.water_stress_score ?? '—'})<br>
          🌾 Food IPC: Phase ${c.details?.food_ipc_phase ?? '—'} (${c.details?.food_ipc_description || '—'})<br>
          ⚔ Conflict 30d: ${c.details?.conflict_fatalities_30d ?? 0} fatalities<br>
          ⚡ Grid carbon: ${c.details?.grid_carbon_gco2_kwh ?? '—'} gCO2/kWh<br>
          <br>
          <small>Composite of 5 per-country signals. Source: WorldTwin internal aggregation.</small>
        `,
      });
    });
  }

  // ==================================================
  // GDACS — unified hazard alerts
  // ==================================================
  async function renderGdacs() {
    clearLayer('gdacs_events');
    const d = await fetchCache('gdacs_events');
    if (!d || !d.events) return;
    const typeIcon = { EQ: 'earthquake', TC: 'cyclone', FL: 'flood', VO: 'volcano', WF: 'fire', DR: 'drought' };
    const severityHex = { 1: '#22c55e', 3: '#fb923c', 5: '#ef4444' };
    d.events.slice(0, 300).forEach(e => {
      const hex = severityHex[e.severity] || '#fbbf24';
      const radius = 4 + e.severity * 2;
      addEntity('gdacs_events', {
        position: Cesium.Cartesian3.fromDegrees(e.lon, e.lat),
        point: {
          pixelSize: radius,
          color: window.pulseAlpha(DS.c(hex), 0.4, 1.0, 0.6),
          outlineColor: DS.c('#ffffff', 0.6),
          outlineWidth: 1,
        },
        name: e.name || e.type_name,
        description: `
          <b>${e.type_name}</b> · <span style="color:${hex}">${e.alert_level}</span><br>
          ${e.name}<br>
          ${e.country ? 'Country: ' + e.country + '<br>' : ''}
          ${e.from_date ? 'Started: ' + e.from_date + '<br>' : ''}
          ${e.description ? '<p style="font-size:11px;opacity:0.85">' + e.description + '</p>' : ''}
          ${e.url ? '<a href="' + e.url + '" target="_blank">GDACS report →</a>' : ''}
          <br><small>Source: GDACS (JRC/ECHO) CC-BY</small>
        `,
      });
    });
  }

  // ==================================================
  // NHC Cyclones
  // ==================================================
  async function renderNhc() {
    clearLayer('nhc_cyclones');
    const d = await fetchCache('nhc_cyclones');
    if (!d || !d.storms) return;
    const catColor = { TD:'#4cc2ff', TS:'#fde047', Cat1:'#fb923c', Cat2:'#f97316', Cat3:'#ef4444', Cat4:'#dc2626', Cat5:'#ffffff' };
    d.storms.forEach(s => {
      const hex = catColor[s.category] || '#fde047';
      addEntity('nhc_cyclones', {
        position: Cesium.Cartesian3.fromDegrees(s.lon, s.lat),
        point: {
          pixelSize: 18,
          color: window.pulseAlpha(DS.c(hex), 0.5, 1.0, 0.8),
          outlineColor: DS.c('#ffffff', 0.9),
          outlineWidth: 2,
        },
        label: {
          text: s.name + ' (' + s.category + ')',
          font: '700 11px Inter',
          fillColor: DS.c('#ffffff'),
          outlineColor: DS.c('#000', 0.9),
          outlineWidth: 2,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new Cesium.Cartesian2(0, -24),
          showBackground: true,
          backgroundColor: DS.c('#000', 0.7),
          backgroundPadding: new Cesium.Cartesian2(6, 4),
        },
        name: s.name,
        description: `
          <b>${s.name}</b><br>
          Category: <span style="color:${hex}">${s.category}</span><br>
          Winds: ${s.wind_kts} kts<br>
          Pressure: ${s.pressure_mb || '—'} mb<br>
          Movement: ${s.movement || '—'}<br>
          <small>Source: NOAA NHC · Public Domain</small>
        `,
      });
    });
  }

  // ==================================================
  // ClimateTRACE — facility emissions
  // ==================================================
  async function renderClimateTrace(sectorFilter=null) {
    clearLayer('climatetrace_assets');
    const d = await fetchCache('climatetrace_assets');
    if (!d || !d.assets) return;
    const sectorHue = {
      'oil-and-gas-production': '#E69F00',
      'oil-and-gas-refining':   '#D55E00',
      'coal-mining':            '#2a2a2a',
      'electricity-generation': '#f4c84a',
      'iron-and-steel':         '#9aa5b1',
      'cement':                 '#b6a07a',
      'aluminum':               '#CC79A7',
      'pulp-and-paper':         '#009E73',
      'chemicals':              '#a76bff',
      'petrochemicals':         '#CC79A7',
      'fluorinated-gases':      '#5eead4',
      'solid-waste-disposal':   '#6b7790',
    };
    let assets = d.assets;
    if (sectorFilter) assets = (d.by_sector?.[sectorFilter] || []).slice(0, 500);
    const median = assets.length ? assets[Math.floor(assets.length/2)].emissions_tco2e || 1e6 : 1e6;
    assets.forEach(a => {
      const hex = sectorHue[a.sector] || '#6b7790';
      const radius = DS.pointRadius(a.emissions_tco2e, median, 3, 16);
      addEntity('climatetrace_assets', {
        position: Cesium.Cartesian3.fromDegrees(a.lon, a.lat),
        point: {
          pixelSize: radius,
          color: DS.c(hex, 0.9),
          outlineColor: DS.c('#ffffff', 0.4),
          outlineWidth: 0.8,
        },
        name: a.name,
        description: `
          <b>${a.name}</b><br>
          Country: ${a.country}<br>
          Sector: ${a.sector}<br>
          Emissions: <b>${DS.fmt(a.emissions_tco2e)} tCO2e/yr</b><br>
          ${a.owners && a.owners.length ? 'Owners: ' + a.owners.join(', ') + '<br>' : ''}
          ${a.thumbnail ? '<img src="' + a.thumbnail + '" style="max-width:100%;margin-top:8px;border-radius:4px">' : ''}
          <br><small>Source: ClimateTRACE · CC-BY 4.0</small>
        `,
      });
    });
  }

  // ==================================================
  // WIND SAMPLE (Open-Meteo 18x10 grid)
  // ==================================================
  async function renderWind() {
    clearLayer('wind_sample');
    const d = await fetchCache('wind_sample');
    if (!d || !d.points) return;
    d.points.forEach(p => {
      const speed = p.speed_ms || 0;
      const dir = (p.dir_deg || 0) * Math.PI / 180;
      // Colour by speed (blue slow → red fast, max ~30 m/s)
      const t = Math.min(1, speed / 30);
      const hex = DS.sampleRamp('heat', t);
      // Wind arrow rendered as a polyline from the grid point in the direction
      // (trailing 200km arrow)
      const r = 2.0;  // arrow length in degrees
      const endLat = p.lat + r * Math.cos(dir);
      const endLon = p.lon + r * Math.sin(dir);
      const positions = window.buildGreatCircle(p.lat, p.lon, endLat, endLon, 6);
      addEntity('wind_sample', {
        polyline: {
          positions: positions,
          width: 1.4 + t * 2.5,
          material: DS.c(hex, 0.65 + t * 0.3),
          arcType: Cesium.ArcType.NONE,
        },
      });
      // Head dot
      addEntity('wind_sample', {
        position: Cesium.Cartesian3.fromDegrees(endLon, endLat, 10000),
        point: {
          pixelSize: 2.5 + t * 2,
          color: DS.c(hex, 0.9),
          outlineWidth: 0,
        },
      });
    });
  }
  // ==================================================
  // POPULATION / country centroids (for country-click interaction)
  // ==================================================
  async function loadPopulation() {
    const d = await fetchCache('population');
    return d;
  }

  // Dispatch table used by modes.js
  const LAYERS = {
    wind_sample: { render: renderWind, clear: () => clearLayer('wind_sample') },
    pulse_mode: { render: renderPulse, clear: () => clearLayer('pulse_mode') },
    gdacs_events: { render: renderGdacs, clear: () => clearLayer('gdacs_events') },
    nhc_cyclones: { render: renderNhc, clear: () => clearLayer('nhc_cyclones') },
    climatetrace_assets: { render: renderClimateTrace, clear: () => clearLayer('climatetrace_assets') },
    quakes: { render: renderQuakes, clear: () => clearLayer('quakes') },
    fires: { render: renderFires, clear: () => clearLayer('fires') },
    cables: { render: renderCables, clear: () => clearLayer('cables') },
    portwatch_chokepoints: { render: renderPortwatchChokepoints, clear: () => clearLayer('portwatch_chokepoints') },
    trade_annual: { render: renderTradeAnnual, clear: () => clearLayer('trade_annual') },
    wri_power_plants: { render: renderWriPowerPlants, clear: () => clearLayer('wri_power_plants') },
    ucdp_ged: { render: renderUcdp, clear: () => clearLayer('ucdp_ged') },
    wikidata_battles: { render: renderWikidataBattles, clear: () => clearLayer('wikidata_battles') },
    swpc_aurora: { render: renderAuroraOval, clear: () => clearLayer('swpc_aurora') },
    gdelt_gkg_themes: { render: renderGkgThemes, clear: () => clearLayer('gdelt_gkg_themes') },
    flights: { render: renderFlights, clear: () => clearLayer('flights') },
    ships: { render: renderShips, clear: () => clearLayer('ships') },
    iss: { render: renderISS, clear: () => clearLayer('iss') },
    satellites: { render: renderSatellites, clear: () => clearLayer('satellites') },
  };
  window.LAYERS = LAYERS;
  window.fetchCache = fetchCache;       // used by mapmode.js, layers2.js, energy-viz.js, etc.
  // window.buildGreatCircle is exported earlier (line 263)
})();
