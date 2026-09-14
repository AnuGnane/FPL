import type { ReactNode } from 'react'
import { thClass } from './table'

/** What a sortable column is currently doing, in the vocabulary `aria-sort`
 *  speaks. `'none'` is a column that can be sorted and is not — which is what
 *  tells a screen-reader user the header is a control at all. */
export type ThSort = 'ascending' | 'descending' | 'none'

export interface ThProps {
  children?: ReactNode
  /** Right-aligned, as `thClass` draws a numeric column. */
  numeric?: boolean
  sort?: ThSort
  /** Appended after `thClass`, exactly as the hand-written headers did. */
  className?: string
  colSpan?: number
}

/**
 * A column header.
 *
 * v18f §2.2. `table.ts` gave every table the same class string and nothing
 * else, so the `scope="col"` that tells a screen reader which cells a header
 * governs was a thing each table had to remember, and none of them did. This
 * carries it, and the sort state with it: a header whose glyph says which way
 * the column points says the same thing in `aria-sort`, and the glyph itself
 * is hidden from the reader who is being told in words.
 *
 * `table.ts` cannot hold this — a `.ts` file has no JSX — so the class
 * strings stay there and the element lives here.
 */
export default function Th(
  { children, numeric = false, sort, className = '', colSpan }: ThProps,
) {
  const classes = className
    ? `${thClass(numeric)} ${className}` : thClass(numeric)
  return (
    <th scope="col" aria-sort={sort} colSpan={colSpan} className={classes}>
      {children}
    </th>
  )
}
