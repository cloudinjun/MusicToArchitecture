/**
 * Shared motion conventions for the SVG panels.
 *
 * anime.js owns the DOM/SVG layer only. The 3D assembly runs on the r3f clock and
 * must never be driven from here — two clocks fighting over one scene is how motion
 * starts to stutter. Panels animate once per meaningful event (first open, a level
 * change, a run change), never on incidental re-renders, and everything collapses to
 * final state under `prefers-reduced-motion`.
 */

export function reducedMotion(): boolean {
  return typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** The house ease, as anime.js spells it. */
export const EASE_OUT = 'cubicBezier(0.23, 1, 0.32, 1)';
