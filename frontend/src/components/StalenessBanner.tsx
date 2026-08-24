import type { Staleness } from '../types'

export default function StalenessBanner(
  { staleness, onRerun, busy }:
  { staleness: Staleness; onRerun: () => void; busy: boolean },
) {
  if (!staleness.stale) return null
  return (
    <div className="banner">
      <span>
        {staleness.reason} · generated {staleness.generated_at}
      </span>
      <button onClick={onRerun} disabled={busy}>
        {busy ? 'Re-running…' : 'Re-run advice'}
      </button>
    </div>
  )
}
