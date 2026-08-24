// Hand-rolled SVG rather than a charting dependency: three small line charts
// do not justify a runtime library, and inline SVG is directly assertable in
// jsdom, where a responsive-container chart renders at zero size.
export interface Series {
  name: string
  colour: string
  points: Array<{ x: number; y: number }>
}

const WIDTH = 640
const HEIGHT = 220
const PAD = 32

export default function LineChart(
  { label, series }: { label: string; series: Series[] },
) {
  const all = series.flatMap((s) => s.points)
  if (all.length === 0) return <p className="muted">No data yet.</p>
  const xs = all.map((p) => p.x)
  const ys = all.map((p) => p.y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys, 0)
  const maxY = Math.max(...ys, 1)
  const px = (x: number) =>
    PAD + ((x - minX) / Math.max(maxX - minX, 1)) * (WIDTH - 2 * PAD)
  const py = (y: number) =>
    HEIGHT - PAD - ((y - minY) / Math.max(maxY - minY, 1)) * (HEIGHT - 2 * PAD)

  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      className="chart"
    >
      <line x1={PAD} y1={HEIGHT - PAD} x2={WIDTH - PAD} y2={HEIGHT - PAD}
        stroke="var(--line)" />
      <line x1={PAD} y1={PAD} x2={PAD} y2={HEIGHT - PAD}
        stroke="var(--line)" />
      {series.map((s) => (
        <polyline
          key={s.name}
          fill="none"
          stroke={s.colour}
          strokeWidth={2}
          points={s.points.map((p) => `${px(p.x)},${py(p.y)}`).join(' ')}
        />
      ))}
      {series.map((s, index) => (
        <text key={s.name} x={PAD + 8} y={PAD + 14 * (index + 1)}
          fill={s.colour} fontSize="12">
          {s.name}
        </text>
      ))}
    </svg>
  )
}
