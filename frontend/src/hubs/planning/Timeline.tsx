import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Badge, Card, EmptyState, Loading, PosBadge, fmtNum } from '../../kit'
import type { PlanMove, PlanTimeline } from '../../types'

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

export default function Timeline({ gw }: { gw: number }) {
  const [data, setData] = useState<PlanTimeline | null>(null)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    setMissing(false)
    apiGet<PlanTimeline>(`/api/plan/${gw}`).then(setData)
      .catch(() => setMissing(true))
  }, [gw])

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
          </Card>
        </div>
      ))}
    </div>
  )
}
