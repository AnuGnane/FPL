import type { Staleness } from '../types'

/**
 * Two different problems, two different banners.
 *
 * `.banner-stale` — the advice is for a gameweek that has moved on; re-run it.
 * `.banner-data` — the advice is current, but was built before FPL finalized
 * the gameweek just played, so the model never saw those results.
 */
export default function StalenessBanner(
  { staleness, onRerun, busy }:
  { staleness: Staleness; onRerun: () => void; busy: boolean },
) {
  if (!staleness.stale && !staleness.data_warning) return null
  return (
    <>
      {staleness.stale && (
        <div className="banner banner-stale">
          <span>
            {staleness.reason} · generated {staleness.generated_at}
          </span>
          <button onClick={onRerun} disabled={busy}>
            {busy ? 'Re-running…' : 'Re-run advice'}
          </button>
        </div>
      )}
      {staleness.data_warning && (
        <div className="banner banner-data" role="status">
          <span>
            <strong>Underinformed advice:</strong> {staleness.data_warning}
          </span>
        </div>
      )}
    </>
  )
}
