import { LAYERS, rawHref, type LayerDef } from '../layers/registry'
import { relTime } from '../lib/api'
import { Swatch } from './LayerSheet'
import type { CountsLedger, LoadedLayer } from '../lib/types'

/**
 * THE PLANE — the non-globe region of the screen, and it never hides.
 * 240px along the bottom on a phone; the same three regions rotated into a
 * 380px left rail at ≥1024px. It answers "what am I looking at, how many,
 * since when, from whom" without a tap:
 *
 *   THE CLAIM   "59 earthquakes · last 24 h", with the honest sub-line for
 *               density layers ("shown as 5,990 area-weighted cells of 0.1°" —
 *               printed from the payload's own bins meta, never a constant).
 *   THE RECORD  a hand-rolled SVG sparkline over /api/cache/v1/counts.json.
 *               Days with no entry are GAPS, never zero; under 30 days of
 *               ledger it draws what exists and says "record since <date>".
 *   THE STRIP   the active-layer chips (focused expanded, context small) and
 *               the Layers control that opens the full sheet.
 *
 * Footer: source · provenance word · fetched Nm ago · raw ↗ (the exact cache
 * file rendered) · table.
 */

const BY_ID = new Map(LAYERS.map((l) => [l.id, l]))

const DAY = 86_400_000

function Sparkline({ series, color }: { series: Record<string, number> | undefined; color: string }) {
  const dates = series ? Object.keys(series).sort() : []
  if (!series || dates.length === 0) {
    return (
      <p className="text-[10px] leading-snug text-[var(--color-ink-faint)]">
        no record yet — the ledger starts with the first fetch
      </p>
    )
  }

  const first = dates[0]
  const todayKey = new Date().toISOString().slice(0, 10)
  const t0 = Date.parse(`${first}T00:00:00Z`)
  const t1 = Math.max(t0, Date.parse(`${todayKey}T00:00:00Z`))
  const n = Math.round((t1 - t0) / DAY) + 1

  const vals: (number | null)[] = []
  for (let i = 0; i < n; i++) {
    const key = new Date(t0 + i * DAY).toISOString().slice(0, 10)
    vals.push(series[key] ?? null)
  }
  const present = vals.filter((v): v is number => v !== null)
  const lo = Math.min(...present)
  const hi = Math.max(...present)

  const W = 320
  const H = 40
  const X = (i: number) => (n === 1 ? W / 2 : 4 + ((W - 8) * i) / (n - 1))
  const Y = (v: number) => (hi === lo ? H / 2 : H - 4 - ((H - 8) * (v - lo)) / (hi - lo))

  // Consecutive runs of real readings. A day the ledger is silent BREAKS the
  // line — a gap is a different sentence from a zero.
  const runs: Array<Array<[number, number]>> = []
  let run: Array<[number, number]> = []
  vals.forEach((v, i) => {
    if (v === null) {
      if (run.length) runs.push(run)
      run = []
    } else {
      run.push([X(i), Y(v)])
    }
  })
  if (run.length) runs.push(run)

  const todayVal = vals[n - 1]
  // A zero-length round-capped stroke stays a round dot when the svg
  // stretches (preserveAspectRatio="none" would squash a <circle>).
  const dot = (x: number, y: number, w: number, stroke: string, key?: string | number) => (
    <polyline
      key={key}
      points={`${x},${y} ${x},${y}`}
      fill="none"
      stroke={stroke}
      strokeWidth={w}
      strokeLinecap="round"
      vectorEffect="non-scaling-stroke"
    />
  )

  const caption = [
    n < 30 ? `record since ${first}` : `${n} days`,
    todayVal === null ? 'no reading today' : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-10 w-full" aria-hidden>
        {runs.map((r, k) =>
          r.length > 1 ? (
            <polyline
              key={k}
              points={r.map(([x, y]) => `${x},${y}`).join(' ')}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          ) : (
            // An isolated reading is still a reading — a dot, not a hole.
            dot(r[0][0], r[0][1], 4, color, k)
          ),
        )}
        {todayVal !== null && dot(X(n - 1), Y(todayVal), 5, 'var(--color-ink)')}
      </svg>
      <p className="mt-0.5 font-mono text-[10px] tabular-nums leading-snug text-[var(--color-ink-faint)]">{caption}</p>
    </>
  )
}

/** The claim's headline count: for density layers the TRUE total from the
 *  bins meta, never the number of circles on screen. */
function claimCount(info: LoadedLayer): number {
  return info.bins ? info.bins.n : info.count
}

interface Props {
  /** Ordered: index 0 is the focused layer. */
  active: string[]
  loaded: Record<string, LoadedLayer>
  loading: string[]
  failed: Record<string, string>
  counts: CountsLedger | null
  onFocus: (id: string) => void
  onOpenSheet: () => void
  onOpenTable: (id: string) => void
}

function Claim({ def, info, busy, error }: { def: LayerDef; info?: LoadedLayer; busy: boolean; error?: string }) {
  if (info?.retired) {
    return (
      <p className="text-[13px] leading-snug text-[var(--color-status-warning)]">
        {def.label}: retired — {info.retired.reason}
      </p>
    )
  }
  if (error) {
    return (
      <p className="text-[13px] leading-snug text-[var(--color-status-critical)]">
        {def.label}: failed to load — {error}
      </p>
    )
  }
  if (!info) {
    return <p className="text-[17px] text-[var(--color-ink-muted)]">{busy ? `loading ${def.label}…` : def.label}</p>
  }
  return (
    <>
      <p className="text-[17px] font-medium leading-tight tabular-nums text-[var(--color-ink)]">
        {claimCount(info).toLocaleString()} {def.noun ?? def.label.toLowerCase()}
        {def.windowLabel ? ` · ${def.windowLabel}` : ''}
      </p>
      {info.bins && (
        <p className="mt-0.5 font-mono text-[11px] tabular-nums leading-snug text-[var(--color-ink-faint)]">
          shown as {info.bins.shown.toLocaleString()} area-weighted cells of {info.bins.cellDeg}°
        </p>
      )}
    </>
  )
}

export function Plane({ active, loaded, loading, failed, counts, onFocus, onOpenSheet, onOpenTable }: Props) {
  const focusedId = active[0] ?? null
  const def = focusedId ? BY_ID.get(focusedId) : undefined
  const info = focusedId ? loaded[focusedId] : undefined

  return (
    <section
      aria-label="Focused layer"
      className="absolute inset-x-0 bottom-0 z-10 flex h-[240px] flex-col border-t border-[var(--color-hairline)] bg-[var(--color-surface)]/90 backdrop-blur-md lg:inset-x-auto lg:inset-y-0 lg:left-0 lg:h-auto lg:w-[380px] lg:border-r lg:border-t-0 lg:pt-16"
    >
      {/* The seam: the planet dissolves into the plane, never a hard cut. */}
      <div
        className="pointer-events-none absolute inset-x-0 -top-10 h-10 lg:hidden"
        style={{ background: 'linear-gradient(to top, rgba(13,17,23,0.9), transparent)' }}
        aria-hidden
      />

      {/* THE CLAIM */}
      <div className="shrink-0 px-4 pt-3">
        {def ? (
          <Claim def={def} info={info} busy={!!focusedId && loading.includes(focusedId)} error={focusedId ? failed[focusedId] : undefined} />
        ) : (
          <p className="text-[17px] text-[var(--color-ink-muted)]">No layers on screen</p>
        )}
      </div>

      {/* THE RECORD */}
      <div className="shrink-0 px-4 pt-2">
        {def && <Sparkline series={counts?.[def.id]} color={def.color} />}
      </div>

      {/* THE STRIP */}
      <div className="flex min-h-0 flex-1 items-center gap-2 overflow-x-auto px-4 py-2 lg:flex-none lg:flex-wrap lg:overflow-x-visible lg:pt-4">
        {active.map((id) => {
          const d = BY_ID.get(id)
          if (!d) return null
          const isFocused = id === focusedId
          const n = loaded[id] && !loaded[id].retired ? loaded[id].count : null
          return (
            <button
              key={id}
              onClick={() => onFocus(id)}
              aria-pressed={isFocused}
              className={`flex shrink-0 items-center gap-2 rounded-full border px-3 ${
                isFocused
                  ? 'border-[var(--color-ink-faint)] bg-[var(--color-surface-raised)] py-2.5 text-sm text-[var(--color-ink)]'
                  : 'border-[var(--color-hairline)] py-2 text-xs text-[var(--color-ink-muted)] hover:bg-white/[0.03]'
              }`}
            >
              <Swatch shape={d.shape} color={d.color} filled={isFocused} />
              <span className="whitespace-nowrap">{d.label}</span>
              {isFocused && n !== null && (
                <span className="font-mono text-[11px] tabular-nums text-[var(--color-ink-faint)]">
                  {n.toLocaleString()}
                </span>
              )}
            </button>
          )
        })}
        <button
          onClick={onOpenSheet}
          className="flex shrink-0 items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface-raised)]/90 px-4 py-3 text-sm text-[var(--color-ink)] hover:bg-[var(--color-surface-raised)]"
        >
          Layers
          <span className="font-mono text-[11px] tabular-nums text-[var(--color-ink-faint)]">{active.length}</span>
          <span aria-hidden>▾</span>
        </button>
      </div>

      {/* Footer: the provenance line. */}
      {def && info && !info.retired && (
        <p className="flex shrink-0 items-center gap-1.5 truncate px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-1 font-mono text-[10px] tabular-nums text-[var(--color-ink-faint)] lg:pb-3">
          <span className="truncate">{info.source || def.label}</span>
          <span aria-hidden>·</span>
          <span>{def.how ?? 'reported'}</span>
          <span aria-hidden>·</span>
          <span className="whitespace-nowrap">fetched {relTime(info.fetchedAt)}</span>
          <span aria-hidden>·</span>
          <a
            href={rawHref(def)}
            target="_blank"
            rel="noreferrer"
            className="whitespace-nowrap underline hover:text-[var(--color-ink-muted)]"
          >
            raw ↗
          </a>
          <span aria-hidden>·</span>
          <button onClick={() => onOpenTable(def.id)} className="underline hover:text-[var(--color-ink-muted)]">
            table
          </button>
        </p>
      )}
    </section>
  )
}
