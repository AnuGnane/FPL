import { describe, expect, it } from 'vitest'
import type { PlanGw, PlanMove } from '../../types'
import { boardRequest, horizonFor } from './boardRequest'

// v18f §2.1: the handoff the board sends, as a table. The board's own tests
// still press the button and read the call; these state the body itself, week
// by week, without a render.

function move(code: number): PlanMove {
  return { code, name: `p${code}`, position: 'MID', ep: 5, price: 6.5 }
}

function week(over: Partial<PlanGw> = {}): PlanGw {
  return {
    gw: 5, buys: [], sells: [], hits: 0, hit_cost: 0, chip: null,
    captain: null, vice: null, expected_pts: 61.5, bank: 2.1, trace: null,
    ...over,
  }
}

describe('boardRequest', () => {
  it('sends an empty week as no constraints at all', () => {
    expect(boardRequest({ week: week(), gw: 5 })).toEqual({
      lock: [], ban: [], force_out: [], force_in: [], max_hits: 0,
      max_transfers: null, chip: 'none', horizon: 1,
    })
  })

  it('carries a planned sell as a must-sell and never as a ban', () => {
    // v11 mapped the sell onto `ban`, which also forbade buying him back and
    // never credited the bank; §4.1 gave the solver the constraint that says
    // "sell him".
    const body = boardRequest({
      week: week({ buys: [move(1)], sells: [move(2)] }), gw: 5 })
    expect(body.force_out).toEqual([2])
    expect(body.force_in).toEqual([1])
    expect(body.ban).toEqual([])
    expect(body.lock).toEqual([])
  })

  it('maps a week’s chip onto the request code, and an unknown one to none',
    () => {
      expect(boardRequest({ week: week({ chip: 'bboost' }), gw: 5 }).chip)
        .toBe('bb')
      expect(boardRequest({ week: week({ chip: 'freehit' }), gw: 5 }).chip)
        .toBe('fh')
      // A chip pair has no single What-If arm, so the solve runs without one
      // rather than under half of it.
      expect(boardRequest({ week: week({ chip: 'wildcard+bboost' }), gw: 5 })
        .chip).toBe('none')
    })

  it('caps the hits at the three the lab accepts, and never below zero', () => {
    expect(boardRequest({ week: week({ hits: 5 }), gw: 5 }).max_hits).toBe(3)
    expect(boardRequest({ week: week({ hits: 2 }), gw: 5 }).max_hits).toBe(2)
    expect(boardRequest({ week: week({ hits: -1 }), gw: 5 }).max_hits).toBe(0)
  })

  it('spans the horizon to the week whose moves it carries, up to six', () => {
    // The lab always solves from now, so a GW8 buy needs a four-week horizon
    // to be a GW8 buy at all; past six the lab cannot reach and stops short.
    expect(horizonFor({ week: week({ gw: 8 }), gw: 5 })).toBe(4)
    expect(horizonFor({ week: week({ gw: 20 }), gw: 5 })).toBe(6)
    expect(horizonFor({ week: week({ gw: 5 }), gw: 5 })).toBe(1)
    // A week behind the board's own is not a negative horizon.
    expect(horizonFor({ week: week({ gw: 3 }), gw: 5 })).toBe(1)
    expect(boardRequest({ week: week({ gw: 8 }), gw: 5 }).horizon).toBe(4)
  })

  it('never sends a transfer cap the board has no number for', () => {
    expect(boardRequest({ week: week({ hits: 3 }), gw: 5 }).max_transfers)
      .toBeNull()
  })
})
