import {
  Bar, TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
} from '../../../kit'
import type { FlagLatencyData } from '../../../types'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

// The bar is scaled to the largest bucket in *this* histogram, the way
// PairedBar scales to its own row: lead times are counts and a shared axis
// across a fortnight of snapshots would draw every early bucket as nothing.
function LeadBar({ started, missed, top }:
                 { started: number; missed: number; top: number }) {
  return (
    // Both grey, like the news pair above: started and did not start are
    // two counts of one histogram, not a direction the reader is on.
    <span className="inline-flex flex-col gap-0.5 align-middle">
      <Bar fraction={started / top} width={128} testId="lead-started"
           aria-label={`started ${started}`} />
      <Bar fraction={missed / top} width={128} testId="lead-missed"
           aria-label={`did not start ${missed}`} />
    </span>
  )
}

export default function FlagLatencySection(
  { data }: { data: FlagLatencyData },
) {
  // Two gates, one empty state. `available` is the server's fourteen-day
  // rule; `rows === 0` is an open gate over a fortnight in which nothing
  // moved. Either way the tables would be a row of zeroes that reads as a
  // measurement, and spec §1 wants a sentence instead — the server's own
  // where there is one, so the CLI and the page cannot drift apart on it.
  if (!data.available || data.rows === 0) {
    return (
      <p data-testid="flag-latency-empty" className="text-text-muted">
        {data.note
          ?? `No status changed before a deadline in ${data.snap_dates} `
             + 'snapshot days of graded gameweeks.'}
      </p>
    )
  }
  const top = Math.max(
    1, ...data.histogram.map((b) => Math.max(b.started, b.missed)))
  return (
    <>
      <p className="mb-2 text-text-secondary">
        {data.rows}
        {' status changes over '}
        {data.snap_dates}
        {' snapshot days, in gameweeks '}
        {data.checked_covered_gws.join(', ')}
        {'.'}
      </p>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Warning</th>
              <th scope="col" className={thClass(true)}>Started</th>
              <th scope="col" className={thClass(true)}>Did not</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.histogram.map((b) => (
              <tr key={b.bucket} data-testid={`lead-bucket-${b.bucket}`}
                  className={TR_CLASS}>
                <td className={`${tdClass()} tn text-text`}>{b.bucket}</td>
                <td className={`${tdClass(true)} text-text`}>
                  {b.started}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {b.missed}
                </td>
                <td className={tdClass()}>
                  <LeadBar started={b.started} missed={b.missed} top={top} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.late_flags.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <p className="label mb-1">
            Latest flags whose final status disagreed with the start
          </p>
          <table className={TABLE_CLASS}>
            <tbody>
              {data.late_flags.map((f) => (
                <tr key={`${f.gw}-${f.code}`}
                    data-testid={`late-flag-${f.gw}-${f.code}`}
                    className={TR_CLASS}>
                  <td className={`${tdClass()} tn text-text`}>{`GW${f.gw}`}</td>
                  <td className={`${tdClass()} tn text-text-secondary`}>
                    {`code ${f.code}`}
                  </td>
                  <td className={tdClass(true)}>
                    {`${fmtNum(f.lead_days, 0)}d`}
                  </td>
                  <td className={`${tdClass()} text-text-muted`}>
                    {`${f.from_status} → ${f.final_status}`}
                  </td>
                  <td className={tdClass(true)}>
                    {f.started ? 'started' : 'did not start'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
