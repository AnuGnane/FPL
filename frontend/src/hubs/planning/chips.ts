import type { WhatIfRequest } from '../../types'

/**
 * The two chip lookups, cut out of `ChipsTab.tsx` in v18f §2.1.
 *
 * They live here because both sides of that cut read them: the tab and its
 * season-outlook panel print the same labels, and the planner board's request
 * builder maps the same names onto the same codes. Left in the tab, the panel
 * would have to import back out of the file it was cut from — a cycle around
 * the very file the cut exists to thin.
 */

export const LABELS: Record<string, string> = {
  wildcard: 'Wildcard',
  bboost: 'Bench Boost',
  freehit: 'Free Hit',
  '3xc': 'Triple Captain',
  // v12 W3 §4.5: the one chip *pair*, named rather than composed.
  'wildcard+bboost': 'Wildcard + Bench Boost',
}

// The chip table speaks the solver's names; the What-If request speaks the
// API's two-letter codes. A row the mapping does not know is left alone
// rather than mapped to 'none', which would silently re-solve without a chip
// and look like the chip was worth nothing.
// Exported since v11: the planner board maps the same chip names onto the same
// codes when it prefills the lab, and two copies of this table would drift.
export const CHIP_CODES: Record<string, WhatIfRequest['chip']> = {
  wildcard: 'wc',
  bboost: 'bb',
  freehit: 'fh',
  '3xc': 'tc',
}
