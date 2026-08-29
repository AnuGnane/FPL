import { describe, expect, it } from 'vitest'
import { fmtDelta, fmtNum, fmtPct, fmtPrice } from './format'

describe('formatters', () => {
  it('renders an em dash for anything that is not a finite number', () => {
    for (const bad of [null, undefined, NaN, Infinity]) {
      expect(fmtNum(bad as number | null)).toBe('—')
      expect(fmtPct(bad as number | null)).toBe('—')
      expect(fmtPrice(bad as number | null)).toBe('—')
      expect(fmtDelta(bad as number | null)).toBe('—')
    }
  })

  it('rounds to one decimal by default and honours an explicit precision', () => {
    expect(fmtNum(6.44)).toBe('6.4')
    expect(fmtNum(6.44, 2)).toBe('6.44')
    expect(fmtNum(0)).toBe('0.0')
  })

  it('renders a fraction as a whole percent', () => {
    expect(fmtPct(0.856)).toBe('86%')
    expect(fmtPct(0)).toBe('0%')
  })

  it('renders 0.1m price units as millions', () => {
    expect(fmtPrice(128)).toBe('12.8')
  })

  it('signs deltas so a gain is unmistakable', () => {
    expect(fmtDelta(1.25)).toBe('+1.3')
    expect(fmtDelta(-1.25)).toBe('-1.3')
    expect(fmtDelta(0)).toBe('0.0')
  })
})
