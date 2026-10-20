/**
 * Holiday F-153 — the chart palette (spec §8, plan R6): four greys, every
 * one a token rather than a colour, the first two solid and the third and
 * fourth dashed so four lines stay tellable.
 */
import { describe, expect, it } from 'vitest'
import { SERIES_COLOURS, SERIES_DASH, dotFor } from './series'

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

  // Holiday F-158: a one-point series is no path at all, so it gets a dot.
  it('draws no dot on a series of two or more points, or of none', () => {
    expect(dotFor(0, SERIES_COLOURS[0])).toBe(false)
    expect(dotFor(2, SERIES_COLOURS[0])).toBe(false)
    expect(dotFor(38, SERIES_COLOURS[1])).toBe(false)
  })

  it('draws a lone point as a dot in its own series colour', () => {
    expect(dotFor(1, SERIES_COLOURS[2]))
      .toEqual({ r: 3, strokeWidth: 0, fill: SERIES_COLOURS[2] })
  })

  it('never falls back to recharts\' white dot', () => {
    for (const stroke of SERIES_COLOURS) {
      const dot = dotFor(1, stroke)
      expect(dot && dot.fill).toBe(stroke)
    }
  })
})
