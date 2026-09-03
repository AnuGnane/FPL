import { useEffect, useState } from 'react'
import {
  Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis,
  YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import {
  Badge, Card, EmptyState, PlayerName, PosBadge, Sparkline,
  difficultyBackground, fmtDelta, fmtNum,
} from '../../kit'
import type {
  ComponentsBreakdown, FixtureMatrixData, PlayerRow,
} from '../../types'
import CompareRadar from './CompareRadar'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

/**
 * The additive terms `web/routers/components.py`'s `TERMS` writes for one
 * fixture — the full breakdown, not the rows this card happens to print.
 * A term that rounds to zero is dropped before the payload leaves the server,
 * so `rows.length` is a floor on the number of roundings behind a card's
 * total and never a count of them.
 */
const BREAKDOWN_LABELS = ['Minutes', 'Goals', 'Assists', 'Clean sheet',
  'Goals conceded', 'Saves', 'Defensive contribution', 'Bonus',
  'Penalty saves', 'Cards', 'Calibration'] as const
const TERM_COUNT_PER_FIXTURE = BREAKDOWN_LABELS.length

/**
 * What the p25–p75 pair beside a player's xPts is a range *of*.
 *
 * `ep_gw` and `sigma` have been on `/api/components/{gw}` since the bands
 * shipped and nothing rendered either of them, so the schema documented two
 * fields the UI never showed. They belong here rather than in a column: σ is
 * the scale of the range the reader is already looking at, and `ep_gw` is the
 * single gameweek it brackets — which is *not* `ep`, the horizon sum the bar
 * chart above is drawn from, and the difference is exactly the kind of thing
 * a range beside the wrong number would hide.
 */
function bandTitle(components: ComponentsBreakdown | null,
                   code: number): string {
  const base = 'p25–p75 of what he might score: expected points plus '
    + 'football’s own variance, plus how far the forecast itself might move.'
  const comp = components?.players.find((p) => p.code === code)
  if (!comp || comp.sigma == null || comp.ep_gw == null) return base
  return `${base} GW forecast ${comp.ep_gw.toFixed(2)}, `
    + `σ ${comp.sigma.toFixed(2)} points.`
}

/**
 * One term of a player's expected points, signed.
 *
 * Not a stacked recharts bar (plan A3): eleven series need eleven
 * distinguishable colours and `SERIES_COLOURS` has four; a negative segment in
 * a recharts stack renders below the axis and stops reading as part of a
 * whole; and at 390px each card is a full-width column, where rows read and an
 * eleven-series stack does not.
 */
function SignedBar({ label, points, scale }: { label: string; points: number
                                               scale: number }) {
  const width = Math.min(50, (Math.abs(points) / scale) * 50)
  return (
    <div className="flex items-center gap-2">
      <span className="label flex-1 truncate">{label}</span>
      <span className="relative h-2 w-20 rounded bg-base">
        <span className="absolute left-1/2 top-0 h-2 w-px bg-text-faint" />
        <span
          className={`absolute top-0 h-2 ${points < 0
            ? 'rounded-l bg-rust' : 'rounded-r bg-sage'}`}
          style={points < 0
            ? { right: '50%', width: `${width}%` }
            : { left: '50%', width: `${width}%` }}
        />
      </span>
      <span className="num w-12 text-right text-text">
        {fmtDelta(points, 2)}
      </span>
    </div>
  )
}

/** How loudly a set-piece order is worth saying. `null` is "the bootstrap does
 *  not say", which is not "not a taker" — so it renders as nothing at all
 *  rather than as a crossed-out badge. */
function SetPieceFlag({ kind, order }: { kind: string; order: number | null }) {
  if (order === null) return null
  const tone = order === 1 ? 'text-text'
    : order === 2 ? 'text-text-muted' : 'text-text-faint'
  return (
    <span className={tone} title={`${kind}, order ${order}`}>
      {`${kind} ${order}`}
    </span>
  )
}

export interface ComparePanelProps {
  gw: number
  players: PlayerRow[]
  /** The explorer's currently-filtered rows, so the radar's axes can be
   *  normalized against a pool rather than against the two to four names the
   *  reader happens to have ticked. Optional: the panel renders without it
   *  and the radar's caption says which reference it used. */
  pool?: PlayerRow[]
}

export default function ComparePanel(
  { gw, players, pool = [] }: ComparePanelProps,
) {
  const [components, setComponents] = useState<ComponentsBreakdown | null>(null)
  const [matrix, setMatrix] = useState<FixtureMatrixData | null>(null)

  useEffect(() => {
    apiGet<ComponentsBreakdown>(`/api/components/${gw}`).then(setComponents)
      .catch(() => setComponents(null))
    apiGet<FixtureMatrixData>(`/api/fixtures/matrix?from=${gw}&n=6`)
      .then(setMatrix).catch(() => setMatrix(null))
  }, [gw])

  if (players.length < 2) {
    return (
      <EmptyState
        title="Pick at least two players"
        detail="Compare reads the expected-points decomposition side by side,
                so it needs two names ticked in the explorer."
        action="Tick two rows in Explorer"
      />
    )
  }
  if (players.length > 4) {
    return (
      <EmptyState
        title="Compare at most four players"
        detail="Beyond four the component bars stop being readable. Untick a
                name to bring the chart back."
        action="Untick a row in Explorer"
      />
    )
  }

  // One row per component label, one bar series per player: the shape Recharts
  // stacks, and the shape that makes "where does his EP come from" readable.
  const labels = new Set<string>()
  for (const player of components?.players ?? []) {
    for (const fixture of player.fixtures) {
      for (const component of fixture.components) labels.add(component.label)
    }
  }
  // Keyed by code, not by name: two players can share a surname, and a series
  // keyed by one of them would silently overwrite the other's bars. The name
  // rides on the series as its label, which is what the legend and the
  // tooltip print.
  const chart = [...labels].map((label) => {
    const row: Record<string, string | number> = { label }
    for (const player of players) {
      const found = components?.players.find((p) => p.code === player.code)
      row[String(player.code)] = found?.fixtures.reduce((total, fixture) => (
        total + (fixture.components.find((c) => c.label === label)?.points ?? 0)
      ), 0) ?? 0
    }
    return row
  })

  return (
    <div>
      <Card title="EP components" className="mb-4">
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chart}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="label" stroke="var(--color-text-muted)" />
            <YAxis stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            <Legend />
            {players.map((player, i) => (
              <Bar key={player.code} dataKey={String(player.code)}
                   name={player.name}
                   fill={SERIES_COLOURS[i % SERIES_COLOURS.length]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </Card>
      <Card title="Profile" className="mb-4">
        <CompareRadar gw={gw} players={players} pool={pool}
                      components={components} matrix={matrix} />
      </Card>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {players.map((player) => {
          const team = matrix?.teams.find((t) => t.code === player.team_code)
          const comp = components?.players.find((p) => p.code === player.code)
          // One row per label, summed over the horizon the payload holds —
          // the same reduction the grouped chart above performs, transposed.
          // Zeros stay dropped: that is `components.py`'s own honesty rule
          // ("a panel whose job is showing what moved should not print nine
          // zeroes to get to the one number that did") and not this cycle's
          // to overturn. The rows still sum to the total printed under them.
          const terms = new Map<string, number>()
          for (const fixture of comp?.fixtures ?? []) {
            for (const c of fixture.components) {
              terms.set(c.label, (terms.get(c.label) ?? 0) + c.points)
            }
          }
          const rows = [...terms].sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
          const total = rows.reduce((sum, [, points]) => sum + points, 0)
          const scale = Math.max(...rows.map(([, p]) => Math.abs(p)), 0.01)
          // Every term is already inside Goals — it was folded into e_goals
          // before the terms were assembled — so it is an annotation under
          // that row and never a twelfth component.
          const pen = (comp?.fixtures ?? [])
            .reduce((sum, f) => sum + (f.pen_taker ?? 0), 0)
          // The requested gameweek's fixtures, both of them on a double. Not a
          // mean: p_play averaged over two fixtures is a probability of
          // nothing, and p60 does not add. xMins is the one of the three that
          // does, so a total is shown beside the pair (plan A5).
          // A total missing one of its terms is not a smaller total: 88′
          // printed beside two fixtures reads as the pair, and it would be
          // one of them. `plan.py`'s bank convention, on the one quantity
          // here that adds — any null fixture blanks the total.
          const here = (comp?.fixtures ?? []).filter((f) => f.gw === gw)
          const xmSum = here.some((f) => f.minutes.xmins == null)
            ? null
            : here.reduce((sum, f) => sum + (f.minutes.xmins ?? 0), 0)
          return (
            <div key={player.code} data-testid={`compare-${player.code}`}>
              {/* The name is the control, not a label of one: the same
                  click-to-explain affordance every other page gives it.
                  PosBadge stays in the action slot, so no dot here. */}
              <Card
                heading={<PlayerName code={player.code} name={player.name} />}
                titleSize="lg"
                action={<PosBadge pos={player.position} />}
              >
                <dl className="grid grid-cols-2 gap-1">
                  <dt className="label">Price</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.price)}
                  </dd>
                  <dt className="label">xPts</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.ep_next)}
                    {player.ep_lo != null && player.ep_hi != null && (
                      // `ep_gw` and `sigma` ride in the tooltip rather than
                      // in a column of their own: the payload has carried
                      // them since the bands shipped and nothing rendered
                      // either, which left the schema making a promise the
                      // UI did not keep. They are also the two numbers that
                      // explain the range — σ is its scale, and `ep_gw` is
                      // the single gameweek it brackets, which is not the
                      // horizon sum in the bar chart above.
                      <span className="ml-1 text-text-muted"
                            title={bandTitle(components, player.code)}>
                        {`${player.ep_lo.toFixed(1)}–`
                          + `${player.ep_hi.toFixed(1)}`}
                      </span>
                    )}
                  </dd>
                  <dt className="label">EO%</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.league_eo)}
                  </dd>
                  <dt className="label">Field EO</dt>
                  <dd className="num text-right text-text"
                      data-testid={`field-eo-${player.code}`}>
                    {/* A "± —" is a plus-or-minus of nothing: the glyph
                        promises an interval the log did not record. An older
                        log carries an EO with no error at all, so the symbol
                        goes with the number it qualifies and the absence
                        moves into the title of the figure itself — 0.0 there
                        would still be the worse lie, a claim of perfect
                        precision from a few hundred entries. */}
                    <span title={player.field_eo === null
                      ? 'No field EO was measured for this player.'
                      : player.field_se === null
                        ? 'No error was recorded for this figure, so it '
                          + 'carries no interval.'
                        : 'Field EO, measured off sampled entries.'}>
                      {player.field_eo === null
                        ? '—' : `${fmtNum(player.field_eo, 1)}%`}
                    </span>
                    {player.field_eo !== null && player.field_se !== null && (
                      <span
                        className="ml-1 text-text-muted"
                        title={player.field_n === null
                          ? 'The sample size behind this figure is not recorded.'
                          : `Measured over ${player.field_n} sampled entries.`}
                      >
                        {`± ${fmtNum(player.field_se, 1)}`}
                      </span>
                    )}
                    {player.field_class && (
                      <span className="ml-1 text-text-muted">
                        {player.field_class}
                      </span>
                    )}
                  </dd>
                  <dt className="label">Own%</dt>
                  <dd className="num text-right text-text">
                    {fmtNum(player.ownership)}
                  </dd>
                </dl>
                {rows.length > 0 && (
                  <div className="mt-3" data-testid={`breakdown-${player.code}`}>
                    <p className="label">Where the points come from</p>
                    <div className="mt-1 flex flex-col gap-1">
                      {rows.map(([label, points]) => (
                        <div key={label}>
                          <SignedBar label={label} points={points}
                                     scale={scale} />
                          {label === 'Goals' && pen > 0 && (
                            <p className="pl-1 text-xs text-text-faint">
                              {`of which penalty duty ${fmtNum(pen, 2)} — `
                               + 'already inside Goals, not a term of its own'}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                    <p data-testid={`breakdown-total-${player.code}`}
                       className="mt-1 flex items-baseline justify-between
                                  border-t border-divider pt-1">
                      <span className="label">Total</span>
                      <span className="num text-text">{fmtNum(total, 2)}</span>
                    </p>
                    <p className="text-xs text-text-faint">
                      {/* `total` is the terms summed over every fixture the
                          payload holds — the same number `ep` is — and the
                          caption's job is to say when the xPts printed above
                          is *not* that: `ep_gw` is the requested gameweek
                          alone. So the comparison is against `ep_gw`, and a
                          payload that carries no `ep_gw` is compared against
                          itself and stays silent. The tolerance is per-term
                          rounding, not a constant: every term arrives at 2dp
                          and so does `ep_gw`, so a two-fixture card carries
                          twice the full breakdown's worth of half-hundredths,
                          plus one for the total itself, before anything is
                          actually inconsistent. The epsilon is float noise on
                          that exact boundary. */}
                      {comp && Math.abs((comp.ep_gw ?? total) - total)
                        > 0.005 * (TERM_COUNT_PER_FIXTURE
                                   * comp.fixtures.length + 1) + 1e-9
                        ? `The terms sum to the horizon (${fmtNum(total, 2)}); `
                          + `the xPts above is GW${gw} alone `
                          + `(${fmtNum(comp.ep_gw, 2)}).`
                        : 'These terms add up to the xPts above.'}
                    </p>
                  </div>
                )}
                {here.length > 0 && (
                  <div className="mt-3" data-testid={`minutes-${player.code}`}>
                    <p className="label">{`GW${gw} minutes`}</p>
                    {here.map((fixture) => (
                      <p key={`${fixture.gw}-${fixture.opponent}`}
                         data-testid={`minutes-${player.code}-`
                           + `${fixture.opponent}`}
                         className="flex items-baseline justify-between">
                        <span className="text-text-muted">
                          {`${fixture.home ? 'vs' : 'at'} ${fixture.opponent}`}
                        </span>
                        <span className="num text-text">
                          {/* An em dash, never 0.00: zero here reads as
                              "expected not to play", which is the strongest
                              claim this payload can make. */}
                          {`p ${fmtNum(fixture.minutes.p_play, 2)} · `
                           + `p60 ${fmtNum(fixture.minutes.p60, 2)} · `
                           + `${fmtNum(fixture.minutes.xmins, 0)}′`}
                        </span>
                      </p>
                    ))}
                    {here.length > 1 && (
                      <p data-testid={`minutes-total-${player.code}`}
                         className="flex items-baseline justify-between
                                    border-t border-divider pt-1">
                        <span className="label">xMins across both</span>
                        <span className="num text-text"
                              title={xmSum === null
                                ? 'One of these fixtures has no expected '
                                  + 'minutes, so the pair has no total. It is '
                                  + 'not the other fixture’s figure.'
                                : 'Expected minutes across both fixtures.'}>
                          {xmSum === null ? '—' : `${fmtNum(xmSum, 0)}′`}
                        </span>
                      </p>
                    )}
                  </div>
                )}
                {(player.penalties_order !== null
                  || player.free_kicks_order !== null
                  || player.corners_order !== null
                  || (player.set_piece_manual ?? []).length > 0) && (
                  <p data-testid={`setpieces-${player.code}`}
                     className="mt-2 flex flex-wrap items-center gap-2">
                    <SetPieceFlag kind="Pens" order={player.penalties_order} />
                    <SetPieceFlag kind="FK" order={player.free_kicks_order} />
                    <SetPieceFlag kind="Corners"
                                  order={player.corners_order} />
                    {/* v12 W4 §5.4: the row is your correction, not FPL's
                        publication. The list is in the title because which
                        kinds were overridden is the thing a reader checking
                        his own edit wants, and it does not fit on a chip.
                        `?? []` because the field is default-empty on the
                        server: a payload that predates it means "nothing
                        overridden", not a column that throws. */}
                    {(player.set_piece_manual ?? []).length > 0 && (
                      <Badge variant="info"
                             title={'Your override: '
                                    + (player.set_piece_manual
                                       ?? []).join(', ')}>
                        manual
                      </Badge>
                    )}
                  </p>
                )}
                <div className="mt-2">
                  <p className="label">Last 4</p>
                  <Sparkline values={player.last4} />
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {(team?.cells ?? []).map((cell) => {
                    // The cell carries two scores because a fixture is two
                    // different questions. `attack` is how freely the opponent
                    // concedes; `defence` is how hard they make a clean sheet.
                    // Colouring every card by `attack` told a goalkeeper's
                    // owner about his chances of scoring.
                    const score = player.position === 'GKP'
                      || player.position === 'DEF'
                      ? cell.defence
                      : cell.attack
                    // Timeline's idiom (plan A4): the tint is the number
                    // itself rather than a three-way band over it.
                    return (
                      <span
                        key={cell.gw}
                        className="rounded px-1 text-[10px] text-text"
                        style={{ background: difficultyBackground(score) }}
                        title={`GW${cell.gw} · ${cell.home ? 'home' : 'away'}`}
                      >
                        {`${cell.opponent} (${cell.home ? 'H' : 'A'})`}
                      </span>
                    )
                  })}
                </div>
              </Card>
            </div>
          )
        })}
      </div>
    </div>
  )
}
