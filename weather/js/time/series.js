// time/series.js — interpolate a sparse historical series at the current Clock year.
//
// Most paleo / historical series have unevenly-spaced samples (CO2 ice cores
// at -800,000, -799,500, -798,000... vs Mauna Loa monthly since 1958). For
// rendering a number "now" on the scrubber we don't need Cesium's full
// SampledProperty — we just need monotonic-year nearest / linear lookup.
//
// API:
//   const s = new HistoricalSeries(samples);
//      samples = [[year, value], ...]  (will be sorted; non-finite values dropped)
//   s.at(year)          → interpolated value (linear between neighbours; null if out of range)
//   s.nearest(year)     → nearest sample value (for non-numeric, e.g. category labels)
//   s.range()           → [minYear, maxYear]
//   s.coverage(ya, yb)  → fraction of [ya,yb] window covered by samples
//
// Optional 2nd arg `opts`:
//   { extrapolate: false }           → return null outside [min,max] (default true: clamps to nearest)
//   { interp: 'linear' | 'step' }    → 'step' returns the most-recent sample at-or-before y
(function(){
  function HistoricalSeries(samples, opts) {
    opts = opts || {};
    const extrapolate = opts.extrapolate !== false;
    const interp = opts.interp || 'linear';
    const cleaned = (samples || [])
      .filter(s => s && Number.isFinite(s[0]) && Number.isFinite(s[1]))
      .map(s => [s[0], s[1]])
      .sort((a, b) => a[0] - b[0]);
    const ys = cleaned.map(s => s[0]);

    function _bsearch(year) {
      // Returns index of first sample with year >= y, or cleaned.length if none.
      let lo = 0, hi = ys.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (ys[mid] < year) lo = mid + 1; else hi = mid;
      }
      return lo;
    }

    this.at = function(year) {
      if (cleaned.length === 0) return null;
      if (year <= ys[0])              return extrapolate ? cleaned[0][1] : null;
      if (year >= ys[ys.length - 1])  return extrapolate ? cleaned[cleaned.length - 1][1] : null;
      const i = _bsearch(year);
      if (interp === 'step') {
        // Most-recent sample at-or-before y
        return cleaned[Math.max(0, i - 1)][1];
      }
      // Linear between [i-1, i]
      const [y0, v0] = cleaned[i - 1];
      const [y1, v1] = cleaned[i];
      if (y1 === y0) return v0;
      const t = (year - y0) / (y1 - y0);
      return v0 + t * (v1 - v0);
    };

    this.nearest = function(year) {
      if (cleaned.length === 0) return null;
      const i = _bsearch(year);
      if (i === 0) return cleaned[0][1];
      if (i === cleaned.length) return cleaned[i - 1][1];
      const [y0, v0] = cleaned[i - 1];
      const [y1, v1] = cleaned[i];
      return (year - y0) <= (y1 - year) ? v0 : v1;
    };

    this.range = function() {
      if (cleaned.length === 0) return [NaN, NaN];
      return [ys[0], ys[ys.length - 1]];
    };

    this.coverage = function(ya, yb) {
      if (cleaned.length === 0 || ya >= yb) return 0;
      const lo = Math.max(ya, ys[0]);
      const hi = Math.min(yb, ys[ys.length - 1]);
      if (hi <= lo) return 0;
      return (hi - lo) / (yb - ya);
    };

    this.size = function() { return cleaned.length; };
  }

  window.HistoricalSeries = HistoricalSeries;
})();
