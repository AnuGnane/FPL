/**
 * Holiday F-153 — the chart palette (spec §8, plan R6): four greys, every
 * one a token rather than a colour, the first two solid and the third and
 * fourth dashed so four lines stay tellable.
 */
import { describe, expect, it } from 'vitest'
import { SERIES_COLOURS, SERIES_DASH } from './series'

describe('series', () => {
  it('is four grey tokens with no blue, green or rust', () => {
    expect(SERIES_COLOURS).toEqual([
      'var(--color-text)', 'var(--color-text-muted)',
      'var(--color-text-secondary)', 'var(--color-text-faint)',
    ])
  })

  it('dashes the third and fourth series and only those', () => {
    expect(SERIES_DASH).toHaveLength(SERIES_COLOURS.length)
    expect(SERIES_DASH.slice(0, 2)).toEqual([undefined, undefined])
    expect(SERIES_DASH.slice(2).every((dash) => dash === '4 3')).toBe(true)
  })
})
