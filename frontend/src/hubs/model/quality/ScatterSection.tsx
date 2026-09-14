import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { usePageData } from '../../../api/pageData'
import { Card, EmptyState, Loaded, SERIES_COLOURS } from '../../../kit'
import type { ReviewData } from '../../../types'

/**
 * Cut from `QualityTab.tsx` in v18f §2.1 — the tab was a thousand lines with
 * a natural seam at its self-fetching sections. This one reads `/api/review`
 * itself, so it moved with the two helpers only it uses.
 */

/**
 * Your points against the model's, one point per graded gameweek.
 *
 * Both axes come off `reports/decision_ledger.json`, and that is the whole
 * design. The card used to plot `advise.raw_xi_pts` — an untilted sum of EP
 * over the eleven the advice run picked, before captaincy and before hits —
 * against the entry's official net score off `meta.py`. Two different
 * quantities on two axes with a y = x line drawn through them: every point
 * sat above the line, and the "gap" the reader took away was a unit mismatch
 * rather than a miss.
 *
 * The ledger's two numbers are commensurable by construction. `review.grade_gw`
 * hand-scores both squads against the same actuals frame: `my_points` is my
 * eleven with my armband, net of hits, and `model_points` is that same squad
 * with every *comparable* lane replaced by the model's. So the diagonal is a
 * real reference — above it my week beat the model's advice, below it the
 * advice would have beaten me — and the vertical distance is in points.
 *
 * Its own fetch, on PensSection's pattern: /api/review is a different
 * artifact with its own "nothing banked yet" state, and folding it into
 * /api/quality would let one missing file blank the other's card.
 *
 * A `no_advice` row carries `model_points: null` — the advice for that week
 * has been pruned, so there is no model squad to score. Those rows are
 * dropped rather than plotted at zero, and the card says how many weeks it is
 * actually drawing. Under two of them there is no scatter to draw and the
 * card says *that* instead of vanishing: an absent card reads as a missing
 * feature, where the truth is a season that has not been graded yet.
 */
function scatterPoints(gws: ReviewData['gws']) {
  return gws
    .filter((r) => r.model_points !== null && r.my_points !== null)
    .map((r) => ({ gw: r.gw, model: r.model_points as number,
                   mine: r.my_points as number }))
}

export default function ScatterSection() {
  // v18e §2.3, ruling 7: `.catch(() => setGws([]))` drew "No graded gameweek
  // yet" over a review the server could not hand over. The 404 and the 422
  // keep that sentence — the artifact really is not written — and every
  // other status is the kit's error callout with its retry. The entry is
  // shared with the Review and Season tabs, so the walk asks once.
  const page = usePageData<ReviewData>('/api/review')

  return (
    <Loaded
      page={page}
      isEmpty={(body) => scatterPoints(body.gws).length === 0}
      empty={(
        <Card title="Your points against the model’s" className="mt-4">
          <EmptyState
            title="No graded gameweek yet"
            detail="This compares what you scored against what the model's own
                    squad would have scored, for every gameweek FPL has
                    finalised. None has been graded yet."
            action="gaffer review"
          />
        </Card>
      )}
    >
      {(body) => <ScatterBody points={scatterPoints(body.gws)} />}
    </Loaded>
  )
}

function ScatterBody({ points }: { points: ReturnType<typeof scatterPoints> }) {
  // One point is not an empty state, it is an *insufficient* one, and the
  // sentence is telling the reader something true about statistics.
  if (points.length < 2) {
    return (
      <Card title="Your points against the model’s" className="mt-4">
        <p className="text-text-muted">
          1 graded gameweek so far. One point is an anecdote, not a scatter;
          the chart appears from the second graded week.
        </p>
      </Card>
    )
  }

  const top = Math.ceil(Math.max(
    ...points.map((p) => Math.max(p.model, p.mine)), 10) / 10) * 10

  return (
    <Card title="Your points against the model’s" className="mt-4">
      <p className="mb-3 text-text-muted">
        {'Each point is one graded gameweek. Both numbers are whole squads '
          + 'scored off the same results — yours net of hits, against yours '
          + 'with every comparable decision taken from the model instead. '
          + `${points.length} graded gameweeks. Above the dashed line your `
          + 'week beat the advice; below it the advice would have beaten you.'}
      </p>
      <div aria-label="your points against the model’s">
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--color-divider)" />
            <XAxis type="number" dataKey="model" name="model"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <YAxis type="number" dataKey="mine" name="yours"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <ZAxis range={[60, 60]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              contentStyle={{ background: 'var(--color-raised)',
                              border: '1px solid var(--color-border)' }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: top, y: top }]}
                           stroke="var(--color-text-muted)"
                           strokeDasharray="4 4" />
            <Scatter data={points} fill={SERIES_COLOURS[0]} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
