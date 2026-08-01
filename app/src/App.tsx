import { useCallback, useEffect, useState } from 'react'
import { GlobeMap } from './components/GlobeMap'
import { LayerSheet } from './components/LayerSheet'
import { Freshness } from './components/Freshness'
import { DetailCard } from './components/DetailCard'
import { DEFAULT_ON, LAYERS } from './layers/registry'
import { loadHealth, loadLayer } from './lib/api'
import type { Health, LoadedLayer, Point } from './lib/types'

/** Layer selection lives in the URL so any view is a shareable link — the
 *  property the old client got right and the one worth carrying over. */
function readActive(): string[] {
  const raw = new URLSearchParams(location.search).get('layers')
  if (!raw) return DEFAULT_ON
  const valid = new Set(LAYERS.map((l) => l.id))
  const picked = raw.split(',').filter((id) => valid.has(id))
  return picked.length ? picked : DEFAULT_ON
}

export default function App() {
  const [active, setActive] = useState<string[]>(readActive)
  const [loaded, setLoaded] = useState<Record<string, LoadedLayer>>({})
  const [loading, setLoading] = useState<string[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [offline, setOffline] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [pick, setPick] = useState<{ layerId: string; point: Point } | null>(null)

  // Fetch a layer the first time it is switched on, never before. The initial
  // view therefore costs a few hundred KB rather than the ~25 MB the previous
  // client preloaded — fires alone is 85k points.
  useEffect(() => {
    for (const id of active) {
      if (loaded[id] || loading.includes(id)) continue
      setLoading((l) => [...l, id])
      loadLayer(id)
        .then((data) => setLoaded((prev) => ({ ...prev, [id]: data })))
        .catch(() => {})
        .finally(() => setLoading((l) => l.filter((x) => x !== id)))
    }
  }, [active, loaded, loading])

  useEffect(() => {
    let alive = true
    const tick = () =>
      loadHealth()
        .then((h) => alive && (setHealth(h), setOffline(false)))
        .catch(() => alive && setOffline(true))
    tick()
    const t = setInterval(tick, 30_000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  useEffect(() => {
    const url = new URL(location.href)
    url.searchParams.set('layers', active.join(','))
    history.replaceState(null, '', url)
  }, [active])

  const toggle = useCallback((id: string) => {
    setActive((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }, [])

  const onPick = useCallback((layerId: string, point: Point) => setPick({ layerId, point }), [])

  const newestCached =
    Object.values(loaded)
      .map((l) => l.fetchedAt)
      .sort()
      .at(-1) ?? null

  return (
    <div className="relative h-full w-full">
      <GlobeMap loaded={loaded} active={active} onPick={onPick} />

      <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div className="pointer-events-auto rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 backdrop-blur">
          <span className="text-sm font-medium tracking-tight">WorldTwin</span>
        </div>
        <div className="pointer-events-auto">
          <Freshness health={health} offline={offline} cachedAt={newestCached} />
        </div>
      </header>

      {!sheetOpen && (
        <button
          onClick={() => setSheetOpen(true)}
          className="absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface-raised)]/90 px-4 py-2.5 text-sm backdrop-blur transition-colors hover:bg-[var(--color-surface-raised)]"
        >
          <span className="size-2 rounded-full bg-[var(--color-series-1)]" aria-hidden />
          Layers
          <span className="font-mono text-[11px] text-[var(--color-ink-faint)]">{active.length}</span>
        </button>
      )}

      <LayerSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        active={active}
        onToggle={toggle}
        loaded={loaded}
        loading={loading}
      />

      <DetailCard pick={pick} loaded={loaded} onClose={() => setPick(null)} />
    </div>
  )
}
