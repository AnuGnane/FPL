import Bar from './Bar'
import { fmtNum } from './format'

export interface ThresholdBarProps {
  label: string
  value: number | null | undefined
  threshold: number
  /** Bar full scale; defaults to twice the threshold. */
  max?: number
}

/** The chip meter: the one bar allowed inside a stat tile (rule 7). Over the
 *  threshold is `up`, under it `down` — a direction relative to θ. */
export default function ThresholdBar(
  { label, value, threshold, max }: ThresholdBarProps,
) {
  const scale = max ?? Math.max(threshold * 2, 1)
  const finite = typeof value === 'number' && Number.isFinite(value)
  const over = finite && value >= threshold
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="label">{label}</span>
        <span className="tn text-text">{finite ? fmtNum(value) : '—'}</span>
      </div>
      <div className="mt-1">
        <Bar width="full" testId="threshold"
             fraction={finite ? value / scale : null}
             mark={Math.min(threshold / scale, 1)}
             tone={over ? 'up' : 'down'} />
      </div>
      <p className="tn mt-1 text-xs text-text-faint">θ {fmtNum(threshold)}</p>
    </div>
  )
}
