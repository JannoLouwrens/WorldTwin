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

  // Colour ramps — SEMANTIC:
  //   bad      — HIGH = BAD (green → red)
  //   good     — HIGH = GOOD (red → green)
  //   neutral  — raw size/intensity, no value judgment (teal → deep blue)
  // Legacy ramps (heat/fire/coldhot/diverging/density) kept for backwards-compat
  // but we avoid them for new mapmodes so the user always gets green=good, red=bad.
  const RAMPS = {
    bad:      ['#15803d','#84cc16','#fde047','#fb923c','#ef4444','#b91c1c'],
    good:     ['#b91c1c','#ef4444','#fb923c','#fde047','#84cc16','#15803d'],
    neutral:  ['#cffafe','#67e8f9','#06b6d4','#0e7490','#1e3a8a'],

    // Legacy
    heat: ['#1e3a8a','#2563eb','#06b6d4','#84cc16','#fde047','#fb923c','#ef4444'],
    coldhot: ['#1e40af','#4cc2ff','#f8fafc','#fb923c','#b91c1c'],
    diverging: ['#7f1d1d','#ef4444','#fde047','#84cc16','#22c55e'],
    density: ['#440154','#3b528b','#21908d','#5dc863','#fde725'],
    fire: ['#fff7b8','#fde047','#fb923c','#ef4444','#b91c1c','#4a0e0e'],
  };

  function sampleRamp(ramp, t) {
    const stops = RAMPS[ramp] || RAMPS.bad;
    const i = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    const lo = Math.floor(i), hi = Math.ceil(i);
    if (lo === hi) return stops[lo];
    // Interpolate linearly for smoother transitions
    const t2 = i - lo;
    const a = stops[lo], b = stops[hi];
    const ra = parseInt(a.slice(1,3),16), ga = parseInt(a.slice(3,5),16), ba = parseInt(a.slice(5,7),16);
    const rb = parseInt(b.slice(1,3),16), gb2 = parseInt(b.slice(3,5),16), bb = parseInt(b.slice(5,7),16);
    const r = Math.round(ra + (rb-ra)*t2), g = Math.round(ga + (gb2-ga)*t2), bl = Math.round(ba + (bb-ba)*t2);
    return '#' + [r,g,bl].map(x => x.toString(16).padStart(2,'0')).join('');
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

  // 2) GDP (current USD) — NEUTRAL (raw size, neither good nor bad)
  window.Mapmode.register(
    'gdp',
    'GDP (USD)',
    (iso3, props) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['NY.GDP.MKTP.CD'] || {}).value;
      if (v == null) return null;
      return sampleRamp('neutral', logNorm(v, 8, 13.5));
    },
    { title: 'GDP (current USD)', ramp: 'neutral', min: '$100M', max: '$25T', semantic: 'neutral' },
    'trending-up'
  );

  // 3) Population — NEUTRAL
  window.Mapmode.register(
    'population',
    'Population',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.POP.TOTL'] || {}).value;
      if (v == null) return null;
      return sampleRamp('neutral', logNorm(v, 4, 9.2));
    },
    { title: 'Population', ramp: 'neutral', min: '10k', max: '1.5B', semantic: 'neutral' },
    'users-2'
  );

  // 4) GDP per capita — GOOD (higher = better wealth)
  window.Mapmode.register(
    'gdp_pc',
    'GDP per capita',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['NY.GDP.PCAP.CD'] || {}).value;
      if (v == null) return null;
      return sampleRamp('good', Math.max(0, Math.min(1, (Math.log10(Math.max(1, v)) - 2.3) / 2.8)));
    },
    { title: 'GDP per capita (USD)', ramp: 'good', min: '$200 (poor)', max: '$120k (rich)', semantic: 'good' },
    'coins'
  );

  // 5) Inflation — BAD (higher = worse)
  window.Mapmode.register(
    'inflation',
    'Inflation',
    (iso3) => {
      const imf = window.Mapmode.getDataCache('imf_data');
      const v = imf?.countries?.[iso3]?.PCPIPCH?.value;
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 15)));
    },
    { title: 'Inflation % (IMF)', ramp: 'bad', min: '0% (stable)', max: '15%+ (high)', semantic: 'bad' },
    'percent'
  );

  // 6) Military spend % GDP — BAD (higher = more militarised)
  window.Mapmode.register(
    'military',
    'Military spend % GDP',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['MS.MIL.XPND.GD.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 10)));
    },
    { title: 'Military spend % GDP', ramp: 'bad', min: '0% (low)', max: '10%+ (high)', semantic: 'bad' },
    'swords'
  );

  // 7) Water stress — BAD (higher = worse)
  window.Mapmode.register(
    'water_stress',
    'Water stress',
    (iso3) => {
      const dd = window.Mapmode.getDataCache('country_deep_dive');
      const v = dd?.countries?.[iso3]?.water?.baseline_water_stress;
      if (v == null) return null;
      return sampleRamp('bad', v / 5);
    },
    { title: 'Water stress (Aqueduct BWS)', ramp: 'bad', min: 'Low (good)', max: 'Extreme (bad)', semantic: 'bad' },
    'droplet'
  );

  // 8) Food security — BAD (higher IPC phase = worse, more hungry)
  window.Mapmode.register(
    'food',
    'Food security (IPC)',
    (iso3) => {
      const dd = window.Mapmode.getDataCache('country_deep_dive');
      const v = dd?.countries?.[iso3]?.food?.ipc_phase;
      if (v == null) return null;
      return sampleRamp('bad', (v - 1) / 4);
    },
    { title: 'Food security (IPC phase)', ramp: 'bad', min: 'None (good)', max: 'Famine (bad)', semantic: 'bad' },
    'wheat'
  );

  // 9) CO2 per capita — BAD (higher = more pollution)
  window.Mapmode.register(
    'co2',
    'CO2 per capita',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['EN.GHG.CO2.PC.CE.AR5'] || {}).value;
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 25)));
    },
    { title: 'CO2 per capita (tonnes)', ramp: 'bad', min: '0 (clean)', max: '25+ (dirty)', semantic: 'bad' },
    'factory'
  );

  // 10) Renewable share of electricity — GOOD (higher = cleaner energy)
  window.Mapmode.register(
    'renewable',
    'Renewable electricity %',
    (iso3) => {
      const owid = window.Mapmode.getDataCache('owid_energy');
      const v = owid?.countries?.[iso3]?.renewables_share_elec;
      if (v == null) return null;
      return sampleRamp('good', v / 100);
    },
    { title: 'Renewable electricity %', ramp: 'good', min: '0% (fossil)', max: '100% (green)', semantic: 'good' },
    'zap'
  );

  // 11) Internet users — GOOD (higher = better connectivity)
  window.Mapmode.register(
    'internet',
    'Internet penetration',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['IT.NET.USER.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('good', v / 100);
    },
    { title: 'Internet users %', ramp: 'good', min: '0% (offline)', max: '100% (online)', semantic: 'good' },
    'globe-2'
  );

  // 12) Life expectancy — GOOD (higher = better health)
  window.Mapmode.register(
    'life',
    'Life expectancy',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.DYN.LE00.IN'] || {}).value;
      if (v == null) return null;
      return sampleRamp('good', Math.max(0, Math.min(1, (v - 50) / 35)));
    },
    { title: 'Life expectancy (years)', ramp: 'good', min: '50 (low)', max: '85 (high)', semantic: 'good' },
    'heart'
  );

  // 13) Urban population % — NEUTRAL (neither inherently good nor bad)
  window.Mapmode.register(
    'urban',
    'Urban population %',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['SP.URB.TOTL.IN.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('neutral', v / 100);
    },
    { title: 'Urban %', ramp: 'neutral', min: '0% (rural)', max: '100% (urban)', semantic: 'neutral' },
    'building-2'
  );

  // 14) Debt % GDP — BAD (higher = more indebted)
  window.Mapmode.register(
    'debt',
    'Gov debt % GDP',
    (iso3) => {
      const wb = window.Mapmode.getDataCache('world_bank');
      const v = (wb?.countries?.[iso3]?.['GC.DOD.TOTL.GD.ZS'] || {}).value;
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 200)));
    },
    { title: 'Gov debt % GDP', ramp: 'bad', min: '0% (low)', max: '200%+ (high)', semantic: 'bad' },
    'landmark'
  );

  // 15) Religion — CATEGORICAL (family-colored)
  window.Mapmode.register(
    'religion',
    'Religion',
    (iso3) => {
      const c = window.Mapmode.getDataCache('country_culture');
      const r = c?.countries?.[iso3];
      return r?.religion_color || '#2a3447';
    },
    {
      title: 'Primary religion', categorical: true, semantic: 'categorical',
      swatches: [
        { color: '#6B8CCE', label: 'Christianity' },
        { color: '#2E8B57', label: 'Islam' },
        { color: '#FF8C42', label: 'Hinduism' },
        { color: '#F4C430', label: 'Buddhism' },
        { color: '#9B7EBD', label: 'Judaism' },
        { color: '#E8B4C8', label: 'Shinto' },
        { color: '#7BA05B', label: 'Folk/Animist' },
        { color: '#888888', label: 'Non-religious' },
      ],
    },
    'church'
  );

  // 16) Ethnicity — CATEGORICAL (family-colored)
  window.Mapmode.register(
    'ethnicity',
    'Ethnicity',
    (iso3) => {
      const c = window.Mapmode.getDataCache('country_culture');
      const e = c?.countries?.[iso3];
      return e?.ethnicity_color || '#2a3447';
    },
    {
      title: 'Primary ethnic group', categorical: true, semantic: 'categorical',
      swatches: [
        { color: '#D4A574', label: 'European' },
        { color: '#A8754E', label: 'Slavic' },
        { color: '#E8B04B', label: 'East Asian' },
        { color: '#C67E3E', label: 'Southeast Asian' },
        { color: '#D47C4E', label: 'South Asian' },
        { color: '#9B6B43', label: 'Arab' },
        { color: '#B87A4F', label: 'Iranian' },
        { color: '#C48254', label: 'Turkic' },
        { color: '#6B8E3A', label: 'Sub-Saharan African' },
        { color: '#B58A5C', label: 'Latino/Mestizo' },
        { color: '#A07048', label: 'Indigenous' },
        { color: '#5C8EA0', label: 'Pacific Islander' },
      ],
    },
    'users-round'
  );

  // ============================================================
  // HISTORICAL / TIME-AWARE MAPMODES — read window.__CURRENT_YEAR__
  // ============================================================

  // Helper: nearest sample at-or-before y for a series of [year, value, ...]
  function _nearestAtOrBefore(series, year) {
    if (!series || !series.length) return null;
    let chosen = null;
    for (const row of series) {
      if (row[0] <= year) chosen = row;
      else break;
    }
    return chosen;
  }

  // Maddison historical GDP per capita (year 1 → 2018)
  window.Mapmode.register(
    'gdp_pc_history',
    'GDP/capita (history)',
    (iso3) => {
      const md = window.Mapmode.getDataCache('maddison_history');
      if (!md || !md.countries) return null;
      const year = window.__CURRENT_YEAR__;
      // Look up by iso3 (entries are entity-name keyed but each row carries iso3)
      let bucket = null;
      for (const ent in md.countries) {
        if (md.countries[ent].iso3 === iso3) { bucket = md.countries[ent]; break; }
      }
      if (!bucket) return null;
      const row = _nearestAtOrBefore(bucket.series, year);
      if (!row || row[1] == null) return null;
      // 2011 int$. Log-normalise: $200 → 0, $80,000 → 1
      const v = row[1];
      const t = Math.max(0, Math.min(1, (Math.log10(Math.max(1, v)) - 2.3) / 2.6));
      return sampleRamp('good', t);
    },
    { title: 'GDP per capita (Maddison)', ramp: 'good', min: '$200 / $5k pre-1700', max: '$80k+ modern', semantic: 'good' },
    'coins',
    { timeAware: true, years: [1, 2018] }
  );

  // HYDE long-run population (10,000 BC → today)
  window.Mapmode.register(
    'population_history',
    'Population (history)',
    (iso3) => {
      const hp = window.Mapmode.getDataCache('hyde_population');
      if (!hp || !hp.countries) return null;
      const year = window.__CURRENT_YEAR__;
      const bucket = hp.countries[iso3];
      if (!bucket) return null;
      const row = _nearestAtOrBefore(bucket.series, year);
      if (!row || row[1] == null) return null;
      const v = row[1];
      // Log-normalise: 100 → 0, 1.5B → 1
      const t = Math.max(0, Math.min(1, (Math.log10(Math.max(1, v)) - 2) / 7.2));
      return sampleRamp('neutral', t);
    },
    { title: 'Population (HYDE 3.3 + UN)', ramp: 'neutral', min: '<10k', max: '>1B', semantic: 'neutral' },
    'users-2',
    { timeAware: true, years: [-10000, 2023] }
  );

  // 17) Pulse composite (apocalypse radar) — BAD (high score = trouble)
  window.Mapmode.register(
    'pulse',
    'Pulse (apocalypse radar)',
    (iso3) => {
      const p = window.Mapmode.getDataCache('pulse_mode');
      const c = p?.countries?.[iso3];
      if (!c) return null;
      return sampleRamp('bad', (c.composite || 0) / 100);
    },
    { title: 'Pulse composite', ramp: 'bad', min: 'Fine (good)', max: 'Alarming (bad)', semantic: 'bad' },
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
    ensureCache('country_culture'),
    ensureCache('maddison_history'),
    ensureCache('hyde_population'),
    ensureCache('paleo_temperature'),
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
