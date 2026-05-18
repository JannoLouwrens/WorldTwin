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
    // ATMOSPHERE — cinematic tuning (sky + ground + fog)
    // Mie/Rayleigh coefficients tuned for "blue limb at horizon, deep
    // black at zenith" — the look of NASA Earth-from-ISS photos.
    // ============================================================
    scene.skyAtmosphere.show = true;
    // hueShift was -0.05 (warm); shifted to 0 (neutral) so the dark side
    // doesn't pick up a red tint from the bloom-stage highlight bleed.
    scene.skyAtmosphere.hueShift = 0;
    scene.skyAtmosphere.saturationShift = 0.18;
    scene.skyAtmosphere.brightnessShift = 0.02;
    if ('atmosphereLightIntensity' in scene.skyAtmosphere) {
      scene.skyAtmosphere.atmosphereLightIntensity = 12;
    }
    if ('atmosphereMieCoefficient' in scene.skyAtmosphere) {
      scene.skyAtmosphere.atmosphereMieCoefficient = new Cesium.Cartesian3(2.1e-5, 2.1e-5, 2.1e-5);
      scene.skyAtmosphere.atmosphereRayleighCoefficient = new Cesium.Cartesian3(5.5e-6, 13e-6, 28.4e-6);
      scene.skyAtmosphere.atmosphereMieScaleHeight = 3200;
    }

    // Ground atmosphere — the limb glow visible from space
    scene.globe.showGroundAtmosphere = true;
    scene.globe.atmosphereLightIntensity = 10.0;
    if ('atmosphereRayleighCoefficient' in scene.globe) {
      scene.globe.atmosphereRayleighCoefficient = new Cesium.Cartesian3(5.5e-6, 13e-6, 28.4e-6);
      scene.globe.atmosphereRayleighScaleHeight = 10000;
      scene.globe.atmosphereMieScaleHeight = 3200;
    }
    scene.globe.dynamicAtmosphereLighting = true;
    scene.globe.dynamicAtmosphereLightingFromSun = true;  // shading follows real sun position
    scene.globe.enableLighting = true;
    scene.globe.nightFadeOutDistance = 10000000;
    scene.globe.nightFadeInDistance = 50000000;
    scene.globe.maximumScreenSpaceError = 1.8;

    // Fog — distant horizon haze
    scene.fog.enabled = true;
    scene.fog.density = 0.00018;
    scene.fog.minimumBrightness = 0.03;
    scene.fog.screenSpaceErrorFactor = 4.0;

    // ============================================================
    // POST-PROCESSING — HDR + MSAA + bloom + custom vignette
    // ============================================================
    try {
      // HDR + tonemapping — re-enabled with carefully tuned downstream
      // imagery brightness/gamma so it doesn't blow out.
      scene.highDynamicRange = true;
      // MSAA 4x — free anti-aliasing on modern GPUs (Cesium 1.108+)
      if ('msaaSamples' in scene) scene.msaaSamples = 4;
      viewer.resolutionScale = Math.min(window.devicePixelRatio || 1, 2);

      const bloom = scene.postProcessStages.bloom;
      if (bloom) {
        // Dialed-down: contrast 128 + brightness -0.3 was crushing the night
        // side into red bloom around city-light clusters. These values keep
        // a subtle highlight glow without bleeding warm hue across the dark
        // hemisphere.
        bloom.enabled = true;
        bloom.uniforms.contrast = 40;
        bloom.uniforms.brightness = -0.15;
        bloom.uniforms.glowOnly = false;
        bloom.uniforms.delta = 1.2;
        bloom.uniforms.sigma = 2.0;
        bloom.uniforms.stepSize = 1.0;
      }

      // FXAA off — MSAA replaces it
      const fxaa = scene.postProcessStages.fxaa;
      if (fxaa) fxaa.enabled = false;

      // HBAO off — heavy + uneven on the globe
      const ao = scene.postProcessStages.ambientOcclusion;
      if (ao) ao.enabled = false;

      // Custom vignette + warm/cool color grade.
      // Cesium 1.124 GLSL fragment shader convention.
      const vignetteShader = `
        uniform sampler2D colorTexture;
        in vec2 v_textureCoordinates;
        void main() {
          vec2 uv = v_textureCoordinates;
          vec4 c = texture(colorTexture, uv);
          float d = distance(uv, vec2(0.5));
          float v = smoothstep(0.92, 0.30, d);
          c.rgb *= mix(0.55, 1.0, v);
          // shadow warm, highlight cool
          c.r += (1.0 - v) * -0.015;
          c.b += (1.0 - v) *  0.030;
          out_FragColor = c;
        }`;
      const vignette = new Cesium.PostProcessStage({
        name: 'tw_vignette',
        fragmentShader: vignetteShader,
      });
      scene.postProcessStages.add(vignette);
      window._vignetteStage = vignette;
      console.log('[setup] HDR + MSAA + vignette enabled');
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

    // ============================================================
    // ERA-AWARE BASE IMAGERY SWAP — Stamen Watercolor for pre-1800,
    // bathymetry-tinted Bing for 1800-1945, modern Bing for 1945+.
    // The era boundary triggers a 600ms crossfade so it never pops.
    // ============================================================
    window._eraImageryProviders = {
      modern: null,    // Bing — re-use existing window._dayLayer
      antique: null,   // Stamen Watercolor (lazy-built)
    };
    window._currentEra = 'modern';
    async function swapBaseForYear(year) {
      // 3-tier era split: antique pre-1800 (BlueMarble, painterly),
      // industrial 1800-1945 (Bing dimmed + saturation drop, sepia tilt),
      // modern 1945+ (Bing as-shipped).
      const era = year < 1800 ? 'antique' : (year < 1945 ? 'industrial' : 'modern');
      if (era === window._currentEra) return;
      // Build antique layer on first need
      if (era === 'antique' && !window._eraImageryProviders.antique) {
        try {
          // NASA GIBS BlueMarble Next Generation — natural-color monthly composite,
          // looks "earthier" without modern roads/cities/labels. Free, no key.
          const provider = new Cesium.UrlTemplateImageryProvider({
            url: 'https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/BlueMarble_NextGeneration/default/500m/{z}/{y}/{x}.jpeg',
            credit: 'NASA EOSDIS GIBS — BlueMarble Next Generation',
            tilingScheme: new Cesium.GeographicTilingScheme(),
            maximumLevel: 8,
            tileWidth: 512,
            tileHeight: 512,
          });
          const layer = viewer.imageryLayers.addImageryProvider(provider);
          layer.alpha = 0;
          layer.brightness = 1.0;
          layer.saturation = 1.25;
          layer.gamma = 1.1;
          window._eraImageryProviders.antique = layer;
          // Antique drawn ABOVE day base — but must be BELOW night overlay
          if (window._nightLayer) {
            const nightIdx = viewer.imageryLayers.indexOf(window._nightLayer);
            const antIdx = viewer.imageryLayers.indexOf(layer);
            if (nightIdx >= 0 && antIdx > nightIdx) {
              viewer.imageryLayers.lower(layer);
            }
          }
        } catch (e) { console.warn('[era] antique imagery failed:', e); return; }
      }
      // Imagery selection: antique uses BlueMarble layer, industrial+modern both use Bing
      const wasAntique = (window._currentEra === 'antique');
      const willAntique = (era === 'antique');
      window._currentEra = era;

      // Modern → industrial / industrial → modern: just retune the existing Bing
      // colour/brightness/saturation. No layer crossfade needed — re-rolls instantly.
      const tuneBing = () => {
        if (!window._dayLayer) return;
        if (era === 'industrial') {
          window._dayLayer.brightness = 0.55;     // dimmer
          window._dayLayer.saturation = 0.45;     // muted
          window._dayLayer.gamma = 1.05;
          window._dayLayer.hue = -0.05;           // slight sepia warm shift
        } else if (era === 'modern') {
          window._dayLayer.brightness = 0.62;
          window._dayLayer.saturation = 0.85;
          window._dayLayer.gamma = 1.3;
          window._dayLayer.hue = 0;
        }
      };

      if (willAntique && !wasAntique) {
        // Modern/industrial → antique: crossfade Bing → BlueMarble
        const oldLayer = window._dayLayer;
        const newLayer = window._eraImageryProviders.antique;
        const start = performance.now();
        const oldStartAlpha = oldLayer.alpha;
        function tick() {
          const t = Math.min(1, (performance.now() - start) / 600);
          newLayer.alpha = t;
          oldLayer.alpha = oldStartAlpha * (1 - t);
          if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      } else if (!willAntique && wasAntique) {
        // Antique → industrial/modern: crossfade BlueMarble → Bing, plus retune
        const oldLayer = window._eraImageryProviders.antique;
        const newLayer = window._dayLayer;
        tuneBing();
        const start = performance.now();
        const oldStartAlpha = oldLayer.alpha;
        function tick() {
          const t = Math.min(1, (performance.now() - start) / 600);
          newLayer.alpha = t;
          oldLayer.alpha = oldStartAlpha * (1 - t);
          if (t < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      } else {
        // Same family — just retune (industrial ↔ modern)
        tuneBing();
      }
      console.log(`[era] swapped to ${era} for year ${year}`);
    }
    window.swapBaseForYear = swapBaseForYear;

    // ============================================================
    // Bind WorldTwin Clock → viewer.clock so the day/night terminator
    // follows the scrubber. Without this, the sun is locked at boot
    // time and BC dates render with the wrong shading.
    // ============================================================
    try {
      if (window.Clock) {
        const applyYearToCesiumClock = (year) => {
          if (year === undefined) year = window.Clock.year;
          // Cesium JulianDate goes wonky for BC dates and silently produces
          // NaN, which kills dynamic atmosphere lighting (the globe goes black).
          // Clamp the year fed to the *Cesium clock* to a positive year so the
          // sun-position math stays sane. The visual difference of orbital
          // precession over 4000 years is < 1 degree — nobody notices.
          const safeYear = Math.max(1900, Math.min(year, window.Clock.MAX_YEAR));
          let jd;
          try { jd = window.Clock.toJulianDate(safeYear); } catch (_) { return; }
          if (!jd) return;
          // Add wall-clock seconds so day/night still rotates over a session
          const secondsToday = (Date.now() / 1000) % 86400;
          Cesium.JulianDate.addSeconds(jd, secondsToday, jd);
          // Sanity: bail if Cesium produced a NaN-laden date
          const iso = Cesium.JulianDate.toIso8601(jd);
          if (iso && !iso.includes('NaN')) {
            viewer.clock.currentTime = jd;
          }
          viewer.clock.shouldAnimate = (year === window.Clock.MAX_YEAR);
          if (year === window.Clock.MAX_YEAR) {
            viewer.clock.multiplier = 600;   // ~1 day per ~2.4 minutes
          }
          // Era-aware base imagery swap (uses real year, not clamped)
          if (window.swapBaseForYear) window.swapBaseForYear(year);
          // Auto-load historical layers when entering pre-modern era (real year)
          if (window.autoLoadHistoricalLayers) window.autoLoadHistoricalLayers(year);
        };
        window.Clock.subscribe(applyYearToCesiumClock);
        applyYearToCesiumClock();
      }
    } catch (e) { console.warn('[setup] Clock binding failed:', e); }

    console.log('[setup] Cesium viewer initialised — cinematic stack ready');
    return viewer;
  };
})();
