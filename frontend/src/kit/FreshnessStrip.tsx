import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { Freshness, FreshnessRow } from '../types'

const LABELS: Record<string, string> = {
  refresh: 'data', odds: 'odds', field: 'field EO',
  advise: 'advice', backup: 'backup',
}

/**
 * Green under a day, amber under three, red beyond, grey for never.
 *
 * `null` is checked before the number and not folded into it: "never" and
 * "very old" are different states, and a `>= 72` branch would paint a cold
 * clone red as if something had gone wrong rather than not yet happened.
 */
export function tone(age: number | null): string {
  if (age === null) return 'text-text-faint'
  if (age < 24) return 'text-moss'
  if (age < 72) return 'text-amber'
  return 'text-rust'
}

export function ageText(age: number | null): string {
  if (age === null) return 'never'
  if (age < 1) return 'just now'
  if (age < 48) return `${Math.round(age)}h`
  return `${Math.round(age / 24)}d`
}

export default function FreshnessStrip() {
  const [rows, setRows] = useState<FreshnessRow[] | null>(null)

  useEffect(() => {
    // Fails soft and stays visible. A strip that disappeared when its own
    // fetch failed would teach the reader that no strip means nothing stale.
    apiGet<Freshness>('/api/meta/freshness')
      .then((data) => setRows(data.rows))
      .catch(() => setRows([]))
  }, [])

  if (rows === null) return null

  const known = new Map<string, FreshnessRow>(rows.map((r) => [r.source, r]))
  return (
    <div
      data-testid="freshness-strip"
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs
                 text-text-muted"
    >
      <span className="text-text-faint">as of</span>
      {/* Driven by LABELS rather than by `rows`, so an older server or a
          payload that lost a row still renders five greys — a shorter strip is
          a strip nobody notices is shorter. */}
      {Object.entries(LABELS).map(([source, label]) => {
        const row = known.get(source)
        const age = row?.age_hours ?? null
        return (
          <span key={source} className="whitespace-nowrap">
            {`${label} `}
            <span
              className={tone(age)}
              title={row?.modified_at ?? 'never run'}
              data-testid={`freshness-${source}`}
            >
              {ageText(age)}
            </span>
          </span>
        )
      })}
    </div>
  )
}
