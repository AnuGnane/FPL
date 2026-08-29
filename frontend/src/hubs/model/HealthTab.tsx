import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, EmptyState } from '../../kit'
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

  if (error) return <p className="text-rust">{error}</p>
  if (!data) return <p className="text-text-muted">Loading…</p>

  return (
    <>
      <Card title="Data freshness" className="mb-4">
        <table>
          <tbody>
            {data.data.map((source) => (
              <tr key={source.source}>
                <td>{source.source}</td>
                <td className="text-text-muted">{source.path}</td>
                <td>
                  {source.present
                    ? <span className="num">{`${source.age_hours}h ago`}</span>
                    : <span className="text-rust">missing</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.odds_key_present && (
          <p className="text-text-muted">
            No odds key configured — add an odds key for market-implied
            numbers.
          </p>
        )}
      </Card>
      <Card title="Models" className="mb-4">
        <table>
          <tbody>
            {data.models.map((model) => (
              <tr key={model.name}>
                <td>{model.name}</td>
                <td>{model.saved_at}</td>
                <td className="text-text-muted">
                  {JSON.stringify(model.metrics)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.model_health && (
          <p className="text-text-muted">
            Last scored gameweek: {JSON.stringify(data.model_health)}
          </p>
        )}
      </Card>
      <Card title="Automation" className="mb-4">
        <p className="text-text-muted">{data.launchd.log}</p>
        {data.launchd.present
          ? <p>{data.launchd.last_line}</p>
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
        <table>
          <tbody>
            {data.artifacts.map((item) => (
              <tr key={item.name}>
                <td>{item.name}</td>
                <td className="text-text-muted">
                  <span className="num">{item.bytes}</span> bytes
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}
