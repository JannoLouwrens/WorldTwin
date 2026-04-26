// causal-lines.js — hover-arc dependency edges.
//
// When the user hovers ANY country (in any mapmode), draw faint arcs to:
//   * Top trade partners (country_resources.partners) — color by direction
//     (export = phosphor amber, import = signal cyan)
//   * Allies (country_relations.allies) — bloc-coloured ally arc
//   * Enemies (country_relations.enemies) — vermillion enemy arc
//
// Each arc is registered with Cesium's pickcard system so clicking opens
// a tooltip explaining the edge: "Egypt → Sudan: 95% of Egypt's water
// originates from the Nile, sourced upstream by GERD."
//
// Trade partner explanations are auto-generated from country_resources
// (top commodity, USD value, year). For allies/enemies we use the
// curated bloc/relation labels in country_relations.
//
// This module REPLACES the legacy connections.js hover handler (which
// only fired in 'political' mapmode and only drew ally/enemy lines).
(function(){
  let _entities = [];
  let _activeIso = null;
  let _enabled = true;

  function clear() {
    if (!window.viewer || !_entities.length) {
      _entities = [];
      return;
    }
    for (const e of _entities) {
      try { window.viewer.entities.remove(e); } catch {}
    }
    _entities = [];
  }

  function getCentroid(iso3) {
    const cr = window._cacheStore?.get('country_resources');
    const c = cr?.countries?.[iso3];
    if (!c || c.lat == null || c.lon == null) return null;
    return { lat: c.lat, lon: c.lon, name: c.name || iso3 };
  }

  // Draw one arc + register a pickcard explanation
  function drawArc(home, other, color, width, kind, explanation) {
    if (!home || !other) return;
    const dx = other.lon - home.lon;
    const dy = other.lat - home.lat;
    const dist = Math.sqrt(dx*dx + dy*dy);
    const arcHeight = Math.min(2_500_000, 350_000 + dist * 35_000);
    const ent = window.viewer.entities.add({
      polyline: {
        positions: Cesium.Cartesian3.fromDegreesArrayHeights([
          home.lon, home.lat, 80_000,
          (home.lon + other.lon) / 2, (home.lat + other.lat) / 2, arcHeight,
          other.lon, other.lat, 80_000,
        ]),
        width,
        arcType: Cesium.ArcType.NONE,
        material: new Cesium.PolylineGlowMaterialProperty({
          color: Cesium.Color.fromCssColorString(color).withAlpha(0.85),
          glowPower: 0.22,
          taperPower: 0.7,
        }),
      },
      properties: {
        causal_kind: kind,
        causal_home: home.name,
        causal_other: other.name,
        pickcard: {
          getValue: () => ({
            title: `${home.name} ↔ ${other.name}`,
            subtitle: kind.toUpperCase(),
            source_name: 'WorldTwin Causal Lines',
            values: [
              { label: 'Why', value: explanation },
              { label: 'Edge', value: kind },
            ],
          }),
        },
      },
      description: `<b>${home.name} ↔ ${other.name}</b><br><i>${kind}</i><br>${explanation}`,
    });
    _entities.push(ent);
  }

  function renderFor(iso3) {
    if (_activeIso === iso3) return;
    _activeIso = iso3;
    clear();
    if (!iso3 || !window.viewer || !_enabled) return;

    const home = getCentroid(iso3);
    if (!home) return;

    // 1) Top trade partners — both directions
    const cr = window._cacheStore?.get('country_resources');
    const me = cr?.countries?.[iso3];
    const exports = (me?.top_export_partners || me?.export_partners || []).slice(0, 6);
    const imports = (me?.top_import_partners || me?.import_partners || []).slice(0, 6);

    for (const p of exports) {
      const partnerIso = p.iso3 || p.partner_iso3 || p.partnerISO || null;
      if (!partnerIso || partnerIso === iso3) continue;
      const other = getCentroid(partnerIso);
      if (!other) continue;
      const valueUsd = p.value_usd || p.value || p.trade_usd;
      const explain = valueUsd
        ? `${home.name} exports to ${other.name}: $${(valueUsd / 1e9).toFixed(2)}B (Comtrade)`
        : `${home.name} exports to ${other.name}`;
      drawArc(home, other, '#ffb547', 1.8, 'export', explain);
    }
    for (const p of imports) {
      const partnerIso = p.iso3 || p.partner_iso3 || p.partnerISO || null;
      if (!partnerIso || partnerIso === iso3) continue;
      const other = getCentroid(partnerIso);
      if (!other) continue;
      const valueUsd = p.value_usd || p.value || p.trade_usd;
      const explain = valueUsd
        ? `${home.name} imports from ${other.name}: $${(valueUsd / 1e9).toFixed(2)}B (Comtrade)`
        : `${home.name} imports from ${other.name}`;
      drawArc(home, other, '#00d4ff', 1.4, 'import', explain);
    }

    // 2) Allies + enemies from country_relations
    const rel = window._cacheStore?.get('country_relations');
    const r = rel?.by_country?.[iso3];
    if (r) {
      const blocs = (r.blocs || []).slice(0, 3).join(', ');
      const allyExplain = blocs
        ? `Shared bloc membership: ${blocs}`
        : 'Cooperation pattern (GDELT QuadClass)';
      const allyHue = r.bloc_color || '#5fbf7d';
      (r.allies || []).slice(0, 8).forEach(a => {
        const other = getCentroid(a);
        if (other) drawArc(home, other, allyHue, 1.2, 'ally', allyExplain);
      });
      (r.enemies || []).slice(0, 6).forEach(e => {
        const other = getCentroid(e);
        if (other) drawArc(home, other, '#d94747', 1.6, 'enemy', 'Adversarial relationship (GDELT QuadClass + curated)');
      });
    }
  }

  // Listen for hover events from mapmode (replaces the legacy handler in
  // connections.js which only fired in political mapmode)
  window.addEventListener('mapmode_hover', (e) => {
    const d = e.detail;
    if (!d) { renderFor(null); return; }
    renderFor(d.iso3);
  });

  // Public API + toggle
  window.CausalLines = {
    renderFor,
    clear,
    setEnabled: (on) => { _enabled = !!on; if (!on) clear(); },
    isEnabled: () => _enabled,
  };

  // Defang the legacy connections.js hover handler so we don't double-render.
  // We can't remove the listener (no reference), but we can stub out its
  // renderHoverLines so it becomes a no-op.
  function deCascade() {
    if (window.Connections && window.Connections.renderHoverLines) {
      const noop = () => {};
      window.Connections.renderHoverLines = noop;
      window.Connections.clearHoverLines = noop;
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(deCascade, 1000));
  } else {
    setTimeout(deCascade, 1000);
  }
})();
