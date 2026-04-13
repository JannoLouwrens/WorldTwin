// Cesium viewer boot — cinematic visual stack.
// Includes: Cesium ion base imagery, NASA VIIRS Black Marble night overlay with day/night alpha,
// Google Photorealistic 3D Tiles (gated below 120km), Cesium World Terrain,
// HBAO + bloom + lens flare post-processing, atmosphere tuning, shared animation clock.
//
// Phase 2 change: exposes window.buildEarthViewer() instead of running at document-load.
// This gives planets.js (the owner of viewer lifecycle) a single entry point to create
// or re-create the Earth viewer. Fixes the first-boot race where cesium-setup.js was
// creating the viewer before planets.js could initialize it with the Earth body config,
// leaving the user with a half-configured Earth until they switched to Moon and back.
(function(){
  // Cesium ion token (reused from Janno's existing frontend)
  Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJkM2Y5YmMzYy00YjM2LTQ3NWEtOTc0NS00MzFlNWQ3MjNhMWIiLCJpZCI6NDE1OTE4LCJpYXQiOjE3NzU3Mzc3MzF9.OUBBTwCH3I0kY9E64upcUBX97KjwtZuRq64oSeMszJk';

  // Animation clock is globally shared — initialized once per page load.
  window._animT = 0;
  const _animStart = performance.now();

  // The main entry: build the Earth viewer. Returns a Promise that resolves when
  // the viewer exists and base imagery has been chosen (or all providers failed).
  window.buildEarthViewer = async function buildEarthViewer() {
    // Defensive teardown of any previous viewer
    if (window.viewer) {
      try { window.viewer.destroy(); } catch (_) {}
    }
    document.getElementById('globe').innerHTML = '';

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
      skyAtmosphere: new Cesium.SkyAtmosphere(),
      contextOptions: {
        webgl: {
          alpha: false,
          preserveDrawingBuffer: false,
          powerPreference: 'high-performance',
          depth: true,
          stencil: false,
          antialias: true,
        },
      },
    });
    window.viewer = viewer;
    window.scene = viewer.scene;
    const scene = viewer.scene;

    // ============================================================
    // ATMOSPHERE — cinematic tuning
    // ============================================================
    scene.skyAtmosphere.hueShift = -0.08;
    scene.skyAtmosphere.saturationShift = 0.18;
    scene.skyAtmosphere.brightnessShift = 0.10;
    scene.globe.atmosphereLightIntensity = 6.0; // was 12.0 — halved to reduce glow blowout
    scene.globe.dynamicAtmosphereLighting = true;
    scene.globe.enableLighting = true;         // day/night terminator
    scene.globe.showGroundAtmosphere = true;
    scene.globe.maximumScreenSpaceError = 1.8; // slightly sharper than default 2.0
    scene.fog.enabled = true;
    scene.fog.density = 0.00015;
    scene.fog.screenSpaceErrorFactor = 4.0;

    // ============================================================
    // POST-PROCESSING — subtle bloom only, no HBAO, no lens flare
    // Previous values (contrast:130, bloom brightness:-0.25, ao intensity:2.4,
    // flare intensity:2.0) caused a massive red/crimson blowout on the globe.
    // Dialed back to gentle glow that enhances without destroying readability.
    // ============================================================
    try {
      scene.highDynamicRange = false; // HDR was causing tone-mapping blowout

      const bloom = scene.postProcessStages.bloom;
      if (bloom) {
        bloom.enabled = true;
        bloom.uniforms.contrast = 119;     // was 130 — way too hot
        bloom.uniforms.brightness = -0.1;  // was -0.25
        bloom.uniforms.glowOnly = false;
        bloom.uniforms.delta = 1.0;
        bloom.uniforms.sigma = 2.0;        // was 3.8 — tighter glow
        bloom.uniforms.stepSize = 1.0;
      }

      // HBAO disabled — it was darkening the globe unevenly
      const ao = scene.postProcessStages.ambientOcclusion;
      if (ao) {
        ao.enabled = false;
      }

      // Lens flare disabled — it was adding unwanted colour wash
    } catch (e) { console.warn('[setup] post-processing failed:', e); }

    // ============================================================
    // IMAGERY — stack
    // ============================================================
    viewer.imageryLayers.removeAll();

    // Base imagery — 3-tier fallback chain. AWAIT this so callers know when it's done.
    window._baseLayerName = 'loading…';
    const attempts = [
      {
        name: 'Cesium ion World Imagery',
        build: async () => await Cesium.IonImageryProvider.fromAssetId(2),
        brightness: 0.62, saturation: 0.85, gamma: 1.3, contrast: 1.15,
      },
      {
        name: 'ESRI World Imagery',
        build: async () => await Cesium.ArcGisMapServerImageryProvider.fromUrl(
          'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer',
          { enablePickFeatures: false }
        ),
        brightness: 0.70, saturation: 0.85, gamma: 1.2,
      },
      {
        name: 'OpenStreetMap',
        build: async () => new Cesium.OpenStreetMapImageryProvider({ url: 'https://tile.openstreetmap.org/' }),
        brightness: 0.65, saturation: 0.7,
      },
    ];
    for (const a of attempts) {
      try {
        const provider = await a.build();
        const dayLayer = viewer.imageryLayers.addImageryProvider(provider);
        if (a.brightness !== undefined) dayLayer.brightness = a.brightness;
        if (a.saturation !== undefined) dayLayer.saturation = a.saturation;
        if (a.gamma !== undefined) dayLayer.gamma = a.gamma;
        if (a.contrast !== undefined) dayLayer.contrast = a.contrast;
        window._dayLayer = dayLayer;
        window._baseLayerName = a.name;
        console.log('[setup] base imagery:', a.name);
        break;
      } catch (e) {
        console.warn('[setup] imagery failed:', a.name, e.message);
      }
    }
    if (window._baseLayerName === 'loading…') {
      window._baseLayerName = 'NONE — all providers failed';
    }
    if (window.updateDiagnostics) window.updateDiagnostics();

    // Night overlay: NASA VIIRS Black Marble via GIBS
    try {
      const nightLayer = viewer.imageryLayers.addImageryProvider(
        new Cesium.UrlTemplateImageryProvider({
          url: 'https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/VIIRS_Black_Marble/default/2016-01-01/500m/{z}/{y}/{x}.png',
          credit: 'NASA EOSDIS GIBS — VIIRS Black Marble',
          tilingScheme: new Cesium.GeographicTilingScheme(),
          maximumLevel: 8,
          tileWidth: 512,
          tileHeight: 512,
        })
      );
      nightLayer.dayAlpha = 0.0;
      nightLayer.nightAlpha = 0.95;
      nightLayer.brightness = 1.15;
      window._nightLayer = nightLayer;
    } catch (e) { console.warn('[setup] black marble failed:', e); }

    // Thin labels overlay
    try {
      const labelLayer = viewer.imageryLayers.addImageryProvider(
        new Cesium.UrlTemplateImageryProvider({
          url: 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}.png',
          subdomains: 'abcd',
          minimumLevel: 0,
          maximumLevel: 18,
        })
      );
      labelLayer.alpha = 0.55;
      window._labelLayer = labelLayer;
    } catch (e) {}

    // ============================================================
    // TERRAIN — Cesium World Terrain (free tier)
    // ============================================================
    try {
      scene.setTerrain(Cesium.Terrain.fromWorldTerrain());
    } catch (e) { console.warn('[setup] terrain failed:', e); }

    // ============================================================
    // GOOGLE PHOTOREALISTIC 3D TILES — lazy-loaded below 120km
    // ============================================================
    let photoRealTileset = null;
    let photoRealTried = false;
    async function tryEnablePhotoReal() {
      if (photoRealTileset || photoRealTried) return;
      photoRealTried = true;
      try {
        photoRealTileset = await Cesium.createGooglePhotorealistic3DTileset();
        scene.primitives.add(photoRealTileset);
        photoRealTileset.show = true;
        console.log('[setup] Google Photoreal 3D Tiles loaded');
      } catch (e) {
        console.warn('[setup] photoreal unavailable on this token:', e.message);
      }
    }
    scene.postRender.addEventListener(() => {
      if (photoRealTried) return;
      const height = scene.camera.positionCartographic.height;
      if (height < 120000) tryEnablePhotoReal();
    });

    // ============================================================
    // INITIAL CAMERA POSITION — far enough that flyTo looks cinematic
    // ============================================================
    viewer.camera.setView({
      destination: Cesium.Cartesian3.fromDegrees(20, 10, 24000000),
    });

    // ============================================================
    // SHARED ANIMATION CLOCK — attach to this scene
    // ============================================================
    scene.preRender.addEventListener(function(){
      window._animT = (performance.now() - _animStart) / 1000;
    });

    // Helpers used by layers.js for pulsing markers
    window.pulseAlpha = function(baseColor, lo=0.3, hi=1.0, freq=1) {
      return new Cesium.CallbackProperty(function(){
        const k = (Math.sin(window._animT * freq * Math.PI * 2) + 1) / 2;
        return baseColor.withAlpha(lo + (hi - lo) * k);
      }, false);
    };
    window.pulseSize = function(lo, hi, freq=1) {
      return new Cesium.CallbackProperty(function(){
        const k = (Math.sin(window._animT * freq * Math.PI * 2) + 1) / 2;
        return lo + (hi - lo) * k;
      }, false);
    };

    // NASA GIBS cloud composite (weather mode)
    window.addCloudComposite = function() {
      if (window._cloudLayer) return;
      try {
        const yesterday = new Date(Date.now() - 36 * 3600 * 1000).toISOString().slice(0, 10);
        const cloud = viewer.imageryLayers.addImageryProvider(
          new Cesium.WebMapTileServiceImageryProvider({
            url: 'https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/wmts.cgi',
            layer: 'MODIS_Terra_CorrectedReflectance_TrueColor',
            style: 'default',
            format: 'image/jpeg',
            tileMatrixSetID: '250m',
            time: yesterday,
            maximumLevel: 9,
            tilingScheme: new Cesium.GeographicTilingScheme(),
            credit: 'NASA GIBS',
          })
        );
        cloud.alpha = 0.55;
        window._cloudLayer = cloud;
      } catch (e) { console.warn('[setup] cloud composite:', e); }
    };
    window.removeCloudComposite = function() {
      if (window._cloudLayer) {
        try { viewer.imageryLayers.remove(window._cloudLayer); } catch (_) {}
        window._cloudLayer = null;
      }
    };

    console.log('[setup] Cesium viewer initialised — cinematic stack ready');
    return viewer;
  };
})();
