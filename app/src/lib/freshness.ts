/**
 * Per-layer freshness in TTL multiples, computed from each layer's OWN
 * envelope — never from an aggregate endpoint. /api/health is backend memory
 * state seeded from disk mtimes at scheduler start; a layer that has not
 * fetched since restart simply vanishes from it. The envelope cannot lie that
 * way: `fetched_at` and `expires_at` are written in the same atomic commit as
 * the data itself.
 *
 * A flat 24-hour rule fails both ways — it flags 30-day-TTL layers at hour 25
 * and clears a 1-minute-TTL flights layer at 23 hours. TTL-relative at 3x
 * correctly separates "the scheduler is a bit behind" from "this instrument
 * stopped".
 */

export type FreshState = 'fresh' | 'late' | 'stale'

/** Queue-lag floor. The overdue ratio is measured against at least six hours
 *  regardless of how short the layer's real TTL is, so a busy scheduler queue
 *  never reads as a break. (A flights layer 20 minutes overdue is not news.) */
export const TTL_FLOOR_MS = 6 * 3_600_000

/**
 * overdue = (now − fetched_at) / max(expires_at − fetched_at, 6 h)
 * fresh ≤ 1× · late 1–3× · stale > 3×.
 *
 * Missing or unparseable timestamps are STALE, not fresh — an envelope that
 * cannot state when it was fetched has no claim to freshness.
 */
export function layerFreshness(
  fetchedAt: string | null | undefined,
  expiresAt: string | null | undefined,
  now = Date.now(),
): FreshState {
  if (!fetchedAt) return 'stale'
  const fetched = Date.parse(fetchedAt)
  if (!Number.isFinite(fetched)) return 'stale'
  const expires = expiresAt ? Date.parse(expiresAt) : NaN
  const ttl = Number.isFinite(expires) && expires > fetched ? expires - fetched : TTL_FLOOR_MS
  const overdue = (now - fetched) / Math.max(ttl, TTL_FLOOR_MS)
  if (overdue <= 1) return 'fresh'
  if (overdue <= 3) return 'late'
  return 'stale'
}

const RANK: Record<FreshState, number> = { fresh: 0, late: 1, stale: 2 }

/** The badge state: the WORST among the layers actually on screen. */
export function worstState(states: Iterable<FreshState>): FreshState | null {
  let worst: FreshState | null = null
  for (const s of states) {
    if (worst === null || RANK[s] > RANK[worst]) worst = s
  }
  return worst
}
