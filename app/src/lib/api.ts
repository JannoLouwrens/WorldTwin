import type { Envelope, Health, LoadedLayer, Point } from './types'

/** Served from the same origin as the aggregator, so relative paths work in
 *  both the dev proxy and production. */
const CACHE = '/api/cache/v1'

/** Layers whose payload is far too large to hand a phone whole. The cap is
 *  applied after sorting by `value` so what survives is the significant end,
 *  and the UI states the number it dropped rather than implying full coverage.
 *  (fires alone is 85k points / 14.8 MB raw.) */
const RENDER_CAP: Record<string, number> = {
  fires: 4000,
  flights: 3000,
  volcanoes: 1500,
}

const cache = new Map<string, Promise<LoadedLayer>>()

function isPoint(v: unknown): v is Point {
  if (typeof v !== 'object' || v === null) return false
  const p = v as Record<string, unknown>
  return typeof p.lat === 'number' && typeof p.lon === 'number' && Number.isFinite(p.lat) && Number.isFinite(p.lon)
}

/** Pull the point list out of an envelope. Most layers put a flat array in
 *  `data`; a few wrap it in an object (gdacs_events uses `data.events`). Rather
 *  than special-casing each one, find the first array of point-shaped things. */
function extractPoints(data: unknown): Point[] {
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

export async function loadLayer(id: string): Promise<LoadedLayer> {
  const existing = cache.get(id)
  if (existing) return existing

  const promise = (async (): Promise<LoadedLayer> => {
    const res = await fetch(`${CACHE}/${id}.json`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`${id}: HTTP ${res.status}`)
    const env = (await res.json()) as Envelope

    let points = extractPoints(env.data)
    const total = points.length
    const cap = RENDER_CAP[id]
    let truncatedFrom: number | undefined

    if (cap && total > cap) {
      points = [...points].sort((a, b) => (b.value ?? 0) - (a.value ?? 0)).slice(0, cap)
      truncatedFrom = total
    }

    return {
      points,
      source: env.source,
      sourceUrl: env.source_url,
      fetchedAt: env.fetched_at,
      count: env.count ?? total,
      truncatedFrom,
    }
  })()

  cache.set(id, promise)
  // A failed load must not be cached forever, or the layer can never recover.
  promise.catch(() => cache.delete(id))
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
