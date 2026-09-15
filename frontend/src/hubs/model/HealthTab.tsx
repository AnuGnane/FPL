import { usePageData } from '../../api/pageData'
import {
  type Column, Callout, Card, Chip, DataTable, EmptyState, Loading,
  TABLE_CLASS, THEAD_CLASS, TR_CLASS, ageText, tdClass, thClass, tone,
} from '../../kit'
import type { HealthData, JobHealth } from '../../types'

/**
 * Every installed plist and whether it has run lately (v19a §2.3).
 *
 * A job that has quietly stopped is invisible everywhere else in the app: the
 * artifacts it writes simply age, and the freshness strip says a *file* is
 * old without saying which timer stopped writing it. Last run is the log's
 * mtime, so the stamp goes in the title — a reader chasing a stopped job
 * wants the exact minute, and "3d" in the cell is what they are scanning for.
 */
const JOB_COLUMNS: Column<JobHealth>[] = [
  { key: 'label', header: 'Job', primary: true, value: (job) => job.label },
  { key: 'schedule', header: 'Schedule', primary: true,
    value: (job) => job.schedule },
  { key: 'last_run', header: 'Last run', primary: true,
    value: (job) => ageText(job.age_hours),
    render: (job) => (
      <span className="tn" title={job.modified_at ?? 'never run'}>
        {ageText(job.age_hours)}
      </span>
    ) },
  { key: 'status', header: 'Status',
    value: (job) => (job.overdue ? 'overdue' : 'ok'),
    // The word, not only the colour: `down` ink alone says "something here"
    // to a reader who can see it and nothing at all to one who cannot.
    render: (job) => (
      <span className={job.overdue ? 'text-down' : 'text-text-muted'}>
        {job.overdue ? 'overdue' : 'ok'}
      </span>
    ) },
]

// No buttons here. This tab used to carry its own "Refresh data" and "Re-run
// advice" pair, posting to the legacy JobRegistry routes — a second lane past
// the single-flight runner, from which two full advise runs could write to
// reports/ at once. The Model hub's JobButtons are the one control, and the
// routes those buttons posted to are gone.
export default function HealthTab() {
  // v18e §2.3. The hub used to remount this tab on a nonce to refresh it
  // after a job; the job now clears this URL instead, and the entry the hook
  // holds is what every reader of it sees.
  const page = usePageData<HealthData>('/api/health')

  if (page.error !== null) {
    return (
      <Card title="Health unavailable">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  const data = page.data
  if (!data) return <Loading />

  return (
    <>
      {/* `=== false`, never `!data.season_ok`: null is "cannot tell" and a
          falsy check would paint this on every cold clone. */}
      {data.season_ok === false && (
        <Callout tone="error" className="mb-4" data-testid="season-mismatch">
          <p className="font-semibold">Season mismatch</p>
          <p className="mt-1 text-text-secondary">
            The last refresh banked {data.season_ingested}; config.toml says{' '}
            {data.season_config}. Set <span className="tn">[data]
            current_season</span> to {data.season_ingested} and append{' '}
            {data.season_config} to <span className="tn">train_seasons</span>{' '}
            — both, together. Until then every row ingested carries the wrong
            season label and every model trained on them trains on the mixture.
          </p>
        </Callout>
      )}
      <Card title="Data freshness" className="mb-4">
        <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Source</th>
              <th scope="col" className={thClass()}>Path</th>
              <th scope="col" className={thClass(true)}>Age</th>
            </tr>
          </thead>
          <tbody>
            {data.data.map((source) => (
              <tr key={source.source} className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{source.source}</td>
                <td className={`${tdClass()} tn text-xs text-text-faint`}>
                  {source.path}
                </td>
                <td className={tdClass(true)}>
                  {/* The strip's own three ages (plan R2), so one feed does
                      not read as stale here and fresh in the header. A
                      source nobody has fetched is doubt, not a failure. */}
                  {/* A day, explicitly, since v19a §2.2 gave `tone` a
                      cadence: these are the ingested files, every one of them
                      written by a job that runs at least nightly, and the
                      row carries no cadence of its own to read. */}
                  {source.present
                    ? <span className={`tn ${tone(source.age_hours, 24)}`}>
                        {`${source.age_hours}h ago`}
                      </span>
                    : <Chip tone="warn">missing</Chip>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {/* v12 W1 §2.1. In this card rather than its own, because a backup is
            a freshness fact — it has an mtime and it goes stale. `never` is
            spelled out with the command that fixes it: a blank cell reads as
            "not applicable" and this always applies. */}
        <p className="mt-3 text-text-secondary" data-testid="last-backup">
          <span className="label">last backup: </span>
          {data.last_backup
            ? <span className="tn">
                {/* The stamp is served as UTC ISO-8601 and sliced rather
                    than parsed, so the zone has to be said out loud: a
                    23:45 nightly job rendered as a bare "23:45" reads as
                    local time to everyone west of Greenwich, and the
                    backup looks eight hours older or newer than it is. */}
                {data.last_backup.modified_at.slice(0, 16).replace('T', ' ')}
                {' UTC'}
                {' '}({(data.last_backup.bytes / 1e6).toFixed(1)} MB)
              </span>
            : <span className="text-text-muted">
                never — run <span className="tn">gaffer backup</span>
              </span>}
        </p>
        {!data.odds_key_present && (
          <p className="mt-3 text-text-muted">
            No odds key configured — add an odds key for market-implied
            numbers.
          </p>
        )}
      </Card>
      {/* v12 W4 §5.1. The collector is opt-in, so a clone that has never run
          it says what it is waiting for. Three zeros would read as a
          measurement of an archive that had nothing in it. */}
      <Card title="Core insights" className="mb-4">
        {data.core_insights == null || !data.core_insights.collected ? (
          <p className="text-text-muted">
            Not collected yet ({data.core_insights?.season ?? '—'}). Waiting
            for {data.core_insights?.waiting_for ?? 'a collector run'}.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className={TABLE_CLASS}>
              <thead className={THEAD_CLASS}>
                <tr>
                  <th scope="col" className={thClass()}>Table</th>
                  <th scope="col" className={thClass(true)}>Rows</th>
                  <th scope="col" className={thClass(true)}>Latest</th>
                </tr>
              </thead>
              <tbody>
                {data.core_insights.tables.map((t) => (
                  <tr key={t.table} className={TR_CLASS}>
                    <td className={`${tdClass()} text-text`}>{t.table}</td>
                    <td className={tdClass(true)}>{t.rows}</td>
                    <td className={`${tdClass(true)} text-text-muted`}>
                      {t.rows === 0
                        ? 'the archive publishes none yet'
                        : (t.latest ?? '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {/* Its own card: these are config, not freshness. Nothing here has an
          mtime, and sitting it under a table of file ages invited the reading
          that the pool sizes were stale. */}
      {data.solver_top_n && (
        <Card title="Solver pool" className="mb-4">
          <div data-testid="solver-pool">
            <p className="text-text-secondary">
              players per position the solver may consider, on top of the ones
              you own
            </p>
            <p className="tn mt-1 text-text">
              {Object.entries(data.solver_top_n)
                .map(([pos, n]) => `${pos} ${n}`).join('  ·  ')}
            </p>
          </div>
        </Card>
      )}
      <Card title="Models" className="mb-4">
        <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Model</th>
              <th scope="col" className={thClass()}>Saved</th>
              <th scope="col" className={thClass()}>Metrics</th>
            </tr>
          </thead>
          <tbody>
            {data.models.map((model) => (
              <tr key={model.name} className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{model.name}</td>
                <td className={`${tdClass()} tn text-text-secondary`}>
                  {model.saved_at}
                </td>
                <td className={`${tdClass()} tn text-xs text-text-faint`}>
                  {JSON.stringify(model.metrics)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {data.model_health && (
          <p className="mt-3">
            <span className="label">Last scored gameweek</span>{' '}
            <span className="tn text-xs text-text-faint">
              {JSON.stringify(data.model_health)}
            </span>
          </p>
        )}
      </Card>
      <Card title="Automation" className="mb-4">
        {/* `?? []` because the field arrived in v19a: a server or a fixture
            older than this cycle carries no jobs at all, and the table's own
            sentence is the honest answer to both that and a machine with no
            plists installed. */}
        <DataTable
          columns={JOB_COLUMNS}
          rows={data.jobs ?? []}
          rowKey={(job) => job.label}
          rowLabel={(job) => job.label}
          empty={(
            <p className="text-text-muted">
              No launchd jobs were found — nothing in scripts/ is installed on
              a timer, so every run here is one somebody started by hand.
            </p>
          )}
        />
        <p className="tn mt-3 text-xs text-text-faint">{data.launchd.log}</p>
        {data.launchd.present
          ? (
            /* No box (§5): one hairline down the left says "a log line". */
            <p className="tn mt-2 overflow-x-auto border-l-2 border-border
                          pl-3 text-text-secondary">
              {data.launchd.last_line}
            </p>
            )
          : (
            <EmptyState
              title="No launchd log yet"
              detail="The scheduled run writes this log the first time it
                      fires; nothing has run on a timer yet."
              action="Refresh data"
            />
            )}
      </Card>
      <Card title="Artifacts">
        <div className="overflow-x-auto">
        <table className={TABLE_CLASS}>
          <thead className={THEAD_CLASS}>
            <tr>
              <th scope="col" className={thClass()}>Artifact</th>
              <th scope="col" className={thClass(true)}>Bytes</th>
            </tr>
          </thead>
          <tbody>
            {data.artifacts.map((item) => (
              <tr key={item.name} className={TR_CLASS}>
                <td className={`${tdClass()} text-text`}>{item.name}</td>
                <td className={`${tdClass(true)} text-text-secondary`}>
                  {item.bytes}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </Card>
    </>
  )
}
