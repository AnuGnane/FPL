import type { ReactNode } from 'react'

/**
 * A table read down instead of across (v19c §2.1).
 *
 * A phone cannot show eight columns, and the app's answer until now was an
 * `overflow-x-auto` scroller per table: every number was there, and none of
 * them was beside its own heading. This is the ledger's own answer instead —
 * a list of rows, each a heading line and its label/value pairs, hairlines
 * between them and no card — so the four tables a Thursday reader actually
 * meets can render down the page while the desktop `<table>` is left byte
 * for byte where it was.
 *
 * The component is deliberately dumb: the caller computes the cells once and
 * hands the same strings to this and to its `<table>`, which is the only
 * thing stopping the two renderings from drifting apart.
 */

export interface StackedPair {
  label: string
  value: ReactNode
  /** Tabular figures and the numeric voice, as a right-aligned column is. */
  numeric?: boolean
}

export interface StackedRow {
  key: string | number
  title: ReactNode
  /** A chip-sized slot before the title: a direction, a tone, a verdict. */
  lead?: ReactNode
  pairs: StackedPair[]
  /** The panel the row's disclosure opens. Absent, there is no disclosure. */
  detail?: ReactNode
  /** The caller owns the open state, so a rung opened on the desktop table
   *  is still open when the phone rendering takes over (v19c §2.1). */
  open?: boolean
  onToggle?: () => void
}

/**
 * The pairs alone, in the one label voice (v19c §2.1).
 *
 * Exported because a row's disclosure holds the columns the row itself does
 * not show, and a second spelling of the label style is how two of them end
 * up looking different.
 */
export function StackedPairs(
  { pairs, className = '' }: { pairs: StackedPair[]; className?: string },
) {
  if (pairs.length === 0) return null
  return (
    <dl className={`grid grid-cols-2 gap-x-3 gap-y-0.5 ${className}`}>
      {pairs.map((pair) => (
        <div key={pair.label}
             className="flex items-baseline justify-between gap-2">
          <dt className="text-[11px] uppercase tracking-wide text-text-muted">
            {pair.label}
          </dt>
          <dd className={pair.numeric ? 'tn text-text' : 'text-text-secondary'}>
            {pair.value}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export interface StackedRowsProps {
  rows: StackedRow[]
  className?: string
  /** For a rail that wants to scope its query to one list. */
  testId?: string
}

export default function StackedRows(
  { rows, className = '', testId }: StackedRowsProps,
) {
  return (
    <ul role="list" data-testid={testId}
        className={`flex flex-col ${className}`}>
      {rows.map((row, i) => (
        <li
          key={row.key}
          data-testid={`stacked-row-${row.key}`}
          // The last row's rule would be a line under the list, and the
          // section below already draws its own (spec §5).
          className={`py-2${i < rows.length - 1
            ? ' border-b border-divider' : ''}`}
        >
          <div className="flex flex-wrap items-center gap-1.5">
            {row.lead !== undefined && row.lead !== null && (
              <span className="flex shrink-0 items-center gap-1.5">
                {row.lead}
              </span>
            )}
            <span className="min-w-0 flex-1 text-text">{row.title}</span>
            {row.detail !== undefined && row.onToggle && (
              <button
                type="button"
                aria-expanded={row.open === true}
                onClick={row.onToggle}
                className="shrink-0 text-text-muted hover:text-accent-text"
              >
                {row.open === true ? 'Less' : 'More'}
              </button>
            )}
          </div>
          <StackedPairs pairs={row.pairs} className="mt-1" />
          {row.detail !== undefined && row.open === true && (
            <div className="mt-2">{row.detail}</div>
          )}
        </li>
      ))}
    </ul>
  )
}
