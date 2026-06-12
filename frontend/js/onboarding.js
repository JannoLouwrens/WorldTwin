// onboarding.js — first-visit overlay teaching the 4 ways to interact.
// Stored in localStorage 'tw_onboarded' so it only shows once.
//
// Press '?' anytime to bring it back.
(function(){
  function build() {
    if (document.getElementById('twOnboard')) return document.getElementById('twOnboard');
    const el = document.createElement('div');
    el.id = 'twOnboard';
    Object.assign(el.style, {
      position: 'fixed', inset: '0', zIndex: 220,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      opacity: '0', transition: 'opacity .3s ease',
    });
    el.innerHTML = `
      <div style="
        background: linear-gradient(180deg, rgba(20,28,48,0.96), rgba(14,19,32,0.96));
        border: 1px solid rgba(76,194,255,0.35);
        border-radius: 18px;
        padding: 32px 36px;
        max-width: 720px;
        color: #f5f7fa;
        font: 13px Inter, sans-serif;
        box-shadow: 0 32px 80px rgba(0,0,0,0.6);
      ">
        <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px">
          <div>
            <div style="font-size:11px;color:#4cc2ff;letter-spacing:0.22em;text-transform:uppercase;margin-bottom:6px">Welcome to</div>
            <div style="font-size:26px;font-weight:700;letter-spacing:0.01em;line-height:1.1">WorldTwin</div>
            <div style="font-size:11px;color:#b8c1d1;letter-spacing:0.18em;text-transform:uppercase;margin-top:6px">Live Earth · 84 data layers · 800,000 BC → today</div>
          </div>
          <button id="twOnboardClose" style="background:none;border:0;color:#b8c1d1;font-size:24px;cursor:pointer;line-height:1">×</button>
        </div>

        <p style="color:#d6dce8;font-size:13px;line-height:1.6;margin:0 0 10px 0">
          A news source built from <b>actual data</b> — not headlines. WorldTwin streams live readings from 75+ open data sources (NASA, USGS, World Bank, IMF, UCDP, NOAA, GDACS and more) onto a 3D Earth, so you can <i>see</i> what's happening — earthquakes, fires, conflicts, trade flows, weather, energy, markets — instead of reading what someone says is happening.
        </p>

        <div style="margin:0 0 8px 0;padding:10px 14px;background:rgba(255,184,77,0.08);border:1px solid rgba(255,184,77,0.28);border-radius:10px;display:flex;gap:10px;align-items:flex-start">
          <span style="color:#ffb84d;font-weight:700;font-size:11px;letter-spacing:0.16em;text-transform:uppercase;white-space:nowrap;padding-top:1px">Early dev</span>
          <span style="color:#c8d0e0;font-size:12px;line-height:1.55">
            This is a one-person project in active development. Things break, some sources rate-limit (you'll see "no data right now" toasts), cold boot takes ~10 s. Start with the <a href="/worldtwin/brief.html" style="color:#4cc2ff;text-decoration:none">Daily Earth Brief</a> · code at <a href="https://github.com/JannoLouwrens/WorldTwin" target="_blank" style="color:#4cc2ff;text-decoration:none">GitHub</a>. Your view is always shareable — the URL follows what you see.
          </span>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:20px 0">
          <div style="background:rgba(76,194,255,0.08);border:1px solid rgba(76,194,255,0.25);border-radius:12px;padding:14px">
            <div style="font-size:11px;color:#4cc2ff;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Hover</div>
            <div style="font-weight:600;margin-bottom:4px">A country</div>
            <div style="color:#b8c1d1;font-size:12px;line-height:1.5">See its value for the active mapmode (GDP, religion, etc.) in a small tooltip.</div>
          </div>
          <div style="background:rgba(76,194,255,0.08);border:1px solid rgba(76,194,255,0.25);border-radius:12px;padding:14px">
            <div style="font-size:11px;color:#4cc2ff;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Click</div>
            <div style="font-weight:600;margin-bottom:4px">Anything</div>
            <div style="color:#b8c1d1;font-size:12px;line-height:1.5">Country → deep dive. Quake / fire / port / satellite → details + source link.</div>
          </div>
          <div style="background:rgba(168,85,247,0.08);border:1px solid rgba(168,85,247,0.3);border-radius:12px;padding:14px">
            <div style="font-size:11px;color:#a855f7;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Scrub</div>
            <div style="font-weight:600;margin-bottom:4px">The bottom timeline</div>
            <div style="color:#b8c1d1;font-size:12px;line-height:1.5">Drag back to 2000 BC. Borders, base imagery, religion, GDP all change with year. Press <b>Live</b> to return.</div>
          </div>
          <div style="background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.3);border-radius:12px;padding:14px">
            <div style="font-size:11px;color:#22c55e;letter-spacing:0.14em;text-transform:uppercase;margin-bottom:6px">Press L</div>
            <div style="font-weight:600;margin-bottom:4px">Open the Browse panel</div>
            <div style="color:#b8c1d1;font-size:12px;line-height:1.5">85 layers + mapmodes. Search, toggle, opacity. Color the world by anything.</div>
          </div>
        </div>

        <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:14px;display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#8c95aa">
          <div>
            <span style="display:inline-block;background:rgba(255,255,255,0.06);padding:3px 8px;border-radius:4px;margin-right:6px;font-family:ui-monospace,monospace">?</span> help
            <span style="display:inline-block;background:rgba(255,255,255,0.06);padding:3px 8px;border-radius:4px;margin:0 6px 0 14px;font-family:ui-monospace,monospace">L</span> browse
            <span style="display:inline-block;background:rgba(255,255,255,0.06);padding:3px 8px;border-radius:4px;margin:0 6px 0 14px;font-family:ui-monospace,monospace">T</span> hide timeline
            <span style="display:inline-block;background:rgba(255,255,255,0.06);padding:3px 8px;border-radius:4px;margin:0 6px 0 14px;font-family:ui-monospace,monospace">R</span> reset camera
          </div>
          <button id="twOnboardGo" style="
            background: #4cc2ff; color: #000; font-weight:600;
            border:0; border-radius:8px; padding:9px 22px; cursor:pointer;
            font-size:12px; letter-spacing:0.08em; text-transform:uppercase;
          ">Explore</button>
        </div>
      </div>
    `;
    document.body.appendChild(el);
    el.querySelector('#twOnboardClose').onclick = () => hide();
    el.querySelector('#twOnboardGo').onclick = () => hide();
    el.onclick = (e) => { if (e.target === el) hide(); };
    return el;
  }
  function show() {
    const el = build();
    el.style.display = 'flex';
    requestAnimationFrame(() => { el.style.opacity = '1'; });
  }
  function hide() {
    const el = document.getElementById('twOnboard');
    if (!el) return;
    el.style.opacity = '0';
    setTimeout(() => { el.style.display = 'none'; }, 350);
    try { localStorage.setItem('tw_onboarded_v2', '1'); } catch (_) {}
  }
  function maybeShowOnFirstVisit() {
    try {
      if (localStorage.getItem('tw_onboarded_v2') === '1') return;
    } catch (_) {}
    setTimeout(show, 1200);
  }

  document.addEventListener('keydown', e => {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === '?' || (e.key === '/' && e.shiftKey)) show();
    if (e.key === 'Escape') hide();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', maybeShowOnFirstVisit);
  } else {
    maybeShowOnFirstVisit();
  }
  window.showOnboarding = show;
})();
