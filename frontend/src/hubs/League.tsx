import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../api/client'
import {
  type Column, Card, DataTable, EmptyState, Loading, PageHeader, fmtNum,
  fmtPct,
} from '../kit'
import type { LeagueRaceData, RivalSummary } from '../types'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

export default function League() {
  const [race, setRace] = useState<LeagueRaceData | null>(null)
  const [rivals, setRivals] = useState<RivalSummary[]>([])
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    apiGet<LeagueRaceData>('/api/league/race')
      .then((body) => { setRace(body); setMissing(false) })
      .catch(() => setMissing(true))
    apiGet<RivalSummary[]>('/api/league/rivals').then(setRivals).catch(() => {})
  }, [])

  if (missing) {
    return (
      <>
        <PageHeader title="League" />
        <EmptyState
          title="No league configured"
          detail="Set fpl.league_id to your mini-league, then run advise so the
                  rival ownership table is built."
          action="config.toml"
        />
      </>
    )
  }
  if (!race) {
    return (
      <>
        <PageHeader title="League" />
        <Loading />
      </>
    )
  }

  // Recharts wants one row per gameweek with a column per entry. Keyed by the
  // entry id, not the team name: FPL does not make team names unique, and two
  // managers who both called their side "The Invincibles" shared a column —
  // the second overwrote the first, so they were drawn as one line and one
  // manager's season vanished off the chart.
  const seriesKey = (entry: number) => `e${entry}`
  const gws = [...new Set(race.trajectory
    .flatMap((t) => t.points.map((p) => p.gw)))].sort((a, b) => a - b)
  const chart = gws.map((gw) => {
    const row: Record<string, number> = { gw }
    for (const entry of race.trajectory) {
      const point = entry.points.find((p) => p.gw === gw)
      if (point) row[seriesKey(entry.entry)] = point.total
    }
    return row
  })

  /** Trajectories carry no `is_you`; the standings row for the entry does. */
  const isYou = (entry: number) => Boolean(
    race.standings.find((row) => row.entry === entry)?.is_you)

  /** The line colour this entry was drawn in, so the table is the legend. */
  const seriesColour = (entry: number) => {
    const i = race.trajectory.findIndex((t) => t.entry === entry)
    return i < 0 ? 'transparent' : SERIES_COLOURS[i % SERIES_COLOURS.length]
  }

  // The one sentence the hub exists to answer: where you are in it.
  const you = race.standings.find((row) => row.is_you)
  const leagueContext = you
    ? `${race.standings.length} managers · you are ${you.rank}`
      + ` on ${you.total}`
    : `${race.standings.length} managers`

  const rivalColumns: Column<RivalSummary>[] = [
    { key: 'rank', header: '#', primary: true, numeric: true,
      value: (r) => r.rank },
    {
      key: 'name', header: 'Team', primary: true, value: (r) => r.name,
      render: (r) => (
        <Link to={`/league/rival/${r.entry}`} className="text-info underline">
          {r.name}
        </Link>
      ),
    },
    { key: 'total', header: 'Total', primary: true, numeric: true,
      value: (r) => r.total },
  ]

  return (
    <>
      <PageHeader title="League" context={leagueContext} />
      <Tabs.Root defaultValue="race">
        <Tabs.List className="mb-4 flex border-b border-divider">
          <Tabs.Trigger value="race" className={TAB_CLASS}>Race</Tabs.Trigger>
          <Tabs.Trigger value="rivals" className={TAB_CLASS}>Rivals</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="race">
          <Card title="Cumulative points" className="mb-4">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={chart}>
                <CartesianGrid stroke="var(--color-divider)" vertical={false} />
                <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
                <YAxis stroke="var(--color-text-muted)" />
                <Tooltip contentStyle={{
                  background: 'var(--color-card)',
                  border: '1px solid var(--color-border)',
                }} />
                {/* No Recharts <Legend>: the standings table below names every
                    entry already, and its swatch carries the same colour. */}
                {race.trajectory.map((entry, i) => (
                  <Line
                    key={entry.entry}
                    type="monotone"
                    dataKey={seriesKey(entry.entry)}
                    // The tooltip would otherwise read "e2"; the standings
                    // table below is the legend and names every entry.
                    name={entry.name}
                    dot={false}
                    strokeWidth={isYou(entry.entry) ? 2.5 : 1.5}
                    stroke={SERIES_COLOURS[i % SERIES_COLOURS.length]}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </Card>
          <Card title="Standings" className="mb-4">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="label pb-1 text-left">#</th>
                  <th className="label pb-1 text-left">Team</th>
                  <th className="label pb-1 text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {race.standings.map((row) => (
                  <tr key={row.entry} data-testid={`standing-${row.entry}`}
                      data-you={String(row.is_you)}
                      className="border-t border-divider">
                    <td className="num py-1 text-text-muted">
                      <span
                        aria-hidden
                        className="mr-2 inline-block h-2 w-2 rounded-full"
                        style={{ background: seriesColour(row.entry) }}
                      />
                      {row.rank}
                    </td>
                    <td className={`py-1 ${row.is_you
                      ? 'text-text' : 'text-text-secondary'}`}>{row.name}</td>
                    <td className="num py-1 text-right text-text">
                      {row.total}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Win probability">
            <table className="w-full">
              <thead>
                <tr>
                  <th className="label pb-1 text-left">Team</th>
                  <th className="label pb-1 text-right">P(win)</th>
                  <th className="label pb-1 text-right">Projected</th>
                </tr>
              </thead>
              <tbody>
                {race.win_probability.map((prob) => (
                  <tr key={prob.name} className="border-t border-divider">
                    <td className="py-1 text-text-secondary">{prob.name}</td>
                    <td className="num py-1 text-right text-text">
                      {fmtPct(prob.p_win)}
                    </td>
                    <td className="num py-1 text-right text-text-muted">
                      {fmtNum(prob.total, 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </Tabs.Content>
        <Tabs.Content value="rivals">
          <Card>
            <DataTable
              columns={rivalColumns}
              rows={rivals}
              rowKey={(r) => r.entry}
              rowLabel={(r) => r.name}
              initialSort="rank"
              empty={<p className="text-text-muted">No rivals yet.</p>}
            />
          </Card>
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
}
