import { fmtNum } from '../../kit'

const FAN_KEYS = ['p05', 'p25', 'p50', 'p75', 'p95'] as const

/**
 * The margin fan: how far ahead of — or behind — the best rival the season
 * ends, at five centiles.
 *
 * The engine has published these since v8c and nothing rendered them, so the
 * card showed three point estimates and no spread at all. Five numbers and
 * two divs rather than a chart library: the shape here is a range with a
 * middle, which a bar says as well as an axis would and without a dependency.
 *
 * Zero is drawn wherever it falls in the range, because the only question the
 * strip has to answer at a glance is which side of it the season sits on.
 *
 * Cut out of `League.tsx` in v18f §2.1: the hub was four hundred and eighty
 * lines and this is the one piece of it that is a function of five numbers.
 */
export default function MarginFan({ quantiles }: {
  quantiles: Record<string, number>
}) {
  const values = FAN_KEYS.map((k) => quantiles[k])
  if (values.some((v) => typeof v !== 'number' || !Number.isFinite(v))) {
    return null
  }
  const [p05, p25, p50, p75, p95] = values
  const span = p95 - p05
  // A degenerate fan — no weeks left, one entry — is a point, not a bar.
  const at = (v: number) => (span > 0 ? ((v - p05) / span) * 100 : 50)
  const zero = Math.min(100, Math.max(0, at(0)))
  return (
    <div className="mb-3" data-testid="sim-margin-fan">
      <div className="label mb-1">Final margin over the best rival</div>
      {/* Rule 7's named league-race gap: one flat fill on the track, the
          median in text ink, zero in muted. Ahead is a direction (rule 1), so
          a median on the wrong side of zero draws the fan in `down`. */}
      <div className="relative mb-1 h-1.5 w-full rounded-chip bg-border">
        <div
          className={`absolute h-1.5 rounded-chip ${p50 >= 0
            ? 'bg-up' : 'bg-down'}`}
          style={{ left: `${at(p25)}%`, width: `${at(p75) - at(p25)}%` }}
        />
        <div
          className="absolute h-1.5 w-px bg-text"
          style={{ left: `${at(p50)}%` }}
        />
        {span > 0 && p05 <= 0 && p95 >= 0 && (
          <div
            className="absolute h-1.5 w-px bg-text-muted"
            style={{ left: `${zero}%` }}
            data-testid="sim-margin-zero"
          />
        )}
      </div>
      <div className="flex justify-between">
        {FAN_KEYS.map((key) => (
          <span key={key} className="tn text-xs text-text-muted"
                data-testid={`margin-${key}`}>
            {fmtNum(quantiles[key], 0)}
          </span>
        ))}
      </div>
    </div>
  )
}
