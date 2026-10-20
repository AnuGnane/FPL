/**
 * The chart palette (spec §8, plan R6). Blue is chrome (rule 3) and green/
 * rust are directions (rule 1), so a series that is merely "the second
 * rival" is grey: text, muted, secondary, faint, with the third and fourth
 * dashed so four lines stay tellable. Whoever draws "you" draws them first.
 */
export const SERIES_COLOURS = [
  'var(--color-text)', 'var(--color-text-muted)',
  'var(--color-text-secondary)', 'var(--color-text-faint)',
]

export const SERIES_DASH: Array<string | undefined> = [
  undefined, undefined, '4 3', '4 3',
]

/**
 * Holiday F-158 (ROADMAP v11's residual): a one-point series is no path at
 * all, and recharts' own fallback dot is filled white, a colour no token
 * names. A lone point is drawn as a dot filled in the series' own stroke; two
 * points are a line and need none, so `dot` stays off for every longer season.
 */
export function dotFor(n: number, stroke: string)
  : false | { r: number, strokeWidth: number, fill: string } {
  return n === 1 ? { r: 3, strokeWidth: 0, fill: stroke } : false
}
