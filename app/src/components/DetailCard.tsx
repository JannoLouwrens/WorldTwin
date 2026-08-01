import { LAYERS } from '../layers/registry'
import { relTime } from '../lib/api'
import type { LoadedLayer, Point } from '../lib/types'

interface Props {
  pick: { layerId: string; point: Point } | null
  loaded: Record<string, LoadedLayer>
  onClose: () => void
}

/** Values worth surfacing, in a readable order, without dumping the whole
 *  props bag at the reader. */
function rows(point: Point): Array<[string, string]> {
  const props = point.props ?? {}
  const out: Array<[string, string]> = []
  for (const [k, v] of Object.entries(props)) {
    if (v === null || v === undefined || v === '') continue
    if (typeof v === 'object') continue
    if (k.endsWith('_url')) continue
    out.push([k.replace(/_/g, ' '), String(v)])
  }
  return out.slice(0, 8)
}

/**
 * Tap a mark, get its provenance. This is the charter made literal: the number,
 * where it came from, when it was measured, and a link to the instrument.
 */
export function DetailCard({ pick, loaded, onClose }: Props) {
  if (!pick) return null
  const def = LAYERS.find((l) => l.id === pick.layerId)
  const info = loaded[pick.layerId]
  if (!def) return null

  const url = (pick.point.props?.usgs_url ?? pick.point.props?.url ?? info?.sourceUrl) as string | undefined

  return (
    <div className="pointer-events-auto fixed inset-x-3 bottom-3 z-40 rounded-2xl border border-[var(--color-hairline)] bg-[var(--color-surface-raised)]/95 p-4 backdrop-blur sm:left-auto sm:right-4 sm:w-96">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="size-2 shrink-0 rounded-full" style={{ background: def.color }} aria-hidden />
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-faint)]">
              {def.label}
            </span>
          </div>
          <p className="mt-1 truncate text-lg font-medium">{def.format(pick.point)}</p>
          {pick.point.label && def.format(pick.point) !== pick.point.label && (
            <p className="truncate text-sm text-[var(--color-ink-muted)]">{pick.point.label}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="-m-2 shrink-0 p-2 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
          aria-label="Close details"
        >
          ✕
        </button>
      </div>

      <dl className="mt-3 space-y-1">
        {rows(pick.point).map(([k, v]) => (
          <div key={k} className="flex justify-between gap-4 text-xs">
            <dt className="shrink-0 text-[var(--color-ink-faint)]">{k}</dt>
            <dd className="truncate text-right text-[var(--color-ink-muted)]">{v}</dd>
          </div>
        ))}
        <div className="flex justify-between gap-4 text-xs">
          <dt className="shrink-0 text-[var(--color-ink-faint)]">position</dt>
          <dd className="text-right font-mono text-[var(--color-ink-muted)]">
            {pick.point.lat.toFixed(3)}, {pick.point.lon.toFixed(3)}
          </dd>
        </div>
      </dl>

      {info && (
        <p className="mt-3 border-t border-[var(--color-hairline)] pt-2 text-[11px] leading-relaxed text-[var(--color-ink-faint)]">
          {info.source} · fetched {relTime(info.fetchedAt)}
          {url && (
            <>
              {' · '}
              <a href={url} target="_blank" rel="noreferrer" className="underline hover:text-[var(--color-ink-muted)]">
                source
              </a>
            </>
          )}
        </p>
      )}
    </div>
  )
}
