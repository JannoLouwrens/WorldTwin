import { relTime } from '../lib/api'
import type { Health } from '../lib/types'

interface Props {
  health: Health | null
  /** True once a health fetch has failed — the API is unreachable. */
  offline: boolean
  /** Newest fetch time we can prove from the cache files themselves. */
  cachedAt: string | null
}

/**
 * The honesty bar.
 *
 * The previous client returned early when /api/health failed, which left the
 * last good timestamp frozen on screen — so during the six-day July outage the
 * globe read "moments ago" over week-old data. Here an unreachable API is a
 * *state we render*, dated from the cache payload itself, and staleness is
 * counted across all sources rather than taken from the single freshest one.
 */
export function Freshness({ health, offline, cachedAt }: Props) {
  let text: string
  let detail: string
  let tone: 'live' | 'stale' | 'offline'

  if (offline || !health) {
    tone = 'offline'
    text = cachedAt ? `cached · ${relTime(cachedAt)}` : 'offline'
    detail = 'Live API unreachable — showing data cached on the server'
  } else {
    const entries = Object.values(health.layers).filter((l) => l.last_fetch)
    const dayAgo = Date.now() - 86_400_000
    const stale = entries.filter((l) => new Date(l.last_fetch!).getTime() < dayAgo).length
    const newest = entries.reduce((acc, l) => Math.max(acc, new Date(l.last_fetch!).getTime()), 0)
    tone = stale > entries.length / 2 ? 'stale' : 'live'
    text = `updated ${relTime(new Date(newest).toISOString())}`
    detail =
      stale > 0
        ? `${stale} of ${entries.length} sources haven't updated in over a day`
        : `all ${entries.length} sources updated within the day`
  }

  const dot =
    tone === 'live'
      ? 'bg-[var(--color-status-good)]'
      : tone === 'stale'
        ? 'bg-[var(--color-status-warning)]'
        : 'bg-[var(--color-status-critical)]'

  return (
    <div
      title={detail}
      className="flex items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 backdrop-blur"
    >
      <span className={`size-1.5 shrink-0 rounded-full ${dot}`} aria-hidden />
      <span className="font-mono text-[11px] tracking-wide text-[var(--color-ink-muted)]">{text}</span>
    </div>
  )
}
