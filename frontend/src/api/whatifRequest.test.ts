/**
 * Holiday F-156 — the request the What-If lab opens on, now shared from
 * `api/` by the lab and the squad's row menu (v19e §2.4).
 */
import { describe, expect, it } from 'vitest'
import { EMPTY_WHATIF } from './whatifRequest'

describe('EMPTY_WHATIF', () => {
  it('constrains nothing: no players named, no hits, no chip', () => {
    expect(EMPTY_WHATIF).toEqual({
      lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
      max_transfers: null, chip: 'none', horizon: null,
    })
  })

  it('leaves the base object alone when a handoff spreads one code into it', () => {
    // PlayerActions' shape: a fresh array replaces the field, so the next
    // menu click still starts from nothing.
    const request = { ...EMPTY_WHATIF, lock: [7] }
    expect(request.lock).toEqual([7])
    expect(EMPTY_WHATIF.lock).toEqual([])
  })
})
