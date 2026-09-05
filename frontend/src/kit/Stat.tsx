import type { ReactNode } from 'react'
import { TONE_CLASS, fmtDelta, fmtNum, toneOf } from './format'

/**
 * The one stat tile shape (spec §5): label; value at 22px with the unit in
 * 12px muted beside it; one 12px muted context line; an optional meter
 * (rule 7 — the chip threshold only). A name (the captain) is a value like
 * any other. It draws no box: `StatRow` puts the hairlines between tiles.
 */
export interface StatProps {
  label: string
  /** A pre-formatted string, or a raw number that goes through fmtNum. */
  value: ReactNode | number
  unit?: ReactNode
  context?: ReactNode
  meter?: ReactNode
  /** Pre-v14 shape, still honoured: rendered as a toned context line. */
  delta?: number | null
  deltaLabel?: string
}

export default function Stat(
  { label, value, unit, context, meter, delta, deltaLabel }: StatProps,
) {
  const shown = typeof value === 'number' ? fmtNum(value) : value
  return (
    <div className="min-w-0 px-4 py-3">
      <p className="label">{label}</p>
      <p className="mt-1 flex items-baseline gap-1.5 text-[22px] font-semibold
                    leading-tight text-text">
        <span className="tn truncate">{shown}</span>
        {unit !== undefined && unit !== null && (
          <span className="text-xs font-normal text-text-muted">{unit}</span>
        )}
      </p>
      {context !== undefined && context !== null && (
        <p className="mt-0.5 text-xs text-text-muted">{context}</p>
      )}
      {delta !== undefined && delta !== null && (
        <p data-testid="stat-delta"
           className={`tn mt-0.5 text-xs ${TONE_CLASS[toneOf(delta)]}`}>
          {fmtDelta(delta)}
          {deltaLabel ? <span className="ml-1 text-text-faint">{deltaLabel}</span> : null}
        </p>
      )}
      {meter && <div className="mt-2">{meter}</div>}
    </div>
  )
}
