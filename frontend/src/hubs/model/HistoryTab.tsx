import { useEffect, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart as RLineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../../api/client'
import {
  Callout, Card, EmptyState, Loading, SERIES_COLOURS, SERIES_DASH, TABLE_CLASS,
  THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
import type { HistoryData } from '../../types'

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
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{error}</Callout>
      </Card>
    )
  }
  if (!data) return <Loading />

  const rows = priceRows(data.prices)

  return (
    <>
      <Card title="Past runs" className="mb-4">
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th className={thClass(true)}>GW</th>
                <th className={thClass()}>Captain</th>
                <th className={thClass()}>In</th>
                <th className={thClass()}>Out</th>
                <th className={thClass(true)}>Hits</th>
                <th className={thClass(true)}>Expected</th>
                <th className={thClass(true)}>Actual</th>
              </tr>
            </thead>
            <tbody>
              {data.runs.map((run) => (
                <tr key={run.gw} className={TR_CLASS}>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {run.gw}
                  </td>
                  <td className={`${tdClass()} text-text`}>{run.captain}</td>
                  {/* In and out of the squad: a direction (rule 1). */}
                  <td className={`${tdClass()} text-up`}>
                    {run.buys.join(', ') || '—'}
                  </td>
                  <td className={`${tdClass()} text-down`}>
                    {run.sells.join(', ') || '—'}
                  </td>
                  <td className={`${tdClass(true)} text-text-muted`}>
                    {run.hits}
                  </td>
                  <td className={`${tdClass(true)} text-text-secondary`}>
                    {fmtNum(run.expected_pts)}
                  </td>
                  <td className={tdClass(true)}>
                    {run.actual_pts === null
                      ? <span className="text-text-faint">not resolved yet</span>
                      : <span className="text-text">{run.actual_pts}</span>}
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
              <Tooltip contentStyle={{ background: 'var(--color-raised)',
                                       border: '1px solid var(--color-border)' }} />
              <Legend />
              {/* Four greys, the last two dashed (plan R6): a price line is
                  not a direction and not something you click. */}
              {data.prices.map((series, index) => (
                <Line key={series.code} type="monotone" dataKey={series.name}
                      dot={false} strokeWidth={2}
                      stroke={SERIES_COLOURS[index % 4]}
                      strokeDasharray={SERIES_DASH[index % 4]} />
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
            /* No box (§5): one hairline down the left says "a record" as
               well as a card did. */
            <ul className="flex flex-col gap-1">
              {data.backtests.map((row, index) => (
                <li key={index}
                    className="tn overflow-x-auto border-l-2 border-border
                               pl-3 text-xs text-text-secondary">
                  {JSON.stringify(row)}
                </li>
              ))}
            </ul>
          )}
      </Card>
    </>
  )
}
