// mapmode-card.js — Deep-dive panel for each mapmode.
//
// When a mapmode is active and user clicks a country polygon, this shows
// a panel specific to THAT mapmode indicator with: value, rank, peers,
// related context, and source info.
//
// Each of the 15 mapmodes gets its own card builder with relevant data.
(function(){

  // ============================================================
  // Helpers
  // ============================================================
  function fmtN(n, decimals) {
    if (n == null) return '—';
    if (typeof decimals === 'undefined') decimals = 1;
    const abs = Math.abs(n);
    if (abs >= 1e12) return (n / 1e12).toFixed(decimals) + 'T';
    if (abs >= 1e9)  return (n / 1e9).toFixed(decimals) + 'B';
    if (abs >= 1e6)  return (n / 1e6).toFixed(decimals) + 'M';
    if (abs >= 1e3)  return (n / 1e3).toFixed(decimals) + 'K';
    return n.toFixed(decimals);
  }

  function pct(n) { return n != null ? n.toFixed(1) + '%' : '—'; }
  function yr(obj) { return obj && obj.year ? ' (' + obj.year + ')' : ''; }

  // Compute global rank for an indicator across all countries
  function rankFor(allCountries, iso3, indicator, higherIsBetter) {
    const vals = [];
    for (const [k, c] of Object.entries(allCountries)) {
      const entry = c[indicator];
      const v = typeof entry === 'object' ? entry?.value : entry;
      if (v != null && typeof v === 'number') vals.push({ iso3: k, v });
    }
    if (higherIsBetter) vals.sort((a, b) => b.v - a.v);
    else vals.sort((a, b) => a.v - b.v);
    const idx = vals.findIndex(x => x.iso3 === iso3);
    return idx >= 0 ? { rank: idx + 1, total: vals.length } : null;
  }

  // Build a mini bar chart as inline HTML
  function miniBar(value, max, color, label) {
    const pct = Math.min(100, Math.max(0, (value / max) * 100));
    return `<div style="display:flex;align-items:center;gap:6px;margin:2px 0">
      <span style="width:70px;font-size:9px;color:#9ca3af">${label}</span>
      <div style="flex:1;height:8px;background:rgba(255,255,255,0.06);border-radius:4px;overflow:hidden">
        <div style="width:${pct}%;height:100%;background:${color};border-radius:4px"></div>
      </div>
      <span style="width:50px;text-align:right;font-size:9px;color:#e8edf3;font-weight:600">${typeof value === 'number' ? fmtN(value) : value}</span>
    </div>`;
  }

  // Peer comparison: show this country vs 5 peers for a metric
  function peerCompare(wb, iso3, indicator, peerList, higherIsBetter, unit) {
    if (!peerList || !peerList.length) return '';
    const vals = [];
    for (const p of [...peerList, iso3]) {
      const entry = wb[p]?.[indicator];
      const v = typeof entry === 'object' ? entry?.value : entry;
      if (v != null) vals.push({ iso3: p, v: typeof v === 'number' ? v : 0 });
    }
    if (vals.length < 2) return '';
    if (higherIsBetter) vals.sort((a, b) => b.v - a.v);
    else vals.sort((a, b) => a.v - b.v);
    const max = Math.max(...vals.map(x => Math.abs(x.v)), 1);

    return `<div style="margin:6px 0">
      <div style="font-size:9px;color:#5eead4;font-weight:700;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:4px">Peer comparison</div>
      ${vals.map(x => {
        const isMe = x.iso3 === iso3;
        const color = isMe ? '#5eead4' : 'rgba(255,255,255,0.25)';
        const label = (isMe ? '► ' : '') + x.iso3;
        return miniBar(x.v, max, color, label);
      }).join('')}
      ${unit ? `<div style="font-size:8px;color:#6b7280;margin-top:2px">${unit}</div>` : ''}
    </div>`;
  }

  // ============================================================
  // Mapmode-specific card builders
  // ============================================================
  function getWB() { return (window._cacheStore?.get('world_bank') || {}).countries || {}; }
  function getIMF() { return (window._cacheStore?.get('imf_data') || {}).countries || {}; }
  function getIntel() { return (window._cacheStore?.get('country_intel') || {}).countries || {}; }
  function getOWID() { return (window._cacheStore?.get('owid_energy') || {}).countries || {}; }
  function getEntsoe() { return (window._cacheStore?.get('entsoe_grid') || {}); }
  function getPeers(iso3) { return (getIntel()[iso3] || {}).peers || []; }

  const BUILDERS = {
    political(iso3) {
      const intel = getIntel()[iso3] || {};
      const s = intel.snapshot || {};
      const deps = intel.dependencies || {};
      const blocs = [];
      let alliesCount = 0, enemiesCount = 0, blocPrimary = null;
      const rel = window._cacheStore?.get('country_relations');
      if (rel?.by_country?.[iso3]) {
        const rc = rel.by_country[iso3];
        blocs.push(...(rc.blocs || []));
        alliesCount = (rc.allies || []).length;
        enemiesCount = (rc.enemies || []).length;
        blocPrimary = rc.bloc_primary;
      }
      // Fall back to world_bank if intel snapshot is empty
      const wb = getWB()[iso3] || {};
      if (!s.gdp_usd) s.gdp_usd = (wb['NY.GDP.MKTP.CD'] || {}).value;
      if (!s.population) s.population = (wb['SP.POP.TOTL'] || {}).value;
      if (!s.military_spend_pct) s.military_spend_pct = (wb['MS.MIL.XPND.GD.ZS'] || {}).value;
      if (!s.internet_pct) s.internet_pct = (wb['IT.NET.USER.ZS'] || {}).value;
      return {
        title: 'Political Profile',
        value: blocPrimary || '—',
        rows: [
          ['Blocs', blocs.join(', ') || '—'],
          ['Allies', String(alliesCount)],
          ['Enemies', String(enemiesCount)],
          ['GDP', '$' + fmtN(s.gdp_usd)],
          ['Population', fmtN(s.population)],
          ['Military', pct(s.military_spend_pct) + ' of GDP'],
          ['Internet', pct(s.internet_pct)],
          ['Trade partners', (deps.trade_partners || []).join(', ') || '—'],
        ],
        source: 'Country Relations + World Bank',
        alerts: intel.alerts,
      };
    },

    gdp(iso3) {
      const wb = getWB();
      const entry = wb[iso3]?.['NY.GDP.MKTP.CD'];
      const growth = wb[iso3]?.['NY.GDP.MKTP.KD.ZG'];
      const pcap = wb[iso3]?.['NY.GDP.PCAP.CD'];
      const rank = rankFor(wb, iso3, 'NY.GDP.MKTP.CD', true);
      const imf = getIMF()[iso3];
      return {
        title: 'GDP (current USD)',
        value: '$' + fmtN(entry?.value) + yr(entry),
        rank: rank ? `#${rank.rank} of ${rank.total} globally` : null,
        rows: [
          ['GDP', '$' + fmtN(entry?.value)],
          ['GDP growth', pct(growth?.value) + yr(growth)],
          ['GDP per capita', '$' + fmtN(pcap?.value, 0)],
          ['IMF forecast (2030)', imf?.NGDPDPC?.value ? '$' + fmtN(imf.NGDPDPC.value, 0) + '/cap' : '—'],
        ],
        peers: peerCompare(wb, iso3, 'NY.GDP.MKTP.CD', getPeers(iso3), true, 'Current USD'),
        source: 'World Bank WDI 🥇',
      };
    },

    population(iso3) {
      const wb = getWB();
      const pop = wb[iso3]?.['SP.POP.TOTL'];
      const growth = wb[iso3]?.['SP.POP.GROW'];
      const urban = wb[iso3]?.['SP.URB.TOTL.IN.ZS'];
      const life = wb[iso3]?.['SP.DYN.LE00.IN'];
      const rank = rankFor(wb, iso3, 'SP.POP.TOTL', true);
      return {
        title: 'Population',
        value: fmtN(pop?.value, 0) + yr(pop),
        rank: rank ? `#${rank.rank} of ${rank.total}` : null,
        rows: [
          ['Total', fmtN(pop?.value, 0)],
          ['Growth rate', pct(growth?.value) + '/yr'],
          ['Urban', pct(urban?.value)],
          ['Life expectancy', life?.value ? life.value.toFixed(1) + ' years' : '—'],
          ['Under-5 mortality', fmtN(wb[iso3]?.['SH.DYN.MORT']?.value) + '/1000'],
        ],
        peers: peerCompare(wb, iso3, 'SP.POP.TOTL', getPeers(iso3), true, 'People'),
        source: 'World Bank WDI 🥇',
      };
    },

    gdp_pc(iso3) {
      const wb = getWB();
      const entry = wb[iso3]?.['NY.GDP.PCAP.CD'];
      const gni = wb[iso3]?.['NY.GNP.PCAP.PP.CD'];
      const rank = rankFor(wb, iso3, 'NY.GDP.PCAP.CD', true);
      return {
        title: 'GDP per Capita',
        value: '$' + fmtN(entry?.value, 0) + yr(entry),
        rank: rank ? `#${rank.rank} of ${rank.total}` : null,
        rows: [
          ['GDP/capita', '$' + fmtN(entry?.value, 0)],
          ['GNI PPP/capita', '$' + fmtN(gni?.value, 0)],
          ['GDP growth', pct(wb[iso3]?.['NY.GDP.MKTP.KD.ZG']?.value)],
          ['Unemployment', pct(wb[iso3]?.['SL.UEM.TOTL.ZS']?.value)],
        ],
        peers: peerCompare(wb, iso3, 'NY.GDP.PCAP.CD', getPeers(iso3), true, 'USD per capita'),
        source: 'World Bank WDI 🥇',
      };
    },

    inflation(iso3) {
      const imf = getIMF();
      const wb = getWB();
      const inf = wb[iso3]?.['FP.CPI.TOTL.ZG'];
      const imfInf = imf[iso3]?.['PCPIPCH'];
      return {
        title: 'Inflation (CPI)',
        value: pct(inf?.value) + yr(inf),
        rows: [
          ['CPI inflation', pct(inf?.value) + yr(inf)],
          ['IMF forecast', imfInf?.value ? pct(imfInf.value) + ' (' + imfInf.year + ')' : '—'],
          ['GDP growth', pct(wb[iso3]?.['NY.GDP.MKTP.KD.ZG']?.value)],
          ['Unemployment', pct(wb[iso3]?.['SL.UEM.TOTL.ZS']?.value)],
          ['Debt/GDP', pct(wb[iso3]?.['GC.DOD.TOTL.GD.ZS']?.value)],
        ],
        peers: peerCompare(wb, iso3, 'FP.CPI.TOTL.ZG', getPeers(iso3), false, 'Lower is better'),
        source: 'IMF DataMapper 🥇 + World Bank 🥇',
      };
    },

    military(iso3) {
      const wb = getWB();
      const mil = wb[iso3]?.['MS.MIL.XPND.GD.ZS'];
      const intel = getIntel()[iso3] || {};
      const conflict = (intel.risks || {}).conflict || 0;
      return {
        title: 'Military Spend (% GDP)',
        value: pct(mil?.value) + yr(mil),
        rows: [
          ['Military/GDP', pct(mil?.value)],
          ['GDP', '$' + fmtN(wb[iso3]?.['NY.GDP.MKTP.CD']?.value)],
          ['Est. military budget', mil?.value && wb[iso3]?.['NY.GDP.MKTP.CD']?.value
            ? '$' + fmtN(mil.value / 100 * wb[iso3]['NY.GDP.MKTP.CD'].value) : '—'],
          ['Conflict risk', (conflict * 100).toFixed(0) + '% (UCDP-derived)'],
          ['Population', fmtN(wb[iso3]?.['SP.POP.TOTL']?.value, 0)],
        ],
        peers: peerCompare(wb, iso3, 'MS.MIL.XPND.GD.ZS', getPeers(iso3), true, '% of GDP'),
        source: 'World Bank WDI 🥇 + UCDP 🥈',
      };
    },

    water_stress(iso3) {
      const deep = (window._cacheStore?.get('country_deep_dive') || {}).countries || {};
      const c = deep[iso3] || {};
      const water = c.water || {};
      return {
        title: 'Water Stress',
        value: water.bws_label || water.stress_label || '—',
        rows: [
          ['BWS score', water.bws != null ? water.bws.toFixed(2) : '—'],
          ['Stress level', water.bws_label || water.stress_label || '—'],
          ['Freshwater withdrawal', pct((getWB()[iso3]?.['ER.H2O.FWTL.ZS'] || {}).value)],
          ['Agricultural land', pct((getWB()[iso3]?.['AG.LND.AGRI.ZS'] || {}).value)],
          ['Forest area', pct((getWB()[iso3]?.['AG.LND.FRST.ZS'] || {}).value)],
        ],
        source: 'WRI Aqueduct 🥈 + World Bank 🥇',
      };
    },

    food(iso3) {
      const deep = (window._cacheStore?.get('country_deep_dive') || {}).countries || {};
      const c = deep[iso3] || {};
      const food = c.food || {};
      const fao = window._cacheStore?.get('fao_food_prices') || {};
      return {
        title: 'Food Security',
        value: food.ipc_description || 'No FEWS data',
        rows: [
          ['IPC Phase', food.ipc_phase != null ? food.ipc_phase + '/5' : '—'],
          ['Description', food.ipc_description || '—'],
          ['FAO Food Price Index', fao.items?.[0]?.value ? fao.items[0].value.toFixed(1) : '—'],
          ['Agricultural land', pct((getWB()[iso3]?.['AG.LND.AGRI.ZS'] || {}).value)],
          ['Rural population', pct((getWB()[iso3]?.['SP.RUR.TOTL.ZS'] || {}).value)],
        ],
        note: 'FEWS NET covers ~30 countries in Africa/Central America/Middle East. Other regions show "No data" — not necessarily food-secure.',
        source: 'FEWS NET 🥈 + FAO 🥇',
      };
    },

    co2(iso3) {
      const wb = getWB();
      const co2 = wb[iso3]?.['EN.GHG.CO2.PC.CE.AR5'];
      const energy = wb[iso3]?.['EG.USE.PCAP.KG.OE'];
      const rank = rankFor(wb, iso3, 'EN.GHG.CO2.PC.CE.AR5', false);
      const berkeley = window._cacheStore?.get('berkeley_earth') || {};
      return {
        title: 'CO₂ per Capita',
        value: co2?.value ? co2.value.toFixed(1) + ' tonnes' + yr(co2) : '—',
        rank: rank ? `#${rank.rank} of ${rank.total} (lower = better)` : null,
        rows: [
          ['CO₂/capita', co2?.value ? co2.value.toFixed(1) + ' t' : '—'],
          ['Energy/capita', energy?.value ? energy.value.toFixed(0) + ' kg oil eq' : '—'],
          ['Electricity access', pct((wb[iso3]?.['EG.ELC.ACCS.ZS'] || {}).value)],
          ['Global temp anomaly', berkeley.latest?.anomaly_c ? '+' + berkeley.latest.anomaly_c.toFixed(2) + '°C' : '—'],
          ['5yr trend', berkeley.trend_5yr_vs_prev_5yr ? (berkeley.trend_5yr_vs_prev_5yr > 0 ? '+' : '') + berkeley.trend_5yr_vs_prev_5yr.toFixed(3) + '°C/yr' : '—'],
        ],
        peers: peerCompare(wb, iso3, 'EN.GHG.CO2.PC.CE.AR5', getPeers(iso3), false, 'Tonnes CO₂ (lower = better)'),
        source: 'World Bank 🥇 + Berkeley Earth 🥈',
      };
    },

    renewable(iso3) {
      const owid = getOWID();
      const c = owid[iso3] || {};
      const latest = c.latest || c;
      const entsoe = getEntsoe();
      let entsoeData = null;
      // Try to find ENTSO-E data for this country
      for (const [iso2, ed] of Object.entries(entsoe.countries || {})) {
        if (ed.name && (getIntel()[iso3]?.name || '').toLowerCase().startsWith(ed.name.toLowerCase().slice(0, 4))) {
          entsoeData = ed;
          break;
        }
      }
      const rows = [
        ['Renewable share', pct(latest.renewables_share_elec)],
        ['Solar', pct(latest.solar_share_elec)],
        ['Wind', pct(latest.wind_share_elec)],
        ['Hydro', pct(latest.hydro_share_elec)],
        ['Nuclear', pct(latest.nuclear_share_elec)],
        ['Fossil', pct(latest.fossil_share_elec)],
      ];
      if (entsoeData) {
        rows.push(['Real-time gen', (entsoeData.total_generation_mw / 1000).toFixed(1) + ' GW (ENTSO-E)']);
        rows.push(['Elec price', entsoeData.price_eur_mwh ? entsoeData.price_eur_mwh.toFixed(0) + ' EUR/MWh' : '—']);
      }
      return {
        title: 'Renewable Electricity',
        value: pct(latest.renewables_share_elec),
        rows,
        source: 'Our World in Data 🥈' + (entsoeData ? ' + ENTSO-E 🥈' : ''),
      };
    },

    internet(iso3) {
      const wb = getWB();
      const net = wb[iso3]?.['IT.NET.USER.ZS'];
      const mobile = wb[iso3]?.['IT.CEL.SETS.P2'];
      const rank = rankFor(wb, iso3, 'IT.NET.USER.ZS', true);
      return {
        title: 'Internet Users',
        value: pct(net?.value) + yr(net),
        rank: rank ? `#${rank.rank} of ${rank.total}` : null,
        rows: [
          ['Internet users', pct(net?.value)],
          ['Mobile subs/100', mobile?.value ? mobile.value.toFixed(0) : '—'],
          ['GDP/capita', '$' + fmtN((wb[iso3]?.['NY.GDP.PCAP.CD'] || {}).value, 0)],
          ['Sci. articles', fmtN((wb[iso3]?.['IP.JRN.ARTC.SC'] || {}).value, 0)],
        ],
        peers: peerCompare(wb, iso3, 'IT.NET.USER.ZS', getPeers(iso3), true, '% of population'),
        source: 'World Bank WDI 🥇',
      };
    },

    life(iso3) {
      const wb = getWB();
      const le = wb[iso3]?.['SP.DYN.LE00.IN'];
      const mort = wb[iso3]?.['SH.DYN.MORT'];
      const health = wb[iso3]?.['SH.XPD.CHEX.GD.ZS'];
      const rank = rankFor(wb, iso3, 'SP.DYN.LE00.IN', true);
      return {
        title: 'Life Expectancy',
        value: le?.value ? le.value.toFixed(1) + ' years' + yr(le) : '—',
        rank: rank ? `#${rank.rank} of ${rank.total}` : null,
        rows: [
          ['Life expectancy', le?.value ? le.value.toFixed(1) + ' yr' : '—'],
          ['Under-5 mortality', mort?.value ? mort.value.toFixed(1) + '/1000' : '—'],
          ['Health spend', pct(health?.value) + ' of GDP'],
          ['Women in parliament', pct((wb[iso3]?.['SG.GEN.PARL.ZS'] || {}).value)],
          ['Education spend', pct((wb[iso3]?.['SE.XPD.TOTL.GD.ZS'] || {}).value) + ' of GDP'],
        ],
        peers: peerCompare(wb, iso3, 'SP.DYN.LE00.IN', getPeers(iso3), true, 'Years'),
        source: 'World Bank WDI 🥇',
      };
    },

    urban(iso3) {
      const wb = getWB();
      const urb = wb[iso3]?.['SP.URB.TOTL.IN.ZS'];
      const rural = wb[iso3]?.['SP.RUR.TOTL.ZS'];
      return {
        title: 'Urban Population',
        value: pct(urb?.value) + yr(urb),
        rows: [
          ['Urban', pct(urb?.value)],
          ['Rural', pct(rural?.value)],
          ['Population', fmtN((wb[iso3]?.['SP.POP.TOTL'] || {}).value, 0)],
          ['Pop growth', pct((wb[iso3]?.['SP.POP.GROW'] || {}).value) + '/yr'],
          ['Internet', pct((wb[iso3]?.['IT.NET.USER.ZS'] || {}).value)],
        ],
        peers: peerCompare(wb, iso3, 'SP.URB.TOTL.IN.ZS', getPeers(iso3), true, '% urban'),
        source: 'World Bank WDI 🥇',
      };
    },

    debt(iso3) {
      const wb = getWB();
      const debt = wb[iso3]?.['GC.DOD.TOTL.GD.ZS'];
      const imf = getIMF()[iso3];
      const rank = rankFor(wb, iso3, 'GC.DOD.TOTL.GD.ZS', false);
      return {
        title: 'Government Debt (% GDP)',
        value: pct(debt?.value) + yr(debt),
        rank: rank ? `#${rank.rank} of ${rank.total} (lower = better)` : null,
        rows: [
          ['Debt/GDP', pct(debt?.value)],
          ['IMF forecast', imf?.GGXWDG_NGDP?.value ? pct(imf.GGXWDG_NGDP.value) + ' (' + imf.GGXWDG_NGDP.year + ')' : '—'],
          ['GDP', '$' + fmtN((wb[iso3]?.['NY.GDP.MKTP.CD'] || {}).value)],
          ['GDP growth', pct((wb[iso3]?.['NY.GDP.MKTP.KD.ZG'] || {}).value)],
          ['FDI inflows', pct((wb[iso3]?.['BX.KLT.DINV.WD.GD.ZS'] || {}).value) + ' of GDP'],
          ['Exports', pct((wb[iso3]?.['NE.EXP.GNFS.ZS'] || {}).value) + ' of GDP'],
        ],
        peers: peerCompare(wb, iso3, 'GC.DOD.TOTL.GD.ZS', getPeers(iso3), false, '% of GDP (lower = better)'),
        source: 'World Bank 🥇 + IMF 🥇',
      };
    },

    religion(iso3) {
      const cc = window._cacheStore?.get('country_culture');
      const rec = cc?.countries?.[iso3];
      if (!rec) return null;
      const intel = getIntel()[iso3] || {};
      const wb = getWB()[iso3] || {};
      const pop = (wb['SP.POP.TOTL'] || {}).value;
      return {
        title: 'Religion (' + (rec.religion?.family || '—') + ')',
        value: rec.religion?.label || '—',
        rows: [
          ['Family', rec.religion?.family || '—'],
          ['Population', pop ? fmtN(pop) : '—'],
          ['Ethnicity', rec.ethnicity?.label || '—'],
        ],
        source: 'Wikidata SPARQL P140 + CIA/Pew fallback',
      };
    },

    ethnicity(iso3) {
      const cc = window._cacheStore?.get('country_culture');
      const rec = cc?.countries?.[iso3];
      if (!rec) return null;
      const wb = getWB()[iso3] || {};
      const pop = (wb['SP.POP.TOTL'] || {}).value;
      return {
        title: 'Ethnicity (' + (rec.ethnicity?.family || '—') + ')',
        value: rec.ethnicity?.label || '—',
        rows: [
          ['Family', rec.ethnicity?.family || '—'],
          ['Population', pop ? fmtN(pop) : '—'],
          ['Religion', rec.religion?.label || '—'],
        ],
        source: 'Wikidata SPARQL P172 + CIA/Pew fallback',
      };
    },

    // gdp_pc_history + population_history removed 2026-04-25 — those mapmode
    // ids are gone, the regular `gdp_pc` and `population` builders above are
    // shown instead (they'll be enriched with historical-year context next).

    pulse(iso3) {
      const intel = getIntel()[iso3];
      if (!intel) return null;
      const r = intel.risks || {};
      const s = intel.snapshot || {};
      const riskTypes = [
        ['Conflict', r.conflict], ['Hazard', r.natural_hazard], ['Energy', r.energy],
        ['Food', r.food], ['Displacement', r.displacement], ['Economy', r.economic_downturn],
        ['Climate', r.climate],
      ];
      return {
        title: 'Pulse — Composite Risk',
        value: (r.composite * 100).toFixed(0) + '% overall risk',
        rows: riskTypes.map(([label, val]) => [label, ((val || 0) * 100).toFixed(0) + '%']),
        alerts: intel.alerts,
        source: 'WorldTwin Intelligence Engine (cross-source)',
      };
    },
  };

  // ============================================================
  // Render the mapmode card
  // ============================================================
  function renderMapmodeCard(iso3) {
    const currentMM = window.Mapmode?.current();
    if (!currentMM || !BUILDERS[currentMM]) return null;

    const data = BUILDERS[currentMM](iso3);
    if (!data) return null;

    const intel = getIntel()[iso3] || {};
    const name = intel.name || iso3;

    let html = `<div class="mc-header">
      <div class="mc-country">${name}</div>
      <div class="mc-title">${data.title}</div>
      ${data.value ? `<div class="mc-value">${data.value}</div>` : ''}
      ${data.rank ? `<div class="mc-rank">${data.rank}</div>` : ''}
    </div>`;

    // Rows
    if (data.rows && data.rows.length) {
      html += '<div class="mc-section">';
      data.rows.forEach(([k, v]) => {
        html += `<div class="mc-row"><span class="mc-k">${k}</span><span class="mc-v">${v}</span></div>`;
      });
      html += '</div>';
    }

    // Peer comparison
    if (data.peers) {
      html += `<div class="mc-section">${data.peers}</div>`;
    }

    // Note
    if (data.note) {
      html += `<div class="mc-note">${data.note}</div>`;
    }

    // Alerts
    if (data.alerts && data.alerts.length) {
      const sevIcons = { high: '🔴', medium: '🟡', low: '🟢', info: 'ℹ️' };
      html += '<div class="mc-section mc-alerts">';
      data.alerts.forEach(a => {
        html += `<div class="mc-alert">${sevIcons[a.severity] || '•'} ${a.text}</div>`;
      });
      html += '</div>';
    }

    // Source
    html += `<div class="mc-source">${data.source || ''}</div>`;

    return html;
  }

  // ============================================================
  // Show/hide
  // ============================================================
  function injectStyles() {
    if (document.getElementById('mc-styles')) return;
    const style = document.createElement('style');
    style.id = 'mc-styles';
    style.textContent = `
      #mapmodeCard {
        position: fixed; top: 120px; right: 16px; width: 340px; max-height: 70vh;
        overflow-y: auto; background: rgba(8,12,24,0.94); backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.1); border-radius: 12px;
        box-shadow: 0 12px 48px rgba(0,0,0,0.6); color: #e8edf3;
        font: 12px 'Inter', system-ui, sans-serif; z-index: 146; display: none; padding: 0;
      }
      .mc-header { padding: 14px 16px 10px; border-bottom: 1px solid rgba(255,255,255,0.06); }
      .mc-country { font-size: 15px; font-weight: 700; color: #fff; }
      .mc-title { font-size: 10px; color: #5eead4; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; margin-top: 4px; }
      .mc-value { font-size: 22px; font-weight: 800; color: #fff; margin-top: 4px; font-family: 'JetBrains Mono', monospace; }
      .mc-rank { font-size: 10px; color: #9ca3af; margin-top: 2px; }
      .mc-section { padding: 8px 16px; border-bottom: 1px solid rgba(255,255,255,0.04); }
      .mc-row { display: flex; justify-content: space-between; padding: 3px 0; font-size: 11px; }
      .mc-k { color: #9ca3af; }
      .mc-v { color: #e8edf3; font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 10px; }
      .mc-note { padding: 8px 16px; font-size: 9px; color: #6b7280; font-style: italic; }
      .mc-alerts { background: rgba(239,68,68,0.04); }
      .mc-alert { font-size: 10px; color: #cbd5e1; padding: 2px 0; }
      .mc-source { padding: 8px 16px; font-size: 9px; color: #4b5563; border-top: 1px solid rgba(255,255,255,0.04); }
      .mc-close { position: absolute; top: 10px; right: 12px; width: 24px; height: 24px; border: none;
        background: rgba(255,255,255,0.06); color: #fff; border-radius: 6px; cursor: pointer; font-size: 14px; }
      .mc-close:hover { background: rgba(255,255,255,0.12); }
    `;
    document.head.appendChild(style);
  }

  function ensureContainer() {
    let el = document.getElementById('mapmodeCard');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'mapmodeCard';
    document.body.appendChild(el);
    return el;
  }

  function showMapmodeCard(iso3) {
    injectStyles();
    const html = renderMapmodeCard(iso3);
    if (!html) return false; // no mapmode active or no data

    if (window.dismissAllPopups) window.dismissAllPopups();
    const el = ensureContainer();
    el.innerHTML = '<button class="mc-close" title="Close">&times;</button>' + html;
    el.style.display = 'block';
    el.querySelector('.mc-close').addEventListener('click', () => el.style.display = 'none');
    return true; // handled
  }

  function hideMapmodeCard() {
    const el = document.getElementById('mapmodeCard');
    if (el) el.style.display = 'none';
  }

  window.showMapmodeCard = showMapmodeCard;
  window.hideMapmodeCard = hideMapmodeCard;
})();
