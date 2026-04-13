// App bootstrap — Phase 2: single boot path.
//
// Order of operations on page load:
//   1. DOMContentLoaded fires
//   2. Inject SVG icons, wire mode buttons and help key
//   3. Fetch /weather/config.json (single source of truth) into window.CONFIG
//   4. Preloader.preload() — parallel fetch every cache file in CONFIG
//   5. Planets.switchToBody('earth') — builds the viewer through the canonical path
//      (planets.js in turn calls window.buildEarthViewer, which is defined in
//      cesium-setup.js). When the viewer exists, planets.js schedules
//      activateMode('world') for us.
//   6. Attach click/hover handlers (now that the viewer exists).
//   7. Hide boot splash.
(function(){

  async function boot() {
    // Inject SVG icons
    if (window.injectIcons) window.injectIcons();

    // Wire mode buttons
    document.querySelectorAll('.mode').forEach(btn => {
      btn.addEventListener('click', () => {
        window.activateMode(btn.dataset.mode);
      });
    });

    // Help key + reset camera
    document.addEventListener('keydown', (e) => {
      if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
        if (window.showLegendCard) {
          window.showLegendCard('WorldTwin Help', `
            <div class="lg-section">
              <div class="lg-section-label">Keyboard</div>
              <div class="lg-row"><span class="swatch"></span>? — This help</div>
              <div class="lg-row"><span class="swatch"></span>R — Reset camera</div>
              <div class="lg-row"><span class="swatch"></span>L — Layer browser</div>
              <div class="lg-row"><span class="swatch"></span>D — Diagnostics</div>
              <div class="lg-row"><span class="swatch"></span>1-9 0 q w e r t — Mapmode shortcuts</div>
            </div>
            <div class="lg-section">
              <div class="lg-section-label">Modes</div>
              <div class="lg-row">Click any mode above. Each mode activates its own data layers, legend and filters.</div>
            </div>
            <div class="lg-section">
              <div class="lg-section-label">Country facts</div>
              <div class="lg-row">Click any marker to see details. In Resources mode, click a country to see its top exports, imports, partners, and power mix.</div>
            </div>
            <div class="attribution">
              Data: UN Comtrade · IMF PortWatch · NASA FIRMS · USGS · NOAA SWPC · GDELT · UCDP · Wikidata · WRI GPPD · CelesTrak · Smithsonian GVP · Open-Meteo · World Bank
            </div>
          `);
        }
      }
      if ((e.key === 'r' || e.key === 'R') && window.viewer) {
        window.viewer.camera.flyTo({
          destination: Cesium.Cartesian3.fromDegrees(20, 10, 20000000),
          duration: 2.5,
          easingFunction: Cesium.EasingFunction.QUINTIC_IN_OUT,
        });
      }
    });
    const helpBtn = document.getElementById('helpBtn');
    if (helpBtn) {
      helpBtn.addEventListener('click', () => {
        window.dispatchEvent(new KeyboardEvent('keydown', { key: '?' }));
      });
    }

    // Step 1: load config.json — single source of truth
    try {
      const cr = await fetch('/weather/config.json');
      if (cr.ok) {
        window.CONFIG = await cr.json();
        console.log(`[boot] config.json loaded · ${window.CONFIG.layers.length} layers in catalog`);
      } else {
        console.warn('[boot] config.json missing — falling back to hardcoded preloader list');
        window.CONFIG = null;
      }
    } catch (e) {
      console.warn('[boot] config.json fetch failed:', e);
      window.CONFIG = null;
    }

    // Step 2: preloader
    const pt = document.getElementById('bootProgressText');
    const pf = document.getElementById('bootProgressFill');

    let preloadIds = null;
    if (window.CONFIG && window.CONFIG.layers) {
      // Skip huge or non-renderable layers — they're fetched on demand
      const SKIP = new Set(['geoboundaries_adm1', 'spacetrack_gp', 'nasa_epic_earth']);
      preloadIds = window.CONFIG.layers
        .filter(l => !SKIP.has(l.id) && l.status !== 'disabled')
        .map(l => l.id);
    }

    if (window.Preloader) {
      const res = await window.Preloader.preload(preloadIds, (done, total, id) => {
        if (pt) pt.textContent = `Loading ${done}/${total} layers…`;
        if (pf) pf.style.width = ((done/total)*100) + '%';
      });
      if (pt) pt.textContent = `${res.ok} layers ready · entering`;
    }

    // Step 3: build the Earth viewer through the canonical planets.js path
    await window.Planets.switchToBody('earth');

    // Step 4: attach click + hover handlers (viewer now exists)
    attachGlobeHandlers();

    // Step 5: hide boot splash
    setTimeout(() => {
      const bootEl = document.getElementById('boot');
      if (bootEl) bootEl.classList.add('hidden');
    }, 400);
  }

  function attachGlobeHandlers() {
    if (!window.viewer) return;
    const canvas = window.viewer.scene.canvas;

    // Hover handler — mapmode alliance highlight (EU4-style)
    const hoverHandler = new Cesium.ScreenSpaceEventHandler(canvas);
    let _lastHoveredIso3 = null;
    hoverHandler.setInputAction(function(movement) {
      const picked = window.viewer.scene.pick(movement.endPosition);
      if (picked && picked.id && picked.id.properties && picked.id.properties.mapmode_entity) {
        const iso3 = picked.id.properties.iso3?.getValue();
        if (iso3 && iso3 !== _lastHoveredIso3) {
          _lastHoveredIso3 = iso3;
          if (window.Mapmode) window.Mapmode.hoverCountry(iso3);
        }
      } else if (_lastHoveredIso3) {
        _lastHoveredIso3 = null;
        if (window.Mapmode) window.Mapmode.clearHover();
      }
    }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    // Close ALL popups — ensures no overlapping panels
    function dismissAllPopups() {
      // Close Cesium infoBox
      if (window.viewer && window.viewer.selectedEntity) window.viewer.selectedEntity = undefined;
      // Close our pickCard
      if (window.hidePickCard) window.hidePickCard();
      // Close intel card
      if (window.hideIntelCard) window.hideIntelCard();
      // Close mapmode card
      if (window.hideMapmodeCard) window.hideMapmodeCard();
      // Close country card
      const cc = document.getElementById('countryCard');
      if (cc) cc.style.display = 'none';
      // Close legend card
      const lc = document.getElementById('legendCard');
      if (lc) lc.style.display = 'none';
    }
    window.dismissAllPopups = dismissAllPopups;

    // Unified click handler
    const handler = new Cesium.ScreenSpaceEventHandler(canvas);
    handler.setInputAction(function(click){
      const picked = window.viewer.scene.pick(click.position);

      // Case 0: clicked a mapmode polygon → show mapmode-specific deep card
      if (picked && picked.id && picked.id.properties && picked.id.properties.mapmode_entity) {
        const iso3 = picked.id.properties.iso3?.getValue?.() || picked.id.properties.iso3;
        if (iso3 && window.showMapmodeCard) {
          const handled = window.showMapmodeCard(iso3);
          if (handled) return;
        }
      }

      // Case 1: clicked an entity with pickcard properties → show universal card
      if (picked && picked.id && picked.id.properties && picked.id.properties.pickcard) {
        try {
          const props = picked.id.properties.pickcard.getValue();
          if (window.showPickCard) {
            dismissAllPopups();
            window.showPickCard(props);
            return;
          }
        } catch (_) {}
      }

      // Case 2: clicked an entity with a description → Cesium shows infobox
      if (picked && picked.id && picked.id.description) {
        // Close our custom popups so they don't overlap
        if (window.hidePickCard) window.hidePickCard();
        const cc = document.getElementById('countryCard');
        if (cc) cc.style.display = 'none';
        const lc = document.getElementById('legendCard');
        if (lc) lc.style.display = 'none';
        return;
      }

      // Case 3: clicked the globe surface → intelligence card for any country
      dismissAllPopups();
      const ray = window.viewer.camera.getPickRay(click.position);
      const cart = window.viewer.scene.globe.pick(ray, window.viewer.scene);
      if (!cart) return;
      const carto = Cesium.Cartographic.fromCartesian(cart);
      const lat = Cesium.Math.toDegrees(carto.latitude);
      const lon = Cesium.Math.toDegrees(carto.longitude);
      findNearestCountry(lat, lon).then(iso3 => {
        if (!iso3) return;
        // Try intelligence card first (cross-source analysis)
        if (window.showIntelCard) {
          window.showIntelCard(iso3);
        } else if (window.showCountryCard) {
          window.showCountryCard(iso3);
        }
      });
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
  }

  async function findNearestCountry(lat, lon) {
    try {
      const d = window._cacheStore ? window._cacheStore.get('country_resources') : null;
      if (!d || !d.countries) return null;
      let best = null, bestDist = Infinity;
      for (const iso3 in d.countries) {
        const c = d.countries[iso3];
        if (c.lat == null || c.lon == null) continue;
        const dlat = c.lat - lat;
        const dlon = c.lon - lon;
        const dist = dlat*dlat + dlon*dlon;
        if (dist < bestDist) { bestDist = dist; best = iso3; }
      }
      return best;
    } catch (_) { return null; }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})();
