import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import type { ConfidenceData } from '../../types'

/**
 * What the banked record entitles the captain card to claim.
 *
 * Prose, and prose only. The whole reason this component exists is that every
 * other tool prints a confidence percentage computed from nothing, so there
 * is deliberately no bar, no colour scale and no number here that the ledger
 * did not count — the server sends a sentence and this renders it.
 *
 * Its own fetch, and a silent one: an unreachable endpoint renders nothing.
 * The captain's name above it is still correct without this line, and a red
 * error strip next to an armband would read as a problem with the armband.
 */
export default function ConfidenceLine() {
  const [data, setData] = useState<ConfidenceData | null>(null)

  useEffect(() => {
    apiGet<ConfidenceData>('/api/confidence').then(setData)
      .catch(() => setData(null))
  }, [])

  if (!data?.captain?.text) return null
  return (
    <p className="mt-2 text-text-muted" data-testid="captain-confidence">
      {data.captain.text}
    </p>
  )
}
