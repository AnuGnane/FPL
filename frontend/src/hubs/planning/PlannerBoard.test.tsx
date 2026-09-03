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

// v12 W3 T4-T7 review, Minor 11: the strip is a tablist, so its controls
// answer to role="tab" rather than to the implicit button role.
const pickPlan = async (label: string) =>
  userEvent.click(await screen.findByRole('tab', { name: label }))

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
    await pickPlan('Plan B')
    expect(await screen.findByTestId('board-in-300')).toBeInTheDocument()
  })

  it('says an alternative is behind, and by how much, in the right frame',
    async () => {
      wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: 0.4, weeks: [] }]))
      render(<PlannerBoard gw={5} />)
      await pickPlan('Plan B')
      const note = await screen.findByTestId('plan-gap')
      expect(note.textContent).toMatch(/0\.4 objective points behind/)
      // The frame, so nobody reads it against the xPts on the same card.
      expect(note.textContent).toMatch(/not a raw xPts gap/)
    })

  it('says AHEAD when the gap is negative, rather than showing a minus sign',
    async () => {
      wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: -1.2, weeks: [] }]))
      render(<PlannerBoard gw={5} />)
      await pickPlan('Plan B')
      const note = (await screen.findByTestId('plan-gap')).textContent
      expect(note).toMatch(/1\.2 objective points AHEAD/)
      // T4-T7 review, Important 3: there are two reasons an alternative can
      // price above the recommendation, and the caption used to name only
      // the sweep's constraint. §F1's second pass takes each plan's bench and
      // vice scales from its own XI, so a small gap either way can be that.
      expect(note).toMatch(/bench weightings differ/)
    })

  it('highlights the moves that differ from Plan A', async () => {
    wire(plan([WEEK], 1.5, [
      { label: 'Plan B', gap: 0.4, weeks: [altWeek({
        buys: [{ code: 300, name: 'Other', position: 'MID', ep: 5.1,
                 price: 6.0 }],
        sells: [{ code: 2, name: 'Isak', position: 'FWD', ep: 3.2,
                  price: 9.1 }] })] }]))
    render(<PlannerBoard gw={5} />)
    await pickPlan('Plan B')
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
    await pickPlan('Plan B')
    expect(screen.queryByTestId('board-try-5')).toBeNull()
  })

  it('wraps the tab strip rather than adding a second scroller', async () => {
    // ChipsTab's established answer for the same control: a strip that wraps
    // inside the column scroller, not a scroller of its own.
    //
    // T4-T7 review, Minor 12: this used to stub innerWidth to 390 and then
    // assert a static className, which is true at every width — a test that
    // claimed a viewport it never exercised. jsdom applies no CSS, so the
    // honest claim is the one below: wrapping is unconditional, and no
    // breakpoint prefix hides it at a narrow width.
    wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: 0.4, weeks: [] }]))
    render(<PlannerBoard gw={5} />)
    const strip = await screen.findByTestId('plan-tabs')
    expect(strip.className).toMatch(/(^|\s)flex-wrap(\s|$)/)
    expect(strip.className).not.toMatch(/overflow-x-auto/)
  })

  it('is a tablist whose selected tab names the board it controls', async () => {
    // T4-T7 review, Minor 11. aria-pressed said "this control is on"; these
    // controls swap the panel below, which is what a tab does.
    wire(plan([WEEK], 1.5, [{ label: 'Plan B', gap: 0.4, weeks: [altWeek()] }]))
    render(<PlannerBoard gw={5} />)
    const strip = await screen.findByTestId('plan-tabs')
    expect(strip).toHaveAttribute('role', 'tablist')
    const tabs = within(strip).getAllByRole('tab')
    expect(tabs.map((t) => t.getAttribute('aria-selected')))
      .toEqual(['true', 'false'])
    const board = document.getElementById('plan-board')
    expect(board).toHaveAttribute('role', 'tabpanel')
    expect(tabs.every((t) => t.getAttribute('aria-controls') === 'plan-board'))
      .toBe(true)
    await pickPlan('Plan B')
    expect(tabs.map((t) => t.getAttribute('aria-selected')))
      .toEqual(['false', 'true'])
    expect(board).toHaveAttribute('aria-labelledby', tabs[1].id)
  })

  it('gives the tab strip a roving tabindex and arrow keys', async () => {
    // T8-T11 review, Minor 9. A tablist is one tab stop, not one per tab, and
    // the arrows move between them — which is the half of the ARIA pattern
    // Minor 11 added the roles without.
    wire(plan([WEEK], 1.5, [
      { label: 'Plan B', gap: 0.4, weeks: [altWeek()] },
      { label: 'Plan C', gap: 0.9, weeks: [altWeek({ expected_pts: 57.1 })] },
    ]))
    render(<PlannerBoard gw={5} />)
    const strip = await screen.findByTestId('plan-tabs')
    const tabs = within(strip).getAllByRole('tab')
    const roving = () => tabs.map((t) => t.getAttribute('tabindex'))
    expect(roving()).toEqual(['0', '-1', '-1'])

    tabs[0].focus()
    await userEvent.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(tabs[1])
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(roving()).toEqual(['-1', '0', '-1'])

    await userEvent.keyboard('{End}')
    expect(document.activeElement).toBe(tabs[2])
    // Wraps, so the last tab's Right is the first: a strip is a ring.
    await userEvent.keyboard('{ArrowRight}')
    expect(document.activeElement).toBe(tabs[0])
    await userEvent.keyboard('{ArrowLeft}')
    expect(document.activeElement).toBe(tabs[2])
    await userEvent.keyboard('{Home}')
    expect(document.activeElement).toBe(tabs[0])
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('leaves the board unlabelled when there is no strip to control',
    async () => {
      // No tablist, no tabpanel: a panel that answers to a control nobody
      // drew is a role with nothing on the other end of it.
      render(<PlannerBoard gw={5} />)
      await screen.findByTestId('board-week-5')
      expect(document.getElementById('plan-board'))
        .not.toHaveAttribute('role')
    })

  // v12 W5 §6.5 — "Why this move". Accounting over the objective's own terms
  // at the plan the solver returned; the board still never solves.
  describe('the move trace', () => {
    const MOVE = {
      buy_code: 1, buy_name: 'Wirtz', sell_code: 2, sell_name: 'Isak',
      ep_gain: 3.5, lambda_tilt: 0.0, note: '',
    }
    const TRACE = {
      gw: 5, moves: [MOVE], ep_gain: 3.5, hit_cost: 0, ft_used: 1,
      ft_after: 1, ft_use_penalty: 0, ft_shadow: 1.5, ft_basis: 'flat',
      bank_value: null, theta: null, price_charge: 0, note: '',
    }
    const open = async (gw = 5) => {
      const why = await screen.findByTestId(`board-why-${gw}`)
      await userEvent.click(within(why).getByText('Why this move'))
      return why
    }

    it('renders the pair and its signed gain', async () => {
      wire(plan([{ ...WEEK, trace: TRACE }]))
      render(<PlannerBoard gw={5} />)
      const why = await open()
      const move = within(why).getByTestId('board-why-move-5-1')
      expect(move).toHaveTextContent('Isak → Wirtz')
      // Signed, because the sign is the whole claim: fmtDelta prints '+3.5'.
      expect(move).toHaveTextContent('+3.5')
    })

    it('renders an em dash and the note for a gain it could not price',
      async () => {
        // Never a zero. "We could not price this" and "this swap is worth
        // nothing" are different facts and must not print the same.
        wire(plan([{ ...WEEK,
          trace: { ...TRACE,
            moves: [{ ...MOVE, ep_gain: null,
              note: 'player 2 is not in the pool the solver used' }],
            ep_gain: null } }]))
        render(<PlannerBoard gw={5} />)
        const why = await open()
        const move = within(why).getByTestId('board-why-move-5-1')
        expect(move).toHaveTextContent('—')
        expect(move).not.toHaveTextContent('0.0')
        expect(move).toHaveTextContent('not in the pool')
      })

    it('says a week does nothing rather than showing an empty list',
      async () => {
        wire(plan([{ ...WEEK, buys: [], sells: [],
          trace: { ...TRACE, moves: [], ep_gain: 0 } }]))
        render(<PlannerBoard gw={5} />)
        const why = await open()
        expect(within(why).getByText('No moves this week.'))
          .toBeInTheDocument()
      })

    it('draws no disclosure at all for a week with no trace', async () => {
      // A payload from a server older than the field, or a trace that threw:
      // the plan still draws, without a control that would open on nothing.
      wire(plan([{ ...WEEK, trace: null }]))
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByTestId('board-week-5')).toBeInTheDocument()
      expect(screen.queryByTestId('board-why-5')).toBeNull()
    })

    it('prints the disclaimer with the numbers rather than behind a hover',
      async () => {
        // A caveat discovered by hovering is a caveat discovered after the
        // decision — and it has to name the terms that are missing, or a
        // reader adds these lines up and asks why they miss the xPts.
        wire(plan([{ ...WEEK, trace: TRACE }]))
        render(<PlannerBoard gw={5} />)
        const why = await open()
        expect(why).toHaveTextContent('the board never re-solves')
        expect(why).toHaveTextContent(
          'captain, vice and bench weightings are not attributed here')
      })

    it('shows the week note and no charge line when the charge is null',
      async () => {
        wire(plan([{ ...WEEK,
          trace: { ...TRACE, price_charge: null,
            note: 'price_timing is off, so the plan was solved without a '
                  + 'price-timing term' } }]))
        render(<PlannerBoard gw={5} />)
        const why = await open()
        expect(within(why).queryByText(/price-timing charge/)).toBeNull()
        expect(within(why).getByTestId('board-why-note-5'))
          .toHaveTextContent('price_timing is off')
      })

    it('shows no charge line for a charge of zero', async () => {
      // The first week is never charged the term, and a "−0.000" would read
      // as a charge that was checked and found to be nothing.
      wire(plan([{ ...WEEK, trace: { ...TRACE, price_charge: 0 } }]))
      render(<PlannerBoard gw={5} />)
      const why = await open()
      expect(within(why).queryByText(/price-timing charge/)).toBeNull()
    })

    it('says the alternatives carry no trace instead of showing nothing',
      async () => {
        // An absent control is not an explanation. Plan B came out of a
        // different solve, so its weeks carry no trace and the board says why.
        wire(plan([{ ...WEEK, trace: TRACE }], 1.5, [
          { label: 'Plan B', gap: 0.4, weeks: [altWeek({ trace: null })] },
        ]))
        render(<PlannerBoard gw={5} />)
        await open()
        // Not on Plan A, which *has* the trace: a caveat left standing on the
        // page it does not apply to teaches the reader to ignore it.
        expect(screen.queryByTestId('plan-no-trace')).toBeNull()
        await pickPlan('Plan B')
        expect(screen.queryByTestId('board-why-5')).toBeNull()
        expect(screen.getByTestId('plan-no-trace'))
          .toHaveTextContent('shown for Plan A only')
      })
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
