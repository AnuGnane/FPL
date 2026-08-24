import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import History from './History'

const apiGet = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({
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
  })
})

describe('History', () => {
  it('pairs expected with actual and charts prices', async () => {
    render(<MemoryRouter><History /></MemoryRouter>)
    expect(await screen.findByText('61.5')).toBeInTheDocument()
    expect(screen.getByText('64')).toBeInTheDocument()
    expect(screen.getByText('not resolved yet')).toBeInTheDocument()
    expect(screen.getByLabelText('Price history')).toBeInTheDocument()
    expect(screen.getByText(/2025-26/)).toBeInTheDocument()
  })
})
