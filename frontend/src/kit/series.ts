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
