import { useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart as RLineChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { ApiError, apiGet } from '../../api/client'
import { Card, EmptyState } from '../../kit'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  NewsShadowData, QualityData, StratifiedTable,
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
    <table>
      <thead>
        <tr>
          <th>Category</th>
          {columns.map(([name]) => (
            <th key={name} colSpan={2}>{name}</th>
          ))}
        </tr>
        <tr>
          <th />
          {columns.map(([name]) => [
            <th key={`${name}-rmse`}>RMSE</th>,
            <th key={`${name}-mae`}>MAE</th>,
          ])}
        </tr>
      </thead>
      <tbody>
        {CATEGORIES.map(([key, label]) => (
          <tr key={key}>
            <td>{label}</td>
            {columns.map(([name, table]) => [
              <td key={`${name}-${key}-rmse`}>
                <span className="num">{table[key] === undefined ? '—' : table[key].rmse}</span>
              </td>,
              <td key={`${name}-${key}-mae`}>
                <span className="num">{table[key] === undefined ? '—' : table[key].mae}</span>
              </td>,
            ])}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
  const points = head.reliability
  return (
    <div>
      <p className="text-text-muted">
        {label} — log loss {head.log_loss ?? 'n/a'}
      </p>
      <div aria-label={`${label} reliability`}>
        <ResponsiveContainer width="100%" height={220}>
          <RLineChart data={points}>
            <CartesianGrid stroke="var(--color-divider)" vertical={false} />
            <XAxis dataKey="pred" stroke="var(--color-text-muted)" />
            <YAxis stroke="var(--color-text-muted)" />
            <Tooltip contentStyle={{ background: 'var(--color-card)',
                                     border: '1px solid var(--color-border)' }} />
            <Line type="monotone" dataKey="obs" dot={false}
                  stroke="var(--color-sage)" strokeWidth={2} />
          </RLineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function CurrentSection({ current }: { current: CurrentEvaluation }) {
  return (
    <>
      <Card title="Holdout" className="mb-4">
        <p className="text-text-muted">
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
      <p className="text-text-muted">{benchmark.caveat}</p>
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
      <table>
        <thead>
          <tr><th>Run</th><th>Total</th><th>Per GW</th><th>Hits</th></tr>
        </thead>
        <tbody>
          {CELLS.map(([key, label]) => {
            const cell = decomposition.cells[key]
            return cell === undefined ? null : (
              <tr key={key}>
                <td>{label}</td>
                <td><span className="num">{cell.total}</span></td>
                <td><span className="num">{cell.per_gw}</span></td>
                <td><span className="num">{cell.hits}</span></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <table>
        <tbody>
          <tr>
            <td>Forecast gap (3-week)</td>
            <td><span className="num">{decomposition.forecast_gap_h3}</span></td>
            <td className="text-text-muted">
              points better forecasting could still win
            </td>
          </tr>
          <tr>
            <td>Planning ceiling</td>
            <td><span className="num">{decomposition.planning_ceiling}</span></td>
            <td className="text-text-muted">
              the most multi-week planning can ever be worth
            </td>
          </tr>
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
    <span style={{ display: 'inline-flex', gap: 4, width: 120 }}>
      <span className="bar"
            style={{ width: `${(news / top) * 100}%`,
                     background: 'var(--color-sage)' }}
            aria-label={`news ${news}`} />
      <span className="bar"
            style={{ width: `${(flags / top) * 100}%`,
                     background: 'var(--color-text-muted)' }}
            aria-label={`flags ${flags}`} />
    </span>
  )
}

function NewsShadowSection({ shadow }: { shadow: NewsShadowData }) {
  return (
    <Card title="News layer">
      <p className="text-text-muted">{verdict(shadow)}</p>
      <table>
        <thead>
          <tr>
            <th>GW</th>
            <th>Brier news</th><th>Brier flags</th><th />
            <th>Minutes MAE news</th><th>MAE flags</th><th />
            <th>Rows</th>
          </tr>
        </thead>
        <tbody>
          {shadow.by_gw.map((row) => (
            <tr key={row.gw}>
              <td>GW{row.gw}</td>
              <td><span className="num">{row.brier_news}</span></td>
              <td><span className="num">{row.brier_flags}</span></td>
              <td>
                <PairedBar news={row.brier_news} flags={row.brier_flags} />
              </td>
              <td><span className="num">{row.mae_news}</span></td>
              <td><span className="num">{row.mae_flags}</span></td>
              <td>
                <PairedBar news={row.mae_news} flags={row.mae_flags} />
              </td>
              <td><span className="num">{row.rows}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
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

  if (error) return <p className="text-rust">{error}</p>
  if (empty) {
    return (
      <EmptyState
        title="Nothing evaluated yet"
        detail={empty}
        action="gaffer evaluate"
      />
    )
  }
  if (!data) return <p className="text-text-muted">Loading…</p>

  return (
    <>
      {data.current && <CurrentSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
    </>
  )
}
