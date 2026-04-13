// War hotspots — compute per-country war severity from UCDP GED + GDACS
// and populate window.MAPMODE_WAR_HOTSPOTS. mapmode.js reads this every
// frame to paint pulsing red outlines on affected countries.
(function(){
  async function refresh() {
    const out = {};
    // UCDP last-30-day fatality aggregation
    try {
      const r = await (window.fetchCache ? window.fetchCache('ucdp_ged') : fetch('/api/cache/ucdp_ged.json').then(r => r.json()));
      if (r && r.events) {
        const cutoff = new Date(Date.now() - 30 * 86400 * 1000).toISOString().slice(0, 10);
        const byCountry = {};
        for (const ev of r.events) {
          if ((ev.date_start || '') < cutoff) continue;
          const name = (ev.country || '').trim();
          if (!name) continue;
          byCountry[name] = (byCountry[name] || 0) + (ev.best || 0);
        }
        // Map country name → iso3 via country_relations or country_polygons
        const poly = window.Mapmode && window.Mapmode.polygonsByIso3 ? window.Mapmode.polygonsByIso3() : {};
        for (const [name, fatalities] of Object.entries(byCountry)) {
          let iso3 = null;
          for (const [k, v] of Object.entries(poly)) {
            if ((v.name || '').toLowerCase() === name.toLowerCase() ||
                (v.admin || '').toLowerCase() === name.toLowerCase()) {
              iso3 = k; break;
            }
          }
          if (iso3) {
            // Severity 1-5 from log fatalities
            let sev = 1;
            if (fatalities >= 500) sev = 5;
            else if (fatalities >= 100) sev = 4;
            else if (fatalities >= 30) sev = 3;
            else if (fatalities >= 5) sev = 2;
            out[iso3] = Math.max(out[iso3] || 0, sev);
          }
        }
      }
    } catch (e) { console.warn('[war-hotspots] ucdp', e); }

    // GDACS events — hazards with country matched to iso3
    try {
      const r = await (window.fetchCache ? window.fetchCache('gdacs_events') : fetch('/api/cache/gdacs_events.json').then(r => r.json()));
      if (r && r.events) {
        const poly = window.Mapmode && window.Mapmode.polygonsByIso3 ? window.Mapmode.polygonsByIso3() : {};
        for (const ev of r.events) {
          if (ev.severity < 3) continue;  // only orange/red
          const country = (ev.country || '').trim();
          if (!country) continue;
          for (const [k, v] of Object.entries(poly)) {
            if ((v.name || '').toLowerCase() === country.toLowerCase()) {
              out[k] = Math.max(out[k] || 0, ev.severity);
              break;
            }
          }
        }
      }
    } catch (e) { console.warn('[war-hotspots] gdacs', e); }

    window.MAPMODE_WAR_HOTSPOTS = out;
    console.log('[war-hotspots] flagged', Object.keys(out).length, 'countries');
  }

  // Initial + every 5 min
  setTimeout(refresh, 6000);
  setInterval(refresh, 300000);
  window.refreshWarHotspots = refresh;
})();
