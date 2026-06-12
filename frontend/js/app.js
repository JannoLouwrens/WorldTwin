// App bootstrap — Phase 2: single boot path.
//
// Order of operations on page load:
//   1. DOMContentLoaded fires
//   2. Inject SVG icons, wire mode buttons and help key
//   3. Fetch /worldtwin/config.json (single source of truth) into window.CONFIG
//   4. Preloader.preload() — parallel fetch every cache file in CONFIG
//   5. Planets.switchToBody('earth') — builds the viewer through the canonical path
//      (planets.js in turn calls window.buildEarthViewer, which is defined in
//      cesium-setup.js). When the viewer exists, planets.js schedules
//      activateMode('world') for us.
//   6. Attach click/hover handlers (now that the viewer exists).
//   7. Hide boot splash.
(function(){

  // Safety net: even if anything below throws, the splash hides after
  // 25 s so the user is never stranded staring at "Loading layers…".
  const BOOT_HARD_DEADLINE_MS = 25000;
  setTimeout(() => {
    const bootEl = document.getElementById('boot');
    if (bootEl && !bootEl.classList.contains('hidden')) {
      console.warn('[boot] hard deadline reached — forcing splash hide');
      bootEl.classList.add('hidden');
    }
  }, BOOT_HARD_DEADLINE_MS);

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
              <div class="lg-row"><span class="swatch"></span>1-9 0 q w e — Mapmode shortcuts</div>
              <div class="lg-row"><span class="swatch"></span>T — Hide/show timeline</div>
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
      // Guard: typing 'r' in the layer-browser search (or any input) must
      // not fly the camera — every other hotkey (L, D, T) already guards.
      if (e.target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
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
      // Cache-buster: a stale browser-cached config kept fetching layers
      // that no longer exist (dartmouth_floods 404 on every boot).
      const cr = await fetch('/worldtwin/config.json?v=' + (window.WT_BUILD || '20260611'));
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
      // Skip huge or non-renderable layers — they're fetched on demand.
      // The historical heavies (vdem, brecke, clio, cow, maddison, hyde,
      // historical_borders, historical_disasters, paleo_temperature) are
      // lazy-loaded when the scrubber leaves Live (see time-awareness-ui.js).
      const SKIP = new Set([
        'geoboundaries_adm1', 'spacetrack_gp', 'nasa_epic_earth',
        'vdem_democracy', 'brecke_wars', 'clio_life_expectancy',
        'cow_alliances',
        'historical_borders', 'historical_disasters',
        // Heavy + not needed for first paint. Lazy-loaded when their layer
        // toggle / mapmode is activated. Total saved: ~25 MB cold boot.
        'climatetrace_assets',  // 4.2 MB
        'disasters',            // 2.6 MB
        'ucdp_ged',             // 1.1 MB
        'wri_power_plants',     // 1.2 MB
        'gfw_events',           // 9.1 MB — renderer lazy-fetches
        'ucdp',                 // 3.2 MB — renderer lazy-fetches
        'openaq_stations',      // 2.0 MB — renderer lazy-fetches
        'nasa_neows',           // 1.5 MB — renderer lazy-fetches
        // Note: maddison_history + hyde_population stay in preload because
        // gdp_pc and population mapmodes (always-shown defaults) read them
        // even at Live for the unified-mapmode UX. ~1.5MB combined.
      ]);
      preloadIds = window.CONFIG.layers
        .filter(l => !SKIP.has(l.id) && l.status !== 'disabled')
        .map(l => l.id);
    }

    // PROGRESSIVE BOOT: the preload is NOT awaited. A first-time visitor
    // was staring at a black splash for up to 18s while 65 caches loaded —
    // but the globe doesn't need them to render, and every renderer
    // lazy-fetches via the store-first fetchCache anyway. The Earth is the
    // admission; the data streams in behind it (progress shown in the
    // small #loading pill, not a full-screen wall).
    if (window.Preloader) {
      const pill = document.getElementById('loading');
      const pillText = document.getElementById('loadingText');
      if (pill) pill.style.opacity = '1';
      window.Preloader.preload(preloadIds, (done, total) => {
        if (pillText) pillText.textContent = `DATA ${done}/${total}`;
      }).then(res => {
        if (pillText) pillText.textContent = `${res.ok} SOURCES LIVE`;
        if (pill) setTimeout(() => { pill.style.opacity = '0'; }, 2500);
      }).catch(() => {});
    }
    if (pt) pt.textContent = 'Starting the globe…';

    // Step 3: build the Earth viewer through the canonical planets.js path
    await window.Planets.switchToBody('earth');

    // Step 4: attach click + hover handlers (viewer now exists)
    attachGlobeHandlers();
    // Planet switches rebuild the viewer with a NEW canvas — handlers bound
    // to the old canvas die silently and clicks/hovers stop working after a
    // Moon round-trip. Watch for canvas identity changes and re-attach.
    let _handlerCanvas = window.viewer && window.viewer.scene.canvas;
    setInterval(() => {
      const c = window.viewer && !window.viewer.isDestroyed?.() && window.viewer.scene && window.viewer.scene.canvas;
      if (c && c !== _handlerCanvas) {
        _handlerCanvas = c;
        attachGlobeHandlers();
        console.log('[app] viewer canvas changed — handlers re-attached');
      }
    }, 2000);

    // Step 4b: mount historical timeline scrubber
    if (window.Scrubber) {
      window.Scrubber.mount('#timeline');
      // Default to "Live" — current real-world year — so existing layers behave as before
      window.Clock.setYear(window.Clock.MAX_YEAR, { force: true });
    }

    // Step 5: hide boot splash NOW — the globe is up; data keeps streaming.
    const bootEl = document.getElementById('boot');
    if (bootEl) bootEl.classList.add('hidden');
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
      // Close dossier (multi-source country panel)
      if (window.hideDossier) window.hideDossier();
      // Close mapmode card
      if (window.hideMapmodeCard) window.hideMapmodeCard();
      // Close legend card
      const lc = document.getElementById('legendCard');
      if (lc) lc.style.display = 'none';
    }
    window.dismissAllPopups = dismissAllPopups;

    // Unified click handler
    const handler = new Cesium.ScreenSpaceEventHandler(canvas);
    handler.setInputAction(function(click){
      const picked = window.viewer.scene.pick(click.position);
      const isCompare = !!(click && (click.shift || (window.event && window.event.shiftKey)));

      // Case 0: clicked a mapmode polygon → show mapmode-specific deep card
      // Shift-click bypasses the mapmode card and goes straight to dossier compare.
      if (picked && picked.id && picked.id.properties && picked.id.properties.mapmode_entity) {
        const iso3 = picked.id.properties.iso3?.getValue?.() || picked.id.properties.iso3;
        if (iso3 && isCompare && window.showDossier) {
          window.showDossier(iso3, { compare: true });
          return;
        }
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

      // Case 2: clicked an entity with a description → Cesium shows infobox.
      // Mutual exclusion: the infoBox wins this click, so EVERY other
      // right-lane card must yield — previously the dossier (z-110) and
      // mapmode card stayed open underneath the infoBox (z-130), stacking
      // three cards in the same lane. We can't call dismissAllPopups()
      // here because it clears viewer.selectedEntity, which would close
      // the infoBox Cesium just opened for this very click.
      if (picked && picked.id && picked.id.description) {
        if (window.hidePickCard) window.hidePickCard();
        if (window.hideDossier) window.hideDossier();
        if (window.hideMapmodeCard) window.hideMapmodeCard();
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
        // Single source of truth for country deep-dive: dossier.js composes 8 caches.
        if (window.showDossier) {
          window.showDossier(iso3, { compare: isCompare });
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
