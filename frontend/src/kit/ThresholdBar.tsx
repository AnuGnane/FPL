import { fmtNum } from './format'

export interface ThresholdBarProps {
  label: string
  value: number | null | undefined
  threshold: number
  /** Bar full scale; defaults to twice the threshold. */
  max?: number
}

export default function ThresholdBar(
  { label, value, threshold, max }: ThresholdBarProps,
) {
  const scale = max ?? Math.max(threshold * 2, 1)
  const finite = typeof value === 'number' && Number.isFinite(value)
  const pct = finite ? Math.min(Math.max((value / scale) * 100, 0), 100) : 0
  const over = finite && value >= threshold
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="label">{label}</span>
        <span className="num text-text">{finite ? fmtNum(value) : '—'}</span>
      </div>
      <div className="relative mt-1 h-2 rounded bg-base">
        <div
          data-testid="threshold-fill"
          style={{ width: `${pct}%` }}
          className={`h-2 rounded ${over ? 'bg-sage' : 'bg-rust'}`}
        />
        <div
          data-testid="threshold-mark"
          style={{ left: `${Math.min((threshold / scale) * 100, 100)}%` }}
          className="absolute top-0 h-2 w-px bg-text-muted"
        />
      </div>
      <p className="num mt-1 text-xs text-text-faint">θ {fmtNum(threshold)}</p>
    </div>
  )
}
