import { usePageData } from '../../api/pageData'
import {
  Callout, Card, Chip, EmptyState, Loading, TABLE_CLASS, THEAD_CLASS,
  TR_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
import type { ChipPlan, FixtureOutlook } from '../../types'
import { LABELS } from './chips'

/**
 * Cut from `ChipsTab.tsx` in v18f §2.1 — the tab was over five hundred lines
 * and this panel is one of its three segments, with two fetches of its own
 * and two helpers nothing else uses.
 */

/** The season ahead: what each chip's bar does over the coming weeks, and
 *  which weeks are doubles or blanks (v10b §F2c).
 *
 *  Two independent fetches, on purpose. `/api/chips/plan` re-solves a handful
 *  of small MILPs and `/api/fixtures/outlook` reads a parquet; they fail for
 *  unrelated reasons, and a tab that blanks both because one is down is worse
 *  than a tab that shows the half it has.
 *
 *  It reports and does not instruct. θ is the bar the advise run itself
 *  solved against — the same expression, from the same asset — so this panel
 *  says where the season stands, not what to do about it.
 */
export default function ChipOutlook() {
  // Two hooks and not one `Loaded`, for the reason the docblock gives: each
  // half keeps its own error slot beside the half that did load, which is
  // what a shared loader would take away (v18e §2.3).
  const planPage = usePageData<ChipPlan>('/api/chips/plan')
  const outlookPage = usePageData<FixtureOutlook>('/api/fixtures/outlook')
  const plan = planPage.data
  const outlook = outlookPage.data
  const planError = planPage.error
  const outlookError = outlookPage.error

  if (!plan && !outlook && !planError && !outlookError) return <Loading />

  const weeks = outlook?.weeks ?? []
  // The filter is for *display* — which rows are worth a line in the table.
  // Whether there is anything scheduled at all is the server's answer, and
  // the empty-state copy reads it off the served flags rather than
  // re-deriving it here: `has_doubles` is a claim about the served slice, and
  // the rows are only what this slice happens to carry. v9d's `available`,
  // same reasoning.
  //
  // So `has_doubles && interesting.length === 0` renders neither the empty
  // state nor the table. That gap is unreachable in this client: the flags are
  // computed over the same slice the rows come from, and this component sends
  // no `from`, so the slice is the whole published list. If a caller ever does
  // narrow it, the honest render is nothing rather than a contradiction.
  const interesting = weeks.filter(
    (w) => w.doubles.length > 0 || w.blanks.length > 0)
  const nothingScheduled = !outlook?.has_doubles && !outlook?.has_blanks

  return (
    <div data-testid="chip-outlook">
      <Card title="The season ahead" className="mb-4">
        <p className="mb-3 text-text-muted" data-testid="outlook-caveat">
          Planning, not advice: this is where each chip&rsquo;s bar sits over
          the coming weeks and which weeks are unusual. What to play this week
          is This Week&rsquo;s answer.
        </p>
        {planError && <Callout tone="error">{planError}</Callout>}
        {plan?.chips.map((row) => {
          const expiry = row.window?.[1]
          return (
            <div key={row.chip} data-testid={`outlook-chip-${row.chip}`}
                 className="mb-3 border-t border-divider pt-2">
              <div className="flex flex-wrap items-baseline gap-x-3">
                <span className="text-text">{LABELS[row.chip] ?? row.chip}</span>
                <span className="tn text-text-secondary">
                  {`best GW${row.best_gw} · ${fmtNum(row.best_gain, 1)} pts`}
                </span>
                <span className="tn text-text-muted">
                  {`θ ${fmtNum(row.threshold_now ?? null, 1)}`}
                </span>
                {expiry != null && (
                  <span className="text-text-muted">
                    {`expires after GW${expiry}`}
                  </span>
                )}
              </div>
              <ThetaTrack weeks={row.weeks} thetas={row.thetas} />
            </div>
          )
        })}
      </Card>
      <Card title="Doubles and blanks">
        {outlookError && <Callout tone="error">{outlookError}</Callout>}
        {/* Only alongside rows: on a fresh clone the server serves no weeks
            at all, and "club names unavailable" over an empty table is a
            complaint about names nothing was going to print. */}
        {outlook != null && outlook.weeks.length > 0
          && outlook.teams_known === false && (
          <p className="mb-2 text-text-muted"
             data-testid="outlook-teams-unknown">
            Club names unavailable — counts still hold.
          </p>
        )}
        {outlook && nothingScheduled && (
          <EmptyState
            title="Nothing unusual scheduled"
            detail={outlook.note
              ?? 'No doubles or blanks are scheduled yet — rearrangements '
                + 'usually start appearing around the cup rounds.'}
            action="Refresh data"
          />
        )}
        {interesting.length > 0 && (
          <div className="overflow-x-auto">
            <table className={TABLE_CLASS}>
              <thead className={THEAD_CLASS}>
                <tr>
                  <th scope="col" className={thClass()}>GW</th>
                  <th scope="col" className={thClass(true)}>Fixtures</th>
                  <th scope="col" className={thClass()}>Doubles</th>
                  <th scope="col" className={thClass()}>Blanks</th>
                </tr>
              </thead>
              <tbody>
                {interesting.map((w) => (
                  <tr key={w.gw} className={TR_CLASS}
                      data-testid={`outlook-week-${w.gw}`}>
                    <td className={`${tdClass()} tn`}>GW{w.gw}</td>
                    <td className={`${tdClass(true)} text-text-secondary`}>
                      {w.fixtures}
                    </td>
                    {/* Rule 1: an extra fixture is a week going your way and
                        a blank is one going against you. */}
                    <td className={`${tdClass()} text-up`}>
                      {w.doubles.map(teamLabel).join(', ') || '—'}
                    </td>
                    <td className={`${tdClass()} text-down`}>
                      {w.blanks.map(teamLabel).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

/** A club, named if the teams snapshot could be read and numbered if not.
 *  The raw id is shown rather than hidden: a count with an unnameable club in
 *  it is still a true count, and pretending the row is not there is worse. */
function teamLabel(team: { code: number; short_name: string | null }): string {
  return team.short_name ?? `#${team.code}`
}

/** θ per week beside the gain that week offers, aligned by index.
 *
 *  A compact strip rather than a chart: the question is "does any week ahead
 *  clear its bar", which is a row of comparisons, and the weeks are few. */
function ThetaTrack(
  { weeks, thetas }: {
    weeks: Array<{ gw: number; gain: number }>
    thetas: number[]
  },
) {
  if (weeks.length === 0) return null
  return (
    <div className="mt-1 flex flex-wrap gap-2" data-testid="theta-track">
      {weeks.map((w, i) => {
        const theta = thetas[i]
        const over = theta !== undefined && w.gain >= theta
        // Rule 1: clearing the bar is the direction the strip is read for;
        // a week under it is information and stays grey.
        return (
          <Chip key={w.gw}
                tone={over ? 'up' : 'neutral'}
                className="tn"
                title={theta === undefined
                  ? `GW${w.gw}: gain ${w.gain.toFixed(1)}`
                  : `GW${w.gw}: gain ${w.gain.toFixed(1)} against a bar of `
                    + theta.toFixed(1)}>
            {`GW${w.gw} ${w.gain.toFixed(1)}`}
          </Chip>
        )
      })}
    </div>
  )
}
