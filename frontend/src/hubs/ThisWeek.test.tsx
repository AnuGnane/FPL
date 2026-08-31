import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ThisWeek from './ThisWeek'

const { FakeApiError, apiGet, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status = 0
    detail: unknown = null
  }
  return { FakeApiError, apiGet: vi.fn(), apiPost: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

const ADVICE = {
  gw: 5,
  mode: 'weekly',
  deadline: '2099-09-18T17:30:00Z',
  advice: {
    gw: 5, deadline: '2099-09-18T17:30:00Z', expected_pts: 61.5, hits: 1,
    xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4 }],
    bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6 }],
    captain: { code: 1, name: 'Salah', ep: 6.4 },
    vice: { code: 2, name: 'Gabriel', ep: 4.6 },
    buys: [{ code: 3, name: 'Wirtz', ep: 6.1, frequency: 0.82 }],
    sells: [{ code: 4, name: 'Isak', ep: 3.2, frequency: 0.79 }],
    scenarios: { n: 200, completed: 200, seed: 7, captain_frequency: 0.74 },
    strategy: { lam: 0.25, gap: 84, weeks_left: 36, stance: 'chase',
                rival_name: 'Ten Hag Hive' },
    chip_table: [{ chip: 'bboost', gw: 7, gain: 8.2, threshold: 6.0,
                   play_now: false }],
  },
  staleness: {
    advice_gw: 5, current_gw: 5, generated_at: '2026-08-29T09:00:00Z',
    deadline: '2099-09-18T17:30:00Z', deadline_passed: false, stale: false,
    reason: 'current for GW5', data_through_gw: 4, data_warning: null,
  },
}

const PLAYERS = [
  { code: 1, name: 'Salah', position: 'MID', team_code: 300, team_name: 'LIV',
    price: 13.0, ep_next: 6.4, ep_horizon: 12.0, ownership: 42.1,
    league_eo: 61.5, available: true, status: 'a',
    news: 'Knock - 75% chance of playing', chance_of_playing: 75,
    penalties_order: 1, free_kicks_order: 1, corners_order: null,
    in_squad: true, last4: [2, 9, 5, 12], element: 7 },
  { code: 2, name: 'Gabriel', position: 'DEF', team_code: 301,
    team_name: 'ARS', price: 6.0, ep_next: 4.6, ep_horizon: 9.0,
    ownership: 30.0, league_eo: 12.0, available: true, status: 'a',
    news: '', chance_of_playing: null, penalties_order: null,
    free_kicks_order: null, corners_order: null, in_squad: true,
    last4: [], element: 8 },
]

const COMPONENTS = {
  gw: 5,
  players: [{
    code: 1, name: 'Salah', position: 'MID', team_name: 'LIV', ep: 6.4,
    fixtures: [{
      gw: 5, opponent: 'ARS', home: true, kickoff_time: null,
      components: [{ label: 'Minutes', points: 1.9 },
                   { label: 'Goals', points: 3.1 }],
      pen_taker: 0.6,
      minutes: { p_play: 0.98, p60: 0.9, xmins: 88 }, ep: 6.4,
    }],
  }],
}

function route(path: string) {
  if (path === '/api/advice/latest') return Promise.resolve(ADVICE)
  if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
  if (path.startsWith('/api/components/')) return Promise.resolve(COMPONENTS)
  if (path.startsWith('/api/news/')) {
    return Promise.resolve({ gw: 5, moved: 0, rows: [] })
  }
  if (path.startsWith('/api/advice/diff')) {
    return Promise.resolve({ gw: 5, available: false })
  }
  return Promise.reject(new Error(`unexpected path ${path}`))
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation(route)
  // The league what-if is the captaincy chip's only caller and it is
  // fire-and-forget: the default here is the "no simulation available" path,
  // which every test but the chip's own expects to be silent.
  apiPost.mockReset()
  apiPost.mockRejectedValue(new Error('no sim'))
})

describe('This Week hub', () => {
  it('heads the page with the gameweek and the deadline', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByRole('heading', { level: 1, name: /GW5/ }))
      .toBeInTheDocument()
  })

  it('shows the four stats: XI, captain, chip and league', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText('Expected XI')).toBeInTheDocument()
    expect(screen.getByText('61.5')).toBeInTheDocument()
    // The captain's name is on the pitch, in the squad table and in the
    // caption too, so this one is scoped to the stat tile.
    const captainStat = screen.getByText('Captain').closest('div')!
    expect(within(captainStat).getByText(/Salah/)).toBeInTheDocument()
    expect(screen.getByText('Next chip')).toBeInTheDocument()
    expect(screen.getByText('League')).toBeInTheDocument()
  })

  it('draws the chip gain against its threshold', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await waitFor(() =>
      expect(screen.getByTestId('threshold-fill')).toBeInTheDocument())
    expect(screen.getByText(/θ 6.0/)).toBeInTheDocument()
  })

  it('lists the squad with EO from the players endpoint', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText('61.5')).toBeInTheDocument()
  })

  it('lists the recommended moves', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText('Wirtz')).toBeInTheDocument()
    expect(screen.getByText('Isak')).toBeInTheDocument()
  })

  it('offers a Run advise button', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Run advise' }))
      .toBeInTheDocument()
  })

  it('shows an empty state naming the button when there is no advice',
    async () => {
      apiGet.mockImplementation((path: string) => (
        path === '/api/advice/latest'
          ? Promise.reject(Object.assign(new FakeApiError('no advice on disk '
            + 'yet — run `gaffer advise` first'), { status: 422 }))
          : route(path)
      ))
      render(<MemoryRouter><ThisWeek /></MemoryRouter>)
      expect(await screen.findByText(/no advice/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Run advise' }))
        .toBeInTheDocument()
    })
})

describe('an advice payload missing its armband', () => {
  // advice.captain.name, unguarded, is a TypeError during render — which
  // React answers by unmounting the whole tree. A hub that cannot name a
  // captain should say so, not go white.
  const withoutCaptain = (key: 'captain' | 'vice') => {
    const advice = { ...ADVICE.advice }
    delete (advice as Record<string, unknown>)[key]
    return { ...ADVICE, advice }
  }

  it('renders an empty state rather than a white screen', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/advice/latest'
        ? Promise.resolve(withoutCaptain('captain'))
        : route(path)))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /this week/i }))
      .toBeInTheDocument()
  })

  it('says the same for a missing vice', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/advice/latest'
        ? Promise.resolve(withoutCaptain('vice'))
        : route(path)))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
  })

  it('still offers the run that would fix it', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/advice/latest'
        ? Promise.resolve(withoutCaptain('captain'))
        : route(path)))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await screen.findByTestId('empty-state')
    expect(screen.getByRole('button', { name: /advise/i })).toBeInTheDocument()
  })

  it('offers the fast run beside the full one', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Run advise' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fast advise' }))
      .toBeInTheDocument()
  })
})

describe('the captaincy title-odds chip', () => {
  it('prices the armband against the alternative when the sim answers',
     async () => {
       // apiPost is the what-if call; the chip asks for the captain swap the
       // vice would have been.
       apiPost.mockResolvedValue({
         baseline_p_win: 0.42, p_win: 0.39, delta_p_win: -0.03,
         baseline_exp_finish: 1.6, exp_finish: 1.7, delta_rank: 0.1,
         table: [], unknown_codes: [],
       })
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       expect(await screen.findByTestId('captain-odds-chip'))
         .toHaveTextContent('+3.0%')
     })

  it('is simply absent when the simulation is not available', async () => {
    apiPost.mockRejectedValue(new Error('422'))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText(/Starting XI/)).toBeInTheDocument()
    expect(screen.queryByTestId('captain-odds-chip')).not.toBeInTheDocument()
  })

  it('never blocks the page on it', async () => {
    apiPost.mockReturnValue(new Promise(() => {}))     // never resolves
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText(/Starting XI/)).toBeInTheDocument()
  })
})
