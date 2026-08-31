import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhyPanel from './WhyPanel'

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const COMPONENTS = {
  gw: 5,
  players: [
    {
      code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
      ep: 6.4,
      fixtures: [{
        gw: 5, opponent: 'ARS', home: true,
        kickoff_time: '2026-09-05T14:00:00Z',
        components: [
          { label: 'Minutes', points: 1.9 },
          { label: 'Goals', points: 2.6 },
        ],
        pen_taker: 0.31,
        minutes: { p_play: 0.96, p60: 0.9 },
        ep: 6.4,
      }],
    },
  ],
}

const DIFF = {
  gw: 5, available: true, changed: true,
  previous_at: '2026-09-03T09:00:00+00:00',
  current_at: '2026-09-04T09:00:00+00:00',
  buys_added: [{ code: 201, name: 'Wirtz' }],
  buys_dropped: [{ code: 200, name: 'Isak' }],
  sells_added: [], sells_dropped: [],
  captain_from: { code: 100, name: 'Salah' },
  captain_to: { code: 101, name: 'Haaland' },
  chip_from: null, chip_to: 'bboost',
  expected_pts_delta: 2.5,
  ep_movers: [], ep_movers_count: null,
}

/** Every list empty and no retrain to report — the shape the endpoint sends
 *  on a first run of the week. */
const EMPTY_DIFF = {
  gw: 5, available: false, changed: false,
  previous_at: null, current_at: null,
  buys_added: [], buys_dropped: [], sells_added: [], sells_dropped: [],
  captain_from: null, captain_to: null, chip_from: null, chip_to: null,
  expected_pts_delta: 0.0, ep_movers: [], ep_movers_count: null,
}

const PINS = {
  active: true,
  rows: [{ code: 100, name: 'Salah', p_play: 1.0, e_min: null,
           note: 'saw him train', set_at: '2026-09-04T09:00:00+00:00',
           model_p_play: 0.82, model_e_min: null }],
}

const NO_PINS = { active: true, rows: [] }

const CODES = [100]

/** The panel now reads three endpoints, so every mock answers by path. */
function serve(pins: unknown = NO_PINS, diff: unknown = DIFF,
               components: unknown = COMPONENTS) {
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/components')) {
      return components instanceof Error
        ? Promise.reject(components) : Promise.resolve(components)
    }
    if (path.startsWith('/api/overrides')) return Promise.resolve(pins)
    return Promise.resolve(diff)
  })
}

beforeEach(() => {
  apiGet.mockReset()
  serve()
})

describe('WhyPanel', () => {
  it('asks only for the players the plan actually shows', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(apiGet).toHaveBeenCalledWith('/api/components/5?codes=100')
  })

  it('expands a player into his additive terms', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /salah/i }))
    expect(screen.getByText('Goals')).toBeInTheDocument()
    expect(screen.getByText('2.6')).toBeInTheDocument()
    expect(screen.getByText(/vs ARS/)).toBeInTheDocument()
  })

  it('annotates Goals with the penalty duty inside it', async () => {
    // Not a row of its own: the increment was folded into e_goals before the
    // terms were assembled, so listing it beside them would stop the column
    // summing to the xPts above it.
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /salah/i }))
    expect(screen.getByText(/of which penalty duty \+?0\.31/))
      .toBeInTheDocument()
    expect(screen.queryByText('Penalty duty')).not.toBeInTheDocument()
  })

  it('says nothing at all about a player with no penalty duty', async () => {
    serve(NO_PINS, DIFF, {
      ...COMPONENTS,
      players: [{
        ...COMPONENTS.players[0],
        fixtures: [{ ...COMPONENTS.players[0].fixtures[0],
                     pen_taker: null }],
      }],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /salah/i }))
    expect(screen.queryByText(/penalty duty/i)).not.toBeInTheDocument()
  })

  it('asks for the diff of the gameweek the page is showing', async () => {
    // Not whatever the server last wrote: This Week can be asked for an
    // explicit gameweek, and a strip comparing another week's two runs
    // answers a question nobody asked.
    render(<MemoryRouter><WhyPanel gw={7} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(apiGet).toHaveBeenCalledWith('/api/advice/diff?gw=7')
  })

  it('shows what changed since the previous run', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/since last run/i)).toBeInTheDocument()
    expect(screen.getByText(/Wirtz/)).toBeInTheDocument()
    expect(screen.getByText(/Isak/)).toBeInTheDocument()
    expect(screen.getByText(/Salah → Haaland/)).toBeInTheDocument()
    expect(screen.getByText(/\+2.5/)).toBeInTheDocument()
  })

  it('shows no strip at all when there is no previous run', async () => {
    serve(NO_PINS, EMPTY_DIFF)
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/since last run/i)).not.toBeInTheDocument()
  })

  it('says which parts of the plan the manager wrote himself', async () => {
    serve(PINS)
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/your pins are in this plan/i))
      .toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/overrides')
    expect(screen.getByText(
      /You pinned Salah p_play 1\.00 — the model had 0\.82 — saw him train/))
      .toBeInTheDocument()
  })

  it('says a pin is not being applied when the flag is off', async () => {
    serve({ ...PINS, active: false })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/not currently applied/))
      .toBeInTheDocument()
  })

  it('names only the pins on players this plan actually contains', async () => {
    // "Your pins are in this plan" has to be true of every line under it: a
    // pin on somebody the plan never names is not in this plan.
    serve({
      active: true,
      rows: [
        ...PINS.rows,
        { code: 999, name: 'Nobody', p_play: 0.1, e_min: null, note: '',
          set_at: '2026-09-04T09:00:00+00:00', model_p_play: 0.9,
          model_e_min: null },
      ],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/You pinned Salah/)).toBeInTheDocument()
    expect(screen.queryByText(/You pinned Nobody/)).not.toBeInTheDocument()
  })

  it('hides the pin strip when every pin is on somebody else', async () => {
    serve({
      active: true,
      rows: [{ code: 999, name: 'Nobody', p_play: 0.1, e_min: null, note: '',
               set_at: '2026-09-04T09:00:00+00:00', model_p_play: 0.9,
               model_e_min: null }],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/your pins are in this plan/i))
      .not.toBeInTheDocument()
  })

  it('shows no pin strip when nothing is pinned', async () => {
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/your pins are in this plan/i))
      .not.toBeInTheDocument()
  })

  it('hides itself when no components file exists', async () => {
    serve(PINS, EMPTY_DIFF,
          new FakeApiError(404, 'no component breakdown'))
    const { container } = render(
      <MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})

describe('the retrain movers line', () => {
  it('names the count and the top three', async () => {
    serve(NO_PINS, {
      ...EMPTY_DIFF, available: true, changed: true, ep_movers_count: 5,
      ep_movers: [
        { code: 1, name: 'Saka', ep_prev: 5.0, ep_now: 6.4, delta: 1.4 },
        { code: 2, name: 'Rice', ep_prev: 4.0, ep_now: 3.1, delta: -0.9 },
        { code: 3, name: 'Gvardiol', ep_prev: 4.0, ep_now: 4.7, delta: 0.7 },
        { code: 4, name: 'Wirtz', ep_prev: 4.0, ep_now: 4.6, delta: 0.6 },
        { code: 5, name: 'Isak', ep_prev: 4.0, ep_now: 4.6, delta: 0.6 },
      ],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    const line = await screen.findByText(/5 players moved/)
    expect(line.textContent).toContain('Saka')
    expect(line.textContent).toContain('Gvardiol')
    expect(line.textContent).not.toContain('Isak')
  })

  it('shows the strip on a first run of the week when only movers exist',
     async () => {
    // A10: `available` is false, so the old condition hid a true statement.
    serve(NO_PINS, {
      ...EMPTY_DIFF, available: false, ep_movers_count: 1,
      ep_movers: [
        { code: 1, name: 'Saka', ep_prev: 5.0, ep_now: 6.4, delta: 1.4 }],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/1 player moved/)).toBeInTheDocument()
    // and none of the ornaments that only make sense against a previous run.
    // Matched on the delta's own shape rather than a bare /xPts$/, which the
    // breakdown table's own column header answers to.
    expect(screen.queryByText(/^[+−-]?\d+\.\d+ xPts$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/2026-09-03/)).not.toBeInTheDocument()
  })

  it('says nothing about movers when there is no predecessor', async () => {
    serve(NO_PINS, {
      ...EMPTY_DIFF, available: true, changed: true,
      previous_at: '2026-09-03T09:00:00+00:00',
      ep_movers_count: null, ep_movers: [],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    expect(await screen.findByText(/Since last run/)).toBeInTheDocument()
    expect(screen.queryByText(/moved/)).not.toBeInTheDocument()
  })

  it('says nothing when the retrain moved nobody', async () => {
    serve(NO_PINS, {
      ...EMPTY_DIFF, available: true, changed: true,
      ep_movers_count: 0, ep_movers: [],
    })
    render(<MemoryRouter><WhyPanel gw={5} codes={CODES} /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText(/moved/)).not.toBeInTheDocument()
  })
})
