// url-state.js — the view IS the URL.
//
// Serializes camera, mode, mapmode, active layer toggles and scrubber year
// into query params (debounced, replaceState) and applies them back on boot.
// This is the shareability primitive of the whole product: any interesting
// view of the world becomes a link you can send. Params:
//   mode=war  mm=religion  layers=quakes,fires  yr=1900  cam=lon,lat,heightKm
(function(){
  const P = new URLSearchParams(location.search);
  const wanted = {
    mode:   P.get('mode'),
    mm:     P.get('mm'),
    layers: (P.get('layers') || '').split(',').filter(Boolean),
    yr:     P.get('yr') != null ? parseInt(P.get('yr'), 10) : null,
    cam:    (P.get('cam') || '').split(',').map(Number).filter(n => Number.isFinite(n)),
  };
  const hasDeepLink = !!(wanted.mode || wanted.mm || wanted.layers.length ||
                         wanted.yr != null || wanted.cam.length === 3);

  let _applying = false;

  async function applyOnce() {
    if (!window.viewer || !window.Clock || !window.Mapmode) return false;
    if (!document.getElementById('boot')?.classList.contains('hidden')) return false;
    _applying = true;
    try {
      if (wanted.cam.length === 3) {
        window.viewer.camera.setView({
          destination: Cesium.Cartesian3.fromDegrees(wanted.cam[0], wanted.cam[1], wanted.cam[2] * 1000),
        });
      }
      if (wanted.yr != null && !Number.isNaN(wanted.yr)) {
        window.Clock.setYear(wanted.yr, { force: true });
      }
      if (wanted.mode && window.activateMode) {
        await window.activateMode(wanted.mode);
      }
      if (wanted.mm) {
        await window.Mapmode.activate(wanted.mm);
      }
      for (const id of wanted.layers) {
        const btn = document.querySelector(`#layerToggles button[data-layer="${id}"]`);
        if (btn && !btn.classList.contains('lt-active')) btn.click();
      }
      console.log('[url-state] applied deep link', wanted);
    } catch (e) {
      console.warn('[url-state] apply failed', e);
    } finally {
      // Give the activations a beat before the serializer takes over.
      setTimeout(() => { _applying = false; }, 1500);
    }
    return true;
  }

  function currentState() {
    const s = new URLSearchParams();
    try {
      const mode = (typeof window.currentModeId === 'function' && window.currentModeId()) || '';
      if (mode && mode !== 'world') s.set('mode', mode);
      const mm = window.Mapmode && window.Mapmode.current();
      if (mm) s.set('mm', mm);
      const layers = [...document.querySelectorAll('#layerToggles button.lt-active')]
        .map(b => b.dataset.layer).filter(Boolean);
      if (layers.length) s.set('layers', layers.join(','));
      if (window.Clock && window.Clock.year !== window.Clock.MAX_YEAR) {
        s.set('yr', String(window.Clock.year));
      }
      const c = window.viewer && !window.viewer.isDestroyed?.() &&
                window.viewer.camera.positionCartographic;
      if (c) {
        const lon = (c.longitude * 180 / Math.PI).toFixed(2);
        const lat = (c.latitude * 180 / Math.PI).toFixed(2);
        const hKm = Math.round(c.height / 1000);
        s.set('cam', `${lon},${lat},${hKm}`);
      }
    } catch (_) {}
    return s;
  }

  function startSerializer() {
    let last = '';
    setInterval(() => {
      if (_applying || !window.viewer) return;
      if (!document.getElementById('boot')?.classList.contains('hidden')) return;
      const qs = currentState().toString();
      if (qs !== last) {
        last = qs;
        try {
          history.replaceState(null, '', qs ? '?' + qs : location.pathname);
        } catch (_) {}
      }
    }, 2000);
  }

  // Boot: poll until the app is ready, apply any deep link, then serialize.
  let tries = 0;
  const t = setInterval(async () => {
    tries++;
    const ready = window.viewer && window.Clock && window.Mapmode &&
                  document.getElementById('boot')?.classList.contains('hidden');
    if (ready) {
      clearInterval(t);
      if (hasDeepLink) {
        // Let the default world-mode activation settle first, then override.
        setTimeout(applyOnce, 800);
      }
      setTimeout(startSerializer, hasDeepLink ? 4000 : 1500);
    } else if (tries > 120) {
      clearInterval(t);
    }
  }, 500);
})();
