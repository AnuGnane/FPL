import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Badge, Card, EmptyState, Loading, PosBadge, fmtNum } from '../../kit'
import type { PlanMove, PlanTimeline } from '../../types'

/**
 * v11 §F1 — the solved horizon, week by week.
 *
 * It fetches `/api/plan/{gw}` itself rather than sharing Timeline's (plan
 * A10): Radix unmounts an inactive tab, so a board on a sixth tab would fetch
 * it on first open anyway, and hoisting a read-only GET into the hub would put
 * a second request in Planning for the benefit of a tab the reader may never
 * open. The two views therefore read the same endpoint and must not disagree
 * about it — the accessors below are Timeline's.
 *
 * **The board never solves.** It draws the plan the advice run wrote.
 */

function MoveRow({ move, side }: { move: PlanMove; side: 'in' | 'out' }) {
  return (
    <p
      data-testid={`board-${side}-${move.code}`}
      className={`flex items-center gap-1 ${side === 'in'
        ? 'text-sage' : 'text-rust'}`}
    >
      <span aria-hidden>{side === 'in' ? '↑' : '↓'}</span>
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
      {move.price !== null && (
        <span className="num ml-1 text-text-faint">{fmtNum(move.price)}</span>
      )}
    </p>
  )
}

export default function PlannerBoard({ gw }: { gw: number }) {
  const [data, setData] = useState<PlanTimeline | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    setMissing(false)
    apiGet<PlanTimeline>(`/api/plan/${gw}`).then(setData)
      .catch(() => setMissing(true))
  }, [gw])

  // The two empty states are different facts and get different words: nothing
  // was ever advised, versus a run that solved no horizon. Collapsing them
  // would tell a reader to run advise when he already has.
  if (missing) {
    return (
      <EmptyState
        title="Nothing to plan from"
        detail="The board lays out the horizon the last advice run solved.
                Nothing has been solved for this gameweek yet."
        action="Run advise"
      />
    )
  }
  if (!data) return <Loading />
  if (data.weeks.length === 0) {
    return (
      <EmptyState
        title="This run solved no horizon"
        detail="The advice for this gameweek recorded no week-by-week plan —
                re-run advise to write one."
        action="Run advise"
      />
    )
  }

  return (
    <div>
      <p className="mb-2 text-text-muted">
        {'Starting bank '}
        <span className="num text-text">{fmtNum(data.bank)}</span>
        {' — the horizon the last advice run solved. The board draws that '
         + 'plan; it never re-solves.'}
      </p>
      {/* One column per week the plan names, and never a padded sixth: a
          shorter horizon is a shorter board. */}
      <div className="flex gap-3 overflow-x-auto pb-2">
        {data.weeks.map((week) => (
          <div key={week.gw} data-testid={`board-week-${week.gw}`}
               className="min-w-[220px] flex-1">
            <Card
              title={`GW${week.gw}`}
              action={week.chip
                ? <Badge variant="info">{week.chip}</Badge>
                : null}
            >
              <div className="flex flex-col gap-0.5">
                {week.buys.map((m) => (
                  <MoveRow key={`in-${m.code}`} move={m} side="in" />
                ))}
                {week.sells.map((m) => (
                  <MoveRow key={`out-${m.code}`} move={m} side="out" />
                ))}
                {week.buys.length === 0 && week.sells.length === 0 && (
                  <p className="text-text-muted">No moves.</p>
                )}
              </div>
              {week.hits > 0 && (
                <p data-testid={`board-hits-${week.gw}`} className="mt-2">
                  <Badge variant="negative">
                    {`${week.hits} hit${week.hits === 1 ? '' : 's'} `
                     + `· -${week.hit_cost}`}
                  </Badge>
                </p>
              )}
              <p className="mt-2 label">Bank after</p>
              <p
                data-testid={`board-bank-${week.gw}`}
                className="num text-text"
                title={week.bank === null
                  ? 'A move in this week or an earlier one has no price, so '
                    + 'the running bank is unknown from here on. It is not '
                    + 'zero.'
                  : 'What is left after this week\'s moves, in millions.'}
              >
                {fmtNum(week.bank)}
              </p>
              <p className="mt-2 label">xPts</p>
              <p className="num text-xl text-text">
                {fmtNum(week.expected_pts)}
              </p>
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}
