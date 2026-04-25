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
  // Time-aware lookup helpers
  // ============================================================
  // World Bank cache shape (post-2026-04-25 refactor):
  //   countries[iso3][indicator] = { year, value, latest:{year,value}, history:{year_str:value} }
  //
  // wbValue(iso3, code) returns the right value for the current scrubber year:
  //   - At Live: latest.value (current accuracy)
  //   - Historical scrubbed: nearest sample at-or-before year, from history{}
  //   - No data for that year: null (country renders grey, honest)
  function wbValue(iso3, code) {
    const wb = window.Mapmode.getDataCache('world_bank');
    const entry = wb?.countries?.[iso3]?.[code];
    if (!entry) return null;
    const year = window.__CURRENT_YEAR__;
    const isLive = window.Clock && year === window.Clock.MAX_YEAR;
    if (isLive || !entry.history) {
      return (entry.latest || entry).value ?? null;
    }
    // Historical: find nearest year <= scrubber year
    let chosen = null;
    for (const yStr of Object.keys(entry.history)) {
      const y = parseInt(yStr, 10);
      if (y <= year && (chosen === null || y > chosen)) chosen = y;
    }
    return chosen != null ? entry.history[String(chosen)] : null;
  }

  // IMF parallel — same shape (post-refactor)
  function imfValue(iso3, code) {
    const imf = window.Mapmode.getDataCache('imf_data');
    const entry = imf?.countries?.[iso3]?.[code];
    if (!entry) return null;
    const year = window.__CURRENT_YEAR__;
    const isLive = window.Clock && year === window.Clock.MAX_YEAR;
    if (isLive || !entry.history) {
      return (entry.latest || entry).value ?? null;
    }
    let chosen = null;
    for (const yStr of Object.keys(entry.history)) {
      const y = parseInt(yStr, 10);
      if (y <= year && (chosen === null || y > chosen)) chosen = y;
    }
    return chosen != null ? entry.history[String(chosen)] : null;
  }

  // ============================================================
  // MAPMODES
  // ============================================================

  // 1) Political — coloured by primary bloc/alliance membership — TIME-AWARE
  // At Live: country_relations (NATO, EU, BRICS, AU, ...).
  // Scrubbed back: COW historical alliances (Triple Entente, Axis, Warsaw Pact, ...).
  window.Mapmode.register(
    'political',
    'Political blocs',
    (iso3) => {
      const year = window.__CURRENT_YEAR__;
      const isLive = window.Clock && year === window.Clock.MAX_YEAR;
      if (!isLive && year < 2009) {
        // Use COW historical alliance graph
        const cow = window.Mapmode.getDataCache('cow_alliances');
        const aid = cow?.by_country_year?.[iso3]?.[String(year)];
        if (aid && cow.alliances?.[aid]) return cow.alliances[aid].color;
        // If no historical alliance — fall back to "non-aligned" grey
        return '#2a3447';
      }
      // Modern (2009+ or Live) — use curated bloc colours
      const rel = window.Mapmode.getDataCache('country_relations');
      if (!rel) return '#6b7790';
      const r = (rel.by_country || {})[iso3];
      return r?.bloc_color || '#2a3447';
    },
    { title: 'Political blocs / alliances', ramp: 'heat', min: 'Non-aligned', max: 'Major bloc' },
    'users',
    { timeAware: true, years: [1815, 2026] }
  );

  // 1b) Democracy — GOOD — TIME-AWARE (V-Dem 1789→2025)
  // Score 0..1 from the Varieties of Democracy electoral-democracy index.
  // Pre-1900 values are scholarly reconstructions.
  window.Mapmode.register(
    'democracy',
    'Electoral democracy',
    (iso3) => {
      const v = window.Mapmode.getDataCache('vdem_democracy');
      const bucket = v?.countries?.[iso3];
      if (!bucket?.history) return null;
      const year = window.__CURRENT_YEAR__;
      let chosen = null;
      for (const yStr of Object.keys(bucket.history)) {
        const y = parseInt(yStr, 10);
        if (y <= year && (chosen === null || y > chosen)) chosen = y;
      }
      if (chosen === null) return null;
      return sampleRamp('good', bucket.history[String(chosen)]);
    },
    { title: 'Electoral democracy (V-Dem 0..1)', ramp: 'good', min: '0 (autocracy)', max: '1 (full democracy)', semantic: 'good' },
    'vote',
    { timeAware: true, years: [1789, 2025] }
  );

  // 2) GDP (current USD) — NEUTRAL — TIME-AWARE (WB 1960-now)
  window.Mapmode.register(
    'gdp',
    'GDP (USD)',
    (iso3) => {
      const v = wbValue(iso3, 'NY.GDP.MKTP.CD');
      if (v == null) return null;
      return sampleRamp('neutral', logNorm(v, 8, 13.5));
    },
    { title: 'GDP (current USD)', ramp: 'neutral', min: '$100M', max: '$25T', semantic: 'neutral' },
    'trending-up',
    { timeAware: true, years: [1960, 2024] }
  );

  // ============================================================
  // Helper: nearest sample at-or-before y for a [year, value, ...] series
  // ============================================================
  function _nearestAtOrBefore(series, year) {
    if (!series || !series.length) return null;
    let chosen = null;
    for (const row of series) {
      if (row[0] <= year) chosen = row;
      else break;
    }
    return chosen;
  }

  // 3) Population — NEUTRAL — TIME-AWARE
  // Live (or post-2023): World Bank 'SP.POP.TOTL' (latest, accurate to today).
  // Historical (year < 2023): HYDE 3.3 series (10,000 BC → 2023).
  window.Mapmode.register(
    'population',
    'Population',
    (iso3) => {
      const year = window.__CURRENT_YEAR__;
      const useHistorical = year < 2023;
      let v = null;
      if (useHistorical) {
        const hp = window.Mapmode.getDataCache('hyde_population');
        const bucket = hp?.countries?.[iso3];
        const row = bucket && _nearestAtOrBefore(bucket.series, year);
        if (row && row[1] != null) v = row[1];
      } else {
        const wb = window.Mapmode.getDataCache('world_bank');
        v = (wb?.countries?.[iso3]?.['SP.POP.TOTL'] || {}).value;
      }
      if (v == null) return null;
      return sampleRamp('neutral', logNorm(v, 2, 9.2));
    },
    { title: 'Population', ramp: 'neutral', min: '<1k', max: '1.5B', semantic: 'neutral' },
    'users-2',
    { timeAware: true, years: [-10000, 2024] }
  );

  // 4) GDP per capita — GOOD — TIME-AWARE
  // Live (or post-2018): World Bank 'NY.GDP.PCAP.CD' (current USD).
  // Historical (year < 2018): Maddison Project 2020 (2011 int$, 1 AD → 2018).
  window.Mapmode.register(
    'gdp_pc',
    'GDP per capita',
    (iso3) => {
      const year = window.__CURRENT_YEAR__;
      const useHistorical = year < 2018;
      let v = null;
      if (useHistorical) {
        const md = window.Mapmode.getDataCache('maddison_history');
        if (md?.countries) {
          for (const ent in md.countries) {
            if (md.countries[ent].iso3 === iso3) {
              const row = _nearestAtOrBefore(md.countries[ent].series, year);
              if (row && row[1] != null) v = row[1];
              break;
            }
          }
        }
      } else {
        const wb = window.Mapmode.getDataCache('world_bank');
        v = (wb?.countries?.[iso3]?.['NY.GDP.PCAP.CD'] || {}).value;
      }
      if (v == null) return null;
      return sampleRamp('good', Math.max(0, Math.min(1, (Math.log10(Math.max(1, v)) - 2.3) / 2.8)));
    },
    { title: 'GDP per capita (USD/2011 int$)', ramp: 'good', min: '$200 (poor)', max: '$120k (rich)', semantic: 'good' },
    'coins',
    { timeAware: true, years: [1, 2024] }
  );

  // 5) Inflation — BAD — TIME-AWARE (IMF history 1980-now; pre-1980 → grey)
  window.Mapmode.register(
    'inflation',
    'Inflation',
    (iso3) => {
      const v = imfValue(iso3, 'PCPIPCH');
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 15)));
    },
    { title: 'Inflation % (IMF)', ramp: 'bad', min: '0% (stable)', max: '15%+ (high)', semantic: 'bad' },
    'percent',
    { timeAware: true, years: [1980, 2030] }
  );

  // 6) Military spend % GDP — BAD — TIME-AWARE (WB 1960-now)
  window.Mapmode.register(
    'military',
    'Military spend % GDP',
    (iso3) => {
      const v = wbValue(iso3, 'MS.MIL.XPND.GD.ZS');
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 10)));
    },
    { title: 'Military spend % GDP', ramp: 'bad', min: '0% (low)', max: '10%+ (high)', semantic: 'bad' },
    'swords',
    { timeAware: true, years: [1960, 2024] }
  );

  // 7) Water stress — BAD (single snapshot; no historical Aqueduct series)
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

  // 8) Food security — BAD (IPC current snapshot only; no historical series)
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

  // 9) CO2 per capita — BAD — TIME-AWARE (WB 1960-now)
  window.Mapmode.register(
    'co2',
    'CO2 per capita',
    (iso3) => {
      const v = wbValue(iso3, 'EN.GHG.CO2.PC.CE.AR5');
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 25)));
    },
    { title: 'CO2 per capita (tonnes)', ramp: 'bad', min: '0 (clean)', max: '25+ (dirty)', semantic: 'bad' },
    'factory',
    { timeAware: true, years: [1960, 2024] }
  );

  // 10) Renewable share of electricity — GOOD — TIME-AWARE (OWID 1985-now)
  // OWID Energy now stores history[] per country. At Live: latest snapshot;
  // scrubbed: nearest year sample.
  window.Mapmode.register(
    'renewable',
    'Renewable electricity %',
    (iso3) => {
      const owid = window.Mapmode.getDataCache('owid_energy');
      const year = window.__CURRENT_YEAR__;
      const isLive = window.Clock && year === window.Clock.MAX_YEAR;
      let v = null;
      if (isLive) {
        v = owid?.countries?.[iso3]?.renewables_share_elec;
      } else {
        const series = owid?.history?.[iso3] || [];
        let chosen = null;
        for (const row of series) {
          if ((row.year || 0) <= year) chosen = row; else break;
        }
        v = chosen?.renewables_share_elec ?? null;
      }
      if (v == null) return null;
      return sampleRamp('good', v / 100);
    },
    { title: 'Renewable electricity %', ramp: 'good', min: '0% (fossil)', max: '100% (green)', semantic: 'good' },
    'zap',
    { timeAware: true, years: [1985, 2024] }
  );

  // 11) Internet users — GOOD — TIME-AWARE (WB 1960-now; usually 1990+ has data)
  window.Mapmode.register(
    'internet',
    'Internet penetration',
    (iso3) => {
      const v = wbValue(iso3, 'IT.NET.USER.ZS');
      if (v == null) return null;
      return sampleRamp('good', v / 100);
    },
    { title: 'Internet users %', ramp: 'good', min: '0% (offline)', max: '100% (online)', semantic: 'good' },
    'globe-2',
    { timeAware: true, years: [1990, 2024] }
  );

  // 12) Life expectancy — GOOD — TIME-AWARE
  // World Bank covers 1960-now (high accuracy). Clio-Infra/Riley extend
  // back to 1770 with reconstruction-quality values.
  window.Mapmode.register(
    'life',
    'Life expectancy',
    (iso3) => {
      const year = window.__CURRENT_YEAR__;
      let v = wbValue(iso3, 'SP.DYN.LE00.IN');
      if (v == null) {
        // Fall back to Clio-Infra (1770-2023)
        const clio = window.Mapmode.getDataCache('clio_life_expectancy');
        const bucket = clio?.countries?.[iso3];
        if (bucket?.history) {
          let chosen = null;
          for (const yStr of Object.keys(bucket.history)) {
            const y = parseInt(yStr, 10);
            if (y <= year && (chosen === null || y > chosen)) chosen = y;
          }
          if (chosen != null) v = bucket.history[String(chosen)];
        }
      }
      if (v == null) return null;
      return sampleRamp('good', Math.max(0, Math.min(1, (v - 25) / 60)));
    },
    { title: 'Life expectancy (years)', ramp: 'good', min: '25 (pre-modern)', max: '85 (modern)', semantic: 'good' },
    'heart',
    { timeAware: true, years: [1770, 2024] }
  );

  // 13) Urban population % — NEUTRAL — TIME-AWARE (WB 1960-now)
  window.Mapmode.register(
    'urban',
    'Urban population %',
    (iso3) => {
      const v = wbValue(iso3, 'SP.URB.TOTL.IN.ZS');
      if (v == null) return null;
      return sampleRamp('neutral', v / 100);
    },
    { title: 'Urban %', ramp: 'neutral', min: '0% (rural)', max: '100% (urban)', semantic: 'neutral' },
    'building-2',
    { timeAware: true, years: [1960, 2024] }
  );

  // 14) Debt % GDP — BAD — TIME-AWARE (WB 1960-now)
  window.Mapmode.register(
    'debt',
    'Gov debt % GDP',
    (iso3) => {
      const v = wbValue(iso3, 'GC.DOD.TOTL.GD.ZS');
      if (v == null) return null;
      return sampleRamp('bad', Math.max(0, Math.min(1, v / 200)));
    },
    { title: 'Gov debt % GDP', ramp: 'bad', min: '0% (low)', max: '200%+ (high)', semantic: 'bad' },
    'landmark',
    { timeAware: true, years: [1960, 2024] }
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

  // NOTE: 'gdp_pc_history' and 'population_history' mapmodes were removed
  // 2026-04-25 — they're now folded into the regular 'gdp_pc' and 'population'
  // mapmodes which auto-fall-back to Maddison/HYDE when the scrubber is in
  // historical years. One mapmode per concept, time-aware everywhere.

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
    // Historical (Phase 7 will lazy-load these — for now eager so dev iteration works)
    ensureCache('vdem_democracy'),
    ensureCache('brecke_wars'),
    ensureCache('clio_life_expectancy'),
    ensureCache('cow_alliances'),
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
