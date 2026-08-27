import { useEffect, useState } from 'react'
import { ApiError, apiGet } from '../api/client'
import LineChart from '../components/LineChart'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  NewsShadowData, QualityData, StratifiedTable,
} from '../types'

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
                {table[key] === undefined ? '—' : table[key].rmse}
              </td>,
              <td key={`${name}-${key}-mae`}>
                {table[key] === undefined ? '—' : table[key].mae}
              </td>,
            ])}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
  return (
    <div>
      <p className="muted">
        {label} — log loss {head.log_loss ?? 'n/a'}
      </p>
      <LineChart
        label={`${label} reliability`}
        series={[
          {
            name: 'observed',
            colour: '#4ade80',
            points: head.reliability.map((bin) => ({
              x: bin.pred, y: bin.obs,
            })),
          },
          // The diagonal a perfectly calibrated head would sit on.
          {
            name: 'perfect',
            colour: '#60a5fa',
            points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
          },
        ]}
      />
    </div>
  )
}

function CurrentSection({ current }: { current: CurrentEvaluation }) {
  return (
    <>
      <div className="card">
        <h2>Holdout</h2>
        <p className="muted">
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
      </div>
      <div className="card">
        <h2>Calibration</h2>
        {HEADS.map(([key, label]) => {
          const head = current.heads[key]
          return head === undefined ? null
            : <Reliability key={key} label={label} head={head} />
        })}
      </div>
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
    <div className="card">
      <h2>Benchmark — {benchmark.test_season}</h2>
      <StratifiedTableView
        columns={[['Ours', benchmark.stratified.all ?? {}], ...references]}
      />
      <p className="muted">{benchmark.caveat}</p>
    </div>
  )
}

function DecompositionSection(
  { decomposition }: { decomposition: DecompositionData },
) {
  return (
    <div className="card">
      <h2>Decomposition — {decomposition.season} from GW
        {decomposition.start_gw}</h2>
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
                <td>{cell.total}</td>
                <td>{cell.per_gw}</td>
                <td>{cell.hits}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <table>
        <tbody>
          <tr>
            <td>Forecast gap (3-week)</td>
            <td>{decomposition.forecast_gap_h3}</td>
            <td className="muted">
              points better forecasting could still win
            </td>
          </tr>
          <tr>
            <td>Planning ceiling</td>
            <td>{decomposition.planning_ceiling}</td>
            <td className="muted">
              the most multi-week planning can ever be worth
            </td>
          </tr>
        </tbody>
      </table>
    </div>
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
                     background: 'var(--pitch-300)' }}
            aria-label={`news ${news}`} />
      <span className="bar"
            style={{ width: `${(flags / top) * 100}%`,
                     background: 'var(--chalk-dim)' }}
            aria-label={`flags ${flags}`} />
    </span>
  )
}

function NewsShadowSection({ shadow }: { shadow: NewsShadowData }) {
  return (
    <div className="card">
      <h2>News layer</h2>
      <p className="muted">{verdict(shadow)}</p>
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
              <td>{row.brier_news}</td>
              <td>{row.brier_flags}</td>
              <td>
                <PairedBar news={row.brier_news} flags={row.brier_flags} />
              </td>
              <td>{row.mae_news}</td>
              <td>{row.mae_flags}</td>
              <td>
                <PairedBar news={row.mae_news} flags={row.mae_flags} />
              </td>
              <td>{row.rows}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Quality() {
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

  if (error) return <p className="bad">{error}</p>
  if (empty) {
    return (
      <>
        <h2>Model Quality</h2>
        <div className="card"><p className="muted">{empty}</p></div>
      </>
    )
  }
  if (!data) return <p className="muted">Loading…</p>

  return (
    <>
      <h2>Model Quality</h2>
      {data.current && <CurrentSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
    </>
  )
}
