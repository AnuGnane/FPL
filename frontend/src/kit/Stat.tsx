import type { ReactNode } from 'react'
import { TONE_CLASS, fmtDelta, fmtNum, toneOf } from './format'

export interface StatProps {
  label: string
  /** A pre-formatted string, or a raw number that goes through fmtNum. */
  value: ReactNode | number
  delta?: number | null
  deltaLabel?: string
}

export default function Stat({ label, value, delta, deltaLabel }: StatProps) {
  const shown = typeof value === 'number' ? fmtNum(value) : value
  return (
    <div className="rounded-card border border-border bg-card px-4 py-3">
      <p className="label">{label}</p>
      <p className="num mt-1 text-2xl text-text">{shown}</p>
      {delta !== undefined && delta !== null && (
        <p data-testid="stat-delta"
           className={`num mt-1 text-xs ${TONE_CLASS[toneOf(delta)]}`}>
          {fmtDelta(delta)}
          {deltaLabel ? <span className="ml-1 text-text-faint">{deltaLabel}</span> : null}
        </p>
      )}
    </div>
  )
}
