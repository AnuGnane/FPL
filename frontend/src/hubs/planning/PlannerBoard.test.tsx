import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlannerBoard from './PlannerBoard'

const { apiGet, ApiError } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
}))

vi.mock('../../api/client', () => ({
  ApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

const WEEK = {
  gw: 5,
  buys: [{ code: 1, name: 'Wirtz', position: 'MID', ep: 6.1, price: 8.5 }],
  sells: [{ code: 2, name: 'Isak', position: 'FWD', ep: 3.2, price: 9.1 }],
  hits: 0, hit_cost: 0, chip: null, captain: null, vice: null,
  expected_pts: 61.5, bank: 2.1,
}

function plan(weeks: unknown[], bank: number | null = 1.5,
              alternatives: unknown[] = []) {
  // `alternatives` defaults to the empty list every artifact written before
  // v12 serves, so the board's one-plan behaviour is what the whole file
  // exercises unless a test says otherwise (v12 W3 §4.3).
  return { gw: 5, generated_at: '2026-09-01T09:00:00Z', weeks, bank,
           alternatives }
}

function altWeek(over: Record<string, unknown> = {}) {
  return { gw: 5, buys: [], sells: [], hits: 0, hit_cost: 0, chip: null,
           captain: null, vice: null, expected_pts: 58.2, bank: 0.5, ...over }
}

function wire(body: unknown, movers: unknown = { available: true,
  as_of: null, rows: [] }) {
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/prices/movers')
      ? Promise.resolve(movers)
      : Promise.resolve(body)))
}

beforeEach(() => {
  apiGet.mockReset()
  wire(plan([WEEK]))
})

describe('PlannerBoard', () => {
  it('draws one column per week the plan names', async () => {
    wire(plan([
      WEEK, { ...WEEK, gw: 6 }, { ...WEEK, gw: 7 }]))
    render(<PlannerBoard gw={5} />)
    expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
    expect(screen.getByTestId('board-week-6')).toBeInTheDocument()
    expect(screen.getByTestId('board-week-7')).toBeInTheDocument()
  })

  it('draws one column for a one-week horizon, not three with two blanks',
    async () => {
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
      expect(screen.queryByTestId('board-week-6')).toBeNull()
    })

  it('shows the hit cost only when the week takes hits', async () => {
    wire(plan([WEEK, { ...WEEK, gw: 6, hits: 2,
      hit_cost: 8 }]))
    render(<PlannerBoard gw={5} />)
    expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
    expect(screen.queryByTestId('board-hits-5')).toBeNull()
    expect(screen.getByTestId('board-hits-6')).toHaveTextContent('-8')
  })

  it('renders buy and sell prices', async () => {
    render(<PlannerBoard gw={5} />)
    const week = await screen.findByTestId('board-week-5')
    expect(within(week).getByTestId('board-in-1')).toHaveTextContent('8.5')
    expect(within(week).getByTestId('board-out-2')).toHaveTextContent('9.1')
  })

  it('draws a chip when the plan names one and nothing when it does not',
    async () => {
      wire(plan([WEEK, { ...WEEK, gw: 6, chip: 'bboost' }]))
      render(<PlannerBoard gw={5} />)
      const six = await screen.findByTestId('board-week-6')
      expect(within(six).getByText('bboost')).toBeInTheDocument()
      const five = screen.getByTestId('board-week-5')
      expect(within(five).queryByText('bboost')).toBeNull()
    })

  it('draws an em dash for a broken bank, never a zero', async () => {
    wire(plan([WEEK, { ...WEEK, gw: 6, bank: null }]))
    render(<PlannerBoard gw={5} />)
    expect(await screen.findByTestId('board-bank-5')).toHaveTextContent('2.1')
    const blank = screen.getByTestId('board-bank-6')
    expect(blank).toHaveTextContent('—')
    expect(blank).not.toHaveTextContent('0')
  })

  it('distinguishes nothing-advised from a run that solved no horizon',
    async () => {
      apiGet.mockRejectedValue(new ApiError('no advice'))
      const { unmount } = render(<PlannerBoard gw={5} />)
      expect(await screen.findByText('Nothing to plan from'))
        .toBeInTheDocument()
      unmount()

      wire(plan([]))
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByText('This run solved no horizon'))
        .toBeInTheDocument()
    })

  it('warns with a direction and a percentage, and never a price', async () => {
    wire(plan([WEEK]), { available: true, as_of: '2026-09-01T02:00:00Z',
      rows: [{ code: 1, name: 'Wirtz', now_cost: 85,
               price_change_percent: 94.2, direction: 'rise',
               calibrating: false, source: 'plan' }] })
    render(<PlannerBoard gw={5} />)
    const warn = await screen.findByTestId('board-mover-1')
    expect(warn).toHaveTextContent('94%')
    // MoverRow carries no predicted price; a board printing one invents it.
    expect(warn).not.toHaveTextContent('8.6')
    expect(warn).not.toHaveTextContent('85')
  })

  it('draws nothing for a mover the price log is still calibrating',
    async () => {
      wire(plan([WEEK]), { available: true, as_of: null,
        rows: [{ code: 1, name: 'Wirtz', now_cost: 85,
                 price_change_percent: 94.2, direction: 'rise',
                 calibrating: true, source: 'plan' }] })
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
      expect(screen.queryByTestId('board-mover-1')).toBeNull()
    })

  it('draws the whole board when the movers fetch fails', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/prices/movers')
        ? Promise.reject(new ApiError('no price log'))
        : Promise.resolve(plan([WEEK]))))
    render(<PlannerBoard gw={5} />)
    expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
    expect(screen.getByTestId('board-in-1')).toBeInTheDocument()
    expect(screen.queryByTestId('board-mover-1')).toBeNull()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
  })

  it('carries a planned sell as a must-sell rather than as a ban',
    async () => {
      // v11 mapped the sell onto `ban`, which also forbade buying him back
      // and never credited the bank. §4.1 gave the solver the constraint that
      // says "sell him", so the handoff says it and `ban` is left empty.
      const onTry = vi.fn()
      wire(plan([{ ...WEEK, hits: 5, chip: 'bboost' }]))
      render(<PlannerBoard gw={5} onTry={onTry} />)
      await userEvent.click(await screen.findByTestId('board-try-5'))
      expect(onTry).toHaveBeenCalledWith({
        lock: [], ban: [], force_out: [2], force_in: [1],
        // clamped into ConstraintsPanel's 0-3 range
        max_hits: 3, chip: 'bb',
        // the target week is the current one, so one week spans it
        horizon: 1,
      })
    })

  it('prefills a horizon that reaches the week whose moves it carries',
    async () => {
      // GW8's buys over a one-week solve are GW5's buys: the lab starts now,
      // so the constraints have to be applied to a horizon that gets there.
      const onTry = vi.fn()
      wire(plan([WEEK, { ...WEEK, gw: 8 }]))
      render(<PlannerBoard gw={5} onTry={onTry} />)
      await userEvent.click(await screen.findByTestId('board-try-8'))
      expect(onTry.mock.calls[0][0].horizon).toBe(4)
    })

  it('clamps the prefilled horizon to the range the lab accepts',
    async () => {
      const onTry = vi.fn()
      wire(plan([{ ...WEEK, gw: 20 }]))
      render(<PlannerBoard gw={5} onTry={onTry} />)
      await userEvent.click(await screen.findByTestId('board-try-20'))
      expect(onTry.mock.calls[0][0].horizon).toBe(6)
      // …and the sentence says the solve stops short rather than leaving the
      // reader to infer it from a result.
      expect(screen.getByTestId('board-try-note-20'))
        .toHaveTextContent(/stops short of GW20/)
    })

  it('says what a carried-over sell actually means, without a hover',
    async () => {
      render(<PlannerBoard gw={5} onTry={vi.fn()} />)
      expect(await screen.findByText(/does not solve/)).toBeInTheDocument()
      const note = screen.getByTestId('board-try-note-5')
      // The apology for the missing constraint goes with the constraint.
      expect(note.textContent).not.toMatch(/rules out buying him back/i)
      expect(note.textContent).toMatch(/sold in the solve's first week/i)
    })

  it('says the solve starts now, and what that costs a future week',
    async () => {
      wire(plan([WEEK, { ...WEEK, gw: 7 }]))
      render(<PlannerBoard gw={5} onTry={vi.fn()} />)
      const note = await screen.findByTestId('board-try-note-7')
      expect(note).toHaveTextContent(/starts now at GW5/)
      expect(note).toHaveTextContent(/earlier sells first/)
      expect(note).toHaveTextContent(/first week, not scheduled/)
    })

  it('names the hit cap only when the week was actually clamped',
    async () => {
      wire(plan([{ ...WEEK, gw: 5, hits: 5 }, { ...WEEK, gw: 6, hits: 2 }]))
      render(<PlannerBoard gw={5} onTry={vi.fn()} />)
      expect(await screen.findByTestId('board-try-note-5'))
        .toHaveTextContent(/capped at 3/)
      expect(screen.getByTestId('board-try-note-6'))
        .not.toHaveTextContent(/capped at 3/)
    })

  it('renders at 390px with no console error', async () => {
    // §Gates' 390px claim for this view: Planning's cold-clone rail renders
    // only its default tab, which is not the board.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {},
      dispatchEvent: () => false,
    }))
    const { container } = render(<PlannerBoard gw={5} onTry={vi.fn()} />)
    await screen.findByTestId('board-week-5')
    // The board draws no table; the column strip owns its own scroller, so
    // the page does not widen behind it.
    expect(container.querySelectorAll('table')).toHaveLength(0)
    expect(container.querySelector('.overflow-x-auto')).not.toBeNull()
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
    vi.unstubAllGlobals()
  })

  // --- v12 W3 §4.3: Plan A / B / C ----------------------------------------

  it('draws no tab strip when the run banked no alternatives', async () => {
    render(<PlannerBoard gw={5} />)
    await screen.findByTestId('board-week-5')
    // A strip with one tab in it is a control that does nothing.
    expect(screen.queryByTestId('plan-tabs')).toBeNull()
  })

  it('switches to Plan B and draws its weeks', async () => {
    wire(plan([WEEK], 1.5, [
      { label: 'Plan B', gap: 0.4, weeks: [altWeek({
        buys: [{ code: 300, name: 'Other', position: 'MID', ep: 5.1,
                 price: 6.0 }] })] }]))
    render(<PlannerBoard gw={5} />)
    await userEvent.click(await screen.findByRole('button',
                                                  { name: /Plan B/ }))
    expect(await screen.findByTestId('board-in-300')).toBeInTheDocument()
  })

  it('says an alternative is behind, and by how much, in the right frame',
    async () => {
      wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: 0.4, weeks: [] }]))
      render(<PlannerBoard gw={5} />)
      await userEvent.click(await screen.findByRole('button',
                                                    { name: /Plan B/ }))
      const note = await screen.findByTestId('plan-gap')
      expect(note.textContent).toMatch(/0\.4 objective points behind/)
      // The frame, so nobody reads it against the xPts on the same card.
      expect(note.textContent).toMatch(/not a raw xPts gap/)
    })

  it('says AHEAD when the gap is negative, rather than showing a minus sign',
    async () => {
      wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: -1.2, weeks: [] }]))
      render(<PlannerBoard gw={5} />)
      await userEvent.click(await screen.findByRole('button',
                                                    { name: /Plan B/ }))
      expect((await screen.findByTestId('plan-gap')).textContent)
        .toMatch(/1\.2 objective points AHEAD/)
    })

  it('highlights the moves that differ from Plan A', async () => {
    wire(plan([WEEK], 1.5, [
      { label: 'Plan B', gap: 0.4, weeks: [altWeek({
        buys: [{ code: 300, name: 'Other', position: 'MID', ep: 5.1,
                 price: 6.0 }],
        sells: [{ code: 2, name: 'Isak', position: 'FWD', ep: 3.2,
                  price: 9.1 }] })] }]))
    render(<PlannerBoard gw={5} />)
    await userEvent.click(await screen.findByRole('button',
                                                  { name: /Plan B/ }))
    // 300 is not in Plan A's week; 2 is (the fixture's sell).
    expect(screen.getByTestId('board-in-300').dataset.differs).toBe('true')
    expect(screen.getByTestId('board-out-2').dataset.differs).toBe('false')
  })

  it('offers no handoff from an alternative', async () => {
    wire(plan([WEEK], 1.5, [
      { label: 'Plan B', gap: 0.4, weeks: [altWeek({
        buys: [{ code: 300, name: 'Other', position: 'MID', ep: 5.1,
                 price: 6.0 }] })] }]))
    render(<PlannerBoard gw={5} onTry={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button',
                                                  { name: /Plan B/ }))
    expect(screen.queryByTestId('board-try-5')).toBeNull()
  })

  it('wraps the tab strip at 390px rather than adding a second scroller',
    async () => {
      // ChipsTab's established answer for the same control: a strip that wraps
      // inside the column scroller, not a scroller of its own.
      wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: 0.4, weeks: [] }]))
      vi.stubGlobal('innerWidth', 390)
      render(<PlannerBoard gw={5} />)
      const strip = await screen.findByTestId('plan-tabs')
      expect(strip.className).toMatch(/flex-wrap/)
      expect(strip.className).not.toMatch(/overflow-x-auto/)
      vi.unstubAllGlobals()
    })

  // Plan A18: the hub-level cold-clone rail renders only Planning's default
  // tab, so the board's own cold-clone case is asserted here.
  it('renders an empty state on a cold clone with no console error',
    async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      apiGet.mockRejectedValue(new ApiError('no advice on disk yet'))
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
})
