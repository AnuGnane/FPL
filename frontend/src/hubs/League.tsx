import * as Tabs from '@radix-ui/react-tabs'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { apiGet, apiPost, errorText } from '../api/client'
import { invalidate, usePageData } from '../api/pageData'
import {
  type Column, Callout, Card, DataTable, EmptyState, Loading, PageHeader,
  Sparkline, Stat, StatRow, TABLE_CLASS, TAB_CLASS, TAB_LIST_CLASS, THEAD_CLASS,
  TR_CLASS, TR_SELECTED_CLASS, fmtNum, fmtPct, tdClass, thClass, toast,
  useTabParam,
} from '../kit'
import type {
  AdviceLatest, LeagueRaceData, LeagueSimData, LeaguesOverview, RivalSummary,
} from '../types'
import FieldPanel from './league/FieldPanel'
import LeaguesTab, { type Stance, lamText } from './league/LeaguesTab'
import WhatIfSim, { type WhatIfSquadPlayer } from './league/WhatIfSim'

// v15 §6.1: the overview first. `race`/`rivals`/`whatif` show the league in
// `?league=`, or the focus when it is absent.
const TABS = ['leagues', 'race', 'rivals', 'whatif'] as const

/** `path?league_id=N` when a league is chosen; the bare path is the focus. */
function withLeague(path: string, leagueId: number | null): string {
  return leagueId === null ? path : `${path}?league_id=${leagueId}`
}

const FAN_KEYS = ['p05', 'p25', 'p50', 'p75', 'p95'] as const

/**
 * The margin fan: how far ahead of — or behind — the best rival the season
 * ends, at five centiles.
 *
 * The engine has published these since v8c and nothing rendered them, so the
 * card showed three point estimates and no spread at all. Five numbers and
 * two divs rather than a chart library: the shape here is a range with a
 * middle, which a bar says as well as an axis would and without a dependency.
 *
 * Zero is drawn wherever it falls in the range, because the only question the
 * strip has to answer at a glance is which side of it the season sits on.
 */
function MarginFan({ quantiles }: { quantiles: Record<string, number> }) {
  const values = FAN_KEYS.map((k) => quantiles[k])
  if (values.some((v) => typeof v !== 'number' || !Number.isFinite(v))) {
    return null
  }
  const [p05, p25, p50, p75, p95] = values
  const span = p95 - p05
  // A degenerate fan — no weeks left, one entry — is a point, not a bar.
  const at = (v: number) => (span > 0 ? ((v - p05) / span) * 100 : 50)
  const zero = Math.min(100, Math.max(0, at(0)))
  return (
    <div className="mb-3" data-testid="sim-margin-fan">
      <div className="label mb-1">Final margin over the best rival</div>
      {/* Rule 7's named league-race gap: one flat fill on the track, the
          median in text ink, zero in muted. Ahead is a direction (rule 1), so
          a median on the wrong side of zero draws the fan in `down`. */}
      <div className="relative mb-1 h-1.5 w-full rounded-chip bg-border">
        <div
          className={`absolute h-1.5 rounded-chip ${p50 >= 0
            ? 'bg-up' : 'bg-down'}`}
          style={{ left: `${at(p25)}%`, width: `${at(p75) - at(p25)}%` }}
        />
        <div
          className="absolute h-1.5 w-px bg-text"
          style={{ left: `${at(p50)}%` }}
        />
        {span > 0 && p05 <= 0 && p95 >= 0 && (
          <div
            className="absolute h-1.5 w-px bg-text-muted"
            style={{ left: `${zero}%` }}
            data-testid="sim-margin-zero"
          />
        )}
      </div>
      <div className="flex justify-between">
        {FAN_KEYS.map((key) => (
          <span key={key} className="tn text-xs text-text-muted"
                data-testid={`margin-${key}`}>
            {fmtNum(quantiles[key], 0)}
          </span>
        ))}
      </div>
    </div>
  )
}

export default function League() {
  const [tab, setTab] = useTabParam(TABS, 'leagues')
  const [params] = useSearchParams()
  const asked = params.get('league')
  const leagueId = asked !== null && /^\d+$/.test(asked) ? Number(asked) : null
  const [overview, setOverview] = useState<LeaguesOverview | null>(null)
  const [race, setRace] = useState<LeagueRaceData | null>(null)
  const [rivals, setRivals] = useState<RivalSummary[]>([])
  const [missing, setMissing] = useState<string | null>(null)
  const [sim, setSim] = useState<LeagueSimData | null>(null)
  const [busy, setBusy] = useState(false)
  // The same read This Week, Planning and Players make (v17h §3). The league's
  // own four endpoints below keep `apiGet`: they are this hub's alone and no
  // cached card is watching them.
  const latest = usePageData<AdviceLatest>('/api/advice/latest')

  const loadOverview = useCallback(() => {
    apiGet<LeaguesOverview>('/api/league/leagues')
      .then(setOverview).catch(() => setOverview(null))
  }, [])

  const loadLeague = useCallback(() => {
    setRace(null)
    apiGet<LeagueRaceData>(withLeague('/api/league/race', leagueId))
      .then((body) => { setRace(body); setMissing(null) })
      .catch((e) => setMissing(errorText(e)))
    apiGet<RivalSummary[]>(withLeague('/api/league/rivals', leagueId))
      .then(setRivals).catch(() => setRivals([]))
    // The simulated card degrades to the parametric one rather than to an
    // error: /api/league/race already carries those numbers, and a league
    // page with no win-probability panel at all is a worse answer than an
    // older one.
    apiGet<LeagueSimData>(withLeague('/api/league/sim', leagueId))
      .then(setSim).catch(() => setSim(null))
  }, [leagueId])

  useEffect(() => { loadOverview() }, [loadOverview])
  useEffect(() => { loadLeague() }, [loadLeague])

  // An empty squad is a working empty state in the What-if panel, so the
  // failure path is [] rather than an error. Memoised because it is a prop:
  // a fresh array each render is a new identity for the panel to chase.
  const squad: WhatIfSquadPlayer[] = useMemo(
    () => (latest.data?.advice?.xi ?? []).map((p) => (
      { code: p.code, name: p.name, position: p.position ?? '' })),
    [latest.data])

  // Both writes go through the settings endpoint (v15 §4.2), so the Model
  // tab, the CLI and the solve job read the same file. A refusal is a toast
  // and the control stays where the server left it.
  function write(key: 'focus' | 'stance', value: number | string,
                 what: string) {
    setBusy(true)
    apiPost('/api/settings', { key, value })
      .then(() => {
        // Two URLs, because a stance or a focus written here is read on
        // another hub (v17h §5): the ladder card holds /api/settings, and the
        // leagues overview is what This Week's league tile prints — it names
        // the focus league and says whether the stance was set by hand.
        invalidate('/api/settings')
        invalidate('/api/league/leagues')
        loadOverview()
        loadLeague()
      })
      .catch((e) => toast('negative', `Could not ${what} — ${errorText(e)}`))
      .finally(() => setBusy(false))
  }
  const onFocus = (id: number) => write('focus', id, 'set the focus league')
  const onStance = (s: Stance) => write('stance', s, 'set the stance')

  if (missing !== null && overview === null) {
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

  const onLeagues = tab === 'leagues'
  const title = onLeagues ? 'Leagues' : (race?.league_name ?? 'League')
  const back = onLeagues ? undefined : (
    <Link to="/league?tab=leagues" className="text-accent-text hover:underline">
      ‹ Leagues
    </Link>
  )

  // Recharts wants one row per gameweek with a column per entry. Keyed by the
  // entry id, not the team name: FPL does not make team names unique, and two
  // managers who both called their side "The Invincibles" shared a column —
  // the second overwrote the first, so they were drawn as one line and one
  // manager's season vanished off the chart.
  const seriesKey = (entry: number) => `e${entry}`
  const gws = [...new Set((race?.trajectory ?? [])
    .flatMap((t) => t.points.map((p) => p.gw)))].sort((a, b) => a - b)
  const chart = gws.map((gw) => {
    const row: Record<string, number> = { gw }
    for (const entry of race?.trajectory ?? []) {
      const point = entry.points.find((p) => p.gw === gw)
      if (point) row[seriesKey(entry.entry)] = point.total
    }
    return row
  })

  /** Trajectories carry no `is_you`; the standings row for the entry does. */
  const isYou = (entry: number) => Boolean(
    race?.standings.find((row) => row.entry === entry)?.is_you)

  // A four-grey palette cannot separate fifty managers: it draws fifty
  // near-identical lines and the reader cannot find himself in them. So the
  // field is one faint grey and you are text ink on top of it — drawn LAST, a
  // stable sort so the rest keep the order the server sent.
  const trajectory = [...(race?.trajectory ?? [])].sort(
    (a, b) => Number(isYou(a.entry)) - Number(isYou(b.entry)))

  // The one sentence the hub exists to answer: where you are in it.
  const you = race?.standings.find((row) => row.is_you)
  const leagueContext = race === null ? undefined : (you
    ? `${race.standings.length} managers · you are ${you.rank}`
      + ` on ${you.total}`
    : `${race.standings.length} managers`)

  const rivalColumns: Column<RivalSummary>[] = [
    { key: 'rank', header: '#', primary: true, numeric: true,
      value: (r) => r.rank },
    {
      key: 'name', header: 'Team', primary: true, value: (r) => r.name,
      render: (r) => (
        <Link to={`/league/rival/${r.entry}${leagueId === null
                    ? '' : `?league=${leagueId}`}`}
              className="text-accent-text hover:underline">
          {r.name}
        </Link>
      ),
    },
    { key: 'total', header: 'Total', primary: true, numeric: true,
      value: (r) => r.total },
  ]

  return (
    <>
      {/* On the overview the context is the overview's own count, not the
          focus league's standings line, which belongs to the Race tab. */}
      <PageHeader
        title={title}
        context={onLeagues
          ? (overview
              ? `${overview.private.length} private · ${overview.public.length} public`
              : undefined)
          : leagueContext}
        action={back}
      />
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className={TAB_LIST_CLASS}>
          <Tabs.Trigger value="leagues" className={TAB_CLASS}>Leagues</Tabs.Trigger>
          <Tabs.Trigger value="race" className={TAB_CLASS}>Race</Tabs.Trigger>
          <Tabs.Trigger value="rivals" className={TAB_CLASS}>Rivals</Tabs.Trigger>
          <Tabs.Trigger value="whatif" className={TAB_CLASS}>What if</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="leagues">
          {overview ? (
            <LeaguesTab overview={overview} busy={busy}
                        onFocus={onFocus} onStance={onStance} />
          ) : <Loading />}
        </Tabs.Content>
        <Tabs.Content value="race">
          {race === null ? (missing !== null
            ? <Callout tone="error">{missing}</Callout> : <Loading />) : (
            <>
              {overview && !race.focus && (
                <Callout tone="note" className="mb-4" data-testid="focus-note">
                  {`Plan is set by ${overview.focus_name ?? 'the focus league'} `
                   + `(${overview.stance === 'auto'
                        ? overview.focus_stance : `manual ${overview.stance}`}). `
                   + `Here you would ${race.stance === 'neutral'
                        ? 'be neutral' : race.stance}, λ ${lamText(race.lam)}.`}
                </Callout>
              )}
              <Card title="Cumulative points" className="mb-4">
                <ResponsiveContainer width="100%" height={260}>
                  <LineChart data={chart}>
                    <CartesianGrid stroke="var(--color-divider)" vertical={false} />
                    <XAxis dataKey="gw" stroke="var(--color-text-muted)" />
                    <YAxis stroke="var(--color-text-muted)" />
                    <Tooltip contentStyle={{
                      background: 'var(--color-raised)',
                      border: '1px solid var(--color-border)',
                    }} />
                    {/* No Recharts <Legend>: the standings table below names every
                        entry already, and the accent tint on your own row there
                        says which of these lines is yours. */}
                    {trajectory.map((entry) => (
                      <Line
                        key={entry.entry}
                        type="monotone"
                        dataKey={seriesKey(entry.entry)}
                        // The tooltip would otherwise read "e2"; the standings
                        // table below is the legend and names every entry.
                        name={entry.name}
                        dot={false}
                        strokeWidth={isYou(entry.entry) ? 2.5 : 1}
                        stroke={isYou(entry.entry)
                          ? 'var(--color-text)' : 'var(--color-text-faint)'}
                        strokeOpacity={isYou(entry.entry) ? 1 : 0.7}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </Card>
              <Card title="Standings" className="mb-4">
                <div className="overflow-x-auto">
                <table className={TABLE_CLASS}>
                  <thead className={THEAD_CLASS}>
                    <tr>
                      <th className={thClass()}>#</th>
                      <th className={thClass()}>Team</th>
                      <th className={thClass(true)}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {race.standings.map((row) => (
                      // Your own row is the one the reader is: the selected row
                      // of this table, accent-tinted like every other (rule 3).
                      <tr key={row.entry} data-testid={`standing-${row.entry}`}
                          data-you={String(row.is_you)}
                          className={`${TR_CLASS}${row.is_you
                            ? ` ${TR_SELECTED_CLASS}` : ''}`}>
                        <td className={`${tdClass()} tn text-text-muted`}>
                          {row.rank}
                        </td>
                        <td className={`${tdClass()} ${row.is_you
                          ? 'text-text' : 'text-text-secondary'}`}>{row.name}</td>
                        <td className={`${tdClass(true)} text-text`}>
                          {row.total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </Card>
              {sim ? (
                <Card title="Win probability">
                  {/* The three numbers are stat tiles like every other on the
                      site; the testids ride on a span inside each value so the
                      tile shape is the kit's and nothing that reads them moved. */}
                  <StatRow cols={3} className="mb-3">
                    {/* fmtPct rounds to whole percent, which is the right
                        resolution here rather than a stylistic one: at n = 2,000
                        the Monte Carlo standard error on a probability near 0.5
                        is sqrt(0.25 / 2000) ≈ 0.9pp, so a decimal place would be
                        reporting the seed. Raise [league] sim_n before adding
                        one. */}
                    <Stat label="P(win)" value={(
                      <span data-testid="sim-p-win">{fmtPct(sim.p_win)}</span>
                    )} />
                    <Stat label="P(top 3)" value={(
                      <span data-testid="sim-p-top3">{fmtPct(sim.p_top3)}</span>
                    )} />
                    {/* One decimal. A second one is finer than the Monte Carlo
                        resolves: at n = 2,000 the standard error on a probability
                        near 0.5 is about 0.9pp, and the finish is the same draws
                        counted a different way. */}
                    <Stat label="Expected finish"
                          value={fmtNum(sim.exp_finish, 1)} />
                  </StatRow>
                  {sim.history.length > 1 && (
                    <div className="mb-3" data-testid="sim-sparkline">
                      <div className="label">Trend</div>
                      <Sparkline values={sim.history.map((h) => h.p_win)} />
                    </div>
                  )}
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
                  <MarginFan quantiles={sim.margin_quantiles} />
                  <div className="overflow-x-auto">
                  <table className={TABLE_CLASS}>
                    <thead className={THEAD_CLASS}>
                      <tr>
                        <th className={thClass()}>Rival</th>
                        <th className={thClass(true)}>P(I beat him)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sim.per_rival.map((rival) => (
                        <tr key={rival.entry} data-testid={`beat-${rival.entry}`}
                            className={TR_CLASS}>
                          <td className={`${tdClass()} text-text-secondary`}>
                            {rival.name}
                          </td>
                          <td className={`${tdClass(true)} text-text`}>
                            {/* A dash, not a number: an entry whose squad could
                                not be read is not one I am certain to beat. */}
                            {rival.p_beat === null ? '—' : fmtPct(rival.p_beat)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </Card>
              ) : (
                // Card does not forward data-testid, so the fallback marker sits
                // on a wrapper rather than on the card itself.
                <div data-testid="legacy-win-probability">
                  <Card title="Win probability">
                    {/* The pre-v8c parametric pairwise numbers, kept as the
                        fallback until the simulated card is always available. */}
                    <div className="overflow-x-auto">
                    <table className={TABLE_CLASS}>
                      <thead className={THEAD_CLASS}>
                        <tr>
                          <th className={thClass()}>Team</th>
                          <th className={thClass(true)}>P(win)</th>
                          <th className={thClass(true)}>Projected</th>
                        </tr>
                      </thead>
                      <tbody>
                        {race.win_probability.map((prob) => (
                          <tr key={prob.name} className={TR_CLASS}>
                            <td className={`${tdClass()} text-text-secondary`}>
                              {prob.name}
                            </td>
                            <td className={`${tdClass(true)} text-text`}>
                              {fmtPct(prob.p_win)}
                            </td>
                            <td className={`${tdClass(true)} text-text-muted`}>
                              {fmtNum(prob.total, 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                  </Card>
                </div>
              )}
              {/* Below the win-probability card and outside its ternary rather
                  than inside the `sim` branch: the panel already renders nothing
                  when there is no simulation, so a fragment around that branch
                  would buy a second place for the same null check to live. */}
              <FieldPanel field={sim?.field ?? null} />
            </>
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
          {race === null ? <Loading /> : (
            <WhatIfSim
              squad={squad}
              leagueId={leagueId}
              rivals={race.standings.filter((s) => !s.is_you)
                .map((s) => ({ entry: s.entry, name: s.name }))}
            />
          )}
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
}
