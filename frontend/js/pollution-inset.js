// pollution-inset.js — paired-trace chart that ONLY appears when the
// 'pollution' mapmode is active. Sits above the timeline at bottom-right.
//
// Why this exists: the user asked for a pollution mode that shows
// "pollution amount and its effects like temp through time". The mapmode
// itself paints per-country CO2 emissions per capita; this inset shows
// the *global* signal — atmospheric CO2 ppm (cause) and global temperature
// anomaly (effect) — both moving with the scrubber so the cause-effect
// chain is visible in one frame.
//
// Data sources (already cached):
//   - noaa_co2.historical_series  : [[year_ad, co2_ppm], ...] -800,000 → today
//   - paleo_temperature.series    : [[year_ad, anom_c],  ...] -9,300 → today
//
// Reads window.Clock for the playhead year. Re-renders on Clock subscribe.
(function(){
  const W = 320, H = 130;
  const PAD_L = 38, PAD_R = 32, PAD_T = 18, PAD_B = 22;
  const CHART_W = W - PAD_L - PAD_R;
  const CHART_H = H - PAD_T - PAD_B;

  let host, svg, gPpm, gTemp, gPlayhead, gYear, gPpmReadout, gTempReadout;
  let _ppmSeries = null;       // [[year, ppm], ...]
  let _tempSeries = null;      // [[year, anom_c], ...]
  let _viewMin = 1750, _viewMax = 2030;  // default view: industrial era
  let _currentMode = null;
  let _mounted = false;

  function fmtYear(y) {
    if (y < 0) return Math.abs(y).toLocaleString() + ' BC';
    return String(Math.round(y));
  }

  function ensureMount() {
    if (_mounted) return;
    host = document.createElement('div');
    host.id = 'pollutionInset';
    host.setAttribute('aria-label', 'Atmospheric CO₂ and global temperature anomaly through time');
    host.innerHTML = `
      <div class="pi-head">
        <div class="pi-title">Atmospheric CO₂ &amp; temperature anomaly</div>
        <div class="pi-sub">Cause &amp; effect, ${fmtYear(_viewMin)} → today</div>
      </div>
      <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img"></svg>
      <div class="pi-legend">
        <span class="pi-sw pi-sw-ppm"></span>CO₂ (ppm)
        <span class="pi-readout" id="piPpm">— ppm</span>
        <span class="pi-sep"></span>
        <span class="pi-sw pi-sw-temp"></span>Temp anomaly
        <span class="pi-readout" id="piTemp">— °C</span>
      </div>`;
    document.body.appendChild(host);
    svg = host.querySelector('svg');
    drawAxes();
    gPpm = ensureGroup('pi-ppm');
    gTemp = ensureGroup('pi-temp');
    gPlayhead = ensureGroup('pi-playhead');
    gYear = ensureGroup('pi-year');
    gPpmReadout = host.querySelector('#piPpm');
    gTempReadout = host.querySelector('#piTemp');
    _mounted = true;
  }

  function ensureGroup(cls) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', cls);
    svg.appendChild(g);
    return g;
  }

  // ----- coordinate helpers -----
  function xOf(year) {
    const t = (year - _viewMin) / (_viewMax - _viewMin);
    return PAD_L + Math.max(0, Math.min(1, t)) * CHART_W;
  }
  // Two y-scales sharing the chart area: ppm on the left, °C on the right.
  // ppm range fixed 250..450 (covers Holocene 280 → present 427).
  // temp range fixed -1..+1.5 (covers Marcott 0 → today +1.2).
  function yPpm(ppm) {
    const t = (ppm - 250) / (450 - 250);
    return PAD_T + (1 - Math.max(0, Math.min(1, t))) * CHART_H;
  }
  function yTemp(c) {
    const t = (c - (-1)) / (1.5 - (-1));
    return PAD_T + (1 - Math.max(0, Math.min(1, t))) * CHART_H;
  }

  function drawAxes() {
    // Background frame
    const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bg.setAttribute('x', PAD_L); bg.setAttribute('y', PAD_T);
    bg.setAttribute('width', CHART_W); bg.setAttribute('height', CHART_H);
    bg.setAttribute('class', 'pi-frame');
    svg.appendChild(bg);

    // Year tick marks (every 50 years inside view, every 100 for label)
    const tickGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    tickGroup.setAttribute('class', 'pi-ticks');
    const span = _viewMax - _viewMin;
    const step = span > 800 ? 100 : span > 200 ? 50 : 25;
    const labelStep = span > 800 ? 100 : 50;
    const startTick = Math.ceil(_viewMin / step) * step;
    for (let y = startTick; y <= _viewMax; y += step) {
      const x = xOf(y);
      const tk = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      tk.setAttribute('x1', x); tk.setAttribute('x2', x);
      tk.setAttribute('y1', PAD_T + CHART_H);
      tk.setAttribute('y2', PAD_T + CHART_H + 3);
      tk.setAttribute('class', 'pi-tick');
      tickGroup.appendChild(tk);
      if (y % labelStep === 0) {
        const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        tx.setAttribute('x', x);
        tx.setAttribute('y', PAD_T + CHART_H + 13);
        tx.setAttribute('class', 'pi-axislabel');
        tx.setAttribute('text-anchor', 'middle');
        tx.textContent = fmtYear(y);
        tickGroup.appendChild(tx);
      }
    }
    svg.appendChild(tickGroup);

    // Y-axis labels — left = ppm, right = °C
    const leftLabels = [
      [280, '280', 'pre-industrial'],
      [350, '350', ''],
      [420, '420', 'today'],
    ];
    leftLabels.forEach(([v, label]) => {
      const y = yPpm(v);
      const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      tx.setAttribute('x', PAD_L - 6); tx.setAttribute('y', y + 3);
      tx.setAttribute('class', 'pi-axislabel pi-axisleft');
      tx.setAttribute('text-anchor', 'end');
      tx.textContent = label;
      svg.appendChild(tx);
      const gridLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      gridLine.setAttribute('x1', PAD_L); gridLine.setAttribute('x2', PAD_L + CHART_W);
      gridLine.setAttribute('y1', y); gridLine.setAttribute('y2', y);
      gridLine.setAttribute('class', 'pi-grid');
      svg.appendChild(gridLine);
    });
    const rightLabels = [[+1.2, '+1.2°'], [0, '0°'], [-0.6, '−0.6°']];
    rightLabels.forEach(([v, label]) => {
      const y = yTemp(v);
      const tx = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      tx.setAttribute('x', PAD_L + CHART_W + 6); tx.setAttribute('y', y + 3);
      tx.setAttribute('class', 'pi-axislabel pi-axisright');
      tx.setAttribute('text-anchor', 'start');
      tx.textContent = label;
      svg.appendChild(tx);
    });

    // Axis titles
    const ppmTitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    ppmTitle.setAttribute('x', PAD_L); ppmTitle.setAttribute('y', PAD_T - 6);
    ppmTitle.setAttribute('class', 'pi-axistitle pi-axistitle-ppm');
    ppmTitle.setAttribute('text-anchor', 'start');
    ppmTitle.textContent = 'ppm';
    svg.appendChild(ppmTitle);
    const tempTitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    tempTitle.setAttribute('x', PAD_L + CHART_W); tempTitle.setAttribute('y', PAD_T - 6);
    tempTitle.setAttribute('class', 'pi-axistitle pi-axistitle-temp');
    tempTitle.setAttribute('text-anchor', 'end');
    tempTitle.textContent = '°C anomaly';
    svg.appendChild(tempTitle);
  }

  // Build SVG path "M x,y L x,y ..." from a series within view bounds
  function buildPath(series, yFn) {
    if (!series || !series.length) return '';
    let d = '';
    let started = false;
    for (const [year, val] of series) {
      if (val == null || !isFinite(val)) continue;
      if (year < _viewMin - 200 || year > _viewMax + 50) continue;
      const x = xOf(year);
      const y = yFn(val);
      d += (started ? ' L ' : 'M ') + x.toFixed(1) + ',' + y.toFixed(1);
      started = true;
    }
    return d;
  }

  function drawTraces() {
    if (!_mounted) return;
    gPpm.innerHTML = ''; gTemp.innerHTML = '';
    if (_ppmSeries) {
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', buildPath(_ppmSeries, yPpm));
      p.setAttribute('class', 'pi-line pi-line-ppm');
      gPpm.appendChild(p);
    }
    if (_tempSeries) {
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', buildPath(_tempSeries, yTemp));
      p.setAttribute('class', 'pi-line pi-line-temp');
      gTemp.appendChild(p);
    }
  }

  // Find nearest sample at-or-before `year`
  function lookup(series, year) {
    if (!series || !series.length) return null;
    let chosen = null;
    for (const row of series) {
      if (row[0] <= year) chosen = row; else break;
    }
    return chosen;
  }

  function drawPlayhead(year) {
    if (!_mounted) return;
    gPlayhead.innerHTML = '';
    gYear.innerHTML = '';
    const x = xOf(year);
    if (x < PAD_L - 1 || x > PAD_L + CHART_W + 1) {
      // Year is outside view range — show a small note
      gPpmReadout.textContent = '—';
      gTempReadout.textContent = '—';
      return;
    }
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x); line.setAttribute('x2', x);
    line.setAttribute('y1', PAD_T); line.setAttribute('y2', PAD_T + CHART_H);
    line.setAttribute('class', 'pi-playhead');
    gPlayhead.appendChild(line);

    const ppmRow = lookup(_ppmSeries, year);
    const tempRow = lookup(_tempSeries, year);

    // Year label above playhead
    const yt = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    yt.setAttribute('x', x); yt.setAttribute('y', PAD_T - 6);
    yt.setAttribute('class', 'pi-yearlabel');
    yt.setAttribute('text-anchor', 'middle');
    yt.textContent = fmtYear(year);
    gYear.appendChild(yt);

    // Markers
    if (ppmRow) {
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', yPpm(ppmRow[1]));
      c.setAttribute('r', 3);
      c.setAttribute('class', 'pi-dot pi-dot-ppm');
      gPlayhead.appendChild(c);
      gPpmReadout.textContent = ppmRow[1].toFixed(1) + ' ppm';
    } else {
      gPpmReadout.textContent = '— ppm';
    }
    if (tempRow) {
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', x); c.setAttribute('cy', yTemp(tempRow[1]));
      c.setAttribute('r', 3);
      c.setAttribute('class', 'pi-dot pi-dot-temp');
      gPlayhead.appendChild(c);
      const sign = tempRow[1] > 0 ? '+' : '';
      gTempReadout.textContent = sign + tempRow[1].toFixed(2) + ' °C';
    } else {
      gTempReadout.textContent = '— °C';
    }
  }

  // ---- Data load ----
  async function loadData() {
    // Each series independently — never short-circuit on the first load
    // because a partial success previously made the second never retry.
    if (!_ppmSeries) {
      try {
        const co2 = await window.fetchCache('noaa_co2');
        if (co2 && Array.isArray(co2.historical_series)) {
          _ppmSeries = co2.historical_series.filter(r => Array.isArray(r) && typeof r[0] === 'number' && r[0] >= _viewMin - 200);
          console.log('[pollution-inset] ppm loaded', _ppmSeries.length, 'samples');
        }
      } catch (e) { console.warn('[pollution-inset] noaa_co2 load failed', e); }
    }
    if (!_tempSeries) {
      try {
        const tmp = await window.fetchCache('paleo_temperature');
        if (tmp && Array.isArray(tmp.series)) {
          _tempSeries = tmp.series.filter(r => Array.isArray(r) && typeof r[0] === 'number' && r[0] >= _viewMin - 200);
          console.log('[pollution-inset] temp loaded', _tempSeries.length, 'samples');
        }
      } catch (e) { console.warn('[pollution-inset] paleo_temperature load failed', e); }
    }
    drawTraces();
  }

  function setVisible(on) {
    if (!_mounted) return;
    host.classList.toggle('pi-on', !!on);
    if (on) {
      loadData().then(() => repaint());
    }
  }

  function repaint() {
    if (!_mounted) return;
    drawTraces();
    const y = (window.Clock && window.Clock.year) || new Date().getUTCFullYear();
    drawPlayhead(y);
  }

  function onModeChange(id) {
    if (id === _currentMode) return;
    _currentMode = id;
    setVisible(id === 'pollution');
  }

  function init() {
    ensureMount();
    // Subscribe to Clock — if the data isn't loaded yet, kick off load+full
    // repaint instead of just moving the playhead (otherwise readouts blank).
    if (window.Clock && window.Clock.subscribe) {
      window.Clock.subscribe((y) => {
        if (!host || !host.classList.contains('pi-on')) return;
        if (!_ppmSeries || !_tempSeries) {
          loadData().then(() => { drawTraces(); drawPlayhead(y); });
        } else {
          drawPlayhead(y);
        }
      });
    }
    // Wrap Mapmode.activate so we know when it changes
    if (window.Mapmode && window.Mapmode.activate) {
      const orig = window.Mapmode.activate;
      window.Mapmode.activate = async function(id) {
        const r = await orig.call(window.Mapmode, id);
        onModeChange(id);
        return r;
      };
      // Initial state in case 'pollution' was already activated
      onModeChange(window.Mapmode.current && window.Mapmode.current());
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 600));
  } else {
    setTimeout(init, 600);
  }

  window.PollutionInset = { setVisible, repaint };
})();
