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

/** What the UI knows about a layer once it has been loaded. */
export interface LoadedLayer {
  points: Point[]
  /** Kept so every mark can state its provenance — the charter's whole point. */
  source: string
  sourceUrl: string
  fetchedAt: string
  count: number
  /** True when we rendered fewer points than the source actually holds. */
  truncatedFrom?: number
}
