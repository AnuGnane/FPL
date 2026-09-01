import { render, screen, within } from '@testing-library/react'
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

function plan(weeks: unknown[], bank: number | null = 1.5) {
  return { gw: 5, generated_at: '2026-09-01T09:00:00Z', weeks, bank }
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(plan([WEEK]))
})

describe('PlannerBoard', () => {
  it('draws one column per week the plan names', async () => {
    apiGet.mockResolvedValue(plan([
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
    apiGet.mockResolvedValue(plan([WEEK, { ...WEEK, gw: 6, hits: 2,
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
      apiGet.mockResolvedValue(plan([WEEK, { ...WEEK, gw: 6, chip: 'bboost' }]))
      render(<PlannerBoard gw={5} />)
      const six = await screen.findByTestId('board-week-6')
      expect(within(six).getByText('bboost')).toBeInTheDocument()
      const five = screen.getByTestId('board-week-5')
      expect(within(five).queryByText('bboost')).toBeNull()
    })

  it('draws an em dash for a broken bank, never a zero', async () => {
    apiGet.mockResolvedValue(plan([WEEK, { ...WEEK, gw: 6, bank: null }]))
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

      apiGet.mockResolvedValue(plan([]))
      render(<PlannerBoard gw={5} />)
      expect(await screen.findByText('This run solved no horizon'))
        .toBeInTheDocument()
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
