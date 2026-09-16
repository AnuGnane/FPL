import {
  Card, TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass, thClass,
} from '../../../kit'
import type { DecompositionData } from '../../../types'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

const CELLS: Array<[string, string]> = [
  ['model_h1', 'Model, 1-week'],
  ['model_h3', 'Model, 3-week'],
  ['oracle_h1', 'Oracle, 1-week'],
  ['oracle_h3', 'Oracle, 3-week'],
]

export default function DecompositionSection(
  { decomposition }: { decomposition: DecompositionData },
) {
  return (
    <Card
      title={`Decomposition — ${decomposition.season} from GW`
        + ` ${decomposition.start_gw}`}
      className="mb-4"
    >
      <div className="overflow-x-auto">
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>Run</th>
            <th scope="col" className={thClass(true)}>Total</th>
            <th scope="col" className={thClass(true)}>Per GW</th>
            <th scope="col" className={thClass(true)}>Hits</th>
          </tr>
        </thead>
        <tbody>
          {CELLS.map(([key, label]) => {
            const cell = decomposition.cells[key]
            return cell === undefined ? null : (
              <tr key={key} className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{label}</td>
                <td className={`${tdClass(true)} text-text`}>
                  {cell.total}
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {cell.per_gw}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {cell.hits}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
      <div className="overflow-x-auto">
      <table className={`mt-4 ${TABLE_CLASS}`}>
        <tbody>
          {([
            ['Forecast gap (3-week)', decomposition.forecast_gap_h3,
             'points better forecasting could still win'],
            ['Planning ceiling', decomposition.planning_ceiling,
             'the most multi-week planning can ever be worth'],
          ] as const).map(([label, value, note]) => (
            <tr key={label} className={TR_CLASS}>
              <td className={`${tdClass()} text-text`}>{label}</td>
              <td className={`${tdClass(true)} text-text`}>{value}</td>
              <td className={`${tdClass()} text-text-muted`}>{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Card>
  )
}
