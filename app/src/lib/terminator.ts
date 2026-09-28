/**
 * Solar terminator — computed truth, not decoration.
 *
 * `nightPolygon()` returns the night hemisphere as a GeoJSON polygon: 361
 * vertices along the terminator (one per degree of longitude) closed over
 * whichever pole is in darkness. The map fills it #05070b at 0.45 and swaps
 * the geometry with `source.setData` on a 60-second interval — the terminator
 * SNAPS, it never animates, and there is no rAF loop and no triggerRepaint,
 * so an idle map still does zero GPU work.
 *
 * Solar position is the standard low-precision almanac (good to ~0.01°, which
 * at 1° vertex sampling is far below visibility).
 */

const RAD = Math.PI / 180

/** Where the sun is directly overhead right now. */
export function subsolarPoint(date: Date): { lat: number; lon: number } {
  // Days since J2000.0 (2000-01-01 12:00 UTC).
  const d = (date.getTime() - Date.UTC(2000, 0, 1, 12)) / 86_400_000
  // Mean longitude and mean anomaly of the sun.
  const L = (280.46 + 0.9856474 * d) % 360
  const g = ((357.528 + 0.9856003 * d) % 360) * RAD
  // Ecliptic longitude, obliquity → declination and right ascension.
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * RAD
  const eps = (23.439 - 0.0000004 * d) * RAD
  const decl = Math.asin(Math.sin(eps) * Math.sin(lambda))
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda))
  // Subsolar longitude = right ascension minus Greenwich mean sidereal time.
  const gmst = (280.46061837 + 360.98564736629 * d) % 360
  const lon = (((ra / RAD - gmst) % 360) + 540) % 360 - 180
  return { lat: decl / RAD, lon }
}

/** The night hemisphere, as a polygon MapLibre can fill.
 *
 *  A point sits on the terminator when its angular distance to the subsolar
 *  point is 90°: sinδ·sinφ + cosδ·cosφ·cos(λ−λs) = 0, i.e.
 *  φ = atan(−cos(λ−λs)/tanδ). Walking λ from −180 to 180 keeps longitudes
 *  monotonic, so the ring never crosses the antimeridian; it closes along the
 *  dark pole instead (south pole when the northern hemisphere leans sunward).
 */
export function nightPolygon(date: Date = new Date()): GeoJSON.Feature<GeoJSON.Polygon> {
  const sun = subsolarPoint(date)
  // At the equinox instant tanδ → 0 and the formula divides by zero; a hair
  // of declination keeps it finite and is invisible at 1° sampling.
  const sign = sun.lat >= 0 ? 1 : -1
  const tanDecl = Math.tan(Math.max(Math.abs(sun.lat), 0.001) * RAD) * sign

  const ring: [number, number][] = []
  for (let i = 0; i <= 360; i++) {
    const lon = -180 + i
    const lat = Math.atan(-Math.cos((lon - sun.lon) * RAD) / tanDecl) / RAD
    ring.push([lon, lat])
  }
  const pole = sun.lat >= 0 ? -90 : 90
  ring.push([180, pole], [-180, pole], [ring[0][0], ring[0][1]])

  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}
