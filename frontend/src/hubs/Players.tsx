import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost, errorText } from '../api/client'
import { useDebounced } from '../api/useDebounced'
import {
  type Column, Card, DataTable, EmptyState, Loading, PageHeader, PlayerName,
  PosBadge, Sparkline, fmtNum, posColor, toast, useTabParam,
} from '../kit'
import type {
  AdviceLatest, OverridesPanel, PlayerRow, WatchlistPanel,
} from '../types'
import ComparePanel from './players/ComparePanel'
import FixtureMatrix from './players/FixtureMatrix'
import PinDialog from './players/PinDialog'
import WatchlistTab from './players/WatchlistTab'

const POSITIONS = ['', 'GKP', 'DEF', 'MID', 'FWD']

// `shrink-0 whitespace-nowrap` so a trigger scrolls out of the strip rather
// than compressing into two lines of one word at 390px.
const TAB_CLASS = 'shrink-0 whitespace-nowrap px-3 py-2 text-text-muted '
  + 'data-[state=active]:text-text '
  + 'data-[state=active]:border-b data-[state=active]:border-text'

// The strip's values, in strip order. Named so `useTabParam` can reject a
// `?tab=` this hub does not have rather than rendering an empty panel.
const TABS = ['explorer', 'compare', 'matrix', 'watchlist'] as const

export default function Players() {
  const [tab, setTab] = useTabParam(TABS, 'explorer')
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
  // The row whose availability the manager is overruling, or null.
  const [pinning, setPinning] = useState<PlayerRow | null>(null)
  // Codes with a pin standing. Read once and then kept current from the
  // dialog's own answer, so the table says which of these numbers are the
  // manager's own without a second round trip per save.
  const [pinned, setPinned] = useState<number[]>([])
  // Starred codes, or `null` for "we do not know yet". Read once on mount and
  // then kept current from each write's own answer, exactly as `pinned` is:
  // the alternative is a GET per star, on a table of six hundred rows.
  //
  // Three states rather than two, for the same reason `gwFailed` exists. `[]`
  // used to mean both "nobody is starred" and "the read failed", so a failed
  // GET drew an empty ☆ on every row — and one click on a ☆ that is wrong
  // posts a star for a player who already has one.
  const [starred, setStarred] = useState<number[] | null>(null)
  // Every keystroke drove a GET, and five letters is five requests whose
  // answers can land out of order — the last one back wins, not the last typed.
  const settledSearch = useDebounced(search)

  useEffect(() => {
    apiGet<OverridesPanel>('/api/overrides')
      .then((panel) => setPinned(panel.rows.map((r) => r.code)))
      .catch(() => setPinned([]))
  }, [])

  useEffect(() => {
    apiGet<WatchlistPanel>('/api/watchlist')
      .then((panel) => setStarred(panel.rows.map((r) => r.code)))
      // Left `null`, not emptied. The star column disables itself rather than
      // showing a hollow star the manager can click.
      .catch(() => setStarred(null))
  }, [])

  // A star is a bookmark and its success is the flip itself — no toast (spec
  // D3): a toast for every bookmark on a six-hundred-row table is noise. Its
  // *failure* is a different matter: the write was swallowed, so the star
  // stayed filled and claimed a player was on a list he was not on.
  const toggleStar = (code: number, name: string) => {
    // Unreachable through the UI — the control is disabled while this is
    // unknown — and stated anyway, because "which way do I toggle?" has no
    // answer here and guessing would be the bug this state exists to stop.
    if (starred === null) return
    const on = starred.includes(code)
    // Functional throughout, and per-code on the way back. A whole-array
    // snapshot taken at click time is wrong twice over: two stars in one
    // frame both read the same stale `starred` and the second drops the
    // first, and a revert that restores the snapshot un-stars a *different*
    // player whose write succeeded while this one was in flight — wiping
    // from the UI a row the server has.
    setStarred((prev) => (on
      ? (prev ?? []).filter((c) => c !== code)
      : [...(prev ?? []), code]))
    const request = on
      ? apiDelete<WatchlistPanel>(`/api/watchlist/${code}`)
      // `{ code }`, with no `note`. An omitted note means "star him and say
      // nothing about the note", and the store then keeps whatever note and
      // star date the row has; sending `note: ''` used to destroy a sentence
      // typed on the Watchlist tab on every star. (Not every *click* — this
      // is a toggle, and the other half of the clicks are the DELETE above.)
      : apiPost<WatchlistPanel>('/api/watchlist', { code })
    request
      .then((panel) => setStarred(panel.rows.map((r) => r.code)))
      .catch((e) => {
        // The inverse of the change that was attempted, touching this code
        // and nothing else.
        setStarred((prev) => (on
          ? [...(prev ?? []), code]
          : (prev ?? []).filter((c) => c !== code)))
        toast('negative',
          `Could not ${on ? 'unstar' : 'star'} ${name} — ${errorText(e)}`)
      })
  }

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
    { key: 'name', header: 'Player', primary: true, value: (r) => r.name,
      // No pos dot: the explorer has its own position column, and two
      // statements of the same fact in one row is one too many.
      render: (r) => <PlayerName code={r.code} name={r.name} /> },
    { key: 'team_name', header: 'Team', value: (r) => r.team_name },
    { key: 'position', header: 'Pos', value: (r) => r.position,
      render: (r) => <PosBadge pos={r.position} /> },
    { key: 'price', header: 'Price', primary: true, numeric: true,
      value: (r) => r.price, render: (r) => fmtNum(r.price) },
    { key: 'ep_next', header: 'xPts', primary: true, numeric: true,
      value: (r) => r.ep_next, render: (r) => fmtNum(r.ep_next) },
    { key: 'range', header: 'Range', numeric: true,
      // `== null` rather than `=== null`: the fields are nullable by design,
      // and a payload from a server older than v8g carries none of them at
      // all — an em dash is the right answer to both.
      value: (r) => (r.ep_hi == null || r.ep_lo == null
        ? null : r.ep_hi - r.ep_lo),
      render: (r) => (r.ep_lo == null || r.ep_hi == null
        ? <span className="num text-text-muted">—</span>
        : (
          <span className="num text-text-secondary"
                title={'p25–p75 of what he might score next gameweek: his '
                  + 'expected points plus football’s own variance, plus how '
                  + 'far the forecast itself might move'}>
            {`${r.ep_lo.toFixed(1)}–${r.ep_hi.toFixed(1)}`}
          </span>
        )) },
    { key: 'ep_horizon', header: 'Horizon', numeric: true,
      value: (r) => r.ep_horizon, render: (r) => fmtNum(r.ep_horizon) },
    { key: 'ownership', header: 'Own%', numeric: true,
      value: (r) => r.ownership, render: (r) => fmtNum(r.ownership) },
    { key: 'league_eo', header: 'EO%', numeric: true,
      value: (r) => r.league_eo, render: (r) => fmtNum(r.league_eo) },
    // The label is the reason the column is here: a number is ownership, a
    // word is a position. `Column` has no `sub` member, so the word rides
    // inside the rendered cell; `value` stays the sortable number.
    { key: 'field_eo', header: 'Field%', numeric: true,
      value: (r) => r.field_eo,
      render: (r) => (r.field_eo === null ? '—' : (
        <>
          {fmtNum(r.field_eo, 1)}
          {r.field_eo_delta !== null && r.field_eo_delta !== undefined && (
            // The arrow is the sign and the title is the number. A delta drawn
            // as a second figure in the cell would read as a second ownership.
            <span className="ml-1 text-text-muted"
                  title={`${r.field_eo_delta > 0 ? '+' : ''}`
                    + `${fmtNum(r.field_eo_delta, 1)} since the last sampled `
                    + `gameweek; projected ${fmtNum(r.field_eo_deadline, 1)}%`}
                  data-testid={`eo-trend-${r.code}`}>
              {r.field_eo_delta > 0 ? '↑'
                : (r.field_eo_delta < 0 ? '↓' : '→')}
            </span>
          )}
          {r.field_class && (
            <span className="ml-1 text-text-muted">{r.field_class}</span>
          )}
        </>
      )) },
    { key: 'last4', header: 'Last 4', numeric: true,
      value: (r) => r.last4.length ? r.last4[r.last4.length - 1] : null,
      render: (r) => <Sparkline values={r.last4} /> },
    {
      key: 'star', header: '', value: () => '',
      render: (r) => {
        // A hollow star over an unknown watchlist is a claim, and a clickable
        // one is worse: the click posts a star for a player who may already
        // have one. Disabled, and the title says which of the two it is.
        const unknown = starred === null
        const on = starred?.includes(r.code) ?? false
        return (
          <button
            type="button"
            disabled={unknown}
            title={unknown ? 'watchlist unavailable' : undefined}
            aria-label={unknown
              ? `watchlist unavailable for ${r.name}`
              : `${on ? 'unstar' : 'star'} ${r.name}`}
            onClick={() => toggleStar(r.code, r.name)}
            className="px-1 text-text-muted hover:text-text
                       disabled:cursor-not-allowed disabled:opacity-40"
          >
            {on ? '★' : '☆'}
          </button>
        )
      },
    },
    {
      key: 'pin', header: '', value: () => '',
      render: (r) => (
        <button
          type="button"
          aria-label={`pin ${r.name}`}
          onClick={() => setPinning(r)}
          className="rounded-card border border-border px-2 py-0.5
                     text-text-muted hover:text-text"
        >
          {pinned.includes(r.code) ? 'Pinned' : 'Pin'}
        </button>
      ),
    },
  ]

  const selected = (rows ?? []).filter((r) => picked.includes(r.code))

  return (
    <>
      <PageHeader
        title="Players"
        // Always says something: an empty context line under a title is the
        // one thing the header cannot do well.
        context={picked.length > 0
          ? `${picked.length} selected for compare`
          : `${(rows ?? []).length} in the candidate pool`}
      />
      <Tabs.Root value={tab} onValueChange={setTab}>
        <Tabs.List className="mb-4 flex overflow-x-auto border-b
                              border-divider">
          <Tabs.Trigger value="explorer" className={TAB_CLASS}>Explorer</Tabs.Trigger>
          <Tabs.Trigger value="compare" className={TAB_CLASS}>Compare</Tabs.Trigger>
          <Tabs.Trigger value="matrix" className={TAB_CLASS}>Fixture matrix</Tabs.Trigger>
          <Tabs.Trigger value="watchlist" className={TAB_CLASS}>Watchlist</Tabs.Trigger>
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
                <div className="mb-3 flex flex-wrap items-center gap-4">
                  <div role="group" aria-label="Position"
                       className="flex flex-wrap gap-1">
                    {POSITIONS.map((p) => {
                      const active = position === p
                      const hue = posColor(p)
                      return (
                        <button
                          key={p || 'all'}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setPosition(p)}
                          className={`num rounded-card border px-2.5 py-1
                            text-[11px] tracking-[0.08em] ${active
                              ? 'bg-card' : 'border-border text-text-muted'}`}
                          // Active takes the position's own hue, so the filter
                          // and the column agree on what a MID looks like.
                          style={active
                            ? { color: hue ?? 'var(--color-text)',
                                borderColor: hue ?? 'var(--color-text)' }
                            : undefined}
                        >
                          {p || 'ALL'}
                        </button>
                      )
                    })}
                  </div>
                  <label className="flex items-center gap-2">
                    <span className="label">Search</span>
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
              ? <Loading />
              : <ComparePanel gw={gw} players={selected}
                              pool={rows ?? []} />}
        </Tabs.Content>
        <Tabs.Content value="matrix">
          <FixtureMatrix from={gw ?? 1} />
        </Tabs.Content>
        <Tabs.Content value="watchlist">
          {/* The hub already owns `starred` for the explorer's star column
              (`:49`), and every write here returns the whole panel — so the
              two surfaces are re-seeded from one answer instead of drifting. */}
          <WatchlistTab onChange={setStarred} />
        </Tabs.Content>
      </Tabs.Root>
      {pinning && (
        <PinDialog code={pinning.code} name={pinning.name}
                   onClose={() => setPinning(null)}
                   onSaved={(panel) => setPinned(
                     panel.rows.map((r) => r.code))} />
      )}
    </>
  )
}
