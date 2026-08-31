import { useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart as RLineChart, ReferenceLine,
  ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import { ApiError, apiGet } from '../../api/client'
import {
  type Column, Badge, Card, DataTable, EmptyState, Loading, PlayerName,
  PosBadge, Stat, fmtNum, fmtPct,
} from '../../kit'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  MissRow, MissesData, NewsShadowData, PenTrackerData,
  PenTrackerGw, QualityData, ReviewData, StratifiedTable,
} from '../../types'

// Categories are OpenFPL's, defined on actual points, so the labels have to
// stay recognisable next to their published table.
const CATEGORIES: Array<[string, string]> = [
  ['zeros', 'Zeros'],
  ['blanks', 'Blanks'],
  ['tickers', 'Tickers'],
  ['haulers', 'Haulers'],
  ['all', 'All'],
]

const HEADS: Array<[string, string]> = [
  ['p_play', 'P(plays)'],
  ['p60', 'P(60+ minutes)'],
  // v8a has emitted this since the trichotomy landed and nothing rendered it.
  // p_play is a sum of two modes, so a model that sharpens the start/cameo
  // split while leaving the sum alone is invisible in the two above.
  ['p_start', 'P(starts)'],
  ['cs', 'P(clean sheet)'],
]

const SOURCE_LABELS: Record<string, string> = {
  openfpl: 'OpenFPL',
  fplreview: 'FPL Review',
}

const CELLS: Array<[string, string]> = [
  ['model_h1', 'Model, 1-week'],
  ['model_h3', 'Model, 3-week'],
  ['oracle_h1', 'Oracle, 1-week'],
  ['oracle_h3', 'Oracle, 3-week'],
]

function StratifiedTableView(
  { columns }: { columns: Array<[string, StratifiedTable]> },
) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr>
            <th className="label pb-1 text-left">Category</th>
            {columns.map(([name]) => (
              <th key={name} colSpan={2}
                  className="label border-l border-divider pb-1 text-center">
                {name}
              </th>
            ))}
          </tr>
          <tr>
            <th />
            {columns.map(([name]) => [
              <th key={`${name}-rmse`}
                  className="label border-l border-divider pb-1 pl-2
                             text-right">
                RMSE
              </th>,
              <th key={`${name}-mae`} className="label pb-1 text-right">
                MAE
              </th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {CATEGORIES.map(([key, label]) => (
            <tr key={key} className="border-t border-divider">
              <td className="py-1.5 text-text">{label}</td>
              {columns.map(([name, table]) => [
                <td key={`${name}-${key}-rmse`}
                    className="num border-l border-divider py-1.5 pl-2
                               text-right text-text">
                  {table[key] === undefined ? '—' : table[key].rmse}
                </td>,
                <td key={`${name}-${key}-mae`}
                    className="num py-1.5 text-right text-text-secondary">
                  {table[key] === undefined ? '—' : table[key].mae}
                </td>,
              ])}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

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
function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
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
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            {/* Perfect calibration. Drawn as a segment rather than a
                ReferenceLine because a diagonal reference needs two points
                and recharts' ReferenceLine takes a single axis value. */}
            <Line data={[{ pred: 0, ideal: 0 }, { pred: 1, ideal: 1 }]}
                  dataKey="ideal" dot={false} isAnimationActive={false}
                  stroke="var(--color-text-muted)" strokeDasharray="4 4"
                  strokeWidth={1} />
            <Line type="monotone" dataKey="obs" dot={false}
                  stroke="var(--color-sage)" strokeWidth={2} />
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

function CurrentSection({ current }: { current: CurrentEvaluation }) {
  return (
    <>
      <Card title="Holdout" className="mb-4">
        <p className="mb-3 text-text-muted">
          Last-10-slot holdout, {current.holdout_slots} gameweeks, sha{' '}
          {current.git_sha}, run {current.run_at}.
        </p>
        <StratifiedTableView
          columns={[
            ['Model (all)', current.stratified.all ?? {}],
            ['Model (starters)', current.stratified.starters ?? {}],
            ['Last-5 mean', current.baselines.last5 ?? {}],
            ['Last-38 mean', current.baselines.last38_ppg ?? {}],
          ]}
        />
      </Card>
      <Card title="Calibration" className="mb-4">
        {HEADS.map(([key, label]) => {
          const head = current.heads[key]
          return head === undefined ? null
            : <Reliability key={key} label={label} head={head} />
        })}
      </Card>
    </>
  )
}

function BenchmarkSection({ benchmark }: { benchmark: BenchmarkEvaluation }) {
  const references: Array<[string, StratifiedTable]> = Object.entries(
    benchmark.references,
  ).map(([source, table]) => [
    SOURCE_LABELS[source] ?? source,
    Object.fromEntries(Object.entries(table).map(([cat, m]) => [
      cat, { rmse: m.rmse, mae: m.mae, n: 0 },
    ])) as StratifiedTable,
  ])
  return (
    <Card title={`Benchmark — ${benchmark.test_season}`} className="mb-4">
      <StratifiedTableView
        columns={[['Ours', benchmark.stratified.all ?? {}], ...references]}
      />
      <p className="mt-3 text-text-muted">{benchmark.caveat}</p>
    </Card>
  )
}

function DecompositionSection(
  { decomposition }: { decomposition: DecompositionData },
) {
  return (
    <Card
      title={`Decomposition — ${decomposition.season} from GW`
        + ` ${decomposition.start_gw}`}
      className="mb-4"
    >
      <table className="w-full">
        <thead>
          <tr>
            <th className="label pb-1 text-left">Run</th>
            <th className="label pb-1 text-right">Total</th>
            <th className="label pb-1 text-right">Per GW</th>
            <th className="label pb-1 text-right">Hits</th>
          </tr>
        </thead>
        <tbody>
          {CELLS.map(([key, label]) => {
            const cell = decomposition.cells[key]
            return cell === undefined ? null : (
              <tr key={key} className="border-t border-divider">
                <td className="py-1.5 text-text">{label}</td>
                <td className="num py-1.5 text-right text-text">
                  {cell.total}
                </td>
                <td className="num py-1.5 text-right text-text-secondary">
                  {cell.per_gw}
                </td>
                <td className="num py-1.5 text-right text-text-muted">
                  {cell.hits}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <table className="mt-4 w-full">
        <tbody>
          {([
            ['Forecast gap (3-week)', decomposition.forecast_gap_h3,
             'points better forecasting could still win'],
            ['Planning ceiling', decomposition.planning_ceiling,
             'the most multi-week planning can ever be worth'],
          ] as const).map(([label, value, note]) => (
            <tr key={label} className="border-t border-divider">
              <td className="py-1.5 text-text">{label}</td>
              <td className="num py-1.5 pl-3 text-right text-text">{value}</td>
              <td className="py-1.5 pl-3 text-text-muted">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

// Lower is better for both metrics, so "ahead" means a smaller number. Said
// in a sentence as well as drawn, because a pair of bars two hundredths apart
// is not a verdict anyone should have to squint at.
function verdict(shadow: NewsShadowData): string {
  const o = shadow.overall
  if (o.brier_news === undefined || o.mae_news === undefined) {
    return 'Nothing scored yet.'
  }
  const brier = (o.brier_flags ?? 0) - o.brier_news
  const mae = (o.mae_flags ?? 0) - o.mae_news
  if (brier > 0 && mae > 0) {
    return `News is ahead on both: Brier ${brier.toFixed(4)} better, `
      + `minutes MAE ${mae.toFixed(2)} better, over ${shadow.rows} `
      + 'player-gameweeks.'
  }
  if (brier <= 0 && mae <= 0) {
    return `Flags are ahead on both, over ${shadow.rows} player-gameweeks — `
      + 'the news layer is not earning its place yet.'
  }
  return `Split: Brier ${brier > 0 ? 'news' : 'flags'}, minutes `
    + `${mae > 0 ? 'news' : 'flags'}, over ${shadow.rows} player-gameweeks.`
}

// Paired bars, per gameweek, both metrics. Each pair is scaled to its own
// row's larger value: the two Brier numbers differ in the third decimal and a
// shared axis across gameweeks would draw every pair as one flat line.
function PairedBar({ news, flags }: { news: number; flags: number }) {
  const top = Math.max(news, flags) || 1
  return (
    <span className="inline-flex w-28 flex-col gap-0.5 align-middle">
      <span className="h-1.5 rounded-full bg-base">
        <span className="block h-1.5 rounded-full"
              style={{ width: `${(news / top) * 100}%`,
                       background: 'var(--color-sage)' }}
              aria-label={`news ${news}`} />
      </span>
      <span className="h-1.5 rounded-full bg-base">
        <span className="block h-1.5 rounded-full"
              style={{ width: `${(flags / top) * 100}%`,
                       background: 'var(--color-text-muted)' }}
              aria-label={`flags ${flags}`} />
      </span>
    </span>
  )
}

function NewsShadowSection({ shadow }: { shadow: NewsShadowData }) {
  return (
    <Card title="News layer">
      <p className="mb-3 rounded-card border-l-2 border-info bg-base px-3
                    py-2 text-text-secondary">
        {verdict(shadow)}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">GW</th>
              <th className="label pb-1 text-right">Brier news</th>
              <th className="label pb-1 text-right">Brier flags</th>
              <th />
              <th className="label pb-1 text-right">Minutes MAE news</th>
              <th className="label pb-1 text-right">MAE flags</th>
              <th />
              <th className="label pb-1 text-right">Rows</th>
            </tr>
          </thead>
          <tbody>
            {shadow.by_gw.map((row) => (
              <tr key={row.gw} className="border-t border-divider">
                <td className="num py-1.5 text-text">GW{row.gw}</td>
                <td className="num py-1.5 text-right text-sage">
                  {row.brier_news}
                </td>
                <td className="num py-1.5 text-right text-text-muted">
                  {row.brier_flags}
                </td>
                <td className="px-2 py-1.5">
                  <PairedBar news={row.brier_news} flags={row.brier_flags} />
                </td>
                <td className="num py-1.5 text-right text-sage">
                  {row.mae_news}
                </td>
                <td className="num py-1.5 text-right text-text-muted">
                  {row.mae_flags}
                </td>
                <td className="px-2 py-1.5">
                  <PairedBar news={row.mae_news} flags={row.mae_flags} />
                </td>
                <td className="num py-1.5 text-right text-text-secondary">
                  {row.rows}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// The instrument is the first thing to read on a pen row: an xg-gap week
// counts penalties, a pens_missed_only week can only see the ones that were
// missed, so every number beside it is a floor rather than a count.
function InstrumentCell({ row }: { row: PenTrackerGw }) {
  if (row.error) {
    return (
      <span className="text-text-muted" title={row.error}>unreadable</span>
    )
  }
  if (row.instrument === 'pens_missed_only') {
    return (
      <Badge variant="negative"
             title="counted from missed penalties only — converted spot kicks
                    are invisible, so every count on this row is a floor">
        floor
      </Badge>
    )
  }
  return <Badge variant="info">{row.instrument ?? '—'}</Badge>
}

const PEN_COLUMNS: Column<PenTrackerGw>[] = [
  { key: 'gw', header: 'GW', primary: true, value: (r) => r.gw,
    render: (r) => (
      <span className={r.error ? 'num text-text-muted' : 'num text-text'}>
        GW{r.gw}
      </span>
    ) },
  { key: 'instrument', header: 'Instrument', primary: true,
    value: (r) => (r.error ? 'unreadable' : r.instrument ?? '—'),
    render: (r) => <InstrumentCell row={r} /> },
  { key: 'covered_rows', header: 'Covered', numeric: true,
    value: (r) => r.covered_rows ?? null,
    render: (r) => fmtNum(r.covered_rows, 0) },
  { key: 'pens_taken', header: 'Pens', primary: true, numeric: true,
    value: (r) => r.pens_taken ?? null,
    render: (r) => fmtNum(r.pens_taken) },
  { key: 'taker_hit_rate', header: 'Hit rate', numeric: true,
    value: (r) => r.taker_hit_rate ?? null,
    render: (r) => fmtPct(r.taker_hit_rate) },
]

/**
 * The v6 penalty term, measured forward. Its own fetch, like every other
 * section here: the tracker is a separate artifact with its own "not written
 * yet" state, and folding it into /api/quality would make one missing file
 * blank the other's page.
 */
function PensSection() {
  const [data, setData] = useState<PenTrackerData | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<PenTrackerData>('/api/pens').then(setData).catch((e: Error) => {
      // 422 is the ordinary "nobody has run it yet". Anything else is a
      // server that cannot answer — said in this card and no louder, because
      // the page above still has its numbers. Silence was worse: a card that
      // simply disappears reads as "no penalties tracked".
      if (e instanceof ApiError && e.status === 422) setEmpty(e.message)
      else setError(e.message)
    })
  }, [])

  if (error) {
    return (
      <Card title="Penalty term unavailable" className="mt-4">
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (empty) {
    return (
      <EmptyState
        title="No penalty tracker yet"
        detail={empty}
        action="gaffer track-pens"
      />
    )
  }
  // A payload without a gws array is not a tracker: render nothing rather
  // than crash the tab on an artifact half-written by an older version.
  if (!data || !Array.isArray(data.gws)) return null

  const totals = data.season_totals ?? {}
  return (
    <Card title={`Penalty term — ${data.season || 'season unknown'}`}
          className="mt-4">
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Pens taken" value={fmtNum(totals.pens_taken)} />
        <Stat label="Taker hit rate" value={fmtPct(totals.taker_hit_rate)} />
        <Stat
          label="Pens / team-game"
          value={`${fmtNum(totals.pens_per_team_game, 3)} vs `
            + `${fmtNum(totals.league_pens_pg_served, 2)} served`}
        />
        <Stat
          label="Predicted EP / realized"
          value={`${fmtNum(totals.predicted_ep_pen_taker)} / `
            + `${fmtNum(totals.realized_pen_points)}`}
        />
      </div>
      <DataTable
        columns={PEN_COLUMNS}
        rows={data.gws}
        rowKey={(r) => r.gw}
        rowLabel={(r) => `GW${r.gw}`}
        initialSort="gw"
        empty={<p className="text-text-muted">No finished gameweek yet.</p>}
      />
      {(data.notes ?? []).map((note) => (
        <p key={note} className="mt-2 text-text-faint">{note}</p>
      ))}
    </Card>
  )
}

/**
 * Your points against the model's, one point per graded gameweek.
 *
 * Both axes come off `reports/decision_ledger.json`, and that is the whole
 * design. The card used to plot `advise.raw_xi_pts` — an untilted sum of EP
 * over the eleven the advice run picked, before captaincy and before hits —
 * against the entry's official net score off `meta.py`. Two different
 * quantities on two axes with a y = x line drawn through them: every point
 * sat above the line, and the "gap" the reader took away was a unit mismatch
 * rather than a miss.
 *
 * The ledger's two numbers are commensurable by construction. `review.grade_gw`
 * hand-scores both squads against the same actuals frame: `my_points` is my
 * eleven with my armband, net of hits, and `model_points` is that same squad
 * with every *comparable* lane replaced by the model's. So the diagonal is a
 * real reference — above it my week beat the model's advice, below it the
 * advice would have beaten me — and the vertical distance is in points.
 *
 * Its own fetch, on PensSection's pattern: /api/review is a different
 * artifact with its own "nothing banked yet" state, and folding it into
 * /api/quality would let one missing file blank the other's card.
 *
 * A `no_advice` row carries `model_points: null` — the advice for that week
 * has been pruned, so there is no model squad to score. Those rows are
 * dropped rather than plotted at zero, and the card says how many weeks it is
 * actually drawing. Under two of them there is no scatter to draw and the
 * card says *that* instead of vanishing: an absent card reads as a missing
 * feature, where the truth is a season that has not been graded yet.
 */
function ScatterSection() {
  const [gws, setGws] = useState<ReviewData['gws'] | null>(null)

  useEffect(() => {
    apiGet<ReviewData>('/api/review')
      .then((body) => setGws(body.gws ?? []))
      .catch(() => setGws([]))
  }, [])

  if (gws === null) return null
  const points = gws
    .filter((r) => r.model_points !== null && r.my_points !== null)
    .map((r) => ({ gw: r.gw, model: r.model_points as number,
                   mine: r.my_points as number }))

  if (points.length < 2) {
    return (
      <Card title="Your points against the model’s" className="mt-4">
        <p className="text-text-muted">
          {points.length === 0
            ? 'No graded gameweek yet — review a finished week and this '
              + 'compares what you scored against what the model’s own '
              + 'squad would have.'
            : '1 graded gameweek so far. One point is an anecdote, not a '
              + 'scatter; the chart appears from the second graded week.'}
        </p>
      </Card>
    )
  }

  const top = Math.ceil(Math.max(
    ...points.map((p) => Math.max(p.model, p.mine)), 10) / 10) * 10

  return (
    <Card title="Your points against the model’s" className="mt-4">
      <p className="mb-3 text-text-muted">
        {'Each point is one graded gameweek. Both numbers are whole squads '
          + 'scored off the same results — yours net of hits, against yours '
          + 'with every comparable decision taken from the model instead. '
          + `${points.length} graded gameweeks. Above the dashed line your `
          + 'week beat the advice; below it the advice would have beaten you.'}
      </p>
      <div aria-label="your points against the model’s">
        <ResponsiveContainer width="100%" height={260}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--color-divider)" />
            <XAxis type="number" dataKey="model" name="model"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <YAxis type="number" dataKey="mine" name="yours"
                   domain={[0, top]} stroke="var(--color-text-muted)" />
            <ZAxis range={[60, 60]} />
            <Tooltip
              cursor={{ strokeDasharray: '3 3' }}
              contentStyle={{ background: 'var(--color-card)',
                              border: '1px solid var(--color-border)' }} />
            <ReferenceLine segment={[{ x: 0, y: 0 }, { x: top, y: top }]}
                           stroke="var(--color-text-muted)"
                           strokeDasharray="4 4" />
            <Scatter data={points} fill="var(--color-sage)" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

const MISS_COLUMNS: Column<MissRow>[] = [
  { key: 'name', header: 'Player', primary: true, value: (r) => r.name,
    render: (r) => (
      <span className="flex items-center gap-1.5">
        <PlayerName code={r.code} name={r.name} />
        <PosBadge pos={r.position} variant="dot" />
      </span>
    ) },
  { key: 'price', header: 'Price', numeric: true, value: (r) => r.price,
    render: (r) => fmtNum(r.price, 1) },
  { key: 'ep', header: 'Forecast', primary: true, numeric: true,
    value: (r) => r.ep, render: (r) => fmtNum(r.ep) },
  { key: 'actual', header: 'Scored', primary: true, numeric: true,
    value: (r) => r.actual, render: (r) => r.actual },
  { key: 'minutes', header: 'Mins', numeric: true, value: (r) => r.minutes,
    render: (r) => r.minutes },
  { key: 'miss', header: 'Miss', primary: true, numeric: true,
    value: (r) => Math.abs(r.miss),
    render: (r) => (
      <span className={r.miss >= 0 ? 'num text-sage' : 'num text-rust'}>
        {`${r.miss >= 0 ? '+' : ''}${r.miss.toFixed(1)}`}
      </span>
    ) },
]

/**
 * Who the model got most wrong last week.
 *
 * The aggregates above say the heads are calibrated in the mean, which is a
 * claim nobody can check against their own memory of the football. This is
 * the card a manager argues with, so it keeps both signs: an over-forecast is
 * a transfer the tool may have talked somebody into, an under-forecast is a
 * captaincy it talked them out of.
 */
function MissesSection() {
  const [data, setData] = useState<MissesData | null>(null)

  useEffect(() => {
    apiGet<MissesData>('/api/misses').then(setData).catch(() => setData(null))
  }, [])

  // No scored gameweek is an absent card, not a card of zeros — and a payload
  // without a rows array is not a misses report at all, so render nothing
  // rather than crash the tab on an artifact an older version half-wrote.
  if (!data?.gw || !Array.isArray(data.rows) || data.rows.length === 0) {
    return null
  }
  return (
    <Card title={`Biggest misses — GW${data.gw}`} className="mt-4">
      <p className="mb-3 text-text-muted">
        Forecast against what he actually scored, largest gap first. A positive
        miss is a player the model under-rated.
      </p>
      <DataTable
        columns={MISS_COLUMNS}
        rows={data.rows}
        rowKey={(r) => r.code}
        rowLabel={(r) => r.name}
        initialSort="miss"
        empty={<p className="text-text-muted">Nothing scored yet.</p>}
      />
    </Card>
  )
}

export default function QualityTab() {
  const [data, setData] = useState<QualityData | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<QualityData>('/api/quality').then(setData).catch((e: Error) => {
      // A 422 here is the ordinary "nothing has been evaluated yet" state,
      // not a failure: the server's own sentence says what to run.
      if (e instanceof ApiError && e.status === 422) setEmpty(e.message)
      else setError(e.message)
    })
  }, [])

  if (error) {
    return (
      <Card title="Quality unavailable">
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (empty) {
    return (
      <EmptyState
        title="Nothing evaluated yet"
        detail={empty}
        action="gaffer evaluate"
      />
    )
  }
  if (!data) return <Loading />

  return (
    <>
      {data.current && <CurrentSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
      <ScatterSection />
      <MissesSection />
      <PensSection />
    </>
  )
}
