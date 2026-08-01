export type Shape = 'circle' | 'triangle' | 'diamond' | 'square'

/** Draw a mark as a canvas image for MapLibre's `addImage`.
 *
 *  This exists because the palette caps us at three categorical hues — on a map
 *  any layer can sit beside any other, and past three slots no hue ordering
 *  clears the all-pairs separation floors. So identity beyond three layers is
 *  carried by SHAPE, with hue denoting the family. That is the "secondary
 *  encoding" the palette rules require, not decoration.
 *
 *  Every mark gets a dark surface ring so overlapping marks stay separable
 *  against both the ocean and the bright parts of the basemap.
 */
export function makeShapeIcon(shape: Shape, color: string, px = 22, ratio = 2): ImageData {
  const size = px * ratio
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('2d context unavailable')

  const c = size / 2
  const r = size / 2 - 3 * ratio

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

  ctx.fillStyle = color
  ctx.fill()
  // Surface ring: keeps overlapping marks legible instead of merging into a blob.
  ctx.lineWidth = 2 * ratio
  ctx.strokeStyle = 'rgba(13, 17, 23, 0.85)'
  ctx.stroke()

  return ctx.getImageData(0, 0, size, size)
}
