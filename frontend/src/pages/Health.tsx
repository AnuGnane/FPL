import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { useJob } from '../api/useJob'
import type { HealthData } from '../types'

export default function Health() {
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

  if (error) return <p className="bad">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

  // A rejected submission (429 from a full queue) leaves the hook in `error`
  // with the server's own sentence, so the buttons re-enable and the page
  // says why nothing started instead of hanging on a job that never was.
  const busy = job.status === 'queued' || job.status === 'running'
  const run = (path: string) => { setPending(path); job.start(path) }
  const waiting = (path: string) => busy && pending === path
  return (
    <>
      <h2>Runs &amp; Health</h2>
      <div className="card">
        <button onClick={() => run('/api/data/refresh')}
          disabled={waiting('/api/data/refresh')}>
          Refresh data
        </button>{' '}
        <button onClick={() => run('/api/advice/rerun')}
          disabled={waiting('/api/advice/rerun')}>
          Re-run advice
        </button>
        {busy && <span className="muted"> job {job.status}…</span>}
        {job.status === 'error' && <p className="bad">{job.error}</p>}
      </div>
      <div className="card">
        <h2>Data freshness</h2>
        <table>
          <tbody>
            {data.data.map((source) => (
              <tr key={source.source}>
                <td>{source.source}</td>
                <td className="muted">{source.path}</td>
                <td>
                  {source.present
                    ? `${source.age_hours}h ago`
                    : <span className="bad">missing</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.odds_key_present && (
          <p className="muted">
            No odds key configured — add an odds key for market-implied
            numbers.
          </p>
        )}
      </div>
      <div className="card">
        <h2>Models</h2>
        <table>
          <tbody>
            {data.models.map((model) => (
              <tr key={model.name}>
                <td>{model.name}</td>
                <td>{model.saved_at}</td>
                <td className="muted">{JSON.stringify(model.metrics)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data.model_health && (
          <p className="muted">
            Last scored gameweek: {JSON.stringify(data.model_health)}
          </p>
        )}
      </div>
      <div className="card">
        <h2>Automation</h2>
        <p className="muted">{data.launchd.log}</p>
        {data.launchd.present
          ? <p>{data.launchd.last_line}</p>
          : <p className="muted">No launchd log yet.</p>}
      </div>
      <div className="card">
        <h2>Artifacts</h2>
        <table>
          <tbody>
            {data.artifacts.map((item) => (
              <tr key={item.name}>
                <td>{item.name}</td>
                <td className="muted">{item.bytes} bytes</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
