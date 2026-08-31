import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WhatIfRequest } from '../../types'
import DraftsTab from './DraftsTab'

const { apiDelete, apiGet, apiPost } = vi.hoisted(() => ({
  apiDelete: vi.fn(), apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: (path: string) => apiDelete(path),
}))

const CURRENT: WhatIfRequest = {
  lock: [100], ban: [], force_in: [], max_hits: 1, chip: 'none',
  horizon: null,
}

const EMPTY_CONSTRAINTS: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}

function draft(name: string) {
  return { name, created_at: '2026-08-31T09:00:00+00:00',
           constraints: EMPTY_CONSTRAINTS }
}

const LIST = { drafts: [draft('keep Salah'), draft('go wildcard')] }

const COMPARE = {
  gw: 5,
  weeks: 4,
  rows: [
    { name: 'the optimum', is_reference: true,
      solved_at: '2026-08-31T09:10:00+00:00', horizon_pts: 210.4,
      expected_pts: 61.5, delta_xpts: 0, hits: 0, chip: null,
      buys: [{ code: 100, name: 'Salah', ep: 6.4 }],
      sells: [{ code: 101, name: 'Bloke', ep: 2.0 }],
      captain: { code: 100, name: 'Salah', ep: 6.4 }, error: null },
    { name: 'keep Salah', is_reference: false,
      solved_at: '2026-08-31T09:10:00+00:00', horizon_pts: 207.1,
      expected_pts: 60.0, delta_xpts: -3.3, hits: 1, chip: null,
      buys: [], sells: [],
      captain: { code: 100, name: 'Salah', ep: 6.4 }, error: null },
    { name: 'go wildcard', is_reference: false,
      solved_at: '2026-08-31T09:10:00+00:00', horizon_pts: null,
      expected_pts: null, delta_xpts: null, hits: null, chip: null,
      buys: [], sells: [], captain: null,
      error: 'no legal squad satisfies this draft' },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiDelete.mockReset()
  apiGet.mockImplementation((path: string) => (
    path === '/api/drafts' ? Promise.resolve(LIST)
      : Promise.resolve({ id: 'j1', status: 'done', result: COMPARE,
                          error: null })))
  apiPost.mockResolvedValue({ job_id: 'j1' })
})

describe('DraftsTab', () => {
  it('says so when nothing is saved', async () => {
    apiGet.mockResolvedValue({ drafts: [] })
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    expect(await screen.findByText('No drafts yet.')).toBeInTheDocument()
  })

  it('saves the constraints the What-If tab is holding', async () => {
    apiPost.mockResolvedValue({ drafts: [...LIST.drafts, draft('third')] })
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await screen.findByText('keep Salah')
    await userEvent.type(screen.getByLabelText('draft name'), 'third')
    await userEvent.click(screen.getByRole('button',
      { name: /save the current what-if/i }))
    expect(apiPost).toHaveBeenCalledWith('/api/drafts',
      { name: 'third', constraints: CURRENT })
    expect(await screen.findByText('third')).toBeInTheDocument()
  })

  it('refuses to save a draft with no name', async () => {
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await screen.findByText('keep Salah')
    expect(screen.getByRole('button',
      { name: /save the current what-if/i })).toBeDisabled()
  })

  it('shows why a save was refused', async () => {
    apiPost.mockRejectedValue(new Error('a draft called third already exists'))
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await screen.findByText('keep Salah')
    await userEvent.type(screen.getByLabelText('draft name'), 'third')
    await userEvent.click(screen.getByRole('button',
      { name: /save the current what-if/i }))
    expect(await screen.findByText(/already exists/)).toBeInTheDocument()
  })

  it('compares the ticked drafts and renders the reference row first',
    async () => {
      render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
      await userEvent.click(await screen.findByLabelText(
        'compare keep Salah'))
      await userEvent.click(screen.getByRole('button', { name: 'Compare' }))
      await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
        '/api/drafts/compare', { names: ['keep Salah'] }))
      expect(await screen.findByText('Compared over 4 weeks'))
        .toBeInTheDocument()
      const rows = screen.getAllByRole('row').slice(1)
      expect(rows[0].textContent).toContain('the optimum')
      // The reference row has nothing to be worse than, so it prints no delta.
      expect(rows[1].textContent).toContain('-3.3')
      expect(screen.getByText(/against the saved GW5 board/))
        .toBeInTheDocument()
    })

  it('gives an infeasible draft a row carrying its reason', async () => {
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await userEvent.click(await screen.findByLabelText('compare go wildcard'))
    await userEvent.click(screen.getByRole('button', { name: 'Compare' }))
    expect(await screen.findByText('no legal squad satisfies this draft'))
      .toBeInTheDocument()
  })

  it('caps a comparison at six drafts', async () => {
    const many = { drafts: ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map(draft) }
    apiGet.mockImplementation((path: string) => (
      path === '/api/drafts' ? Promise.resolve(many) : Promise.resolve({})))
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await screen.findByText('a')
    for (const name of ['a', 'b', 'c', 'd', 'e', 'f']) {
      await userEvent.click(screen.getByLabelText(`compare ${name}`))
    }
    expect(screen.getByLabelText('compare g')).toBeDisabled()
    // The six already ticked stay clickable, so a choice can be swapped.
    expect(screen.getByLabelText('compare a')).not.toBeDisabled()
  })

  it('deletes a draft through DELETE', async () => {
    apiDelete.mockResolvedValue({ drafts: [draft('go wildcard')] })
    render(<MemoryRouter><DraftsTab current={CURRENT} /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'delete keep Salah' }))
    expect(apiDelete).toHaveBeenCalledWith('/api/drafts/keep%20Salah')
    await waitFor(() => expect(screen.queryByText('keep Salah'))
      .not.toBeInTheDocument())
  })
})
