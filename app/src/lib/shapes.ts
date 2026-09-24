export type Shape = 'circle' | 'triangle' | 'diamond' | 'square'

export interface ShapeIconOpts {
  /** Stroke-only variant — the STALE mark. Stale data is displayed as
   *  silence, hollow at reduced opacity; it is never hidden. */
  hollow?: boolean
  /** Concentric rings (0–3) drawn around the shape. A COUNT encoding for
   *  levels (GDACS Green/Orange/Red = 1/2/3), because the status palette
   *  fails as a categorical set by design — level must never be carried by
   *  colour alone. The literal word appears in the detail card. */
  rings?: number
}

/** Draw a mark as a canvas image for MapLibre's `addImage`.
 *
 *  This exists because the palette caps us at three categorical hues — on a map
 *  any layer can sit beside any other, and past three slots no hue ordering
 *  clears the all-pairs separation floors. So identity beyond three layers is
 *  carried by SHAPE, with hue denoting the family. That is the "secondary
 *  encoding" the palette rules require, not decoration.
 *
 *  Every solid mark gets a dark surface ring so overlapping marks stay
 *  separable against both the ocean and the bright parts of the basemap.
 */
export function makeShapeIcon(shape: Shape, color: string, px = 22, ratio = 2, opts: ShapeIconOpts = {}): ImageData {
  const size = px * ratio
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('2d context unavailable')

  const c = size / 2
  const rings = Math.max(0, Math.min(3, Math.floor(opts.rings ?? 0)))
  const ringGap = 2.6 * ratio
  // The outermost ring lands where the plain shape's edge would be, so ringed
  // and unringed marks read at the same overall size; the shape shrinks inward.
  const r = size / 2 - 3 * ratio - rings * ringGap

  ctx.beginPath()
  switch (shape) {
    case 'circle':
      ctx.arc(c, c, r, 0, Math.PI * 2)
      break
    case 'triangle':
      ctx.moveTo(c, c - r)
      ctx.lineTo(c + r * 0.92, c + r * 0.72)
      ctx.lineTo(c - r * 0.92, c + r * 0.72)
      ctx.closePath()
      break
    case 'diamond':
      ctx.moveTo(c, c - r)
      ctx.lineTo(c + r, c)
      ctx.lineTo(c, c + r)
      ctx.lineTo(c - r, c)
      ctx.closePath()
      break
    case 'square':
      ctx.rect(c - r * 0.82, c - r * 0.82, r * 1.64, r * 1.64)
      break
  }

  if (opts.hollow) {
    ctx.lineWidth = 1.8 * ratio
    ctx.strokeStyle = color
    ctx.stroke()
  } else {
    ctx.fillStyle = color
    ctx.fill()
    // Surface ring: keeps overlapping marks legible instead of merging into a blob.
    ctx.lineWidth = 2 * ratio
    ctx.strokeStyle = 'rgba(13, 17, 23, 0.85)'
    ctx.stroke()
  }

  // Level rings — count, not colour, carries the level.
  ctx.lineWidth = 1.2 * ratio
  ctx.strokeStyle = color
  for (let i = 1; i <= rings; i++) {
    ctx.beginPath()
    ctx.arc(c, c, r + i * ringGap, 0, Math.PI * 2)
    ctx.stroke()
  }

  return ctx.getImageData(0, 0, size, size)
}
