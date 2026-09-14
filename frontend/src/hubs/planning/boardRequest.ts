import type { PlanGw, WhatIfRequest } from '../../types'
import { CHIP_CODES } from './chips'

/**
 * The request the planner board hands the What-If lab, as a pure function of
 * the two things it depends on — cut out of `PlannerBoard.tsx` in v18f §2.1,
 * where the board was over five hundred lines and this was the one piece of
 * it with an answer a table can state.
 */

/** The board's state a handoff reads, and nothing else: the week whose button
 *  was pressed, and the gameweek the board is drawn for. Not the component's
 *  props — `onTry` and the fetched plan have no say in the body. */
export interface BoardRequestState {
  week: PlanGw
  /** The gameweek the board opens on. The lab always solves from *now*, so
   *  this is where the prefilled solve starts. */
  gw: number
}

// Clamped into ConstraintsPanel's own 1-6 range: past six weeks the lab
// cannot span it and the sentence under the button says so.
export const HORIZON_MAX = 6

export function horizonFor({ week, gw }: BoardRequestState): number {
  return Math.max(1, Math.min(HORIZON_MAX, week.gw - gw + 1))
}

/**
 * A planned week as the constraint vocabulary can express it (plan A7).
 * `ban` is not an exact fit for a sell — it also forbids buying him back —
 * and there is no bank constraint at all; both are printed under the button
 * rather than smoothed over, because a limit discovered by hovering is a
 * limit discovered after the solve.
 *
 * The lab always solves from *now*. A week further down the board is
 * therefore only inside the solve if the horizon reaches it, so the handoff
 * spans it rather than leaving the constraints to be applied to a horizon
 * that stops short — a solve told to buy a GW8 target over a one-week plan
 * buys him this week instead, which is a different plan wearing the board's
 * numbers.
 */
export function boardRequest(state: BoardRequestState): WhatIfRequest {
  const { week } = state
  return {
    lock: [],
    ban: [],
    // v11 carried a planned sell across as `ban`, which also forbade buying
    // him back — the imprecision plan A7 printed under the button. §4.1 gave
    // the solver the constraint that actually says "sell him".
    force_out: week.sells.map((m) => m.code),
    force_in: week.buys.map((m) => m.code),
    max_hits: Math.max(0, Math.min(3, week.hits)),
    max_transfers: null,
    chip: (week.chip && CHIP_CODES[week.chip]) || 'none',
    horizon: horizonFor(state),
  }
}
