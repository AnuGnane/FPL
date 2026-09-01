import { useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import {
  Card, EmptyState, Loading, TONE_CLASS, fmtDelta, toneOf,
} from '../../kit'
import type { ReviewData, ReviewLaneName } from '../../types'

/**
 * v11 §F3 — the season, as it fills.
 *
 * `season_summary` is already served on `GET /api/review`, so there is no new
 * endpoint here and none was added: the two quantities this view needed —
 * per-lane win rates and the overall rank — went onto that payload, because
 * the graded-counter honesty rule lives in `season_summary` and a win rate
 * counted in this component would be a second implementation of it.
 *
 * **It is built empty on purpose.** Today's ledger is one row with four
 * ungraded lanes, no accuracy and no rank, so every honesty rule below fires
 * on the real data on day one.
 */

const LANE_ORDER: ReviewLaneName[] = ['transfers', 'captaincy', 'bench', 'chip']

const LANE_TITLE: Record<ReviewLaneName, string> = {
  transfers: 'Transfers',
  captaincy: 'Captaincy',
  bench: 'Bench order',
  chip: 'Chip',
}

// The wording `ReviewTab` already uses for exactly this case. The two views
// must agree word for word or the reader will think they mean different
// things.
const NEVER_GRADED = 'never graded'

const GATE = 'The first grades land when FPL marks GW2 data_checked — the '
  + 'Tuesday review job banks them automatically.'

export default function SeasonTab() {
  const [data, setData] = useState<ReviewData | null>(null)

  useEffect(() => {
    // `/api/review` never errors (routers/review.py); the catch is for a clone
    // whose server is not up, which reads the same to the page.
    apiGet<ReviewData>('/api/review').then(setData)
      .catch(() => setData({ gws: [], summary: null }))
  }, [])

  if (!data) return <Loading />

  const summary = data.summary
  const anyGraded = summary !== null
    && LANE_ORDER.some((name) => (summary.lanes[name]?.graded ?? 0) > 0)

  if (!anyGraded) {
    // The detail names a thing that happens by itself; the action beside it is
    // the manual path, and it is the command `ReviewTab` already prints for
    // exactly this case rather than a second wording of it.
    return (
      <EmptyState
        title="Nothing graded yet"
        detail={`${GATE} The hub's Review last week button runs the same `
          + 'thing.'}
        action="gaffer review"
      />
    )
  }

  const accuracy = summary!.accuracy
  // A null rank is a gap, never a zero and never a line through it —
  // `connectNulls` is false by default and must stay that way.
  const ranks = [...data.gws]
    .sort((a, b) => a.gw - b.gw)
    .map((row) => ({ gw: row.gw, overall_rank: row.overall_rank }))
  const ranked = ranks.filter((row) => row.overall_rank !== null).length
  // A gameweek whose history was never banked is a gap in the series, not a
  // zero: a season of unbanked histories sums to a season of empty benches,
  // which is a season nobody had.
  let running = 0
  const bench = [...data.gws]
    .sort((a, b) => a.gw - b.gw)
    .map((row) => {
      if (row.points_on_bench === null) return { gw: row.gw, bench: null }
      running += row.points_on_bench
      return { gw: row.gw, bench: running }
    })

  return (
    <div>
      <Card title="Decision record" className="mb-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {LANE_ORDER.map((name) => {
            const cell = summary!.lanes[name]
            const graded = cell?.graded ?? 0
            return (
              <div key={name} data-testid={`season-lane-${name}`}
                   className="rounded-card border border-border bg-card
                              px-4 py-3">
                <p className="label">{LANE_TITLE[name]}</p>
                <p className={`num mt-1 text-2xl
                               ${TONE_CLASS[toneOf(cell?.pts ?? 0)]}`}>
                  {graded > 0 ? fmtDelta(cell.pts, 0) : '—'}
                </p>
                <p className="num mt-1 text-xs text-text-faint">
                  {/* The denominator is `graded` and not `wins + losses`: a
                      zero delta is a week I did what the model did, and
                      dividing it away would turn agreement into judgment. */}
                  {graded > 0
                    ? `${cell.wins}/${graded} won · ${cell.losses} lost`
                    : NEVER_GRADED}
                </p>
              </div>
            )
          })}
        </div>
        <p className="mt-3 text-sm text-text-muted">
          {`Bench points this season: ${summary!.points_on_bench} over `
           + `${summary!.points_on_bench_gws} GW. Selection left `
           + `${summary!.hindsight_gap} on the table over `
           + `${summary!.hindsight_gap_gws} GW.`}
        </p>
      </Card>

      <Card title="Points left on the bench" className="mb-4">
        {bench.length === 0 ? (
          <p className="text-text-muted">No gameweek carries a bench total.</p>
        ) : (
          <div aria-label="Cumulative bench points">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={bench}>
                <CartesianGrid stroke="var(--color-divider)" vertical={false} />
                <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
                <YAxis stroke="var(--color-text-muted)" />
                <Tooltip contentStyle={{ background: 'var(--color-card)',
                                         border: '1px solid var(--color-border)' }} />
                <Line type="monotone" dataKey="bench" dot={false}
                      strokeWidth={2} stroke="var(--color-rust)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <p className="mt-1 text-xs text-text-faint">
          {`Cumulative, over the ${summary!.points_on_bench_gws} gameweek(s) `
           + 'whose history was banked. A gameweek with none is a gap, not a '
           + 'zero.'}
        </p>
      </Card>

      <Card title="Accuracy" className="mb-4">
        {accuracy.length === 0 ? (
          <p data-testid="accuracy-empty" className="text-text-muted">
            No gameweek carries an accuracy figure yet.
          </p>
        ) : (
          <div aria-label="Accuracy by gameweek">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={accuracy}>
                <CartesianGrid stroke="var(--color-divider)" vertical={false} />
                <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
                <YAxis stroke="var(--color-text-muted)" />
                <Tooltip contentStyle={{ background: 'var(--color-card)',
                                         border: '1px solid var(--color-border)' }} />
                <Line type="monotone" dataKey="accuracy" dot={false}
                      strokeWidth={2} stroke="var(--color-info)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <Card title="Overall rank" className="mb-4">
        {ranked === 0 ? (
          <p data-testid="rank-empty" className="text-text-muted">
            No graded gameweek carries a rank yet. Grades are banked and never
            re-derived, so the trajectory starts from the next graded week.
          </p>
        ) : (
          <div aria-label="Overall rank by gameweek">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={ranks}>
                <CartesianGrid stroke="var(--color-divider)" vertical={false} />
                <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
                {/* Reversed: a lower rank is better, and a line that rises
                    when the season goes badly is a chart lying with its
                    shape. */}
                <YAxis reversed stroke="var(--color-text-muted)"
                       domain={['dataMin', 'dataMax']} />
                <Tooltip contentStyle={{ background: 'var(--color-card)',
                                         border: '1px solid var(--color-border)' }} />
                {/* `connectNulls` is false by default and stays that way: a
                    straight line through a missing rank is the most confident
                    lie this dashboard could tell. */}
                <Line type="monotone" dataKey="overall_rank" dot={false}
                      strokeWidth={2} stroke="var(--color-sage)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        <p className="mt-1 text-xs text-text-faint">
          {`${ranked} of ${data.gws.length} graded gameweek(s) carry a rank. `
           + 'Lower is better, so the axis runs downward.'}
        </p>
      </Card>
    </div>
  )
}
