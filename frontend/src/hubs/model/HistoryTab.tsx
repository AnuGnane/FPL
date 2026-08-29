import { useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart as RLineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import { Card, EmptyState } from '../../kit'
import type { HistoryData } from '../../types'

const COLOURS = ['var(--color-sage)', 'var(--color-info)', 'var(--color-rust)',
  'var(--color-text-muted)', 'var(--color-text-faint)']

/** Recharts wants one row per x with a column per series. */
function priceRows(prices: HistoryData['prices']): Array<Record<string, number>> {
  const byGw = new Map<number, Record<string, number>>()
  for (const series of prices) {
    for (const point of series.points) {
      const row = byGw.get(point.gw) ?? { gw: point.gw }
      row[series.name] = point.price
      byGw.set(point.gw, row)
    }
  }
  return [...byGw.values()].sort((a, b) => a.gw - b.gw)
}

export default function HistoryTab() {
  const [data, setData] = useState<HistoryData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    apiGet<HistoryData>('/api/history').then(setData)
      .catch((e: Error) => setError(e.message))
  }, [])

  if (error) return <p className="text-rust">{error}</p>
  if (!data) return <p className="text-text-muted">Loading…</p>

  const rows = priceRows(data.prices)

  return (
    <>
      <Card title="Past runs" className="mb-4">
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
                <td><span className="num">{run.gw}</span></td>
                <td>{run.captain}</td>
                <td>{run.buys.join(', ') || '—'}</td>
                <td>{run.sells.join(', ') || '—'}</td>
                <td><span className="num">{run.hits}</span></td>
                <td><span className="num">{run.expected_pts}</span></td>
                <td>
                  {run.actual_pts === null
                    ? <span className="text-text-muted">not resolved yet</span>
                    : <span className="num">{run.actual_pts}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Price history" className="mb-4">
        <div aria-label="Price history">
          <ResponsiveContainer width="100%" height={220}>
            <RLineChart data={rows}>
              <CartesianGrid stroke="var(--color-divider)" vertical={false} />
              <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
              <YAxis stroke="var(--color-text-muted)" />
              <Tooltip contentStyle={{ background: 'var(--color-card)',
                                       border: '1px solid var(--color-border)' }} />
              <Legend />
              {data.prices.map((series, index) => (
                <Line key={series.code} type="monotone" dataKey={series.name}
                      dot={false} strokeWidth={2}
                      stroke={COLOURS[index % COLOURS.length]} />
              ))}
            </RLineChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <Card title="Backtests">
        {data.backtests.length === 0
          ? (
            <EmptyState
              title="No backtest log on disk"
              detail="Backtests are written when a run is banked, so the log
                      fills up as the season goes."
              action="Run advise"
            />
            )
          : (
            <ul>
              {data.backtests.map((row, index) => (
                <li key={index}>{JSON.stringify(row)}</li>
              ))}
            </ul>
          )}
      </Card>
    </>
  )
}
