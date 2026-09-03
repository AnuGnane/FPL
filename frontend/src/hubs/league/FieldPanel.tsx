import { Card } from '../../kit'
import type { FieldRank } from '../../types'

/**
 * v12 W4 §5.3. This gameweek against a synthetic field drawn from EO.
 *
 * Two of the three headline numbers are null today and each says what it is
 * waiting for. They are rendered as rows with their reasons rather than
 * hidden, because a row that vanishes is a question the reader stops asking.
 */
export default function FieldPanel({ field }: { field: FieldRank | null }) {
  if (field == null) return null
  const pct = (v: number) => `${Math.round(v * 100)}%`
  return (
    <Card title="Field" className="mt-4">
      {field.p_green == null ? (
        <p className="text-text-muted">{field.waiting_for}</p>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="num text-2xl text-text">{pct(field.p_green)}</span>
            <span className="text-text-muted">chance of a green arrow</span>
          </div>
          {field.my_ep != null && field.field_median_ep != null && (
            <p className="num mt-1 text-text-muted">
              your week {field.my_ep.toFixed(1)} pts vs the field&rsquo;s
              median {field.field_median_ep.toFixed(1)}
            </p>
          )}
        </>
      )}

      <dl className="mt-3 flex flex-col gap-2">
        <div>
          <dt className="label">Top 10k this week</dt>
          <dd>
            {field.p_top10k == null
              ? (
                <span className="text-text-muted">
                  not computed — waiting for{' '}
                  {field.top10k_waiting_for ?? 'a score threshold'}
                </span>
              )
              : <span className="num text-text">{pct(field.p_top10k)}</span>}
          </dd>
        </div>
        <div>
          <dt className="label">Overall rank response</dt>
          <dd>
            {field.rank_slope == null
              ? (
                <span className="text-text-muted">
                  not computed — waiting for{' '}
                  {field.rank_waiting_for ?? 'graded gameweeks'}
                </span>
              )
              : (
                <span className="num text-text">
                  {Math.abs(Math.round(field.rank_slope)).toLocaleString()}{' '}
                  places per point, over {field.rank_slope_rows} graded
                  gameweeks
                </span>
              )}
          </dd>
        </div>
      </dl>

      {/* A probability with no population, no n and no seed beside it is a
          decoration; and the portfolio sentence is here because the field is
          not a set of legal squads and a reader who assumed it was would
          over-read every number above. */}
      <p className="mt-3 text-text-muted">
        {field.managers} simulated managers drawn from {field.eo_source} EO,
        n={field.n}, seed {field.seed}. The field is an ownership portfolio,
        not a legal squad.
      </p>
    </Card>
  )
}
