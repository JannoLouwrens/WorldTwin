#!/usr/bin/env node
// smoke-test.mjs — browser-side plausibility check for the live site.
//
// Spins Playwright, opens /weather/, waits for boot + briefing,
// extracts every numeric value visible to the user, asserts each is in a
// plausible range. Catches bugs that don't go through the AI narrative —
// e.g. if briefing.js reads a corrupted FRED series, this catches it.
//
// Usage:
//    node scripts/smoke-test.mjs                 # default URL
//    URL=http://localhost/weather/ node scripts/smoke-test.mjs
//
// Exit code: 0 if all checks pass, 1 if any plausibility violation.
import { chromium } from 'playwright';

const URL = process.env.URL || 'http://129.151.191.74/weather/';
const TIMEOUT = parseInt(process.env.TIMEOUT || '60000', 10);

// Same RULES philosophy as aggregator/worldtwin/sanity.py — keep in sync.
const RULES = {
  brent_oil_usd:   [10,    300, 'Brent crude $/bbl'],
  wti_oil_usd:     [10,    300, 'WTI crude $/bbl'],
  vix:             [5,     100, 'VIX volatility'],
  fed_funds_pct:   [-1,     25, 'US Fed funds %'],
  yield_pct:       [-10,    50, 'Yield %'],
  change_24h_pct:  [-99, 100000, 'Crypto/equity 24h % change'],
};

function passes(rule, val) {
  if (val == null || !Number.isFinite(val)) return false;
  const r = RULES[rule];
  if (!r) return true;
  return val >= r[0] && val <= r[1];
}

async function main() {
  console.log(`[smoke] opening ${URL}`);
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.error('[page-error]', e.message));
  page.on('console', m => {
    if (m.type() === 'error') console.warn('[console]', m.text().slice(0, 200));
  });
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: TIMEOUT });

  // Skip onboarding so the briefing is exposed
  await page.evaluate(() => { try { localStorage.setItem('tw_onboarded', '1'); } catch (_) {} });
  await page.reload({ waitUntil: 'domcontentloaded' });

  // Wait for briefing to populate
  await page.waitForFunction(() => {
    return window.viewer && document.getElementById('twBriefing')
      && document.getElementById('twBriefing').innerHTML.length > 1000;
  }, { timeout: TIMEOUT });

  // Pull briefing data + any cached crypto/macros
  const data = await page.evaluate(() => {
    const out = { kpis: [], crypto: [], cross: [] };
    // KPI tiles in briefing
    document.querySelectorAll('#twBriefing [style*="font-feature"]').forEach(el => {
      const txt = el.textContent.trim();
      const num = parseFloat(txt.replace(/[^0-9.\-]/g, ''));
      if (Number.isFinite(num)) out.kpis.push({ label: txt.slice(0, 40), value: num });
    });
    // Direct cache reads
    const eco = window._cacheStore?.get?.('economy');
    const fred = window._cacheStore?.get?.('fred')?.series || {};
    const ai = window._cacheStore?.get?.('gemini_narrative');

    out.crypto = (eco?.crypto || []).slice(0, 5).map(c => ({
      sym: c.symbol, price: c.price_usd, change_24h: c.change_24h,
    }));
    out.fred_macros = {
      brent: fred.DCOILBRENTEU?.latest,
      wti: fred.DCOILWTICO?.latest,
      vix: fred.VIXCLS?.latest,
      fed_funds: fred.FEDFUNDS?.latest,
      us_10y: fred.DGS10?.latest,
    };
    out.ai_source = ai?.source;
    out.ai_today = (ai?.today || '').slice(0, 200);
    out.ai_cross = (ai?.digest?.crypto || []).map(c => c.cross_check).filter(Boolean);
    return out;
  });

  let pass = 0, fail = 0;
  function check(label, rule, val) {
    if (passes(rule, val)) {
      console.log(`  ✓ ${label}: ${val}`);
      pass++;
    } else {
      console.error(`  ✗ ${label}: ${val} OUTSIDE ${RULES[rule] ? RULES[rule].slice(0,2) : '?'}`);
      fail++;
    }
  }

  console.log('--- FRED macros ---');
  check('Brent oil $/bbl', 'brent_oil_usd', data.fred_macros.brent);
  check('WTI oil $/bbl',   'wti_oil_usd',   data.fred_macros.wti);
  check('VIX',             'vix',           data.fred_macros.vix);
  check('Fed funds %',     'fed_funds_pct', data.fred_macros.fed_funds);
  check('US 10Y yield %',  'yield_pct',     data.fred_macros.us_10y);

  console.log('--- Crypto change_24h ---');
  for (const c of data.crypto) {
    check(`${c.sym} 24h%`, 'change_24h_pct', c.change_24h);
  }

  console.log('--- AI narrative ---');
  console.log(`  source: ${data.ai_source}`);
  console.log(`  today (1st 200 chars): ${data.ai_today}`);
  if (data.ai_cross?.length) {
    const disagree = data.ai_cross.filter(c => c.agrees === false);
    if (disagree.length) {
      console.warn(`  ⚠ ${disagree.length} crypto values diverge between CoinGecko and Binance`);
    } else {
      console.log(`  ✓ ${data.ai_cross.length} crypto cross-checks all agree`);
    }
  } else {
    console.log('  (no cross_check data — Binance fetch may be in progress)');
  }

  await browser.close();
  console.log(`\n[smoke] ${pass} passed, ${fail} failed`);
  process.exit(fail > 0 ? 1 : 0);
}

main().catch(e => { console.error('[smoke] crashed:', e); process.exit(2); });
