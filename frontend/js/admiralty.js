// admiralty.js — Admiralty Plate aesthetic shell.
//
// Wraps existing #mmbar + #layerToggles in a single .tw-header plate,
// mounts a top-left .tw-masthead, runs the boot-reveal stagger, and
// wires the [Alt]-key graticule + plate-focus signature interactions.
//
// Pure additive: doesn't touch any existing module's API. Each piece
// is null-safe so a partial load won't break the page.
(function(){
  function toRoman(n) {
    const map = [['M',1000],['CM',900],['D',500],['CD',400],['C',100],['XC',90],
                 ['L',50],['XL',40],['X',10],['IX',9],['V',5],['IV',4],['I',1]];
    let r = '';
    for (const [s, v] of map) { while (n >= v) { r += s; n -= v; } }
    return r;
  }
  const MONTHS = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];

  function mountMasthead() {
    if (document.getElementById('twMasthead')) return;
    const el = document.createElement('header');
    el.id = 'twMasthead';
    el.className = 'tw-masthead has-gnomons-4';
    el.setAttribute('aria-label', 'WorldTwin masthead');
    const d = new Date();
    const stamp = `${String(d.getDate()).padStart(2,'0')}.${MONTHS[d.getMonth()]}.${toRoman(d.getFullYear())}`;
    el.innerHTML = `
      <div class="tw-masthead-title">
        <span class="tw-masthead-name">World<em>Twin</em></span>
        <span class="tw-masthead-led">
          <span class="tw-masthead-led-dot" aria-hidden="true"></span>Live
        </span>
      </div>
      <div class="tw-masthead-rule" aria-hidden="true"></div>
      <div class="tw-masthead-meta">
        <span>Earth Observatory</span>
        <span>No. 04</span>
        <span>${stamp}</span>
      </div>`;
    document.body.appendChild(el);
  }

  function wrapHeader() {
    if (document.getElementById('twHeader')) return;
    const mm = document.getElementById('mmbar');
    const lt = document.getElementById('layerToggles');
    if (!mm || !lt) return;
    const wrap = document.createElement('section');
    wrap.id = 'twHeader';
    wrap.className = 'tw-header has-gnomons-4';
    wrap.setAttribute('aria-label', 'Mapmodes and layers');
    wrap.innerHTML = '<div class="tw-header-kicker"><span>Atlas Plate</span></div>';
    mm.parentNode.insertBefore(wrap, mm);
    wrap.appendChild(mm);
    wrap.appendChild(lt);
  }

  function mountStrata() {
    const tl = document.getElementById('timeline');
    if (!tl || tl.querySelector('.tw-scrubber-eras')) return;
    const eras = document.createElement('div');
    eras.className = 'tw-scrubber-eras';
    eras.setAttribute('aria-hidden', 'true');
    eras.innerHTML = `
      <div class="tw-scrubber-era">Pleistocene<span class="tw-scrubber-era-mono">800k–10k BC</span></div>
      <div class="tw-scrubber-era">Neolithic<span class="tw-scrubber-era-mono">10k–3k BC</span></div>
      <div class="tw-scrubber-era">Bronze · Iron<span class="tw-scrubber-era-mono">3k–500 BC</span></div>
      <div class="tw-scrubber-era">Classical<span class="tw-scrubber-era-mono">500 BC–500 AD</span></div>
      <div class="tw-scrubber-era">Medieval<span class="tw-scrubber-era-mono">500–1500</span></div>
      <div class="tw-scrubber-era">Early Modern<span class="tw-scrubber-era-mono">1500–1800</span></div>
      <div class="tw-scrubber-era">Industrial<span class="tw-scrubber-era-mono">1800–1945</span></div>
      <div class="tw-scrubber-era">Contemporary<span class="tw-scrubber-era-mono">1945–Live</span></div>`;
    tl.insertBefore(eras, tl.firstChild);
  }

  function decoratePanels() {
    const brief = document.getElementById('twBriefing');
    if (brief) brief.classList.add('has-gnomons-4');
    const inset = document.getElementById('pollutionInset');
    if (inset) inset.classList.add('has-gnomons-4');
  }

  function wireGraticule() {
    document.addEventListener('keydown', (e) => {
      if (e.altKey) document.body.classList.add('tw-graticule-bright');
    });
    document.addEventListener('keyup', (e) => {
      if (!e.altKey) document.body.classList.remove('tw-graticule-bright');
    });
    window.addEventListener('blur', () => document.body.classList.remove('tw-graticule-bright'));
  }

  function wirePlateFocus() {
    document.addEventListener('mouseover', (e) => {
      if (e.target.closest && e.target.closest('.has-gnomons-4')) {
        document.body.classList.add('tw-plate-focus');
      }
    });
    document.addEventListener('mouseout', (e) => {
      const r = e.relatedTarget;
      if (!r || !(r.closest && r.closest('.has-gnomons-4'))) {
        document.body.classList.remove('tw-plate-focus');
      }
    });
  }

  function bootReveal() {
    requestAnimationFrame(() => {
      setTimeout(() => document.body.classList.add('tw-booted'), 80);
    });
  }

  // Hide the legacy brand corner if present (we replace it)
  function hideLegacyBrand() {
    const old = document.querySelector('.tw-brand');
    if (old) old.style.display = 'none';
  }

  function init() {
    mountMasthead();
    wrapHeader();
    mountStrata();
    decoratePanels();
    wireGraticule();
    wirePlateFocus();
    hideLegacyBrand();
    bootReveal();

    // Re-decorate periodically while panels mount async
    let n = 0;
    const t = setInterval(() => {
      decoratePanels();
      wrapHeader();
      mountStrata();
      if (++n > 8) clearInterval(t);
    }, 700);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
  } else {
    setTimeout(init, 200);
  }

  window.Admiralty = { init, mountMasthead, wrapHeader };
})();
