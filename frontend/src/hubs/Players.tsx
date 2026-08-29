import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { useDebounced } from '../api/useDebounced'
import {
  type Column, Card, DataTable, EmptyState, PageHeader, Sparkline, fmtNum,
} from '../kit'
import type { AdviceLatest, PlayerRow } from '../types'
import ComparePanel from './players/ComparePanel'
import FixtureMatrix from './players/FixtureMatrix'

const POSITIONS = ['', 'GKP', 'DEF', 'MID', 'FWD']

const TAB_CLASS = 'px-3 py-2 text-text-muted data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

export default function Players() {
  const [rows, setRows] = useState<PlayerRow[] | null>(null)
  const [missing, setMissing] = useState(false)
  const [position, setPosition] = useState('')
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<number[]>([])
  const [gw, setGw] = useState<number | null>(null)
  // Three states, not two: `gw === null` used to mean both "still loading" and
  // "there is nothing to load", so a failed /api/advice/latest left the Compare
  // tab on "Loading…" for ever with nothing saying what to do about it.
  const [gwFailed, setGwFailed] = useState(false)
  // Every keystroke drove a GET, and five letters is five requests whose
  // answers can land out of order — the last one back wins, not the last typed.
  const settledSearch = useDebounced(search)

  useEffect(() => {
    apiGet<AdviceLatest>('/api/advice/latest')
      .then((b) => { setGw(b.gw); setGwFailed(false) })
      .catch(() => { setGw(null); setGwFailed(true) })
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (position) params.set('position', position)
    if (settledSearch) params.set('search', settledSearch)
    apiGet<PlayerRow[]>(`/api/players?${params.toString()}`)
      .then((body) => { setRows(body); setMissing(false) })
      .catch(() => setMissing(true))
  }, [position, settledSearch])

  const toggle = (code: number) => setPicked((prev) => (
    prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
  ))

  const columns: Column<PlayerRow>[] = [
    {
      key: 'pick', header: '', value: () => '',
      render: (r) => (
        <input
          type="checkbox"
          aria-label={`compare ${r.name}`}
          checked={picked.includes(r.code)}
          onChange={() => toggle(r.code)}
        />
      ),
    },
    { key: 'name', header: 'Player', primary: true, value: (r) => r.name },
    { key: 'team_name', header: 'Team', value: (r) => r.team_name },
    { key: 'position', header: 'Pos', value: (r) => r.position },
    { key: 'price', header: 'Price', primary: true, numeric: true,
      value: (r) => r.price, render: (r) => fmtNum(r.price) },
    { key: 'ep_next', header: 'xPts', primary: true, numeric: true,
      value: (r) => r.ep_next, render: (r) => fmtNum(r.ep_next) },
    { key: 'ep_horizon', header: 'Horizon', numeric: true,
      value: (r) => r.ep_horizon, render: (r) => fmtNum(r.ep_horizon) },
    { key: 'ownership', header: 'Own%', numeric: true,
      value: (r) => r.ownership, render: (r) => fmtNum(r.ownership) },
    { key: 'league_eo', header: 'EO%', numeric: true,
      value: (r) => r.league_eo, render: (r) => fmtNum(r.league_eo) },
    { key: 'last4', header: 'Last 4', numeric: true,
      value: (r) => r.last4.length ? r.last4[r.last4.length - 1] : null,
      render: (r) => <Sparkline values={r.last4} /> },
  ]

  const selected = (rows ?? []).filter((r) => picked.includes(r.code))

  return (
    <>
      <PageHeader
        title="Players"
        context={picked.length > 0 ? `${picked.length} selected` : undefined}
      />
      <Tabs.Root defaultValue="explorer">
        <Tabs.List className="mb-4 flex border-b border-divider">
          <Tabs.Trigger value="explorer" className={TAB_CLASS}>Explorer</Tabs.Trigger>
          <Tabs.Trigger value="compare" className={TAB_CLASS}>Compare</Tabs.Trigger>
          <Tabs.Trigger value="matrix" className={TAB_CLASS}>Fixture matrix</Tabs.Trigger>
        </Tabs.List>
        <Tabs.Content value="explorer">
          {missing
            ? (
              <EmptyState
                title="No candidate pool"
                detail="The explorer lists the players the last solve
                        considered, priced with its own expected points."
                action="Run advise"
              />
              )
            : (
              <Card>
                <div className="mb-3 flex flex-wrap gap-3">
                  <label className="flex items-center gap-2 text-text-muted">
                    Position
                    <select
                      value={position}
                      onChange={(e) => setPosition(e.target.value)}
                      className="rounded-card border border-border bg-base
                                 px-2 py-1 text-text"
                    >
                      {POSITIONS.map((p) => (
                        <option key={p || 'all'} value={p}>{p || 'All'}</option>
                      ))}
                    </select>
                  </label>
                  <label className="flex items-center gap-2 text-text-muted">
                    Search
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="rounded-card border border-border bg-base
                                 px-2 py-1 text-text"
                    />
                  </label>
                </div>
                <DataTable
                  columns={columns}
                  rows={rows ?? []}
                  rowKey={(r) => r.code}
                  rowLabel={(r) => r.name}
                  initialSort="ep_next"
                  empty={<p className="text-text-muted">No players match.</p>}
                />
              </Card>
              )}
        </Tabs.Content>
        <Tabs.Content value="compare">
          {gwFailed
            ? (
              <EmptyState
                title="Nothing to compare against"
                detail="Comparing players reads the expected-points
                        decomposition of a solved gameweek, and no run has
                        been banked yet."
                action="Run advise"
              />
              )
            : gw === null
              ? <p className="text-text-muted">Loading…</p>
              : <ComparePanel gw={gw} players={selected} />}
        </Tabs.Content>
        <Tabs.Content value="matrix">
          <FixtureMatrix from={gw ?? 1} />
        </Tabs.Content>
      </Tabs.Root>
    </>
  )
}
