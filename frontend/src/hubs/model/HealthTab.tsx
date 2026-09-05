import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Callout, Card, Chip, EmptyState, Loading, TABLE_CLASS, THEAD_CLASS, TR_CLASS,
  tdClass, thClass, tone,
} from '../../kit'
import type { HealthData } from '../../types'

// No buttons here. This tab used to carry its own "Refresh data" and "Re-run
// advice" pair, posting to the legacy JobRegistry routes — a second lane past
// the single-flight runner, from which two full advise runs could write to
// reports/ at once. The Model hub's JobButtons are the one control, and the
// routes those buttons posted to are gone.
export default function HealthTab() {
  const [data, setData] = useState<HealthData | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    apiGet<HealthData>('/api/health').then(setData)
      .catch((e: Error) => setError(e.message))
  }
  useEffect(load, [])

  if (error) {
    return (
      <Card title="Health unavailable">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{error}</Callout>
      </Card>
    )
  }
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
              <th className={thClass()}>Source</th>
              <th className={thClass()}>Path</th>
              <th className={thClass(true)}>Age</th>
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
                  {source.present
                    ? <span className={`tn ${tone(source.age_hours)}`}>
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
                  <th className={thClass()}>Table</th>
                  <th className={thClass(true)}>Rows</th>
                  <th className={thClass(true)}>Latest</th>
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
              <th className={thClass()}>Model</th>
              <th className={thClass()}>Saved</th>
              <th className={thClass()}>Metrics</th>
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
        <p className="tn text-xs text-text-faint">{data.launchd.log}</p>
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
              <th className={thClass()}>Artifact</th>
              <th className={thClass(true)}>Bytes</th>
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
