import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Card, EmptyState } from '../../kit'
import type { HealthData } from '../../types'

export default function HealthTab() {
  const [data, setData] = useState<HealthData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const job = useJob()
  // Which button is waiting: the queue happily takes a refresh and a re-run
  // back to back, so only the button whose job is in flight goes grey.
  const [pending, setPending] = useState<string | null>(null)

  const load = () => {
    apiGet<HealthData>('/api/health').then(setData)
      .catch((e: Error) => setError(e.message))
  }
  useEffect(load, [])
  useEffect(() => { if (job.status === 'done') load() }, [job.status])

  if (error) return <p className="text-rust">{error}</p>
  if (!data) return <p className="text-text-muted">Loading…</p>

  // A rejected submission (429 from a full queue) leaves the hook in `error`
  // with the server's own sentence, so the buttons re-enable and the page
  // says why nothing started instead of hanging on a job that never was.
  const busy = job.status === 'queued' || job.status === 'running'
  const run = (path: string) => { setPending(path); job.start(path) }
  const waiting = (path: string) => busy && pending === path
  return (
    <>
      <Card className="mb-4">
        <button onClick={() => run('/api/data/refresh')}
          disabled={waiting('/api/data/refresh')}>
          Refresh data
        </button>{' '}
        <button onClick={() => run('/api/advice/rerun')}
          disabled={waiting('/api/advice/rerun')}>
          Re-run advice
        </button>
        {busy && <span className="text-text-muted"> job {job.status}…</span>}
        {job.status === 'error' && <p className="text-rust">{job.error}</p>}
      </Card>
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
