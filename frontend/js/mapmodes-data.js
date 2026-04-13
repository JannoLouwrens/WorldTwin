// Mapmode registrations — 15 EU4-style choropleth modes.
// Each registers a colorFn(iso3, props) → hex that reads from cached data.
// Depends on mapmode.js being loaded first.
(function(){
  if (!window.Mapmode) {
    console.warn('[mapmodes-data] Mapmode engine not loaded');
    return;
  }

  // Helper: fetch a data source into the Mapmode cache once, lazily
  async function ensureCache(id) {
    let d = window.Mapmode.getDataCache(id);
    if (d) return d;
    if (window.fetchCache) {
      d = await window.fetchCache(id);
      if (d) window.Mapmode.setDataCache(id, d);
    } else {
      try {
        const r = await fetch(`/api/cache/${id}.json`);
        if (r.ok) { d = await r.json(); window.Mapmode.setDataCache(id, d); }
      } catch (_) {}
    }
    return d;
  }

  // Colour ramps
  const RAMPS = {
    // Sequential heat (low → high)
    heat: ['#1e3a8a','#2563eb','#06b6d4','#84cc16','#fde047','#fb923c','#ef4444'],
    // Cold → hot (good → bad)
    coldhot: ['#1e40af','#4cc2ff','#f8fafc','#fb923c','#b91c1c'],
    // Diverging recession (below 100 = red, above = green)
    diverging: ['#7f1d1d','#ef4444','#fde047','#84cc16','#22c55e'],
    // Density (viridis-like)
    density: ['#440154','#3b528b','#21908d','#5dc863','#fde725'],
    // Fire (alarming)
    fire: ['#fff7b8','#fde047','#fb923c','#ef4444','#b91c1c','#4a0e0e'],
  };

  function sampleRamp(ramp, t) {
    const stops = RAMPS[ramp] || RAMPS.heat;
    const i = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    const lo = Math.floor(i), hi = Math.ceil(i);
    return stops[lo === hi ? lo : Math.round(i)];
  }

  function logNorm(value, minExp, maxExp) {
    // Log-normalise value to 0..1 given expected log10 range
    if (!value || value <= 0) return 0;
    const l = Math.log10(value);
    return Math.max(0, Math.min(1, (l - minExp) / (maxExp - minExp)));
  }

  // ============================================================
  // MAPMODES
  // ============================================================

  // 1) Political — coloured by primary bloc membership
  window.Mapmode.register(
    'political',
    'Political blocs',
    (iso3, props) => {
      const rel = window.Mapmode.getDataCache('country_relations');
      if (!rel) return '#6b7790';
      const r = (rel.by_country || {})[iso3];
      return r?.bloc_color || '#2a3447';
    },
    { title: 'Political blocs', ramp: 'heat', min: 'Non-aligned', max: 'Major bloc' },
    'users'
  );

  // 2) GDP (current USD) — World Bank NY.GDP.MKTP.CD
  window.Mapmode.register(
    'gdp',
    'GDP (USD)',
    (iso3, props) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['NY.GDP.MKTP.CD'] || {}).value;
      if (v == null) return null;
      // $100M (8) → $25T (13.4)
      return sampleRamp('density', logNorm(v, 8, 13.5));
    },
    { title: 'GDP (current USD)', ramp: 'density', min: '$100M', max: '$25T' },
    'trending-up'
  );

  // 3) Population — World Bank SP.POP.TOTL
  window.Mapmode.register(
    'population',
    'Population',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.POP.TOTL'] || {}).value;
      if (v == null) return null;
      // 10k (4) → 1.5B (9.2)
      return sampleRamp('density', logNorm(v, 4, 9.2));
    },
    { title: 'Population', ramp: 'density', min: '10k', max: '1.5B' },
    'users-2'
  );

  // 4) GDP per capita — World Bank NY.GDP.PCAP.CD
  window.Mapmode.register(
    'gdp_pc',
    'GDP per capita',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['NY.GDP.PCAP.CD'] || {}).value;
      if (v == null) return null;
      return sampleRamp('coldhot', Math.max(0, Math.min(1, (Math.log10(Math.max(1, v)) - 2.3) / 2.8)));
    },
    { title: 'GDP per capita (USD)', ramp: 'coldhot', min: '$200', max: '$120k' },
    'coins'
  );

  // 5) Inflation — IMF PCPIPCH
  window.Mapmode.register(
    'inflation',
    'Inflation',
    (iso3) => {
      const imf = window.Mapmode.getDataCache('imf_data');
      const v = imf?.countries?.[iso3]?.PCPIPCH?.value;
      if (v == null) return null;
      // 0% → 0, 15%+ → 1 (red)
      return sampleRamp('coldhot', Math.max(0, Math.min(1, v / 15)));
    },
    { title: 'Inflation % (IMF)', ramp: 'coldhot', min: '0%', max: '15%+' },
    'percent'
  );

  // 6) Military spend % GDP — World Bank MS.MIL.XPND.GD.ZS
  window.Mapmode.register(
    'military',
    'Military spend % GDP',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['MS.MIL.XPND.GD.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('fire', Math.max(0, Math.min(1, v / 10)));
    },
    { title: 'Military spend % GDP', ramp: 'fire', min: '0%', max: '10%' },
    'swords'
  );

  // 7) Water stress — country_deep_dive.water.baseline_water_stress (0–5)
  window.Mapmode.register(
    'water_stress',
    'Water stress',
    (iso3) => {
      const dd = window.Mapmode.getDataCache('country_deep_dive');
      const v = dd?.countries?.[iso3]?.water?.baseline_water_stress;
      if (v == null) return null;
      return sampleRamp('coldhot', v / 5);
    },
    { title: 'Water stress (Aqueduct BWS)', ramp: 'coldhot', min: 'Low', max: 'Extreme' },
    'droplet'
  );

  // 8) Food security — country_deep_dive.food.ipc_phase (1–5)
  window.Mapmode.register(
    'food',
    'Food security (IPC)',
    (iso3) => {
      const dd = window.Mapmode.getDataCache('country_deep_dive');
      const v = dd?.countries?.[iso3]?.food?.ipc_phase;
      if (v == null) return null;
      return sampleRamp('fire', (v - 1) / 4);
    },
    { title: 'Food security (IPC phase)', ramp: 'fire', min: 'None', max: 'Famine' },
    'wheat'
  );

  // 9) CO2 per capita — World Bank EN.GHG.CO2.PC.CE.AR5
  window.Mapmode.register(
    'co2',
    'CO2 per capita',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['EN.GHG.CO2.PC.CE.AR5'] || {}).value;
      if (v == null) return null;
      // 0t → 0, 25t+ → 1 (high)
      return sampleRamp('fire', Math.max(0, Math.min(1, v / 25)));
    },
    { title: 'CO2 per capita (tonnes)', ramp: 'fire', min: '0', max: '25+' },
    'factory'
  );

  // 10) Renewable share of electricity — OWID energy
  window.Mapmode.register(
    'renewable',
    'Renewable electricity %',
    (iso3) => {
      const owid = window.Mapmode.getDataCache('owid_energy');
      const v = owid?.countries?.[iso3]?.renewables_share_elec;
      if (v == null) return null;
      return sampleRamp('diverging', v / 100);
    },
    { title: 'Renewable electricity %', ramp: 'diverging', min: '0%', max: '100%' },
    'zap'
  );

  // 11) Internet users — World Bank IT.NET.USER.ZS
  window.Mapmode.register(
    'internet',
    'Internet penetration',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['IT.NET.USER.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('density', v / 100);
    },
    { title: 'Internet users %', ramp: 'density', min: '0%', max: '100%' },
    'globe-2'
  );

  // 12) Life expectancy — World Bank SP.DYN.LE00.IN
  window.Mapmode.register(
    'life',
    'Life expectancy',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.DYN.LE00.IN'] || {}).value;
      if (v == null) return null;
      // 50 → 0, 85 → 1
      return sampleRamp('coldhot', Math.max(0, Math.min(1, (v - 50) / 35)));
    },
    { title: 'Life expectancy (years)', ramp: 'coldhot', min: '50', max: '85' },
    'heart'
  );

  // 13) Urban population % — World Bank SP.URB.TOTL.IN.ZS
  window.Mapmode.register(
    'urban',
    'Urban population %',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.URB.TOTL.IN.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('density', v / 100);
    },
    { title: 'Urban %', ramp: 'density', min: '0%', max: '100%' },
    'building-2'
  );

  // 14) Debt % GDP — World Bank GC.DOD.TOTL.GD.ZS
  window.Mapmode.register(
    'debt',
    'Gov debt % GDP',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['GC.DOD.TOTL.GD.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('fire', Math.max(0, Math.min(1, v / 200)));
    },
    { title: 'Gov debt % GDP', ramp: 'fire', min: '0%', max: '200%+' },
    'landmark'
  );

  // 15) Pulse composite (apocalypse radar) — pulse_mode
  window.Mapmode.register(
    'pulse',
    'Pulse (apocalypse radar)',
    (iso3) => {
      const p = window.Mapmode.getDataCache('pulse_mode');
      const c = p?.countries?.[iso3];
      if (!c) return null;
      return sampleRamp('fire', (c.composite || 0) / 100);
    },
    { title: 'Pulse composite score', ramp: 'fire', min: 'Fine', max: 'Alarming' },
    'atom'
  );

  // Preload all caches the mapmodes need, then default-activate 'political'
  Promise.all([
    ensureCache('world_bank'),
    ensureCache('imf_data'),
    ensureCache('country_deep_dive'),
    ensureCache('owid_energy'),
    ensureCache('pulse_mode'),
    ensureCache('country_relations'),
    ensureCache('country_polygons'),
  ]).then(() => {
    console.log('[mapmodes-data] all data sources cached');
    // Auto-activate political mode after boot
    setTimeout(() => {
      if (window.Mapmode && !window.Mapmode.current()) {
        window.Mapmode.activate('political');
      }
    }, 3500);
  });
})();
