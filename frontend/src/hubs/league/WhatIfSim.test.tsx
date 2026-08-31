import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WhatIfSim from './WhatIfSim'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const SQUAD = [
  { code: 100, name: 'Salah', position: 'MID' },
  { code: 101, name: 'Dud', position: 'DEF' },
]

const RESULT = {
  baseline_p_win: 0.42, p_win: 0.31, delta_p_win: -0.11,
  baseline_exp_finish: 1.6, exp_finish: 2.1, delta_rank: 0.5,
  table: [
    { entry: 1, name: 'Mine', is_you: true, total: 300, p_win: 0.31,
      exp_finish: 2.1 },
    { entry: 2, name: 'Ten Hag Hive', is_you: false, total: 290, p_win: 0.69,
      exp_finish: 0 },
  ],
  unknown_codes: [],
}

describe('WhatIfSim', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiPost.mockReset()
    apiPost.mockResolvedValue(RESULT)
  })

  it('asks for nothing until an event is pinned', () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    expect(apiPost).not.toHaveBeenCalled()
    expect(screen.getByText(/pick an event/i)).toBeInTheDocument()
  })

  it('prices a blank as a change in title odds', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/league/whatif',
      { pins: [{ code: 100, event: 'blank' }], captain_override: null,
        rival_captain_blanks: null }))
    // The tab never sets ``cached_only``: here the simulation is the page,
    // and a 204 would be a blank panel.
    expect(apiPost.mock.calls[0][1]).not.toHaveProperty('cached_only')
    expect(await screen.findByTestId('delta-p-win')).toHaveTextContent('-11')
  })

  it('shows the re-scored table', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByTestId('whatif-row-2')).toHaveTextContent('69%')
  })

  it('clears back to no pins', async () => {
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    await screen.findByTestId('delta-p-win')
    await userEvent.click(screen.getByRole('button', { name: /clear/i }))
    expect(screen.getByText(/pick an event/i)).toBeInTheDocument()
  })

  it('reports a code the server could not resolve', async () => {
    apiPost.mockResolvedValue({ ...RESULT, unknown_codes: [999] })
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByText(/999/)).toBeInTheDocument()
  })

  it('shows a retriable message when the endpoint is down', async () => {
    apiPost.mockRejectedValue(new Error('422'))
    render(<WhatIfSim squad={SQUAD} rivals={[{ entry: 2, name: 'Hive' }]} />)
    await userEvent.click(screen.getByTestId('pin-100-blank'))
    expect(await screen.findByText(/could not be run/i)).toBeInTheDocument()
  })

  it('is an empty state without a squad', () => {
    render(<WhatIfSim squad={[]} rivals={[]} />)
    expect(screen.getByText(/run advise/i)).toBeInTheDocument()
  })
})
