import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LadderPayload } from '../../types'
import LadderCard, { capText } from './LadderCard'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

// The wire ref carries the identity fields too; they are null here because
// nothing this card renders reads them, and a partial literal would not
// type-check against `LadderWeek`.
const ref = (code: number, name: string, ep = 5.0) =>
  ({ code, name, position: 'MID', ep,
     next_fixture: null, team_code: null, team_short: null })

const week = (gw: number, hits: number, buys: ReturnType<typeof ref>[],
              sells: ReturnType<typeof ref>[]) => ({
  gw, hits, buys, sells,
  xi: [ref(1, 'Keeper'), ref(2, 'Back')], bench: [ref(3, 'Sub')],
  captain: ref(2, 'Back'), vice: ref(1, 'Keeper'), expected_pts: 60,
})

const PAYLOAD: LadderPayload = {
  gw: 3, gws: [3, 4, 5], generated_at: '2026-09-04T13:00:00+00:00',
  free_transfers: 1, cap: { max_hits: 2, max_transfers: null },
  cap_rung: 'hits2', recommended: 'hits1', n_draws: 200, seed: 7,
  sigma_source: 'bands', wall_s: 31.2, note: null,
  rungs: [
    { key: 'bank', hits: 0, transfers: 0, cost: 0, same_as: null,
      plan_by_gw: [week(3, 0, [], [])], week_pts: 60, horizon_pts: 180,
      objective: 170, mean_pts: 180, p10_pts: 160, p90_pts: 200,
      p_beats_bank: null, p_beats_top: 0.42, p_best: 0.2, vs_below: null },
    { key: 'hits0', hits: 0, transfers: 1, cost: 0, same_as: null,
      plan_by_gw: [week(3, 0, [ref(20, 'Star')], [ref(16, 'Dud')])],
      week_pts: 63, horizon_pts: 186, objective: 176, mean_pts: 186,
      p10_pts: 165, p90_pts: 207, p_beats_bank: 0.71, p_beats_top: 0.5,
      p_best: 0.3,
      vs_below: { extra_buys: [ref(20, 'Star')], extra_sells: [ref(16, 'Dud')],
                  dropped_buys: [], dropped_sells: [], delta_mean_pts: 6,
                  delta_cost: 0 } },
    { key: 'hits1', hits: 1, transfers: 2, cost: 4, same_as: null,
      plan_by_gw: [week(3, 1, [ref(20, 'Star'), ref(19, 'Second')],
                        [ref(16, 'Dud'), ref(17, 'Filler')])],
      week_pts: 64, horizon_pts: 188, objective: 177, mean_pts: 188,
      p10_pts: 166, p90_pts: 210, p_beats_bank: 0.74, p_beats_top: null,
      p_best: 0.5,
      vs_below: { extra_buys: [ref(19, 'Second')],
                  extra_sells: [ref(17, 'Filler')], dropped_buys: [],
                  dropped_sells: [], delta_mean_pts: 1.9, delta_cost: 4 } },
    { key: 'hits2', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
      plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
      mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
      p_beats_top: null, p_best: null, vs_below: null },
    { key: 'hits3', hits: 1, transfers: 2, cost: 4, same_as: 'hits1',
      plan_by_gw: [], week_pts: null, horizon_pts: null, objective: null,
      mean_pts: null, p10_pts: null, p90_pts: null, p_beats_bank: null,
      p_beats_top: null, p_best: null, vs_below: null },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/ladder') return PAYLOAD
    if (path.startsWith('/api/jobs/')) {
      return { id: 'j1', status: 'done', result: PAYLOAD, error: null }
    }
    throw new Error(`unexpected GET ${path}`)
  })
  apiPost.mockResolvedValue({ job_id: 'j1' })
})

function mount(props: Parameters<typeof LadderCard>[0] = {}) {
  return render(<MemoryRouter><LadderCard {...props} /></MemoryRouter>)
}

describe('LadderCard', () => {
  it('lists one row per rung with the moves, the cost and the odds', async () => {
    mount()
    const row = (await screen.findByText('1 hit')).closest('tr')!
    expect(row).toHaveTextContent('Star, Second')
    expect(row).toHaveTextContent('−4')
    expect(row).toHaveTextContent('74%')     // P(beats bank)
    expect(row).toHaveTextContent('50%')     // P(best)
    expect(screen.getByText('Bank').closest('tr')).toHaveTextContent('—')
  })

  it('highlights the cap rung and mutes the rungs beyond it', async () => {
    mount()
    const cap = (await screen.findByText('2 hits')).closest('tr')!
    expect(cap).toHaveAttribute('data-cap', 'true')
    const beyond = screen.getByText('3 hits').closest('tr')!
    expect(beyond).toHaveClass('text-text-muted')
    expect(beyond).toHaveAttribute('title', 'beyond your cap')
    expect(cap).not.toHaveClass('text-text-muted')
  })

  it('marks the recommended rung and says when a rung repeats the one below', async () => {
    mount()
    const rec = (await screen.findByText('1 hit')).closest('tr')!
    expect(within(rec).getByText('recommended')).toBeInTheDocument()
    expect(screen.getByText('2 hits').closest('tr'))
      .toHaveTextContent(/solver would not spend it — same as 1 hit/)
  })

  it('names the free transfers and the cap in the heading', async () => {
    mount()
    expect(await screen.findByText(/1 free transfer · cap 2 hits/))
      .toBeInTheDocument()
    expect(capText(PAYLOAD)).toBe('1 free transfer · cap 2 hits')
    expect(capText({ ...PAYLOAD, free_transfers: 2,
                     cap: { max_hits: null, max_transfers: 0 } }))
      .toBe('2 free transfers · hits uncapped · bank')
  })

  it('expands a rung to show what the last hit bought', async () => {
    mount()
    await userEvent.click(await screen.findByText('1 hit'))
    expect(screen.getByText(/\+ Second for Filler/)).toBeInTheDocument()
    expect(screen.getByText(/\+1.9 xPts over 3 GWs, −4 now/))
      .toBeInTheDocument()
    expect(screen.getByText('Back')).toBeInTheDocument()   // the XI
  })

  it('rebuilds through the job endpoint and reloads', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button',
                                                    { name: /rebuild/i }))
    expect(apiPost).toHaveBeenCalledWith('/api/ladder', undefined)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(3),
                  { timeout: 4000 })
  })

  it('saves a changed cap through settings and then rebuilds', async () => {
    const onLoaded = vi.fn()
    mount({ onLoaded })
    await screen.findByText('1 hit')
    await userEvent.selectOptions(screen.getByLabelText('Max hits'), '1')
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'max_hits', value: 1 }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/ladder',
                                                              undefined))
    expect(onLoaded).toHaveBeenCalled()
  })

  it('offers a rebuild when nothing is banked yet', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/ladder') {
        return { ...PAYLOAD, rungs: [], note: 'no ladder for GW3 — rebuild' }
      }
      throw new Error(path)
    })
    mount()
    expect(await screen.findByText(/no ladder for GW3/)).toBeInTheDocument()
  })
})
