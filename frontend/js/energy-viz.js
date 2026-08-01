// energy-viz.js — Rich energy visualization layer.
//
// Combines three data sources into one unified energy view:
//   1. ENTSO-E (EU): real-time generation, load, price, fuel mix, cross-border flows
//   2. EIA International (global): annual oil/gas/coal/electricity production + consumption
//   3. OWID Energy (global): electricity mix percentages, renewables share
//
// Renders:
//   - Per-country fuel mix as canvas stacked-bar billboards
//   - Cross-border energy flows as animated arcs (EU only, from ENTSO-E A11)
//   - Color-coded by renewable percentage
(function(){

  const FUEL_COLORS = {
    solar:    '#facc15',
    wind:     '#38bdf8',
    hydro:    '#3b82f6',
    nuclear:  '#a855f7',
    gas:      '#f97316',
    coal:     '#6b7280',
    oil:      '#92400e',
    biomass:  '#22c55e',
    geothermal:'#14b8a6',
    marine:   '#06b6d4',
    waste:    '#a16207',
    other:    '#9ca3af',
    renewable_other: '#10b981',
  };

  const FUEL_ORDER = ['solar','wind','hydro','nuclear','biomass','geothermal','marine','renewable_other','gas','coal','oil','waste','other'];

  // Render a stacked horizontal bar as a canvas image for a Cesium billboard
  const _barCache = {};
  function makeFuelBar(fuelMix, totalMW, width=120, height=20) {
    const key = JSON.stringify(fuelMix) + totalMW;
    if (_barCache[key]) return _barCache[key];

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');

    // Background
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.roundRect(0, 0, width, height, 4);
    ctx.fill();

    if (totalMW <= 0) {
      _barCache[key] = canvas;
      return canvas;
    }

    // Stacked bar (inner, with 2px padding)
    const barX = 2, barY = 2, barW = width - 4, barH = height - 4;
    let x = barX;
    for (const fuel of FUEL_ORDER) {
      const mw = fuelMix[fuel];
      if (!mw || mw <= 0) continue;
      const w = (mw / totalMW) * barW;
      if (w < 1) continue;
      ctx.fillStyle = FUEL_COLORS[fuel] || '#9ca3af';
      ctx.fillRect(x, barY, w, barH);
      x += w;
    }

    // Border
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.lineWidth = 1;
    ctx.roundRect(0, 0, width, height, 4);
    ctx.stroke();

    _barCache[key] = canvas;
    return canvas;
  }

  function clearLayer(id) {
    const arr = window._layerEntities && window._layerEntities[id];
    if (arr) arr.forEach(e => { try { window.viewer.entities.remove(e); } catch (_) {} });
    if (window._layerEntities) window._layerEntities[id] = [];
  }

  function addEntity(id, opts) {
    if (!window._layerEntities) window._layerEntities = {};
    if (!window._layerEntities[id]) window._layerEntities[id] = [];
    const e = window.viewer.entities.add(opts);
    window._layerEntities[id].push(e);
    return e;
  }

  async function getCache(id) {
    if (window._cacheStore && window._cacheStore.has(id)) return window._cacheStore.get(id);
    if (window.fetchCache) return await window.fetchCache(id);
    try {
      const r = await fetch('/api/cache/' + id + '.json?_=' + Date.now());
      if (!r.ok) return null;
      return await r.json();
    } catch { return null; }
  }

  // Build a unified energy map: merge ENTSO-E (real-time EU) + OWID (global composition)
  function mergeEnergySources(entsoeData, owidData, eiaData) {
    const merged = {}; // keyed by ISO2 or ISO3

    // 1) ENTSO-E — real-time, highest priority for EU countries
    if (entsoeData && entsoeData.countries) {
      for (const [iso2, c] of Object.entries(entsoeData.countries)) {
        merged[iso2] = {
          source: 'ENTSO-E (real-time)',
          name: c.name,
          lat: c.lat, lon: c.lon,
          total_mw: c.total_generation_mw || 0,
          fuel_mix: c.fuel_mix || {},
          load_mw: c.load_mw || 0,
          price_eur: c.price_eur_mwh || 0,
          renewable_pct: c.renewable_pct || 0,
          realtime: true,
        };
      }
    }

    // 2) OWID — global, annual, fills in everyone else
    if (owidData && owidData.countries) {
      for (const [iso3, c] of Object.entries(owidData.countries)) {
        if (iso3.length !== 3) continue;
        // Skip if already have ENTSO-E real-time
        // Need ISO3→ISO2 check — just check if any ENTSO-E entry has matching name
        const alreadyHas = Object.values(merged).some(m =>
          m.name && c.name && m.name.toLowerCase().includes(c.name.toLowerCase().slice(0, 5)));
        if (alreadyHas) continue;

        const latest = c.latest || c;
        const fuelMix = {};
        const fields = {
          solar: 'solar_share_elec', wind: 'wind_share_elec',
          hydro: 'hydro_share_elec', nuclear: 'nuclear_share_elec',
          gas: 'gas_share_elec', coal: 'coal_share_elec',
          oil: 'oil_share_elec', biomass: 'biofuel_share_elec',
        };
        let hasAny = false;
        for (const [fuel, key] of Object.entries(fields)) {
          const v = latest[key];
          if (v != null && v > 0) {
            fuelMix[fuel] = v; // percentage, not MW
            hasAny = true;
          }
        }
        if (!hasAny) continue;

        const renewPct = (fuelMix.solar || 0) + (fuelMix.wind || 0) + (fuelMix.hydro || 0) +
                         (fuelMix.biomass || 0);

        // Get coordinates from population cache
        let lat = null, lon = null;
        const pop = window._cacheStore && window._cacheStore.get('population');
        if (Array.isArray(pop)) {
          const match = pop.find(p => p.cca3 === iso3);
          if (match && match.latlng) {
            [lat, lon] = match.latlng;
          }
        }
        if (lat == null) continue;

        merged[iso3] = {
          source: 'OWID Energy (annual)',
          name: c.name || latest.country || iso3,
          lat, lon,
          total_mw: 0, // OWID doesn't provide real-time MW
          fuel_mix: fuelMix,
          load_mw: 0,
          price_eur: 0,
          renewable_pct: Math.round(renewPct * 10) / 10,
          realtime: false,
          pct_based: true, // fuel_mix values are percentages, not MW
        };
      }
    }

    return merged;
  }

  async function renderEnergyViz() {
    clearLayer('energy_viz');

    const [entsoe, owid, eia] = await Promise.all([
      getCache('entsoe_grid'),
      getCache('owid_energy'),
      getCache('eia_international'),
    ]);

    const merged = mergeEnergySources(entsoe, owid, eia);

    // Render per-country fuel mix billboards
    for (const [key, c] of Object.entries(merged)) {
      if (c.lat == null || c.lon == null) continue;

      const totalForBar = c.pct_based ? 100 : (c.total_mw || 0);
      const barCanvas = makeFuelBar(c.fuel_mix, totalForBar, 120, 18);

      // Label: "45.3 GW" for real-time or "67% renewable" for OWID
      let labelText = '';
      if (c.realtime && c.total_mw > 0) {
        labelText = (c.total_mw / 1000).toFixed(1) + ' GW';
      } else if (c.renewable_pct > 0) {
        labelText = c.renewable_pct.toFixed(0) + '% rnw';
      }

      // Color by renewable %
      let dotColor = '#6b7280';
      if (c.renewable_pct >= 80) dotColor = '#22c55e';
      else if (c.renewable_pct >= 60) dotColor = '#84cc16';
      else if (c.renewable_pct >= 40) dotColor = '#facc15';
      else if (c.renewable_pct >= 20) dotColor = '#f97316';
      else dotColor = '#ef4444';

      // Fuel mix values list for pickcard
      const vals = [];
      if (c.realtime) {
        vals.push({ label: 'Generation', value: c.total_mw > 0 ? (c.total_mw/1000).toFixed(1) + ' GW' : '—' });
        vals.push({ label: 'Load', value: c.load_mw > 0 ? (c.load_mw/1000).toFixed(1) + ' GW' : '—' });
        vals.push({ label: 'Price', value: c.price_eur > 0 ? c.price_eur.toFixed(1) + ' EUR/MWh' : '—' });
      }
      vals.push({ label: 'Renewable', value: c.renewable_pct > 0 ? c.renewable_pct.toFixed(1) + '%' : '—' });
      for (const fuel of FUEL_ORDER) {
        const v = c.fuel_mix[fuel];
        if (v && v > 0) {
          const unit = c.pct_based ? '%' : ' MW';
          vals.push({ label: fuel.charAt(0).toUpperCase() + fuel.slice(1), value: Math.round(v) + unit });
        }
      }

      const bag = new Cesium.PropertyBag();
      bag.addProperty('pickcard', new Cesium.ConstantProperty({
        title: c.name + ' — Energy',
        source_name: c.source,
        source_url: c.realtime ? 'https://transparency.entsoe.eu/' : 'https://ourworldindata.org/energy',
        fetched_at: entsoe?.fetched || owid?.fetched,
        location: c.name,
        values: vals,
        category_color: dotColor,
      }));

      // The stacked bar billboard
      addEntity('energy_viz', {
        position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat),
        billboard: {
          image: barCanvas,
          scale: 1.0,
          pixelOffset: new Cesium.Cartesian2(0, -12),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 15000000),
        },
        name: c.name,
        properties: bag,
      });

      // Small colored dot below the bar
      addEntity('energy_viz', {
        position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat),
        point: {
          pixelSize: 8,
          color: Cesium.Color.fromCssColorString(dotColor),
          outlineColor: Cesium.Color.WHITE.withAlpha(0.5),
          outlineWidth: 1,
          heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        },
      });

      // Label
      if (labelText) {
        addEntity('energy_viz', {
          position: Cesium.Cartesian3.fromDegrees(c.lon, c.lat),
          label: {
            text: labelText,
            font: '700 9px Inter',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            pixelOffset: new Cesium.Cartesian2(0, 8),
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 8000000),
          },
        });
      }
    }

    // Render cross-border energy flow arcs (ENTSO-E only)
    if (entsoe && entsoe.flows && window.buildGreatCircle) {
      for (const flow of entsoe.flows) {
        if (!flow.from_lat || !flow.to_lat) continue;
        const mw = Math.abs(flow.mw);
        if (mw < 50) continue;

        // Arc width proportional to flow
        const width = Math.max(1.5, Math.min(8, mw / 2000));

        // Color: green for >1GW, yellow for >500MW, orange for smaller
        let color = '#22c55e';
        if (mw < 500) color = '#f97316';
        else if (mw < 1000) color = '#facc15';

        const positions = window.buildGreatCircle(
          flow.from_lat, flow.from_lon, flow.to_lat, flow.to_lon, 24
        );

        addEntity('energy_viz', {
          polyline: {
            positions,
            width,
            material: new Cesium.PolylineGlowMaterialProperty({
              glowPower: 0.2,
              taperPower: 0.8,
              color: Cesium.Color.fromCssColorString(color).withAlpha(0.7),
            }),
            arcType: Cesium.ArcType.NONE,
          },
          name: flow.from + ' → ' + flow.to + ': ' + mw + ' MW',
          description: '<b>' + flow.from + ' → ' + flow.to + '</b><br>' + mw + ' MW<br>Source: ENTSO-E',
        });
      }
    }
  }

  // Register
  function register() {
    if (!window.LAYERS) { setTimeout(register, 200); return; }
    window.LAYERS.energy_viz = { render: renderEnergyViz, clear: () => clearLayer('energy_viz') };
    console.log('[energy-viz] registered');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(register, 400));
  } else {
    setTimeout(register, 400);
  }
})();
