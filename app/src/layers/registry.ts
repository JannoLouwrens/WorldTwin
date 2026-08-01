import type { Shape } from '../lib/shapes'
import type { Point } from '../lib/types'

export interface LayerDef {
  id: string
  label: string
  /** One line, plain language — what you are actually looking at. */
  blurb: string
  /** Family hue. Only three exist; see index.css for why. */
  color: string
  /** Identity within a family. */
  shape: Shape
  /** Rendered by default on first load. Keep this list short — the initial
   *  view should be readable, not a demonstration of everything we have. */
  on: boolean
  /** Base mark size in px; `sizeBy` scales it where magnitude matters. */
  size: number
  sizeBy?: (p: Point) => number
  /** Formats the headline value shown when a mark is tapped. */
  format: (p: Point) => string
}

export const SERIES = {
  movement: 'var(--color-series-1)',
  heat: 'var(--color-series-2)',
  seismic: 'var(--color-series-3)',
} as const

/** Resolved hex values — MapLibre cannot read CSS custom properties. */
export const HEX = {
  movement: '#3987e5',
  heat: '#d95926',
  seismic: '#199e70',
} as const

export const LAYERS: LayerDef[] = [
  {
    id: 'quakes',
    label: 'Earthquakes',
    blurb: 'Every quake USGS has recorded in the last day, sized by magnitude.',
    color: HEX.seismic,
    shape: 'circle',
    on: true,
    size: 14,
    sizeBy: (p) => 8 + Math.max(0, (p.value ?? 0) - 2) * 5,
    format: (p) => (p.value != null ? `M${p.value.toFixed(1)}` : '—'),
  },
  {
    id: 'gdacs_events',
    label: 'Disaster alerts',
    blurb: 'Active alerts from GDACS — cyclones, floods, wildfires, droughts.',
    // Status colours, not a series hue: alert level is a state, and a status
    // colour must never impersonate a fourth series. Always shown with a label.
    color: '#fab219',
    shape: 'diamond',
    on: true,
    size: 20,
    format: (p) => String(p.props?.alert_level ?? p.label ?? 'Alert'),
  },
  {
    id: 'volcanoes',
    label: 'Volcanoes',
    blurb: 'Holocene volcanoes from the Smithsonian Global Volcanism Program.',
    color: HEX.heat,
    shape: 'triangle',
    on: false,
    size: 13,
    format: (p) => String(p.props?.type ?? 'Volcano'),
  },
  {
    id: 'fires',
    label: 'Wildfires',
    blurb: 'Thermal hotspots detected by NASA VIIRS satellites in the last 24h.',
    color: HEX.heat,
    shape: 'circle',
    on: false,
    size: 6,
    format: (p) => (p.value != null ? `${p.value.toFixed(1)} MW` : 'hotspot'),
  },
  {
    id: 'flights',
    label: 'Flights',
    blurb: 'Aircraft currently broadcasting their position over ADS-B.',
    color: HEX.movement,
    shape: 'square',
    on: false,
    size: 7,
    format: (p) => String(p.props?.callsign ?? p.label ?? 'aircraft'),
  },
]

export const DEFAULT_ON = LAYERS.filter((l) => l.on).map((l) => l.id)
