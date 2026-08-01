import { useEffect, useRef } from 'react'
import maplibregl, { type Map as MLMap, type StyleSpecification } from 'maplibre-gl'
import { LAYERS } from '../layers/registry'
import { makeShapeIcon } from '../lib/shapes'
import type { LoadedLayer, Point } from '../lib/types'

/** Keyless raster basemap. No Mapbox/MapTiler token to leak or rotate, and no
 *  third-party JS — just tiles. Carto's dark base is the same one the previous
 *  client used, so attribution and usage terms are unchanged. */
const STYLE: StyleSpecification = {
  version: 8,
  projection: { type: 'globe' },
  sources: {
    carto: {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      maxzoom: 18,
      attribution: '© <a href="https://carto.com/attributions">CARTO</a> © OpenStreetMap contributors',
    },
  },
  layers: [
    { id: 'bg', type: 'background', paint: { 'background-color': '#0d1117' } },
    { id: 'carto', type: 'raster', source: 'carto', paint: { 'raster-opacity': 0.92 } },
  ],
  sky: {
    'sky-color': '#0d1117',
    'horizon-color': '#1c2733',
    'fog-color': '#0d1117',
    'fog-ground-blend': 0.6,
  },
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

interface Props {
  loaded: Record<string, LoadedLayer>
  active: string[]
  onPick: (layerId: string, point: Point) => void
}

export function GlobeMap({ loaded, active, onPick }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<MLMap | null>(null)
  const ready = useRef(false)
  // Held in a ref so the map's event handlers always see current data without
  // being torn down and rebound on every render.
  const latest = useRef({ loaded, active, onPick })
  latest.current = { loaded, active, onPick }

  useEffect(() => {
    if (!container.current || map.current) return

    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [12, 25],
      zoom: 1.6,
      minZoom: 0.6,
      maxZoom: 12,
      attributionControl: { compact: true },
      // Touch devices: let a one-finger drag rotate the globe rather than
      // fighting the page, and keep pitch off — it buys nothing on a globe.
      pitchWithRotate: false,
      dragRotate: false,
    })
    map.current = m

    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')

    m.on('load', () => {
      for (const def of LAYERS) {
        const name = `icon-${def.id}`
        if (!m.hasImage(name)) {
          m.addImage(name, makeShapeIcon(def.shape, def.color), { pixelRatio: 2 })
        }
        m.addSource(def.id, { type: 'geojson', data: toFeatureCollection([]) })
        m.addLayer({
          id: def.id,
          type: 'symbol',
          source: def.id,
          layout: {
            'icon-image': name,
            'icon-size': ['get', 'scale'],
            'icon-allow-overlap': true,
            'icon-ignore-placement': true,
          },
        })

        m.on('click', def.id, (e) => {
          const f = e.features?.[0]
          if (!f) return
          const idx = f.properties?.idx as number
          const pt = latest.current.loaded[def.id]?.points[idx]
          if (pt) latest.current.onPick(def.id, pt)
        })
        m.on('mouseenter', def.id, () => (m.getCanvas().style.cursor = 'pointer'))
        m.on('mouseleave', def.id, () => (m.getCanvas().style.cursor = ''))
      }
      ready.current = true
      sync()
    })

    return () => {
      m.remove()
      map.current = null
      ready.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function sync() {
    const m = map.current
    if (!m || !ready.current) return
    for (const def of LAYERS) {
      const src = m.getSource(def.id) as maplibregl.GeoJSONSource | undefined
      if (!src) continue
      const isOn = latest.current.active.includes(def.id)
      const layer = latest.current.loaded[def.id]
      const points = isOn && layer ? layer.points : []

      const fc = toFeatureCollection(points)
      // Mark size is baked per-feature so magnitude reads directly off the map.
      fc.features.forEach((f, i) => {
        const p = points[i]
        const px = def.sizeBy ? def.sizeBy(p) : def.size
        f.properties = { ...f.properties, scale: px / 22 }
      })
      src.setData(fc)
      m.setLayoutProperty(def.id, 'visibility', isOn ? 'visible' : 'none')
    }
  }

  useEffect(sync, [loaded, active])

  return <div ref={container} className="absolute inset-0" />
}
