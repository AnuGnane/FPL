import { describe, expect, it } from 'vitest'
import type { LadderPayload } from '../../types'
import { capText } from './ladderText'

// Holiday F-154: the one line This Week and the ladder card both print
// (v17h §3), pinned here so neither card's test has to.

function payload(free_transfers: number | null,
                 max_hits: number | null,
                 max_transfers: number | null = null): LadderPayload {
  return { free_transfers, cap: { max_hits, max_transfers } } as LadderPayload
}

describe('capText', () => {
  it('says one free transfer and one hit in the singular', () => {
    expect(capText(payload(1, 1))).toBe('1 free transfer · cap 1 hit')
  })

  it('says two free transfers and two hits in the plural', () => {
    expect(capText(payload(2, 2))).toBe('2 free transfers · cap 2 hits')
  })

  it('says the hits are uncapped when there is no cap', () => {
    expect(capText(payload(null, null))).toBe('0 free transfers · hits uncapped')
  })

  it('says bank when no transfer is allowed and names a move cap otherwise', () => {
    expect(capText(payload(1, 0, 0))).toBe('1 free transfer · cap 0 hits · bank')
    expect(capText(payload(1, 0, 1)))
      .toBe('1 free transfer · cap 0 hits · max 1 transfer')
  })
})
