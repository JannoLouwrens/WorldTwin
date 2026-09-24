import { useCallback, useEffect, useMemo, useState } from 'react'
import { GlobeMap } from './components/GlobeMap'
import { LayerSheet } from './components/LayerSheet'
import { Freshness } from './components/Freshness'
import { DetailCard } from './components/DetailCard'
import { Credits } from './components/Credits'
import { DEFAULT_ON, LAYERS } from './layers/registry'
import { loadHealth, loadLayer, loadManifest } from './lib/api'
import { loadSliced } from './lib/renderSlice'
import { layerFreshness, type FreshState } from './lib/freshness'
import { normalizeSelection, toggleLayer, type LayerMeta, type Selection } from './lib/toggles'
import type { Health, LoadedLayer, Manifest, Point } from './lib/types'

const BY_ID = new Map(LAYERS.map((l) => [l.id, l]))

const META: LayerMeta = {
  family: (id) => BY_ID.get(id)?.family ?? 'EARTH',
  label: (id) => BY_ID.get(id)?.label ?? id,
}

/** Layer selection lives in the URL so any view is a shareable link — the
 *  property the old client got right and the one worth carrying over. The
 *  order carries focus (first = focused), and whatever arrives — URL or
 *  registry defaults — passes through the reducer's normalizer, which is the
 *  single enforcement point for the screen invariant. */
function readSelection(): Selection {
  const raw = new URLSearchParams(location.search).get('layers')
  const valid = new Set(LAYERS.map((l) => l.id))
  const picked = raw ? raw.split(',').filter((id) => valid.has(id)) : []
  return normalizeSelection(picked.length ? picked : DEFAULT_ON, META)
}

export default function App() {
  const [sel, setSel] = useState<Selection>(readSelection)
  const [loaded, setLoaded] = useState<Record<string, LoadedLayer>>({})
  const [loading, setLoading] = useState<string[]>([])
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [health, setHealth] = useState<Health | null>(null)
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [offline, setOffline] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [pick, setPick] = useState<{ layerId: string; point: Point } | null>(null)

  const active = sel.active

  // Fetch a layer the first time it is switched on, never before. The initial
  // view therefore costs a few hundred KB rather than the ~25 MB the previous
  // client preloaded. Oversized layers arrive as a render slice (bins), and a
  // layer that failed stays failed — with the reason on its sheet row — until
  // it is toggled again, rather than hot-looping retries.
  useEffect(() => {
    for (const id of active) {
      if (loaded[id] || loading.includes(id) || failed[id]) continue
      const def = BY_ID.get(id)
      if (!def) continue
      setLoading((l) => [...l, id])
      const promise = def.slice ? loadSliced(id) : loadLayer(id, def.extract)
      promise
        .then((data) => setLoaded((prev) => ({ ...prev, [id]: data })))
        .catch((err: unknown) =>
          setFailed((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : String(err) })),
        )
        .finally(() => setLoading((l) => l.filter((x) => x !== id)))
    }
  }, [active, loaded, loading, failed])

  // One poll drives both honesty surfaces: /api/health (the counter's
  // fallback + offline detection) and manifest.json (the counter's source of
  // truth; 404 is expected until the backend deploy lands). Gated on tab
  // visibility — a hidden tab neither needs nor deserves the traffic — and
  // re-run the moment the tab returns.
  useEffect(() => {
    let alive = true
    const tick = () => {
      if (document.visibilityState === 'hidden') return
      loadHealth()
        .then((h) => {
          if (!alive) return
          setHealth(h)
          setOffline(false)
        })
        .catch(() => alive && setOffline(true))
      loadManifest(true)
        .then((mf) => alive && setManifest(mf))
        .catch(() => {})
    }
    tick()
    const t = setInterval(tick, 120_000)
    const onVis = () => {
      if (document.visibilityState === 'visible') tick()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      alive = false
      clearInterval(t)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [])

  useEffect(() => {
    const url = new URL(location.href)
    url.searchParams.set('layers', active.join(','))
    history.replaceState(null, '', url)
  }, [active])

  const toggle = useCallback((id: string) => {
    // Re-toggling a failed layer is the retry gesture — clear its verdict.
    setFailed((prev) => {
      if (!(id in prev)) return prev
      const next = { ...prev }
      delete next[id]
      return next
    })
    setSel((s) => toggleLayer(s.active, id, META))
  }, [])

  const onPick = useCallback((layerId: string, point: Point) => setPick({ layerId, point }), [])

  // Per-layer TTL-multiple freshness for what is actually on screen, computed
  // from each envelope's own timestamps. The health poll's re-render doubles
  // as the recompute clock, so "now" advances at least every two minutes.
  const states = useMemo(() => {
    const out: Record<string, FreshState> = {}
    for (const id of active) {
      const l = loaded[id]
      if (!l || l.retired) continue
      out[id] = layerFreshness(l.fetchedAt, l.expiresAt)
    }
    return out
  }, [active, loaded, health]) // eslint-disable-line react-hooks/exhaustive-deps

  const healthReporting = health ? Object.values(health.layers).filter((l) => l.ok).length : null

  const newestFetched =
    Object.values(loaded)
      .map((l) => l.fetchedAt)
      .filter((v): v is string => !!v)
      .sort()
      .at(-1) ?? null

  return (
    <div className="relative h-full w-full">
      <GlobeMap loaded={loaded} active={active} states={states} onPick={onPick} />

      {/* Vignette. Pulls the eye to the centre of the globe and stops the bright
          limb of the planet from fighting the chrome at the screen edges. */}
      <div
        className="pointer-events-none absolute inset-0 z-[5]"
        style={{ background: 'radial-gradient(ellipse at 50% 50%, transparent 46%, rgba(3,5,9,0.5) 100%)' }}
        aria-hidden
      />

      <header className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div className="pointer-events-auto rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 backdrop-blur">
          <span className="text-sm font-medium tracking-tight">WorldTwin</span>
        </div>
        <div className="pointer-events-auto">
          <Freshness
            states={states}
            counts={manifest?.counts ?? null}
            healthReporting={healthReporting}
            offline={offline}
            newestFetched={newestFetched}
          />
        </div>
      </header>

      {!sheetOpen && (
        <button
          onClick={() => setSheetOpen(true)}
          className="absolute bottom-4 left-4 z-10 flex items-center gap-2 rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface-raised)]/90 px-4 py-2.5 text-sm backdrop-blur transition-colors hover:bg-[var(--color-surface-raised)]"
        >
          <span className="size-2 rounded-full bg-[var(--color-series-1)]" aria-hidden />
          Layers
          <span className="font-mono text-[11px] tabular-nums text-[var(--color-ink-faint)]">{active.length}</span>
        </button>
      )}

      <LayerSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        active={active}
        onToggle={toggle}
        loaded={loaded}
        loading={loading}
        failed={failed}
        notice={sel.notice}
      />

      <Credits />

      <DetailCard pick={pick} loaded={loaded} onClose={() => setPick(null)} />
    </div>
  )
}
