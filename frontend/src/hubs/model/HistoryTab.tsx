import { useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart as RLineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import { Card, EmptyState, Loading, fmtNum } from '../../kit'
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

  if (error) {
    return (
      <Card title="History unavailable">
        <p className="text-rust">{error}</p>
      </Card>
    )
  }
  if (!data) return <Loading />

  const rows = priceRows(data.prices)

  return (
    <>
      <Card title="Past runs" className="mb-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-right">GW</th>
                <th className="label pb-1 text-left">Captain</th>
                <th className="label pb-1 text-left">In</th>
                <th className="label pb-1 text-left">Out</th>
                <th className="label pb-1 text-right">Hits</th>
                <th className="label pb-1 text-right">Expected</th>
                <th className="label pb-1 text-right">Actual</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((run) => (
                <tr key={run.gw} className="border-t border-divider">
                  <td className="num py-1.5 text-right text-text-secondary">
                    {run.gw}
                  </td>
                  <td className="py-1.5 text-text">{run.captain}</td>
                  <td className="py-1.5 text-sage">
                    {run.buys.join(', ') || '—'}
                  </td>
                  <td className="py-1.5 text-rust">
                    {run.sells.join(', ') || '—'}
                  </td>
                  <td className="num py-1.5 text-right text-text-muted">
                    {run.hits}
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {fmtNum(run.expected_pts)}
                  </td>
                  <td className="py-1.5 text-right">
                    {run.actual_pts === null
                      ? <span className="text-text-faint">not resolved yet</span>
                      : <span className="num text-text">{run.actual_pts}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
            <ul className="flex flex-col gap-1">
              {data.backtests.map((row, index) => (
                <li key={index}
                    className="num overflow-x-auto rounded-card border
                               border-border bg-base px-2 py-1 text-xs
                               text-text-secondary">
                  {JSON.stringify(row)}
                </li>
              ))}
            </ul>
          )}
      </Card>
    </>
  )
}
