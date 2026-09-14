import type { ReactNode } from 'react'
import type { PageData } from '../api/pageData'
import Button from './Button'
import Callout from './Callout'

export interface LoadedProps<T> {
  page: PageData<T>
  children: (data: T) => ReactNode
  /** Shown for a 404 and for `isEmpty`. `null` when a card wants neither. */
  empty?: ReactNode
  /** Default `null`, so a card that sets its own height keeps it. */
  loading?: ReactNode
  /** A body that arrived but says nothing — no rows, no fixtures. */
  isEmpty?: (data: T) => boolean
}

/**
 * The five states of one fetched page, in one place (v18e §2.2).
 *
 * Why the 404 is the empty state and every other status is an error: the
 * server answers 404 for an artifact that has not been written yet, which is
 * a thing the user fixes by running a job, and 500 for a server that broke,
 * which is a thing the user fixes by retrying or reading the log. Design
 * ruling 7 is that a page must never render a failure as a healthy empty —
 * so the split is on the status, not on the presence of an error, and the
 * error branch always offers the retry that distinguishes it.
 */
export default function Loaded<T>(
  { page, children, empty = null, loading = null, isEmpty }: LoadedProps<T>,
) {
  if (page.error !== null && page.status !== 404) {
    return (
      <Callout tone="error">
        {page.error}{' '}
        <Button variant="ghost" onClick={page.reload}>Retry</Button>
      </Callout>
    )
  }
  // A 404 is not a failure to report; it is the artifact not being there yet.
  if (page.error !== null) return <>{empty}</>
  if (page.data === null) return <>{loading}</>
  if (isEmpty?.(page.data)) return <>{empty}</>
  return <>{children(page.data)}</>
}
