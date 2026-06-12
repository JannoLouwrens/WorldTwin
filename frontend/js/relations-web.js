// relations-web.js — the relationship reveal.
//
// WorldTwin shows nouns (dots: a fire here, a war there). Understanding lives
// in the EDGES between them. This module draws those edges: click a country
// and the globe lights up what it's connected to —
//   • gold arcs   → its biggest trade partners (who it feeds / buys from)
//   • green lines → its allies / bloc partners
//   • red lines   → its adversaries
// Data already exists in the caches (trade_annual flows w/ coords,
// country_relations allies/enemies, country_resources centroids). Nothing
// new is fetched — this just connects what was always there.
//
// Listens for the same dossier-open signal the click handler fires, so it
// reveals in lockstep with the country card. Esc / deselect clears it.
(function(){
  const GROUP = '_relweb';
  let _ents = [];
  let _activeIso = null;

  function clear() {
    const v = window.viewer;
    if (v) _ents.forEach(e => { try { v.entities.remove(e); } catch(_){} });
    _ents = [];
    _activeIso = null;
  }

  function centroid(iso3) {
    const res = window._cacheStore?.get('country_resources');
    const c = res?.countries?.[iso3];
    if (c && c.lat != null && c.lon != null) return [c.lon, c.lat];
    // fallback: mapmode polygon label point
    const polys = window.Mapmode?.polygonsByIso3?.() || {};
    const p = polys[iso3];
    if (p && p.label_x != null) return [p.label_x, p.label_y];
    return null;
  }

  // A great-circle arc that bows UP off the surface so trade routes read as
  // flight paths, not scribbles on the ground. Height scales with distance.
  function arcPositions(from, to) {
    const [lon1, lat1] = from, [lon2, lat2] = to;
    const dLon = Math.abs(lon1 - lon2), dLat = Math.abs(lat1 - lat2);
    const dist = Math.sqrt(dLon*dLon + dLat*dLat);
    const peak = Math.min(1.2e6, 1.5e5 + dist * 1.5e4); // metres above surface
    const steps = 32;
    const pos = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const lon = lon1 + (lon2 - lon1) * t;
      const lat = lat1 + (lat2 - lat1) * t;
      const h = Math.sin(t * Math.PI) * peak;       // 0 at ends, peak in middle
      pos.push(Cesium.Cartesian3.fromDegrees(lon, lat, h));
    }
    return pos;
  }

  function addArc(from, to, colorHex, width, glow) {
    const v = window.viewer;
    if (!v) return;
    const color = Cesium.Color.fromCssColorString(colorHex);
    const mat = glow
      ? new Cesium.PolylineGlowMaterialProperty({ color, glowPower: 0.25, taperPower: 0.6 })
      : new Cesium.ColorMaterialProperty(color.withAlpha(0.6));
    const e = v.entities.add({
      polyline: {
        positions: arcPositions(from, to),
        width,
        material: mat,
        arcType: Cesium.ArcType.NONE,  // we already bowed it manually
      },
    });
    _ents.push(e);
  }

  function reveal(iso3) {
    clear();
    const v = window.viewer;
    if (!v || !iso3) return;
    const origin = centroid(iso3);
    if (!origin) return;
    _activeIso = iso3;

    // 1) TRADE — top partners by USD value, gold arcs sized by value.
    const ta = window._cacheStore?.get('trade_annual');
    const flows = (ta?.flows || [])
      .filter(f => (f.from_iso3 === iso3 || f.to_iso3 === iso3) && f.from_iso3 !== f.to_iso3)
      .sort((a,b) => (b.value_usd||0) - (a.value_usd||0))
      .slice(0, 8);
    const maxV = flows[0]?.value_usd || 1;
    for (const f of flows) {
      const fromC = (f.from_lat != null) ? [f.from_lon, f.from_lat] : centroid(f.from_iso3);
      const toC   = (f.to_lat != null)   ? [f.to_lon, f.to_lat]     : centroid(f.to_iso3);
      if (!fromC || !toC) continue;
      const w = 1.5 + (f.value_usd / maxV) * 4.5;
      addArc(fromC, toC, '#ffb547', w, true);   // gold, glowing
    }

    // 2) ALLIES — green lines to bloc partners (capped so it's a web, not a hairball).
    const rel = window._cacheStore?.get('country_relations');
    const r = rel?.by_country?.[iso3];
    if (r) {
      (r.allies || []).slice(0, 14).forEach(a => {
        const c = centroid(a);
        if (c) addArc(origin, c, '#5fbf7d', 1.2, false);  // green, thin
      });
      (r.enemies || []).forEach(en => {
        const c = centroid(en);
        if (c) addArc(origin, c, '#ef4444', 2.0, true);   // red, glowing
      });
    }

    // 3) A pulsing ring at the origin so the user sees the anchor of the web.
    v.entities.add._noop;
    const ring = v.entities.add({
      position: Cesium.Cartesian3.fromDegrees(origin[0], origin[1]),
      point: { pixelSize: 14, color: Cesium.Color.WHITE.withAlpha(0.9),
               outlineColor: Cesium.Color.fromCssColorString('#4cc2ff'), outlineWidth: 3 },
    });
    _ents.push(ring);
  }

  // Hook the existing flows. dossier.js / app.js call window.showDossier(iso3)
  // on a country click; mirror that here. We monkey-wrap rather than replace
  // so the dossier still opens normally.
  function install() {
    const origShow = window.showDossier;
    if (typeof origShow === 'function' && !origShow._relwebWrapped) {
      window.showDossier = function(iso3, opts) {
        try { reveal(iso3); } catch (e) { console.warn('[relweb]', e); }
        return origShow.call(this, iso3, opts);
      };
      window.showDossier._relwebWrapped = true;
    }
    const origHide = window.hideDossier;
    if (typeof origHide === 'function' && !origHide._relwebWrapped) {
      window.hideDossier = function() { clear(); return origHide.apply(this, arguments); };
      window.hideDossier._relwebWrapped = true;
    }
  }

  // showDossier may not exist yet at load — retry until it does.
  let tries = 0;
  const t = setInterval(() => {
    if (window.showDossier || tries > 60) { clearInterval(t); install(); }
    tries++;
  }, 250);

  document.addEventListener('keydown', e => { if (e.key === 'Escape') clear(); });
  window.RelationsWeb = { reveal, clear };
})();
