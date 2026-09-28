import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { GlobeMap } from './components/GlobeMap'
import { LayerSheet } from './components/LayerSheet'
import { Freshness } from './components/Freshness'
import { DetailCard } from './components/DetailCard'
import { Credits } from './components/Credits'
import { Plane } from './components/Plane'
import { TableView } from './components/TableView'
import { DEFAULT_ON, LAYERS } from './layers/registry'
import { CACHE, loadCounts, loadHealth, loadLayer, loadLines, loadManifest } from './lib/api'
import { loadSliced } from './lib/renderSlice'
import { layerFreshness, type FreshState } from './lib/freshness'
import { normalizeSelection, toggleLayer, type LayerMeta, type Selection } from './lib/toggles'
import { parseUrlState, writeUrlState, type CamState } from './lib/urlState'
import type { CountsLedger, Health, LoadedLayer, Manifest, Point } from './lib/types'

const BY_ID = new Map(LAYERS.map((l) => [l.id, l]))

const META: LayerMeta = {
  family: (id) => BY_ID.get(id)?.family ?? 'EARTH',
  label: (id) => BY_ID.get(id)?.label ?? id,
}

/** The whole view lives in the URL — layers (order carries focus), camera,
 *  selection, table read — so any screen is a shareable link. Parsed once at
 *  boot; whatever arrives passes through the reducer's normalizer, the single
 *  enforcement point for the screen invariant. */
const BOOT = parseUrlState(new Set(LAYERS.map((l) => l.id)))

function readSelection(): Selection {
  return normalizeSelection(BOOT.layers.length ? BOOT.layers : DEFAULT_ON, META)
}

export default function App() {
  const [sel, setSel] = useState<Selection>(readSelection)
  const [loaded, setLoaded] = useState<Record<string, LoadedLayer>>({})
  const [loading, setLoading] = useState<string[]>([])
  const [failed, setFailed] = useState<Record<string, string>>({})
  const [health, setHealth] = useState<Health | null>(null)
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [counts, setCounts] = useState<CountsLedger | null>(null)
  const [offline, setOffline] = useState(false)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [pick, setPick] = useState<{ layerId: string; point: Point } | null>(null)
  const [table, setTable] = useState<string | null>(
    BOOT.read === 'table' ? (BOOT.readLayer ?? readSelection().active[0] ?? null) : null,
  )
  const [copied, setCopied] = useState(false)

  const active = sel.active

  // A mark selection restored from a shared link, resolved once its layer
  // finishes loading.
  const pendingSel = useRef(BOOT.sel)

  // Fetch a layer the first time it is switched on, never before. The initial
  // view therefore costs a few hundred KB rather than the ~25 MB the previous
  // client preloaded. Oversized layers arrive as a render slice (bins), line
  // layers through their own loader, and a layer that failed stays failed —
  // with the reason on its sheet row — until it is toggled again, rather than
  // hot-looping retries.
  useEffect(() => {
    for (const id of active) {
      if (loaded[id] || loading.includes(id) || failed[id]) continue
      const def = BY_ID.get(id)
      if (!def) continue
      setLoading((l) => [...l, id])
      const promise =
        def.kind === 'lines'
          ? loadLines(id, def.url ?? `${CACHE}/${id}.json`)
          : def.slice
            ? loadSliced(id)
            : loadLayer(id, def.extract)
      promise
        .then((data) => setLoaded((prev) => ({ ...prev, [id]: data })))
        .catch((err: unknown) =>
          setFailed((prev) => ({ ...prev, [id]: err instanceof Error ? err.message : String(err) })),
        )
        .finally(() => setLoading((l) => l.filter((x) => x !== id)))
    }
  }, [active, loaded, loading, failed])

  // One poll drives the honesty surfaces: /api/health (the counter's fallback
  // + offline detection), manifest.json (the counter's source of truth) and
  // counts.json (the sparkline's ledger; 404 degrades to "no record yet").
  // Gated on tab visibility — a hidden tab neither needs nor deserves the
  // traffic — and re-run the moment the tab returns.
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
      loadCounts()
        .then((c) => alive && setCounts(c))
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

  // ---- URL-as-state ----
  // Everything but the camera writes immediately; the camera debounces 400 ms
  // after idle so a drag doesn't spam replaceState.
  const camRef = useRef<CamState | null>(BOOT.cam)
  const camTimer = useRef<number | null>(null)
  const urlBits = useRef({ active, pick, table, loaded })
  urlBits.current = { active, pick, table, loaded }

  const pushUrl = useCallback(() => {
    const { active, pick, table, loaded } = urlBits.current
    let selParam: { layerId: string; ref: string } | null = null
    if (pick) {
      const idx = loaded[pick.layerId]?.points.indexOf(pick.point) ?? -1
      const ref = pick.point.id ?? (idx >= 0 ? String(idx) : null)
      if (ref != null) selParam = { layerId: pick.layerId, ref }
    }
    writeUrlState({
      layers: active,
      cam: camRef.current,
      sel: selParam,
      read: table ? 'table' : null,
      readLayer: table,
    })
  }, [])

  useEffect(pushUrl, [active, pick, table, pushUrl])

  const onCamera = useCallback(
    (cam: CamState) => {
      camRef.current = cam
      if (camTimer.current != null) window.clearTimeout(camTimer.current)
      camTimer.current = window.setTimeout(pushUrl, 400)
    },
    [pushUrl],
  )

  const copyLink = useCallback(() => {
    pushUrl()
    const href = location.href
    const done = () => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    }
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(href).then(done, () => window.prompt('Copy this link:', href))
    } else {
      window.prompt('Copy this link:', href)
    }
  }, [pushUrl])

  // Restore a shared selection once its layer arrives: by the point's own id
  // first, by index as the fallback.
  useEffect(() => {
    const pend = pendingSel.current
    if (!pend) return
    const info = loaded[pend.layerId]
    if (!info) return
    pendingSel.current = null
    const byId = info.points.find((p) => p.id === pend.ref)
    const idx = Number(pend.ref)
    const pt = byId ?? (Number.isInteger(idx) && idx >= 0 ? info.points[idx] : undefined)
    if (pt) setPick({ layerId: pend.layerId, point: pt })
  }, [loaded])

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

  /** Chip tap in the plane: an already-active layer takes focus. */
  const focus = useCallback((id: string) => {
    setSel((s) => (s.active[0] === id ? s : normalizeSelection([id, ...s.active.filter((x) => x !== id)], META)))
  }, [])

  const onPick = useCallback((layerId: string, point: Point) => setPick({ layerId, point }), [])

  // Keyboard: T toggles the table read for the focused layer, L the sheet,
  // Esc closes whatever is topmost.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (e.key === 'Escape') {
        setTable(null)
        setPick(null)
        setSheetOpen(false)
      } else if (e.key === 't' || e.key === 'T') {
        setTable((cur) => (cur ? null : (urlBits.current.active[0] ?? null)))
      } else if (e.key === 'l' || e.key === 'L') {
        setSheetOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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

  // Licence-mandated per-layer credits (cables' CC BY-NC-SA line) for the
  // layers currently on screen, carried verbatim into the credit line.
  const extraCredits = useMemo(() => {
    const out: string[] = []
    for (const id of active) {
      const a = loaded[id]?.attribution
      if (a && !out.includes(a)) out.push(a)
    }
    return out
  }, [active, loaded])

  const target = useMemo(() => (pick ? { lon: pick.point.lon, lat: pick.point.lat } : null), [pick])

  return (
    <div className="relative h-full w-full">
      {/* Starfield: a fixed CSS gradient + tiled dots behind the transparent
          canvas. Zero JS, zero GPU — see index.css. */}
      <div className="starfield absolute inset-0" aria-hidden />

      <GlobeMap
        loaded={loaded}
        active={active}
        states={states}
        onPick={onPick}
        initialCam={BOOT.cam}
        onCamera={onCamera}
        target={target}
      />

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
        <div className="pointer-events-auto flex items-start gap-2">
          <button
            onClick={copyLink}
            title="Copy a link to exactly this view"
            className="rounded-full border border-[var(--color-hairline)] bg-[var(--color-surface)]/80 px-3 py-1.5 font-mono text-[11px] tracking-wide text-[var(--color-ink-muted)] backdrop-blur hover:bg-[var(--color-surface-raised)]"
          >
            {copied ? 'copied' : 'copy link'}
          </button>
          <Freshness
            states={states}
            counts={manifest?.counts ?? null}
            healthReporting={healthReporting}
            offline={offline}
            newestFetched={newestFetched}
          />
        </div>
      </header>

      <Plane
        active={active}
        loaded={loaded}
        loading={loading}
        failed={failed}
        counts={counts}
        onFocus={focus}
        onOpenSheet={() => setSheetOpen(true)}
        onOpenTable={(id) => setTable(id)}
      />

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

      <Credits extra={extraCredits} />

      <DetailCard pick={pick} loaded={loaded} onClose={() => setPick(null)} />

      {table && <TableView layerId={table} loaded={loaded} onClose={() => setTable(null)} />}
    </div>
  )
}
