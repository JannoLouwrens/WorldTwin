// inspector-toggle.js — Apple-clean reveal pill for the data inspector.
// The inspector mounts on first DataInspector.open() but our new CSS
// keeps it slid off-screen until aria-hidden="false" or .tw-inspector-open.
// This pill gives the user an explicit way to pop it open with whatever
// detail was last shown (or a placeholder if nothing yet).
(function(){
  function ensureBtn() {
    if (document.getElementById('twInspectorToggle')) return;
    const b = document.createElement('button');
    b.id = 'twInspectorToggle';
    b.type = 'button';
    b.setAttribute('aria-label', 'Toggle data inspector');
    b.title = 'Data · trace any value to its source';
    b.innerHTML = `
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="6.4"></circle>
        <line x1="15.6" y1="15.6" x2="20" y2="20"></line>
      </svg>`;
    b.addEventListener('click', () => {
      const insp = document.getElementById('twDataInspector');
      const open = insp && (insp.classList.contains('tw-inspector-open')
                         || insp.getAttribute('aria-hidden') === 'false');
      if (open) {
        if (window.DataInspector && DataInspector.close) DataInspector.close();
        b.classList.remove('is-open');
      } else {
        if (window.DataInspector && DataInspector.open) {
          DataInspector.open({
            label: 'Data inspector',
            value: 'Click any value on the page',
            source: 'WorldTwin',
            path: '',
          });
        }
        b.classList.add('is-open');
      }
    });
    document.body.appendChild(b);

    // Keep pill state in sync if inspector is opened/closed elsewhere.
    const sync = () => {
      const insp = document.getElementById('twDataInspector');
      if (!insp) return;
      const open = insp.classList.contains('tw-inspector-open')
                || insp.getAttribute('aria-hidden') === 'false';
      b.classList.toggle('is-open', open);
    };
    const obs = new MutationObserver(sync);
    const tryObserve = () => {
      const insp = document.getElementById('twDataInspector');
      if (insp) {
        obs.observe(insp, { attributes: true, attributeFilter: ['class', 'aria-hidden'] });
      } else {
        setTimeout(tryObserve, 500);
      }
    };
    tryObserve();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ensureBtn);
  } else {
    ensureBtn();
  }
})();
