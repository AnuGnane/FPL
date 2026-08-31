import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhatIfTab from './WhatIfTab'

// vi.mock's factory is hoisted above the file body, so the fake error class
// and the spies have to be hoisted with it.
const { FakeApiError, apiGet, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super('failed')
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
  apiDelete: vi.fn(),
}))

// The tab now mounts the sensitivity and pins cards, which have their own
// tests. Stub them so this file keeps testing the solve and nothing else.
vi.mock('./SensitivityCard', () => ({ default: () => <p>sensitivity card</p> }))
vi.mock('./OverridesCard', () => ({ default: () => <p>pins card</p> }))

const PLAYERS = [
  { code: 100, name: 'Salah', position: 'MID', price: 13.0, ep_next: 6.4 },
  { code: 101, name: 'Bloke', position: 'DEF', price: 4.5, ep_next: 2.0 },
]

const RESULT = {
  baseline: {
    gw: 3,
    xi: [{ code: 100, name: 'Salah', position: 'MID', ep: 6.4 }],
    bench: [], captain: { code: 100, name: 'Salah', position: 'MID', ep: 6.4 },
    vice: { code: 101, name: 'Bloke', position: 'DEF', ep: 2.0 },
    buys: [{ code: 100, name: 'Salah', position: 'MID', ep: 6.4 }],
    sells: [], hits: 0, expected_pts: 61.5, horizon_pts: 120.4,
  },
  yours: {
    gw: 3,
    xi: [{ code: 101, name: 'Bloke', position: 'DEF', ep: 2.0 }],
    bench: [], captain: { code: 101, name: 'Bloke', position: 'DEF', ep: 2.0 },
    vice: { code: 101, name: 'Bloke', position: 'DEF', ep: 2.0 },
    buys: [], sells: [], hits: 0, expected_pts: 58.7, horizon_pts: 117.6,
  },
  delta_xpts: -2.8,
  xi_in: [{ code: 101, name: 'Bloke', position: 'DEF', ep: 2.0 }],
  xi_out: [{ code: 100, name: 'Salah', position: 'MID', ep: 6.4 }],
  transfers_changed: true,
  captain_changed: true,
  verdict: 'your version costs 2.8 expected points',
}

// The page embeds the read-only fixture ticker, so every mock has to answer
// its GET as well as the solve's.
const TICKER = {
  gws: [3], source: 'elo',
  teams: [{ code: 300, name: 'Liverpool', short_name: 'LIV',
            mean_difficulty: 0.2,
            cells: [{ gw: 3, opponent: 'ARS', home: true, difficulty: 0.2 }] }],
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/players?')) return PLAYERS
    if (path.startsWith('/api/fixtures/ticker')) return TICKER
    if (path.startsWith('/api/jobs/')) {
      return { id: 'j1', status: 'done', result: RESULT, error: null }
    }
    throw new Error(`unexpected GET ${path}`)
  })
})

describe('what-if tab', () => {
  it('carries the robustness and pins cards beside the solve', async () => {
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    expect(await screen.findByText('sensitivity card')).toBeInTheDocument()
    expect(screen.getByText('pins card')).toBeInTheDocument()
  })

  it('lets the hub own the constraints so a draft can save them', async () => {
    // Controlled: Planning holds them above the tab, because Radix unmounts
    // an unselected tab and the Drafts tab would otherwise save a default.
    const onChange = vi.fn()
    render(
      <MemoryRouter>
        <WhatIfTab
          value={{ lock: [], ban: [], force_in: [], max_hits: 2,
                   chip: 'none', horizon: null }}
          onChange={onChange}
        />
      </MemoryRouter>)
    const select = await screen.findByLabelText('Max hits') as
      HTMLSelectElement
    expect(select.value).toBe('2')
    await userEvent.selectOptions(select, '1')
    expect(onChange).toHaveBeenCalled()
  })

  it('sends the constraints and renders the diff and verdict', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1' })
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)

    await userEvent.type(screen.getByLabelText('Ban'), 'Sal')
    await userEvent.click(await screen.findByRole('button',
      { name: /Salah/ }))
    await userEvent.selectOptions(screen.getByLabelText('Max hits'), '1')
    await userEvent.selectOptions(screen.getByLabelText('Chip'), 'bb')
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))

    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/whatif', {
      lock: [], ban: [100], force_in: [], max_hits: 1, chip: 'bb',
      horizon: null,
    }))
    expect(await screen.findByText('your version costs 2.8 expected points'))
      .toBeInTheDocument()
    expect(screen.getByText('61.5')).toBeInTheDocument()
    expect(screen.getByText('58.7')).toBeInTheDocument()
    expect(screen.getByText('120.4')).toBeInTheDocument()
    expect(screen.getByText('117.6')).toBeInTheDocument()
    // The dead `.changed` class is gone; the row states it as data instead.
    expect(screen.getAllByRole('row').some(
      (row) => row.getAttribute('data-changed') === 'true')).toBe(true)
  })

  it('labels the points rows as captain-inclusive and net of hits', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1' })
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    expect(await screen.findByText(
      /xPts this GW \(incl\. captain, after hits\)/)).toBeInTheDocument()
    expect(screen.getByText(
      /xPts over horizon \(incl\. captain, after hits\)/)).toBeInTheDocument()
  })

  it('starts with max hits pinned to zero, not empty', async () => {
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    const select = screen.getByLabelText('Max hits') as HTMLSelectElement
    expect(select.value).toBe('0')
  })

  it('shows a structured infeasibility inline', async () => {
    apiPost.mockRejectedValue(new FakeApiError(422, {
      constraint: 'lock_and_ban',
      error: 'player 100 cannot be both locked in and banned',
      players: [100],
    }))
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    expect(await screen.findByText(/cannot be both locked in and banned/))
      .toBeInTheDocument()
    expect(screen.getByText(/lock_and_ban/)).toBeInTheDocument()
  })

  it('shows a solver failure from the job record', async () => {
    apiPost.mockResolvedValue({ job_id: 'j2' })
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/players?')) return PLAYERS
      if (path.startsWith('/api/fixtures/ticker')) return TICKER
      return { id: 'j2', status: 'error', result: null,
               error: 'no legal squad satisfies those constraints' }
    })
    render(<MemoryRouter><WhatIfTab /></MemoryRouter>)
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    expect(await screen.findByText(/no legal squad/)).toBeInTheDocument()
  })
})
