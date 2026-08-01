/**
 * Basemap attribution.
 *
 * NASA GIBS, CARTO and OpenStreetMap all require visible credit, so this is a
 * licensing obligation rather than a decoration. MapLibre's built-in control
 * renders expanded and collides with the Layers button at phone widths, so the
 * credit is laid out here instead: one quiet line, always on screen, clear of
 * the bottom-left chrome.
 */
export function Credits() {
  return (
    <p className="pointer-events-none absolute bottom-[max(0.5rem,env(safe-area-inset-bottom))] right-3 z-10 max-w-[52vw] text-right font-mono text-[9px] leading-tight text-[var(--color-ink-faint)]/70 sm:right-16">
      Imagery NASA EOSDIS GIBS · labels © CARTO, OpenStreetMap
    </p>
  )
}
