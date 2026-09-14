import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChipOutlook from './ChipOutlook'

// Moved beside the panel in v18f §2.1, with the fixtures the tab's own file
// held for it. The two cases about the *segmented control* that opens it —
// that it is a third segment, and that the chip table and wildcard panel are
// unchanged beside it — stay in `ChipsTab.test.tsx`, where the control is.

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  // `usePageData` reads every rejection through this, so a double that
  // omitted it would make the failure path throw rather than render.
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

const PLAN = {
  gw: 5,
  chips: [
    { chip: 'bboost', weeks: [{ gw: 5, gain: 2.0, per_week: 2.0 },
                              { gw: 6, gain: 3.5, per_week: 3.5 }],
      best_gw: 6, best_gain: 3.5, best_gain_per_week: 3.5, weeks_scored: 2,
      now_gain: 2.0, play_now_delta: -1.5, threshold_now: 4.0,
      play_now: false, thetas: [4.0, 3.2], window: [5, 19] },
    { chip: 'freehit', weeks: [{ gw: 5, gain: 6.0, per_week: 6.0 }],
      best_gw: 5, best_gain: 6.0, best_gain_per_week: 6.0, weeks_scored: 1,
      now_gain: 6.0, play_now_delta: 0.0, threshold_now: 4.0,
      play_now: true, thetas: [4.0], window: [5, 19] },
  ],
}

const OUTLOOK_EMPTY = {
  from_gw: 5, weeks: [{ gw: 5, fixtures: 10, doubles: [], blanks: [] }],
  has_doubles: false, has_blanks: false, teams_known: true,
  note: 'No doubles or blanks are scheduled yet — rearrangements usually '
    + 'start appearing around the cup rounds.',
}

const OUTLOOK_FULL = {
  from_gw: 5,
  weeks: [
    { gw: 5, fixtures: 10, doubles: [], blanks: [] },
    { gw: 6, fixtures: 11,
      doubles: [{ code: 14, short_name: 'LIV' }],
      blanks: [{ code: 8, short_name: 'CHE' }] },
  ],
  has_doubles: true, has_blanks: true, teams_known: true, note: null,
}

function serveOutlook(outlook: unknown = OUTLOOK_EMPTY, plan: unknown = PLAN) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/chips/plan')) return Promise.resolve(plan)
    if (path.startsWith('/api/fixtures/outlook')) return Promise.resolve(
      outlook)
    return Promise.resolve({})
  })
}

function openOutlook() {
  render(<MemoryRouter><ChipOutlook /></MemoryRouter>)
}

beforeEach(() => {
  apiGet.mockReset()
})

describe('the season outlook segment (v10b §F2c)', () => {
  it('says plainly that nothing is scheduled yet', async () => {
    // Asserted as a string, because this sentence *is* the feature for the
    // next four months: today's list is ten fixtures in every one of
    // thirty-eight gameweeks.
    serveOutlook()
    openOutlook()
    expect(await screen.findByText(/No doubles or blanks are scheduled yet/))
      .toBeInTheDocument()
  })

  it('lists the doubles and blanks per gameweek when there are any',
     async () => {
       serveOutlook(OUTLOOK_FULL)
       openOutlook()
       const week = await screen.findByTestId('outlook-week-6')
       expect(within(week).getByText(/LIV/)).toBeInTheDocument()
       expect(within(week).getByText(/CHE/)).toBeInTheDocument()
       expect(screen.queryByText(/No doubles or blanks are scheduled/))
         .toBeNull()
     })

  it('shows each chip’s gain against its bar and its θ per week', async () => {
    serveOutlook()
    openOutlook()
    const row = await screen.findByTestId('outlook-chip-bboost')
    expect(within(row).getByText(/θ 4.0/)).toBeInTheDocument()
    expect(within(row).getByText(/best GW6 · 3.5/))
      .toBeInTheDocument()
    expect(within(row).getByTestId('theta-track')).toBeInTheDocument()
  })

  it('names the GW19 expiry for a first-half chip only', async () => {
    serveOutlook()
    openOutlook()
    // Both chips in the fixture sit in the first-half window.
    expect((await screen.findAllByText(/expires after GW19/))).toHaveLength(2)
  })

  it('does not name a GW19 expiry in the second half of the season',
     async () => {
       // `window` drives it. A hardcoded 19 would be wrong from GW20 onward,
       // when the second set of chips runs to GW38.
       serveOutlook(OUTLOOK_EMPTY, {
         ...PLAN,
         chips: PLAN.chips.map((c) => ({ ...c, window: [25, 38] })),
       })
       openOutlook()
       await screen.findByTestId('chip-outlook')
       expect(screen.queryByText(/expires after GW19/)).toBeNull()
     })

  it('names the window’s own expiry in the second half of the season',
     async () => {
       // The row carries its window; the component reads the end of it. The
       // literal it replaced could only ever say GW19, so the second set of
       // chips — which runs to GW38 — had no expiry at all.
       serveOutlook(OUTLOOK_EMPTY, {
         ...PLAN,
         chips: PLAN.chips.map((c) => ({ ...c, window: [25, 38] })),
       })
       openOutlook()
       expect((await screen.findAllByText(/expires after GW38/)))
         .toHaveLength(2)
     })

  it('trusts the served flags over the slice it happens to be rendering',
     async () => {
       // `has_doubles` is the server's answer about the season; the filtered
       // rows are only what this slice shows. A client that re-derives the
       // empty state from the rows tells the user nothing is scheduled on
       // exactly the payload that says something is.
       serveOutlook({
         ...OUTLOOK_EMPTY, has_doubles: true, note: null,
       })
       openOutlook()
       await screen.findByTestId('chip-outlook')
       expect(screen.queryByText(/Nothing unusual scheduled/)).toBeNull()
       expect(screen.queryByText(/No doubles or blanks are scheduled/))
         .toBeNull()
     })

  it('says when the clubs could not be named and the counts still hold',
     async () => {
       // `teams_known: false` is the teams-snapshot degradation: the counts
       // are the published list's own and only the short names are missing.
       // The table shows `#14` either way; this line says why.
       serveOutlook({
         ...OUTLOOK_FULL, teams_known: false,
         weeks: [{ gw: 6, fixtures: 11,
                   doubles: [{ code: 14, short_name: null }], blanks: [] }],
       })
       openOutlook()
       expect(await screen.findByTestId('outlook-teams-unknown'))
         .toHaveTextContent(/club names unavailable/i)
     })

  it('does not complain about club names when there are no rows', async () => {
    // The fresh-clone shape: no fixtures file, so no weeks and no teams
    // snapshot either. "Club names unavailable — counts still hold" over an
    // empty table is a complaint about names nothing was going to print, and
    // it is the *first* line a new user reads.
    serveOutlook({
      from_gw: null, weeks: [], has_doubles: false, has_blanks: false,
      teams_known: false, note: 'No fixture list yet — run refresh-data.',
    })
    openOutlook()
    expect(await screen.findByText(/No fixture list yet/)).toBeInTheDocument()
    expect(screen.queryByTestId('outlook-teams-unknown')).toBeNull()
    expect(screen.queryByText(/Club names unavailable/i)).toBeNull()
  })

  it('does not say the clubs are unnamed when they are', async () => {
    serveOutlook(OUTLOOK_FULL)
    openOutlook()
    await screen.findByTestId('outlook-week-6')
    expect(screen.queryByTestId('outlook-teams-unknown')).toBeNull()
  })

  it('is labelled planning rather than advice', async () => {
    // The whole risk of this panel is that a θ trajectory reads like an
    // instruction. It says which it is, above the numbers.
    serveOutlook()
    openOutlook()
    expect(await screen.findByTestId('outlook-caveat'))
      .toHaveTextContent(/planning/i)
  })

  it('keeps one source working when the other fails', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips/plan')) {
        return Promise.reject(new Error('plan is down'))
      }
      if (path.startsWith('/api/fixtures/outlook')) {
        return Promise.resolve(OUTLOOK_FULL)
      }
      return Promise.resolve({})
    })
    openOutlook()
    expect(await screen.findByTestId('outlook-week-6')).toBeInTheDocument()
  })
})
