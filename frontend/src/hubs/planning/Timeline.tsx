import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Badge, Card, EmptyState, Loading, PosBadge, difficultyBackground, fmtNum,
} from '../../kit'
import type { PlanMove, PlanTimeline, TickerData } from '../../types'

/** The ticker's own cell shape. Declared locally rather than exported from
 *  `types.ts`, which would move `types.test.ts`'s lockstep pin for a type the
 *  server never sends by that name. */
type TickerCell = TickerData['teams'][number]['cells'][number]

function MoveLine({ move, side }: { move: PlanMove; side: 'in' | 'out' }) {
  return (
    <p className={`flex items-center gap-1 ${side === 'in'
      ? 'text-sage' : 'text-rust'}`}>
      {/* The arrow carries the verdict; the dot carries the identity. */}
      <span aria-hidden>{side === 'in' ? '↑' : '↓'}</span>
      <PosBadge pos={move.position} variant="dot" />
      {move.name}
      {move.price !== null && (
        <span className="num ml-1 text-text-faint">{fmtNum(move.price)}</span>
      )}
    </p>
  )
}

export default function Timeline(
  { gw, teamByCode }: { gw: number; teamByCode?: Map<number, number> },
) {
  const [data, setData] = useState<PlanTimeline | null>(null)
  const [missing, setMissing] = useState(false)
  // The ticker's own cells, indexed by `${teamCode}:${gw}`. Null while it
  // loads and after any failure — the timeline is the feature and the tint is
  // a decoration on it, so a decoration that cannot load costs nothing else.
  const [cells, setCells] = useState<Map<string, TickerCell> | null>(null)

  useEffect(() => {
    setMissing(false)
    apiGet<PlanTimeline>(`/api/plan/${gw}`).then(setData)
      .catch(() => setMissing(true))
  }, [gw])

  // Exactly the window the plan covers, asked for after the plan lands.
  useEffect(() => {
    if (data === null || data.weeks.length === 0) return
    let live = true
    apiGet<TickerData>(`/api/fixtures/ticker?weeks=${data.weeks.length}`)
      .then((body) => {
        if (!live) return
        const map = new Map<string, TickerCell>()
        for (const team of body.teams) {
          for (const cell of team.cells) map.set(`${team.code}:${cell.gw}`, cell)
        }
        setCells(map)
      })
      .catch(() => { if (live) setCells(null) })
    return () => { live = false }
  }, [data])

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
  if (!data) return <Loading />
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
      {data.weeks.map((week) => (
        <div key={week.gw} data-testid={`plan-week-${week.gw}`}
             className="min-w-[220px] flex-1">
          <Card
            title={`GW${week.gw}`}
            action={week.chip ? <Badge variant="info">{week.chip}</Badge> : null}
          >
            <p className="label">xPts</p>
            <p className="num text-xl text-text">
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
                <Badge variant="negative">-{week.hit_cost}</Badge>
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
                chips.push(
                  <span
                    key={teamCode}
                    data-testid={`gw-fixture-${teamCode}-${week.gw}`}
                    className="rounded px-1 text-[10px] text-text"
                    style={{ background: difficultyBackground(cell.difficulty) }}
                    title={`${move.name} — ${cell.home ? 'vs' : 'at'} `
                      + `${cell.opponent} (GW${week.gw}), difficulty `
                      + `${cell.difficulty}`}
                  >
                    {`${cell.opponent} (${cell.home ? 'H' : 'A'})`}
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
