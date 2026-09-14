import { useMemo } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Card, Chip, EmptyState, Loading, PosBadge, difficultyTone, fmtNum,
} from '../../kit'
import type { PlanMove, PlanTimeline, TickerData } from '../../types'

/** The ticker's own cell shape. Declared locally rather than exported from
 *  `types.ts`, which would move `types.test.ts`'s lockstep pin for a type the
 *  server never sends by that name. */
type TickerCell = TickerData['teams'][number]['cells'][number]

function MoveLine({ move, side }: { move: PlanMove; side: 'in' | 'out' }) {
  return (
    <p className={`flex items-center gap-1 ${side === 'in'
      ? 'text-up' : 'text-down'}`}>
      {/* The arrow carries the verdict; the dot carries the identity. */}
      <span aria-hidden>{side === 'in' ? '↑' : '↓'}</span>
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
      {move.price !== null && (
        <span className="tn ml-1 text-text-faint">{fmtNum(move.price)}</span>
      )}
    </p>
  )
}

export default function Timeline(
  { gw, teamByCode }: { gw: number; teamByCode?: Map<number, number> },
) {
  const plan = usePageData<PlanTimeline>(`/api/plan/${gw}`)
  const data = plan.data

  // Exactly the window the plan covers, asked for after the plan lands — one
  // request, and the only one this decoration costs. `null` until the plan is
  // known is how v18e §2.3 spells a read that waits on another read: no URL
  // is invented for a horizon whose length nobody has said yet.
  //
  // `weeks=N` asks the ticker for N gameweeks *from the current one*, which
  // is the window the plan covers whenever the plan starts at the current
  // gameweek — the ordinary case, since the timeline draws the horizon the
  // last advice run solved. If the two ever fall out of step (a plan banked
  // for a gameweek that has since passed, say), the far end of the horizon
  // falls outside the ticker's window, its cells are missing, and those weeks
  // draw no chips. That is the designed degradation and not a bug to code
  // around: absent, never guessed (spec D6). Widening the request to cover an
  // offset plan would need a start-gameweek parameter the endpoint does not
  // take, which is a server change and not this cycle's.
  const ticker = usePageData<TickerData>(
    data !== null && data.weeks.length > 0
      ? `/api/fixtures/ticker?weeks=${data.weeks.length}` : null)

  // The ticker's own cells, indexed by `${teamCode}:${gw}`. Null while it
  // loads and after any failure — the timeline is the feature and the tint is
  // a decoration on it, so a decoration that cannot load costs nothing else:
  // its failure is silence, where the plan's own is the empty state below.
  const cells = useMemo(() => {
    if (ticker.data === null) return null
    const map = new Map<string, TickerCell>()
    for (const team of ticker.data.teams) {
      for (const cell of team.cells) map.set(`${team.code}:${cell.gw}`, cell)
    }
    return map
  }, [ticker.data])

  // Every failure is this state, exactly as it was before v18e. `/api/plan`
  // answers 404 for a horizon nobody has solved, but a cold clone answers the
  // app-wide 422 for most of what this hub reads (app.py:67-69), so splitting
  // the two on the status here would put a red callout on the one page the
  // documented cold-clone walk expects an empty state on. `Loaded`'s split is
  // for the nine reads spec §2.3 names; this is not one of them.
  const missing = plan.error !== null

  if (missing) {
    return (
      <EmptyState
        title="No plan to draw"
        detail="The timeline reads the horizon the last advice run solved.
                Nothing has been solved for this gameweek yet."
        action="Run advise"
      />
    )
  }
  if (data === null) return <Loading />
  if (data.weeks.length === 0) {
    return (
      <EmptyState
        title="No plan to draw"
        detail="This advice run recorded no horizon — re-run advise to write one."
        action="Run advise"
      />
    )
  }

  return (
    <div className="flex gap-3 overflow-x-auto pb-2">
      {/* No boxes (§5): every column after the first is told apart from its
          neighbour by one hairline rule, not by a card. */}
      {data.weeks.map((week, i) => (
        <div key={week.gw} data-testid={`plan-week-${week.gw}`}
             className={`min-w-[220px] flex-1${
               i > 0 ? ' border-l border-border pl-3' : ''}`}>
          <Card
            title={`GW${week.gw}`}
            action={week.chip ? <Chip>{week.chip}</Chip> : null}
          >
            <p className="label">xPts</p>
            <p className="tn text-[22px] font-semibold text-text">
              {fmtNum(week.expected_pts)}
            </p>
            <div className="mt-2 flex flex-col gap-0.5">
              {week.buys.map((m) => (
                <MoveLine key={`in-${m.code}`} move={m} side="in" />
              ))}
              {week.sells.map((m) => (
                <MoveLine key={`out-${m.code}`} move={m} side="out" />
              ))}
              {week.buys.length === 0 && week.sells.length === 0 && (
                <p className="text-text-muted">No moves.</p>
              )}
            </div>
            {week.hits > 0 && (
              <p className="mt-2">
                <Chip tone="down">-{week.hit_cost}</Chip>
              </p>
            )}
            <p data-testid={`plan-captain-${week.gw}`}
               className="mt-2 text-text-muted">
              {week.captain ? `C ${week.captain.name}` : '—'}
              {week.vice ? ` · V ${week.vice.name}` : ''}
            </p>
            {(() => {
              // The teams this card already names — captain, vice, buys,
              // sells — deduplicated, in that order. Not the eleven: a 220px
              // card cannot carry eleven chips, and a strip of eleven
              // opponents is a fixture ticker, which is one tab away and
              // better at being one.
              if (!cells || !teamByCode) return null
              const named = [week.captain, week.vice, ...week.buys,
                ...week.sells]
              const seen = new Set<number>()
              const chips = []
              for (const move of named) {
                if (!move) continue
                const teamCode = teamByCode.get(move.code)
                if (teamCode === undefined || seen.has(teamCode)) continue
                seen.add(teamCode)
                const cell = cells.get(`${teamCode}:${week.gw}`)
                // Absent, not guessed (spec D6): no team, no cell, no chip.
                if (!cell) continue
                // The wrapper carries the test id, the tone and the title;
                // `Chip` is a closed primitive that draws the tint (rule 1).
                const tone = difficultyTone(cell.difficulty)
                chips.push(
                  <span
                    key={teamCode}
                    data-testid={`gw-fixture-${teamCode}-${week.gw}`}
                    data-tone={tone}
                    title={`${move.name} — ${cell.home ? 'vs' : 'at'} `
                      + `${cell.opponent} (GW${week.gw}), difficulty `
                      + `${cell.difficulty}`}
                  >
                    <Chip tone={tone}>
                      {`${cell.opponent} (${cell.home ? 'H' : 'A'})`}
                    </Chip>
                  </span>,
                )
              }
              if (chips.length === 0) return null
              return (
                <div data-testid={`gw-strip-${week.gw}`}
                     className="mt-2 flex flex-wrap gap-1">
                  {chips}
                </div>
              )
            })()}
          </Card>
        </div>
      ))}
    </div>
  )
}
