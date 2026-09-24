import { useEffect, useRef } from 'react'
import maplibregl, { type Map as MLMap, type StyleSpecification } from 'maplibre-gl'
import { LAYERS, type LayerDef } from '../layers/registry'
import { makeShapeIcon, type ShapeIconOpts } from '../lib/shapes'
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
 *  Place labels ride on top from Carto, faded in only once you have zoomed past
 *  the whole-globe view, so the planet stays uncluttered at rest. */
const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'

const STYLE: StyleSpecification = {
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
      attribution:
        'Imagery <a href="https://earthdata.nasa.gov/gibs">NASA EOSDIS GIBS</a> · labels © <a href="https://carto.com/attributions">CARTO</a>, OpenStreetMap',
    },
    citylights: {
      type: 'raster',
      tiles: [`${GIBS}/VIIRS_CityLights_2012/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`],
      tileSize: 256,
      maxzoom: 8,
    },
    labels: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      maxzoom: 18,
    },
  },
  layers: [
    { id: 'space', type: 'background', paint: { 'background-color': '#05070b' } },
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
      id: 'citylights',
      type: 'raster',
      source: 'citylights',
      // Human settlement, coming up as you approach. Kept low so it warms the
      // night side rather than washing the imagery out.
      paint: {
        'raster-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.16, 3, 0.3, 6, 0.42],
      },
    },
    {
      id: 'labels',
      type: 'raster',
      source: 'labels',
      paint: { 'raster-opacity': ['interpolate', ['linear'], ['zoom'], 1.8, 0, 3.2, 0.55, 6, 0.8] },
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

/** Zoom at which the whole globe sits inside the viewport with margin.
 *
 *  A fixed zoom cannot work across a 390px portrait phone and a 1440px desktop:
 *  1.6 filled a phone edge to edge and clipped the planet at both sides.
 *  Calibrated empirically — at zoom 1.6 the globe spans ~390 CSS px — and
 *  driven off the *smaller* axis so the sphere is never cropped. */
function fitZoom(el: HTMLElement): number {
  const { width, height } = el.getBoundingClientRect()
  const shortest = Math.min(width || 390, height || 844)
  const target = shortest * 0.86
  return Math.max(0.4, Math.min(4, 1.6 + Math.log2(target / 390)))
}

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

type Role = 'focused' | 'context' | 'off'

interface Props {
  loaded: Record<string, LoadedLayer>
  /** Ordered by the toggle reducer: index 0 is the FOCUSED layer. */
  active: string[]
  /** Per-layer TTL-multiple freshness. Stale layers render hollow at 0.55
   *  opacity — displayed as silence, never hidden. */
  states: Record<string, FreshState>
  onPick: (layerId: string, point: Point) => void
}

export function GlobeMap({ loaded, active, states, onPick }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MLMap | null>(null)
  const ready = useRef(false)
  const resizeObs = useRef<ResizeObserver | null>(null)
  // Held in a ref so the map's event handlers always see current data without
  // being torn down and rebound on every render.
  const latest = useRef({ loaded, active, states, onPick })
  latest.current = { loaded, active, states, onPick }

  useEffect(() => {
    if (!container.current || map.current) return

    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [12, 18],
      zoom: fitZoom(container.current),
      minZoom: 0.4,
      maxZoom: 12,
      // MapLibre's own control renders expanded and, on a 390px phone, lands
      // straight under the Layers button with no room to sit beside it. The
      // credits are still shown — see <Credits/> — just laid out deliberately.
      attributionControl: false,
      // Pitch buys nothing on a globe, and two-finger rotation makes a pinch
      // zoom drift; a deliberate one-finger drag still pans the planet.
      pitchWithRotate: false,
      dragRotate: false,
    })
    m.touchPitch.disable()
    m.touchZoomRotate.disableRotation()
    map.current = m

    // Pinch and double-tap already zoom on touch, so the buttons are just
    // clutter over the planet. Keep them where there is no touch.
    if (!window.matchMedia('(pointer: coarse)').matches) {
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    }

    // Keep the whole planet in frame across rotation and window resizes.
    const refit = () => {
      if (!container.current) return
      const target = fitZoom(container.current)
      if (Math.abs(m.getZoom() - target) > 0.35) m.setZoom(target)
    }
    const ro = new ResizeObserver(refit)
    ro.observe(container.current)
    resizeObs.current = ro

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
        // Bins layers draw as plain circles — a density field has no icon.
        if (!def.slice) {
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

        // MapLibre's geojson defaults (maxzoom 18, buffer 128px) make
        // geojson-vt eagerly subdivide every point layer and duplicate edge
        // points for zero visual benefit at our zoom ceiling.
        m.addSource(def.id, {
          type: 'geojson',
          data: toFeatureCollection([]),
          maxzoom: 6,
          buffer: 0,
          tolerance: 1,
        })
      }

      // Layer order is paint order, and it is built in PASSES, not per layer:
      // every glow first, then density fields, then context dots, then every
      // symbol. Interleaving glows with symbols let one layer's blurred
      // circles paint OVER another layer's shapes, undermining the entire
      // shape-encoding scheme.

      // Pass 1 — glows. A soft halo beneath each focused mark; against
      // satellite imagery a flat dot disappears into terrain.
      for (const def of LAYERS) {
        if (def.slice) continue
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
        if (def.slice) continue
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

      for (const def of LAYERS) {
        for (const layerId of [def.id, `${def.id}-context`]) {
          m.on('click', layerId, (e) => {
            const f = e.features?.[0]
            if (!f) return
            const idx = f.properties?.idx as number
            const pt = latest.current.loaded[def.id]?.points[idx]
            if (pt) latest.current.onPick(def.id, pt)
          })
          m.on('mouseenter', layerId, () => (m.getCanvas().style.cursor = 'pointer'))
          m.on('mouseleave', layerId, () => (m.getCanvas().style.cursor = ''))
        }
      }

      ready.current = true
      sync()
    })

    return () => {
      resizeObs.current?.disconnect()
      resizeObs.current = null
      m.remove()
      map.current = null
      ready.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
      const points = role !== 'off' && layer ? layer.points : []
      const stale = (fresh[def.id] ?? 'fresh') === 'stale'
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

      const vis = (visible: boolean) => (visible ? 'visible' : 'none')
      m.setLayoutProperty(def.id, 'visibility', vis(role === 'focused'))
      m.setLayoutProperty(`${def.id}-context`, 'visibility', vis(role === 'context'))

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
  // does to `position`. See the import-order note in index.css.
  return <div ref={container} className="h-full w-full" />
}
