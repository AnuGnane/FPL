import { describe, expect, it } from 'vitest'
import { CHIP_CODES, LABELS } from './chips'

// Holiday F-154: the two lookups cut out of `ChipsTab.tsx` in v18f §2.1.

describe('chip lookups', () => {
  it('labels every solver chip name and the one chip pair', () => {
    expect(LABELS['wildcard']).toBe('Wildcard')
    expect(LABELS['bboost']).toBe('Bench Boost')
    expect(LABELS['freehit']).toBe('Free Hit')
    expect(LABELS['3xc']).toBe('Triple Captain')
    expect(LABELS['wildcard+bboost']).toBe('Wildcard + Bench Boost')
  })

  it('maps each solver name onto its What-If code, one to one', () => {
    expect(CHIP_CODES).toEqual({ wildcard: 'wc', bboost: 'bb',
                                 freehit: 'fh', '3xc': 'tc' })
    // The reverse direction: no two names share a code.
    expect(new Set(Object.values(CHIP_CODES)).size)
      .toBe(Object.keys(CHIP_CODES).length)
  })

  it('leaves a name it does not know unmapped rather than none', () => {
    // The comment's rule: an unknown row must not re-solve as 'none'.
    expect(CHIP_CODES['wildcard+bboost']).toBeUndefined()
    expect(CHIP_CODES['unknown']).toBeUndefined()
    expect(LABELS['unknown']).toBeUndefined()
  })
})
