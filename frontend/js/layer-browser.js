// Layer Browser — individual layer toggle panel.
// Press L to open. Every registered layer has its own on/off + opacity slider.
// Mode selection is a preset that bulk-toggles, but individual toggles stick
// across mode switches.
(function(){

  // Master registry of every layer known to the frontend. Source of truth for
  // the Layer Browser panel. Each entry points at a cache file + a renderer in
  // window.LAYERS (which is populated by layers.js).
  //
  // Categories:
  //   hazards       — earthquakes, fires, volcanoes, cyclones, floods, droughts
  //   weather       — wind, temperature, clouds, lightning, radar
  //   transit       — flights, ships, rail, AIS
  //   space         — ISS, satellites, aurora, space weather, asteroids
  //   economy       — trade flows, commodities, chokepoints, ports, macro
  //   resources     — power plants, climatetrace, country deep dive, oil/gas
  //   war           — UCDP, Wikidata battles, GDELT, GDACS, ReliefWeb
  //   society       — news, trends, YouTube, radio, gaming, sports
  //   infra         — cables, BGP, internet outages
  //   environment   — forest loss, AQ, water stress
  window.LAYER_REGISTRY = [
    // ===== HAZARDS =====
    { id: 'quakes',             name: 'Earthquakes (USGS)',        category: 'hazards', source: 'USGS', default: true },
    { id: 'fires',              name: 'Wildfires (VIIRS)',         category: 'hazards', source: 'NASA FIRMS', default: true },
    { id: 'volcanoes',          name: 'Volcanoes',                 category: 'hazards', source: 'Smithsonian GVP', default: false },
    { id: 'usgs_volcano_hans',  name: 'Elevated volcanoes',        category: 'hazards', source: 'USGS HANS', default: false },
    { id: 'nhc_cyclones',       name: 'Tropical cyclones',         category: 'hazards', source: 'NOAA NHC', default: true },
    { id: 'gdacs_events',       name: 'GDACS alerts',              category: 'hazards', source: 'GDACS', default: true },
    { id: 'disasters',          name: 'NASA EONET disasters',      category: 'hazards', source: 'NASA EONET', default: false },
    { id: 'dartmouth_floods',   name: 'Floods (Dartmouth)',        category: 'hazards', source: 'Dartmouth FO', default: false },

    // ===== WEATHER =====
    { id: 'wind_sample',        name: 'Wind particles',            category: 'weather', source: 'Open-Meteo', default: false },
    { id: 'rainviewer',         name: 'Rain radar',                category: 'weather', source: 'RainViewer', default: false },
    { id: 'air_quality',        name: 'Air quality (45 cities)',   category: 'weather', source: 'Open-Meteo', default: false },
    { id: 'openaq_stations',    name: 'Air quality (12k stations)',category: 'weather', source: 'OpenAQ v3', default: false },

    // ===== TRANSIT =====
    { id: 'flights',            name: 'Aircraft (ADS-B)',          category: 'transit', source: 'adsb.lol', default: true },
    { id: 'ships',              name: 'Ships (AIS)',               category: 'transit', source: 'AISStream', default: true },
    { id: 'gfw_events',         name: 'Dark vessels / gaps',       category: 'transit', source: 'Global Fishing Watch', default: false },
    { id: 'portwatch_chokepoints', name: 'Shipping chokepoints',   category: 'transit', source: 'IMF PortWatch', default: true },
    { id: 'portwatch_ports',    name: 'Ports (800)',               category: 'transit', source: 'IMF PortWatch', default: false },

    // ===== SPACE =====
    { id: 'iss',                name: 'ISS + crew',                category: 'space', source: 'WhereIsTheISS', default: true },
    { id: 'satellites',         name: 'Satellites (CelesTrak)',    category: 'space', source: 'CelesTrak', default: false },
    { id: 'spacetrack_gp',      name: 'Satellites (25k, Space-Track)', category: 'space', source: 'Space-Track', default: false },
    { id: 'swpc_aurora',        name: 'Aurora + space weather',    category: 'space', source: 'NOAA SWPC', default: false },
    { id: 'nasa_donki',         name: 'Space weather events',      category: 'space', source: 'NASA DONKI', default: false },
    { id: 'nasa_neows',         name: 'Asteroid close approaches', category: 'space', source: 'NASA NeoWs', default: false },
    { id: 'nasa_epic_earth',    name: 'L1 Earth images',           category: 'space', source: 'NASA EPIC', default: false },
    { id: 'nasa_mars_photos',   name: 'Mars rover photos',         category: 'space', source: 'NASA Mars Photos', default: false, planet: 'mars' },

    // ===== ECONOMY =====
    { id: 'trade_annual',       name: 'Trade flows (Comtrade)',    category: 'economy', source: 'UN Comtrade', default: true },
    { id: 'trade_monthly',      name: 'Monthly trade (Comtrade)',  category: 'economy', source: 'UN Comtrade', default: false },
    { id: 'commodity_prices',   name: 'Commodity ticker',          category: 'economy', source: 'datahub.io + CoinGecko', default: true },
    { id: 'economy',            name: 'Forex + crypto',            category: 'economy', source: 'Frankfurter + CoinGecko', default: false },
    { id: 'fred',               name: 'FRED macro (50 series)',    category: 'economy', source: 'St. Louis Fed', default: false },
    { id: 'imf_data',           name: 'IMF forecasts',             category: 'economy', source: 'IMF DataMapper', default: false },
    { id: 'world_bank',         name: 'World Bank indicators',     category: 'economy', source: 'World Bank API', default: false },
    { id: 'oecd_cli',           name: 'OECD recession signal',     category: 'economy', source: 'OECD SDMX', default: false },
    { id: 'fao_food_prices',    name: 'FAO food price index',      category: 'economy', source: 'FAO', default: false },
    { id: 'eia_petroleum',      name: 'US oil inventories',        category: 'economy', source: 'EIA', default: false },

    // ===== RESOURCES =====
    { id: 'wri_power_plants',   name: 'Power plants (WRI)',        category: 'resources', source: 'WRI GPPD', default: true },
    { id: 'climatetrace_assets',name: 'Facility emissions',        category: 'resources', source: 'ClimateTRACE', default: false },
    { id: 'country_resources',  name: 'Country fact sheets',       category: 'resources', source: 'UN Comtrade', default: false },
    { id: 'country_deep_dive',  name: 'Country deep dive',         category: 'resources', source: 'Aggregated', default: false },
    { id: 'owid_energy',        name: 'Country energy mix',        category: 'resources', source: 'OWID', default: false },
    { id: 'eia_international',  name: 'EIA International energy',  category: 'resources', source: 'EIA', default: false },
    { id: 'eia_930_grid',       name: 'US hourly grid',            category: 'resources', source: 'EIA-930', default: false },

    // ===== WAR =====
    { id: 'ucdp_ged',           name: 'UCDP conflict events',      category: 'war', source: 'UCDP GED', default: false },
    { id: 'wikidata_battles',   name: 'Wikidata battles',          category: 'war', source: 'Wikidata', default: false },
    { id: 'gdelt_gkg_themes',   name: 'GDELT themes',              category: 'war', source: 'GDELT GKG', default: false },
    { id: 'conflict_events',    name: 'GDELT conflict events',     category: 'war', source: 'GDELT Events 2.0', default: false },
    { id: 'relations',          name: 'Diplomatic relations',      category: 'war', source: 'GDELT QuadClass', default: false },
    { id: 'reliefweb',          name: 'Active humanitarian crises',category: 'war', source: 'ReliefWeb', default: false },
    { id: 'crises',             name: 'HDX crises',                category: 'war', source: 'HDX', default: false },

    // ===== SOCIETY =====
    { id: 'news',               name: 'News (GDELT keyword)',      category: 'society', source: 'GDELT DOC', default: false },
    { id: 'conflicts',          name: 'Conflict news',             category: 'society', source: 'GDELT DOC', default: false },
    { id: 'trends',             name: 'Wikipedia trends',          category: 'society', source: 'Wikimedia', default: false },
    { id: 'youtube',            name: 'YouTube trending',          category: 'society', source: 'YouTube', default: false },
    { id: 'radio',              name: 'Radio stations',            category: 'society', source: 'Radio Browser', default: false },
    { id: 'webcams',            name: 'Live webcams',              category: 'society', source: 'Windy', default: false },
    { id: 'sports',             name: 'Live sports',               category: 'society', source: 'ESPN', default: false },
    { id: 'gaming',             name: 'Gaming + Twitch',           category: 'society', source: 'Steam + Twitch', default: false },
    { id: 'population',         name: 'Country population',        category: 'society', source: 'REST Countries', default: false },

    // ===== INFRA =====
    { id: 'cables',             name: 'Submarine cables',          category: 'infra', source: 'TeleGeography', default: true },
    { id: 'cloudflare_radar',   name: 'Internet outages',          category: 'infra', source: 'Cloudflare Radar', default: false },

    // ===== META =====
    { id: 'global_events',      name: 'Events ticker feed',        category: 'meta', source: 'Aggregated', default: true },
    { id: 'pulse_mode',         name: 'Pulse apocalypse radar',    category: 'meta', source: 'Aggregated', default: false },
  ];

  const CATEGORY_META = {
    hazards:    { label: 'Hazards',       color: '#ef3b3b' },
    weather:    { label: 'Weather',       color: '#7ad7ff' },
    transit:    { label: 'Transit',       color: '#56B4E9' },
    space:      { label: 'Space',         color: '#7c8cff' },
    economy:    { label: 'Economy',       color: '#f4c84a' },
    resources:  { label: 'Resources',     color: '#9aa5b1' },
    war:        { label: 'War',           color: '#D55E00' },
    society:    { label: 'Society',       color: '#34d399' },
    infra:      { label: 'Infrastructure',color: '#5eead4' },
    environment:{ label: 'Environment',   color: '#009E73' },
    meta:       { label: 'Meta',          color: '#CC79A7' },
  };

  // Runtime state: {id: {on: bool, opacity: 0..1}}
  const state = {};
  window.LAYER_REGISTRY.forEach(l => {
    state[l.id] = { on: !!l.default, opacity: 1.0 };
  });
  window.LAYER_STATE = state;

  let _browserOpen = false;

  function buildPanel() {
    const host = document.getElementById('layerBrowser');
    if (!host) return;

    // Group by category
    const groups = {};
    window.LAYER_REGISTRY.forEach(l => {
      (groups[l.category] = groups[l.category] || []).push(l);
    });

    const head = `
      <div class="lb-head">
        <span>LAYERS <span style="color:var(--text-lo);font-weight:400">${window.LAYER_REGISTRY.length}</span></span>
        <span class="lb-close" id="lbClose">×</span>
      </div>
      <input class="lb-search" id="lbSearch" placeholder="Search layers…">
      <div class="lb-quick">
        <button class="lb-btn" id="lbShowAll">Show all</button>
        <button class="lb-btn" id="lbHideAll">Hide all</button>
        <button class="lb-btn" id="lbReset">Reset</button>
      </div>
      <div class="lb-groups" id="lbGroups"></div>
    `;
    host.innerHTML = head;

    const groupsEl = host.querySelector('#lbGroups');
    Object.entries(groups).forEach(([cat, layers]) => {
      const meta = CATEGORY_META[cat] || { label: cat, color: '#999' };
      const block = document.createElement('div');
      block.className = 'lb-cat';
      block.innerHTML = `
        <div class="lb-cat-head">
          <span class="lb-cat-dot" style="background:${meta.color}"></span>
          ${meta.label}
          <span class="lb-cat-count" style="color:var(--text-lo);font-weight:400">${layers.length}</span>
        </div>
        <div class="lb-cat-body">
          ${layers.map(l => {
            const on = state[l.id].on;
            return `
              <div class="lb-row" data-id="${l.id}">
                <label class="lb-toggle">
                  <input type="checkbox" ${on ? 'checked' : ''} data-action="toggle" data-id="${l.id}">
                  <span class="lb-swatch" style="background:${on ? meta.color : 'transparent'};border-color:${meta.color}"></span>
                </label>
                <div class="lb-row-main">
                  <div class="lb-row-name">${l.name}</div>
                  <div class="lb-row-sub">${l.source}</div>
                </div>
                <input type="range" class="lb-opacity" min="0" max="100" value="${(state[l.id].opacity * 100) | 0}" data-action="opacity" data-id="${l.id}">
              </div>
            `;
          }).join('')}
        </div>
      `;
      groupsEl.appendChild(block);
    });

    bindHandlers();
  }

  function bindHandlers() {
    const host = document.getElementById('layerBrowser');
    if (!host) return;
    host.querySelector('#lbClose').onclick = () => toggleBrowser(false);
    host.querySelector('#lbSearch').oninput = (e) => {
      const q = e.target.value.toLowerCase();
      host.querySelectorAll('.lb-row').forEach(row => {
        const txt = row.textContent.toLowerCase();
        row.style.display = txt.includes(q) ? '' : 'none';
      });
    };
    host.querySelector('#lbShowAll').onclick = () => { bulkSet(true); };
    host.querySelector('#lbHideAll').onclick = () => { bulkSet(false); };
    host.querySelector('#lbReset').onclick = () => {
      window.LAYER_REGISTRY.forEach(l => { state[l.id].on = !!l.default; });
      applyAll();
      buildPanel();
    };

    host.querySelectorAll('[data-action="toggle"]').forEach(cb => {
      cb.onchange = (e) => {
        const id = e.target.dataset.id;
        state[id].on = e.target.checked;
        applyLayer(id);
      };
    });
    host.querySelectorAll('[data-action="opacity"]').forEach(s => {
      s.oninput = (e) => {
        const id = e.target.dataset.id;
        state[id].opacity = e.target.value / 100;
        // opacity only affects layers already on
        if (state[id].on) applyLayer(id);
      };
    });
  }

  function bulkSet(on) {
    window.LAYER_REGISTRY.forEach(l => { state[l.id].on = on; });
    applyAll();
    buildPanel();
  }

  function applyLayer(id) {
    const entry = window.LAYERS && window.LAYERS[id];
    if (!entry) {
      // Layer not yet implemented in layers.js. Stub; just log.
      console.log(`[layer-browser] layer ${id} not rendered — no renderer in layers.js`);
      return;
    }
    try {
      if (state[id].on) {
        entry.render && entry.render();
      } else {
        entry.clear && entry.clear();
      }
    } catch (e) {
      console.warn('[layer-browser]', id, 'apply error', e);
    }
  }

  function applyAll() {
    Object.keys(state).forEach(applyLayer);
  }

  function toggleBrowser(force) {
    _browserOpen = force !== undefined ? force : !_browserOpen;
    const host = document.getElementById('layerBrowser');
    if (host) host.classList.toggle('show', _browserOpen);
  }

  // Keyboard shortcut
  document.addEventListener('keydown', (e) => {
    if (e.key === 'l' || e.key === 'L') {
      if (document.activeElement && ['INPUT','TEXTAREA'].includes(document.activeElement.tagName)) return;
      toggleBrowser();
    }
  });

  // Rebuild the panel whenever the registry changes
  window.LayerBrowser = {
    toggle: toggleBrowser,
    apply: applyLayer,
    applyAll: applyAll,
    rebuild: buildPanel,
    state,
  };

  // Build on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildPanel);
  } else {
    setTimeout(buildPanel, 200);
  }
})();
