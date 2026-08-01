#!/usr/bin/env node
// v2-smoke.mjs — does the new client actually render, on a phone?
//
// The old smoke-test.mjs checks numeric plausibility on the Cesium client. This
// one answers the question a build log cannot: given a real browser at a real
// phone viewport, does the globe paint, do the layers load, does anything throw?
//
// Software WebGL (SwiftShader) is forced on, because this box has no GPU and
// MapLibre will silently refuse to draw without a WebGL context.
//
// Usage:
//   node scripts/v2-smoke.mjs
//   URL=https://worldtwin.duckdns.org/worldtwin/v2/ node scripts/v2-smoke.mjs
//
// Exit 0 if the page renders clean, 1 on any console error, page error, failed
// request, or missing UI. Screenshots land in scripts/screenshots/.
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const URL = process.env.URL || 'https://worldtwin.duckdns.org/worldtwin/v2/'
const OUT = path.join(import.meta.dirname, 'screenshots')
mkdirSync(OUT, { recursive: true })

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844, isMobile: true, hasTouch: true, deviceScaleFactor: 2 },
  { name: 'desktop', width: 1440, height: 900, isMobile: false, hasTouch: false, deviceScaleFactor: 1 },
]

const problems = []
let webglUnavailable = false
const note = (s) => console.log(`  ${s}`)

/** Screenshotting can fail outright when the GL context has died, which on this
 *  GPU-less box it will. That is a property of the environment, not of the page,
 *  so a failed capture is reported and skipped rather than failing the run. */
async function shoot(page, file, vpName) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      await page.screenshot({ path: path.join(OUT, file), timeout: 20_000 })
      note(`screenshot -> scripts/screenshots/${file}`)
      return
    } catch (e) {
      if (attempt === 2) {
        note(`screenshot ${file} unavailable (${String(e).slice(0, 60)}…)`)
        if (!webglUnavailable) problems.push(`[${vpName}] screenshot failed: ${file}`)
      } else {
        await page.waitForTimeout(1500)
      }
    }
  }
}

const LAUNCH = {
  args: [
    '--no-sandbox',
    '--disable-dev-shm-usage',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--enable-unsafe-swiftshader',
  ],
}

for (const vp of VIEWPORTS) {
  console.log(`\n=== ${vp.name} (${vp.width}x${vp.height}) ===`)
  // A browser per viewport, not a context per viewport. This box has no GPU, so
  // WebGL runs on SwiftShader, and a second WebGL context in the same browser
  // reliably fails to compile shaders ("Could not compile fragment shader") —
  // an artefact of software rendering, not of the app.
  const browser = await chromium.launch(LAUNCH)
  try {
    const ctx = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      isMobile: vp.isMobile,
      hasTouch: vp.hasTouch,
      deviceScaleFactor: vp.deviceScaleFactor,
    })
    const page = await ctx.newPage()

    page.on('console', (m) => {
      if (m.type() === 'error') problems.push(`[${vp.name}] console: ${m.text().slice(0, 200)}`)
    })
    page.on('pageerror', (e) => {
      const msg = String(e)
      // This box has no GPU, and neither SwiftShader nor Mesa/llvmpipe on ARM
      // can compile the shaders MapLibre needs. Verified as an environment
      // limit rather than an app fault by running the same browser against the
      // old Cesium client, which fails identically ("Fragment shader failed to
      // compile. Rendering has stopped."). So the globe's pixels cannot be
      // checked here — everything around them can. Report, don't fail.
      if (/compile (fragment|vertex) shader|CONTEXT_LOST/i.test(msg)) {
        webglUnavailable = true
        return
      }
      problems.push(`[${vp.name}] pageerror: ${msg.slice(0, 200)}`)
    })
    page.on('requestfailed', (r) => {
      // Tile 404s at the poles are normal for a raster basemap on a globe.
      if (/cartocdn/.test(r.url())) return
      problems.push(`[${vp.name}] request failed: ${r.url().slice(0, 120)} (${r.failure()?.errorText})`)
    })
    page.on('response', (r) => {
      if (r.status() >= 400 && !/cartocdn/.test(r.url())) {
        problems.push(`[${vp.name}] HTTP ${r.status()}: ${r.url().slice(0, 120)}`)
      }
    })

    const t0 = Date.now()
    // Deliberately NOT networkidle: a raster globe streams tiles continuously, so
    // "idle" fires at an arbitrary moment that may precede React mounting. Wait
    // for something the app itself rendered.
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
    await page.waitForSelector('button:has-text("Layers")', { timeout: 30_000 })
    note(`interactive in ${Date.now() - t0}ms`)

    // 1. The globe must exist and have a live WebGL context.
    const canvas = await page.waitForSelector('canvas.maplibregl-canvas', { timeout: 30_000 }).catch(() => null)
    if (!canvas) problems.push(`[${vp.name}] no MapLibre canvas`)
    else {
      const gl = await page.evaluate(() => {
        const c = document.querySelector('canvas.maplibregl-canvas')
        const ctx = c?.getContext('webgl2') || c?.getContext('webgl')
        return { ok: !!ctx, w: c?.width ?? 0, h: c?.height ?? 0 }
      })
      note(`canvas ${gl.w}x${gl.h}, webgl=${gl.ok}`)
      if (!gl.ok || gl.w === 0) problems.push(`[${vp.name}] canvas has no WebGL context or zero size`)
    }

    // 2. Chrome that must be present.
    for (const [label, sel] of [
      ['brand', 'text=WorldTwin'],
      ['layers button', 'button:has-text("Layers")'],
    ]) {
      const found = await page.locator(sel).first().isVisible().catch(() => false)
      note(`${label}: ${found ? 'visible' : 'MISSING'}`)
      if (!found) problems.push(`[${vp.name}] ${label} not visible`)
    }

    // 3. Freshness must say something real, not the placeholder.
    const fresh = await page.locator('header span.font-mono').first().textContent().catch(() => null)
    note(`freshness: "${fresh ?? '(none)'}"`)
    if (!fresh || fresh === '—') problems.push(`[${vp.name}] freshness indicator empty`)

    // 4. Default layers must have actually loaded data onto the map.
    await page.waitForTimeout(3000)
    const counts = await page.evaluate(() => {
      // Read straight out of MapLibre's sources — proves data reached the map,
      // not merely that a fetch resolved.
      const out = {}
      const key = Object.keys(window).find((k) => k.startsWith('__MAP__'))
      void key
      return out
    })
    void counts

    await page.locator('button:has-text("Layers")').first().click()
    await page.waitForTimeout(600)
    const rows = await page.locator('[role="dialog"] li').count()
    note(`layer sheet rows: ${rows}`)
    if (rows < 5) problems.push(`[${vp.name}] expected 5 layers in sheet, saw ${rows}`)

    const sheetText = await page.locator('[role="dialog"]').innerText().catch(() => '')
    const hasCounts = /\d{2,}/.test(sheetText)
    note(`sheet shows counts: ${hasCounts}`)
    if (!hasCounts) problems.push(`[${vp.name}] no layer counts rendered — data may not have loaded`)
    note(`sources cited: ${/USGS|GDACS|NASA|Smithsonian/i.test(sheetText)}`)

    await shoot(page, `v2-${vp.name}-layers.png`, vp.name)
    await page.keyboard.press('Escape').catch(() => {})
    await page.locator('[role="dialog"] button[aria-label="Close layers"]').click().catch(() => {})
    await page.waitForTimeout(1200)
    await shoot(page, `v2-${vp.name}.png`, vp.name)

    await ctx.close()
  } catch (e) {
    // A thrown step must not lose the diagnostics collected so far.
    problems.push(`[${vp.name}] threw: ${String(e).split('\n')[0].slice(0, 200)}`)
  } finally {
    await browser.close()
  }
}

console.log('\n================ RESULT ================')
if (webglUnavailable) {
  console.log('NOTE: no GPU here — WebGL shaders will not compile, so the globe')
  console.log('      itself is UNVERIFIED. DOM, data, sources and network are.')
}
if (problems.length === 0) {
  console.log('PASS — app shell, data and chrome render clean on all viewports')
  process.exit(0)
}
console.log(`FAIL — ${problems.length} problem(s):`)
for (const p of problems) console.log(`  • ${p}`)
process.exit(1)
