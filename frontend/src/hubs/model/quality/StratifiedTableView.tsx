import {
  TABLE_CLASS, THEAD_CLASS, TR_CLASS, tdClass, thClass,
} from '../../../kit'
import type { StratifiedTable } from '../../../types'

// Cut from `QualityTab.tsx` in v19h §2.1: the tab was 546 lines of
// hand tables, and a section nobody can find is a section nobody checks.
// Markup and class strings are the v18f ones, byte for byte — the Model
// screenshot pair is the proof.

// Categories are OpenFPL's, defined on actual points, so the labels have to
// stay recognisable next to their published table.
const CATEGORIES: Array<[string, string]> = [
  ['zeros', 'Zeros'],
  ['blanks', 'Blanks'],
  ['tickers', 'Tickers'],
  ['haulers', 'Haulers'],
  ['all', 'All'],
]

export default function StratifiedTableView(
  { columns }: { columns: Array<[string, StratifiedTable]> },
) {
  return (
    <div className="overflow-x-auto">
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>Category</th>
            {columns.map(([name]) => (
              <th scope="col" key={name} colSpan={2}
                  className={`${thClass()} border-l border-divider
                              text-center`}>
                {name}
              </th>
            ))}
          </tr>
          <tr>
            <th scope="col" />
            {columns.map(([name]) => [
              <th scope="col" key={`${name}-rmse`}
                  className={`${thClass(true)} border-l border-divider`}>
                RMSE
              </th>,
              <th scope="col" key={`${name}-mae`} className={thClass(true)}>
                MAE
              </th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {CATEGORIES.map(([key, label]) => (
            <tr key={key} className={TR_CLASS}>
              <td className={`${tdClass()} text-text`}>{label}</td>
              {columns.map(([name, table]) => [
                <td key={`${name}-${key}-rmse`}
                    className={`${tdClass(true)} border-l border-divider
                                text-text`}>
                  {table[key] === undefined ? '—' : table[key].rmse}
                </td>,
                <td key={`${name}-${key}-mae`}
                    className={`${tdClass(true)} text-text-secondary`}>
                  {table[key] === undefined ? '—' : table[key].mae}
                </td>,
              ])}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
