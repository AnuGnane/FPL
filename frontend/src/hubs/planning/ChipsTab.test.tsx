import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChipsTab from './ChipsTab'

const { FakeApiError, apiGet, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn(), apiPost: vi.fn() }
})

vi.mock('../../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const CHIPS = {
  gw: 5,
  chips: [
    { chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1, threshold: 8.0,
      play_now: true, note: null },
    { chip: 'bboost', gw: 6, gain: 2.0, per_week: 2.0, threshold: 4.0,
      play_now: false, note: null },
    { chip: 'freehit', gw: 7, gain: 5.0, per_week: 5.0, threshold: 4.0,
      play_now: true, note: 'conservative lower bound' },
  ],
  wildcard: {
    gain_over_horizon: 9.4,
    recommend: true,
    kept: [{ code: 100, name: 'Salah', position: 'MID', price: 13,
             ep: 6.4 }],
    dropped: [{ code: 101, name: 'Watkins', position: 'FWD', price: 9,
                ep: 4.1 }],
    added: [{ code: 102, name: 'Wirtz', position: 'MID', price: 8.5,
              ep: 5.2 }],
  },
}

const PLAYERS = [
  { code: 100, name: 'Salah', position: 'MID', price: 13.0, ep_next: 6.4 },
  { code: 102, name: 'Wirtz', position: 'MID', price: 8.5, ep_next: 5.2 },
]

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
    if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
    return Promise.resolve({})
  })
  apiPost.mockResolvedValue({ job_id: 'job-1' })
})

describe('chips tab', () => {
  it('shows every chip week against its own threshold', async () => {
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    // The hub's tab label names the panel now, so the only heading left is
    // the chip table's own card title.
    expect(await screen.findByRole('heading',
      { name: /gain against the bar/i })).toBeInTheDocument()
    // Two matches on purpose: the tab button and the table row.
    expect(screen.getAllByText(/wildcard/i).length).toBeGreaterThan(1)
    expect(screen.getByText('9.4')).toBeInTheDocument()
    expect(screen.getAllByLabelText(/against a bar of 8/i).length)
      .toBeGreaterThan(0)
  })

  it('marks a θ bar as θ and a flat bar as flat', async () => {
    // v12 W3 §4.2. Three distinct fallbacks produce a flat bar and the row
    // says which one it got, so the caption stops implying θ on a week θ
    // never covered.
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve({
        ...CHIPS,
        chips: [
          { chip: 'bboost', gw: 4, gain: 5, per_week: 5, threshold: 4.2,
            threshold_source: 'theta', play_now: true, note: null },
          { chip: '3xc', gw: 4, gain: 1, per_week: 1, threshold: 4,
            threshold_source: 'flat: no calibrated priors asset',
            play_now: false, note: null },
        ],
      })
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({})
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    const sources = await screen.findAllByTestId('bar-source')
    expect(sources.map((n) => n.textContent)).toEqual(['θ', 'flat'])
  })

  it('marks the weeks worth playing now', async () => {
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await screen.findAllByText(/wildcard/i)
    const rows = screen.getAllByRole('row')
    // The dead `.changed` class is gone; the row states it as data instead.
    const playNow = rows.filter(
      (r) => r.getAttribute('data-play-now') === 'true')
    expect(playNow).toHaveLength(2)
  })

  it('lays the wildcard squad out as kept, out and in', async () => {
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click((await screen.findAllByRole('button',
      { name: /wildcard/i }))[0])
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('Watkins')).toBeInTheDocument()
    expect(screen.getByText('Wirtz')).toBeInTheDocument()
    // The gain is its own <span className="num">, so match across children.
    expect(screen.getByText(
      (_, el) => el?.tagName === 'P'
        && /9\.4\s*expected\s*points/.test(el.textContent ?? ''),
    )).toBeInTheDocument()
  })

  it('submits the constrained re-solve with the chip prefilled', async () => {
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    const [path, body] = apiPost.mock.calls[0]
    expect(path).toBe('/api/whatif')
    expect((body as { chip: string }).chip).toBe('wc')
  })

  it('re-solves the chip whose row was picked, not the default', async () => {
    // The page opened on the wildcard; picking Bench Boost has to reach the
    // solver, or "Try it" answers a question about a different chip than the
    // one the reader is looking at.
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /bench boost/i }))
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as { chip: string }).chip).toBe('bb')
  })

  it('maps every chip the table can name onto its request code', async () => {
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /free hit/i }))
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as { chip: string }).chip).toBe('fh')
  })

  it('shows an empty state when no advice has been run', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      404, 'no advice on disk yet — run `gaffer advise` first'))
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer advise` first/))
      .toBeInTheDocument()
  })

  it('says so when there is no wildcard left to assess', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/chips')
        ? Promise.resolve({ ...CHIPS, wildcard: null })
        : Promise.resolve(PLAYERS)))
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click((await screen.findAllByRole('button',
      { name: /wildcard/i }))[0])
    expect(screen.getByText(/no wildcard available/i)).toBeInTheDocument()
  })

  it('fills the answer frame while the chip solve runs', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({ id: 'j1', status: 'running', result: null,
                               error: null })
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-solve/i }))
    expect(await screen.findByTestId('skeleton')).toBeInTheDocument()
  })

  it('shows no skeleton once the chip solve has failed', async () => {
    // The failure has its own line under the button; a pulse above it would
    // say the thing that already failed is still coming.
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({ id: 'j1', status: 'error', result: null,
                               error: 'solver died' })
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-solve/i }))
    expect(await screen.findByText('solver died')).toBeInTheDocument()
    expect(screen.queryByTestId('skeleton')).not.toBeInTheDocument()
  })
})

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
    if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
    if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
    return Promise.resolve({})
  })
}

async function openOutlook() {
  render(<MemoryRouter><ChipsTab /></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button',
    { name: 'Season outlook' }))
}

describe('the season outlook segment (v10b §F2c)', () => {
  it('is a third segment that opens its own panel', async () => {
    serveOutlook()
    await openOutlook()
    expect(screen.getByRole('button', { name: 'Season outlook' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(await screen.findByTestId('chip-outlook')).toBeInTheDocument()
  })

  it('says plainly that nothing is scheduled yet', async () => {
    // Asserted as a string, because this sentence *is* the feature for the
    // next four months: today's list is ten fixtures in every one of
    // thirty-eight gameweeks.
    serveOutlook()
    await openOutlook()
    expect(await screen.findByText(/No doubles or blanks are scheduled yet/))
      .toBeInTheDocument()
  })

  it('lists the doubles and blanks per gameweek when there are any',
     async () => {
       serveOutlook(OUTLOOK_FULL)
       await openOutlook()
       const week = await screen.findByTestId('outlook-week-6')
       expect(within(week).getByText(/LIV/)).toBeInTheDocument()
       expect(within(week).getByText(/CHE/)).toBeInTheDocument()
       expect(screen.queryByText(/No doubles or blanks are scheduled/))
         .toBeNull()
     })

  it('shows each chip’s gain against its bar and its θ per week', async () => {
    serveOutlook()
    await openOutlook()
    const row = await screen.findByTestId('outlook-chip-bboost')
    expect(within(row).getByText(/θ 4.0/)).toBeInTheDocument()
    expect(within(row).getByText(/best GW6 · 3.5/))
      .toBeInTheDocument()
    expect(within(row).getByTestId('theta-track')).toBeInTheDocument()
  })

  it('names the GW19 expiry for a first-half chip only', async () => {
    serveOutlook()
    await openOutlook()
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
       await openOutlook()
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
       await openOutlook()
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
       await openOutlook()
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
       await openOutlook()
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
    await openOutlook()
    expect(await screen.findByText(/No fixture list yet/)).toBeInTheDocument()
    expect(screen.queryByTestId('outlook-teams-unknown')).toBeNull()
    expect(screen.queryByText(/Club names unavailable/i)).toBeNull()
  })

  it('does not say the clubs are unnamed when they are', async () => {
    serveOutlook(OUTLOOK_FULL)
    await openOutlook()
    await screen.findByTestId('outlook-week-6')
    expect(screen.queryByTestId('outlook-teams-unknown')).toBeNull()
  })

  it('is labelled planning rather than advice', async () => {
    // The whole risk of this panel is that a θ trajectory reads like an
    // instruction. It says which it is, above the numbers.
    serveOutlook()
    await openOutlook()
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
      if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
      return Promise.resolve(PLAYERS)
    })
    await openOutlook()
    expect(await screen.findByTestId('outlook-week-6')).toBeInTheDocument()
  })

  it('leaves the chip table and the wildcard panel as they were', async () => {
    serveOutlook()
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    expect(await screen.findByRole('heading',
      { name: /gain against the bar/i })).toBeInTheDocument()
    // Scoped to the segment strip: the chip table's own rows carry a
    // "Wildcard" button too, and always have.
    const strip = screen.getByRole('button', { name: 'Chip table' })
      .parentElement!
    await userEvent.click(within(strip).getByRole('button',
                                                  { name: 'Wildcard' }))
    expect(await screen.findByText('Wirtz')).toBeInTheDocument()
  })
})
