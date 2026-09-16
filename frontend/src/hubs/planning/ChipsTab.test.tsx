import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../../api/pageData'
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
  // `usePageData` reads every rejection through this, so a double that
  // omitted it would make the failure path throw rather than render.
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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
    // The bar and its source, so the wildcard-bar caption is on screen for
    // every test in this file rather than in none of them.
    threshold: 8.0,
    threshold_source: 'theta',
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

  it('names both weeks of a chip pair', async () => {
    // v12 W3 §4.5. A pair is one option, so it is one row — the wildcard's
    // week and the boost's, under one label. Dead on today's data (no
    // chip_scenarios.toml), which is why the served shape is pinned here.
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve({
        ...CHIPS,
        chips: [
          { chip: 'wildcard+bboost', gw: 4, gw2: 7, gain: 12.5,
            per_week: 3.1, threshold: 8.0, play_now: true, note: null },
        ],
      })
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({})
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    expect(await screen.findByText('Wildcard + Bench Boost'))
      .toBeInTheDocument()
    expect(screen.getByText('GW4 + GW7')).toBeInTheDocument()
  })

  it('offers no What-If arm for a chip pair, and says why', async () => {
    // T8-T11 review, Important 3. `pick()` left `request.chip` at whatever it
    // was for a chip with no CHIP_CODES entry, so "Try it" on the pair row
    // re-solved a plain wildcard under the pair's name — the label said one
    // thing and the solver did another.
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve({
        ...CHIPS,
        chips: [
          { chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1,
            threshold: 8.0, play_now: true, note: null },
          { chip: 'wildcard+bboost', gw: 4, gw2: 7, gain: 12.5,
            per_week: 3.1, threshold: 12.0, play_now: true, note: null },
        ],
      })
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({})
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'Wildcard + Bench Boost' }))
    expect(screen.getByRole('button', { name: /re-solve/i })).toBeDisabled()
    expect(screen.getByText(/A chip pair has no What-If arm/))
      .toBeInTheDocument()
    // And picking a mapped chip afterwards restores the arm. Two buttons say
    // "Wildcard" — the panel strip and the chip row — and it is the row's
    // pick that has to reach the request.
    await userEvent.click(
      screen.getAllByRole('button', { name: 'Wildcard' })[1])
    const resolve = screen.getByRole('button', { name: /re-solve/i })
    expect(resolve).not.toBeDisabled()
    await userEvent.click(resolve)
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as { chip: string }).chip).toBe('wc')
  })

  it('marks a pair’s summed θ bar as θ', async () => {
    // T8-T11 review, Important 2: the pair's bar is two bars added, so its
    // source names both — and the marker must still read θ rather than
    // falling to "flat" on a string it does not recognise.
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve({
        ...CHIPS,
        chips: [
          { chip: 'wildcard+bboost', gw: 4, gw2: 7, gain: 12.5,
            per_week: 3.1, threshold: 12.0,
            threshold_source: 'theta: wildcard 8.00 + bboost 4.00',
            play_now: true, note: null },
        ],
      })
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({})
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    const sources = await screen.findAllByTestId('bar-source')
    expect(sources.map((n) => n.textContent)).toEqual(['θ'])
    expect(sources[0]).toHaveAttribute(
      'title', 'theta: wildcard 8.00 + bboost 4.00')
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

  it('shows the same empty state for the cold clone’s 422', async () => {
    // The 404 above is `chips.py`'s own. A clone with nothing on disk never
    // reaches it: the read raises a `GafferError` the app-wide handler maps to
    // 422 (app.py:67-69), and both mean "run the job" (v18e ruling 7).
    apiGet.mockRejectedValue(new FakeApiError(
      422, 'no advice on disk yet — run `gaffer advise` first'))
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.queryByText('Chips unavailable')).not.toBeInTheDocument()
  })

  it('says the server broke rather than that no chips can be weighed',
    async () => {
      apiGet.mockRejectedValue(new FakeApiError(500, 'boom'))
      render(<MemoryRouter><ChipsTab /></MemoryRouter>)
      const callout = await screen.findByText('boom')
      expect(callout.closest('[data-tone="error"]')).toBeInTheDocument()
      expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument()
    })

  it('names the wildcard’s own bar and where it came from', async () => {
    // Minor 9: the fixture had no threshold, so this caption never rendered
    // in any test and its wording was unasserted.
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click((await screen.findAllByRole('button',
      { name: /wildcard/i }))[0])
    expect(await screen.findByTestId('wildcard-bar')).toHaveTextContent(
      'Against a bar of 8 (θ — the best remaining week’s expected surplus)')
  })

  it('renders a flat reason once, and an unexplained bar not at all',
    async () => {
      // Minor 8: the reason is written server-side and already begins
      // "flat: …", so wrapping it printed "flat fallback — flat: …"; the
      // "unknown" sentinel was printed as though it were a reason.
      const bar = async (source: string | null) => {
        // Three renders in one case, and the tab reads `/api/chips` through
        // the shared cache now: without this the second render is answered
        // from the first one's body and the mock below is never asked.
        resetPageData()
        apiGet.mockImplementation((path: string) => (
          path.startsWith('/api/chips')
            ? Promise.resolve({ ...CHIPS,
                                wildcard: { ...CHIPS.wildcard,
                                            threshold_source: source } })
            : Promise.resolve(PLAYERS)))
        const view = render(<MemoryRouter><ChipsTab /></MemoryRouter>)
        await userEvent.click((await screen.findAllByRole('button',
          { name: /wildcard/i }))[0])
        const text = (await screen.findByTestId('wildcard-bar')).textContent
        view.unmount()
        return text
      }
      expect(await bar('flat: no calibrated priors asset')).toBe(
        'Against a bar of 8 (flat: no calibrated priors asset)')
      expect(await bar('unknown')).toBe('Against a bar of 8')
      expect(await bar(null)).toBe('Against a bar of 8')
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
  ],
}

const OUTLOOK_EMPTY = {
  from_gw: 5, weeks: [{ gw: 5, fixtures: 10, doubles: [], blanks: [] }],
  has_doubles: false, has_blanks: false, teams_known: true,
  note: 'No doubles or blanks are scheduled yet — rearrangements usually '
    + 'start appearing around the cup rounds.',
}

// The panel's own dozen cases moved to `ChipOutlook.test.tsx` in v18f §2.1.
// What is left here is the control that opens it, and the two panels beside
// it — claims about the tab, which the panel's file cannot make.
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

describe('Where a chip’s bar came from', () => {
  // v19g §2.3. `threshold_source` has been served on every row since v12 and
  // the marker read it as one bit — θ or flat. Four different reasons produce
  // a flat bar, with four different fixes, so the suffix names the one this
  // row got and the title spells it out in a sentence.
  const serveSources = (sources: (string | null)[]) => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips')) return Promise.resolve({
        ...CHIPS,
        chips: sources.map((source, i) => ({
          chip: 'bboost', gw: 4 + i, gain: 5, per_week: 5, threshold: 4.2,
          threshold_source: source, play_now: false, note: null,
        })),
      })
      if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
      return Promise.resolve({})
    })
  }

  it('names each flat bar’s own reason', async () => {
    serveSources([
      'flat: no calibrated priors asset',
      'flat: priors asset has no usable chip_surplus',
      'flat: no calibrated surplus for this chip',
      'flat: gameweek outside the calibrated window',
    ])
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    const why = await screen.findAllByTestId('bar-source-why')
    expect(why.map((n) => n.textContent)).toEqual([
      '(no calibrated priors asset)',
      '(priors asset has no usable chip_surplus)',
      '(no calibrated surplus for this chip)',
      '(gameweek outside the calibrated window)',
    ])
  })

  it('explains each source in a sentence on the title', async () => {
    serveSources(['flat: gameweek outside the calibrated window'])
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    const why = await screen.findByTestId('bar-source-why')
    expect(why.getAttribute('title'))
      .toMatch(/outside the window calibration covered/)
    // The marker beside it carries the same sentence, so a reader who hovers
    // either half gets the same answer.
    expect(screen.getByTestId('bar-source').getAttribute('title'))
      .toBe(why.getAttribute('title'))
  })

  it('leaves a θ bar with the marker alone', async () => {
    // θ already says where the bar came from; "(theta)" beside it would be
    // the same word twice.
    serveSources(['theta'])
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    expect(await screen.findByTestId('bar-source')).toHaveTextContent('θ')
    expect(screen.queryByTestId('bar-source-why')).toBeNull()
  })

  it('says nothing at all for a payload with no source', async () => {
    serveSources([null])
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await screen.findAllByText(/bench boost/i)
    expect(screen.queryByTestId('bar-source')).toBeNull()
    expect(screen.queryByTestId('bar-source-why')).toBeNull()
  })

  it('falls back to the served string for a reason it has not seen', async () => {
    // The reason is written server-side; a build that has not caught up with
    // a new one renders it verbatim rather than dropping it.
    serveSources(['flat: some reason invented after this build'])
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    const why = await screen.findByTestId('bar-source-why')
    expect(why).toHaveTextContent('(some reason invented after this build)')
    expect(why.getAttribute('title'))
      .toBe('flat: some reason invented after this build')
  })
})
