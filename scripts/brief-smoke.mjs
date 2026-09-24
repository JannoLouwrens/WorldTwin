#!/usr/bin/env node
// brief-smoke.mjs — do the doctrine surfaces actually render?
//
// Loads the brief archive index, today's brief page, the charter and the
// status ledger in a real browser; asserts zero console errors, the promise
// line, a computed 4-number counts line, and the destroyed-range disclosure.
// Then fetches feed.xml and asserts it parses as XML with <rss> and only
// dated items.
//
// Usage:
//   node scripts/brief-smoke.mjs
//   BASE=https://worldtwin.duckdns.org node scripts/brief-smoke.mjs
//   BRIEF_DATE=2026-09-25 node scripts/brief-smoke.mjs   # non-today brief page
//
// Exit 0 if every check passes, 1 otherwise. PASS/FAIL printed per check.
// Browsers live on /data, not root — root sits ~83% full and a ~1 GB
// browser download there once filled the disk on a box hosting paying tenants.
process.env.PLAYWRIGHT_BROWSERS_PATH ||= '/data/caches/ms-playwright'
import { chromium } from 'playwright'

const BASE = (process.env.BASE || 'http://localhost').replace(/\/$/, '')
const TODAY = process.env.BRIEF_DATE || new Date().toISOString().slice(0, 10)

const LAUNCH = { args: ['--no-sandbox', '--disable-dev-shm-usage'] }

let pass = 0
let fail = 0
function check(label, ok, detail = '') {
  if (ok) {
    console.log(`  PASS  ${label}`)
    pass++
  } else {
    console.error(`  FAIL  ${label}${detail ? ` — ${detail}` : ''}`)
    fail++
  }
}

async function loadPage(ctx, url) {
  const page = await ctx.newPage()
  const consoleErrors = []
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200))
  })
  page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 200)))
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await page.waitForTimeout(1500) // let inline fetch-and-render scripts settle
  return { page, consoleErrors, status: resp ? resp.status() : 0 }
}

const browser = await chromium.launch(LAUNCH)
const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })

try {
  // 1. Brief archive index
  {
    const url = `${BASE}/worldtwin/brief/`
    console.log(`\n=== ${url} ===`)
    const { page, consoleErrors, status } = await loadPage(ctx, url)
    check('index responds 200', status === 200, `status ${status}`)
    check('index has zero console errors', consoleErrors.length === 0, consoleErrors.join(' | '))
    const body = await page.content()
    check('index lists a dated brief', /\d{4}-\d{2}-\d{2}\.html/.test(body))
    check('index carries the record-start note',
      body.includes('destroyed on 9 August 2026'))
    await page.close()
  }

  // 2. Today's brief page
  {
    const url = `${BASE}/worldtwin/brief/${TODAY}.html`
    console.log(`\n=== ${url} ===`)
    const { page, consoleErrors, status } = await loadPage(ctx, url)
    check(`brief ${TODAY} responds 200`, status === 200, `status ${status}`)
    check('brief has zero console errors', consoleErrors.length === 0, consoleErrors.join(' | '))
    const body = await page.content()
    check("brief contains 'What the instruments said'",
      body.includes('What the instruments said'))
    check('brief links its citable JSON', body.includes(`${TODAY}.json`))
    await page.close()
  }

  // 3. Charter
  {
    const url = `${BASE}/worldtwin/charter.html`
    console.log(`\n=== ${url} ===`)
    const { page, consoleErrors, status } = await loadPage(ctx, url)
    check('charter responds 200', status === 200, `status ${status}`)
    check('charter has zero console errors', consoleErrors.length === 0, consoleErrors.join(' | '))
    const body = await page.content()
    check('charter discloses the destroyed range',
      body.includes('11 June') && body.includes('9 August 2026') &&
      body.includes('destroyed on') && body.includes('restarts on 24 September 2026'))
    check('charter states the five rules',
      body.includes('Every number carries its source and its timestamp') &&
      body.includes('The record is permanent'))
    await page.close()
  }

  // 4. Status — computed counts line with 4 numbers
  {
    const url = `${BASE}/worldtwin/status.html`
    console.log(`\n=== ${url} ===`)
    const { page, consoleErrors, status } = await loadPage(ctx, url)
    check('status responds 200', status === 200, `status ${status}`)
    const countsRe = /\d+ live · \d+ stale · \d+ dead · \d+ retired of \d+/
    let countsText = ''
    try {
      await page.waitForFunction(
        (reSrc) => new RegExp(reSrc).test(document.getElementById('countsLine')?.textContent || ''),
        countsRe.source, { timeout: 15_000 })
      countsText = await page.locator('#countsLine').textContent()
    } catch { /* falls through to the check */ }
    check('status renders a computed counts line with 4 numbers',
      countsRe.test(countsText || ''), `saw "${countsText}"`)
    check('status renders layer rows', (await page.locator('tbody tr').count()) > 0)
    check('status has zero console errors', consoleErrors.length === 0, consoleErrors.join(' | '))
    await page.close()
  }

  // 5. feed.xml — parses as XML, is RSS, only dated items
  {
    const url = `${BASE}/worldtwin/brief/feed.xml`
    console.log(`\n=== ${url} ===`)
    const resp = await ctx.request.get(url)
    check('feed responds 200', resp.status() === 200, `status ${resp.status()}`)
    const xml = resp.ok() ? await resp.text() : ''
    check('feed contains <rss', xml.includes('<rss'))
    // Parse with the browser's real XML parser — a regex is not a parser.
    const page = await ctx.newPage()
    const parsed = await page.evaluate((src) => {
      const doc = new DOMParser().parseFromString(src, 'application/xml')
      if (doc.querySelector('parsererror')) return { ok: false, reason: 'parsererror' }
      const links = [...doc.querySelectorAll('item > link')].map((n) => n.textContent || '')
      const pubs = [...doc.querySelectorAll('item > pubDate')].map((n) => n.textContent || '')
      return { ok: true, nItems: links.length, links, pubs }
    }, xml)
    check('feed parses as XML', parsed.ok === true, parsed.reason || '')
    if (parsed.ok) {
      check('feed has at least one item', parsed.nItems > 0)
      const allDated = parsed.links.every((l) => /\/\d{4}-\d{2}-\d{2}\.html$/.test(l)) &&
        parsed.pubs.every((p) => !Number.isNaN(Date.parse(p)))
      check('every feed item is a dated brief with a valid pubDate', allDated,
        parsed.links.filter((l) => !/\/\d{4}-\d{2}-\d{2}\.html$/.test(l)).join(', '))
      const allAbsolute = parsed.links.every((l) =>
        l.startsWith('https://worldtwin.duckdns.org/worldtwin/brief/'))
      check('every feed link is absolute on the canonical host', allAbsolute)
    }
    await page.close()
  }
} catch (e) {
  check('suite completed without throwing', false, String(e).split('\n')[0].slice(0, 200))
} finally {
  await browser.close()
}

console.log(`\n[brief-smoke] ${pass} passed, ${fail} failed`)
process.exit(fail > 0 ? 1 : 0)
