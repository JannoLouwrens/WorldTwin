// layer-toggles.js — Top selector strip showing ALL available layers as toggleable icons.
//
// Renders a compact scrollable row below the mapmode bar. Each button represents
// one data layer (flights, ships, radio, temp, quakes, etc.). Click toggles the
// layer on/off independently of the active mode.
//
// Uses config.json categories for grouping and coloring.
(function(){

  // No more emojis. Each layer button shows just a 6px category dot
  // (styled in CSS via [data-cat]) plus the clean text label.
  const LAYER_ICONS = {};

  // Short human-readable names
  const LAYER_NAMES = {
    quakes: 'Quakes', fires: 'Fires', volcanoes: 'Volcanoes', usgs_volcano_hans: 'HANS',
    nhc_cyclones: 'Cyclones', disasters: 'EONET', gdacs_events: 'GDACS',
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
    nhc_cyclones: 'nature', disasters: 'nature', gdacs_events: 'nature',
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

  // Display order for the categories (left → right). Hot/threat categories
  // first because that's what reads the news asks first; sport/gaming last.
  const CAT_ORDER = ['nature', 'weather', 'war', 'transit', 'economy',
                      'resources', 'health', 'space', 'social',
                      'infra', 'sports', 'gaming', 'meta'];

  // Human-readable category labels for the bar
  const CAT_LABELS = {
    nature: 'Nature', weather: 'Weather', war: 'Conflict', transit: 'Transit',
    economy: 'Economy', resources: 'Resources', health: 'Health',
    space: 'Space', social: 'Society', infra: 'Infra',
    sports: 'Sports', gaming: 'Gaming', meta: 'Meta',
  };

  function buildToggleBar() {
    const host = document.getElementById('layerToggles');
    if (!host) return;
    if (!window.LAYERS) { setTimeout(buildToggleBar, 300); return; }

    // Group all known layers by category
    const groups = {};
    Object.keys(window.LAYERS).filter(id => LAYER_NAMES[id]).forEach(id => {
      const cat = LAYER_CATS[id] || 'meta';
      (groups[cat] = groups[cat] || []).push(id);
    });
    // Alpha within each group
    Object.keys(groups).forEach(cat => groups[cat].sort((a, b) =>
      (LAYER_NAMES[a] || a).localeCompare(LAYER_NAMES[b] || b)));

    host.innerHTML = '';
    host.classList.add('lt-grouped');

    // Order categories per CAT_ORDER, append any unknown at end
    const seen = new Set();
    const ordered = CAT_ORDER.filter(c => groups[c]).concat(
      Object.keys(groups).filter(c => !CAT_ORDER.includes(c))
    );

    for (const cat of ordered) {
      if (seen.has(cat) || !groups[cat]) continue;
      seen.add(cat);
      const group = document.createElement('div');
      group.className = 'lt-group';
      group.dataset.cat = cat;
      group.innerHTML = `<span class="lt-grouplabel">${CAT_LABELS[cat] || cat}</span>`;
      for (const id of groups[cat]) {
        const btn = document.createElement('button');
        btn.className = 'lt-btn';
        btn.dataset.layer = id;
        btn.dataset.cat = cat;
        btn.title = LAYER_NAMES[id] || id;
        btn.innerHTML = `<span class="lt-ico"></span><span class="lt-name">${LAYER_NAMES[id] || id}</span>`;
        btn.addEventListener('click', () => toggleLayer(id, btn));
        group.appendChild(btn);
      }
      host.appendChild(group);
    }
  }

  function _countAll() {
    const v = window.viewer; if (!v) return { ent: 0, img: 0 };
    let n = v.entities.values.length;
    for (let i = 0; i < v.dataSources.length; i++) n += v.dataSources.get(i).entities.values.length;
    return { ent: n, img: v.imageryLayers.length };
  }

  function _toast(msg) {
    let t = document.getElementById('lt-toast');
    if (!t) {
      t = document.createElement('div'); t.id = 'lt-toast';
      t.style.cssText = 'position:fixed;left:50%;bottom:200px;transform:translateX(-50%);background:rgba(15,17,21,0.92);color:#e6edf6;border:1px solid rgba(255,255,255,0.12);backdrop-filter:blur(12px) saturate(140%);padding:10px 16px;border-radius:8px;font:500 12px/1.4 Satoshi,system-ui;letter-spacing:0.02em;z-index:9999;opacity:0;transition:opacity 200ms ease;pointer-events:none;max-width:420px;text-align:center';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.opacity = '1';
    clearTimeout(_toast._tm);
    _toast._tm = setTimeout(() => { t.style.opacity = '0'; }, 2400);
  }

  async function toggleLayer(id, btn) {
    if (!window.LAYERS[id]) return;
    if (activeToggles.has(id)) {
      activeToggles.delete(id);
      window.LAYERS[id].clear();
      btn.classList.remove('lt-active');
      btn.classList.remove('lt-empty');
    } else {
      activeToggles.add(id);
      btn.classList.add('lt-active');
      btn.classList.remove('lt-empty');
      const before = _countAll();
      try { await window.LAYERS[id].render(); } catch (e) { console.warn(id, 'toggle render failed', e); }
      // Tiny grace period — some renderers add entities post-await
      await new Promise(r => setTimeout(r, 600));
      const after = _countAll();
      const added = (after.ent - before.ent) + (after.img - before.img);
      if (added <= 0) {
        btn.classList.add('lt-empty');
        const label = LAYER_NAMES[id] || id;
        _toast(`${label}: no data right now (source quiet or quota hit)`);
      }
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
