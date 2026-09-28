import { FAMILY_HUE, LAYER_FAMILY, type Family } from './families'
import { isPoint } from '../lib/api'
import type { Shape } from '../lib/shapes'
import type { Point } from '../lib/types'

export interface LayerDef {
  id: string
  label: string
  /** One line, plain language — what you are actually looking at. */
  blurb: string
  /** Geometry kind. Default 'points'; 'lines' layers carry a GeoJSON
   *  FeatureCollection of LineStrings and draw as line layers — no icons,
   *  no glow, no density pass. */
  kind?: 'points' | 'lines'
  /** Payload URL when the layer is NOT served from the standard v1 cache
   *  path (cables lives at /api/cache/cables.json). */
  url?: string
  /** Line paint for kind=lines. */
  lineWidth?: number
  lineOpacity?: number
  /** THE CLAIM's noun — "59 earthquakes", "27,486 fire detections". */
  noun?: string
  /** THE CLAIM's window — "last 24 h", "live", "catalogue". */
  windowLabel?: string
  /** HOW, one of the charter's five words. Rides the plane footer and the
   *  table caption; machine-written is never rendered on the globe. */
  how?: 'measured' | 'reported' | 'modelled' | 'reconstructed' | 'machine-written'
  /** MOTION / EARTH / HUMAN. The hue belongs to the family, never the layer;
   *  the toggle reducer allows at most one context layer per family. */
  family: Family
  /** Resolved family hex — MapLibre cannot read CSS custom properties. */
  color: string
  /** Identity within a family. */
  shape: Shape
  /** Rendered by default on first load. The reducer — not this flag — is the
   *  screen invariant's enforcement point, so more defaults than the screen
   *  admits degrade with a stated reason rather than silently. */
  on: boolean
  /** Base mark size in px; `sizeBy` scales it where magnitude matters. */
  size: number
  sizeBy?: (p: Point) => number
  /** Formats the headline value shown when a mark is tapped. */
  format: (p: Point) => string
  /** Explicit extractor where the generic first-array heuristic is unsafe. */
  extract?: (data: unknown) => Point[]
  /** Delivered as `{id}.render.json` bins (lib/renderSlice) and drawn as
   *  plain circles — a density field, not individual marks. */
  slice?: boolean
  /** Concentric rings (1–3) around the mark — level as COUNT, never colour
   *  alone. The literal word rides in `format` for the detail card. */
  rings?: (p: Point) => number
  /** Icon canvas size in CSS px (default 22). Ring-bearing marks need room. */
  iconPx?: number
}

function fam(id: string): { family: Family; color: string } {
  const family = LAYER_FAMILY[id]
  return { family, color: FAMILY_HUE[family] }
}

/** gdacs_events: read `data.events` BY NAME. The payload also carries
 *  per-type tally objects, and a heuristic that scans for "the first array of
 *  point-shaped things" is one schema change away from rendering the wrong
 *  collection. */
function extractGdacs(data: unknown): Point[] {
  if (typeof data !== 'object' || data === null) return []
  const events = (data as { events?: unknown }).events
  return Array.isArray(events) ? events.filter(isPoint) : []
}

/** cloudflare_radar: read `data.outages` BY NAME, returning [] when empty.
 *  The payload holds multiple collections, and the generic first-array
 *  extractor would render DDoS-attack centroids as "outages" whenever
 *  `outages == []`. (Tombstones are handled upstream in envelopeToLoaded.) */
function extractOutages(data: unknown): Point[] {
  if (typeof data !== 'object' || data === null) return []
  const outages = (data as { outages?: unknown }).outages
  return Array.isArray(outages) ? outages.filter(isPoint) : []
}

/** The literal alert word — always shown in text, per the status palette
 *  rule: level is never colour (or ring count) alone. */
export function gdacsAlertWord(p: Point): string {
  const raw = p.props?.alert_level ?? p.props?.alertlevel
  if (typeof raw !== 'string' || !raw) return 'Green'
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase()
}

const GDACS_RINGS: Record<string, number> = { Green: 1, Orange: 2, Red: 3 }

export const LAYERS: LayerDef[] = [
  {
    id: 'quakes',
    label: 'Earthquakes',
    blurb: 'Every quake USGS has recorded in the last day, sized by magnitude.',
    ...fam('quakes'),
    shape: 'circle',
    on: true,
    size: 14,
    noun: 'earthquakes',
    windowLabel: 'last 24 h',
    how: 'measured',
    sizeBy: (p) => 8 + Math.max(0, (p.value ?? 0) - 2) * 5,
    format: (p) => (p.value != null ? `M${p.value.toFixed(1)}` : '—'),
  },
  {
    id: 'gdacs_events',
    label: 'Disaster alerts',
    blurb: 'Active GDACS alerts — quakes, cyclones, floods, wildfires, droughts. Rings count the alert level.',
    ...fam('gdacs_events'),
    shape: 'diamond',
    on: true,
    size: 20,
    iconPx: 30,
    noun: 'active disaster alerts',
    windowLabel: 'now',
    how: 'reported',
    rings: (p) => GDACS_RINGS[gdacsAlertWord(p)] ?? 1,
    format: (p) => {
      const type = p.props?.type_name
      return `${gdacsAlertWord(p)} alert${typeof type === 'string' && type ? ` · ${type}` : ''}`
    },
    extract: extractGdacs,
  },
  {
    id: 'volcanoes',
    label: 'Volcanoes',
    blurb: 'Holocene volcanoes from the Smithsonian Global Volcanism Program.',
    ...fam('volcanoes'),
    shape: 'triangle',
    on: true,
    size: 13,
    noun: 'Holocene volcanoes',
    windowLabel: 'catalogue',
    how: 'reported',
    format: (p) => String(p.props?.type ?? 'Volcano'),
  },
  {
    id: 'fires',
    label: 'Wildfires',
    blurb: 'Wildfire detection density from NASA VIIRS — area-weighted cells, not individual hotspots.',
    ...fam('fires'),
    shape: 'circle',
    on: false,
    slice: true,
    size: 6,
    noun: 'fire detections',
    windowLabel: 'last 24 h',
    how: 'measured',
    // `value` is the bin's cos(lat)-weighted density normalized 0–1 by the
    // slice loader; area on screen tracks the weighted value.
    sizeBy: (p) => 4 + 12 * Math.sqrt(Math.max(0, Math.min(1, p.value ?? 0))),
    format: (p) => {
      const w = p.props?.weight
      return typeof w === 'number' ? `${w.toFixed(1)} detections (area-weighted)` : 'detection cluster'
    },
  },
  {
    id: 'flights',
    label: 'Flights',
    blurb: 'Aircraft currently broadcasting their position over ADS-B.',
    ...fam('flights'),
    shape: 'square',
    on: false,
    size: 7,
    noun: 'aircraft broadcasting',
    windowLabel: 'live',
    how: 'measured',
    format: (p) => String(p.props?.callsign ?? p.label ?? 'aircraft'),
  },
  {
    id: 'cloudflare_radar',
    label: 'Internet outages',
    blurb: "Internet outages seen by Cloudflare's network, placed at country centroids.",
    ...fam('cloudflare_radar'),
    shape: 'square',
    on: false,
    size: 14,
    noun: 'internet outages',
    windowLabel: 'now',
    how: 'reported',
    format: (p) => String(p.props?.country_name ?? p.label ?? 'Outage'),
    extract: extractOutages,
  },
  {
    id: 'cables',
    label: 'Submarine cables',
    blurb: 'The submarine fibre-optic cables that carry the internet between continents (TeleGeography).',
    ...fam('cables'),
    kind: 'lines',
    // Served outside the v1 tree; the payload's own `attribution` field is
    // CC BY-NC-SA-mandated credit and is carried verbatim wherever shown.
    url: '/api/cache/cables.json',
    shape: 'square',
    on: false,
    size: 7,
    lineWidth: 1.2,
    lineOpacity: 0.7,
    noun: 'submarine cables',
    windowLabel: 'current',
    how: 'reported',
    format: (p) => String(p.label ?? p.props?.name ?? 'Submarine cable'),
  },
  {
    id: 'portwatch_chokepoints',
    label: 'Maritime chokepoints',
    blurb: 'Transit calls at the maritime chokepoints world trade squeezes through, from IMF PortWatch satellite AIS.',
    ...fam('portwatch_chokepoints'),
    shape: 'diamond',
    on: false,
    size: 13,
    noun: 'maritime chokepoints',
    windowLabel: 'daily',
    how: 'measured',
    format: (p) => {
      const name = p.props?.name ?? p.label
      const n = typeof name === 'string' && name ? name : 'Chokepoint'
      return p.value != null ? `${n} · ${p.value.toLocaleString()} transits` : n
    },
  },
  {
    id: 'who_don',
    label: 'Disease outbreaks',
    blurb: 'WHO Disease Outbreak News — outbreak events as officially reported.',
    ...fam('who_don'),
    shape: 'triangle',
    on: false,
    size: 13,
    noun: 'outbreak reports',
    windowLabel: 'current',
    how: 'reported',
    format: (p) => String(p.label ?? p.props?.disease ?? p.props?.title ?? 'Outbreak'),
  },
]

export const DEFAULT_ON = LAYERS.filter((l) => l.on).map((l) => l.id)

/** The one-click raw file: exactly what the client rendered. Slice layers
 *  link the render slice actually shown, not a 15 MB full payload. */
export function rawHref(def: LayerDef): string {
  return def.url ?? `/api/cache/v1/${def.id}${def.slice ? '.render' : ''}.json`
}
