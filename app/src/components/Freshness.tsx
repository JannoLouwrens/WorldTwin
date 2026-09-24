import { relTime } from '../lib/api'
import { worstState, type FreshState } from '../lib/freshness'
import type { ManifestCounts } from '../lib/types'

interface Props {
  /** TTL-multiple freshness of each currently-RENDERED layer, computed from
   *  the layers' own envelopes — never from an aggregate endpoint. */
  states: Record<string, FreshState>
  /** manifest.counts when the manifest exists; null degrades the counter. */
  counts: ManifestCounts | null
  /** Fallback N derived from /api/health while manifest.json 404s. The total
   *  is OMITTED then — a hardcoded denominator is a lie waiting to happen. */
  healthReporting: number | null
  /** True once a health fetch has failed — the API is unreachable. */
  offline: boolean
  /** Newest fetch time we can prove from the cache files themselves. */
  newestFetched: string | null
}

const DOT: Record<string, string> = {
  fresh: 'bg-[var(--color-status-good)]',
  late: 'bg-[var(--color-status-warning)]',
  stale: 'bg-[var(--color-status-critical)]',
  offline: 'bg-[var(--color-status-critical)]',
  loading: 'bg-[var(--color-hairline)]',
}

/**
 * The honesty bar: a freshness badge and the source counter.
 *
 * The badge is the WORST TTL-multiple state among the layers actually on
 * screen (fresh ≤1×, late 1–3×, stale >3×, 6h floor), computed from each
 * loaded envelope's own fetched_at/expires_at. Never from /api/health — that
 * is backend memory seeded from disk mtimes at scheduler start, and a layer
 * that has not fetched since restart simply vanishes from it.
 *
 * The counter is the most persuasive honesty signal available: a number that
 * goes DOWN when things break, read from manifest.counts. Sources that
 * stopped reporting are named, with the reason, on the status page.
 */
export function Freshness({ states, counts, healthReporting, offline, newestFetched }: Props) {
  const worst = worstState(Object.values(states))
  const tone = worst ?? (offline ? 'offline' : 'loading')
  const text =
    worst != null ? `${worst} · ${relTime(newestFetched)}` : offline ? 'offline' : 'loading…'
  const detail =
    (worst != null
      ? 'Worst state among the layers on screen, each measured against its own refresh interval.'
      : 'No layer rendered yet.') + (offline ? ' Live API unreachable — showing data cached on the server.' : '')

  const reporting = counts
    ? `${counts.live} / ${counts.total}`
    : healthReporting != null
      ? String(healthReporting)
      : null

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        {reporting && (
          <a
            href="/worldtwin/status.html"
            title="Sources that stopped reporting are named, with the reason — see the list."
            className="flex items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 backdrop-blur hover:bg-[var(--color-surface-raised)]"
          >
            <span className="font-mono text-[11px] tracking-wide text-[var(--color-ink-muted)]">
              <span className="tabular-nums">{reporting}</span> sources reporting
            </span>
          </a>
        )}
        <div
          title={detail}
          className="flex items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 backdrop-blur"
        >
          <span className={`size-1.5 shrink-0 rounded-full ${DOT[tone]}`} aria-hidden />
          <span className="font-mono text-[11px] tracking-wide tabular-nums text-[var(--color-ink-muted)]">{text}</span>
        </div>
      </div>
      {reporting && (
        <p className="hidden max-w-64 text-right text-[10px] leading-snug text-[var(--color-ink-faint)] sm:block">
          Sources that stopped reporting are named, with the reason —{' '}
          <a href="/worldtwin/status.html" className="underline hover:text-[var(--color-ink-muted)]">
            see the list
          </a>
          .
        </p>
      )}
    </div>
  )
}
