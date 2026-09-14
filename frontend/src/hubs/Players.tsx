import * as Tabs from '@radix-ui/react-tabs'
import { useEffect, useState } from 'react'
import { apiDelete, apiPost, errorText } from '../api/client'
import { invalidate, usePageData } from '../api/pageData'
import { useDebounced } from '../api/useDebounced'
import {
  type Column, Bar, Button, Card, DataTable, EmptyState, INPUT_CLASS, Loading,
  PageHeader, PlayerName, PosBadge, Sparkline, TAB_CLASS, TAB_LIST_CLASS,
  fmtNum, segmentClass, toast, useTabParam,
} from '../kit'
import type {
  AdviceLatest, OverridesPanel, PlayerRow, WatchlistPanel,
} from '../types'
import ComparePanel from './players/ComparePanel'
import FixtureMatrix from './players/FixtureMatrix'
import PinDialog from './players/PinDialog'
import WatchlistTab from './players/WatchlistTab'

const POSITIONS = ['', 'GKP', 'DEF', 'MID', 'FWD']

// The strip's values, in strip order. Named so `useTabParam` can reject a
// `?tab=` this hub does not have rather than rendering an empty panel.
const TABS = ['explorer', 'compare', 'matrix', 'watchlist'] as const

export default function Players() {
  const [tab, setTab] = useTabParam(TABS, 'explorer')
  const [position, setPosition] = useState('')
  const [search, setSearch] = useState('')
  const [picked, setPicked] = useState<number[]>([])
  // Shared with This Week, Planning and League, which read the same URL
  // through the same cache (v17h §3).
  const latest = usePageData<AdviceLatest>('/api/advice/latest')
  const gw = latest.data?.gw ?? null
  // Three states, not two: `gw === null` used to mean both "still loading" and
  // "there is nothing to load", so a failed /api/advice/latest left the Compare
  // tab on "Loading…" for ever with nothing saying what to do about it.
  const gwFailed = latest.error !== null
  // The row whose availability the manager is overruling, or null.
  const [pinning, setPinning] = useState<PlayerRow | null>(null)
  // Codes with a pin standing, so the table says which of these numbers are
  // the manager's own. Through the cache since v18e: the pin dialog and the
  // planning card's unpin both invalidate this URL, so the column follows a
  // write made anywhere without being handed the answer.
  const overrides = usePageData<OverridesPanel>('/api/overrides')
  const pinned = overrides.data?.rows.map((r) => r.code) ?? []
  // Starred codes, or `null` for "we do not know yet".
  //
  // Three states rather than two, for the same reason `gwFailed` exists. `[]`
  // used to mean both "nobody is starred" and "the read failed", so a failed
  // GET drew an empty ☆ on every row — and one click on a ☆ that is wrong
  // posts a star for a player who already has one. `data` is null for both
  // "in flight" and "refused", and the column reads that as unknown.
  //
  // The Watchlist tab reads the same URL through the same cache, so the two
  // surfaces are one request and cannot disagree (v18e §1 part 1).
  const watchlist = usePageData<WatchlistPanel>('/api/watchlist')
  const served = watchlist.data
  // Every keystroke drove a GET, and five letters is five requests whose
  // answers can land out of order — the last one back wins, not the last typed.
  const settledSearch = useDebounced(search)

  // The optimistic overlay on the served list, and only that: a star is a
  // bookmark on a six-hundred-row table and it has to flip under the cursor,
  // not a round trip later. It is re-seeded from the cache whenever the
  // served answer changes — the write's own invalidate is what brings that
  // about — so nothing here is the source of truth for longer than a request.
  const [starred, setStarred] = useState<number[] | null>(null)
  useEffect(() => {
    setStarred(served === null ? null : served.rows.map((r) => r.code))
  }, [served])

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
      // The panel comes back on the write, and the cache is what the column
      // and the Watchlist tab both read — so the answer is put where they
      // are looking rather than into this component alone (v17h §5).
      .then(() => invalidate('/api/watchlist'))
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

  // One URL per filter and per settled search word. Through the cache like
  // every other read since v18e §2.3: it is keyed by URL, so going back to a
  // filter costs nothing, and the hook's ask counter is the stale-response
  // guard this effect never had — five letters' answers could land in any
  // order and the last one back won, not the last one typed.
  const params = new URLSearchParams()
  if (position) params.set('position', position)
  if (settledSearch) params.set('search', settledSearch)
  const poolPage = usePageData<PlayerRow[]>(`/api/players?${params.toString()}`)
  const rows = poolPage.data
  // Every failure is this state, as it was before v18e: a cold clone answers
  // the app-wide 422 here (`players.py:245` raises, `app.py:67-69` maps it),
  // not the 404 `Loaded`'s split is written around, so this read is not one
  // of the nine spec §2.3 moves onto it.
  const missing = poolPage.error !== null

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
        ? <span className="tn text-text-muted">—</span>
        : (
          <span className="tn text-text-secondary"
                title={'p25–p75 of what he might score next gameweek: his '
                  + 'expected points plus football’s own variance, plus how '
                  + 'far the forecast itself might move'}>
            {`${r.ep_lo.toFixed(1)}–${r.ep_hi.toFixed(1)}`}
          </span>
        )) },
    { key: 'ep_horizon', header: 'Horizon', numeric: true,
      value: (r) => r.ep_horizon, render: (r) => fmtNum(r.ep_horizon) },
    // Rule 7: ownership and effective ownership are magnitudes against one
    // ceiling with six hundred rows to compare, so each is the bar with its
    // number beside it. 48px: the explorer carries three of these columns.
    { key: 'ownership', header: 'Own%', numeric: true,
      value: (r) => r.ownership,
      render: (r) => (
        <Bar fraction={r.ownership / 100} text={fmtNum(r.ownership)}
             width={48} testId={`own-${r.code}`}
             aria-label={`Owned by ${fmtNum(r.ownership)}%`} />
      ) },
    { key: 'league_eo', header: 'EO%', numeric: true,
      value: (r) => r.league_eo,
      render: (r) => (
        <Bar fraction={r.league_eo / 100} text={fmtNum(r.league_eo)}
             width={48} testId={`eo-${r.code}`}
             aria-label={`EO ${fmtNum(r.league_eo)}%`} />
      ) },
    // The label is the reason the column is here: a number is ownership, a
    // word is a position. `Column` has no `sub` member, so the word rides
    // inside the rendered cell; `value` stays the sortable number.
    { key: 'field_eo', header: 'Field%', numeric: true,
      value: (r) => r.field_eo,
      render: (r) => (r.field_eo === null ? '—' : (
        <>
          <Bar fraction={r.field_eo / 100} text={fmtNum(r.field_eo, 1)}
               width={48} testId={`field-${r.code}`}
               aria-label={`Field ${fmtNum(r.field_eo, 1)}%`} />
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
            className="px-1 text-text-muted hover:text-accent-text
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
        <Button
          variant="ghost"
          aria-label={`pin ${r.name}`}
          onClick={() => setPinning(r)}
        >
          {pinned.includes(r.code) ? 'Pinned' : 'Pin'}
        </Button>
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
        <Tabs.List className={TAB_LIST_CLASS}>
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
                       className="inline-flex divide-x divide-border
                                  overflow-hidden rounded-ctl border
                                  border-border">
                    {POSITIONS.map((p) => (
                      <button
                        key={p || 'all'}
                        type="button"
                        aria-pressed={position === p}
                        onClick={() => setPosition(p)}
                        className={segmentClass(position === p)}
                      >
                        {p || 'ALL'}
                      </button>
                    ))}
                  </div>
                  <label className="flex items-center gap-2">
                    <span className="label">Search</span>
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className={INPUT_CLASS}
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
          {/* The hub already owns `starred` for the explorer's star column,
              and both read `/api/watchlist` through the one cache entry — so
              the two surfaces are one request and cannot drift. `onChange`
              is what keeps the column optimistic while the write is in
              flight; the invalidate behind it is what settles both. */}
          <WatchlistTab onChange={setStarred} />
        </Tabs.Content>
      </Tabs.Root>
      {/* No `onSaved`: the dialog invalidates `/api/overrides` and the pin
          column above reads that URL, so the "Pinned" label follows the write
          without the panel being handed back up (v18e §2.3). */}
      {pinning && (
        <PinDialog code={pinning.code} name={pinning.name}
                   onClose={() => setPinning(null)} />
      )}
    </>
  )
}
