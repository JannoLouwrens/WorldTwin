// concept-map.js — single source of truth for "this conceptual value lives in
// these N caches; here's how to compare them."
//
// Vision: A lab where anyone — from the king of Rome to a sceptical citizen —
// can read the world from raw, dated, cross-checked sources instead of someone
// else's framing, and trace every claim back to the instrument that measured it.
//
// When the Data Inspector opens a claim, it asks this map "what concept is
// this?" If the path matches a concept, the Inspector shows every alternative
// source side-by-side with a green (agree), yellow (close), or red (diverge)
// badge so the user can SEE multi-source confirmation or disagreement.
//
// Each concept has:
//   - id           : stable identifier (snake_case)
//   - label        : human-readable
//   - unit         : "$/bbl", "ppm", "%", "events", etc.
//   - tolerance    : { abs?, pct? } — values within these bounds are GREEN.
//                    Within 2x tolerance is YELLOW. Beyond is RED.
//   - sources[]    : { name, cache, path, transform? }
//                    `path` is dot/bracket-notation against the cache root
//                    `transform` (optional) is a function name to apply
//                    (e.g. "first_of_array" for the first sample, or
//                     "external_api" to fetch live from a URL each open)
//   - external[]   : array of live-fetch URLs (Binance, CoinGecko, NOAA CSV
//                    etc.) for true triangulation against authoritative sources
(function(){

  const CONCEPTS = [
    {
      id: 'btc_usd',
      label: 'Bitcoin price (USD)',
      unit: '$',
      tolerance: { pct: 1.0 },
      sources: [
        { name: 'CoinGecko (cached)', cache: 'economy', path: 'crypto[?symbol=btc].price_usd' },
      ],
      external: [
        { name: 'Binance ticker24h',
          url: 'https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT',
          extract: 'lastPrice' },
        { name: 'CoinGecko (live)',
          url: 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd',
          extract: 'bitcoin.usd' },
      ],
    },
    {
      id: 'brent_crude_usd_bbl',
      label: 'Brent crude (USD/bbl)',
      unit: '$/bbl',
      tolerance: { pct: 2.0 },
      sources: [
        { name: 'FRED (cached)', cache: 'fred', path: 'series.DCOILBRENTEU.latest' },
      ],
      external: [],   // EIA + ICE require keys; left empty for now
    },
    {
      id: 'wti_crude_usd_bbl',
      label: 'WTI crude (USD/bbl)',
      unit: '$/bbl',
      tolerance: { pct: 2.0 },
      sources: [
        { name: 'FRED (cached)', cache: 'fred', path: 'series.DCOILWTICO.latest' },
      ],
      external: [],
    },
    {
      id: 'us_10y_yield_pct',
      label: 'US 10Y Treasury yield (%)',
      unit: '%',
      tolerance: { abs: 0.05 },
      sources: [
        { name: 'FRED (cached)', cache: 'fred', path: 'series.DGS10.latest' },
      ],
      external: [],
    },
    {
      id: 'vix',
      label: 'VIX volatility index',
      unit: '',
      tolerance: { pct: 2.0 },
      sources: [
        { name: 'FRED (cached)', cache: 'fred', path: 'series.VIXCLS.latest' },
      ],
      external: [],
    },
    {
      id: 'co2_ppm_global',
      label: 'Atmospheric CO₂ (ppm)',
      unit: 'ppm',
      tolerance: { abs: 0.5 },
      sources: [
        { name: 'NOAA Mauna Loa (cached)', cache: 'noaa_co2', path: 'headline.current_co2_ppm' },
      ],
      external: [
        { name: 'NOAA Mauna Loa daily CSV',
          url: 'https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_daily_mlo.csv',
          extract: 'csv_last_co2' },
      ],
    },
    {
      id: 'temp_anomaly_c',
      label: 'Global temperature anomaly (°C vs 1961-1990)',
      unit: '°C',
      tolerance: { abs: 0.05 },
      sources: [
        { name: 'HadCRUT5 + Marcott + PAGES2k (cached)', cache: 'paleo_temperature', path: 'headline.current_anomaly_c' },
      ],
      external: [],
    },
    {
      id: 'hormuz_ships_today',
      label: 'Strait of Hormuz vessel count today',
      unit: 'ships',
      tolerance: { abs: 10 },
      sources: [
        { name: 'PortWatch IMF (cached)', cache: 'portwatch_chokepoints', path: 'chokepoints[?name~hormuz].n_total' },
      ],
      external: [],
    },
    {
      id: 'usgs_quakes_24h',
      label: 'USGS earthquakes M4.5+ past 24h',
      unit: 'events',
      tolerance: { abs: 3 },
      sources: [
        { name: 'USGS (cached, M2.5+ filtered to ≥4.5)', cache: 'quakes', path: 'features|>=4.5_count' },
      ],
      external: [
        { name: 'USGS feed M4.5+ live',
          url: 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson',
          extract: 'features.length' },
      ],
    },
    // Inflation — multi-country, the "global south" view.
    // Each adds an IMF WEO source. Some have CB-published rates that could
    // serve as a future cross-check (left external blank for now since most
    // require keys or scraping).
    ...[
      ['IRN', 'Iran'],          ['ARG', 'Argentina'],   ['TUR', 'Türkiye'],
      ['VEN', 'Venezuela'],     ['EGY', 'Egypt'],       ['PAK', 'Pakistan'],
      ['NGA', 'Nigeria'],       ['ZAF', 'South Africa'],['BRA', 'Brazil'],
      ['IND', 'India'],         ['CHN', 'China'],       ['DEU', 'Germany'],
      ['GBR', 'United Kingdom'],
    ].map(([iso, name]) => ({
      id: `${iso.toLowerCase()}_inflation_pct`,
      label: `${name} inflation (% per IMF WEO)`,
      unit: '%',
      tolerance: { abs: 1.0 },
      sources: [
        { name: 'IMF WEO (cached)', cache: 'imf_data', path: `countries.${iso}.PCPIPCH.value` },
      ],
      external: [],
    })),

    // Sovereign 10Y yields — major economies, FRED-fed
    ...[
      ['DGS10',     'United States 10Y yield (%)'],
      ['IRLTLT01DEM156N', 'Germany 10Y yield (%)'],
      ['IRLTLT01JPM156N', 'Japan 10Y yield (%)'],
      ['IRLTLT01GBM156N', 'United Kingdom 10Y yield (%)'],
    ].map(([series, label]) => ({
      id: `${series.toLowerCase()}_yield`,
      label,
      unit: '%',
      tolerance: { abs: 0.05 },
      sources: [
        { name: 'FRED (cached)', cache: 'fred', path: `series.${series}.latest` },
      ],
      external: [],
    })),

    // Global commodities — the markets that move emerging economies
    {
      id: 'copper_usd_t',
      label: 'Copper price (USD/tonne)',
      unit: '$/t',
      tolerance: { pct: 2.0 },
      sources: [{ name: 'FRED (cached)', cache: 'fred', path: 'series.PCOPPUSDM.latest' }],
      external: [],
    },
    {
      id: 'wheat_usd_t',
      label: 'Wheat price (USD/tonne)',
      unit: '$/t',
      tolerance: { pct: 2.0 },
      sources: [{ name: 'FRED (cached)', cache: 'fred', path: 'series.PWHEAMTUSDM.latest' }],
      external: [],
    },
    {
      id: 'natgas_usd',
      label: 'Henry Hub natural gas (USD/MMBtu)',
      unit: '$/MMBtu',
      tolerance: { pct: 2.0 },
      sources: [{ name: 'FRED (cached)', cache: 'fred', path: 'series.DHHNGSP.latest' }],
      external: [],
    },

    // FX rates — the trade-weighted USD already covered, add a few key pairs
    {
      id: 'cny_usd',
      label: 'CNY/USD exchange rate',
      unit: 'CNY/USD',
      tolerance: { pct: 0.5 },
      sources: [{ name: 'FRED (cached)', cache: 'fred', path: 'series.DEXCHUS.latest' }],
      external: [],
    },
    {
      id: 'eur_usd',
      label: 'EUR/USD exchange rate',
      unit: 'EUR/USD',
      tolerance: { pct: 0.5 },
      sources: [{ name: 'FRED (cached)', cache: 'fred', path: 'series.DEXUSEU.latest' }],
      external: [],
    },

    // Other major chokepoints (Hormuz already covered)
    ...[
      ['suez',    'Suez Canal'],
      ['malacca', 'Malacca Strait'],
      ['panama',  'Panama Canal'],
      ['bab',     'Bab el-Mandeb'],
    ].map(([key, label]) => ({
      id: `${key}_ships_today`,
      label: `${label} vessel count today`,
      unit: 'ships',
      tolerance: { abs: 10 },
      sources: [
        { name: 'PortWatch IMF (cached)', cache: 'portwatch_chokepoints', path: `chokepoints[?name~${key}].n_total` },
      ],
      external: [],
    })),
  ];

  // ---- Path resolver — supports JSON pointer + array predicates ----
  // Examples:
  //   "series.DCOILBRENTEU.latest"               → straight nested key
  //   "crypto[?symbol=btc].price_usd"            → array predicate
  //   "chokepoints[?name~hormuz].n_total"        → ~  = case-insensitive substring
  //   "features|>=4.5_count"                     → custom: count features w mag>=4.5
  function resolvePath(root, path) {
    if (!root || !path) return undefined;
    // Custom: "features|>=4.5_count"
    if (path === 'features|>=4.5_count') {
      const f = (root.features || []).filter(x => (x?.properties?.mag ?? 0) >= 4.5);
      return f.length;
    }
    let cur = root;
    const parts = path.split(/(?=[.\[])/);   // split keeping delimiters
    for (let p of parts) {
      if (cur == null) return undefined;
      if (p.startsWith('.')) p = p.slice(1);
      if (p.startsWith('[?')) {
        // array predicate — [?key=value] or [?key~substring]
        const m = p.match(/^\[\?(\w+)([=~])([^\]]+)\]$/);
        if (!m || !Array.isArray(cur)) return undefined;
        const [, k, op, raw] = m;
        const v = raw.toLowerCase();
        cur = cur.find(item => {
          const iv = String(item?.[k] ?? '').toLowerCase();
          return op === '=' ? iv === v : iv.includes(v);
        });
      } else {
        cur = cur[p];
      }
    }
    return cur;
  }

  // Find concept by examining the inspector's path string against every concept's source paths
  function findConcept(cacheName, path) {
    if (!cacheName || !path) return null;
    return CONCEPTS.find(c =>
      c.sources.some(s => s.cache === cacheName && pathsMatch(s.path, path))
    ) || null;
  }
  function pathsMatch(conceptPath, openedPath) {
    // Simple substring match — Inspector path is like "series.DCOILBRENTEU.latest"
    // and concept's path is identical OR a parent. Good enough for the v1.
    return conceptPath === openedPath
        || conceptPath.startsWith(openedPath + '.')
        || openedPath.startsWith(conceptPath);
  }

  // Compare two numeric values per a tolerance spec, return tier
  function tierFor(a, b, tolerance) {
    if (a == null || b == null) return 'unknown';
    const diff = Math.abs(a - b);
    const denom = Math.max(Math.abs(a), Math.abs(b), 1);
    const pct = diff / denom * 100;
    let limit = null;
    if (tolerance?.abs != null) limit = tolerance.abs;
    if (tolerance?.pct != null) limit = (denom * tolerance.pct / 100);
    if (limit == null) limit = denom * 0.02;   // default 2%
    if (diff <= limit)            return 'green';
    if (diff <= limit * 2)        return 'yellow';
    return 'red';
  }

  window.ConceptMap = {
    CONCEPTS, findConcept, resolvePath, tierFor,
  };
})();
