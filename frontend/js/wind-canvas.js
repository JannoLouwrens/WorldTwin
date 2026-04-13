// Lightweight wind-particle canvas overlay (earth.nullschool technique).
// Reads /api/cache/wind_sample.json (Open-Meteo 18x10 grid) and advects
// ~3000 particles on a full-screen canvas that sits above the Cesium globe.
//
// API:
//   WindCanvas.start()    — begin animation
//   WindCanvas.stop()     — stop and clear
//   WindCanvas.refresh()  — refetch wind data
(function(){
  let canvas = null, ctx = null;
  let particles = [];
  let windGrid = null;   // { points: [{lat,lon,u,v,speed}], minLon, maxLon, minLat, maxLat }
  let rafId = null;
  let running = false;
  const PARTICLE_COUNT = 2800;
  const MAX_LIFE = 110;

  function ensureCanvas() {
    if (canvas) return;
    canvas = document.createElement('canvas');
    canvas.id = 'wind-canvas';
    canvas.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:40;mix-blend-mode:screen';
    document.body.appendChild(canvas);
    ctx = canvas.getContext('2d');
    resize();
    window.addEventListener('resize', resize);
  }
  function resize() {
    if (!canvas) return;
    const dpr = 1;  // keep 1x for perf
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
  }

  async function fetchWind() {
    try {
      const r = await fetch('/api/cache/wind_sample.json?_=' + Date.now());
      if (!r.ok) return;
      const d = await r.json();
      const pts = (d.points || []).map(p => {
        const rad = ((p.dir_deg || 0) - 180) * Math.PI / 180;  // meteo convention
        const speed = p.speed_ms || 0;
        return {
          lat: p.lat,
          lon: p.lon,
          u: Math.sin(rad) * speed,  // east-west m/s
          v: Math.cos(rad) * speed,  // north-south m/s
          speed: speed,
        };
      });
      windGrid = { points: pts };
      console.log('[wind] loaded', pts.length, 'grid points');
    } catch (e) { console.warn('[wind] fetch failed', e); }
  }

  function sampleWind(lat, lon) {
    if (!windGrid || !windGrid.points.length) return { u: 0, v: 0, speed: 0 };
    // Nearest neighbour — fast enough for 2800 particles × 18 grid
    let best = null, bestD = Infinity;
    for (const p of windGrid.points) {
      const dLat = p.lat - lat;
      let dLon = p.lon - lon;
      if (dLon > 180) dLon -= 360;
      if (dLon < -180) dLon += 360;
      const d = dLat * dLat + dLon * dLon;
      if (d < bestD) { bestD = d; best = p; }
    }
    return best || { u: 0, v: 0, speed: 0 };
  }

  function randParticle() {
    return {
      lat: (Math.random() - 0.5) * 160,
      lon: (Math.random() - 0.5) * 360,
      life: Math.floor(Math.random() * MAX_LIFE),
      prev: null,
    };
  }
  function seed() {
    particles = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(randParticle());
  }

  function latLonToScreen(lat, lon) {
    if (!window.viewer) return null;
    try {
      const cart = Cesium.Cartesian3.fromDegrees(lon, lat, 0);
      const p2 = window.viewer.scene.cartesianToCanvasCoordinates(cart);
      if (!p2) return null;
      // Reject back-of-globe points
      const cam = window.viewer.camera.positionWC;
      const toCart = Cesium.Cartesian3.subtract(cart, cam, new Cesium.Cartesian3());
      // Dot with surface normal at cart; if points away, hide
      const normal = Cesium.Cartesian3.normalize(cart, new Cesium.Cartesian3());
      const toCam = Cesium.Cartesian3.normalize(Cesium.Cartesian3.negate(toCart, new Cesium.Cartesian3()), new Cesium.Cartesian3());
      const dot = Cesium.Cartesian3.dot(normal, toCam);
      if (dot < 0) return null;
      return p2;
    } catch (_) { return null; }
  }

  function speedHex(speed) {
    const t = Math.min(1, speed / 25);
    // cold-hot ramp: blue → cyan → green → yellow → orange → red
    const stops = ['#3288bd','#66c2a5','#abdda4','#e6f598','#fee08b','#fdae61','#f46d43','#d53e4f'];
    const i = t * (stops.length - 1);
    const lo = Math.floor(i), hi = Math.ceil(i);
    if (lo === hi) return stops[lo];
    return stops[lo];
  }

  function tick() {
    if (!running) return;
    rafId = requestAnimationFrame(tick);
    if (!ctx || !windGrid) return;

    // Fade previous frame
    ctx.globalCompositeOperation = 'destination-in';
    ctx.fillStyle = 'rgba(0,0,0,0.92)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.globalCompositeOperation = 'source-over';

    // Advect and draw each particle
    for (let i = 0; i < particles.length; i++) {
      const p = particles[i];
      const wind = sampleWind(p.lat, p.lon);

      // Step size scaled by wind speed — faster wind, longer segment
      const step = 0.18 + wind.speed * 0.03;
      const dLon = (wind.u * step) / Math.max(0.2, Math.cos(p.lat * Math.PI / 180));
      const dLat = wind.v * step;

      const nextLat = p.lat + dLat;
      const nextLon = ((p.lon + dLon + 540) % 360) - 180;  // wrap

      const s0 = p.prev || latLonToScreen(p.lat, p.lon);
      const s1 = latLonToScreen(nextLat, nextLon);

      if (s0 && s1 && p.life > 0) {
        const dx = s1.x - s0.x, dy = s1.y - s0.y;
        const dist = dx*dx + dy*dy;
        if (dist < 5000) {  // skip jumps (e.g. 180° wrap)
          ctx.strokeStyle = speedHex(wind.speed);
          ctx.lineWidth = 0.9 + Math.min(1.6, wind.speed / 12);
          ctx.beginPath();
          ctx.moveTo(s0.x, s0.y);
          ctx.lineTo(s1.x, s1.y);
          ctx.stroke();
        }
      }
      p.prev = s1;
      p.lat = nextLat;
      p.lon = nextLon;
      p.life--;

      if (p.life <= 0 || nextLat < -85 || nextLat > 85) {
        particles[i] = randParticle();
      }
    }
  }

  async function start() {
    ensureCanvas();
    if (!windGrid) await fetchWind();
    seed();
    running = true;
    if (!rafId) tick();
    console.log('[wind] started');
  }
  function stop() {
    running = false;
    if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  async function refresh() {
    await fetchWind();
    seed();
  }

  window.WindCanvas = { start, stop, refresh };
})();
