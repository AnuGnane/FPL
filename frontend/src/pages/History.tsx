import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import LineChart from '../components/LineChart'
import type { HistoryData } from '../types'

const COLOURS = ['#4ade80', '#f0b429', '#60a5fa', '#e5534b', '#c084fc']

export default function History() {
  const [data, setData] = useState<HistoryData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<HistoryData>('/api/history').then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <p className="bad">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

  return (
    <>
      <h2>History</h2>
      <div className="card">
        <h2>Past runs</h2>
        <table>
          <thead>
            <tr>
              <th>GW</th><th>Captain</th><th>In</th><th>Out</th><th>Hits</th>
              <th>Expected</th><th>Actual</th>
            </tr>
          </thead>
          <tbody>
            {data.runs.map((run) => (
              <tr key={run.gw}>
                <td>{run.gw}</td>
                <td>{run.captain}</td>
                <td>{run.buys.join(', ') || '—'}</td>
                <td>{run.sells.join(', ') || '—'}</td>
                <td>{run.hits}</td>
                <td>{run.expected_pts}</td>
                <td>
                  {run.actual_pts === null
                    ? <span className="muted">not resolved yet</span>
                    : run.actual_pts}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Price history</h2>
        <LineChart
          label="Price history"
          series={data.prices.map((series, index) => ({
            name: series.name,
            colour: COLOURS[index % COLOURS.length],
            points: series.points.map((point) => ({
              x: point.gw, y: point.price,
            })),
          }))}
        />
      </div>
      <div className="card">
        <h2>Backtests</h2>
        {data.backtests.length === 0
          ? <p className="muted">No backtest log on disk.</p>
          : (
            <ul>
              {data.backtests.map((row, index) => (
                <li key={index}>{JSON.stringify(row)}</li>
              ))}
            </ul>
          )}
      </div>
    </>
  )
}
