// layer-toggles.js — Top selector strip showing ALL available layers as toggleable icons.
//
// Renders a compact scrollable row below the mapmode bar. Each button represents
// one data layer (flights, ships, radio, temp, quakes, etc.). Click toggles the
// layer on/off independently of the active mode.
//
// Uses config.json categories for grouping and coloring.
(function(){

  // Layer icon mapping — short emoji-style labels for the toggle buttons
  const LAYER_ICONS = {
    // Nature
    quakes: '⚡', fires: '🔥', volcanoes: '🌋', usgs_volcano_hans: '⛰️',
    nhc_cyclones: '🌀', disasters: '☣️', gdacs_events: '⚠️', dartmouth_floods: '💧',
    // Weather
    temperature_field: '🌡️', pressure_field: '📊', humidity_field: '💧', noaa_sst: '🌊', rainviewer: '🌧️',
    air_quality: '💨', wind_sample: '🌬️', noaa_co2: '🌫️',
    historical_borders: '🏛️', historical_disasters: '🌍', paleo_temperature: '🌡️',
    // Transit
    flights: '✈️', ships: '🚢',
    // Space
    iss: '🛸', satellites: '📡', spacetrack_gp: '🛰️', swpc_aurora: '🌌',
    nasa_donki: '☀️', nasa_neows: '☄️',
    // War
    ucdp_ged: '⚔️', ucdp: '🎓', conflict_events: '💥', wikidata_battles: '🗡️',
    conflicts: '📰', crises: '🆘', reliefweb: '🏥',
    // Economy
    trade_annual: '📦', portwatch_chokepoints: '⚓', portwatch_ports: '🏗️',
    // Resources
    climatetrace_assets: '🏭', wri_power_plants: '⚡', eia_930_grid: '🔌', entsoe_grid: '⚡', energy_viz: '🔋',
    // Social
    gdelt_gkg_themes: '📢', news: '📰', youtube: '▶️', radio: '📻', webcams: '📷',
    // Health
    who_don: '🦠', openaq_stations: '🫁',
    // Infra
    cables: '🔗', cloudflare_radar: '🌐',
    // Sports/Gaming
    sports: '⚽', gaming: '🎮',
    // Meta
    pulse_mode: '💓',
  };

  // Short human-readable names
  const LAYER_NAMES = {
    quakes: 'Quakes', fires: 'Fires', volcanoes: 'Volcanoes', usgs_volcano_hans: 'HANS',
    nhc_cyclones: 'Cyclones', disasters: 'EONET', gdacs_events: 'GDACS', dartmouth_floods: 'Floods',
    temperature_field: 'Temp', pressure_field: 'Pressure', humidity_field: 'Humidity', noaa_sst: 'Ocean SST', rainviewer: 'Radar',
    air_quality: 'AQI', wind_sample: 'Wind', openaq_stations: 'OpenAQ', noaa_co2: 'CO₂',
    historical_borders: 'History', historical_disasters: 'Hist Disasters', paleo_temperature: 'Paleo °C',
    flights: 'Planes', ships: 'Vessels', iss: 'ISS', satellites: 'Sats',
    spacetrack_gp: 'SATCAT', swpc_aurora: 'Aurora', nasa_donki: 'DONKI', nasa_neows: 'Asteroids',
    ucdp_ged: 'UCDP (hist)', ucdp: 'UCDP (2024)', conflict_events: 'Conflicts', wikidata_battles: 'Battles',
    conflicts: 'War News', crises: 'Crises', reliefweb: 'ReliefWeb',
    trade_annual: 'Trade', portwatch_chokepoints: 'Chokepoints', portwatch_ports: 'Ports',
    climatetrace_assets: 'Emissions', wri_power_plants: 'Plants', eia_930_grid: 'US Grid', entsoe_grid: 'EU Grid', energy_viz: 'Energy Mix',
    gdelt_gkg_themes: 'Themes', news: 'News', youtube: 'YouTube', radio: 'Radio', webcams: 'Webcams',
    who_don: 'WHO', cables: 'Cables', cloudflare_radar: 'Internet',
    sports: 'Sports', gaming: 'Gaming', pulse_mode: 'Pulse',
  };

  // Category → color for the active state
  const CAT_COLORS = {
    nature: '#ef6666', war: '#ff3b3b', weather: '#4c7fff', economy: '#22c55e',
    resources: '#f59e0b', health: '#06b6d4', transit: '#a855f7', space: '#8b5cf6',
    infra: '#14b8a6', social: '#ec4899', sports: '#f97316', gaming: '#84cc16', meta: '#94a3b8',
  };

  const LAYER_CATS = {
    quakes: 'nature', fires: 'nature', volcanoes: 'nature', usgs_volcano_hans: 'nature',
    nhc_cyclones: 'nature', disasters: 'nature', gdacs_events: 'nature', dartmouth_floods: 'nature',
    temperature_field: 'weather', pressure_field: 'weather', humidity_field: 'weather', noaa_sst: 'weather', rainviewer: 'weather',
    air_quality: 'health', wind_sample: 'weather', openaq_stations: 'health', noaa_co2: 'nature',
    historical_borders: 'meta', historical_disasters: 'nature', paleo_temperature: 'weather',
    flights: 'transit', ships: 'transit', iss: 'space', satellites: 'space',
    spacetrack_gp: 'space', swpc_aurora: 'space', nasa_donki: 'space', nasa_neows: 'space',
    ucdp_ged: 'war', ucdp: 'war', conflict_events: 'war', wikidata_battles: 'war',
    conflicts: 'war', crises: 'war', reliefweb: 'war',
    trade_annual: 'economy', portwatch_chokepoints: 'economy', portwatch_ports: 'economy',
    climatetrace_assets: 'resources', wri_power_plants: 'resources', eia_930_grid: 'resources', entsoe_grid: 'resources', energy_viz: 'resources',
    gdelt_gkg_themes: 'social', news: 'social', youtube: 'social', radio: 'social', webcams: 'social',
    who_don: 'health', cables: 'infra', cloudflare_radar: 'infra',
    sports: 'sports', gaming: 'gaming', pulse_mode: 'meta',
  };

  // Track which layers are currently rendered (independent of mode)
  const activeToggles = new Set();

  function buildToggleBar() {
    const host = document.getElementById('layerToggles');
    if (!host) return;
    if (!window.LAYERS) { setTimeout(buildToggleBar, 300); return; }

    // Order: group by category, then alpha within group
    const ordered = Object.keys(window.LAYERS)
      .filter(id => LAYER_NAMES[id])  // only layers with known names
      .sort((a, b) => {
        const ca = LAYER_CATS[a] || 'zzz';
        const cb = LAYER_CATS[b] || 'zzz';
        if (ca !== cb) return ca.localeCompare(cb);
        return (LAYER_NAMES[a] || a).localeCompare(LAYER_NAMES[b] || b);
      });

    host.innerHTML = '<span class="lt-label">LAYERS</span>';
    let lastCat = '';
    ordered.forEach(id => {
      const cat = LAYER_CATS[id] || 'meta';
      if (cat !== lastCat) {
        const sep = document.createElement('span');
        sep.className = 'lt-sep';
        sep.textContent = '│';
        host.appendChild(sep);
        lastCat = cat;
      }
      const btn = document.createElement('button');
      btn.className = 'lt-btn';
      btn.dataset.layer = id;
      btn.dataset.cat = cat;
      btn.title = LAYER_NAMES[id] || id;
      btn.innerHTML = `<span class="lt-ico">${LAYER_ICONS[id] || '●'}</span><span class="lt-name">${LAYER_NAMES[id] || id}</span>`;
      btn.addEventListener('click', () => toggleLayer(id, btn));
      host.appendChild(btn);
    });
  }

  async function toggleLayer(id, btn) {
    if (!window.LAYERS[id]) return;
    if (activeToggles.has(id)) {
      // Turn off
      activeToggles.delete(id);
      window.LAYERS[id].clear();
      btn.classList.remove('lt-active');
    } else {
      // Turn on
      activeToggles.add(id);
      btn.classList.add('lt-active');
      try { await window.LAYERS[id].render(); } catch (e) { console.warn(id, 'toggle render failed', e); }
    }
  }

  // When a mode activates, update toggle bar to reflect which layers are now active
  function syncToggles(activeLayers) {
    activeToggles.clear();
    (activeLayers || []).forEach(id => activeToggles.add(id));
    document.querySelectorAll('.lt-btn').forEach(btn => {
      btn.classList.toggle('lt-active', activeToggles.has(btn.dataset.layer));
    });
  }

  // Monkey-patch activateMode to sync toggles after mode switch
  const _origActivateMode = window.activateMode;
  if (_origActivateMode) {
    window.activateMode = async function(modeId) {
      await _origActivateMode(modeId);
      const mode = window.MODES && window.MODES[modeId];
      if (mode) syncToggles(mode.layers);
    };
  }

  window.LayerToggles = { buildToggleBar, syncToggles, activeToggles };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(buildToggleBar, 500));
  } else {
    setTimeout(buildToggleBar, 500);
  }
})();
