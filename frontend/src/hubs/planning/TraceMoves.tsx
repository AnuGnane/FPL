import { fmtDelta } from '../../kit'
import type { PlanMoveTrace } from '../../types'

/**
 * The rows of one move trace: the pair, its signed gain in the objective's
 * own terms, and whatever the solver could not price.
 *
 * Cut out of `PlannerBoard.tsx` in v18f §2.1, where the board was over five
 * hundred lines and wrote this markup twice — once for a week's own trace and
 * once for the objective's (v16 §4).
 */
export default function TraceMoves(
  { moves, gw }: {
    moves: PlanMoveTrace[]
    /** The week, when these are a *week's* rows: it names the test id and
     *  brings the solver's per-move note with it. The objective panel passes
     *  no week and draws neither, exactly as it always has. */
    gw?: number
  },
) {
  return (
    <>
      {moves.map((m) => (
        <p key={`${m.buy_code}-${m.sell_code}`}
           className="font-mono tn text-xs"
           data-testid={gw === undefined
             ? undefined : `board-why-move-${gw}-${m.buy_code}`}>
          <span>{`${m.sell_name} → ${m.buy_name}`}</span>
          <span className="ml-2 text-text">
            {fmtDelta(m.ep_gain)}
          </span>
          {gw !== undefined && m.note && (
            <span className="ml-2 text-text-faint">{m.note}</span>
          )}
        </p>
      ))}
    </>
  )
}
