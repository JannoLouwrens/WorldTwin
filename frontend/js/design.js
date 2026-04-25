// Design tokens (JS mirror of :root CSS vars) + ramps + size/width formulas
// + category colours + motion helpers.
(function(){
  const DS = {
    // Mode hues
    modeHue: {
      world: '#4cc2ff',
      weather: '#7ad7ff',
      nature: '#ff8c2a',
      war: '#ef3b3b',
      economy: '#f4c84a',
      resources: '#9aa5b1',
      gaming: '#a76bff',
      sports: '#ffd23f',
      social: '#34d399',
      space: '#7c8cff',
    },

    // Commodity category colours (Okabe-Ito aligned with commodities taxonomy)
    categoryHue: {
      energy:       '#E69F00',
      agri:         '#009E73',
      metals:       '#D55E00',
      tech:         '#0072B2',
      chemicals:    '#CC79A7',
      manufactures: '#56B4E9',
      textiles:     '#F0E442',
      other:        '#999999',
    },

    // Fuel colours
    fuelHue: {
      coal:       '#3b3b3b',
      gas:        '#56B4E9',
      oil:        '#2a2a2a',
      nuclear:    '#5eead4',
      hydro:      '#3b82f6',
      solar:      '#fbbf24',
      wind:       '#a5f3fc',
      geothermal: '#f97316',
      biomass:    '#84cc16',
      tidal:      '#14b8a6',
      storage:    '#64748b',
      other:      '#6b7790',
    },

    // Continuous ramps — each is [stops]
    // SEMANTIC RAMPS (use these for metrics where value = good/bad):
    //   bad  — HIGH = BAD (inflation, debt, CO2, water stress, pulse…)
    //   good — HIGH = GOOD (life exp, GDP pc, internet %, renewable %…)
    // NEUTRAL RAMPS (for raw size/intensity, no value judgment):
    //   neutral — generic low→high (population, GDP total)
    //   density — viridis-like for density
    //   altitude, depth, recency — domain-specific
    ramps: {
      // good → bad: green → yellow → orange → red
      bad:  ['#15803d','#84cc16','#fde047','#fb923c','#ef4444','#b91c1c'],
      // bad → good: red → orange → yellow → green (reverse of bad)
      good: ['#b91c1c','#ef4444','#fb923c','#fde047','#84cc16','#15803d'],
      // Neutral sequential (teal → deep blue), no good/bad meaning
      neutral: ['#cffafe','#67e8f9','#06b6d4','#0e7490','#1e3a8a'],

      // Legacy names kept for renderers that already reference them
      heat: ['#1e3a8a','#2563eb','#06b6d4','#84cc16','#fde047','#fb923c','#ef4444'],
      fire: ['#fff7b8','#fde047','#fb923c','#ef4444','#b91c1c','#4a0e0e'],
      coldHot: ['#1e40af','#4cc2ff','#f8fafc','#fb923c','#b91c1c'],
      density: ['#440154','#3b528b','#21908d','#5dc863','#fde725'],
      altitude: ['#ffffff','#fde047','#34d399','#4cc2ff','#2563eb','#a76bff'],
      depth: ['#fde047','#fb923c','#ef4444','#7c2d12','#1e1b4b'],
      recency: ['#7f1d1d','#ef4444','#fb923c','#fde047','#fef3c7'],
    },

    // ==== size / width formulas ====

    // Point radius (px) — sqrt scale
    pointRadius(value, median, min=2, max=22) {
      if (!value || value <= 0) return min;
      const k = Math.sqrt(value / Math.max(1, median || value));
      return Math.min(max, Math.max(min, 4 + 6 * k));
    },

    // Arc / line width (px) — log scale (values often span 10^0-10^4 orders)
    arcWidth(value, min=0.6, max=8) {
      if (!value || value <= 0) return min;
      const w = Math.log10(1 + value) * 1.6;
      return Math.min(max, Math.max(min, w));
    },

    // Normalise 0-1 from value in range
    norm(value, lo, hi) {
      if (hi <= lo) return 0;
      return Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    },

    // Sample a ramp at t in [0,1]
    sampleRamp(ramp, t) {
      const stops = Array.isArray(ramp) ? ramp : this.ramps[ramp];
      if (!stops || stops.length === 0) return '#ffffff';
      t = Math.max(0, Math.min(1, t));
      const i = t * (stops.length - 1);
      const lo = Math.floor(i);
      const hi = Math.ceil(i);
      if (lo === hi) return stops[lo];
      return this.mixHex(stops[lo], stops[hi], i - lo);
    },

    mixHex(a, b, t) {
      const pa = DS._hex(a), pb = DS._hex(b);
      const r = Math.round(pa[0] + (pb[0] - pa[0]) * t);
      const g = Math.round(pa[1] + (pb[1] - pa[1]) * t);
      const bl = Math.round(pa[2] + (pb[2] - pa[2]) * t);
      return '#' + [r,g,bl].map(x => x.toString(16).padStart(2,'0')).join('');
    },
    _hex(h) {
      h = h.replace('#','');
      return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
    },

    // Cesium Color convenience
    c(hex, alpha=1) {
      return Cesium.Color.fromCssColorString(hex).withAlpha(alpha);
    },

    // Human-readable number format. precision controls decimals on the SI suffix.
    // For precision=0 on a 4-digit integer like 4034, return "4034" not "4" — i.e. don't suffix under 1000.
    fmt(n, precision=1) {
      if (n === null || n === undefined) return '—';
      const abs = Math.abs(n);
      if (abs >= 1e12) return (n/1e12).toFixed(Math.max(1,precision)) + 'T';
      if (abs >= 1e9)  return (n/1e9).toFixed(Math.max(1,precision)) + 'B';
      if (abs >= 1e6)  return (n/1e6).toFixed(Math.max(1,precision)) + 'M';
      if (abs >= 1e4)  return (n/1e3).toFixed(Math.max(0,precision)) + 'k';  // 10k+
      // Under 10 000 — show raw integer
      return Math.round(n).toLocaleString();
    },

    fmtUSD(n) { return '$' + this.fmt(n); },

    fmtRelTime(iso) {
      if (!iso) return '—';
      const d = new Date(iso).getTime();
      const s = (Date.now() - d) / 1000;
      if (s < 60) return Math.round(s) + 's ago';
      if (s < 3600) return Math.round(s/60) + 'm ago';
      if (s < 86400) return Math.round(s/3600) + 'h ago';
      return Math.round(s/86400) + 'd ago';
    },
  };

  window.DS = DS;
})();
