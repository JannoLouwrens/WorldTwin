/** The aggregator's v1 envelope. Every layer is served in this shape, which is
 *  why one renderer can handle all of them — see /v1/schema on the API. */
export interface Envelope<T = unknown> {
  id: string
  name: string
  category: string
  kind: string
  source: string
  source_url: string
  license: string
  fetched_at: string
  expires_at?: string
  units?: string | null
  count: number
  data: T
  /** 'retired' on tombstone envelopes — the layer stopped publishing on
   *  purpose, with a stated reason, and `data` is empty. */
  state?: string
  retired_reason?: string
}

/** The point shape every geographic layer uses. */
export interface Point {
  lat: number
  lon: number
  id?: string
  value?: number | null
  label?: string
  props?: Record<string, unknown>
}

export interface LayerHealth {
  ok: boolean
  count: number
  error: string | null
  last_fetch: string | null
}

export interface Health {
  ok: boolean
  time: string
  layers: Record<string, LayerHealth>
}

/** /api/cache/v1/manifest.json — the pipeline's own ledger: every layer,
 *  including tombstones, with a computed state. The header counter reads
 *  `counts` and NOTHING is ever hardcoded from it — when the file does not
 *  exist yet the UI degrades to a health-derived count with no denominator. */
export interface ManifestCounts {
  total: number
  live: number
  stale: number
  dead: number
  retired: number
}

export interface ManifestLayer {
  id: string
  state: string
  fetched_at?: string | null
  expires_at?: string | null
  refresh_s?: number
  last_success_at?: string | null
  retired_reason?: string | null
  // The manifest writer emits source as a nested {name, url} object; older
  // shapes may carry a flat string. Consumers must handle both.
  source?: string | { name?: string; url?: string }
  source_url?: string
  count?: number
}

export interface Manifest {
  generated_at: string
  counts: ManifestCounts
  layers: ManifestLayer[]
}

/** Metadata of a bins render slice. Printed VERBATIM in the layer legend —
 *  cell size, cells shown, true total and selection mode all come from the
 *  payload itself, never from a constant in this codebase. */
export interface BinsMeta {
  cellDeg: number
  n: number
  shown: number
  selection: string
}

/** What the UI knows about a layer once it has been loaded. */
export interface LoadedLayer {
  points: Point[]
  /** Kept so every mark can state its provenance — the charter's whole point. */
  source: string
  sourceUrl: string
  fetchedAt: string | null
  /** With fetchedAt, drives the TTL-multiple freshness state (lib/freshness). */
  expiresAt: string | null
  count: number
  /** Present when the layer arrived as a density grid rather than raw points. */
  bins?: BinsMeta
  /** Present when the payload was a tombstone: the layer is retired on
   *  purpose, with this reason, and renders as an empty (but named) row. */
  retired?: { reason: string }
}
