import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet } from '../api/client'
import {
  type Column, Card, DataTable, EmptyState, Loading, PageHeader, Sparkline,
  fmtNum, fmtPct,
} from '../kit'
import type {
  AdviceLatest, LeagueRaceData, LeagueSimData, RivalSummary,
} from '../types'
import WhatIfSim, { type WhatIfSquadPlayer } from './league/WhatIfSim'

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

const SERIES_COLOURS = ['var(--color-sage)', 'var(--color-info)',
  'var(--color-rust)', 'var(--color-text-muted)']

export default function League() {
  const [race, setRace] = useState<LeagueRaceData | null>(null)
  const [rivals, setRivals] = useState<RivalSummary[]>([])
  const [missing, setMissing] = useState(false)
  const [sim, setSim] = useState<LeagueSimData | null>(null)
  const [squad, setSquad] = useState<WhatIfSquadPlayer[]>([])

  useEffect(() => {
    apiGet<LeagueRaceData>('/api/league/race')
      .then((body) => { setRace(body); setMissing(false) })
      .catch(() => setMissing(true))
    apiGet<RivalSummary[]>('/api/league/rivals').then(setRivals).catch(() => {})
    // The simulated card degrades to the parametric one rather than to an
    // error: /api/league/race already carries those numbers, and a league
    // page with no win-probability panel at all is a worse answer than an
    // older one.
    apiGet<LeagueSimData>('/api/league/sim').then(setSim).catch(() => setSim(null))
    // An empty squad is a working empty state in the What-if panel, so the
    // failure path is [] rather than an error.
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => setSquad(body.advice.xi.map((p) => (
        { code: p.code, name: p.name, position: p.position ?? '' }))))
      .catch(() => setSquad([]))
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
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What if</Tabs.Trigger>
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
          {sim ? (
            <Card title="Win probability">
              <div className="mb-3 flex flex-wrap items-baseline gap-4">
                <div>
                  <div className="label">P(win)</div>
                  <div className="num text-2xl text-text"
                       data-testid="sim-p-win">{fmtPct(sim.p_win)}</div>
                </div>
                <div>
                  <div className="label">P(top 3)</div>
                  <div className="num text-2xl text-text"
                       data-testid="sim-p-top3">{fmtPct(sim.p_top3)}</div>
                </div>
                <div>
                  <div className="label">Expected finish</div>
                  <div className="num text-2xl text-text">
                    {fmtNum(sim.exp_finish, 2)}
                  </div>
                </div>
                {sim.history.length > 1 && (
                  <div data-testid="sim-sparkline">
                    <div className="label">Trend</div>
                    <Sparkline values={sim.history.map((h) => h.p_win)} />
                  </div>
                )}
              </div>
              {/* A probability with no n and no seed beside it is a
                  decoration: this is the line that makes it a measurement. */}
              <p className="mb-3 text-text-muted" data-testid="sim-provenance">
                {`${sim.n.toLocaleString()} simulations, seed ${sim.seed}, `}
                {`rival drift ${sim.rival_drift}, ${sim.weeks_left} `}
                {'gameweeks left, '}
                {/* Which model produced the fan below, in three words. With
                    a field sample banked the managers share a weekly factor
                    weighted by how much of the template they own; without
                    one they are drawn independently and the fan is wide. */}
                {sim.field_rate === null
                  ? 'independence assumed — fan wide.'
                  : 'shared-ownership correlated.'}
              </p>
              {sim.notice && (
                <p className="mb-3 text-text-muted">{sim.notice}</p>
              )}
              <table className="w-full">
                <thead>
                  <tr>
                    <th className="label pb-1 text-left">Rival</th>
                    <th className="label pb-1 text-right">P(I beat him)</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.per_rival.map((rival) => (
                    <tr key={rival.entry} data-testid={`beat-${rival.entry}`}
                        className="border-t border-divider">
                      <td className="py-1 text-text-secondary">{rival.name}</td>
                      <td className="num py-1 text-right text-text">
                        {/* A dash, not a number: an entry whose squad could
                            not be read is not one I am certain to beat. */}
                        {rival.p_beat === null ? '—' : fmtPct(rival.p_beat)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          ) : (
            // Card does not forward data-testid, so the fallback marker sits
            // on a wrapper rather than on the card itself.
            <div data-testid="legacy-win-probability">
              <Card title="Win probability">
                {/* The pre-v8c parametric pairwise numbers, kept as the
                    fallback until the simulated card is always available. */}
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
            </div>
          )}
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
        <Tabs.Content value="whatif">
          <WhatIfSim
            squad={squad}
            rivals={race.standings.filter((s) => !s.is_you)
              .map((s) => ({ entry: s.entry, name: s.name }))}
          />
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
}
