import {
  CartesianGrid, Line, LineChart as RLineChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { SERIES_COLOURS } from '../../../kit'
import type { HeadMetrics } from '../../../types'

/**
 * Cut from `QualityTab.tsx` in v18f §2.1 — the tab was a thousand lines with
 * a natural seam at its self-fetching sections.
 *
 * `Reliability` is the one helper on both sides of that seam: the moved
 * `CalibrationSection` draws it and so does `CurrentSection`, which takes
 * props and stayed in the tab. Neither file owns it, so it lives here rather
 * than in the parent — a section importing a helper back out of `QualityTab`
 * would close a cycle around the file the cut exists to thin.
 */

/**
 * One head's reliability curve, against the line it is trying to be.
 *
 * The diagonal is the whole chart. A calibration plot without y = x on it
 * asks the reader to imagine the reference and then judge distance from it by
 * eye, which is exactly the judgement the picture exists to make unnecessary:
 * above the line the head is under-confident, below it over-confident, and
 * the size of the gap is the size of the error the optimizer inherits when it
 * multiplies by these numbers.
 *
 * The observation count is printed rather than drawn. A curve fitted on forty
 * rows and one fitted on forty thousand are the same shape on screen and are
 * not the same evidence.
 */
export function Reliability(
  { label, head }: { label: string; head: HeadMetrics },
) {
  const points = head.reliability
  const n = points.reduce((total, bin) => total + bin.n, 0)
  return (
    <div className="mb-3">
      <p className="label">
        {label} — log loss {head.log_loss ?? 'n/a'}
      </p>
      <div aria-label={`${label} reliability`}>
        <ResponsiveContainer width="100%" height={220}>
          <RLineChart data={points}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="pred" type="number" domain={[0, 1]}
                   stroke="var(--color-text-muted)" />
            <YAxis type="number" domain={[0, 1]}
                   stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{ background: 'var(--color-raised)',
                                     border: '1px solid var(--color-border)' }} />
            {/* Perfect calibration. Drawn as a segment rather than a
                ReferenceLine because a diagonal reference needs two points
                and recharts' ReferenceLine takes a single axis value. */}
            <Line data={[{ pred: 0, ideal: 0 }, { pred: 1, ideal: 1 }]}
                  dataKey="ideal" dot={false} isAnimationActive={false}
                  stroke="var(--color-text-muted)" strokeDasharray="4 4"
                  strokeWidth={1} />
            {/* The observed curve is the first series: the brightest grey,
                not a green (plan R6 — nothing here is a direction). */}
            <Line type="monotone" dataKey="obs" dot={false}
                  stroke={SERIES_COLOURS[0]} strokeWidth={2} />
          </RLineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-text-faint">
        {`${points.length} populated bins over ${n} observations. Above the `
          + 'dashed line the head is under-confident; below it, over-confident.'}
      </p>
    </div>
  )
}
