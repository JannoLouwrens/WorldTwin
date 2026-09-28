/**
 * URL-as-state: the whole view lives in the query string so any screen is a
 * shareable link — layers (order carries focus), camera, selection, and the
 * table read. Written with history.replaceState only (never pushState — Back
 * must leave the site, not unwind camera moves), debounced by the caller for
 * camera idle.
 */

export interface CamState {
  lat: number
  lon: number
  zoom: number
  bearing: number
  pitch: number
}

export interface UrlState {
  /** Ordered — index 0 is the focused layer. Unknown ids are dropped. */
  layers: string[]
  cam: CamState | null
  /** A tapped mark: layer id + the point's own id, or its index. */
  sel: { layerId: string; ref: string } | null
  /** ?read=table&layer={id} — the accessible table view. */
  read: 'table' | null
  readLayer: string | null
}

const num = (v: string | undefined): number | null => {
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

export function parseUrlState(validIds: Set<string>): UrlState {
  const q = new URLSearchParams(location.search)

  const layers = (q.get('layers') ?? '')
    .split(',')
    .filter((id) => validIds.has(id))

  let cam: CamState | null = null
  const rawCam = q.get('cam')
  if (rawCam) {
    const p = rawCam.split(',')
    const lat = num(p[0])
    const lon = num(p[1])
    const zoom = num(p[2])
    if (lat !== null && lon !== null && zoom !== null) {
      cam = {
        lat: Math.max(-85, Math.min(85, lat)),
        lon: ((lon + 540) % 360) - 180,
        zoom: Math.max(0.4, Math.min(10, zoom)),
        bearing: num(p[3]) ?? 0,
        pitch: num(p[4]) ?? 0,
      }
    }
  }

  let sel: UrlState['sel'] = null
  const rawSel = q.get('sel')
  if (rawSel) {
    const i = rawSel.indexOf(':')
    if (i > 0) {
      const layerId = rawSel.slice(0, i)
      const ref = rawSel.slice(i + 1)
      if (validIds.has(layerId) && ref) sel = { layerId, ref }
    }
  }

  const read = q.get('read') === 'table' ? 'table' : null
  const readLayer = read ? q.get('layer') : null

  return { layers, cam, sel, read, readLayer: readLayer && validIds.has(readLayer) ? readLayer : null }
}

export function writeUrlState(s: UrlState): void {
  const url = new URL(location.href)
  const q = url.searchParams

  q.set('layers', s.layers.join(','))

  if (s.cam) {
    const c = s.cam
    q.set('cam', `${c.lat.toFixed(3)},${c.lon.toFixed(3)},${c.zoom.toFixed(2)},${Math.round(c.bearing)},${Math.round(c.pitch)}`)
  } else q.delete('cam')

  if (s.sel) q.set('sel', `${s.sel.layerId}:${s.sel.ref}`)
  else q.delete('sel')

  if (s.read && s.readLayer) {
    q.set('read', s.read)
    q.set('layer', s.readLayer)
  } else {
    q.delete('read')
    q.delete('layer')
  }

  history.replaceState(null, '', url)
}
