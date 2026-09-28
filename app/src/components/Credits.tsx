/**
 * Basemap attribution.
 *
 * NASA GIBS asks for visible credit and the Reference_Labels layer is built on
 * OpenStreetMap data (© OSM contributors), so this is a licensing obligation
 * rather than a decoration. (CARTO is gone — imagery AND labels are GIBS now,
 * which also drops the licence tie: CARTO's free basemap terms cover grantees
 * only.) MapLibre's built-in control renders expanded and collides with the
 * bottom chrome at phone widths, so the credit is laid out here instead: one
 * quiet line, always on screen, sitting just above the plane.
 *
 * `extra` carries per-layer licence-mandated credits (cables: CC BY-NC-SA —
 * TeleGeography's attribution string MUST ride wherever the data shows).
 */
export function Credits({ extra = [] }: { extra?: string[] }) {
  return (
    <p className="pointer-events-none absolute bottom-[246px] right-3 z-10 max-w-[52vw] text-right font-mono text-[9px] leading-tight text-[var(--color-ink-faint)]/70 sm:right-16 lg:bottom-[max(0.5rem,env(safe-area-inset-bottom))]">
      Imagery &amp; labels NASA EOSDIS GIBS · labels © OpenStreetMap contributors
      {extra.map((a) => ` · ${a}`).join('')}
    </p>
  )
}
