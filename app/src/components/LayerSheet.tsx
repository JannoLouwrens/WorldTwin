import { LAYERS } from '../layers/registry'
import { relTime } from '../lib/api'
import type { LoadedLayer } from '../lib/types'

interface Props {
  open: boolean
  onClose: () => void
  active: string[]
  onToggle: (id: string) => void
  loaded: Record<string, LoadedLayer>
  loading: string[]
}

/**
 * One sheet, one list. The previous client had thirteen modes, nineteen country
 * paints and seventy toggles competing for the same screen; this is the whole
 * navigation surface. Layers carry their own provenance inline so identity is
 * never colour-alone and every count is attributable.
 */
export function LayerSheet({ open, onClose, active, onToggle, loaded, loading }: Props) {
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
        <div className="sticky top-0 flex items-center justify-between border-b border-[var(--color-hairline)] bg-[var(--color-surface-raised)] px-4 py-3">
          <h2 className="text-sm font-medium">Layers</h2>
          <button
            onClick={onClose}
            className="-m-2 p-2 text-[var(--color-ink-muted)] hover:text-[var(--color-ink)]"
            aria-label="Close layers"
          >
            ✕
          </button>
        </div>

        <ul className="divide-y divide-[var(--color-hairline)]">
          {LAYERS.map((def) => {
            const on = active.includes(def.id)
            const info = loaded[def.id]
            const busy = loading.includes(def.id)
            return (
              <li key={def.id}>
                <button
                  onClick={() => onToggle(def.id)}
                  aria-pressed={on}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-white/[0.03]"
                >
                  <span
                    className="mt-1 size-3 shrink-0 rounded-[2px]"
                    style={{
                      background: on ? def.color : 'transparent',
                      border: `1.5px solid ${def.color}`,
                      // Shape echoes the map mark, so the legend identifies by
                      // form as well as hue.
                      clipPath:
                        def.shape === 'triangle'
                          ? 'polygon(50% 0%, 100% 100%, 0% 100%)'
                          : def.shape === 'diamond'
                            ? 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)'
                            : undefined,
                      borderRadius: def.shape === 'circle' ? '50%' : undefined,
                    }}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className="text-sm text-[var(--color-ink)]">{def.label}</span>
                      {busy && <span className="font-mono text-[10px] text-[var(--color-ink-faint)]">loading…</span>}
                      {!busy && info && (
                        <span className="font-mono text-[10px] text-[var(--color-ink-faint)]">
                          {info.count.toLocaleString()}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-snug text-[var(--color-ink-muted)]">{def.blurb}</span>
                    {info && (
                      <span className="mt-1 block font-mono text-[10px] text-[var(--color-ink-faint)]">
                        {info.source} · {relTime(info.fetchedAt)}
                        {info.truncatedFrom &&
                          ` · showing ${info.points.length.toLocaleString()} of ${info.truncatedFrom.toLocaleString()}`}
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
          Every layer states its source and when it was last fetched. Where a source is too large to send whole, the
          number actually drawn is shown rather than implied.
        </p>
      </div>
    </>
  )
}
