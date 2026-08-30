import { useEffect, useState } from 'react'
import {
  CartesianGrid, Line, LineChart as RLineChart, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { ApiError, apiGet } from '../../api/client'
import { Card, EmptyState, Loading } from '../../kit'
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

function Reliability({ label, head }: { label: string; head: HeadMetrics }) {
  const points = head.reliability
  return (
    <div className="mb-3">
      <p className="label">
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
    </>
  )
}
