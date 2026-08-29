import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { type ReactNode, useMemo, useState } from 'react'
import { useIsMobile } from './useMediaQuery'

export interface Column<T> {
  key: string
  header: string
  /** One of the three columns the mobile card shows before expanding (§8). */
  primary?: boolean
  /** Right-aligned and rendered in the mono face. */
  numeric?: boolean
  /** The sortable, printable value. */
  value: (row: T) => string | number | null
  /** Optional rich cell; `value` still drives sorting. */
  render?: (row: T) => ReactNode
}

export interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  /** The label used for the expand control and the mobile card heading. */
  rowLabel?: (row: T) => string
  expand?: (row: T) => ReactNode
  empty?: ReactNode
  /** Forces card mode; otherwise the `md` breakpoint decides. */
  collapse?: boolean
  initialSort?: string
}

type Cell = string | number | null

/** Missing values sort last whichever way the column points. `null` = neither
 *  is missing, so the real comparison decides. */
function missingOrder(a: Cell, b: Cell): number | null {
  const aMissing = a === null || a === undefined
  const bMissing = b === null || b === undefined
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1
  return null
}

function compareValues(a: Cell, b: Cell): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b
  return String(a).localeCompare(String(b))
}

// Descending inverts the comparator rather than reversing the sorted array.
// reverse() reverses *everything*: rows that tied came out in the opposite
// order to the one they arrived in, so a re-sort shuffled equal rows for no
// reason, and the missing values this comparator carefully pushes to the
// bottom ended up on top. Array.prototype.sort is stable, so inverting keeps
// ties in input order in both directions.
function compare(a: Cell, b: Cell, desc: boolean): number {
  const missing = missingOrder(a, b)
  if (missing !== null) return missing
  return desc ? -compareValues(a, b) : compareValues(a, b)
}

export default function DataTable<T>(
  { columns, rows, rowKey, rowLabel, expand, empty, collapse,
    initialSort }: DataTableProps<T>,
) {
  const [sortKey, setSortKey] = useState<string | null>(initialSort ?? null)
  const [desc, setDesc] = useState(true)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const mobile = useIsMobile()
  const cards = collapse ?? mobile

  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sortKey)
    if (!column) return rows
    return [...rows].sort(
      (a, b) => compare(column.value(a), column.value(b), desc))
  }, [columns, rows, sortKey, desc])

  const toggleSort = (key: string) => {
    if (key === sortKey) { setDesc((d) => !d); return }
    setSortKey(key)
    setDesc(true)
  }

  const toggleOpen = (key: string) => setOpen((prev) => {
    const next = new Set(prev)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    return next
  })

  const label = (row: T) =>
    rowLabel ? rowLabel(row) : String(columns[0].value(row) ?? '')

  if (rows.length === 0) return <>{empty ?? null}</>

  if (cards) {
    const primary = columns.filter((c) => c.primary).slice(0, 3)
    const rest = columns.filter((c) => !primary.includes(c))
    return (
      <div className="flex flex-col gap-2">
        <DropdownMenu.Root>
          <DropdownMenu.Trigger className="self-start rounded-card border
            border-border bg-card px-2 py-1 text-text-secondary">
            Sort
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content className="rounded-card border border-border
              bg-card p-1 text-text-secondary">
              {columns.map((column) => (
                <DropdownMenu.Item
                  key={column.key}
                  onSelect={() => toggleSort(column.key)}
                  className="cursor-pointer px-2 py-1 outline-none
                             data-[highlighted]:text-text"
                >
                  {column.header}
                </DropdownMenu.Item>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
        {sorted.map((row) => {
          const key = String(rowKey(row))
          const isOpen = open.has(key)
          return (
            <div key={key} data-testid={`row-card-${key}`}
                 className="rounded-card border border-border bg-card p-3">
              <div className="flex items-baseline justify-between gap-2">
                {primary.map((column) => (
                  <span key={column.key}
                        className={column.numeric ? 'num text-text' : 'text-text'}>
                    {column.render ? column.render(row) : column.value(row)}
                  </span>
                ))}
              </div>
              <button type="button" onClick={() => toggleOpen(key)}
                      className="mt-2 text-text-muted">
                {isOpen ? 'Less' : 'More'}
              </button>
              {isOpen && (
                <dl className="mt-2 grid grid-cols-2 gap-1">
                  {rest.map((column) => (
                    <div key={column.key} className="contents">
                      <dt className="label">{column.header}</dt>
                      <dd className={column.numeric ? 'num text-text' : 'text-text'}>
                        {column.render ? column.render(row) : column.value(row)}
                      </dd>
                    </div>
                  ))}
                  {expand && <div className="col-span-2">{expand(row)}</div>}
                </dl>
              )}
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead className="sticky top-0 bg-card">
          <tr>
            {expand && <th className="w-8" />}
            {columns.map((column) => (
              <th key={column.key}
                  className={`border-b border-divider px-2 py-2
                              ${column.numeric ? 'text-right' : 'text-left'}`}>
                <button type="button" onClick={() => toggleSort(column.key)}
                        className="label hover:text-text">
                  {column.header}
                  {sortKey === column.key ? (desc ? ' ▾' : ' ▴') : ''}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = String(rowKey(row))
            const isOpen = open.has(key)
            return [
              <tr key={key} className="border-b border-divider">
                {expand && (
                  <td className="px-2 py-2">
                    <button type="button" onClick={() => toggleOpen(key)}
                            aria-label={`expand ${label(row)}`}
                            className="text-text-muted">
                      {isOpen ? '▾' : '▸'}
                    </button>
                  </td>
                )}
                {columns.map((column) => (
                  <td key={column.key}
                      className={`px-2 py-2 ${column.numeric
                        ? 'num text-right text-text' : 'text-text'}`}>
                    {column.render ? column.render(row) : column.value(row)}
                  </td>
                ))}
              </tr>,
              isOpen && expand
                ? (
                  <tr key={`${key}-expand`} className="border-b border-divider">
                    <td colSpan={columns.length + 1} className="px-2 py-3">
                      {expand(row)}
                    </td>
                  </tr>
                  )
                : null,
            ]
          })}
        </tbody>
      </table>
    </div>
  )
}
