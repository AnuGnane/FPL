import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ExplainModal from './ExplainModal'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it (same pattern as WhatIf.test.tsx).
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

function fixture(gw: number, ep: number) {
  return {
    gw, opponent: 'Arsenal', home: gw % 2 === 1, kickoff_time: null,
    components: [{ label: 'Attacking', points: ep / 2 }],
    minutes: { p_play: 0.9, p60: 0.8 }, calibration_delta: 0.2,
    odds: { weight: 0.7, e_goals_against: 1.1, p_cs_model: 0.25,
            p_cs_blended: 0.32, e_gc_model: 1.4, e_gc_blended: 1.2 },
    ep,
  }
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue({
    code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
    ep_next: 9.0, fixtures: [fixture(3, 6.4), fixture(3, 2.6)],
    next_fixtures: [{ gw: 4, opponent: 'Chelsea', home: false }],
    set_pieces: { penalties: 1, free_kicks: null, corners: null },
  })
})

describe('ExplainModal', () => {
  it('totals a double gameweek across its fixtures', async () => {
    render(<ExplainModal code={100} onClose={() => {}} />)
    expect(await screen.findByText(/GW3 total: 9 xPts across 2 fixtures/))
      .toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    render(<ExplainModal code={100} onClose={onClose} />)
    await screen.findByRole('dialog')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on a backdrop click and focuses its close button', async () => {
    const onClose = vi.fn()
    render(<ExplainModal code={100} onClose={onClose} />)
    const close = await screen.findByRole('button', { name: 'Close' })
    expect(close).toHaveFocus()
    await userEvent.click(screen.getByTestId('modal-backdrop'))
    expect(onClose).toHaveBeenCalled()
  })

  it('ignores a stale response when the code changes mid-flight', async () => {
    const slow = {
      code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
      ep_next: 9.0, fixtures: [fixture(3, 6.4)], next_fixtures: [],
      set_pieces: { penalties: null, free_kicks: null, corners: null },
    }
    const fresh = { ...slow, code: 101, name: 'Bloke', ep_next: 2.0 }
    apiGet.mockReset()
    apiGet.mockImplementationOnce(
      () => new Promise((resolve) => setTimeout(() => resolve(slow), 50)))
    apiGet.mockResolvedValue(fresh)

    const { rerender } = render(
      <ExplainModal code={100} onClose={() => {}} />)
    rerender(<ExplainModal code={101} onClose={() => {}} />)
    expect(await screen.findByText(/Bloke/)).toBeInTheDocument()
    await new Promise((resolve) => setTimeout(resolve, 80))
    expect(screen.queryByText(/Salah/)).not.toBeInTheDocument()
  })
})
