import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, EmptyState, Loading } from '../../kit'
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
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (!data) return <Loading />

  return (
    <>
      {/* `=== false`, never `!data.season_ok`: null is "cannot tell" and a
          falsy check would paint this on every cold clone. */}
      {data.season_ok === false && (
        <div
          data-testid="season-mismatch"
          className="mb-4 rounded-card border border-rust bg-card px-4 py-3
                     text-rust"
        >
          <p className="font-semibold">Season mismatch</p>
          <p className="mt-1 text-text-secondary">
            {`The last refresh banked ${data.season_ingested}; config.toml says
              ${data.season_config}. Set [data] current_season to
              ${data.season_ingested} and append ${data.season_config} to
              train_seasons — both, together. Until then every row ingested
              carries the wrong season label and every model trained on them
              trains on the mixture.`}
          </p>
        </div>
      )}
      <Card title="Data freshness" className="mb-4">
        <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Source</th>
              <th className="label pb-1 text-left">Path</th>
              <th className="label pb-1 text-right">Age</th>
            </tr>
          </thead>
          <tbody>
            {data.data.map((source) => (
              <tr key={source.source} className="border-t border-divider">
                <td className="py-1.5 text-text">{source.source}</td>
                <td className="num py-1.5 text-xs text-text-faint">
                  {source.path}
                </td>
                <td className="py-1.5 text-right">
                  {source.present
                    ? <span className="num text-text-secondary">
                        {`${source.age_hours}h ago`}
                      </span>
                    : <span className="text-rust">missing</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        {data.solver_top_n && (
          <div className="mt-4" data-testid="solver-pool">
            <p className="label">Solver pool</p>
            <p className="mt-1 text-text-secondary">
              players per position the solver may consider, on top of the ones
              you own
            </p>
            <p className="num mt-1 text-text">
              {Object.entries(data.solver_top_n)
                .map(([pos, n]) => `${pos} ${n}`).join('  ·  ')}
            </p>
          </div>
        )}
        {!data.odds_key_present && (
          <p className="mt-3 text-text-muted">
            No odds key configured — add an odds key for market-implied
            numbers.
          </p>
        )}
      </Card>
      <Card title="Models" className="mb-4">
        <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Model</th>
              <th className="label pb-1 text-left">Saved</th>
              <th className="label pb-1 text-left">Metrics</th>
            </tr>
          </thead>
          <tbody>
            {data.models.map((model) => (
              <tr key={model.name} className="border-t border-divider">
                <td className="py-1.5 text-text">{model.name}</td>
                <td className="num py-1.5 text-text-secondary">
                  {model.saved_at}
                </td>
                <td className="num py-1.5 text-xs text-text-faint">
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
            <span className="num text-xs text-text-faint">
              {JSON.stringify(data.model_health)}
            </span>
          </p>
        )}
      </Card>
      <Card title="Automation" className="mb-4">
        <p className="num text-xs text-text-faint">{data.launchd.log}</p>
        {data.launchd.present
          ? (
            <p className="num mt-2 overflow-x-auto rounded-card border
                          border-border bg-base px-2 py-1 text-text-secondary">
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
        <table className="w-full">
          <thead>
            <tr>
              <th className="label pb-1 text-left">Artifact</th>
              <th className="label pb-1 text-right">Bytes</th>
            </tr>
          </thead>
          <tbody>
            {data.artifacts.map((item) => (
              <tr key={item.name} className="border-t border-divider">
                <td className="py-1.5 text-text">{item.name}</td>
                <td className="num py-1.5 text-right text-text-secondary">
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
