import { useMemo, useState } from 'react'
import { LAYERS, rawHref } from '../layers/registry'
import { relTime } from '../lib/api'
import type { LoadedLayer, Point } from '../lib/types'

/**
 * The table view — ?read=table&layer={id}, or the T shortcut. A plain
 * <table> of the focused layer's rows: tabular-nums, sortable sticky headers,
 * a <caption> carrying the provenance sentence, and Download JSON straight to
 * the static cache file. One component satisfies never-colour-alone,
 * raw-is-one-click-away, and the journalist use case simultaneously.
 * Esc closes (handled by the App-level key handler).
 */

type SortKey = 'label' | 'value' | 'lat' | 'lon'

const COLUMNS: Array<{ key: SortKey; head: string }> = [
  { key: 'label', head: 'label' },
  { key: 'value', head: 'value' },
  { key: 'lat', head: 'lat' },
  { key: 'lon', head: 'lon' },
]

function cellLabel(p: Point): string {
  if (p.label) return p.label
  if (typeof p.props?.name === 'string') return p.props.name
  if (typeof p.props?.place === 'string') return p.props.place
  return p.id ?? '—'
}

interface Props {
  layerId: string
  loaded: Record<string, LoadedLayer>
  onClose: () => void
}

export function TableView({ layerId, loaded, onClose }: Props) {
  const def = LAYERS.find((l) => l.id === layerId)
  const info = loaded[layerId]
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: 'value', dir: -1 })

  // Top 200 by value first — the table is a read, not a full export (the raw
  // file is one click away for that) — then the user's chosen ordering.
  const rows = useMemo(() => {
    const pts = info?.points ?? []
    const top = [...pts].sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity)).slice(0, 200)
    const cmp = (a: Point, b: Point): number => {
      switch (sort.key) {
        case 'label':
          return cellLabel(a).localeCompare(cellLabel(b))
        case 'value':
          return (a.value ?? -Infinity) - (b.value ?? -Infinity)
        case 'lat':
          return a.lat - b.lat
        case 'lon':
          return a.lon - b.lon
      }
    }
    return top.sort((a, b) => sort.dir * cmp(a, b))
  }, [info, sort])

  if (!def) return null

  const clickSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: key === 'label' ? 1 : -1 }))

  const provenance = info
    ? `${def.label} — top ${rows.length} of ${info.count.toLocaleString()} rows by value · ${info.source}` +
      `${def.how ? ` · ${def.how}` : ''} · fetched ${relTime(info.fetchedAt)}` +
      `${info.attribution ? ` · ${info.attribution}` : ''}`
    : `${def.label} — not loaded`

  return (
    <div role="dialog" aria-label={`${def.label} as a table`} className="fixed inset-0 z-50 overflow-y-auto bg-[var(--color-surface)]/97 backdrop-blur">
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-[var(--color-hairline)] bg-[var(--color-surface)] px-4 py-3">
        <h2 className="min-w-0 truncate text-sm font-medium">{def.label} — table</h2>
        <div className="flex shrink-0 items-center gap-3">
          <a
            href={rawHref(def)}
            download
            className="text-xs text-[var(--color-ink-muted)] underline hover:text-[var(--color-ink)]"
          >
            Download JSON
          </a>
          <button
            onClick={onClose}
            className="-m-2 p-2 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            aria-label="Close table"
          >
            ✕
          </button>
        </div>
      </div>

      {!info || info.retired ? (
        <p className="px-4 py-6 text-sm text-[var(--color-ink-muted)]">
          {info?.retired ? `Retired — ${info.retired.reason}` : 'This layer has not loaded — toggle it on first.'}
        </p>
      ) : (
        <table className="w-full border-collapse text-left text-xs tabular-nums">
          <caption className="px-4 py-2 text-left font-mono text-[10px] leading-relaxed text-[var(--color-ink-faint)]">
            {provenance}
          </caption>
          <thead>
            <tr>
              <th className="sticky top-[49px] border-b border-[var(--color-hairline)] bg-[var(--color-surface)] px-4 py-2 font-mono text-[10px] font-normal text-[var(--color-ink-faint)]">
                #
              </th>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  aria-sort={sort.key === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : undefined}
                  className="sticky top-[49px] border-b border-[var(--color-hairline)] bg-[var(--color-surface)] px-2 py-0 font-normal"
                >
                  <button
                    onClick={() => clickSort(c.key)}
                    className="w-full px-2 py-2 text-left font-mono text-[10px] text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
                  >
                    {c.head}
                    {sort.key === c.key ? (sort.dir === 1 ? ' ↑' : ' ↓') : ''}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.id ?? i} className="border-b border-[var(--color-hairline)]/50">
                <td className="px-4 py-1.5 font-mono text-[10px] text-[var(--color-ink-faint)]">{i + 1}</td>
                <td className="max-w-[40vw] truncate px-4 py-1.5 text-[var(--color-ink)]">{cellLabel(p)}</td>
                <td className="px-4 py-1.5 text-[var(--color-ink-muted)]">
                  {p.value != null ? p.value.toLocaleString() : '—'}
                </td>
                <td className="px-4 py-1.5 font-mono text-[var(--color-ink-muted)]">{p.lat.toFixed(3)}</td>
                <td className="px-4 py-1.5 font-mono text-[var(--color-ink-muted)]">{p.lon.toFixed(3)}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-sm text-[var(--color-ink-muted)]">
                  0 rows — the source reported nothing in this window.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  )
}
