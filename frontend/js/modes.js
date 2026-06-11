// Mode definitions — each mode specifies which layers to render, the
// legend strip contents, the KPI row, and any mode-specific overrides.
(function(){

  // Phase 3: every mode now has real layers. No more empty layer arrays.
  const MODES = {
    world: {
      label: 'World · Overview',
      layers: ['quakes', 'fires', 'portwatch_chokepoints', 'iss', 'gdelt_gkg_themes', 'disasters', 'who_don'],
      legend: {
        title: 'Global Overview',
        ramp: 'heat',
        min: 'Low activity',
        max: 'High activity',
      },
      describe: 'All modes at a glance. Earth events, shipping pulses, ISS, trending news themes, disease outbreaks.',
    },
    weather: {
      label: 'Weather · Atmosphere',
      layers: ['temperature_field', 'noaa_sst', 'nhc_cyclones', 'fires', 'noaa_co2'],
      legend: {
        title: 'Surface Temperature · SST',
        ramp: 'heat',
        min: '-30 °C',
        max: '+45 °C',
      },
      describe: 'Surface temp, ocean SST, cyclones, fires, wind particles, cloud composite. Toggle pressure/humidity/AQ/radar via the layer bar above.',
      cloudComposite: true,
      windParticles: true,
    },
    nature: {
      label: 'Nature · Earth Events',
      layers: ['quakes', 'fires', 'gdacs_events', 'nhc_cyclones', 'volcanoes', 'usgs_volcano_hans', 'disasters', 'noaa_co2'],
      legend: {
        title: 'Hazard severity',
        ramp: 'fire',
        min: 'Advisory',
        max: 'Severe',
      },
      describe: 'Quakes, fires, volcanoes, floods, cyclones, GDACS unified hazard feed, EONET active disasters.',
    },
    war: {
      label: 'War · Conflict',
      layers: ['ucdp', 'ucdp_ged', 'conflict_events', 'wikidata_battles', 'gdelt_gkg_themes', 'gdacs_events', 'conflicts', 'crises', 'reliefweb'],
      legend: {
        title: 'Fatality intensity',
        ramp: 'fire',
        min: '1 dead',
        max: '1000+ dead',
      },
      describe: 'UCDP academic-verified, GDELT real-time violent events, Wikidata battles, humanitarian crises, conflict news.',
    },
    economy: {
      label: 'Economy · Trade & Markets',
      layers: ['trade_annual', 'portwatch_chokepoints', 'portwatch_ports'],
      legend: {
        title: 'Commodity flow (USD)',
        ramp: 'heat',
        min: '$50 M',
        max: '$50 B',
      },
      describe: 'UN Comtrade annual flows, live shipping chokepoints + port traffic, commodity price ticker.',
      ticker: true,
    },
    energy: {
      label: 'Energy · Grid & Mix',
      layers: ['energy_viz', 'eia_930_grid', 'entsoe_grid', 'wri_power_plants'],
      legend: {
        title: 'Energy mix · Renewable %',
        ramp: 'heat',
        min: '0% renewable',
        max: '100% renewable',
      },
      describe: 'Per-country fuel mix (solar/wind/nuclear/gas/coal/hydro), EU cross-border flows, US/EU grid real-time, 5000 power plants. Data: ENTSO-E + EIA + OWID.',
    },
    resources: {
      label: 'Resources · Commodities',
      layers: ['trade_annual', 'wri_power_plants', 'portwatch_chokepoints', 'climatetrace_assets', 'eia_930_grid', 'entsoe_grid'],
      legend: {
        title: 'Commodity flow (USD)',
        ramp: 'heat',
        min: '$50 M',
        max: '$50 B',
      },
      describe: 'Commodity flows, 5000 power plants, ClimateTRACE facility emissions, US grid monitor, chokepoints.',
      commodityFilter: true,
      ticker: true,
    },
    health: {
      label: 'Health · Outbreaks',
      layers: ['who_don', 'air_quality', 'openaq_stations'],
      legend: {
        title: 'Health risk severity',
        ramp: 'fire',
        min: 'Normal',
        max: 'Critical',
      },
      describe: 'WHO disease outbreaks, air quality at 45 cities + 12k OpenAQ stations.',
    },
    gaming: {
      label: 'Gaming · Esports',
      layers: ['youtube', 'webcams'],
      legend: {
        title: 'Concurrent players',
        ramp: 'density',
        min: 'Low',
        max: 'High',
      },
      describe: 'YouTube trending, webcams. Steam + Twitch data panel coming.',
    },
    sports: {
      label: 'Sports · Live',
      layers: ['sports'],
      legend: {
        title: 'Match engagement',
        ramp: 'density',
        min: '—',
        max: '—',
      },
      describe: 'Live matches: soccer, NBA, NFL, F1, tennis, cricket via ESPN.',
    },
    social: {
      label: 'Social · Narratives',
      layers: ['gdelt_gkg_themes', 'news', 'youtube', 'webcams', 'radio'],
      legend: {
        title: 'Theme mentions (hour)',
        ramp: 'heat',
        min: '5',
        max: '1000+',
      },
      describe: 'GDELT themes, breaking news, YouTube trending, webcams, radio stations worldwide.',
    },
    space: {
      label: 'Space · Orbit',
      layers: ['iss', 'satellites', 'swpc_aurora', 'nasa_donki', 'nasa_neows', 'spacetrack_gp'],
      legend: {
        title: 'Satellite altitude · Aurora probability',
        ramp: 'altitude',
        min: 'LEO',
        max: 'GEO',
      },
      describe: 'ISS with crew, live satellites, aurora oval, space weather (DONKI), asteroids, full satellite catalogue.',
    },
    pulse: {
      label: 'Pulse · Apocalypse Radar',
      layers: ['pulse_mode'],
      legend: {
        title: 'Composite concern score',
        ramp: 'fire',
        min: 'Fine',
        max: 'Alarming',
      },
      describe: 'Per-country composite score across water stress, food security, conflict, fires, grid carbon. Red = worrying.',
      pulsePanel: true,
    },
  };

  // Starts EMPTY — initializing to 'world' made boot's activateMode('world')
  // hit the toggle-OFF branch above, so the default mode never rendered.
  let currentMode = '';
  let _activationToken = 0;

  async function activateMode(modeId) {
    // Click same mode again → clear everything (no mode active)
    if (modeId === currentMode) {
      currentMode = '';
      Object.keys(window.LAYERS).forEach(lid => window.LAYERS[lid].clear());
      window.MAPMODE_COLORS = {};
      window.MAPMODE_HIGHLIGHT = {};
      window.MAPMODE_WAR_HOTSPOTS = {};
      if (window.dismissAllPopups) window.dismissAllPopups();
      try { document.getElementById('commodityPanel').classList.remove('show'); } catch (_) {}
      try { document.getElementById('tickerStrip').classList.remove('show'); } catch (_) {}
      try { document.getElementById('pulsePanel').classList.remove('show'); } catch (_) {}
      if (window.removeCloudComposite) window.removeCloudComposite();
      if (window.WindCanvas) window.WindCanvas.stop();
      window.showLoading(false);
      document.querySelectorAll('.mode').forEach(b => b.classList.remove('active'));
      if (window.setLegendStrip) window.setLegendStrip(null);
      if (window.LayerToggles) window.LayerToggles.syncToggles([]);
      return;
    }
    const mode = MODES[modeId];
    if (!mode) return;
    // Every call bumps the token. If a new call comes in while we are still
    // awaiting layer renders, we detect the staleness and bail out so the
    // newer activation wins cleanly — no overlapping renders, no hangs.
    const myToken = ++_activationToken;
    currentMode = modeId;

    // Clear all previous layers (safer than figuring out diff)
    Object.keys(window.LAYERS).forEach(lid => window.LAYERS[lid].clear());

    // Reset mapmode polygon colors to transparent (don't remove polygons,
    // just make them invisible so they don't bleed into non-mapmode views)
    window.MAPMODE_COLORS = {};
    window.MAPMODE_HIGHLIGHT = {};
    window.MAPMODE_WAR_HOTSPOTS = {};

    // Close any open popups/cards from previous interaction
    if (window.dismissAllPopups) window.dismissAllPopups();

    // Kill ancillary overlays
    try { document.getElementById('commodityPanel').classList.remove('show'); } catch (_) {}
    try { document.getElementById('tickerStrip').classList.remove('show'); } catch (_) {}
    try { document.getElementById('pulsePanel').classList.remove('show'); } catch (_) {}
    if (window.removeCloudComposite) window.removeCloudComposite();
    if (window.WindCanvas) window.WindCanvas.stop();

    // Render new layers
    window.showLoading(true, 'LOADING ' + modeId.toUpperCase());
    for (const lid of mode.layers) {
      if (myToken !== _activationToken) {
        // A newer activation started — abandon this one.
        return;
      }
      if (window.LAYERS[lid]) {
        try { await window.LAYERS[lid].render(); } catch (e) { console.warn(lid, 'render failed', e); }
      }
    }
    if (myToken !== _activationToken) return;
    window.showLoading(false);

    // Update UI chrome
    window.setLegendStrip(mode.legend, mode.describe);
    window.updateKpiRow(modeId);

    // Mode-specific UI
    if (mode.commodityFilter) {
      window.showCommodityFilter();
    }
    if (mode.ticker) {
      window.showTicker();
    }
    if (mode.cloudComposite && window.addCloudComposite) window.addCloudComposite();
    if (mode.windParticles && window.WindCanvas) window.WindCanvas.start();
    if (mode.pulsePanel) {
      document.getElementById('pulsePanel').classList.add('show');
      if (window.refreshPulsePanel) window.refreshPulsePanel();
    }

    // Update active mode button
    document.querySelectorAll('.mode').forEach(b => b.classList.toggle('active', b.dataset.mode === modeId));
  }

  window.activateMode = activateMode;
  window.MODES = MODES;
  window.currentModeId = () => currentMode;
})();
