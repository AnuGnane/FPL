import { readFileSync } from 'node:fs'
import {
  fireEvent, render, screen, waitFor, within,
} from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsTab from '../hubs/model/SettingsTab'
import DecisionPanel from '../hubs/this-week/DecisionPanel'
import type { SettingsPanel } from '../types'
import { invalidate, usePageData } from './pageData'

/**
 * A write must not leave a cached card stale (v17h §5).
 *
 * Before v17h every navigation refetched, so no write could strand a panel.
 * With one body per URL held until something clears it, a write whose GET
 * nobody invalidates is a page showing the value the user just changed away
 * from — and the writer is often in a different hub from the reader, which is
 * why this is a table and not a code review.
 *
 * **Two classes of writer, and the second is the one that was missed.** A
 * request that writes — a POST, a DELETE — names the URL it disturbed and is
 * found by grepping for the verb. A *job* that rewrites names nothing: the
 * Model hub's Refresh data rewrites the player table This Week's explorer and
 * every news panel read, and the only trace in this codebase is a `kind=` on
 * a button. Sweeping `apiPost`/`apiDelete` alone finds the first class and
 * misses the second, so the table below carries both and says which is which.
 *
 * Two instruments, because they catch different mistakes. The table holds the
 * spec to the source and would catch a *future* writer added with no
 * invalidation beside it; the cases under it drive the mechanism and prove it
 * actually re-reads, which reading source can never show — and read the one
 * branch the table is blind to, the settings tab's guard on the key.
 */

/**
 * The file with its comments taken out.
 *
 * The scan is a text match, so without this a call that is commented out — or
 * merely *described* in a comment, which the files above do — satisfies it.
 * Block comments first and line comments second, so a pair of slashes inside a
 * block comment cannot eat the rest of that line. What no text scan can see is
 * a call on the wrong branch or after an early return; that is the argument
 * for the behavioural cases below, not for a cleverer regex.
 */
function code(file: string): string {
  return readFileSync(file, 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\/\/[^\n]*/g, '')
}

/**
 * file → the calls its write must make. Spec §5, transcribed.
 *
 * Not listed, and checked rather than assumed: `snapshot` rewrites
 * `live/availability_log.parquet`, which is an input to the next advise run
 * and to /api/health — no cached URL reads it. `news-shadow` writes an
 * evaluation report and has no button in this app at all. Evaluate, Track pens
 * and Review write `reports/` alone.
 */
const TABLE: Record<string, string[]> = {
  // Requests that write.
  'src/hubs/this-week/LadderCard.tsx': ["invalidate('/api/settings')"],
  'src/hubs/model/SettingsTab.tsx': ["invalidate('/api/settings')",
                                     "invalidate('/api/league/leagues')"],
  'src/hubs/League.tsx': ["invalidate('/api/settings')",
                          "invalidate('/api/league/leagues')"],
  'src/hubs/this-week/DecisionPanel.tsx': ['invalidate(`/api/decisions/${gw}`)'],
  'src/hubs/players/PinDialog.tsx': ["invalidate('/api/overrides')"],
  // The spec put the unpin on the Players hub, where the pin *dialog* lives.
  // The DELETE is the planning card's, and the reader it disturbs — the Why
  // panel's pin list — is the same one either way.
  'src/hubs/planning/OverridesCard.tsx': ["invalidate('/api/overrides')"],
  // Jobs that rewrite. Refresh data moves live/players.parquet, which is both
  // the explorer's table and the names and clubs every /api/news/{gw} panel
  // joins against; field scrape moves the sample behind the EO columns.
  'src/hubs/Model.tsx': ["invalidate('/api/players')",
                         "invalidatePrefix('/api/news/')"],
}

describe('every write clears the cached reads it disturbs', () => {
  for (const [file, calls] of Object.entries(TABLE)) {
    for (const call of calls) {
      it(`${file} calls ${call}`, () => {
        expect(code(file)).toContain(call)
      })
    }
  }
})

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
}))
vi.mock('./client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  // Its own spy. Pointed at `apiGet` it is inert here and a trap later: the
  // cases below count GETs to prove a re-read happened, and a DELETE landing
  // on that same counter is a re-read that never occurred.
  apiDelete: (path: string) => apiDelete(path),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

// `open` is the one state with the reason control and the save button on it:
// before the deadline the panel is a sentence and after the grade it is
// read-only, and neither can write.
const NOTE = { gw: 5, reason: null, text: '', at: null, state: 'open',
               deadline: '2020-01-01T00:00:00Z', grade: null }

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(NOTE)
  apiPost.mockReset()
  apiPost.mockResolvedValue({ ...NOTE, reason: 'gut', text: 'took the rung' })
  apiDelete.mockReset()
})

describe('the mechanism, not only the source', () => {
  it('re-reads the note after the decision panel saves one', async () => {
    render(<DecisionPanel gw={5} />)
    await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(1) })
    fireEvent.click(screen.getByRole('button', { name: 'Gut' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(2) })
    expect(apiGet).toHaveBeenLastCalledWith('/api/decisions/5')
  })

  // The cross-hub half of §5, with the writer stood in for by the call it
  // makes: a card mounted on a URL some other hub has just written re-reads
  // it where it stands, without being told by whoever wrote it.
  it('re-reads for a card mounted on a URL another hub just wrote',
     async () => {
       render(<DecisionPanel gw={5} />)
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(1) })
       invalidate('/api/decisions/5')
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(2) })
     })
})

/** A card holding the leagues overview: This Week's tile, or the League hub's
 *  own panel. All these cases ask of it is that it is mounted on the URL when
 *  the write lands two hubs away. */
function LeaguesProbe() {
  const { data } = usePageData<{ stance: string }>('/api/league/leagues')
  return <span data-testid="probe">{data?.stance ?? '—'}</span>
}

const SETTINGS: SettingsPanel = {
  rows: [
    { key: 'horizon', label: 'Horizon (gameweeks)', kind: 'int', value: 3,
      lo: 1, hi: 8, choices: [], options: [], section: 'optimizer',
      help: 'How far it plans.', source: 'base' },
    { key: 'stance', label: 'Stance', kind: 'choice', value: 'auto',
      choices: ['auto', 'chase', 'defend', 'neutral'], options: [],
      lo: null, hi: null, section: 'league',
      help: 'Auto lets the standings set the tilt.', source: 'default' },
  ],
  unavailable: [], overlay_error: null, apply_note: '',
}

const asked = (path: string) => apiGet.mock.calls
  .filter((call) => call[0] === path).length

// The guard is a branch, and no scan of the source can tell `LEAGUE_KEYS.has`
// from `false` or from the wrong two keys. These two can.
describe('the settings tab, whose guard the table cannot read', () => {
  beforeEach(() => {
    apiGet.mockImplementation((path: string) => Promise.resolve(
      path === '/api/settings' ? SETTINGS : { stance: 'auto' }))
    apiPost.mockResolvedValue(SETTINGS)
  })

  it('re-reads the leagues overview when the stance is saved from the model '
     + 'hub', async () => {
    render(<><SettingsTab /><LeaguesProbe /></>)
    const group = await screen.findByRole('group', { name: 'Stance' })
    await waitFor(() => { expect(asked('/api/league/leagues')).toBe(1) })
    fireEvent.click(within(group).getByRole('button', { name: 'defend' }))
    await waitFor(() => { expect(asked('/api/league/leagues')).toBe(2) })
  })

  it('leaves the overview alone when the setting is not a league one',
     async () => {
       render(<><SettingsTab /><LeaguesProbe /></>)
       await screen.findByLabelText('Horizon (gameweeks)')
       await waitFor(() => { expect(asked('/api/league/leagues')).toBe(1) })
       fireEvent.click(screen.getByRole('button',
                                        { name: 'Save Horizon (gameweeks)' }))
       await waitFor(() => { expect(apiPost).toHaveBeenCalled() })
       expect(asked('/api/league/leagues')).toBe(1)
     })
})
