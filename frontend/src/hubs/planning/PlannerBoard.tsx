import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Badge, Card, EmptyState, Loading, PosBadge, fmtNum } from '../../kit'
import type {
  MoverRow, MoversPanel, PlanGw, PlanMove, PlanTimeline, WhatIfRequest,
} from '../../types'
import { CHIP_CODES } from './ChipsTab'

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

function MoveRow(
  { move, side, mover }: { move: PlanMove; side: 'in' | 'out'
                           mover?: MoverRow },
) {
  return (
    <p
      data-testid={`board-${side}-${move.code}`}
      className={`flex flex-wrap items-center gap-1 ${side === 'in'
        ? 'text-sage' : 'text-rust'}`}
    >
      <span aria-hidden>{side === 'in' ? '↑' : '↓'}</span>
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
      {move.price !== null && (
        <span className="num ml-1 text-text-faint">{fmtNum(move.price)}</span>
      )}
      {/* The direction and how far through the threshold he is, and nothing
          else: MoverRow carries no predicted price, and a board printing
          "→ £8.6m" would be inventing the number (plan A9). */}
      {mover && (
        <span
          data-testid={`board-mover-${move.code}`}
          className="text-text-faint"
          title={`${move.name} is ${Math.round(
            Math.abs(mover.price_change_percent))}% of the way to a price `
            + `${mover.direction}`}
        >
          {`${mover.direction === 'rise' ? '▲' : '▼'} `
           + `${Math.round(Math.abs(mover.price_change_percent))}%`}
        </span>
      )}
    </p>
  )
}

export default function PlannerBoard(
  { gw, onTry }: { gw: number
                   /** Prefill the What-If lab and switch to it. Absent, the
                    *  board draws no handoff — it never solves either way. */
                   onTry?: (request: WhatIfRequest) => void },
) {
  const [data, setData] = useState<PlanTimeline | null>(null)
  const [missing, setMissing] = useState(false)
  // Null while it loads and after any failure. A price decoration must never
  // be the reason a plan does not render — Timeline's ticker rule, verbatim.
  const [movers, setMovers] = useState<Map<number, MoverRow> | null>(null)

  useEffect(() => {
    setMissing(false)
    apiGet<PlanTimeline>(`/api/plan/${gw}`).then(setData)
      .catch(() => setMissing(true))
  }, [gw])

  useEffect(() => {
    let live = true
    apiGet<MoversPanel>('/api/prices/movers')
      .then((body) => {
        if (!live) return
        const map = new Map<number, MoverRow>()
        // `calibrating` says the price log is not yet trustworthy, and a
        // warning drawn from an untrustworthy log is worse than no warning —
        // so those rows never enter the map at all.
        for (const row of body.rows ?? []) {
          if (!row.calibrating) map.set(row.code, row)
        }
        setMovers(map)
      })
      .catch(() => { if (live) setMovers(null) })
    return () => { live = false }
  }, [])

  // A planned week as the constraint vocabulary can express it (plan A7).
  // `ban` is not an exact fit for a sell — it also forbids buying him back —
  // and there is no bank constraint at all; both are printed under the button
  // rather than smoothed over, because a limit discovered by hovering is a
  // limit discovered after the solve.
  function request(week: PlanGw): WhatIfRequest {
    return {
      lock: [],
      ban: week.sells.map((m) => m.code),
      force_in: week.buys.map((m) => m.code),
      max_hits: Math.max(0, Math.min(3, week.hits)),
      chip: (week.chip && CHIP_CODES[week.chip]) || 'none',
      horizon: null,
    }
  }

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
                  <MoveRow key={`in-${m.code}`} move={m} side="in"
                           mover={movers?.get(m.code)} />
                ))}
                {week.sells.map((m) => (
                  <MoveRow key={`out-${m.code}`} move={m} side="out"
                           mover={movers?.get(m.code)} />
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
              {onTry && (week.buys.length > 0 || week.sells.length > 0) && (
                <div className="mt-3">
                  <button
                    type="button"
                    data-testid={`board-try-${week.gw}`}
                    onClick={() => onTry(request(week))}
                    className="rounded-card border border-border bg-base px-2
                               py-1 text-text-secondary hover:text-text"
                  >
                    Try these changes
                  </button>
                  <p className="mt-1 text-text-faint">
                    {'This prefills the lab; it does not solve. A planned sell '
                     + 'is carried across as "don\'t own him", which also '
                     + 'rules out buying him back, and the bank is not a '
                     + 'constraint the lab accepts.'}
                  </p>
                </div>
              )}
            </Card>
          </div>
        ))}
      </div>
    </div>
  )
}
