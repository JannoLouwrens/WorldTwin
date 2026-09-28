import { useEffect, useRef } from 'react'
import maplibregl, {
  type ExpressionSpecification,
  type Map as MLMap,
  type StyleSpecification,
} from 'maplibre-gl'
import { LAYERS, type LayerDef } from '../layers/registry'
import { makeShapeIcon, type ShapeIconOpts } from '../lib/shapes'
import { nightPolygon } from '../lib/terminator'
import type { CamState } from '../lib/urlState'
import type { FreshState } from '../lib/freshness'
import type { LoadedLayer, Point } from '../lib/types'

/** Keyless imagery. No Mapbox/MapTiler token to leak or rotate and no
 *  third-party JS — just tiles.
 *
 *  The basemap is NASA's Blue Marble (shaded relief + bathymetry) rather than a
 *  vector street style: this is a view of a planet, and a grey road map reads as
 *  a diagram of one. GIBS only publishes to zoom 8, so `maxzoom` is set there
 *  and MapLibre overzooms rather than requesting tiles that 404.
 *
 *  Labels are GIBS Reference_Labels — same keyless CDN as the imagery, which
 *  also drops the CARTO licence tie (their free basemap terms cover grantees
 *  only). Level9 is the deepest matrix that serves (Level13/15m 404s at every
 *  tile tested), so the map's maxZoom is 10 and labels overzoom the last step. */
const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'

/** Label opacity starts at fitZoom + 0.8, so ZERO place labels are visible at
 *  rest — the planet, not its captions, is the first read. */
function labelRamp(fz: number): ExpressionSpecification {
  return ['interpolate', ['linear'], ['zoom'], fz + 0.8, 0, fz + 2.2, 0.55, fz + 4.6, 0.8]
}

function makeStyle(fz: number): StyleSpecification {
  return {
    version: 8,
    projection: { type: 'globe' },
    sources: {
      bluemarble: {
        type: 'raster',
        // GIBS orders its REST path {TileMatrix}/{TileRow}/{TileCol} — z/y/x, not
        // the usual z/x/y. MapLibre substitutes the tokens positionally, so the
        // order below is deliberate.
        tiles: [`${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`],
        tileSize: 256,
        maxzoom: 8,
        attribution: 'Imagery <a href="https://earthdata.nasa.gov/gibs">NASA EOSDIS GIBS</a>',
      },
      citylights: {
        type: 'raster',
        tiles: [`${GIBS}/VIIRS_CityLights_2012/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`],
        tileSize: 256,
        maxzoom: 8,
      },
      labels: {
        type: 'raster',
        // Verified live: 200, image/png (6,550 B on a labelled tile; ~334 B
        // blanks over open ocean). The double slash is GIBS's own "default
        // style, default time" REST form.
        tiles: [`${GIBS}/Reference_Labels/default//GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`],
        tileSize: 256,
        maxzoom: 9,
      },
      // The night hemisphere — recomputed every 60 s via source.setData. A
      // snapping terminator is computed truth; an animated one is decoration.
      night: { type: 'geojson', data: nightPolygon() },
    },
    layers: [
      // No opaque `space` background layer: the canvas composites over the CSS
      // starfield behind the map container (zero bytes, zero GPU).
      {
        id: 'bluemarble',
        type: 'raster',
        source: 'bluemarble',
        paint: {
          // Tuned down so the planet sits in the same register as the dark UI and
          // the data marks stay the brightest thing on screen.
          'raster-brightness-max': 0.82,
          'raster-saturation': -0.12,
          'raster-contrast': 0.08,
        },
      },
      {
        id: 'night',
        type: 'fill',
        source: 'night',
        paint: { 'fill-color': '#05070b', 'fill-opacity': 0.45, 'fill-antialias': false },
      },
      {
        id: 'citylights',
        type: 'raster',
        source: 'citylights',
        // Drawn ABOVE the night fill: over the darkened hemisphere the lights
        // read clearly; over daylit imagery the near-black raster all but
        // vanishes. Light becomes the depth cue — city lights on the night
        // side only, replacing the old flat everywhere-ramp.
        paint: { 'raster-opacity': 0.4 },
      },
      {
        id: 'labels',
        type: 'raster',
        source: 'labels',
        paint: { 'raster-opacity': labelRamp(fz) },
      },
    ],
    sky: {
      'sky-color': '#060a12',
      'horizon-color': '#2b5f8f',
      'fog-color': '#0d1117',
      'fog-ground-blend': 0.7,
      'horizon-fog-blend': 0.45,
      'sky-horizon-blend': 0.7,
      'atmosphere-blend': ['interpolate', ['linear'], ['zoom'], 0, 0.9, 6, 0.2],
    },
  }
}

function isDesktop(): boolean {
  return window.matchMedia('(min-width: 1024px)').matches
}

/** Zoom at which the whole globe sits inside the viewport with margin.
 *
 *  A fixed zoom cannot work across a 390px portrait phone and a 1440px desktop:
 *  1.6 filled a phone edge to edge and clipped the planet at both sides.
 *  Calibrated empirically — at zoom 1.6 the globe spans ~390 CSS px — and
 *  driven off the smaller axis of the area the PLANE leaves free (240px bottom
 *  region on phone, 380px left rail on desktop). On phone the result is raised
 *  ~log2(1.18) so the limb bleeds off both sides (§7's layout, not a crop). */
function fitZoom(el: HTMLElement): number {
  const { width, height } = el.getBoundingClientRect()
  const w = width || 390
  const h = height || 844
  const availW = isDesktop() ? Math.max(200, w - 380) : w
  const availH = isDesktop() ? h : Math.max(200, h - 240 - 56)
  const shortest = Math.min(availW, availH)
  let z = 1.6 + Math.log2((shortest * 0.86) / 390)
  if (!isDesktop()) z += Math.log2(1.18)
  return Math.max(0.4, Math.min(4, z))
}

function padding(): { top: number; bottom: number; left: number; right: number } {
  return isDesktop()
    ? { top: 0, bottom: 0, left: 380, right: 0 }
    : { top: 56, bottom: 240, left: 0, right: 0 }
}

/** The one motion constant, as a function: cubic-bezier(0.22, 0.61, 0.36, 1),
 *  solved with a few Newton steps — the same curve CSS would run. */
function cubicBezier(x1: number, y1: number, x2: number, y2: number): (x: number) => number {
  const cx = 3 * x1
  const bx = 3 * (x2 - x1) - cx
  const ax = 1 - cx - bx
  const cy = 3 * y1
  const by = 3 * (y2 - y1) - cy
  const ay = 1 - cy - by
  const xAt = (t: number) => ((ax * t + bx) * t + cx) * t
  const dxAt = (t: number) => (3 * ax * t + 2 * bx) * t + cx
  const yAt = (t: number) => ((ay * t + by) * t + cy) * t
  return (x: number) => {
    let t = x
    for (let i = 0; i < 5; i++) {
      const d = dxAt(t)
      if (d === 0) break
      t -= (xAt(t) - x) / d
    }
    return yAt(Math.max(0, Math.min(1, t)))
  }
}

const EASE = cubicBezier(0.22, 0.61, 0.36, 1)

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

function toFeatureCollection(points: Point[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: points.map((p, i) => ({
      type: 'Feature',
      id: i,
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { idx: i },
    })),
  }
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

type Role = 'focused' | 'context' | 'off'

interface Props {
  loaded: Record<string, LoadedLayer>
  /** Ordered by the toggle reducer: index 0 is the FOCUSED layer. */
  active: string[]
  /** Per-layer TTL-multiple freshness. Stale layers render hollow at 0.55
   *  opacity — displayed as silence, never hidden. */
  states: Record<string, FreshState>
  onPick: (layerId: string, point: Point) => void
  /** Camera restored from the URL at boot; while set, refit never fights it. */
  initialCam?: CamState | null
  /** Fired on moveend — App debounces 400 ms into history.replaceState. */
  onCamera?: (cam: CamState) => void
  /** Tapped mark to centre on: easeTo 700 ms, or jumpTo under
   *  prefers-reduced-motion (rotational vection is the actual nausea trigger). */
  target?: { lon: number; lat: number } | null
}

export function GlobeMap({ loaded, active, states, onPick, initialCam, onCamera, target }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MLMap | null>(null)
  const ready = useRef(false)
  const resizeObs = useRef<ResizeObserver | null>(null)
  // Once the user (or a shared link) has stated a camera, auto-refit must
  // never yank it back to the default framing.
  const camPinned = useRef(!!initialCam)
  // Held in a ref so the map's event handlers always see current data without
  // being torn down and rebound on every render.
  const latest = useRef({ loaded, active, states, onPick, onCamera })
  latest.current = { loaded, active, states, onPick, onCamera }

  useEffect(() => {
    if (!container.current || map.current) return

    const coarse = window.matchMedia('(pointer: coarse)').matches
    const fz = fitZoom(container.current)

    const m = new maplibregl.Map({
      container: container.current,
      style: makeStyle(fz),
      center: initialCam ? [initialCam.lon, initialCam.lat] : [12, 18],
      zoom: initialCam?.zoom ?? fz,
      bearing: initialCam?.bearing ?? 0,
      pitch: initialCam?.pitch ?? 0,
      minZoom: 0.4,
      // Labels stop at Level9; one overzoom step is honest, five are mush.
      maxZoom: 10,
      // MapLibre's own control renders expanded and, on a 390px phone, lands
      // straight under the Layers button with no room to sit beside it. The
      // credits are still shown — see <Credits/> — just laid out deliberately.
      attributionControl: false,
      // Pitch buys nothing on a globe, and two-finger rotation makes a pinch
      // zoom drift; a deliberate one-finger drag still pans the planet.
      pitchWithRotate: false,
      dragRotate: false,
      // Mobile GPU budget: a phone GPU gains nothing past 2× on raster tiles,
      // 60 cached tiles cover our zoom range, and tile cross-fades are the one
      // animation the motion rules already forbid.
      pixelRatio: coarse ? Math.min(window.devicePixelRatio || 1, 2) : undefined,
      maxTileCacheSize: 60,
      fadeDuration: 0,
      canvasContextAttributes: coarse ? { powerPreference: 'low-power' } : undefined,
    })
    m.touchPitch.disable()
    m.touchZoomRotate.disableRotation()
    map.current = m

    // The canvas is pure presentation — the accessible surfaces are the plane,
    // the sheet and the table view.
    m.getCanvas().setAttribute('aria-hidden', 'true')
    m.setPadding(padding())

    // Pinch and double-tap already zoom on touch, so the buttons are just
    // clutter over the planet. Keep them where there is no touch.
    if (!coarse) {
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    }

    // Keep the whole planet in frame across rotation and window resizes, and
    // keep the plane carve-out and the label ramp tracking the layout.
    const refit = () => {
      if (!container.current) return
      m.setPadding(padding())
      const target = fitZoom(container.current)
      if (!camPinned.current && Math.abs(m.getZoom() - target) > 0.35) m.setZoom(target)
      if (ready.current) m.setPaintProperty('labels', 'raster-opacity', labelRamp(target))
    }
    const ro = new ResizeObserver(refit)
    ro.observe(container.current)
    resizeObs.current = ro

    // A user gesture states a camera; from then on resizes only re-pad.
    m.on('movestart', (e) => {
      if ((e as { originalEvent?: unknown }).originalEvent) camPinned.current = true
    })
    m.on('moveend', () => {
      const c = m.getCenter()
      latest.current.onCamera?.({
        lat: c.lat,
        lon: c.lng,
        zoom: m.getZoom(),
        bearing: m.getBearing(),
        pitch: m.getPitch(),
      })
    })

    // Terminator clock: 60-second setInterval + setData. NEVER a rAF loop,
    // never triggerRepaint — an idle MapLibre map does zero GPU work and that
    // battery advantage must survive this feature.
    const nightTimer = window.setInterval(() => {
      const src = m.getSource('night') as maplibregl.GeoJSONSource | undefined
      src?.setData(nightPolygon())
    }, 60_000)

    // Without this, a bad style or a failed source fails silently and the globe
    // is simply absent — which is exactly how the container-height bug hid.
    m.on('error', (e) => console.error('[map]', e.error?.message ?? e))

    m.on('load', () => {
      const addIcon = (name: string, def: LayerDef, opts?: ShapeIconOpts) => {
        if (!m.hasImage(name)) {
          m.addImage(name, makeShapeIcon(def.shape, def.color, def.iconPx ?? 22, 2, opts), { pixelRatio: 2 })
        }
      }

      for (const def of LAYERS) {
        // Bins layers draw as plain circles — a density field has no icon —
        // and line layers have no icon at all.
        if (!def.slice && def.kind !== 'lines') {
          addIcon(`icon-${def.id}`, def)
          // The hollow variant is the stale mark: stroke-only, never hidden.
          addIcon(`icon-${def.id}-stale`, def, { hollow: true })
          if (def.rings) {
            for (const k of [1, 2, 3]) {
              addIcon(`icon-${def.id}-r${k}`, def, { rings: k })
              addIcon(`icon-${def.id}-r${k}-stale`, def, { rings: k, hollow: true })
            }
          }
        }

        if (def.kind === 'lines') {
          // Lines keep the default buffer: buffer 0 would clip strokes at
          // tile edges into visible dashes.
          m.addSource(def.id, { type: 'geojson', data: EMPTY_FC })
          continue
        }

        // MapLibre's geojson defaults (maxzoom 18, buffer 128px) make
        // geojson-vt eagerly subdivide every point layer and duplicate edge
        // points for zero visual benefit at our zoom ceiling.
        m.addSource(def.id, {
          type: 'geojson',
          data: EMPTY_FC,
          maxzoom: 6,
          buffer: 0,
          tolerance: 1,
        })
      }

      // Layer order is paint order, and it is built in PASSES, not per layer:
      // lines, then every glow, then density fields, then context dots, then
      // every symbol, then the invisible hit targets. Interleaving glows with
      // symbols let one layer's blurred circles paint OVER another layer's
      // shapes, undermining the entire shape-encoding scheme.

      // Pass 0 — lines (submarine cables): geometry, not marks. Under every
      // point layer so cables never occlude events.
      for (const def of LAYERS) {
        if (def.kind !== 'lines') continue
        m.addLayer({
          id: def.id,
          type: 'line',
          source: def.id,
          layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
          paint: {
            'line-color': def.color,
            'line-width': def.lineWidth ?? 1.2,
            'line-opacity': def.lineOpacity ?? 0.7,
          },
        })
      }

      // Pass 1 — glows. A soft halo beneath each focused mark; against
      // satellite imagery a flat dot disappears into terrain.
      for (const def of LAYERS) {
        if (def.slice || def.kind === 'lines') continue
        m.addLayer({
          id: `${def.id}-glow`,
          type: 'circle',
          source: def.id,
          layout: { visibility: 'none' },
          paint: {
            'circle-color': def.color,
            'circle-radius': ['*', ['get', 'px'], 0.85],
            'circle-blur': 1,
            'circle-opacity': 0.45,
          },
        })
      }

      // Pass 2 — density fields (render-slice bins), circles sized by the
      // cos-weighted value baked into each feature.
      for (const def of LAYERS) {
        if (!def.slice) continue
        m.addLayer({
          id: def.id,
          type: 'circle',
          source: def.id,
          layout: { visibility: 'none' },
          paint: {
            'circle-color': def.color,
            'circle-radius': ['*', ['get', 'px'], 0.5],
            'circle-opacity': 0.8,
            'circle-stroke-color': def.color,
            'circle-stroke-width': 0,
            'circle-stroke-opacity': 0.55,
          },
        })
      }

      // Pass 3 — the context stratum: 5px dots in the family hue at 0.55
      // opacity. No shape, no glow, no label — but still tappable.
      for (const def of LAYERS) {
        if (def.kind === 'lines') continue
        m.addLayer({
          id: `${def.id}-context`,
          type: 'circle',
          source: def.id,
          layout: { visibility: 'none' },
          paint: {
            'circle-color': def.color,
            'circle-radius': 2.5,
            'circle-opacity': 0.55,
            'circle-stroke-color': def.color,
            'circle-stroke-width': 0,
            'circle-stroke-opacity': 0.55,
          },
        })
      }

      // Pass 4 — symbols, always above every glow and every dot.
      for (const def of LAYERS) {
        if (def.slice || def.kind === 'lines') continue
        m.addLayer({
          id: def.id,
          type: 'symbol',
          source: def.id,
          layout: {
            // Baked per feature: ring variants (GDACS alert level) and the
            // hollow stale variant swap the image, not the layer.
            'icon-image': ['get', 'icon'],
            'icon-size': ['get', 'scale'],
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
            visibility: 'none',
          },
        })
      }

      // Pass 5 — one transparent hit target per point source. A 6px fire mark
      // is unhittable with a thumb (WCAG 2.5.8 wants 24px); this makes every
      // mark at least a 44px target without changing a pixel on screen.
      for (const def of LAYERS) {
        if (def.kind === 'lines') continue
        m.addLayer({
          id: `${def.id}-hit`,
          type: 'circle',
          source: def.id,
          layout: { visibility: 'none' },
          paint: {
            'circle-radius': ['max', ['to-number', ['get', 'px']], 22],
            'circle-opacity': 0,
            'circle-stroke-width': 0,
          },
        })
      }

      // ONE nearest-feature click handler over a padded query, instead of a
      // handler per layer: cross-layer click races become a distance sort.
      const hitIds = LAYERS.filter((d) => d.kind !== 'lines').map((d) => `${d.id}-hit`)
      const lineIds = LAYERS.filter((d) => d.kind === 'lines').map((d) => d.id)
      m.on('click', (e) => {
        const pad = 8
        const box: [maplibregl.PointLike, maplibregl.PointLike] = [
          [e.point.x - pad, e.point.y - pad],
          [e.point.x + pad, e.point.y + pad],
        ]
        let best: { layerId: string; idx: number } | null = null
        let bestD = Infinity
        for (const f of m.queryRenderedFeatures(box, { layers: hitIds.filter((id) => !!m.getLayer(id)) })) {
          if (f.geometry.type !== 'Point') continue
          const pr = m.project(f.geometry.coordinates as [number, number])
          const d = (pr.x - e.point.x) ** 2 + (pr.y - e.point.y) ** 2
          if (d < bestD) {
            bestD = d
            best = { layerId: f.source, idx: f.properties?.idx as number }
          }
        }
        if (best) {
          const pt = latest.current.loaded[best.layerId]?.points[best.idx]
          if (pt) {
            latest.current.onPick(best.layerId, pt)
            return
          }
        }
        // No point mark under the tap — a cable will do. Synthesize a point at
        // the tap so the detail card can state the layer's provenance.
        const lf = m.queryRenderedFeatures(box, { layers: lineIds.filter((id) => !!m.getLayer(id)) })[0]
        if (lf) {
          const props = (lf.properties ?? {}) as Record<string, unknown>
          const name = props.name ?? props.label
          latest.current.onPick(lf.source, {
            lat: e.lngLat.lat,
            lon: e.lngLat.lng,
            ...(typeof name === 'string' && name ? { label: name } : {}),
            props,
          })
        }
      })

      for (const id of [...hitIds, ...lineIds]) {
        m.on('mouseenter', id, () => (m.getCanvas().style.cursor = 'pointer'))
        m.on('mouseleave', id, () => (m.getCanvas().style.cursor = ''))
      }

      ready.current = true
      refit()
      sync()
    })

    return () => {
      window.clearInterval(nightTimer)
      resizeObs.current?.disconnect()
      resizeObs.current = null
      m.remove()
      map.current = null
      ready.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Centre on a tapped mark: the one camera animation, at the one constant.
  useEffect(() => {
    const m = map.current
    if (!m || !target) return
    camPinned.current = true
    const center: [number, number] = [target.lon, target.lat]
    if (reducedMotion()) m.jumpTo({ center })
    else m.easeTo({ center, duration: 700, easing: EASE })
  }, [target])

  function sync() {
    const m = map.current
    if (!m || !ready.current) return
    const { loaded: data, active: on, states: fresh } = latest.current
    const focusedId = on[0] ?? null

    for (const def of LAYERS) {
      const src = m.getSource(def.id) as maplibregl.GeoJSONSource | undefined
      if (!src) continue

      const role: Role = def.id === focusedId ? 'focused' : on.includes(def.id) ? 'context' : 'off'
      const layer = data[def.id]
      const stale = (fresh[def.id] ?? 'fresh') === 'stale'
      const vis = (visible: boolean) => (visible ? 'visible' : 'none')

      if (def.kind === 'lines') {
        src.setData(role !== 'off' && layer?.lines ? layer.lines : EMPTY_FC)
        m.setLayoutProperty(def.id, 'visibility', vis(role !== 'off'))
        // Stale lines fade, never vanish — reduced, like every stale mark.
        m.setPaintProperty(def.id, 'line-opacity', stale ? 0.35 : (def.lineOpacity ?? 0.7))
        continue
      }

      const points = role !== 'off' && layer ? layer.points : []
      const iconPx = def.iconPx ?? 22

      const fc = toFeatureCollection(points)
      // Mark size is baked per-feature so magnitude reads directly off the map;
      // the icon name is baked too (ring/stale variants are images, not layers).
      fc.features.forEach((f, i) => {
        const p = points[i]
        const px = def.sizeBy ? def.sizeBy(p) : def.size
        const rings = def.rings ? Math.max(1, Math.min(3, def.rings(p))) : 0
        const icon = `icon-${def.id}${rings ? `-r${rings}` : ''}${stale ? '-stale' : ''}`
        f.properties = { ...f.properties, px, scale: px / iconPx, icon }
      })
      src.setData(fc)

      m.setLayoutProperty(def.id, 'visibility', vis(role === 'focused'))
      m.setLayoutProperty(`${def.id}-context`, 'visibility', vis(role === 'context'))
      m.setLayoutProperty(`${def.id}-hit`, 'visibility', vis(role !== 'off'))

      if (def.slice) {
        // Density circles: hollow stroke-only at 0.55 when the layer is stale.
        m.setPaintProperty(def.id, 'circle-opacity', stale ? 0 : 0.8)
        m.setPaintProperty(def.id, 'circle-stroke-width', stale ? 1.2 : 0)
      } else {
        // Glow only under a live focused layer — a stale layer must read as
        // silence, and a halo reads as activity.
        m.setLayoutProperty(`${def.id}-glow`, 'visibility', vis(role === 'focused' && !stale))
        m.setPaintProperty(def.id, 'icon-opacity', stale ? 0.55 : 1)
      }

      // Context dots go hollow when stale — reduced, never removed.
      m.setPaintProperty(`${def.id}-context`, 'circle-opacity', stale ? 0 : 0.55)
      m.setPaintProperty(`${def.id}-context`, 'circle-stroke-width', stale ? 1.2 : 0)
    }
  }

  useEffect(sync, [loaded, active, states])

  // Sized by normal flow (h-full/w-full) rather than absolute insets, so the
  // container keeps its dimensions regardless of what MapLibre's own stylesheet
  // does to `position`. Positioned (relative) so it paints ABOVE the absolute
  // starfield div behind it, while the transparent canvas lets the stars show
  // around the planet's limb.
  return <div ref={container} className="relative h-full w-full" />
}
