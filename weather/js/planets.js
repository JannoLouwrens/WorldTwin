// Planet selector: swap the Cesium viewer between Earth and other bodies.
// Uses the destroy-and-rebuild pattern since Cesium's Ellipsoid is a WGS84
// singleton and cannot be hot-swapped. Mission POIs per body.
(function(){

  // ============================================================
  // BODY REGISTRY
  // ============================================================
  // imagery "type":
  //   "trek" — NASA Trek WMTS, uses url + default028mm
  //   "gibs" — NASA GIBS, uses url template
  //   "sss"  — Solar System Scope single-tile equirectangular texture
  //   "ion"  — Cesium Ion asset ID (Earth default)
  const BODIES = {
    earth: {
      id: 'earth',
      name: 'Earth',
      radius_km: 6371,
      ellipsoid: [6378137, 6378137, 6356752],
      color: '#4cc2ff',
      imagery: { type: 'ion', assetId: 2 },
      atmosphere: { show: true, hue: -0.08, saturation: 0.18, brightness: 0.10 },
      missions: [],
      description: 'Home.',
      order: 3,
    },
    moon: {
      id: 'moon',
      name: 'Moon',
      radius_km: 1737,
      ellipsoid: [1737400, 1737400, 1737400],
      color: '#c9c9c9',
      imagery: {
        type: 'trek',
        url: 'https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
      },
      atmosphere: { show: false },
      missions: [
        { name: 'Apollo 11', lat: 0.674, lon: 23.473, year: 1969, type: 'crewed', country: 'USA' },
        { name: 'Apollo 12', lat: -3.01239, lon: -23.42157, year: 1969, type: 'crewed', country: 'USA' },
        { name: 'Apollo 14', lat: -3.64544, lon: -17.47136, year: 1971, type: 'crewed', country: 'USA' },
        { name: 'Apollo 15', lat: 26.13222, lon: 3.63386, year: 1971, type: 'crewed', country: 'USA' },
        { name: 'Apollo 16', lat: -8.9734, lon: 15.5011, year: 1972, type: 'crewed', country: 'USA' },
        { name: 'Apollo 17', lat: 20.1908, lon: 30.7717, year: 1972, type: 'crewed', country: 'USA' },
        { name: 'Luna 16', lat: -0.68, lon: 56.3, year: 1970, type: 'robotic', country: 'USSR' },
        { name: 'Luna 17 / Lunokhod 1', lat: 38.28, lon: -35.00, year: 1970, type: 'rover', country: 'USSR' },
        { name: 'Luna 21 / Lunokhod 2', lat: 25.85, lon: 30.45, year: 1973, type: 'rover', country: 'USSR' },
        { name: 'Chang\'e 3', lat: 44.12, lon: -19.51, year: 2013, type: 'rover', country: 'China' },
        { name: 'Chang\'e 4', lat: -45.46, lon: 177.60, year: 2019, type: 'rover', country: 'China' },
        { name: 'Chang\'e 5', lat: 43.06, lon: -51.92, year: 2020, type: 'robotic', country: 'China' },
        { name: 'Chang\'e 6', lat: -41.6, lon: -153.98, year: 2024, type: 'robotic', country: 'China' },
        { name: 'Chandrayaan-3 / Vikram', lat: -69.37, lon: 32.35, year: 2023, type: 'lander', country: 'India' },
      ],
      description: '3,475 km wide. One-sixth of Earth\'s gravity. Has hosted 14+ successful landings since 1966.',
      order: 4,
    },
    mars: {
      id: 'mars',
      name: 'Mars',
      radius_km: 3390,
      ellipsoid: [3396190, 3396190, 3376200],
      color: '#c1440e',
      imagery: {
        type: 'trek',
        url: 'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
      },
      atmosphere: { show: true, hue: 0.45, saturation: 0.2, brightness: -0.3 },
      missions: [
        { name: 'Viking 1', lat: 22.48, lon: -49.97, year: 1976, type: 'lander', country: 'USA' },
        { name: 'Viking 2', lat: 47.97, lon: 134.14, year: 1976, type: 'lander', country: 'USA' },
        { name: 'Mars Pathfinder / Sojourner', lat: 19.33, lon: -33.55, year: 1997, type: 'rover', country: 'USA' },
        { name: 'Spirit (MER-A)', lat: -14.5684, lon: 175.4726, year: 2004, type: 'rover', country: 'USA' },
        { name: 'Opportunity (MER-B)', lat: -1.9462, lon: -5.5270, year: 2004, type: 'rover', country: 'USA' },
        { name: 'Phoenix', lat: 68.22, lon: -125.7, year: 2008, type: 'lander', country: 'USA' },
        { name: 'Curiosity', lat: -4.589, lon: 137.44, year: 2012, type: 'rover', country: 'USA' },
        { name: 'InSight', lat: 4.5024, lon: 135.6234, year: 2018, type: 'lander', country: 'USA' },
        { name: 'Perseverance + Ingenuity', lat: 18.4447, lon: 77.4508, year: 2021, type: 'rover', country: 'USA' },
        { name: 'Zhurong (China)', lat: 25.1, lon: 109.9, year: 2021, type: 'rover', country: 'China' },
      ],
      description: '6,779 km wide. Red from iron oxide. Home to Olympus Mons, the tallest volcano in the solar system.',
      order: 5,
    },
    mercury: {
      id: 'mercury',
      name: 'Mercury',
      radius_km: 2439,
      ellipsoid: [2440530, 2440530, 2438260],
      color: '#8a7a6b',
      imagery: {
        type: 'trek',
        url: 'https://trek.nasa.gov/tiles/Mercury/EQ/Mercury_MESSENGER_MDIS_Basemap_LOI_Mosaic_Global_166m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
      },
      atmosphere: { show: false },
      missions: [],
      description: '4,880 km wide. Closest planet to the Sun. Airless. Surface temperatures swing 600°C between day and night.',
      order: 2,
    },
    venus: {
      id: 'venus',
      name: 'Venus',
      radius_km: 6052,
      ellipsoid: [6051800, 6051800, 6051800],
      color: '#e8c37a',
      imagery: {
        type: 'sss',
        url: 'https://www.solarsystemscope.com/textures/download/2k_venus_atmosphere.jpg',
      },
      atmosphere: { show: true, hue: 0.15, saturation: 0.3, brightness: 0.2 },
      missions: [
        { name: 'Venera 7', lat: -5, lon: 351, year: 1970, type: 'lander', country: 'USSR' },
        { name: 'Venera 9', lat: 31.01, lon: 291.64, year: 1975, type: 'lander', country: 'USSR' },
        { name: 'Venera 13', lat: -7.55, lon: 303.69, year: 1982, type: 'lander', country: 'USSR' },
      ],
      description: '12,104 km wide. Hottest planet. Crushing CO2 atmosphere at 90 bar. Cloud tops race the surface.',
      order: 1,
    },
    jupiter: {
      id: 'jupiter',
      name: 'Jupiter',
      radius_km: 69911,
      ellipsoid: [71492000, 71492000, 66854000],
      color: '#d4a574',
      imagery: {
        type: 'sss',
        url: 'https://www.solarsystemscope.com/textures/download/2k_jupiter.jpg',
      },
      atmosphere: { show: true, hue: 0.08, saturation: 0.1, brightness: 0.15 },
      missions: [
        { name: 'Galileo probe entry', lat: 6.5, lon: 4.4, year: 1995, type: 'probe', country: 'USA' },
      ],
      description: '139,820 km wide. Largest planet. The Great Red Spot is a 350-year-old storm bigger than Earth.',
      order: 6,
    },
    saturn: {
      id: 'saturn',
      name: 'Saturn',
      radius_km: 58232,
      ellipsoid: [60268000, 60268000, 54364000],
      color: '#e3d9a0',
      imagery: {
        type: 'sss',
        url: 'https://www.solarsystemscope.com/textures/download/2k_saturn.jpg',
      },
      atmosphere: { show: true, hue: 0.05, saturation: 0.1, brightness: 0.1 },
      missions: [
        { name: 'Cassini Grand Finale', lat: 9.4, lon: 53, year: 2017, type: 'orbiter-impact', country: 'USA/ESA' },
      ],
      description: '116,460 km wide. Famous rings stretch 280,000 km wide but are only ~10 m thick.',
      order: 7,
    },
    uranus: {
      id: 'uranus',
      name: 'Uranus',
      radius_km: 25362,
      ellipsoid: [25559000, 25559000, 25559000],
      color: '#a6d8e0',
      imagery: {
        type: 'sss',
        url: 'https://www.solarsystemscope.com/textures/download/2k_uranus.jpg',
      },
      atmosphere: { show: true, hue: 0.5, saturation: 0.2, brightness: 0.1 },
      missions: [],
      description: '50,724 km wide. Rotates on its side. Only visited once, by Voyager 2 in 1986.',
      order: 8,
    },
    neptune: {
      id: 'neptune',
      name: 'Neptune',
      radius_km: 24622,
      ellipsoid: [24764000, 24764000, 24764000],
      color: '#4866d6',
      imagery: {
        type: 'sss',
        url: 'https://www.solarsystemscope.com/textures/download/2k_neptune.jpg',
      },
      atmosphere: { show: true, hue: 0.6, saturation: 0.2, brightness: 0.1 },
      missions: [],
      description: '49,244 km wide. Fastest winds in the solar system (2,100 km/h). Only visited by Voyager 2.',
      order: 9,
    },
    pluto: {
      id: 'pluto',
      name: 'Pluto',
      radius_km: 1188,
      ellipsoid: [1188300, 1188300, 1188300],
      color: '#c9a585',
      imagery: {
        type: 'trek',
        url: 'https://trek.nasa.gov/tiles/Pluto/EQ/Pluto_NewHorizons_Global_Mosaic_300m_Jul2017/1.0.0/default/default028mm/{z}/{y}/{x}.jpg',
      },
      atmosphere: { show: false },
      missions: [
        { name: 'New Horizons closest approach', lat: 0, lon: 180, year: 2015, type: 'flyby', country: 'USA' },
      ],
      description: '2,377 km wide. Dwarf planet. Heart-shaped Sputnik Planitia is nitrogen ice.',
      order: 10,
    },
  };
  window.BODIES = BODIES;

  // ============================================================
  // SWITCH TO BODY
  // ============================================================
  // Phase 2 change: currentBodyId starts as null so first switchToBody('earth')
  // actually builds the viewer (previously returned early → half-baked Earth
  // until user switched to Moon and back).
  let currentBodyId = null;

  async function switchToBody(bodyId) {
    const body = BODIES[bodyId];
    if (!body) return;
    if (bodyId === currentBodyId) return;

    console.log('[planets] switching to', bodyId);

    // Fade to black (overlay may not exist on very first boot)
    const overlay = document.getElementById('planetFade');
    if (overlay) {
      overlay.style.opacity = '1';
      await wait(500);
    }

    // Close all popups and clear mapmode state before switching bodies
    if (window.dismissAllPopups) window.dismissAllPopups();
    if (window.Mapmode && window.Mapmode.clearPolygons) window.Mapmode.clearPolygons();
    window.MAPMODE_COLORS = {};
    window.MAPMODE_HIGHLIGHT = {};
    window.MAPMODE_WAR_HOTSPOTS = {};

    // Earth uses buildEarthViewer() (single source of truth for the
    // full cinematic stack). Other bodies use the generic ellipsoid rebuild.
    if (bodyId === 'earth') {
      if (typeof window.buildEarthViewer === 'function') {
        await window.buildEarthViewer();
      } else {
        console.warn('[planets] buildEarthViewer() missing — cesium-setup.js not loaded?');
      }
      currentBodyId = 'earth';
      window.currentBodyId = 'earth';
      updateBodyCard(body);
      document.querySelectorAll('.planet-rail-item').forEach(el => {
        el.classList.toggle('active', el.dataset.body === 'earth');
      });
      if (overlay) {
        await wait(200);
        overlay.style.opacity = '0';
      }
      // Re-activate the current mode (or 'world' on first boot)
      const mode = (window.currentModeId && window.currentModeId()) || 'world';
      if (window.activateMode) {
        // Let the viewer complete its first frame before adding entities
        setTimeout(() => window.activateMode(mode), 150);
      }
      // Do the initial fly-in (only on very first Earth boot)
      if (!window._didInitialFlyIn && window.viewer) {
        window._didInitialFlyIn = true;
        window.viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(20, 10, 18000000),
          duration: 2.0,
          easingFunction: Cesium.EasingFunction.QUINTIC_IN_OUT,
        });
      }
      return;
    }

    // Non-Earth: destroy any existing viewer and rebuild with body-specific ellipsoid
    if (window.viewer) {
      try {
        window.viewer.entities.removeAll();
        window.viewer.scene.primitives.removeAll();
        window.viewer.destroy();
      } catch (e) { console.warn('[planets] destroy', e); }
    }
    document.getElementById('globe').innerHTML = '';

    // Build ellipsoid
    const [a, b, c] = body.ellipsoid;
    const ellipsoid = new Cesium.Ellipsoid(a, b, c);

    // Build viewer with body-specific ellipsoid
    const viewer = new Cesium.Viewer('globe', {
      animation: false,
      timeline: false,
      fullscreenButton: false,
      vrButton: false,
      geocoder: false,
      homeButton: false,
      infoBox: true,
      selectionIndicator: false,
      navigationHelpButton: false,
      sceneModePicker: false,
      baseLayerPicker: false,
      skyAtmosphere: body.atmosphere && body.atmosphere.show ? new Cesium.SkyAtmosphere(ellipsoid) : false,
      globe: new Cesium.Globe(ellipsoid),
    });
    window.viewer = viewer;
    window.scene = viewer.scene;

    // Remove default imagery
    viewer.imageryLayers.removeAll();

    // Apply body atmosphere tuning
    if (body.atmosphere && body.atmosphere.show && viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.hueShift = body.atmosphere.hue || 0;
      viewer.scene.skyAtmosphere.saturationShift = body.atmosphere.saturation || 0;
      viewer.scene.skyAtmosphere.brightnessShift = body.atmosphere.brightness || 0;
      viewer.scene.globe.showGroundAtmosphere = true;
    } else {
      viewer.scene.globe.showGroundAtmosphere = false;
    }

    // Load imagery
    await loadBodyImagery(viewer, body, ellipsoid);

    // Lighting
    viewer.scene.globe.enableLighting = true;
    viewer.scene.moon.show = (bodyId === 'earth');
    viewer.scene.sun.show = true;

    // Camera: far enough to see the whole body
    const viewDist = Math.max(a, b, c) * 3.5;
    viewer.camera.setView({
      destination: new Cesium.Cartesian3(viewDist, 0, 0),
      orientation: {
        direction: new Cesium.Cartesian3(-1, 0, 0),
        up: new Cesium.Cartesian3(0, 0, 1),
      },
    });

    // Add mission POIs
    if (body.missions && body.missions.length) {
      body.missions.forEach(m => {
        viewer.entities.add({
          position: Cesium.Cartesian3.fromDegrees(m.lon, m.lat, 0, ellipsoid),
          point: {
            pixelSize: 10,
            color: Cesium.Color.fromCssColorString(missionColor(m.type)),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1.5,
          },
          label: {
            text: m.name,
            font: '600 10px Inter',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            pixelOffset: new Cesium.Cartesian2(0, -14),
            showBackground: true,
            backgroundColor: Cesium.Color.fromCssColorString('#000').withAlpha(0.6),
            backgroundPadding: new Cesium.Cartesian2(5, 3),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, viewDist * 2),
          },
          name: m.name,
          description: `
            <b>${m.name}</b><br>
            ${body.name} ${m.year || ''}<br>
            Type: ${m.type}<br>
            Country/Agency: ${m.country}<br>
            Latitude: ${m.lat.toFixed(4)}°<br>
            Longitude: ${m.lon.toFixed(4)}°
          `,
        });
      });
    }

    currentBodyId = bodyId;
    window.currentBodyId = bodyId;

    // Update body card
    updateBodyCard(body);

    // Update rail highlight
    document.querySelectorAll('.planet-rail-item').forEach(el => {
      el.classList.toggle('active', el.dataset.body === bodyId);
    });

    // Fade back in
    if (overlay) {
      await wait(200);
      overlay.style.opacity = '0';
    }
    // Note: Earth case is handled at the top of this function and returned early,
    // so we never reach here for Earth.
  }

  function missionColor(type) {
    return {
      crewed: '#ffd700',
      rover: '#ff8c2a',
      lander: '#4cc2ff',
      robotic: '#a76bff',
      orbiter: '#34d399',
      flyby: '#c9c9c9',
      probe: '#ef3b3b',
      'orbiter-impact': '#34d399',
    }[type] || '#ffffff';
  }

  function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function loadBodyImagery(viewer, body, ellipsoid) {
    const imagery = body.imagery;
    if (!imagery) return;

    if (imagery.type === 'ion') {
      try {
        const provider = await Cesium.IonImageryProvider.fromAssetId(imagery.assetId);
        viewer.imageryLayers.addImageryProvider(provider);
      } catch (e) { console.warn('[planets] ion imagery failed', e); }
      return;
    }

    if (imagery.type === 'trek') {
      const provider = new Cesium.UrlTemplateImageryProvider({
        url: imagery.url,
        tilingScheme: new Cesium.GeographicTilingScheme({ ellipsoid }),
        maximumLevel: 7,
        credit: 'NASA Trek',
      });
      viewer.imageryLayers.addImageryProvider(provider);
      return;
    }

    if (imagery.type === 'sss') {
      try {
        const provider = new Cesium.SingleTileImageryProvider({
          url: imagery.url,
          tilingScheme: new Cesium.GeographicTilingScheme({ ellipsoid }),
          credit: 'Solar System Scope (CC-BY 4.0)',
        });
        viewer.imageryLayers.addImageryProvider(provider);
      } catch (e) { console.warn('[planets] sss imagery failed', e); }
      return;
    }
  }

  // ============================================================
  // PLANET RAIL UI (left edge strip)
  // ============================================================
  function buildRail() {
    const host = document.getElementById('planetRail');
    if (!host) return;
    const sorted = Object.values(BODIES).sort((a, b) => a.order - b.order);
    host.innerHTML = sorted.map(b => {
      const logR = Math.log10(b.radius_km);
      const size = Math.max(18, Math.min(44, (logR - 3) * 14 + 18));
      return `
        <button class="planet-rail-item ${b.id === 'earth' ? 'active' : ''}" data-body="${b.id}" title="${b.name}">
          <span class="planet-dot" style="width:${size}px;height:${size}px;background:radial-gradient(circle at 35% 30%, ${b.color}, #000)"></span>
          <span class="planet-label">${b.name}</span>
        </button>
      `;
    }).join('');
    host.querySelectorAll('.planet-rail-item').forEach(el => {
      el.addEventListener('click', () => switchToBody(el.dataset.body));
    });
  }

  // ============================================================
  // BODY CARD (top-right)
  // ============================================================
  function updateBodyCard(body) {
    const card = document.getElementById('bodyCard');
    if (!card) return;
    card.style.display = body.id === 'earth' ? 'none' : 'block';
    if (body.id === 'earth') return;
    card.innerHTML = `
      <div class="bc-head">
        <span class="bc-dot" style="background:${body.color}"></span>
        <span class="bc-name">${body.name}</span>
      </div>
      <div class="bc-desc">${body.description}</div>
      <div class="bc-stats">
        <div class="bc-stat"><div class="label">Radius</div><div class="val">${body.radius_km.toLocaleString()} km</div></div>
        <div class="bc-stat"><div class="label">Missions</div><div class="val">${body.missions.length}</div></div>
      </div>
      <button class="bc-back" id="bcBack">← Back to Earth</button>
    `;
    card.querySelector('#bcBack')?.addEventListener('click', () => switchToBody('earth'));
  }

  // ============================================================
  // Export
  // ============================================================
  window.Planets = { BODIES, switchToBody, buildRail, currentBody: () => currentBodyId };

  // Auto-build rail when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildRail);
  } else {
    setTimeout(buildRail, 100);
  }
})();
