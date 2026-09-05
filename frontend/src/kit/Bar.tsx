export type BarTone = 'up' | 'down' | 'neutral'

const FILL: Record<BarTone, string> = {
  up: 'bg-up', down: 'bg-down', neutral: 'bg-text-muted',
}

export interface BarProps {
  /** 0..1 of a known ceiling. null, undefined or NaN draws an empty track. */
  fraction: number | null | undefined
  /** Printed beside the track, tabular. Omit for a bare track. */
  text?: string
  /** Grey unless the magnitude is a direction relative to something. */
  tone?: BarTone
  /** A mark at this fraction of the ceiling — the chip threshold. */
  mark?: number
  /** Track width in px, or the full width of the parent. */
  width?: number | 'full'
  /** Prefix for the data-testids: `<testId>-fill`, `<testId>-mark`. */
  testId?: string
  'aria-label'?: string
  className?: string
}

function clamp(pct: number): number {
  return Math.min(Math.max(pct, 0), 100)
}

/**
 * The one bar (rule 7): a flat single-colour fill, 6px, no border, no
 * fade, the number printed beside it. Allowed only where a magnitude
 * between zero and a known ceiling matters and there are several to compare
 * in one view. The track is drawn in `border` rather than `raised` so it is
 * still visible inside a hovered (raised) row (plan R8).
 */
export default function Bar({
  fraction, text, tone = 'neutral', mark, width = 56, testId = 'bar',
  'aria-label': ariaLabel, className = '',
}: BarProps) {
  const finite = typeof fraction === 'number' && Number.isFinite(fraction)
  const pct = finite ? clamp(fraction * 100) : 0
  const full = width === 'full'
  return (
    <span
      role={ariaLabel ? 'img' : undefined}
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-2 ${full ? 'w-full' : ''} `
        + className}
    >
      <span
        aria-hidden
        className={'relative block h-1.5 shrink-0 rounded-chip bg-border '
          + (full ? 'flex-1' : '')}
        style={full ? undefined : { width }}
      >
        <span
          data-testid={`${testId}-fill`}
          className={`block h-1.5 rounded-chip ${FILL[tone]}`}
          style={{ width: `${pct}%` }}
        />
        {mark !== undefined && (
          <span
            data-testid={`${testId}-mark`}
            className="absolute top-0 h-1.5 w-px bg-text"
            style={{ left: `${clamp(mark * 100)}%` }}
          />
        )}
      </span>
      {text !== undefined && <span className="tn shrink-0">{text}</span>}
    </span>
  )
}
