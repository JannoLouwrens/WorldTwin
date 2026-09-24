import { LAYERS } from '../layers/registry'
import { relTime } from '../lib/api'
import { layerFreshness, type FreshState } from '../lib/freshness'
import type { Shape } from '../lib/shapes'
import type { LoadedLayer } from '../lib/types'

/** The legend mark, mirroring the shape drawn on the globe.
 *
 *  Drawn as SVG rather than a clip-path'd box: clip-path cuts the border along
 *  with the fill, which collapsed the triangle into a sliver. Since shape — not
 *  a fourth hue — is what distinguishes layers past the third, this mark has to
 *  be unambiguous. */
function Swatch({ shape, color, filled }: { shape: Shape; color: string; filled: boolean }) {
  const paint = filled ? { fill: color } : { fill: 'none', stroke: color, strokeWidth: 1.6 }
  return (
    <svg viewBox="0 0 12 12" className="mt-1 size-3 shrink-0 overflow-visible" aria-hidden>
      {shape === 'circle' && <circle cx="6" cy="6" r="5" {...paint} />}
      {shape === 'triangle' && <polygon points="6,1 11,10.5 1,10.5" strokeLinejoin="round" {...paint} />}
      {shape === 'diamond' && <polygon points="6,0.8 11.2,6 6,11.2 0.8,6" strokeLinejoin="round" {...paint} />}
      {shape === 'square' && <rect x="1.2" y="1.2" width="9.6" height="9.6" rx="1" {...paint} />}
    </svg>
  )
}

const STATE_COLOR: Record<FreshState, string> = {
  fresh: 'text-[var(--color-status-good)]',
  late: 'text-[var(--color-status-warning)]',
  stale: 'text-[var(--color-status-critical)]',
}

interface Props {
  open: boolean
  onClose: () => void
  /** Ordered: index 0 is the focused layer. */
  active: string[]
  onToggle: (id: string) => void
  loaded: Record<string, LoadedLayer>
  loading: string[]
  /** Load failures by layer id — a layer that will not draw says why here. */
  failed: Record<string, string>
  /** The reducer's one-line explanation when it had to set a layer aside. */
  notice: string | null
}

/**
 * One sheet, one list. The previous client had thirteen modes, nineteen country
 * paints and seventy toggles competing for the same screen; this is the whole
 * navigation surface. Layers carry their own provenance inline — count, source,
 * freshness word — so identity is never colour-alone, every count is
 * attributable, and a layer that is retired or failing says so by name.
 */
export function LayerSheet({ open, onClose, active, onToggle, loaded, loading, failed, notice }: Props) {
  const focused = active[0] ?? null
  return (
    <>
      <div
        onClick={onClose}
        className={`fixed inset-0 z-20 bg-black/40 transition-opacity ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        aria-hidden
      />
      <div
        role="dialog"
        aria-label="Layers"
        className={`fixed inset-x-0 bottom-0 z-30 max-h-[72svh] overflow-y-auto rounded-t-2xl border-t border-[var(--color-hairline)] bg-[var(--color-surface-raised)] pb-[env(safe-area-inset-bottom)] transition-transform duration-200 sm:inset-x-auto sm:left-4 sm:bottom-4 sm:max-h-[70svh] sm:w-80 sm:rounded-2xl sm:border ${
          open ? 'translate-y-0' : 'translate-y-full sm:translate-y-[120%]'
        }`}
      >
        <div className="sticky top-0 z-10 border-b border-[var(--color-hairline)] bg-[var(--color-surface-raised)]">
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="text-sm font-medium">Layers</h2>
            <button
              onClick={onClose}
              className="-m-2 p-2 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
              aria-label="Close layers"
            >
              ✕
            </button>
          </div>
          {notice && (
            <p className="border-t border-[var(--color-hairline)] px-4 py-2 text-[11px] leading-snug text-[var(--color-status-warning)]">
              {notice}
            </p>
          )}
        </div>

        <ul className="divide-y divide-[var(--color-hairline)]">
          {LAYERS.map((def) => {
            const on = active.includes(def.id)
            const info = loaded[def.id]
            const busy = loading.includes(def.id)
            const error = failed[def.id]
            const retired = info?.retired
            const state = info && !retired ? layerFreshness(info.fetchedAt, info.expiresAt) : null
            return (
              <li key={def.id}>
                <button
                  onClick={() => onToggle(def.id)}
                  aria-pressed={on}
                  disabled={!!retired}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-white/[0.03] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Swatch shape={def.shape} color={def.color} filled={on && !retired} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className="text-sm text-[var(--color-ink)]">{def.label}</span>
                      {on && focused === def.id && (
                        <span className="rounded-sm border border-[var(--color-hairline)] px-1 font-mono text-[9px] uppercase tracking-wider text-[var(--color-ink-faint)]">
                          focused
                        </span>
                      )}
                      {busy && <span className="font-mono text-[10px] text-[var(--color-ink-faint)]">loading…</span>}
                      {!busy && info && !retired && (
                        <span className="font-mono text-[10px] tabular-nums text-[var(--color-ink-faint)]">
                          {info.count.toLocaleString()}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-snug text-[var(--color-ink-muted)]">{def.blurb}</span>
                    {retired && (
                      <span className="mt-1 block font-mono text-[10px] leading-snug text-[var(--color-status-warning)]">
                        retired — {retired.reason}
                      </span>
                    )}
                    {!retired && error && (
                      <span className="mt-1 block font-mono text-[10px] leading-snug text-[var(--color-status-critical)]">
                        failed to load — {error}
                      </span>
                    )}
                    {info && !retired && (
                      <span className="mt-1 block font-mono text-[10px] tabular-nums text-[var(--color-ink-faint)]">
                        {info.source} · {relTime(info.fetchedAt)}
                        {state && (
                          <>
                            {' · '}
                            <span className={STATE_COLOR[state]}>{state}</span>
                          </>
                        )}
                      </span>
                    )}
                    {info?.bins && (
                      // The legend line comes from the payload itself — cell
                      // size, cells shown, true total, selection mode. Never
                      // hardcoded, so the map can't overstate its coverage.
                      <span className="mt-0.5 block font-mono text-[10px] tabular-nums text-[var(--color-ink-faint)]">
                        {info.bins.cellDeg}° cells · {info.bins.shown.toLocaleString()} of{' '}
                        {info.bins.n.toLocaleString()} cells · {info.bins.selection}
                      </span>
                    )}
                  </span>
                  <span
                    className={`mt-0.5 h-5 w-9 shrink-0 rounded-full p-0.5 transition-colors ${
                      on ? 'bg-[var(--color-series-1)]' : 'bg-[var(--color-hairline)]'
                    }`}
                  >
                    <span
                      className={`block size-4 rounded-full bg-white transition-transform ${on ? 'translate-x-4' : ''}`}
                    />
                  </span>
                </button>
              </li>
            )
          })}
        </ul>

        <p className="px-4 py-3 text-[11px] leading-relaxed text-[var(--color-ink-faint)]">
          One layer holds focus; up to three more sit behind it as dots, at most one per family. Every layer states its
          source, its count and how fresh it is; density layers print their own cell maths.
        </p>

        <nav className="flex items-center gap-4 border-t border-[var(--color-hairline)] px-4 py-3 text-xs text-[var(--color-ink-muted)]">
          <a href="/worldtwin/brief/" className="underline hover:text-[var(--color-ink)]">
            Brief
          </a>
          <a href="/worldtwin/status.html" className="underline hover:text-[var(--color-ink)]">
            Status
          </a>
          <a href="/worldtwin/charter.html" className="underline hover:text-[var(--color-ink)]">
            Charter
          </a>
        </nav>
      </div>
    </>
  )
}
