// scroll-arrows.js — adds chevron arrows + fade-mask state to horizontally
// scrollable bars (.mmbar, #layerToggles). Without this, users have no idea
// they can scroll right to reveal the other ~half of the layers/mapmodes.
//
// Targets are referenced by ID, so this module is reusable.
(function(){
  const TARGETS = [
    { sel: '#mmbar',         topPx: 0,  heightPx: 32 },
    { sel: '#layerToggles',  topPx: 32, heightPx: 26 },
  ];

  function makeArrow(side, target, topPx, heightPx) {
    const el = document.createElement('div');
    el.className = 'tw-scroll-arrow ' + side + ' hidden';
    el.style.top = topPx + 'px';
    el.style.height = heightPx + 'px';
    el.style[side === 'left' ? 'left' : 'right'] = '0';
    el.textContent = side === 'left' ? '‹' : '›';
    el.title = side === 'left' ? 'Scroll left' : 'Scroll right';
    el.addEventListener('click', () => {
      // Direct scroll — RAF-based easing was being preempted by Cesium's
      // RAF loop. Instant jump is acceptable UX for a 260px scroll.
      const dx = side === 'left' ? -260 : 260;
      const start = target.scrollLeft;
      const end = Math.max(0, Math.min(target.scrollWidth - target.clientWidth, start + dx));
      target.scrollLeft = end;
    });
    document.body.appendChild(el);
    return el;
  }

  function update(target, leftEl, rightEl) {
    const max = target.scrollWidth - target.clientWidth;
    const scrolled = target.scrollLeft;
    const atStart = scrolled <= 1;
    const atEnd = scrolled >= max - 1;
    target.dataset.scrollStart = atStart ? 'true' : 'false';
    target.dataset.scrollEnd = atEnd ? 'true' : 'false';
    leftEl.classList.toggle('hidden', atStart || max <= 0);
    rightEl.classList.toggle('hidden', atEnd || max <= 0);
  }

  function attach(spec) {
    const target = document.querySelector(spec.sel);
    if (!target) return;
    const left = makeArrow('left', target, spec.topPx, spec.heightPx);
    const right = makeArrow('right', target, spec.topPx, spec.heightPx);
    const u = () => update(target, left, right);
    target.addEventListener('scroll', u, { passive: true });
    window.addEventListener('resize', u, { passive: true });
    // Children may load later (layer-toggles.js builds entries async)
    new MutationObserver(u).observe(target, { childList: true, subtree: false });
    setTimeout(u, 100);
    setTimeout(u, 800);
    setTimeout(u, 2500);
  }

  function init() {
    TARGETS.forEach(attach);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
