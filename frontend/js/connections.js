// connections.js — render flow lines on the globe.
//
// Composes three datasets that previously had no globe presence:
//   * trade_annual.flows — top ~80 trade arcs (rotated by value)
//   * cables (geojson) — submarine cable network as thin polylines
//   * country_relations.allies/enemies — radial lines from a hovered country
//
// All using PolylineCollection / GroundPolyline primitives so we can scale
// to thousands of arcs without entity overhead.
(function(){
  let _tradeEntities = [];
  let _cableEntities = [];
  let _hoverEntities = [];

  function clearArr(arr) {
    if (!window.viewer) return;
    for (const e of arr) {
      try { window.viewer.entities.remove(e); } catch (_) {}
    }
    arr.length = 0;
  }

  // ========== TRADE FLOWS — animated curved arcs, top N by value ==========
  async function renderTradeFlows(opts) {
    opts = opts || {};
    const limit = opts.limit || 80;
    clearArr(_tradeEntities);
    // fetchCache is store-first; the bare _cacheStore read left the layer
    // blank whenever the boot preloader's budget skipped trade_annual.
    const data = window.fetchCache
      ? await window.fetchCache('trade_annual')
      : window._cacheStore?.get('trade_annual');
    if (!data?.flows) return;
    const flows = data.flows
      .filter(f => Number.isFinite(f.from_lat) && Number.isFinite(f.from_lon)
                && Number.isFinite(f.to_lat) && Number.isFinite(f.to_lon)
                && f.from_iso3 !== f.to_iso3)
      .sort((a, b) => b.value_usd - a.value_usd)
      .slice(0, limit);
    const max = flows[0]?.value_usd || 1;
    for (const f of flows) {
      const t = Math.min(1, f.value_usd / max);
      // Color by commodity category — energy red, manufactures blue, food green, etc.
      const color = {
        energy:        '#ef4444',
        manufactures:  '#3b82f6',
        agriculture:   '#22c55e',
        minerals:      '#f59e0b',
        chemicals:     '#a855f7',
        machinery:     '#06b6d4',
        textiles:      '#ec4899',
        services:      '#94a3b8',
      }[f.category] || '#7dd3fc';
      const ent = window.viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights([
            f.from_lon, f.from_lat, 80000 + t * 800000,    // arc rises with value
            (f.from_lon + f.to_lon) / 2, (f.from_lat + f.to_lat) / 2, 600000 + t * 1200000,
            f.to_lon, f.to_lat, 80000 + t * 800000,
          ]),
          width: 1 + t * 2.5,
          arcType: Cesium.ArcType.NONE,
          material: new Cesium.PolylineGlowMaterialProperty({
            color: Cesium.Color.fromCssColorString(color).withAlpha(0.4 + 0.5 * t),
            glowPower: 0.18,
            taperPower: 0.85,
          }),
        },
        properties: {
          pickcard: {
            getValue: () => ({
              title: `${f.from_name} → ${f.to_name}`,
              subtitle: f.commodity_name,
              source_name: 'UN Comtrade ' + f.year,
              values: [
                { label: 'Value', value: '$' + (f.value_usd / 1e9).toFixed(2) + 'B' },
                { label: 'Quantity', value: f.qty?.toLocaleString() || '—' },
                { label: 'HS code', value: f.hs },
                { label: 'Category', value: f.category },
              ],
            }),
          },
          trade_flow: true,
        },
        description: `<b>${f.from_name} → ${f.to_name}</b><br>${f.commodity_name}<br>$${(f.value_usd / 1e9).toFixed(2)}B in ${f.year}`,
      });
      _tradeEntities.push(ent);
    }
    console.log(`[connections] rendered ${flows.length} trade arcs`);
  }
  function clearTradeFlows() { clearArr(_tradeEntities); }

  // ========== CABLES — thin ground polylines, dim default, brighter when zoomed ==========
  async function renderCables(opts) {
    opts = opts || {};
    clearArr(_cableEntities);
    const data = window.fetchCache
      ? await window.fetchCache('cables')
      : window._cacheStore?.get('cables');
    if (!data?.features) return;
    let count = 0;
    for (const feat of data.features) {
      const geom = feat.geometry;
      const props = feat.properties || {};
      if (!geom) continue;
      const lines = geom.type === 'MultiLineString' ? geom.coordinates : [geom.coordinates];
      for (const line of lines) {
        const flat = [];
        for (const [lon, lat] of line) flat.push(lon, lat);
        if (flat.length < 4) continue;
        const ent = window.viewer.entities.add({
          polyline: {
            positions: Cesium.Cartesian3.fromDegreesArray(flat),
            width: 1.5,
            clampToGround: true,
            material: Cesium.Color.fromCssColorString(props.color || '#5eead4').withAlpha(0.7),
          },
          properties: {
            pickcard: {
              getValue: () => ({
                title: props.name || 'Submarine cable',
                source_name: 'TeleGeography',
                values: [
                  { label: 'Type', value: 'Subsea fiber' },
                ],
              }),
            },
            cable_id: props.id,
          },
          description: `<b>${props.name || 'Submarine cable'}</b><br>Source: TeleGeography`,
        });
        _cableEntities.push(ent);
        count++;
      }
    }
    console.log(`[connections] rendered ${count} cable segments`);
  }
  function clearCables() { clearArr(_cableEntities); }

  // ========== HOVER ALLY/ENEMY RADIAL LINES ==========
  function renderHoverLines(iso3) {
    clearArr(_hoverEntities);
    if (!iso3) return;
    const rel = window._cacheStore?.get('country_relations');
    const r = rel?.by_country?.[iso3];
    if (!r) return;
    // Use country_resources for lat/lon (country_polygons doesn't carry centroids)
    const cr = window._cacheStore?.get('country_resources');
    const coords = cr?.countries || {};
    const homeProps = coords[iso3];
    if (!homeProps || homeProps.lat == null || homeProps.lon == null) return;
    const homeLat = homeProps.lat, homeLon = homeProps.lon;

    const drawLine = (otherIso, color, width) => {
      const op = coords[otherIso];
      if (!op || op.lat == null || op.lon == null) return;
      const ent = window.viewer.entities.add({
        polyline: {
          positions: Cesium.Cartesian3.fromDegreesArrayHeights([
            homeLon, homeLat, 200000,
            (homeLon + op.lon) / 2, (homeLat + op.lat) / 2, 1500000,
            op.lon, op.lat, 200000,
          ]),
          width,
          arcType: Cesium.ArcType.NONE,
          material: new Cesium.PolylineGlowMaterialProperty({
            color: Cesium.Color.fromCssColorString(color).withAlpha(0.7),
            glowPower: 0.2,
          }),
        },
      });
      _hoverEntities.push(ent);
    };
    const allyHue = r.bloc_color || '#4cc2ff';
    (r.allies || []).slice(0, 12).forEach(a => drawLine(a, allyHue, 2));
    (r.enemies || []).forEach(e => drawLine(e, '#ef4444', 2.5));
  }
  function clearHoverLines() { clearArr(_hoverEntities); }

  // ========== Public API ==========
  window.Connections = {
    renderTradeFlows, clearTradeFlows,
    renderCables, clearCables,
    renderHoverLines, clearHoverLines,
  };

  // Listen for hover events to draw radial lines (only in political mapmode by default)
  window.addEventListener('mapmode_hover', (e) => {
    const detail = e.detail;
    if (!detail) { clearHoverLines(); return; }
    if (detail.mode === 'political') {
      renderHoverLines(detail.iso3);
    } else {
      clearHoverLines();
    }
  });

  // Register layer toggles for trade + cables — but DON'T overwrite an
  // existing renderer: layers.js registers commodity-filter-aware versions
  // of these ids, and this module silently clobbering them killed the
  // Resources-mode commodity filter.
  function waitAndRegister() {
    if (!window.LAYERS) { setTimeout(waitAndRegister, 100); return; }
    if (!window.LAYERS.trade_annual) {
      window.LAYERS.trade_annual = { render: () => renderTradeFlows({ limit: 80 }), clear: clearTradeFlows };
    }
    if (!window.LAYERS.cables) {
      window.LAYERS.cables = { render: () => renderCables(), clear: clearCables };
    }
  }
  waitAndRegister();
})();
