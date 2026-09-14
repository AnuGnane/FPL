import { usePageData } from '../../api/pageData'
import {
  Bar, Callout, Card, EmptyState, Loading, TABLE_CLASS, THEAD_CLASS, TR_CLASS,
  fmtNum, tdClass, thClass,
} from '../../kit'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, FlagLatencyData,
  NewsShadowData, NewsShadowSummary, PresserGradesData, QualityData,
  StratifiedTable,
} from '../../types'
import CalibrationSection from './quality/CalibrationSection'
import MissesSection from './quality/MissesSection'
import PensSection from './quality/PensSection'
import ScatterSection from './quality/ScatterSection'
import { Reliability } from './quality/shared'

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
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>Category</th>
            {columns.map(([name]) => (
              <th scope="col" key={name} colSpan={2}
                  className={`${thClass()} border-l border-divider
                              text-center`}>
                {name}
              </th>
            ))}
          </tr>
          <tr>
            <th scope="col" />
            {columns.map(([name]) => [
              <th scope="col" key={`${name}-rmse`}
                  className={`${thClass(true)} border-l border-divider`}>
                RMSE
              </th>,
              <th scope="col" key={`${name}-mae`} className={thClass(true)}>
                MAE
              </th>,
            ])}
          </tr>
        </thead>
        <tbody>
          {CATEGORIES.map(([key, label]) => (
            <tr key={key} className={TR_CLASS}>
              <td className={`${tdClass()} text-text`}>{label}</td>
              {columns.map(([name, table]) => [
                <td key={`${name}-${key}-rmse`}
                    className={`${tdClass(true)} border-l border-divider
                                text-text`}>
                  {table[key] === undefined ? '—' : table[key].rmse}
                </td>,
                <td key={`${name}-${key}-mae`}
                    className={`${tdClass(true)} text-text-secondary`}>
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
        {/* Named apart from "Calibration by gameweek" below, which grades the
            probabilities the weekly run actually served. This one is the
            holdout. */}
        <p className="mb-3 text-text-muted">
          From the holdout run above, not the weeks actually served.
        </p>
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
      <div className="overflow-x-auto">
      <table className={TABLE_CLASS}>
        <thead className={THEAD_CLASS}>
          <tr>
            <th scope="col" className={thClass()}>Run</th>
            <th scope="col" className={thClass(true)}>Total</th>
            <th scope="col" className={thClass(true)}>Per GW</th>
            <th scope="col" className={thClass(true)}>Hits</th>
          </tr>
        </thead>
        <tbody>
          {CELLS.map(([key, label]) => {
            const cell = decomposition.cells[key]
            return cell === undefined ? null : (
              <tr key={key} className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{label}</td>
                <td className={`${tdClass(true)} text-text`}>
                  {cell.total}
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {cell.per_gw}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {cell.hits}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      </div>
      <div className="overflow-x-auto">
      <table className={`mt-4 ${TABLE_CLASS}`}>
        <tbody>
          {([
            ['Forecast gap (3-week)', decomposition.forecast_gap_h3,
             'points better forecasting could still win'],
            ['Planning ceiling', decomposition.planning_ceiling,
             'the most multi-week planning can ever be worth'],
          ] as const).map(([label, value, note]) => (
            <tr key={label} className={TR_CLASS}>
              <td className={`${tdClass()} text-text`}>{label}</td>
              <td className={`${tdClass(true)} text-text`}>{value}</td>
              <td className={`${tdClass()} text-text-muted`}>{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </Card>
  )
}

// Lower is better for both metrics, so "ahead" means a smaller number. Said
// in a sentence as well as drawn, because a pair of bars two hundredths apart
// is not a verdict anyone should have to squint at.
function verdict(shadow: NewsShadowData): string {
  // `overall` is `NewsShadowSummary | dict` on the server (`schemas.py:1156`):
  // an empty object until a gameweek has been scored, a full summary after.
  // Read the two numbers by type rather than by presence — the empty case is
  // `{}`, so `=== undefined` and `?? 0` both walk straight into it.
  const o = shadow.overall as Partial<NewsShadowSummary>
  if (typeof o.brier_news !== 'number' || typeof o.mae_news !== 'number') {
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
  // Both grey: the pair compares two instruments measuring the same thing,
  // and neither of them is a direction the reader is ahead or behind on.
  return (
    <span className="inline-flex flex-col gap-0.5 align-middle">
      <Bar fraction={news / top} width={112} testId="paired-news"
           aria-label={`news ${news}`} />
      <Bar fraction={flags / top} width={112} testId="paired-flags"
           aria-label={`flags ${flags}`} />
    </span>
  )
}

function NewsShadowSection({ shadow }: { shadow: NewsShadowData }) {
  return (
    <Card title="News layer">
      {/* Information, not a warning (plan R5): grey bar, raised surface. */}
      <Callout className="mb-3">{verdict(shadow)}</Callout>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>GW</th>
              <th scope="col" className={thClass(true)}>Brier news</th>
              <th scope="col" className={thClass(true)}>Brier flags</th>
              <th scope="col" />
              <th scope="col" className={thClass(true)}>Minutes MAE news</th>
              <th scope="col" className={thClass(true)}>MAE flags</th>
              <th scope="col" />
              <th scope="col" className={thClass(true)}>Rows</th>
            </tr>
          </thead>
          <tbody>
            {shadow.by_gw.map((row) => (
              <tr key={row.gw} className={TR_CLASS}>
                <td className={`${tdClass()} tn text-text`}>GW{row.gw}</td>
                {/* News against flags is two instruments, not better against
                    worse: the verdict sentence above says which is ahead. */}
                <td className={`${tdClass(true)} text-text`}>
                  {row.brier_news}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {row.brier_flags}
                </td>
                <td className={tdClass()}>
                  <PairedBar news={row.brier_news} flags={row.brier_flags} />
                </td>
                <td className={`${tdClass(true)} text-text`}>
                  {row.mae_news}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {row.mae_flags}
                </td>
                <td className={tdClass()}>
                  <PairedBar news={row.mae_news} flags={row.mae_flags} />
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
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

// The bar is scaled to the largest bucket in *this* histogram, the way
// PairedBar scales to its own row: lead times are counts and a shared axis
// across a fortnight of snapshots would draw every early bucket as nothing.
function LeadBar({ started, missed, top }:
                 { started: number; missed: number; top: number }) {
  return (
    // Both grey, like the news pair above: started and did not start are
    // two counts of one histogram, not a direction the reader is on.
    <span className="inline-flex flex-col gap-0.5 align-middle">
      <Bar fraction={started / top} width={128} testId="lead-started"
           aria-label={`started ${started}`} />
      <Bar fraction={missed / top} width={128} testId="lead-missed"
           aria-label={`did not start ${missed}`} />
    </span>
  )
}

function FlagLatencySection({ data }: { data: FlagLatencyData }) {
  // Two gates, one empty state. `available` is the server's fourteen-day
  // rule; `rows === 0` is an open gate over a fortnight in which nothing
  // moved. Either way the tables would be a row of zeroes that reads as a
  // measurement, and spec §1 wants a sentence instead — the server's own
  // where there is one, so the CLI and the page cannot drift apart on it.
  if (!data.available || data.rows === 0) {
    return (
      <p data-testid="flag-latency-empty" className="text-text-muted">
        {data.note
          ?? `No status changed before a deadline in ${data.snap_dates} `
             + 'snapshot days of graded gameweeks.'}
      </p>
    )
  }
  const top = Math.max(
    1, ...data.histogram.map((b) => Math.max(b.started, b.missed)))
  return (
    <>
      <p className="mb-2 text-text-secondary">
        {data.rows}
        {' status changes over '}
        {data.snap_dates}
        {' snapshot days, in gameweeks '}
        {data.checked_covered_gws.join(', ')}
        {'.'}
      </p>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Warning</th>
              <th scope="col" className={thClass(true)}>Started</th>
              <th scope="col" className={thClass(true)}>Did not</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {data.histogram.map((b) => (
              <tr key={b.bucket} data-testid={`lead-bucket-${b.bucket}`}
                  className={TR_CLASS}>
                <td className={`${tdClass()} tn text-text`}>{b.bucket}</td>
                <td className={`${tdClass(true)} text-text`}>
                  {b.started}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {b.missed}
                </td>
                <td className={tdClass()}>
                  <LeadBar started={b.started} missed={b.missed} top={top} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.late_flags.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <p className="label mb-1">
            Latest flags whose final status disagreed with the start
          </p>
          <table className={TABLE_CLASS}>
            <tbody>
              {data.late_flags.map((f) => (
                <tr key={`${f.gw}-${f.code}`}
                    data-testid={`late-flag-${f.gw}-${f.code}`}
                    className={TR_CLASS}>
                  <td className={`${tdClass()} tn text-text`}>{`GW${f.gw}`}</td>
                  <td className={`${tdClass()} tn text-text-secondary`}>
                    {`code ${f.code}`}
                  </td>
                  <td className={tdClass(true)}>
                    {`${fmtNum(f.lead_days, 0)}d`}
                  </td>
                  <td className={`${tdClass()} text-text-muted`}>
                    {`${f.from_status} → ${f.final_status}`}
                  </td>
                  <td className={tdClass(true)}>
                    {f.started ? 'started' : 'did not start'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

function PresserGradesSection({ data }: { data: PresserGradesData }) {
  if (!data.available || data.rows === 0) {
    return (
      <p data-testid="presser-grades-empty" className="mt-3 text-text-muted">
        {data.note ?? 'No verdict has been graded yet.'}
      </p>
    )
  }
  const conf = new Map(data.confusion.map((c) => [c.verdict, c]))
  return (
    <div className="mt-4">
      <p className="label mb-1">Presser verdicts</p>
      <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Verdict</th>
              <th scope="col" className={thClass(true)}>Graded</th>
              <th scope="col" className={thClass(true)}>Started</th>
              <th scope="col" className={thClass(true)}>Absent</th>
              <th scope="col" className={thClass(true)}>Precision</th>
              <th scope="col" className={thClass(true)}>Recall</th>
            </tr>
          </thead>
          <tbody>
            {data.per_class.map((row) => (
              <tr key={row.verdict} data-testid={`verdict-${row.verdict}`}
                  className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{row.verdict}</td>
                <td className={tdClass(true)}>{row.n}</td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {conf.get(row.verdict)?.started ?? 0}
                </td>
                <td className={`${tdClass(true)} text-text-muted`}>
                  {conf.get(row.verdict)?.not_started ?? 0}
                </td>
                {/* A precision is a measurement, not a direction (rule 1). */}
                <td className={`${tdClass(true)} text-text`}>
                  {fmtNum(row.precision, 2)}
                </td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {/* The denominator is the gameweek's absences. With none,
                      the payload stores 0 and this prints a dash: 0.00 beside
                      a class that found none of nothing reads as a class that
                      missed everything. */}
                  {data.absent_rows > 0 ? fmtNum(row.recall, 2) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p data-testid="presser-recall-note"
         className="mt-1 text-xs text-text-faint">
        {'Precision is P(did not start | verdict). Recall is over '}
        {data.recall_population}
        {` — ${data.absent_rows} absences among ${data.rows} graded `}
        {'verdicts, not every absence in the gameweek.'}
      </p>
    </div>
  )
}

function AvailabilitySection({ flag, presser }:
                             { flag: FlagLatencyData | null
                               presser: PresserGradesData | null }) {
  return (
    <Card title="Availability signal" className="mt-4">
      {flag && <FlagLatencySection data={flag} />}
      {presser && <PresserGradesSection data={presser} />}
    </Card>
  )
}

export default function QualityTab() {
  // v18e §2.3. Four sections below keep their own reads, each where it lives;
  // this one is the tab's own. The status split it made by hand — a 422 is
  // "nothing has been evaluated yet" and the server's own sentence says what
  // to run — is `Loaded`'s, spelt in its words.
  const page = usePageData<QualityData>('/api/quality')
  const absent = page.status === 404 || page.status === 422

  if (page.error !== null && !absent) {
    return (
      <Card title="Quality unavailable">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  if (page.error !== null) {
    return (
      <EmptyState
        title="Nothing evaluated yet"
        detail={page.error}
        action="gaffer evaluate"
      />
    )
  }
  const data = page.data
  if (!data) return <Loading />

  return (
    <>
      {data.current && <CurrentSection current={data.current} />}
      {data.benchmark && <BenchmarkSection benchmark={data.benchmark} />}
      {data.decomposition
        && <DecompositionSection decomposition={data.decomposition} />}
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
      {/* A9: deliberately not the news-shadow rule above. The card renders
          whenever either key is present, empty report included, because spec
          §1 wants the page to say what it is waiting for. `rows > 0` gates
          the tables inside it, not the card. */}
      {(data.flag_latency || data.presser_grades)
        && <AvailabilitySection flag={data.flag_latency ?? null}
                                presser={data.presser_grades ?? null} />}
      <CalibrationSection />
      <ScatterSection />
      <MissesSection />
      <PensSection />
    </>
  )
}
