import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Planning from './Planning'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('./planning/Timeline', () => ({
  default: () => <p>timeline panel</p>,
}))
vi.mock('./planning/WhatIfTab', () => ({ default: () => <p>whatif panel</p> }))
vi.mock('./planning/ChipsTab', () => ({ default: () => <p>chips panel</p> }))
vi.mock('./planning/TickerTab', () => ({ default: () => <p>ticker panel</p> }))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({
    gw: 5, mode: 'weekly', deadline: '2099-09-18T17:30:00Z',
    advice: { expected_pts: 61.5 },
    staleness: { advice_gw: 5, current_gw: 5,
                 generated_at: '2026-08-29T09:00:00Z',
                 deadline: '2099-09-18T17:30:00Z', deadline_passed: false,
                 stale: false, reason: 'current for GW5',
                 data_through_gw: 4, data_warning: null },
  })
})

describe('Planning hub', () => {
  it('opens on the timeline tab', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    expect(await screen.findByText('timeline panel')).toBeInTheDocument()
  })

  it('lists all four tabs', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    for (const name of ['Timeline', 'What-If', 'Chips', 'Ticker']) {
      expect(await screen.findByRole('tab', { name })).toBeInTheDocument()
    }
  })

  it('switches to the what-if tab on click', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab', { name: 'What-If' }))
    expect(await screen.findByText('whatif panel')).toBeInTheDocument()
  })

  it('shows an empty state when there is no advice at all', async () => {
    apiGet.mockRejectedValue(Object.assign(
      new Error('no advice on disk yet — run `gaffer advise` first'),
      { status: 422 }))
    render(<MemoryRouter><Planning /></MemoryRouter>)
    expect(await screen.findByText(/nothing planned yet/i)).toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
  })
})
