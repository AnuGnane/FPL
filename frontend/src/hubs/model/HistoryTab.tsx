import {
  CartesianGrid, Legend, Line, LineChart as RLineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { useState } from 'react'
import { usePageData } from '../../api/pageData'
import {
  Callout, Card, EmptyState, INPUT_CLASS, Loading, SERIES_COLOURS, SERIES_DASH,
  TABLE_CLASS, THEAD_CLASS, TR_CLASS, fmtNum, tdClass, thClass,
} from '../../kit'
import type { AdviceDiff, HistoryData } from '../../types'
import AdviceDiffRows from '../this-week/AdviceDiffRows'

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

/**
 * One week's served plan against another's (v19e §2.2).
 *
 * The table above lists what each week did; nothing said what changed
 * between two of them, which is the question a reader of a run history
 * actually has. The sentence is `AdviceDiffRows` — the same one This Week's
 * "since last run" strip prints — because the payload is the same payload.
 *
 * Fewer than two gameweeks is no comparison to offer, so the caller renders
 * nothing at all rather than a card with one week in both selects.
 */
function CompareCard({ gws }: { gws: number[] }) {
  const [from, setFrom] = useState(gws[1])
  const [to, setTo] = useState(gws[0])
  const { data } = usePageData<AdviceDiff>(
    `/api/advice/diff?a=${from}&b=${to}`)

  return (
    <Card title="Compare" className="mb-4">
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          <span className="label">From</span>
          <select aria-label="From" className={INPUT_CLASS} value={from}
                  onChange={(e) => setFrom(Number(e.target.value))}>
            {gws.map((gw) => <option key={gw} value={gw}>{`GW${gw}`}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          <span className="label">To</span>
          <select aria-label="To" className={INPUT_CLASS} value={to}
                  onChange={(e) => setTo(Number(e.target.value))}>
            {gws.map((gw) => <option key={gw} value={gw}>{`GW${gw}`}</option>)}
          </select>
        </label>
      </div>
      {/* A week whose plan was never banked is not a fault, here or on the
          server, which answers `available: false` rather than an error. */}
      {data && (data.available
        ? <AdviceDiffRows diff={data} />
        : (
          <p className="text-text-muted">
            no served plan for one of these gameweeks
          </p>
          ))}
    </Card>
  )
}

export default function HistoryTab() {
  // v18e §2.3: one entry per URL, so the tab remounting under Radix does not
  // ask again. The branches below are the ones this tab already had — it
  // synthesised no empty body, so ruling 7 leaves its two states alone.
  const page = usePageData<HistoryData>('/api/history')

  if (page.error !== null) {
    return (
      <Card title="History unavailable">
        {/* A read the server refused, in `down` ink (plan R4). */}
        <Callout tone="error">{page.error}</Callout>
      </Card>
    )
  }
  const data = page.data
  if (!data) return <Loading />

  const rows = priceRows(data.prices)
  // Newest first, deduplicated: the select offers gameweeks, and a week the
  // history lists twice is still one week to compare against.
  const gws = [...new Set(data.runs.map((run) => run.gw))]
    .sort((a, b) => b - a)

  return (
    <>
      <Card title="Past runs" className="mb-4">
        <div className="overflow-x-auto">
          <table className={TABLE_CLASS}>
            <thead className={THEAD_CLASS}>
              <tr>
                <th scope="col" className={thClass(true)}>GW</th>
                <th scope="col" className={thClass()}>Captain</th>
                <th scope="col" className={thClass()}>In</th>
                <th scope="col" className={thClass()}>Out</th>
                <th scope="col" className={thClass(true)}>Hits</th>
                <th scope="col" className={thClass(true)}>Expected</th>
                <th scope="col" className={thClass(true)}>Actual</th>
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
      {gws.length >= 2 && <CompareCard gws={gws} />}
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
