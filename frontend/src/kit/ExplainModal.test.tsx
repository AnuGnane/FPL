import { fireEvent, render, screen } from '@testing-library/react'
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

  it('asks this backend for the portrait, by the code it was opened with', async () => {
    render(<ExplainModal code={223094} onClose={() => {}} />)
    const photo = await screen.findByTestId('explain-photo')
    // Never premierleague.com: the frontend speaks only to this backend, and
    // a hotlinked face is the one request on the page that would tell a third
    // party who is reading it.
    expect(photo).toHaveAttribute('src', '/api/assets/photo/223094')
  })

  it('prints the code, which is what the override file is keyed by',
    async () => {
      // data/set_pieces.toml wants codes, not element ids, and this header is
      // the only place in the app one is printed. A user told to "list takers
      // by code" has to be able to find one.
      render(<ExplainModal code={100} onClose={() => {}} />)
      expect(await screen.findByText('code 100')).toBeInTheDocument()
    })

  it('badges the set-piece orders the override file decided', async () => {
    apiGet.mockReset()
    apiGet.mockResolvedValue({
      code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
      ep_next: 9.0, fixtures: [fixture(3, 9.0)], next_fixtures: [],
      set_pieces: { penalties: 1, free_kicks: null, corners: 2 },
      set_pieces_manual: ['corners', 'penalties'],
    })
    render(<ExplainModal code={100} onClose={() => {}} />)
    const badge = await screen.findByText('manual')
    expect(badge).toHaveAttribute('title', 'Your override: corners, penalties')
  })

  it('shows no badge when the payload predates the field', async () => {
    // The beforeEach fixture omits set_pieces_manual entirely, which is what
    // an older server sends: read through `?? []`, that is "nothing
    // overridden" and not a crash.
    render(<ExplainModal code={100} onClose={() => {}} />)
    await screen.findByText(/Set pieces/)
    expect(screen.queryByText('manual')).not.toBeInTheDocument()
  })

  it('drops the portrait rather than leaving a broken image', async () => {
    render(<ExplainModal code={223094} onClose={() => {}} />)
    const photo = await screen.findByTestId('explain-photo')
    // The server answers a dead CDN with a bundled silhouette, so this path is
    // only reached when even that fails. A broken-image glyph in the header of
    // a modal about expected points is worse than no picture at all.
    fireEvent.error(photo)
    expect(screen.queryByTestId('explain-photo')).not.toBeInTheDocument()
  })
})
