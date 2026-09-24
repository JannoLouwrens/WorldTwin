#!/usr/bin/env node
// shoot-globe.mjs — capture the globe as it actually renders.
//
// This box has no GPU. Headless Chromium falls back to SwiftShader, which
// cannot compile the shaders MapLibre (or Cesium) needs — so headless captures
// come back black. Under Xvfb with a real X display, Chromium reaches Mesa's
// llvmpipe rasteriser and gets a genuine WebGL 2.0 context:
//   ANGLE (Mesa, llvmpipe (LLVM 21.1.8 128 bits), OpenGL 4.5)
// Software rasterisation is slow, hence the long settle time before capture.
//
//   Xvfb :99 -screen 0 1600x1200x24 &
//   DISPLAY=:99 LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe node scripts/shoot-globe.mjs
// Browsers live on /data, not root — root sits ~83% full and a ~1 GB
// browser download there once filled the disk on a box hosting paying tenants.
process.env.PLAYWRIGHT_BROWSERS_PATH ||= '/data/caches/ms-playwright'
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import path from 'node:path'

const URL = process.env.URL || 'https://worldtwin.duckdns.org/worldtwin/v2/'
const SETTLE = parseInt(process.env.SETTLE || '35000', 10)
const OUT = path.join(import.meta.dirname, 'screenshots')
mkdirSync(OUT, { recursive: true })

const SHOTS = [
  { name: 'mobile', width: 390, height: 844, dsf: 2, touch: true },
  { name: 'desktop', width: 1280, height: 800, dsf: 1 },
]

for (const s of SHOTS) {
  const browser = await chromium.launch({
    headless: false,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=angle', '--use-angle=gl', '--ignore-gpu-blocklist'],
  })
  try {
    const page = await (
      await browser.newContext({ viewport: { width: s.width, height: s.height }, deviceScaleFactor: s.dsf, isMobile: !!s.touch, hasTouch: !!s.touch })
    ).newPage()
    const errs = []
    page.on('pageerror', (e) => errs.push(String(e).slice(0, 120)))
    page.on('console', (m) => m.type() === 'error' && errs.push('console: ' + m.text().slice(0, 120)))

    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 90_000 })
    await page.waitForSelector('button:has-text("Layers")', { timeout: 60_000 })
    await page.waitForTimeout(SETTLE)

    const renderer = await page.evaluate(() => {
      const c = document.querySelector('canvas.maplibregl-canvas')
      const g = c?.getContext('webgl2') || c?.getContext('webgl')
      const d = g?.getExtension('WEBGL_debug_renderer_info')
      return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'unknown'
    })
    await page.screenshot({ path: path.join(OUT, `globe-${s.name}.png`), timeout: 60_000 })
    console.log(`${s.name}: ${renderer}`)
    console.log(`  errors: ${errs.slice(0, 3).join(' | ') || 'none'}`)
    console.log(`  -> screenshots/globe-${s.name}.png`)
  } catch (e) {
    console.log(`${s.name}: FAILED ${String(e).split('\n')[0].slice(0, 140)}`)
  } finally {
    await browser.close()
  }
}
