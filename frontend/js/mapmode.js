// Mapmode engine — EU4-style choropleth over country polygons.
// Reads /api/cache/country_polygons.json (Natural Earth 50m admin-0).
// Exposes:
//   window.Mapmode.register(id, name, colorFn, legend, icon) — define a mapmode
//   window.Mapmode.activate(id) — switch mapmode; polygons instantly repaint
//   window.Mapmode.list() — array of registered mapmodes
//   window.Mapmode.current() — active mapmode id
//   window.Mapmode.setDataCache(name, data) — inject a data source
//   window.MAPMODE_COLORS — { iso3: cssHex } — read by the CallbackProperty each frame
//   window.MAPMODE_HIGHLIGHT — { iso3: cssHex } — temporary hover overlay
(function(){
  const MAPMODES = {};
  let currentId = null;
  let polygonEntities = {};  // iso3 → Cesium Entity
  let polygonsLoaded = false;
  let polygonsByIso3 = {};   // iso3 → feature.properties

  // Base layer colour used when a country has no value for the active mapmode
  const NO_DATA = '#2a3447';
  const NO_DATA_ALPHA = 0.35;

  // Hover highlight colour — set by layer-browser or country-click handler
  window.MAPMODE_HIGHLIGHT = {};
  window.MAPMODE_COLORS = {};

  function hexToCesiumColor(hex, alpha = 0.72) {
    if (!hex || typeof hex !== 'string') return Cesium.Color.fromCssColorString(NO_DATA).withAlpha(NO_DATA_ALPHA);
    return Cesium.Color.fromCssColorString(hex).withAlpha(alpha);
  }

  function makeColorProperty(iso3) {
    // CallbackProperty reads the live colour map every frame — switching
    // mapmodes is just `window.MAPMODE_COLORS = {...}` and Cesium repaints.
    return new Cesium.ColorMaterialProperty(new Cesium.CallbackProperty(() => {
      const highlight = window.MAPMODE_HIGHLIGHT[iso3];
      if (highlight) return hexToCesiumColor(highlight, 0.88);
      const c = window.MAPMODE_COLORS[iso3];
      if (c) return hexToCesiumColor(c, 0.72);
      // No mapmode + no highlight → fully transparent (clean Earth visible)
      return Cesium.Color.TRANSPARENT;
    }, false));
  }

  function makeOutlineProperty(iso3) {
    return new Cesium.CallbackProperty(() => {
      // War hotspots (populated by layer war_hotspots) get a red pulse outline
      const warLevel = (window.MAPMODE_WAR_HOTSPOTS || {})[iso3];
      if (warLevel) {
        const t = (Math.sin(window._animT * 3) + 1) / 2;
        return Cesium.Color.RED.withAlpha(0.4 + t * 0.6);
      }
      // Hover: thick white outline on hovered + allies + enemies
      if ((window.MAPMODE_HIGHLIGHT || {})[iso3]) {
        return Cesium.Color.WHITE.withAlpha(0.9);
      }
      // Default outline: very faint hairline. Brightens only when a mapmode is active.
      const hasMode = Object.keys(window.MAPMODE_COLORS || {}).length > 0;
      return Cesium.Color.WHITE.withAlpha(hasMode ? 0.18 : 0.06);
    }, false);
  }

  async function loadPolygons() {
    if (polygonsLoaded) return;
    // Guard against being called before the Cesium viewer is built. Retry every
    // 200ms until viewer.entities exists, then proceed. This was the cause of
    // "Cannot read properties of undefined (reading 'entities')" on cold boot.
    let waitMs = 0;
    while (!window.viewer || !window.viewer.entities) {
      await new Promise(r => setTimeout(r, 200));
      waitMs += 200;
      if (waitMs > 15000) {
        console.warn('[mapmode] viewer never appeared — giving up on polygon load');
        return;
      }
    }
    try {
      const r = await (window.fetchCache ? window.fetchCache('country_polygons') : fetch('/api/cache/country_polygons.json').then(r => r.json()));
      if (!r || !r.features) {
        console.warn('[mapmode] country_polygons not yet available');
        return;
      }
      console.log('[mapmode] loading', r.features.length, 'country polygons');
      r.features.forEach(f => {
        const props = f.properties || {};
        const iso3 = props.iso3;
        if (!iso3) return;
        polygonsByIso3[iso3] = props;
        addCountryEntity(f, iso3, props);
      });
      polygonsLoaded = true;
      console.log('[mapmode] loaded', Object.keys(polygonEntities).length, 'country entities');
      // Re-activate ONLY a genuinely pending activation (one that arrived
      // before polygons finished). Re-firing whenever currentId was truthy
      // made a stale mapmode paint itself minutes after boot — the phantom
      // "Politics choropleth appeared on its own" bug.
      if (_pendingActivate) {
        const id = _pendingActivate;
        _pendingActivate = null;
        activate(id);
      }
    } catch (e) {
      console.warn('[mapmode] loadPolygons error', e);
    }
  }

  function addCountryEntity(feature, iso3, props) {
    const geom = feature.geometry;
    if (!geom) return;

    const addPolygon = (coords) => {
      // coords is an array of rings; outer ring first, holes follow
      const outer = coords[0];
      if (!outer || outer.length < 3) return;
      const positions = [];
      for (const [lon, lat] of outer) positions.push(lon, lat);
      const hierarchy = new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(positions));
      const entity = window.viewer.entities.add({
        name: props.name || iso3,
        polygon: {
          hierarchy: hierarchy,
          material: makeColorProperty(iso3),
          outline: true,
          outlineColor: makeOutlineProperty(iso3),
          outlineWidth: 1.2,
          height: 0,
          extrudedHeight: undefined,
        },
        properties: {
          iso3: iso3,
          mapmode_entity: true,
        },
        description: `<b>${props.name || iso3}</b><br>ISO3: ${iso3}<br>Population: ${(props.pop || 0).toLocaleString()}<br>Continent: ${props.continent || '—'}`,
      });
      // Store first entity per country (most geometries have one dominant ring)
      if (!polygonEntities[iso3]) polygonEntities[iso3] = [];
      polygonEntities[iso3].push(entity);
    };

    if (geom.type === 'Polygon') {
      addPolygon(geom.coordinates);
    } else if (geom.type === 'MultiPolygon') {
      for (const poly of geom.coordinates) addPolygon(poly);
    }
  }

  function register(id, name, colorFn, legend, icon, opts) {
    // opts.timeAware = true   → repaint when Clock fires
    // opts.years = [ya, yb]   → register an availability band on the scrubber
    MAPMODES[id] = { id, name, colorFn, legend, icon, ...(opts || {}) };
  }

  // Re-run the active mapmode's colorFn — used both for first-paint and for
  // time-aware repaint when Clock changes. Cheap because it only touches
  // window.MAPMODE_COLORS; the polygon material reads it via CallbackProperty.
  function repaint() {
    if (!currentId) return;
    const mode = MAPMODES[currentId];
    if (!mode) return;
    const colors = {};
    for (const iso3 of Object.keys(polygonsByIso3)) {
      try {
        const hex = mode.colorFn(iso3, polygonsByIso3[iso3]);
        if (hex) colors[iso3] = hex;
      } catch (_) {}
    }
    window.MAPMODE_COLORS = colors;
  }

  // Subscribe once to Clock — repaint any time-aware mapmode automatically.
  let _clockSub = null;
  function ensureClockSub() {
    if (_clockSub || !window.Clock) return;
    _clockSub = window.Clock.subscribe(() => {
      const mode = MAPMODES[currentId];
      if (mode && mode.timeAware) repaint();
    });
  }

  // Map every mode → list of caches its colorFn / tooltip needs. When a mode
  // is activated we lazy-fetch any of these that aren't already loaded so
  // the choropleth paints with real data instead of the grey fallback.
  const MODE_DATA_NEEDS = {
    religion: ['country_culture'],
    ethnicity: ['country_culture'],
    political: ['country_relations'],
    democracy: ['vdem_democracy'],
    gdp: ['world_bank'], gdp_pc: ['world_bank'],
    population: ['world_bank'],
    urban: ['world_bank'], internet: ['world_bank'], life: ['world_bank'],
    co2: ['world_bank'], renewable: ['world_bank'], military: ['world_bank'],
    inflation: ['imf_data', 'world_bank'],   // WB FP.CPI.TOTL.ZG is the fallback
    debt: ['world_bank', 'imf_data'],        // debt colorFn reads world_bank
    water_stress: ['country_deep_dive'], food: ['country_deep_dive'],
    pulse: ['pulse_mode'],
  };

  async function ensureDataForMode(id) {
    const needs = MODE_DATA_NEEDS[id] || [];
    let fetchedAny = false;
    for (const name of needs) {
      if (dataCaches[name]) continue;
      // Try the page-wide cache first
      const cached = window._cacheStore?.get?.(name);
      if (cached) { dataCaches[name] = cached; fetchedAny = true; continue; }
      // Otherwise fetch on demand
      if (window.fetchCache) {
        try {
          const d = await window.fetchCache(name);
          if (d) { dataCaches[name] = d; fetchedAny = true; }
        } catch(_) {}
      }
    }
    return fetchedAny;
  }

  let _pendingActivate = null;

  async function activate(id) {
    if (!polygonsLoaded) {
      currentId = id;
      _pendingActivate = id;
      await loadPolygons();
      if (!polygonsLoaded) {
        // Will be picked up after polygons finish loading
        return;
      }
      _pendingActivate = null;
    }
    const mode = MAPMODES[id];
    if (!mode) {
      console.warn('[mapmode] unknown mapmode', id);
      return;
    }
    currentId = id;
    // Ensure the data this mode needs is loaded BEFORE we run colorFn —
    // without this, religion/ethnicity/economy choropleths fall back to grey.
    await ensureDataForMode(id);
    // Compute colour per country
    const colors = {};
    for (const iso3 of Object.keys(polygonsByIso3)) {
      try {
        const hex = mode.colorFn(iso3, polygonsByIso3[iso3]);
        if (hex) colors[iso3] = hex;
      } catch (e) {
        // Skip
      }
    }
    window.MAPMODE_COLORS = colors;
    // Paint the Mapmode Bar button active state
    document.querySelectorAll('.mmbar-btn').forEach(b => b.classList.toggle('active', b.dataset.mm === id));
    // Update legend (optional — mode can provide its own legend string)
    if (mode.legend && window.setLegendStrip) {
      window.setLegendStrip(mode.legend, mode.name);
    }
    // Time-aware mapmodes: subscribe to Clock for live repaint, advertise availability
    ensureClockSub();
    if (window.Scrubber) {
      if (mode.timeAware && mode.years) {
        window.Scrubber.registerLayer('mapmode:' + id, mode.years, '#a855f7');
      } else {
        window.Scrubber.unregisterLayer('mapmode:' + id);
      }
    }
    console.log('[mapmode] activated', id, 'coloured', Object.keys(colors).length, 'countries');
  }

  // Clear ALL polygon entities (used on planet switch)
  function clearPolygons() {
    for (const iso3 in polygonEntities) {
      for (const e of polygonEntities[iso3]) {
        try { window.viewer.entities.remove(e); } catch (_) {}
      }
    }
    polygonEntities = {};
    polygonsByIso3 = {};
    polygonsLoaded = false;
  }

  // Optional: inject an external data cache for the colorFn to read.
  // e.g. Mapmode.setDataCache('world_bank', wbJsonDict)
  const dataCaches = {};
  function setDataCache(name, data) {
    dataCaches[name] = data;
  }
  function getDataCache(name) {
    return dataCaches[name];
  }

  // Hover a country — set ally/enemy highlight
  // Mapmode-aware hover. Political shows blocs/enemies. Religion/ethnicity
  // show same-category. Everything else just highlights the hovered country
  // and emits a `mapmode_hover` event for tooltip rendering.
  async function hoverCountry(iso3) {
    if (!iso3) {
      window.MAPMODE_HIGHLIGHT = {};
      window.dispatchEvent(new CustomEvent('mapmode_hover', { detail: null }));
      return;
    }
    const mode = MAPMODES[currentId];
    const props = polygonsByIso3[iso3] || {};
    const highlight = { [iso3]: '#ffffff' };

    if (currentId === 'political') {
      // Show allies (bloc) and enemies — but cap to keep visual clarity
      let rel = dataCaches.country_relations;
      if (!rel && window.fetchCache) {
        rel = await window.fetchCache('country_relations');
        if (rel) dataCaches.country_relations = rel;
      }
      const r = rel?.by_country?.[iso3];
      if (r) {
        const allyHue = r.bloc_color || '#4cc2ff';
        // Allies often number 80+ which is visual noise. Cap to top 12 by alphabetic
        // order (the data isn't ranked) — gives "primary bloc" feel.
        (r.allies || []).slice(0, 12).forEach(a => { highlight[a] = allyHue; });
        (r.enemies || []).forEach(e => { highlight[e] = '#ef3b3b' });
      }
    } else if (currentId === 'religion' || currentId === 'ethnicity') {
      // Highlight all countries with the same religion/ethnicity family.
      // Cache shape is FLAT: { religion_family, ethnicity_family } — not nested.
      const cc = dataCaches.country_culture;
      const target = cc?.countries?.[iso3];
      const myFamily = currentId === 'religion'
        ? (target?.religion_family || target?.religion?.family)
        : (target?.ethnicity_family || target?.ethnicity?.family);
      if (myFamily && cc?.countries) {
        for (const otherIso of Object.keys(cc.countries)) {
          if (otherIso === iso3) continue;
          const other = cc.countries[otherIso];
          const otherFamily = currentId === 'religion'
            ? (other?.religion_family || other?.religion?.family)
            : (other?.ethnicity_family || other?.ethnicity?.family);
          if (otherFamily === myFamily) {
            highlight[otherIso] = (window.MAPMODE_COLORS || {})[otherIso] || '#ffffff';
          }
        }
      }
    }
    // For all other mapmodes (gdp, population, military, etc.) — just the one country.

    window.MAPMODE_HIGHLIGHT = highlight;
    // Emit hover event with the country value for tooltip rendering
    const value = (window.MAPMODE_COLORS || {})[iso3];
    window.dispatchEvent(new CustomEvent('mapmode_hover', {
      detail: { iso3, name: props.name || iso3, value, mode: currentId },
    }));
  }

  function clearHover() {
    window.MAPMODE_HIGHLIGHT = {};
  }

  // True deselect: clear colors + highlight + scrubber registration without
  // activating another mode (used by the Layer Browser active-row re-click).
  function deactivate() {
    if (currentId && window.Scrubber) {
      window.Scrubber.unregisterLayer('mapmode:' + currentId);
    }
    currentId = null;
    _pendingActivate = null;
    window.MAPMODE_COLORS = {};
    window.MAPMODE_HIGHLIGHT = {};
    document.querySelectorAll('.mmbar-btn').forEach(b => b.classList.remove('active'));
    if (window.setLegendStrip) window.setLegendStrip(null);
  }

  window.Mapmode = {
    register,
    activate,
    deactivate,
    repaint,
    list: () => Object.values(MAPMODES),
    current: () => currentId,
    loadPolygons,
    clearPolygons,
    setDataCache,
    getDataCache,
    hoverCountry,
    clearHover,
    polygonsByIso3: () => polygonsByIso3,
  };
})();
