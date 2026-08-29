export interface SparklineProps {
  values: number[]
  width?: number
  height?: number
}

// Hand-rolled rather than Recharts: this is an inline 4-8 point trend inside a
// table cell, where a responsive container would measure a zero-width parent.
export default function Sparkline(
  { values, width = 56, height = 16 }: SparklineProps,
) {
  const clean = values.filter((v) => Number.isFinite(v))
  if (clean.length < 2) return <span className="text-text-faint">—</span>

  const min = Math.min(...clean)
  const max = Math.max(...clean)
  const span = max - min || 1
  const step = clean.length > 1 ? width / (clean.length - 1) : width
  const points = clean
    .map((v, i) => `${(i * step).toFixed(1)},${
      (height - ((v - min) / span) * height).toFixed(1)}`)
    .join(' ')
  const rising = clean[clean.length - 1] >= clean[0]

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         role="img" aria-label="recent form" className="inline-block">
      <polyline
        points={points}
        fill="none"
        strokeWidth={1.5}
        stroke={rising ? 'var(--color-sage)' : 'var(--color-rust)'}
      />
    </svg>
  )
}
