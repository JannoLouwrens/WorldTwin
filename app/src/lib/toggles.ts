/**
 * The toggle reducer — the screen invariant, enforced in code, not guidance:
 *
 *   · at most 4 layers active,
 *   · exactly 1 FOCUSED layer (the most recently turned on),
 *   · at most 3 CONTEXT layers,
 *   · at most one CONTEXT layer per family.
 *
 * This is what makes the three-hue palette cap provable rather than
 * usually-fine: the all-pairs colour floor binds only among marks of equal
 * visual weight, and the context stratum is at most three 5 px dots in the
 * three validated hues. The focused layer separates by size, luminance, shape
 * and glow — channels not subject to dE.
 *
 * `active` is ordered by recency: index 0 is the focused layer. That ordering
 * is what the URL carries, so a shared link reproduces the same focus.
 */

import type { Family } from '../layers/families'

export const MAX_ACTIVE = 4
export const MAX_CONTEXT = MAX_ACTIVE - 1

export interface Selection {
  /** Ordered by recency; index 0 is the FOCUSED layer, the rest are context. */
  active: string[]
  /** One-line explanation when the reducer had to set something aside. The
   *  sheet renders it, so a layer never disappears without a stated reason. */
  notice: string | null
}

export interface LayerMeta {
  family: (id: string) => Family
  label: (id: string) => string
}

/** Give `focused` the focus slot, then fill the context slots from
 *  `candidates` in order, dropping duplicates-by-family and overflow —
 *  and SAY what was dropped and why. */
function fill(focused: string, candidates: string[], meta: LayerMeta): Selection {
  const context: string[] = []
  const dropped: string[] = []
  for (const id of candidates) {
    if (id === focused || context.includes(id)) continue
    if (context.length >= MAX_CONTEXT) {
      dropped.push(`${meta.label(id)} (at most ${MAX_ACTIVE} layers on screen)`)
      continue
    }
    const fam = meta.family(id)
    if (context.some((c) => meta.family(c) === fam)) {
      dropped.push(`${meta.label(id)} (one ${fam} context layer at a time)`)
      continue
    }
    context.push(id)
  }
  return {
    active: [focused, ...context],
    notice: dropped.length ? `Set aside: ${dropped.join('; ')}.` : null,
  }
}

/** Toggle `id`. On = it takes focus and everything else competes for the three
 *  context slots in recency order. Off = it leaves; the next most recent layer
 *  inherits focus (the order already encodes recency, so no work needed). */
export function toggleLayer(active: string[], id: string, meta: LayerMeta): Selection {
  if (active.includes(id)) {
    return { active: active.filter((x) => x !== id), notice: null }
  }
  return fill(id, active, meta)
}

/** Normalize an arbitrary list (URL param, registry defaults) into a valid
 *  selection. The registry may legitimately declare more defaults than the
 *  screen invariant admits — the reducer, as the single enforcement point,
 *  resolves that here and states what it set aside. */
export function normalizeSelection(active: string[], meta: LayerMeta): Selection {
  const first = active[0]
  if (first === undefined) return { active: [], notice: null }
  return fill(first, active, meta)
}
