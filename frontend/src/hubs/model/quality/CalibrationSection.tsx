import { usePageData } from '../../../api/pageData'
import {
  Callout, Card, EmptyState, TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass,
  thClass,
} from '../../../kit'
import type { CalibrationData, CalibrationHead } from '../../../types'
import { Reliability } from './shared'

/**
 * Cut from `QualityTab.tsx` in v18f §2.1 — the tab was a thousand lines with
 * a natural seam at its self-fetching sections. This one reads
 * `/api/model/calibration` itself, so it moved with the two helpers only it
 * uses; `Reliability` is shared with the tab's own holdout card and lives in
 * `./shared`.
 */

// The four heads the banked components carry, in payload order. p_start is
// deliberately not here: the minutes trichotomy is never written to
// components_gw{N}.parquet, so the report omits it *with its reason* and the
// footer prints that reason. A reader who could not see the omission would
// conclude the trichotomy is calibrated.
// Exported since v11: the season dashboard draws the trend of the same four
// heads and must handle the same omissions. Two fetch-and-format
// implementations of one artifact is what would rot.
export const CALIBRATION_HEADS: Array<[string, string]> = [
  ['p_play', 'P(plays)'],
  ['p60', 'P(60+)'],
  ['p_cs', 'P(clean sheet)'],
  ['p_haul', 'P(2+ returns)'],
]

function brierCell(head: CalibrationHead | undefined) {
  // A blank cell reads as "perfect" at a glance, which is the worst possible
  // default for a calibration table, so an ungraded head says so in words.
  if (!head) return <span className="text-text-faint">—</span>
  if (head.status !== 'scored' || head.brier === null) {
    return (
      <span className="text-text-faint">not enough data ({head.n})</span>
    )
  }
  return <>{head.brier.toFixed(4)} <span className="text-text-faint">
    ({head.n})</span></>
}

/**
 * Per-gameweek Brier for the probabilities the weekly run actually served.
 *
 * Its own fetch, like every other section here: the report is a separate key
 * in the evaluation artifact with its own "nobody has run it" state, and a
 * failed fetch must not take the tab's other numbers down.
 *
 * Titled "Calibration by gameweek" because this tab already has a card titled
 * "Calibration" — the last-10-slot holdout curves — and two cards with one
 * name showing different things is worse than either alone.
 */
export default function CalibrationSection() {
  // v18e §2.3: its own read still, where it lives — but through the one
  // entry `SeasonTab`'s trend card shares, so the two views of this artifact
  // are one request. It synthesised no empty body, so ruling 7 leaves its
  // branches where they were.
  const page = usePageData<CalibrationData>('/api/model/calibration')

  if (page.error !== null) {
    return (
      <Card title="Calibration by gameweek" className="mt-4">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  const data = page.data
  if (!data) return null

  if (!data.available || data.gameweeks.length === 0) {
    return (
      <Card title="Calibration by gameweek" className="mt-4">
        <EmptyState
          // Distinct from the scatter card's "No graded gameweek yet" below:
          // two empty states with one sentence on one tab tell a reader
          // nothing about which artifact is missing.
          title="No calibration report yet"
          // The server's own sentence, verbatim: the report is CLI-only,
          // because JOB_KINDS maps a kind to a zero-argument callable and
          // there is no flag a button could pass.
          detail={data.note ?? 'Nothing graded yet.'}
          action="gaffer evaluate --calibration"
        />
      </Card>
    )
  }

  return (
    <Card title="Calibration by gameweek" className="mt-4">
      <p className="mb-3 text-text-muted">
        Brier score per head for the probabilities the weekly run actually
        served — read back off the banked components, never refitted. Lower is
        better.
      </p>
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>GW</th>
            {CALIBRATION_HEADS.map(([key, label]) => (
              <th scope="col" key={key} className={thClass(true)}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.gameweeks.map((row) => (
            <tr key={row.gw} className={TR_CLASS}>
              <th scope="row" className={thClass()}>{`GW${row.gw}`}</th>
              {CALIBRATION_HEADS.map(([key]) => (
                <td key={key} className={tdClass(true)}>
                  {/* A head with no per-gameweek column says so once, in the
                      footer, rather than printing a week's worth of "not
                      enough data" that reads as a fault in the model. */}
                  {key in data.per_gw_omitted
                    ? <span className="text-text-faint" title={
                        data.per_gw_omitted[key]}>cumulative only</span>
                    : brierCell(row.heads[key])}
                </td>
              ))}
            </tr>
          ))}
          {/* The cumulative row is what a model cycle is chosen on, so it is
              separated rather than sorted in among the weeks. */}
          <tr className={TR_CLASS}>
            <th scope="row" className={thClass()}>All</th>
            {CALIBRATION_HEADS.map(([key]) => (
              <td key={key} className={tdClass(true)}>
                {brierCell(data.cumulative[key])}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      {CALIBRATION_HEADS.map(([key, label]) => {
        const head = data.cumulative[key]
        return head && head.status === 'scored'
          ? (
            <Reliability
              key={key}
              label={label}
              head={{ log_loss: head.log_loss, reliability: head.reliability }}
            />
            )
          : null
      })}
      <div className="mt-3 text-text-faint">
        {Object.entries(data.omitted).map(([head, why]) => (
          <p key={head}>{`Omitted: ${head} — ${why}.`}</p>
        ))}
        {Object.entries(data.per_gw_omitted).map(([head, why]) => (
          <p key={head}>{`Per gameweek: ${head} — ${why}.`}</p>
        ))}
        {data.excluded.map((row) => (
          <p key={row.gw}>{`Excluded: GW${row.gw} — ${row.reason}.`}</p>
        ))}
        {data.missing.length > 0 && (
          <p>
            {`No banked components: ${data.missing
              .map((gw) => `GW${gw}`).join(', ')}.`}
          </p>
        )}
      </div>
    </Card>
  )
}
