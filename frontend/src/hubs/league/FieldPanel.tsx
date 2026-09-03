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
        // A null with no reason beside it is the one state this panel must
        // never render as a blank: the reader cannot tell an absent
        // measurement from an absent panel.
        <p className="text-text-muted">{field.waiting_for ?? 'not computed'}</p>
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
          {/* Field EO only counts players a sampled entry actually started,
              so a real differential is simply missing from the table. He is
              simulated as owned by nobody — which is what his absence means —
              rather than dropped from my week, and the reader is told how
              much of his squad the sample cannot speak to. */}
          {field.unsampled_picks > 0 && (
            <p className="mt-1 text-text-muted">
              {field.unsampled_picks} of your players{' '}
              {field.unsampled_picks === 1 ? 'was' : 'were'} in nobody&rsquo;s
              sampled squad, so the field is simulated as not owning{' '}
              {field.unsampled_picks === 1 ? 'him' : 'them'} at all.
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
                // The sign carries the whole meaning — overall rank counts
                // down, so a negative slope is points buying places — and
                // rendering the magnitude alone read a squad that was sliding
                // as one that was climbing.
                <span className="num text-text">
                  {Math.abs(Math.round(field.rank_slope)).toLocaleString()}{' '}
                  places per point{' '}
                  {field.rank_slope < 0 ? 'better' : 'worse'}, over{' '}
                  {field.rank_slope_rows} graded gameweeks
                </span>
              )}
          </dd>
        </div>
      </dl>

      {/* A probability with no population, no n and no seed beside it is a
          decoration; and the portfolio sentence is here because the field is
          not a set of legal squads and a reader who assumed it was would
          over-read every number above. The gameweek is named because it is
          *not* the one at the top of the card: a field sample can only be
          banked for the last scored week, and §3.3 extrapolates it one
          gameweek forward. The draw count is here for the same reason as n —
          which three hundred managers were drawn is noise in its own right,
          and it was the larger term. Withheld entirely when there is no
          probability, because provenance with nothing to attach to is
          furniture. */}
      {field.p_green != null && (
        <p className="mt-3 text-text-muted">
          {field.managers} simulated managers drawn from {field.eo_source} EO
          {field.eo_gw != null
            ? ` — EO drawn from GW ${field.eo_gw}'s sample`
            : ''}. n={field.n} × {field.field_draws} field draws, seed{' '}
          {field.seed}. The field is an ownership portfolio, not a legal
          squad.
        </p>
      )}
    </Card>
  )
}
