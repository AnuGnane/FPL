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
  default: ({ teamByCode }: { teamByCode?: Map<number, number> }) => (
    <>
      <p>timeline panel</p>
      <p>{teamByCode ? `teams:${teamByCode.size}` : 'no map'}</p>
    </>
  ),
}))
vi.mock('./planning/WhatIfTab', () => ({ default: () => <p>whatif panel</p> }))
vi.mock('./planning/ChipsTab', () => ({ default: () => <p>chips panel</p> }))
vi.mock('./planning/DraftsTab', () => ({ default: () => <p>drafts panel</p> }))
vi.mock('./planning/TickerTab', () => ({ default: () => <p>ticker panel</p> }))

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({
    gw: 5, mode: 'weekly', deadline: '2099-09-18T17:30:00Z',
    advice: {
      expected_pts: 61.5,
      // v9a enriches the six player keys with team_code on the way out;
      // Planning keeps the code→team map for the timeline's fixture chips
      // and makes no request of its own for it (plan A11).
      xi: [{ code: 3, name: 'Salah', ep: 6.4, team_code: 14 }],
      bench: [], buys: [], sells: [],
      captain: { code: 3, name: 'Salah', ep: 6.4, team_code: 14 },
      vice: { code: 4, name: 'Saka', ep: 5.5, team_code: null },
    },
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

  it('lists all five tabs', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    for (const name of ['Timeline', 'What-If', 'Drafts', 'Chips', 'Ticker']) {
      expect(await screen.findByRole('tab', { name })).toBeInTheDocument()
    }
  })

  it('switches to the drafts tab on click', async () => {
    render(<MemoryRouter><Planning /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab', { name: 'Drafts' }))
    expect(await screen.findByText('drafts panel')).toBeInTheDocument()
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

  it('hands the timeline a code-to-team map from the advice it already has',
    async () => {
      // No extra request: the enrichment rides on /api/advice/latest, and a
      // player the payload never named is absent rather than guessed (A11).
      render(<MemoryRouter><Planning /></MemoryRouter>)
      expect(await screen.findByText(/teams:1/)).toBeInTheDocument()
    })
})
