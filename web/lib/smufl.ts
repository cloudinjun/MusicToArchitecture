/**
 * The handful of SMuFL facts the score strip engraves with.
 *
 * SMuFL is the Standard Music Font Layout; Bravura is its reference font. Glyphs live
 * in the private-use range, one em is four staff spaces, and each glyph carries a
 * bounding box and stem anchors in staff spaces. The values here are Bravura's
 * published metadata (`redist/Bravura.json`) for the glyphs the strip uses, kept
 * inline so the client never fetches a 500 KB JSON to draw six measures.
 */

export const SMUFL = {
  gClef: '',
  noteheadBlack: '',
  restQuarter: '',
  metNoteQuarterUp: '',
  dynamicPiano: '',
  dynamicMP: '',
  dynamicMF: '',
  dynamicForte: '',
} as const;

/** Bravura engraving defaults, in staff spaces. */
export const ENGRAVING = {
  staffLineThickness: 0.13,
  stemThickness: 0.12,
  beamThickness: 0.5,
  beamSpacing: 0.25,
  thinBarlineThickness: 0.16,
  thickBarlineThickness: 0.5,
  barlineSeparation: 0.4,
  hairpinThickness: 0.16,
  /** The conventional stem: three and a half spaces from the notehead. */
  stemLength: 3.5,
} as const;

/** Bravura glyph boxes and anchors, in staff spaces, origin at the glyph's left on its baseline. */
export const GLYPH = {
  noteheadBlack: { width: 1.18, stemUpSE: [1.18, 0.168] as const },
  gClef: { width: 2.684, above: 4.392, below: 2.632 },
  metNoteQuarterUp: { width: 1.328, above: 2.752 },
  /** Ink extents of the dynamics: how far left of the origin they reach, and their width. */
  dynamic: {
    p: { left: 0.356, width: 1.82 },
    mp: { left: 0.08, width: 3.38 },
    mf: { left: 0.08, width: 3.35 },
    f: { left: 0.564, width: 2.02 },
  },
} as const;

/** The dynamic glyph for a mark. */
export function dynamicGlyph(mark: 'p' | 'mp' | 'mf' | 'f'): string {
  return { p: SMUFL.dynamicPiano, mp: SMUFL.dynamicMP, mf: SMUFL.dynamicMF, f: SMUFL.dynamicForte }[mark];
}
