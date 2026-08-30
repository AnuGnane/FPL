import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import {
  Card, EmptyState, JobButton, Loading, PageHeader, PitchView, Stat,
  ThresholdBar, fmtNum, fmtPct,
} from '../kit'
import type {
  AdviceChipRow, AdviceLatest, ComponentsBreakdown, PlayerRow,
} from '../types'
import MovesCard from './this-week/MovesCard'
import NewsPanel from './this-week/NewsPanel'
import WhyPanel from './this-week/WhyPanel'
import SquadTable, { type SquadBreakdown, type SquadRow }
  from './this-week/SquadTable'

/** The chip the run rated highest that is still ahead of us. */
function nextChip(rows: AdviceChipRow[] | undefined) {
  if (!rows || rows.length === 0) return null
  return [...rows].sort((a, b) => b.gain - a.gain)[0]
}

export default function ThisWeek() {
  const [data, setData] = useState<AdviceLatest | null>(null)
  const [players, setPlayers] = useState<PlayerRow[]>([])
  const [components, setComponents] = useState<ComponentsBreakdown | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((body) => {
        setData(body)
        setError(null)
        // Both of these are decoration on a page that already has its advice:
        // they load behind it and their failure never blanks the hub.
        apiGet<PlayerRow[]>('/api/players').then(setPlayers).catch(() => {})
        apiGet<ComponentsBreakdown>(`/api/components/${body.gw}`)
          .then(setComponents).catch(() => {})
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(load, [load])

  // The armband is dereferenced unguarded all over the page below —
  // advice.captain.name in a Stat, advice.vice.code on the pitch. An artifact
  // written without one made every one of those a TypeError during render,
  // which React answers by unmounting the tree: a white screen, no message.
  const armbandMissing = Boolean(data)
    && (!data!.advice?.captain || !data!.advice?.vice)

  if (error || !data || armbandMissing) {
    return (
      <>
        <PageHeader title="This Week" />
        {error || armbandMissing
          ? (
            // The action is named, not wired: the JobButton underneath is the
            // one control that starts the run, so there is exactly one.
            <EmptyState
              title="Nothing solved yet"
              detail={error ?? 'The saved advice names no captain or vice, so '
                + 'there is no team to lay out. Re-running the solve rewrites '
                + 'it.'}
              action="Run advise"
            />
            )
          : <Loading />}
        {(error || armbandMissing) && <JobButton kind="advise" onDone={load} />}
      </>
    )
  }

  const advice = data.advice
  const byCode = new Map(players.map((p) => [p.code, p]))
  const squad: SquadRow[] = [...advice.xi, ...advice.bench].map((p) => {
    const row = byCode.get(p.code)
    const move = [...advice.buys, ...advice.sells]
      .find((m) => m.code === p.code)
    return {
      code: p.code,
      name: p.name,
      position: p.position ?? row?.position ?? '',
      ep: p.ep,
      xmins: components?.players.find((c) => c.code === p.code)
        ?.fixtures[0]?.minutes.xmins ?? null,
      ownership: row?.ownership ?? NaN,
      leagueEo: row?.league_eo ?? NaN,
      simPct: move?.frequency ?? null,
      last4: row?.last4 ?? [],
      news: row?.news ?? '',
      chanceOfPlaying: row?.chance_of_playing ?? null,
      penalties: (row?.penalties_order ?? 0) === 1,
    }
  })

  const breakdown: Record<number, SquadBreakdown> = {}
  for (const player of components?.players ?? []) {
    const fixture = player.fixtures[0]
    if (!fixture) continue
    breakdown[player.code] = {
      ep: player.ep,
      components: fixture.components,
      penTaker: fixture.pen_taker ?? null,
    }
  }

  const chip = nextChip(advice.chip_table)
  const strategy = advice.strategy

  return (
    <>
      <PageHeader
        title={`GW${data.gw}`}
        context={data.staleness.stale
          ? data.staleness.reason
          : `deadline ${new Date(data.deadline).toLocaleString()}`}
        action={(
          // Two runs, one lane: the full solve and the same solve with the
          // scenario sweep off (~5 min cheaper). Both reload this page.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="advise" onDone={load} />
            <JobButton kind="advise-fast" onDone={load} />
          </div>
        )}
      />
      {data.staleness.data_warning && (
        <p role="alert" className="mb-4 rounded-card border border-rust-soft
                                   bg-card px-3 py-2 text-rust">
          {data.staleness.data_warning}
        </p>
      )}
      <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Expected XI" value={`${fmtNum(advice.expected_pts)} pts`} />
        <Stat
          label="Captain"
          value={advice.captain.name}
          delta={null}
          deltaLabel={undefined}
        />
        <div className="rounded-card border border-border bg-card px-4 py-3">
          <p className="label">Next chip</p>
          {chip
            ? (
              <div className="mt-2">
                <ThresholdBar
                  label={`${chip.chip} · GW${chip.gw}`}
                  value={chip.gain}
                  threshold={chip.threshold ?? 0}
                />
              </div>
              )
            : <p className="mt-1 text-text-muted">No chips available.</p>}
        </div>
        <Stat
          label="League"
          value={strategy ? `${strategy.gap} pts` : '—'}
          delta={strategy ? strategy.lam : null}
          deltaLabel={strategy ? `λ · ${strategy.stance}` : undefined}
        />
      </div>
      {/* The armband belongs to the pitch, not to a stray line above it. */}
      <Card
        title="Starting XI"
        className="mb-4"
        action={(
          <span className="text-text-muted">
            Captain {advice.captain.name}
            {advice.scenarios?.captain_frequency !== undefined
              && ` · ${fmtPct(advice.scenarios.captain_frequency)} of sims`}
            {' · vice '}{advice.vice.name}
          </span>
        )}
      >
        <PitchView
          xi={advice.xi.map((p) => ({ ...p, position: p.position ?? '' }))}
          captain={advice.captain.code}
          vice={advice.vice.code}
        />
      </Card>
      <Card title="Squad" className="mb-4">
        <SquadTable rows={squad} breakdown={breakdown} />
      </Card>
      <div className="mb-4">
        <MovesCard buys={advice.buys} sells={advice.sells} hits={advice.hits} />
      </div>
      <WhyPanel gw={data.gw} codes={squad.map((r) => r.code)} />
      <NewsPanel gw={data.gw} />
    </>
  )
}
