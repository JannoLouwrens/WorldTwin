/**
 * Render-slice loader for oversized point layers (fires).
 *
 * The backend publishes `{id}.render.json`: an area-weighted density grid
 * (mode "bins", each row `[lat, lon, weight]`, weight already cos(lat)
 * corrected) sized to a ~120 KB gz budget. The global view of a large layer is
 * an AGGREGATE, not a top-K sample — top-4,000-by-FRP covers 5.9% of burning
 * area; a 0.25° grid covers 100% of it at 68 KB.
 *
 * Fallback ladder, each step honest about what it is:
 *   1. `{id}.render.json`   — bins → circles sized by the cos-weighted value.
 *   2. `{id}.json` in full  — ONLY if its wire size is acceptable.
 *   3. A thrown error       — surfaced by name in the layer sheet row.
 * Tombstones at any step render as an empty row with the stated reason.
 */

import { CACHE, envelopeToLoaded, loadManifest, tombstoneReason } from './api'
import type { BinsMeta, Envelope, LoadedLayer, ManifestLayer, Point } from './types'

/** Ceiling for step 2, in WIRE bytes (Content-Length — post-gzip when Caddy
 *  serves the precompressed sidecar). Matches the plan's budget of "any single
 *  layer payload ≤ the shell (374 KB gz)". Above this, no slice means no
 *  layer — with the refusal stated, not a 15 MB download on a phone. */
const MAX_FALLBACK_BYTES = 400_000

interface BinsSlice extends BinsMeta {
  bins: Array<[number, number, number]>
}

function asBinsSlice(v: unknown): BinsSlice | null {
  if (typeof v !== 'object' || v === null) return null
  const s = v as Record<string, unknown>
  if (s.mode !== 'bins' || !Array.isArray(s.bins)) return null
  if (typeof s.cell_deg !== 'number' || !Number.isFinite(s.cell_deg)) return null
  const rows = s.bins.filter(
    (r): r is [number, number, number] =>
      Array.isArray(r) && r.length >= 3 && r.slice(0, 3).every((x) => typeof x === 'number' && Number.isFinite(x)),
  )
  return {
    cellDeg: s.cell_deg,
    n: typeof s.n === 'number' && Number.isFinite(s.n) ? s.n : rows.length,
    shown: typeof s.shown === 'number' && Number.isFinite(s.shown) ? s.shown : rows.length,
    selection: typeof s.selection === 'string' ? s.selection : 'aggregate',
    bins: rows,
  }
}

/** Bins → points. `value` is normalized 0–1 (drives circle radius); the raw
 *  cos-weighted weight and the cell size ride along for the detail card. */
function binPoints(slice: BinsSlice): Point[] {
  let max = 0
  for (const [, , w] of slice.bins) max = Math.max(max, w)
  return slice.bins.map(([lat, lon, weight]) => ({
    lat,
    lon,
    value: max > 0 ? weight / max : 0,
    props: { weight, cell_deg: slice.cellDeg },
  }))
}

function fromSlice(slice: BinsSlice, body: unknown, entry: ManifestLayer | null): LoadedLayer {
  // The slice may arrive bare or wrapped in the standard envelope. Prefer the
  // envelope's own metadata; fall back to the manifest's entry for this layer;
  // degrade to nulls (which freshness treats as stale, not fresh).
  const env = (typeof body === 'object' && body !== null ? body : {}) as Partial<Envelope>
  // Manifest rows carry source as a nested {name, url} object — never hand an
  // object to a React child; normalize both shapes to flat strings here.
  const s = entry?.source
  const entryName = typeof s === 'string' ? s : (s?.name ?? '')
  const entryUrl = typeof s === 'object' && s !== null ? (s.url ?? '') : (entry?.source_url ?? '')
  return {
    points: binPoints(slice),
    source: env.source ?? entryName,
    sourceUrl: env.source_url ?? entryUrl,
    fetchedAt: env.fetched_at ?? entry?.fetched_at ?? null,
    expiresAt: env.expires_at ?? entry?.expires_at ?? null,
    count: slice.shown,
    bins: { cellDeg: slice.cellDeg, n: slice.n, shown: slice.shown, selection: slice.selection },
  }
}

async function fallbackFull(id: string): Promise<LoadedLayer> {
  const res = await fetch(`${CACHE}/${id}.json`)
  if (!res.ok) throw new Error(`${id}: HTTP ${res.status}`)
  const len = Number(res.headers.get('content-length') ?? '0')
  if (len > MAX_FALLBACK_BYTES) {
    throw new Error(`full payload is ${(len / 1e6).toFixed(1)} MB and no render slice exists — not sending that to a phone`)
  }
  const env = (await res.json()) as Envelope
  return envelopeToLoaded(env)
}

async function load(id: string): Promise<LoadedLayer> {
  // Manifest metadata is optional garnish here — its absence must never block
  // the layer (pre-deploy window, or a manifest write race).
  const entry = await loadManifest()
    .then((m) => m.layers.find((l) => l.id === id) ?? null)
    .catch(() => null)

  try {
    const res = await fetch(`${CACHE}/${id}.render.json`)
    if (res.ok) {
      const body: unknown = await res.json()
      if (tombstoneReason(body)) return envelopeToLoaded(body as Envelope)
      const slice =
        asBinsSlice(body) ??
        (typeof body === 'object' && body !== null ? asBinsSlice((body as { data?: unknown }).data) : null)
      if (slice) return fromSlice(slice, body, entry)
      // Unrecognized shape — fall through to the full payload.
    }
  } catch {
    // 404, network, or parse failure — the fallback decides what is honest.
  }
  return fallbackFull(id)
}

const sliceCache = new Map<string, Promise<LoadedLayer>>()

export function loadSliced(id: string): Promise<LoadedLayer> {
  const existing = sliceCache.get(id)
  if (existing) return existing
  const promise = load(id)
  sliceCache.set(id, promise)
  promise.catch(() => sliceCache.delete(id))
  return promise
}
