import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LeaguesOverview } from '../types'
import ToastOutlet, { resetToasts } from '../kit/Toast'
import League from './League'

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    // The chart itself needs the measured box: cloning it with a fixed one is
    // what the real container does once it has measured.
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

// The field names are the ones `/api/league/race` actually emits
// (`trajectory`, `gap`, `win_probability`) — see web/schemas.py::LeagueRace.
const RACE = {
  league_id: 1234,
  entry_id: 1,
  standings: [
    { entry: 1, name: 'Mine', player_name: 'Me', rank: 1, total: 300,
      event_total: 60, is_you: true },
    { entry: 2, name: 'Ten Hag Hive', player_name: 'Them', rank: 2,
      total: 290, event_total: 55, is_you: false },
  ],
  trajectory: [
    { entry: 1, name: 'Mine',
      points: [{ gw: 4, points: 60, total: 240 },
               { gw: 5, points: 60, total: 300 }] },
    { entry: 2, name: 'Ten Hag Hive',
      points: [{ gw: 4, points: 55, total: 235 },
               { gw: 5, points: 55, total: 290 }] },
  ],
  gap: [{ gw: 5, gap: 10 }],
  win_probability: [{ name: 'Ten Hag Hive', total: 290, p_win: 0.41 }],
  lam: 1.0,
  stance: 'balanced',
  lam_explained: 'second place, chasing',
  league_name: 'Focus FC League',
  focus: true,
  stance_source: 'auto',
}

// The overview the hub opens on: the focus league plus one other private
// league the reader can open with `?league=`.
const OVERVIEW: LeaguesOverview = {
  focus_league_id: 1234, focus_name: 'Focus FC League', stance: 'auto',
  focus_stance: 'chase', focus_lam: 0.31, focus_warning: null, gw: 5,
  private: [
    { league_id: 1234, name: 'Focus FC League', rank: 15, last_rank: 80,
      entries: 138, started: true, gap: 12, gap_kind: 'behind',
      would: 'chase', is_focus: true },
    { league_id: 9, name: 'NLT', rank: 1, last_rank: 3, entries: 7,
      started: true, gap: 9, gap_kind: 'ahead', would: 'defend',
      is_focus: false },
  ],
  public: [
    { league_id: 314, name: 'Overall', rank: 430473, last_rank: 2562053,
      entries: 10409391 },
  ],
}

const NLT_RACE = {
  ...RACE, league_id: 9, league_name: 'NLT', focus: false, stance: 'defend',
  lam: -0.2,
}

// The hub opens on the Leagues tab now, so every test about race content
// deep-links to the tab it is about.
const RACE_AT = ['/league?tab=race']

const RIVALS = [
  { entry: 2, name: 'Ten Hag Hive', player_name: 'Them', rank: 2, total: 290,
    event_total: 55, overlap: 11, differentials: 4 },
]

beforeEach(() => {
  resetToasts()
  apiGet.mockReset()
  apiPost.mockReset()
  apiPost.mockResolvedValue({})
  apiGet.mockImplementation((path: string) => (
    path === '/api/league/race' ? Promise.resolve(RACE)
      : path === '/api/league/race?league_id=9' ? Promise.resolve(NLT_RACE)
        : path === '/api/league/leagues' ? Promise.resolve(OVERVIEW)
          : path.startsWith('/api/league/rivals') ? Promise.resolve(RIVALS)
            : Promise.reject(new Error(`unexpected ${path}`))
  ))
})

describe('League hub', () => {
  it('draws the race chart', async () => {
    const { container } = render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    // Named twice on this tab now: once in standings, once in win probability.
    await screen.findAllByText('Ten Hag Hive')
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull()
  })

  it('lists the standings with you marked', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByText('Mine')).toBeInTheDocument()
    expect(screen.getByTestId('standing-1')).toHaveAttribute('data-you', 'true')
  })

  it('links each rival to their detail route', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab', { name: 'Rivals' }))
    expect(await screen.findByRole('link', { name: /Ten Hag Hive/ }))
      .toHaveAttribute('href', '/league/rival/2')
  })

  it('shows an empty state naming the config when there is no league',
    async () => {
      apiGet.mockRejectedValue(Object.assign(
        new Error('set fpl.league_id in config.toml first'), { status: 422 }))
      render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
      expect(await screen.findByText(/no league configured/i))
        .toBeInTheDocument()
      expect(screen.getByText('config.toml')).toBeInTheDocument()
    })
})

describe('two rivals with the same team name', () => {
  // FPL does not make team names unique. Keying the chart rows by name meant
  // the second writer of a gameweek overwrote the first, so two managers
  // called "The Invincibles" were drawn as one line and the other vanished.
  const CLASH = {
    ...RACE,
    standings: RACE.standings.map((row) => ({ ...row, name: 'Same Name' })),
    trajectory: RACE.trajectory.map((t) => ({ ...t, name: 'Same Name' })),
  }

  beforeEach(() => {
    // Named paths only: a catch-all here handed the league-sim fetch a rival
    // list, which is not a sim payload, and the card blew up on it.
    apiGet.mockImplementation((path: string) => (
      path.includes('/race') ? Promise.resolve(CLASH)
        : path.includes('/rivals') ? Promise.resolve(RIVALS)
          : Promise.reject(new Error(`unexpected ${path}`))))
  })

  it('draws a line per entry, not per name', async () => {
    const { container } = render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    await screen.findByText('Cumulative points')
    const paths = [...container.querySelectorAll('.recharts-line-curve')]
      .map((node) => node.getAttribute('d'))
    expect(paths).toHaveLength(CLASH.trajectory.length)
    // Keyed by name, both series read the same column, so both lines were
    // drawn through the same points and one manager's season disappeared.
    expect(paths[0]).not.toEqual(paths[1])
  })

  it('keeps both entries distinguishable in the standings', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    await screen.findByText('Cumulative points')
    expect(screen.getByTestId('standing-1')).toBeInTheDocument()
    expect(screen.getByTestId('standing-2')).toBeInTheDocument()
  })
})

const SIM = {
  gw: 7, entries: 2, weeks_left: 31, n: 2000, seed: 20260831,
  rival_drift: 0.5, p_win: 0.42, p_top3: 1.0, exp_finish: 1.6,
  per_rival: [{ entry: 2, name: 'Ten Hag Hive', p_beat: 0.58 }],
  margin_quantiles: { p05: -60, p25: -12, p50: 18, p75: 50, p95: 120 },
  history: [
    { gw: 5, p_win: 0.3, p_top3: 1, exp_finish: 1.8,
      run_at: '2026-09-05T09:00:00+00:00' },
    { gw: 6, p_win: 0.36, p_top3: 1, exp_finish: 1.7,
      run_at: '2026-09-12T09:00:00+00:00' },
  ],
  field_rate: 54.2, notice: null, legacy_win_probability: [],
}

describe('the simulated win-probability card', () => {
  beforeEach(() => {
    apiGet.mockReset()
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') return Promise.resolve(SIM)
      return Promise.reject(new Error(`unexpected ${path}`))
    })
  })

  it('leads with the simulated title odds, not the pairwise ones', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-p-win')).toHaveTextContent('42%')
    expect(screen.getByTestId('sim-p-top3')).toHaveTextContent('100%')
  })

  it('says how many simulations produced the number', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-provenance'))
      .toHaveTextContent('2,000')
  })

  it('names the model that produced the fan', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-provenance'))
      .toHaveTextContent('shared-ownership correlated')
  })

  it('says the fan is wide when no field sample is banked', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') {
        return Promise.resolve({ ...SIM, field_rate: null })
      }
      return Promise.reject(new Error(`unexpected ${path}`))
    })
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-provenance'))
      .toHaveTextContent('independence assumed')
  })

  it('dashes a rival whose squad could not be read', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') {
        return Promise.resolve({ ...SIM, per_rival: [
          { entry: 2, name: 'Ten Hag Hive', p_beat: null }] })
      }
      return Promise.reject(new Error(`unexpected ${path}`))
    })
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('beat-2')).toHaveTextContent('—')
  })

  it('renders the margin fan the engine has always published', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-margin-fan')).toBeInTheDocument()
    expect(screen.getByTestId('margin-p05')).toHaveTextContent('-60')
    expect(screen.getByTestId('margin-p50')).toHaveTextContent('18')
    expect(screen.getByTestId('margin-p95')).toHaveTextContent('120')
    // The fan straddles zero here, so the reader is shown where it is.
    expect(screen.getByTestId('sim-margin-zero')).toBeInTheDocument()
  })

  it('lists every rival with the odds of beating him', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('beat-2')).toHaveTextContent('58%')
  })

  it('draws the sparkline once two gameweeks are banked', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByTestId('sim-sparkline')).toBeInTheDocument()
  })

  it('falls back to the parametric table when the sim will not load',
     async () => {
       apiGet.mockImplementation((path: string) => {
         if (path === '/api/league/race') return Promise.resolve(RACE)
         if (path === '/api/league/rivals') return Promise.resolve([])
         return Promise.reject(new Error('422'))
       })
       render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
       expect(await screen.findByTestId('legacy-win-probability'))
         .toBeInTheDocument()
       expect(screen.queryByTestId('sim-p-win')).not.toBeInTheDocument()
     })

  it('shows the notice when no field sample is banked', async () => {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve([])
      if (path === '/api/league/sim') {
        return Promise.resolve({ ...SIM, field_rate: null,
                                 notice: 'no field sample banked' })
      }
      return Promise.reject(new Error('x'))
    })
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByText(/no field sample banked/))
      .toBeInTheDocument()
  })

  it('offers the What if tab', async () => {
    render(<MemoryRouter initialEntries={RACE_AT}><League /></MemoryRouter>)
    expect(await screen.findByRole('tab', { name: 'What if' }))
      .toBeInTheDocument()
  })
})

describe('the Leagues tab, the URL league and the two writes', () => {
  function show(at?: string) {
    render(
      <MemoryRouter initialEntries={at === undefined ? undefined : [at]}>
        <League />
        <ToastOutlet />
      </MemoryRouter>,
    )
  }

  it('opens on the Leagues tab and lists the leagues', async () => {
    show()
    expect(await screen.findByTestId('league-9')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Leagues' })).toBeInTheDocument()
  })

  it('fetches the league named in the URL and shows a way back', async () => {
    show('/league?tab=race&league=9')
    expect(await screen.findByRole('heading', { name: 'NLT' })).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/league/race?league_id=9')
    expect(apiGet).toHaveBeenCalledWith('/api/league/rivals?league_id=9')
    expect(apiGet).toHaveBeenCalledWith('/api/league/sim?league_id=9')
    expect(screen.getByRole('link', { name: '‹ Leagues' }))
      .toHaveAttribute('href', '/league?tab=leagues')
  })

  it('says which league sets the plan when this is not it', async () => {
    show('/league?tab=race&league=9')
    const note = await screen.findByTestId('focus-note')
    expect(note).toHaveTextContent('Plan is set by Focus FC League (chase)')
    expect(note).toHaveTextContent('Here you would defend, λ −0.20')
  })

  it('has no such note on the focus league', async () => {
    show('/league?tab=race')
    await screen.findByText('Cumulative points')
    expect(screen.queryByTestId('focus-note')).toBeNull()
  })

  it('links a rival of the opened league back through that league', async () => {
    show('/league?tab=rivals&league=9')
    expect(await screen.findByRole('link', { name: /Ten Hag Hive/ }))
      .toHaveAttribute('href', '/league/rival/2?league=9')
  })

  it('writes the focus through settings and refetches', async () => {
    show()
    const nlt = await screen.findByTestId('league-9')
    await userEvent.click(within(nlt).getByRole('button', { name: 'make focus' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'focus', value: 9 }))
    await waitFor(() => expect(
      apiGet.mock.calls.filter((c) => c[0] === '/api/league/leagues')
        .length).toBeGreaterThan(1))
  })

  it('writes the stance through settings', async () => {
    show()
    await screen.findByTestId('league-9')
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Neutral' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/settings', { key: 'stance', value: 'neutral' }))
  })

  it('toasts a refused write and keeps the page', async () => {
    apiPost.mockRejectedValueOnce(
      new Error('Stance is one of auto, chase, defend, neutral'))
    show()
    await screen.findByTestId('league-9')
    const group = screen.getByRole('group', { name: 'Stance' })
    await userEvent.click(within(group).getByRole('button', { name: 'Chase' }))
    expect(await screen.findByText(/Could not set the stance/))
      .toBeInTheDocument()
    expect(screen.getByTestId('league-9')).toBeInTheDocument()
  })
})
