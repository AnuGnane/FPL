import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Badge, Card, EmptyState, Loading, PosBadge, fmtDelta, fmtNum,
} from '../../kit'
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
  { move, side, mover, differs = false }: { move: PlanMove
                                            side: 'in' | 'out'
                                            mover?: MoverRow
                                            /** This plan makes this move and
                                             *  Plan A does not (v12 W3 §4.3).
                                             *  Always false on Plan A. */
                                            differs?: boolean },
) {
  return (
    <p
      data-testid={`board-${side}-${move.code}`}
      data-differs={String(differs)}
      className={`flex flex-wrap items-center gap-1 ${side === 'in'
        ? 'text-sage' : 'text-rust'} ${differs
        ? 'border-l-2 border-current pl-1.5' : ''}`}
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
  // Which plan the strip is on. Plan A is the recommendation and is index 0;
  // an alternative is 1-based into `data.alternatives`. Not persisted, for
  // ThisWeek.tsx:31-34's standing reason: a view preference is a real feature
  // with real questions behind it, and inventing an answer inside a lean cycle
  // is how a preference store gets built by accident.
  const [pick, setPick] = useState(0)
  // Null while it loads and after any failure. A price decoration must never
  // be the reason a plan does not render — Timeline's ticker rule, verbatim.
  const [movers, setMovers] = useState<Map<number, MoverRow> | null>(null)

  useEffect(() => {
    // The same `live` guard the movers fetch has, for the same reason: a
    // gameweek switched while this one is in flight would otherwise let the
    // stale response land on top of the new one, and the board would draw
    // last week's plan under this week's heading.
    let live = true
    setMissing(false)
    // A new gameweek's plan set is a different set; holding index 2 across the
    // switch would open on whichever plan happened to land there.
    setPick(0)
    apiGet<PlanTimeline>(`/api/plan/${gw}`)
      .then((body) => { if (live) setData(body) })
      .catch(() => { if (live) setMissing(true) })
    return () => { live = false }
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
        for (const row of body.rows) {
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
  //
  // The lab always solves from *now*. A week further down the board is
  // therefore only inside the solve if the horizon reaches it, so the handoff
  // spans it rather than leaving the constraints to be applied to a horizon
  // that stops short — a solve told to buy a GW8 target over a one-week plan
  // buys him this week instead, which is a different plan wearing the board's
  // numbers. Clamped into ConstraintsPanel's own 1-6 range: past six weeks
  // the lab cannot span it and the sentence under the button says so.
  const HORIZON_MAX = 6

  function horizonFor(week: PlanGw): number {
    return Math.max(1, Math.min(HORIZON_MAX, week.gw - gw + 1))
  }

  function request(week: PlanGw): WhatIfRequest {
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
      horizon: horizonFor(week),
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

  // v12 W3 §4.3 (specs/2026-09-01-gaffer-v12-program-design.md). An artifact
  // written before v12 carries no key at all, so the empty list is the normal
  // case rather than the degraded one.
  const alternatives = data.alternatives ?? []
  // Null on Plan A. Also null if `pick` outran the list — a payload that
  // shrank under a re-fetch must fall back to the recommendation, never blank.
  const shown = pick > 0 ? alternatives[pick - 1] ?? null : null
  const weeks = shown ? shown.weeks : data.weeks

  // Which of this plan's moves Plan A does not make, per week — the "differing
  // moves highlighted" of spec §4.3. Computed against Plan A's own week rather
  // than against its whole horizon: a buy Plan A makes in GW7 is still a
  // different decision when this plan makes it in GW5.
  const planAMoves = new Map<number, Set<number>>(
    data.weeks.map((w) => [w.gw, new Set([...w.buys, ...w.sells]
      .map((m) => m.code))]))

  function differs(week: PlanGw, move: PlanMove): boolean {
    return shown !== null
      && !(planAMoves.get(week.gw)?.has(move.code) ?? false)
  }

  return (
    <div>
      <p className="mb-2 text-text-muted">
        {'Starting bank '}
        <span className="num text-text">{fmtNum(data.bank)}</span>
        {' — the horizon the last advice run solved. The board draws that '
         + 'plan; it never re-solves.'}
      </p>
      {/* Drawn only when there is something to switch to: a strip with one tab
          in it is a control that does nothing. It wraps rather than scrolling,
          which is ChipsTab's established answer for the same control. */}
      {alternatives.length > 0 && (
        // A tablist, not a row of toggles: each control swaps the panel below
        // rather than turning something on, and aria-pressed said the latter.
        <div className="mb-3 flex flex-wrap gap-1" data-testid="plan-tabs"
             role="tablist" aria-label="Plan A and its alternatives"
             // T8-T11 review, Minor 9: the roles arrived without the keyboard
             // half of the pattern. A tablist is one tab stop — the roving
             // tabindex below — and the arrows move within it, wrapping,
             // because a strip is a ring rather than a list with two ends.
             // Selection follows focus, which is the right variant here: the
             // panel is already-solved data, so moving to a tab costs nothing.
             onKeyDown={(e) => {
               const n = alternatives.length + 1
               const to = e.key === 'ArrowRight' ? (pick + 1) % n
                 : e.key === 'ArrowLeft' ? (pick - 1 + n) % n
                   : e.key === 'Home' ? 0
                     : e.key === 'End' ? n - 1 : null
               if (to === null) return
               e.preventDefault()
               setPick(to)
               document.getElementById(`plan-tab-${to}`)?.focus()
             }}>
          {['Plan A', ...alternatives.map((a) => a.label)].map(
            (label, i) => (
              <button
                key={label}
                type="button"
                role="tab"
                id={`plan-tab-${i}`}
                aria-selected={pick === i}
                aria-controls="plan-board"
                tabIndex={pick === i ? 0 : -1}
                onClick={() => setPick(i)}
                className={`rounded-card border px-3 py-1.5 ${pick === i
                  ? 'border-text text-text' : 'border-border text-text-muted'}`}
              >
                {label}
              </button>
            ))}
        </div>
      )}
      {shown !== null && (
        <p className="mb-2 text-text-muted" data-testid="plan-gap">
          {shown.gap === null
            ? 'This plan’s distance from Plan A could not be read.'
            : shown.gap >= 0
              ? `${fmtNum(shown.gap)} objective points behind Plan A.`
              // Two causes, and naming only the first would be a claim the
              // solver cannot support: the recommendation is held to the
              // sweep's moves and this plan is not, *and* the two plans'
              // bench and vice weightings are derived from their own XIs, so
              // a small gap either way can be that instead.
              : `${fmtNum(Math.abs(shown.gap))} objective points AHEAD of `
                + 'Plan A on its own objective — the recommendation was held '
                + 'to the moves the scenario sweep voted for, or the two '
                + 'plans’ bench weightings differ.'}
          {' Objective points are the solver’s own frame: later weeks are '
           + 'discounted and banked transfers are priced, so this is not a '
           + 'raw xPts gap.'}
        </p>
      )}
      {/* v12 W5 §6.5: the trace is the objective's terms at the plan the
          solver returned, and this is not that plan. Said here rather than
          left as an absent control the reader has to notice. */}
      {shown !== null && (
        <p className="mb-2 text-text-faint" data-testid="plan-no-trace">
          {'“Why this move” is shown for Plan A only: the trace prices the '
           + 'plan the solver returned, and this one came out of a different '
           + 'solve with its own free-transfer count.'}
        </p>
      )}
      {/* One column per week the plan names, and never a padded sixth: a
          shorter horizon is a shorter board. */}
      <div className="flex gap-3 overflow-x-auto pb-2" id="plan-board"
           role={alternatives.length > 0 ? 'tabpanel' : undefined}
           aria-labelledby={alternatives.length > 0
             ? `plan-tab-${pick}` : undefined}>
        {weeks.map((week) => (
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
                           mover={movers?.get(m.code)}
                           differs={differs(week, m)} />
                ))}
                {week.sells.map((m) => (
                  <MoveRow key={`out-${m.code}`} move={m} side="out"
                           mover={movers?.get(m.code)}
                           differs={differs(week, m)} />
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
                  ? 'A move in this week or an earlier one has no price, or '
                    + 'could not be read at all, so the running bank is '
                    + 'unknown from here on. It is not zero.'
                  : 'What is left after this week\'s moves, in millions.'}
              >
                {fmtNum(week.bank)}
              </p>
              <p className="mt-2 label">xPts</p>
              <p className="num text-xl text-text">
                {fmtNum(week.expected_pts)}
              </p>
              {/* v12 W5 §6.5. Every line below is a term of the solver's own
                  objective at the plan it returned — no re-solve, and the
                  caption at the bottom says so rather than leaving "+3.5" to
                  be read as a comparison. */}
              {week.trace && (
                <details className="mt-2" data-testid={`board-why-${week.gw}`}>
                  <summary className="cursor-pointer text-text-muted">
                    Why this move
                  </summary>
                  <div className="mt-1 flex flex-col gap-0.5">
                    {week.trace.moves.length === 0 && (
                      <p className="text-text-muted">No moves this week.</p>
                    )}
                    {week.trace.moves.map((m) => (
                      <p key={`${m.buy_code}-${m.sell_code}`}
                         data-testid={`board-why-move-${week.gw}-${m.buy_code}`}>
                        <span>{`${m.sell_name} → ${m.buy_name}`}</span>
                        <span className="num ml-2 text-text">
                          {fmtDelta(m.ep_gain)}
                        </span>
                        {m.note && (
                          <span className="ml-2 text-text-faint">{m.note}</span>
                        )}
                      </p>
                    ))}
                    {/* "after decay" is not decoration. The badge above this
                        panel prints `week.hit_cost` — the undecayed
                        `hits × 4` the FPL rules charge — and this is the
                        objective's own term, `hits × 4 × decay**i`. On any
                        week but the first they are two different numbers on
                        one card, and without the clause the reader has to
                        guess which of them is wrong. */}
                    {week.trace.hit_cost > 0 && (
                      <p className="text-rust"
                         title={'The badge above is what the hits cost you. '
                           + 'This is what the solver paid for them: the same '
                           + 'charge discounted by this week’s decay factor, '
                           + 'which is why a later week’s is smaller.'}>
                        {`hit charge −${fmtNum(week.trace.hit_cost)} `
                         + 'after decay'}
                      </p>
                    )}
                    <p className="text-text-faint">
                      {`${week.trace.ft_used} free transfer(s) used; one is `
                       + `worth ${fmtNum(week.trace.ft_shadow)} at the end of `
                       + `the horizon (${week.trace.ft_basis})`}
                    </p>
                    {week.trace.ft_use_penalty > 0 && (
                      <p className="text-text-faint">
                        {`transfer friction −`
                         + `${fmtNum(week.trace.ft_use_penalty, 3)}`}
                      </p>
                    )}
                    {week.trace.bank_value !== null
                      && week.trace.bank_value !== undefined && (
                      <p className="text-text-faint">
                        {`bank left at the end of the horizon, valued `
                         + `${fmtNum(week.trace.bank_value, 3)}`}
                      </p>
                    )}
                    {week.trace.theta !== null && (
                      <p className="text-text-faint">
                        {`chip threshold θ ${fmtNum(week.trace.theta)}`}
                      </p>
                    )}
                    {/* Only when there is a number. `null` means the term was
                        off or the log had no row for a player sold here, and
                        a "−0.00" would read as a charge that was checked and
                        found to be nothing. The week's note carries which. */}
                    {week.trace.price_charge !== null
                      && week.trace.price_charge !== 0 && (
                      <p className="text-text-faint">
                        {`price-timing charge −`
                         + `${fmtNum(week.trace.price_charge, 3)}`
                         + ', priced against tonight’s price log'}
                      </p>
                    )}
                    {week.trace.note && (
                      <p className="text-text-faint"
                         data-testid={`board-why-note-${week.gw}`}>
                        {week.trace.note}
                      </p>
                    )}
                    {/* The sentence that stops "+3.5" being read as a
                        comparison against not doing it, and the one that
                        stops these lines being added up and compared to the
                        week's xPts. Printed, never hovered: a caveat
                        discovered by hovering is a caveat discovered after
                        the decision. */}
                    <p className="text-text-faint">
                      {'These are the plan’s own objective terms for the '
                       + 'moves it made, not a comparison against a plan that '
                       + 'did not make them — the board never re-solves. The '
                       + 'captain, vice and bench weightings are not '
                       + 'attributed here, so these lines do not add up to '
                       + 'the week’s xPts.'}
                    </p>
                  </div>
                </details>
              )}
              {/* No handoff from an alternative: it was solved without the
                  sweep's coherence constraints, and prefilling its moves into
                  a lab that solves from now would silently re-impose them
                  (v12 W3 §4.3). */}
              {onTry && shown === null
                && (week.buys.length > 0 || week.sells.length > 0) && (
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
                  <p data-testid={`board-try-note-${week.gw}`}
                     className="mt-1 text-text-faint">
                    {'This prefills the lab; it does not solve. A planned sell '
                     + 'is carried across as "must sell": he is sold in the '
                     + 'solve\'s first week and the bank receives his selling '
                     + 'price. The bank itself is still not a constraint the '
                     + 'lab accepts.'}
                    {/* The horizon spans the week, but the solve still starts
                        this week — every limit of that is said here rather
                        than left to be discovered in the result. */}
                    {` The constraints are applied to a solve that starts now `
                     + `at GW${gw}, over ${horizonFor(week)} week(s)`
                     + `${week.gw - gw + 1 > HORIZON_MAX
                       ? `, which is as far as the lab reaches and stops short `
                         + `of GW${week.gw}` : ''} — a future week's buys may `
                     + `need earlier sells first, and a prefilled chip is `
                     + `played in the solve's first week, not scheduled.`}
                    {week.hits > 3
                      && ' Hits capped at 3 (the lab’s limit).'}
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
