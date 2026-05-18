// scroll-arrows.js — chevron + fade affordance for horizontally scrollable
// bars (#mmbar, #layerToggles). The Atlas-plate header (admiralty.js)
// re-parents these bars after first DOM ready, so wrapping them in a
// container is unreliable. Instead the arrows are FIXED-positioned and
// continuously track the bar's bounding rect.
(function(){
  const TARGETS = ['#mmbar', '#layerToggles'];
  const NUDGE_PX = 60;
  const SCROLL_STEP_PX = 320;

  const bound = new Map();

  function makeArrow(side) {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'tw-edge-arrow tw-edge-arrow--' + side;
    el.setAttribute('aria-label', side === 'left' ? 'Scroll left' : 'More options →');
    el.innerHTML = side === 'left'
      ? '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M9 11L5 7L9 3" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
      : '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 3L9 7L5 11" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    return el;
  }

  function makeFade(side) {
    const el = document.createElement('div');
    el.className = 'tw-edge-fade tw-edge-fade--' + side;
    el.setAttribute('aria-hidden', 'true');
    return el;
  }

  function attach(sel) {
    const bar = document.querySelector(sel);
    if (!bar) return;
    if (bound.has(bar)) return;

    const left = makeArrow('left');
    const right = makeArrow('right');
    const fadeL = makeFade('left');
    const fadeR = makeFade('right');
    // Append to body so they survive when admiralty.js re-parents the bar.
    document.body.appendChild(fadeL);
    document.body.appendChild(fadeR);
    document.body.appendChild(left);
    document.body.appendChild(right);

    const click = (dir) => () => {
      const dx = dir === 'left' ? -SCROLL_STEP_PX : SCROLL_STEP_PX;
      bar.scrollTo({ left: Math.max(0, bar.scrollLeft + dx), behavior: 'smooth' });
    };
    left.addEventListener('click', click('left'));
    right.addEventListener('click', click('right'));

    function position() {
      const r = bar.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) {
        [left, right, fadeL, fadeR].forEach(e => e.style.opacity = '0');
        return;
      }
      const max = bar.scrollWidth - bar.clientWidth;
      const atStart = bar.scrollLeft <= 1;
      const atEnd = bar.scrollLeft >= max - 1;
      const canL = !atStart && max > 0;
      const canR = !atEnd && max > 0;

      // Arrows: vertical-center on the bar
      const cy = r.top + r.height / 2 - 15; // 30/2
      left.style.left = (r.left + 6) + 'px';
      left.style.top = cy + 'px';
      left.style.opacity = canL ? '1' : '0';
      left.style.pointerEvents = canL ? 'auto' : 'none';
      right.style.left = (r.right - 36) + 'px';
      right.style.top = cy + 'px';
      right.style.opacity = canR ? '1' : '0';
      right.style.pointerEvents = canR ? 'auto' : 'none';
      right.classList.toggle('tw-edge-arrow--pulse', canR);

      // Fades: span the full bar height, on left/right sides
      fadeL.style.top = r.top + 'px';
      fadeL.style.left = r.left + 'px';
      fadeL.style.height = r.height + 'px';
      fadeL.style.opacity = canL ? '1' : '0';
      fadeR.style.top = r.top + 'px';
      fadeR.style.left = (r.right - 56) + 'px';
      fadeR.style.height = r.height + 'px';
      fadeR.style.opacity = canR ? '1' : '0';
    }

    bar.addEventListener('scroll', position, { passive: true });
    window.addEventListener('resize', position, { passive: true });
    window.addEventListener('scroll', position, { passive: true });
    // Bar may re-mount or have its children built async
    new MutationObserver(position).observe(bar, { childList: true, subtree: false });
    // Run on a tight schedule for the first 5s while layout settles
    let t = 0;
    const i = setInterval(() => { position(); if (++t > 25) clearInterval(i); }, 200);
    requestAnimationFrame(position);

    bound.set(bar, { position });

    // One-time nudge to tease the existence of more content
    const nudgeKey = 'tw_bar_nudged_v2_' + bar.id;
    if (!sessionStorage.getItem(nudgeKey)) {
      setTimeout(() => {
        if (bar.scrollWidth - bar.clientWidth <= 1) return;
        bar.scrollTo({ left: NUDGE_PX, behavior: 'smooth' });
        setTimeout(() => bar.scrollTo({ left: 0, behavior: 'smooth' }), 850);
        try { sessionStorage.setItem(nudgeKey, '1'); } catch(_){}
      }, 2000);
    }
  }

  function init() {
    TARGETS.forEach(attach);
    new MutationObserver(() => TARGETS.forEach(attach))
      .observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
