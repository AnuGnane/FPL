import type { ReactNode } from 'react'
import type { PageData } from '../api/pageData'
import Button from './Button'
import Callout from './Callout'

export interface LoadedProps<T> {
  page: PageData<T>
  children: (data: T) => ReactNode
  /**
   * Shown for a 404 or 422 and for `isEmpty`; `null` when a card wants
   * neither. A function receives the server's sentence (`page.error`, or
   * `null` under `isEmpty`) for the empty states that print why — "run
   * `gaffer advise` first" is the server's to say.
   */
  empty?: ReactNode | ((message: string | null) => ReactNode)
  /** Default `null`, so a card that sets its own height keeps it. */
  loading?: ReactNode
  /** A body that arrived but says nothing — no rows, no fixtures. */
  isEmpty?: (data: T) => boolean
}

/**
 * The five states of one fetched page, in one place (v18e §2.2).
 *
 * Why a 404 or a 422 is the empty state and every other status is an error:
 * the server answers 404 for an artifact a route deliberately declares
 * absent (the plan, the chips, the components) and 422 for every
 * `GafferError` — "nothing on disk yet, run `gaffer advise` first" — which
 * is the same thing said by the app-wide handler (`web/app.py`); both are
 * things the user fixes by running a job. A 500 is a server that broke,
 * fixed by retrying or reading the log. Design ruling 7 is that a page must
 * never render a failure as a healthy empty — so the split is on the
 * status, not on the presence of an error, and the error branch always
 * offers the retry that distinguishes it. (v18e §2.2, corrected during the
 * cycle: the spec had said 404 alone; the cold clone answers 422.)
 */
export default function Loaded<T>(
  { page, children, empty = null, loading = null, isEmpty }: LoadedProps<T>,
) {
  const absent = page.status === 404 || page.status === 422
  if (page.error !== null && !absent) {
    return (
      <Callout tone="error">
        {page.error}{' '}
        <Button variant="ghost" onClick={page.reload}>Retry</Button>
      </Callout>
    )
  }
  const slot = (message: string | null) =>
    (typeof empty === 'function' ? empty(message) : empty)
  // A 404 or 422 is not a failure to report; the artifact is not there yet.
  if (page.error !== null) return <>{slot(page.error)}</>
  if (page.data === null) return <>{loading}</>
  if (isEmpty?.(page.data)) return <>{slot(null)}</>
  return <>{children(page.data)}</>
}
