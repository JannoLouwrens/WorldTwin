import type { Envelope, Health, LoadedLayer, Manifest, Point } from './types'

/** Served from the same origin as the aggregator, so relative paths work in
 *  both the dev proxy and production. */
export const CACHE = '/api/cache/v1'

const layerCache = new Map<string, Promise<LoadedLayer>>()

export function isPoint(v: unknown): v is Point {
  if (typeof v !== 'object' || v === null) return false
  const p = v as Record<string, unknown>
  return typeof p.lat === 'number' && typeof p.lon === 'number' && Number.isFinite(p.lat) && Number.isFinite(p.lon)
}

/** Pull the point list out of an envelope. Most layers put a flat array in
 *  `data`; a few wrap it in an object. This finds the first array of
 *  point-shaped things — fine for single-collection payloads, UNSAFE for
 *  multi-collection ones (cloudflare_radar), which declare an explicit
 *  extractor in the registry instead. */
export function extractPoints(data: unknown): Point[] {
  if (Array.isArray(data)) return data.filter(isPoint)
  if (typeof data === 'object' && data !== null) {
    for (const value of Object.values(data as Record<string, unknown>)) {
      if (Array.isArray(value)) {
        const pts = value.filter(isPoint)
        if (pts.length) return pts
      }
    }
  }
  return []
}

/** A tombstone is a layer retired ON PURPOSE — state 'retired', empty data,
 *  and a stated reason. Returns the reason, or null for a live envelope. */
export function tombstoneReason(payload: unknown): string | null {
  if (typeof payload !== 'object' || payload === null) return null
  const p = payload as Record<string, unknown>
  if (p.state !== 'retired') return null
  const reason = p.retired_reason ?? p.reason
  return typeof reason === 'string' && reason ? reason : 'retired by the operator'
}

/** One place turns an envelope into what the UI holds, so tombstones are
 *  treated identically no matter which loader met them: empty points, the
 *  reason kept for the sheet row. Never hides, never pretends. */
export function envelopeToLoaded(env: Envelope, extract?: (data: unknown) => Point[]): LoadedLayer {
  const base = {
    source: env.source ?? '',
    sourceUrl: env.source_url ?? '',
    fetchedAt: env.fetched_at ?? null,
    expiresAt: env.expires_at ?? null,
  }
  const reason = tombstoneReason(env)
  if (reason) return { ...base, points: [], count: 0, retired: { reason } }
  const points = (extract ?? extractPoints)(env.data)
  return { ...base, points, count: env.count ?? points.length }
}

/** Load a layer's full payload. No render cap and no client-side truncation:
 *  layers too large to ship whole come through lib/renderSlice as an
 *  area-weighted density grid instead of a silently-sampled point list. */
export async function loadLayer(id: string, extract?: (data: unknown) => Point[]): Promise<LoadedLayer> {
  const existing = layerCache.get(id)
  if (existing) return existing

  const promise = (async (): Promise<LoadedLayer> => {
    // No `cache: 'no-store'`: Caddy emits correct ETag/Last-Modified, so a
    // returning visitor gets a ~200-byte 304 instead of megabytes.
    const res = await fetch(`${CACHE}/${id}.json`)
    if (!res.ok) throw new Error(`${id}: HTTP ${res.status}`)
    const env = (await res.json()) as Envelope
    return envelopeToLoaded(env, extract)
  })()

  layerCache.set(id, promise)
  // A failed load must not be cached forever, or the layer can never recover.
  promise.catch(() => layerCache.delete(id))
  return promise
}

let manifestPromise: Promise<Manifest> | null = null

/** The pipeline's ledger. 404 is an EXPECTED state (pre-deploy window) — every
 *  consumer must degrade: the counter falls back to /api/health-derived
 *  counts, the render-slice loader falls back to envelope metadata. */
export function loadManifest(refresh = false): Promise<Manifest> {
  if (!refresh && manifestPromise) return manifestPromise
  const promise = (async (): Promise<Manifest> => {
    const res = await fetch(`${CACHE}/manifest.json`)
    if (!res.ok) throw new Error(`manifest: HTTP ${res.status}`)
    const m = (await res.json()) as Manifest
    if (typeof m !== 'object' || m === null || typeof m.counts !== 'object' || !Array.isArray(m.layers)) {
      throw new Error('manifest: unexpected shape')
    }
    return m
  })()
  manifestPromise = promise
  promise.catch(() => {
    if (manifestPromise === promise) manifestPromise = null
  })
  return promise
}

export async function loadHealth(): Promise<Health> {
  const res = await fetch('/api/health', { cache: 'no-store' })
  if (!res.ok) throw new Error(`health: HTTP ${res.status}`)
  return (await res.json()) as Health
}

/** "3m ago" / "2d ago". Absolute time is always available in the tooltip; this
 *  is the at-a-glance form. */
export function relTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (!Number.isFinite(then)) return '—'
  const s = (Date.now() - then) / 1000
  if (s < 60) return `${Math.max(0, Math.round(s))}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}
