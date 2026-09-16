import { useMemo, useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Button, Callout, Card, Chip, Disclosure, EmptyState, Loading, PosBadge,
  StackedRows, fmtNum, segmentClass, useIsMobile,
} from '../../kit'
import type { StackedRow } from '../../kit'
import type {
  MoverRow, MoversPanel, PlanGw, PlanMove, PlanTimeline, WhatIfRequest,
} from '../../types'
import TraceMoves from './TraceMoves'
import { HORIZON_MAX, boardRequest } from './boardRequest'

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

/** How far through the threshold he is, and which way — the whole of what a
 *  price row is allowed to say (plan A9). Computed here so the column and the
 *  phone's pair print one string (v19c §2.1). */
function moverText(mover: MoverRow): string {
  return `${mover.direction === 'rise' ? '▲' : '▼'} `
    + `${Math.round(Math.abs(mover.price_change_percent))}%`
}

function moverTitle(move: PlanMove, mover: MoverRow): string {
  return `${move.name} is ${Math.round(
    Math.abs(mover.price_change_percent))}% of the way to a price `
    + `${mover.direction}`
}

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
        ? 'text-up' : 'text-down'} ${differs
        ? 'border-l-2 border-current pl-1.5' : ''}`}
    >
      <span aria-hidden>{side === 'in' ? '↑' : '↓'}</span>
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
      {move.price !== null && (
        <span className="tn ml-1 text-text-faint">{fmtNum(move.price)}</span>
      )}
      {/* The direction and how far through the threshold he is, and nothing
          else: MoverRow carries no predicted price, and a board printing
          "→ £8.6m" would be inventing the number (plan A9). */}
      {mover && (
        <span
          data-testid={`board-mover-${move.code}`}
          className="text-text-faint"
          title={moverTitle(move, mover)}
        >
          {moverText(mover)}
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
  const mobile = useIsMobile()
  const plan = usePageData<PlanTimeline>(`/api/plan/${gw}`)
  // Which plan the strip is on. Plan A is the recommendation and is index 0;
  // an alternative is 1-based into `data.alternatives`. Not persisted, for
  // ThisWeek.tsx:31-34's standing reason: a view preference is a real feature
  // with real questions behind it, and inventing an answer inside a lean cycle
  // is how a preference store gets built by accident.
  const [pick, setPick] = useState(0)
  // A new gameweek's plan set is a different set; holding index 2 across the
  // switch would open on whichever plan happened to land there. All that is
  // left of the fetching effect this card used to run: v18e §2.3 retired its
  // `live` guard along with the stale-response class the hook's ask counter
  // now closes.
  //
  // v19h §2.1: a guarded render-phase set rather than an effect or a `key` on
  // the board — a key would remount the card and throw away the two reads
  // below with it. The pick re-seeds from the `gw` prop, which is in hand.
  const [seenGw, setSeenGw] = useState(gw)
  if (seenGw !== gw) {
    setSeenGw(gw)
    setPick(0)
  }

  // The price decoration, read beside the plan and never inside it: null
  // while it loads and after any failure, because a price warning must never
  // be the reason a plan does not render — Timeline's ticker rule, verbatim.
  // `calibrating` says the price log is not yet trustworthy, and a warning
  // drawn from an untrustworthy log is worse than no warning, so those rows
  // never enter the map at all.
  const moversPage = usePageData<MoversPanel>('/api/prices/movers')
  const movers = useMemo(() => {
    if (moversPage.data === null) return null
    const map = new Map<number, MoverRow>()
    for (const row of moversPage.data.rows) {
      if (!row.calibrating) map.set(row.code, row)
    }
    return map
  }, [moversPage.data])

  // The body a handoff sends, and the horizon it reaches, are `boardRequest`'s
  // — a pure function of the week and this gameweek, with a table test of its
  // own since v18f §2.1.
  function request(week: PlanGw): WhatIfRequest {
    return boardRequest({ week, gw })
  }

  // `Loaded`'s split, in `Loaded`'s words (v18e ruling 7). `/api/plan` answers
  // 404 for a horizon nobody has solved and a cold clone answers the app-wide
  // 422 (app.py:67-69), so both statuses keep the empty state the cold-clone
  // walk expects; a 500 is a server that broke and must not be painted as a
  // healthy "nothing solved yet". Not through `Loaded` itself because the two
  // empty states below are different facts and get different words — nothing
  // was ever advised, versus a run that solved no horizon — and collapsing
  // them into one slot would tell a reader to run advise when he already has.
  const absent = plan.status === 404 || plan.status === 422
  if (plan.error !== null && !absent) {
    return <Callout tone="error">{plan.error}</Callout>
  }
  if (plan.error !== null) {
    return (
      <EmptyState
        title="Nothing to plan from"
        detail="The board lays out the horizon the last advice run solved.
                Nothing has been solved for this gameweek yet."
        action="Run advise"
      />
    )
  }
  const data = plan.data
  if (data === null) return <Loading />
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

  // v19d §2.2: the note is one paragraph about the whole row, so what it has
  // to say is read off every week shown rather than off the week it sits in.
  const anyMoves = weeks.some((w) => w.buys.length > 0 || w.sells.length > 0)
  const beyondReach = weeks.some((w) => w.gw - gw + 1 > HORIZON_MAX)
  const anyCapped = weeks.some((w) => w.hits > 3)

  /** The week's moves in the order the column prints them — buys, then sells
   *  — computed once for both renderings (v19c §2.1). */
  function moves(week: PlanGw): Array<{ key: string
                                        side: 'in' | 'out'
                                        move: PlanMove }> {
    return [
      ...week.buys.map((move) => (
        { key: `in-${move.code}`, side: 'in' as const, move })),
      ...week.sells.map((move) => (
        { key: `out-${move.code}`, side: 'out' as const, move })),
    ]
  }

  function stackedMoves(week: PlanGw): StackedRow[] {
    return moves(week).map(({ key, side, move }) => {
      const mover = movers?.get(move.code)
      const differing = differs(week, move)
      return {
        key,
        // The direction the arrow and the colour carried on the wide board,
        // said in a word as well: a colour alone is not a direction to a
        // reader who cannot see it.
        lead: (
          <Chip tone={side === 'in' ? 'up' : 'down'}>
            {side === 'in' ? 'IN' : 'OUT'}
          </Chip>
        ),
        title: (
          <span
            data-testid={`board-${side}-${move.code}`}
            data-differs={String(differing)}
            className="inline-flex flex-wrap items-center gap-1.5"
          >
            <PosBadge pos={move.position} variant="dot" />
            {move.name}
            {/* The left rule the wide board draws on a differing move; a
                stacked row has no column to hang it on. */}
            {differing && <Chip>not in Plan A</Chip>}
          </span>
        ),
        pairs: [
          ...(move.price !== null
            ? [{ label: 'Price', value: fmtNum(move.price), numeric: true }]
            : []),
          ...(mover
            ? [{ label: 'Ticker',
                 value: (
                   <span data-testid={`board-mover-${move.code}`}
                         title={moverTitle(move, mover)}>
                     {moverText(mover)}
                   </span>
                 ) }]
            : []),
        ],
      }
    })
  }

  return (
    <div>
      <p className="mb-2 text-text-muted">
        {'Starting bank '}
        <span className="tn text-text">{fmtNum(data.bank)}</span>
        {' — the horizon the last advice run solved. The board draws that '
         + 'plan; it never re-solves.'}
      </p>
      {/* Drawn only when there is something to switch to: a strip with one tab
          in it is a control that does nothing. It wraps rather than scrolling,
          which is ChipsTab's established answer for the same control. */}
      {alternatives.length > 0 && (
        // A tablist, not a row of toggles: each control swaps the panel below
        // rather than turning something on, and aria-pressed said the latter.
        <div className="mb-4 inline-flex flex-wrap divide-x divide-border
                        overflow-hidden rounded-ctl border border-border"
             data-testid="plan-tabs"
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
                className={segmentClass(pick === i)}
              >
                {label}
              </button>
            ))}
        </div>
      )}
      {/* v19d §2.3: the frame an alternative's gap has to be read in, and the
          reason it carries no trace — both worth reading once, and both in
          the way of the columns on every visit after that. One disclosure,
          because they are two halves of the same explanation. */}
      {shown !== null && (
      <Disclosure summary="How to read this" storageKey="board-help">
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
        {/* v12 W5 §6.5: the trace is the objective's terms at the plan the
            solver returned, and this is not that plan. Said here rather than
            left as an absent control the reader has to notice. */}
        <p className="mb-2 text-text-faint" data-testid="plan-no-trace">
          {'“Why this move” is shown for Plan A only: the trace prices the '
           + 'plan the solver returned, and this one came out of a different '
           + 'solve with its own free-transfer count.'}
        </p>
      </Disclosure>
      )}
      {/* One column per week the plan names, and never a padded sixth: a
          shorter horizon is a shorter board. */}
      <div className="flex gap-3 overflow-x-auto pb-2" id="plan-board"
           role={alternatives.length > 0 ? 'tabpanel' : undefined}
           aria-labelledby={alternatives.length > 0
             ? `plan-tab-${pick}` : undefined}>
        {/* No boxes (§5): one hairline rule tells a column from the one
            before it, as on the timeline. */}
        {weeks.map((week, i) => (
          <div key={week.gw} data-testid={`board-week-${week.gw}`}
               className={`min-w-[220px] flex-1${
                 i > 0 ? ' border-l border-border pl-3' : ''}`}>
            <Card
              title={`GW${week.gw}`}
              action={week.chip ? <Chip>{week.chip}</Chip> : null}
            >
              <div className="flex flex-col gap-0.5">
                {moves(week).length === 0 && (
                  <p className="text-text-muted">No moves.</p>
                )}
                {/* v19c §2.1: five columns of board pushed side by side is
                    one column of board on a phone, and a move row that wraps
                    mid-name is unreadable. Stacked, the player is the line
                    and his price and his ticker are labelled under it. */}
                {mobile && moves(week).length > 0 && (
                  <StackedRows testId={`board-stacked-${week.gw}`}
                               rows={stackedMoves(week)} />
                )}
                {!mobile && moves(week).map(({ key, side, move }) => (
                  <MoveRow key={key} move={move} side={side}
                           mover={movers?.get(move.code)}
                           differs={differs(week, move)} />
                ))}
              </div>
              {week.hits > 0 && (
                <p data-testid={`board-hits-${week.gw}`} className="mt-2">
                  <Chip tone="down">
                    {`${week.hits} hit${week.hits === 1 ? '' : 's'} `
                     + `· -${week.hit_cost}`}
                  </Chip>
                </p>
              )}
              <p className="mt-2 label">Bank after</p>
              <p
                data-testid={`board-bank-${week.gw}`}
                className="tn text-text"
                title={week.bank === null
                  ? 'A move in this week or an earlier one has no price, or '
                    + 'could not be read at all, so the running bank is '
                    + 'unknown from here on. It is not zero.'
                  : 'What is left after this week\'s moves, in millions.'}
              >
                {fmtNum(week.bank)}
              </p>
              <p className="mt-2 label">xPts</p>
              <p className="tn text-[22px] font-semibold text-text">
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
                    <TraceMoves moves={week.trace.moves} gw={week.gw} />
                    {/* "after decay" is not decoration. The badge above this
                        panel prints `week.hit_cost` — the undecayed
                        `hits × 4` the FPL rules charge — and this is the
                        objective's own term, `hits × 4 × decay**i`. On any
                        week but the first they are two different numbers on
                        one card, and without the clause the reader has to
                        guess which of them is wrong. */}
                    {week.trace.hit_cost > 0 && (
                      <p className="font-mono tn text-xs text-down"
                         title={'The chip above is what the hits cost you. '
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
                      <p className="font-mono tn text-xs text-text-faint">
                        {`bank left at the end of the horizon, valued `
                         + `${fmtNum(week.trace.bank_value, 3)}`}
                      </p>
                    )}
                    {week.trace.theta !== null && (
                      <p className="font-mono tn text-xs text-text-faint">
                        {`chip threshold θ ${fmtNum(week.trace.theta)}`}
                      </p>
                    )}
                    {/* Only when there is a number. `null` means the term was
                        off or the log had no row for a player sold here, and
                        a "−0.00" would read as a charge that was checked and
                        found to be nothing. The week's note carries which. */}
                    {week.trace.price_charge !== null
                      && week.trace.price_charge !== 0 && (
                      <p className="font-mono tn text-xs text-text-faint">
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
              {/* v16 §4: the objective's own week one, when the ladder's
                  restraint served a different rung. Its trace is the same
                  accounting over the plan the solver returned, so the two
                  "why"s are comparable. Plan A only, like the trace: an
                  alternative carries no trace to compare it with. */}
              {i === 0 && shown === null && data.objective && (
                <details className="mt-2" data-testid="board-objective">
                  <summary className="cursor-pointer text-text-muted">
                    The objective wanted
                  </summary>
                  <div className="mt-1 flex flex-col gap-0.5">
                    <p className="text-text">
                      {[...data.objective.buys.map((m) => `${m.name} in`),
                        ...data.objective.sells.map((m) => `${m.name} out`)]
                        .join(', ') || 'no moves'}
                      {data.objective.hits > 0 && (
                        <span className="text-down">
                          {` · ${data.objective.hits} hit`
                           + `${data.objective.hits === 1 ? '' : 's'}`}
                        </span>
                      )}
                    </p>
                    {data.objective.trace
                      && <TraceMoves moves={data.objective.trace.moves} />}
                    <p className="text-text-faint">
                      {'The board above draws the plan the ladder’s restraint '
                       + 'served; this is the solver’s own choice, traced the '
                       + 'same way.'}
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
                  <Button
                    data-testid={`board-try-${week.gw}`}
                    onClick={() => onTry(request(week))}
                  >
                    Try these changes
                  </Button>
                </div>
              )}
            </Card>
          </div>
        ))}
      </div>
      {/* v19d §2.2: one caveat, under the row it is about. It used to be
          printed under every week column that had moves — nine lines, five
          times over, saying the same thing about the same lab — so the board
          read as a wall of apology rather than a horizon. The one per-week
          fact in it, the week the solve starts from, is the same for every
          button, because the lab always solves from now. */}
      {onTry && shown === null && anyMoves && (
        <p data-testid="board-try-note" className="mt-3 text-text-faint">
          {'Each button prefills the lab; it does not solve. A planned sell '
           + 'is carried across as "must sell": he is sold in the solve\'s '
           + 'first week and the bank receives his selling price. The bank '
           + 'itself is still not a constraint the lab accepts.'}
          {` The constraints are applied to a solve that starts now at GW${gw}`
           + `, over at most ${HORIZON_MAX} weeks — a later week's buys may `
           + `need earlier sells first, and a prefilled chip is played in the `
           + `solve's first week, not scheduled.`}
          {beyondReach
            && ` A week after GW${gw + HORIZON_MAX - 1} is past that reach, `
              + `so its solve stops short of it.`}
          {anyCapped && ' Hits capped at 3 (the lab’s limit).'}
        </p>
      )}
    </div>
  )
}
