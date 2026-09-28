#!/usr/bin/env node
// brief_card.mjs — render the daily 1200×630 share card for the brief.
//
// Adapted from shoot-globe.mjs. This box has no GPU: headless Chromium falls
// back to SwiftShader and captures come back black. Under a real X display
// (Xvfb) Chromium reaches Mesa's llvmpipe rasteriser and gets genuine WebGL.
// Software rasterisation is slow, hence the long settle before capture.
//
// Cron: 20 6 * * * — BEFORE the 06:47 brief (MASTER_PLAN Stage 4). The card
// is optional by contract: build_brief.py stats the PNG and omits every
// reference when it is absent, so this script may NEVER block the brief —
// on ANY failure it logs `CARD-FAIL …` and the top-level process exits 0.
//
// Self-guards (all in-process, no wrapper needed in the crontab):
//   flock -n /tmp/wt-brief-card.lock   — never two renders at once
//   timeout 300                        — hard wall-clock ceiling
//   nice -n 19                         — idle priority for the Chromium tree
//
// Usage:  node scripts/brief_card.mjs [--date YYYY-MM-DD]   (default: today UTC)
// Output: /home/opc/worldtwin/weather/brief/card/YYYY-MM-DD.png  (0644)

import { spawn, spawnSync } from 'node:child_process'
import { mkdirSync, existsSync, chmodSync, statSync, unlinkSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import os from 'node:os'
import path from 'node:path'

const SELF = fileURLToPath(import.meta.url)
const LOCK = '/tmp/wt-brief-card.lock'
const OUT_DIR = '/home/opc/worldtwin/weather/brief/card'
const URL = process.env.URL || 'http://localhost/worldtwin/v2/?layers=quakes,gdacs_events'
const SETTLE = parseInt(process.env.SETTLE || '30000', 10) // idle wait for llvmpipe
const MIN_BYTES = 30_000 // a black/blank 1200×630 PNG compresses far below this

function cardDate() {
  const i = process.argv.indexOf('--date')
  const d = i >= 0 ? process.argv[i + 1] : new Date().toISOString().slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d || '')) {
    console.log(`CARD-FAIL bad --date ${JSON.stringify(d)} (want YYYY-MM-DD)`)
    process.exit(0) // a bad flag must not block the brief either
  }
  return d
}

// ---------------------------------------------------------------- outer shell
// Re-exec self under flock -n + timeout 300 + nice -n 19. The outer process
// ALWAYS exits 0 — a missing card must never fail the cron chain.
if (!process.env.WT_CARD_INNER) {
  const r = spawnSync(
    'flock', ['-n', LOCK, 'timeout', '300', 'nice', '-n', '19',
      process.execPath, SELF, ...process.argv.slice(2)],
    { stdio: 'inherit', env: { ...process.env, WT_CARD_INNER: '1' } },
  )
  if (r.status !== 0) {
    const why = r.status === null ? `killed by ${r.signal}`
      : r.status === 124 ? 'timeout after 300 s'
        : `exit ${r.status} (lock held by another render, or the render itself failed — see above)`
    console.log(`CARD-FAIL ${new Date().toISOString()} ${why}`)
  }
  process.exit(0)
}

// ---------------------------------------------------------------- inner render
const DATE = cardDate()
const OUT = path.join(OUT_DIR, `${DATE}.png`)

// Browsers live on /data, not root — root sits ~83% full (see shoot-globe.mjs).
process.env.PLAYWRIGHT_BROWSERS_PATH ||= '/data/caches/ms-playwright'
process.env.LIBGL_ALWAYS_SOFTWARE ||= '1'
process.env.GALLIUM_DRIVER ||= 'llvmpipe'
try { os.setPriority(process.pid, 19) } catch { /* already nice'd by the shell */ }

let xvfb = null
async function ensureDisplay() {
  if (process.env.DISPLAY) return
  for (const n of [98, 97, 96, 95]) {
    if (existsSync(`/tmp/.X${n}-lock`)) continue
    xvfb = spawn('Xvfb', [`:${n}`, '-screen', '0', '1280x720x24'], { stdio: 'ignore' })
    for (let i = 0; i < 40 && !existsSync(`/tmp/.X${n}-lock`); i++)
      await new Promise((res) => setTimeout(res, 100))
    if (existsSync(`/tmp/.X${n}-lock`) && xvfb.exitCode === null) {
      process.env.DISPLAY = `:${n}`
      return
    }
    try { xvfb.kill('SIGTERM') } catch { /* already gone */ }
    xvfb = null
  }
  throw new Error('no free X display (:98–:95 all locked) and DISPLAY unset')
}

const { chromium } = await import('playwright')

let browser = null
try {
  await ensureDisplay()
  mkdirSync(OUT_DIR, { recursive: true })
  browser = await chromium.launch({
    headless: false, // headed under Xvfb → llvmpipe, not SwiftShader
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--use-gl=angle',
      '--use-angle=gl', '--ignore-gpu-blocklist'],
  })
  const page = await (await browser.newContext({
    viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1,
  })).newPage()
  const errs = []
  page.on('pageerror', (e) => errs.push(String(e).slice(0, 120)))
  page.on('console', (m) => m.type() === 'error' && errs.push('console: ' + m.text().slice(0, 120)))

  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.waitForSelector('button:has-text("Layers")', { timeout: 60_000 })
  await page.waitForTimeout(SETTLE) // idle settle — near-zero CPU on an idle map

  const renderer = await page.evaluate(() => {
    const c = document.querySelector('canvas.maplibregl-canvas')
    const g = c?.getContext('webgl2') || c?.getContext('webgl')
    const d = g?.getExtension('WEBGL_debug_renderer_info')
    return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'unknown'
  })
  await page.screenshot({ path: OUT, timeout: 60_000 })
  chmodSync(OUT, 0o644) // served by Caddy

  const size = statSync(OUT).size
  if (size < MIN_BYTES) { // black SwiftShader frame or blank page — worse than no card
    unlinkSync(OUT)
    throw new Error(`screenshot only ${size} B (< ${MIN_BYTES}) — likely black; deleted`)
  }
  console.log(`CARD-OK ${DATE} ${OUT} ${size} B 1200x630 renderer=${renderer}`)
  if (errs.length) console.log(`  page errors: ${errs.slice(0, 3).join(' | ')}`)
} catch (e) {
  console.log(`CARD-FAIL ${new Date().toISOString()} date=${DATE} ${String(e).split('\n')[0].slice(0, 200)}`)
  process.exitCode = 1 // outer maps this to exit 0 after logging
} finally {
  try { if (browser) await browser.close() } catch { /* ignore */ }
  if (xvfb) { try { xvfb.kill('SIGTERM') } catch { /* ignore */ } }
}
