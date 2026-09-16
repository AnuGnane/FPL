import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetPageData } from '../../api/pageData'
import HistoryTab from './HistoryTab'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    // The chart itself needs the measured box: cloning it with a fixed one is
    // what the real container does once it has measured.
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

const DIFF = {
  gw: 3, gw_from: 2, gw_to: 3, available: true, changed: true,
  current_at: null, previous_at: null,
  buys_added: [{ code: 9, name: 'Bruno Fernandes' }],
  buys_dropped: [{ code: 8, name: 'Palmer' }],
  sells_added: [], sells_dropped: [],
  captain_from: { code: 1, name: 'Salah' },
  captain_to: { code: 2, name: 'Haaland' },
  chip_from: null, chip_to: null, expected_pts_delta: 1.4,
  ep_movers: [], ep_movers_count: null,
}

const HISTORY = {
  runs: [
    { gw: 3, deadline: '2026-09-11T17:30:00Z', captain: 'Salah',
      buys: ['Salah'], sells: ['Dud'], hits: 1, expected_pts: 61.5,
      actual_pts: null },
    { gw: 2, deadline: '2026-09-04T17:30:00Z', captain: 'Salah',
      buys: [], sells: [], hits: 0, expected_pts: 58.0, actual_pts: 64 },
  ],
  prices: [{ code: 100, name: 'Salah',
             points: [{ gw: 1, price: 12.9 }, { gw: 2, price: 13.0 }] }],
  backtests: [{ season: '2025-26', from_gw: 5, total: 1834 }],
}

beforeEach(() => {
  resetPageData()
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => Promise.resolve(
    path.startsWith('/api/advice/diff') ? DIFF : HISTORY))
})

describe('HistoryTab', () => {
  it('pairs expected with actual and charts prices', async () => {
    render(<MemoryRouter><HistoryTab /></MemoryRouter>)
    expect(await screen.findByText('61.5')).toBeInTheDocument()
    expect(screen.getByText('64')).toBeInTheDocument()
    expect(screen.getByText('not resolved yet')).toBeInTheDocument()
    expect(screen.getByLabelText('Price history')).toBeInTheDocument()
    expect(screen.getByText(/2025-26/)).toBeInTheDocument()
  })
})

describe('the Compare card (v19e §2.2)', () => {
  it('opens on the two newest gameweeks in the history', async () => {
    render(<MemoryRouter><HistoryTab /></MemoryRouter>)
    expect(await screen.findByLabelText('From')).toHaveValue('2')
    expect(screen.getByLabelText('To')).toHaveValue('3')
    await waitFor(() => expect(apiGet)
      .toHaveBeenCalledWith('/api/advice/diff?a=2&b=3'))
    expect(screen.getByText(/buying Bruno Fernandes instead of Palmer/))
      .toBeInTheDocument()
  })

  it('asks for the comparison the reader picked, not the one it opened on',
    async () => {
      render(<MemoryRouter><HistoryTab /></MemoryRouter>)
      await screen.findByLabelText('From')
      await userEvent.selectOptions(screen.getByLabelText('To'), '2')
      await waitFor(() => expect(apiGet)
        .toHaveBeenCalledWith('/api/advice/diff?a=2&b=2'))
    })

  it('says a week has no served plan rather than drawing an empty sentence',
    async () => {
      apiGet.mockImplementation((path: string) => Promise.resolve(
        path.startsWith('/api/advice/diff')
          ? { ...DIFF, available: false } : HISTORY))
      render(<MemoryRouter><HistoryTab /></MemoryRouter>)
      expect(await screen.findByText(
        'no served plan for one of these gameweeks')).toBeInTheDocument()
    })
})
