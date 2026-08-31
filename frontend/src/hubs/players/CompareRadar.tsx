import {
  Legend, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import type {
  ComponentsBreakdown, FixtureMatrixData, PlayerRow,
} from '../../types'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

/** How far ahead the fixture axis looks. Three, because that is the horizon a
 *  transfer is normally justified over and the one the fixture matrix's own
 *  colouring is read at. */
const FIXTURE_WEEKS = 3

/** Set-piece duty, scored by what each duty is actually worth in points.
 *  Penalties are a goal most times they are taken; corners are a chance of an
 *  assist. Second choice is half of first, because a deputy takes them only
 *  when the first choice is off the pitch. */
const DUTY_WEIGHT: Record<string, number> = {
  penalties: 1.0, freeKicks: 0.6, corners: 0.4,
}

export const AXES: Array<[string, string]> = [
  ['attacking', 'Attacking'],
  ['minutes', 'Minutes'],
  ['setPieces', 'Set pieces'],
  ['fixtures', 'Fixtures'],
  ['form', 'Form'],
]

export interface AxisValues {
  attacking: number
  minutes: number
  setPieces: number
  fixtures: number
  form: number
}

/**
 * Rescale one raw axis value against the pool, to 0-100.
 *
 * A degenerate pool — one player, or every value identical — maps to 50
 * rather than dividing by zero or picking an end. Fifty says "this axis
 * separates nobody here", which is true; zero or a hundred would be a verdict
 * the data does not support.
 */
export function normalize(value: number, pool: number[]): number {
  if (pool.length === 0) return 50
  const lo = Math.min(...pool)
  const hi = Math.max(...pool)
  if (!(hi > lo)) return 50
  const clamped = Math.min(Math.max(value, lo), hi)
  return Math.round(((clamped - lo) / (hi - lo)) * 100)
}

function duty(order: number | null, weight: number): number {
  if (order === 1) return weight
  if (order === 2) return weight / 2
  return 0
}

/**
 * The five raw axis values for one player, before normalization.
 *
 * Every one of them comes off something ComparePanel has already fetched
 * (plan A8) — there is no new endpoint in this feature and no import from
 * `set_pieces.py`, whose penalty share is a fitted input to the EP term
 * rather than a summary of a player's three set-piece duties.
 *
 * Missing inputs answer 0, except fixtures, which answers 0.5: an unfetched
 * fixture matrix is not a hard run of games, and drawing it as one would put
 * a spike in the chart that nothing in the data put there.
 */
export function axisValues(player: PlayerRow,
                           components: ComponentsBreakdown | null,
                           matrix: FixtureMatrixData | null,
                           gw: number): AxisValues {
  const comp = components?.players.find((p) => p.code === player.code)
  const week = (comp?.fixtures ?? []).filter((f) => f.gw === gw)
  const attackingPts = week.reduce((total, fixture) => total
    + fixture.components
      .filter((c) => c.label === 'Goals' || c.label === 'Assists')
      .reduce((sum, c) => sum + c.points, 0), 0)
  const weekEp = week.reduce((total, f) => total + f.ep, 0)

  const cells = (matrix?.teams.find((t) => t.code === player.team_code)?.cells
    ?? []).slice(0, FIXTURE_WEEKS)
  const defensive = player.position === 'GKP' || player.position === 'DEF'
  const difficulty = cells.length === 0 ? 0.5
    : cells.reduce((total, c) => total
      + (defensive ? c.defence : c.attack), 0) / cells.length

  return {
    attacking: weekEp > 0 ? attackingPts / weekEp : 0,
    minutes: week[0]?.minutes.p_play ?? 0,
    setPieces: Math.min(1, duty(player.penalties_order,
                                DUTY_WEIGHT.penalties)
      + duty(player.free_kicks_order, DUTY_WEIGHT.freeKicks)
      + duty(player.corners_order, DUTY_WEIGHT.corners)),
    // Difficulty runs 0 easiest to 1 hardest; the axis runs the other way,
    // because every other axis on this chart is "more is better".
    fixtures: 1 - difficulty,
    form: player.last4.length === 0 ? 0
      : player.last4.reduce((a, b) => a + b, 0) / player.last4.length,
  }
}

export interface CompareRadarProps {
  gw: number
  players: PlayerRow[]
  /** The explorer's currently-filtered rows, for normalization. Empty falls
   *  back to the selection, and the caption says which was used. */
  pool: PlayerRow[]
  components: ComponentsBreakdown | null
  matrix: FixtureMatrixData | null
}

/**
 * Five axes, overlaid.
 *
 * The reason a radar earns its place here and almost nowhere else: comparing
 * two players is genuinely a five-dimensional question, and the bar chart
 * beside it answers only the first dimension. A midfielder who out-scores
 * another on EP while losing on minutes security and set pieces is a
 * different bet, and that shape is what the reader is after.
 *
 * Two rules keep it honest. The normalization is stated in the caption rather
 * than implied — an axis scaled against an unnamed denominator is a number
 * pretending to be a fact. And a comparison across positions is **captioned,
 * not suppressed**: a goalkeeper against a forward is not a bug in the
 * selection, it is a comparison whose axes measure different jobs, and the
 * chart is the fastest way to see that.
 */
export default function CompareRadar(
  { gw, players, pool, components, matrix }: CompareRadarProps,
) {
  const reference = pool.length > 0 ? pool : players
  const raw = new Map(players.map(
    (p) => [p.code, axisValues(p, components, matrix, gw)]))
  const poolValues = reference.map((p) => axisValues(p, components, matrix, gw))

  const data = AXES.map(([key, label]) => {
    const column = poolValues.map((v) => v[key as keyof AxisValues])
    const row: Record<string, string | number> = { axis: label }
    for (const player of players) {
      row[player.name] = normalize(
        raw.get(player.code)![key as keyof AxisValues], column)
    }
    return row
  })

  const positions = new Set(players.map((p) => p.position))
  return (
    <div>
      <div aria-label="player comparison radar">
        <ResponsiveContainer width="100%" height={300}>
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="var(--color-divider)" />
            <PolarAngleAxis dataKey="axis" stroke="var(--color-text-muted)" />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            <Legend />
            {players.map((player, i) => (
              <Radar key={player.code} name={player.name}
                     dataKey={player.name} fillOpacity={0.15}
                     fill={SERIES_COLOURS[i % SERIES_COLOURS.length]}
                     stroke={SERIES_COLOURS[i % SERIES_COLOURS.length]} />
            ))}
          </RadarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-text-faint">
        {`Each axis is scaled 0–100 against the ${reference.length} players `
          + `${pool.length > 0 ? 'currently listed in Explorer'
            : 'being compared'}. Attacking is the share of this gameweek’s `
          + 'expected points coming from goals and assists; fixtures is the '
          + `next ${FIXTURE_WEEKS} weeks, read off defensive difficulty for `
          + 'keepers and defenders and attacking difficulty for everyone else.'}
      </p>
      {positions.size > 1 && (
        <p className="mt-1 text-text-muted">
          {`These players do different jobs — ${[...positions].join(', ')} — `
            + 'so the axes are not measuring the same thing on each of them. '
            + 'Read the shapes, not the overlap.'}
        </p>
      )}
    </div>
  )
}
