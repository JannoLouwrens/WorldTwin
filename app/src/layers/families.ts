/**
 * The three layer families and their validated hues/ramps.
 *
 * Three categorical hues is a permanent, empirically-verified cap, not a
 * preference. Re-validated against the real surface #0d1117 with `--pairs all`
 * (the correct pairlist for a map, where any two marks can be adjacent):
 *
 *   #3987e5 / #d95926 / #199e70  PASS
 *   worst CVD dE 9.4 (deutan) · worst normal-vision dE 20.9 (floor 15)
 *
 * Seven candidate fourth hues spanning amber, violet, purple, cyan, magenta
 * and indigo were tested and every one fails the CVD floor and/or the hard
 * normal-vision floor. Hue is assigned to FAMILY, never to layer — identity
 * within a family is carried by shape.
 *
 * Each family gets a validated 5-step sequential ramp whose MIDDLE step is the
 * family hue, so magnitude never introduces a new hue. Six steps fails
 * adjacent-dL at 0.049 against a 0.06 floor; five is computed, not chosen.
 * Verbatim from docs/MASTER_PLAN.md §6:
 *
 *   MOTION  #184f95 #256abf #3987e5 #6da7ec #9ec5f4   (light-end contrast 2.34:1)
 *   EARTH   #8f3517 #b4491f #d95926 #e8834f #f4b48a   (2.42:1)
 *   HUMAN   #116a4a #158460 #199e70 #4dbd95 #8fd8bd   (2.87:1)
 */

export type Family = 'MOTION' | 'EARTH' | 'HUMAN'

/** The family hue — the middle step of each ramp. */
export const FAMILY_HUE: Record<Family, string> = {
  MOTION: '#3987e5',
  EARTH: '#d95926',
  HUMAN: '#199e70',
}

/** 5-step sequential ramps, dark → light, middle step = family hue. */
export const FAMILY_RAMP: Record<Family, readonly [string, string, string, string, string]> = {
  MOTION: ['#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4'],
  EARTH: ['#8f3517', '#b4491f', '#d95926', '#e8834f', '#f4b48a'],
  HUMAN: ['#116a4a', '#158460', '#199e70', '#4dbd95', '#8fd8bd'],
}

/** Family assignment per layer. EARTH is the physical planet (heat, seismics,
 *  weather-driven disaster), MOTION is things moving through it, HUMAN is
 *  human-built systems. The toggle reducer allows at most one CONTEXT layer
 *  per family, which is what makes the three-hue cap provable on screen. */
export const LAYER_FAMILY: Record<string, Family> = {
  quakes: 'EARTH',
  fires: 'EARTH',
  gdacs_events: 'EARTH',
  volcanoes: 'EARTH',
  flights: 'MOTION',
  cloudflare_radar: 'HUMAN',
}
