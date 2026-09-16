import {
  TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
} from '../../../kit'
import type { PresserGradesData } from '../../../types'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

export default function PresserGradesSection(
  { data }: { data: PresserGradesData },
) {
  if (!data.available || data.rows === 0) {
    return (
      <p data-testid="presser-grades-empty" className="mt-3 text-text-muted">
        {data.note ?? 'No verdict has been graded yet.'}
      </p>
    )
  }
  const conf = new Map(data.confusion.map((c) => [c.verdict, c]))
  return (
    <div className="mt-4">
      <p className="label mb-1">Presser verdicts</p>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Verdict</th>
              <th scope="col" className={thClass(true)}>Graded</th>
              <th scope="col" className={thClass(true)}>Started</th>
              <th scope="col" className={thClass(true)}>Absent</th>
              <th scope="col" className={thClass(true)}>Precision</th>
              <th scope="col" className={thClass(true)}>Recall</th>
            </tr>
          </thead>
          <tbody>
            {data.per_class.map((row) => (
              <tr key={row.verdict} data-testid={`verdict-${row.verdict}`}
                  className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{row.verdict}</td>
                <td className={tdClass(true)}>{row.n}</td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {conf.get(row.verdict)?.started ?? 0}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {conf.get(row.verdict)?.not_started ?? 0}
                </td>
                {/* A precision is a measurement, not a direction (rule 1). */}
                <td className={`${tdClass(true)} text-text`}>
                  {fmtNum(row.precision, 2)}
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {/* The denominator is the gameweek's absences. With none,
                      the payload stores 0 and this prints a dash: 0.00 beside
                      a class that found none of nothing reads as a class that
                      missed everything. */}
                  {data.absent_rows > 0 ? fmtNum(row.recall, 2) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p data-testid="presser-recall-note"
         className="mt-1 text-xs text-text-faint">
        {'Precision is P(did not start | verdict). Recall is over '}
        {data.recall_population}
        {` — ${data.absent_rows} absences among ${data.rows} graded `}
        {'verdicts, not every absence in the gameweek.'}
      </p>
    </div>
  )
}
