import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ComparePanel from './ComparePanel'
import type { PlayerRow } from '../../types'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

// Recharts measures its container, which jsdom reports as 0x0; the responsive
// wrapper then renders nothing. Stub it to a fixed box so the bars exist.
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

const PLAYERS: PlayerRow[] = [
  { code: 1, element: 7, name: 'Salah', position: 'MID', team_code: 300,
    team_name: 'Liverpool', price: 13.0, ep_next: 6.4, ep_horizon: 12.0,
    ownership: 42.1, league_eo: 61.5, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: 1, free_kicks_order: 1,
    corners_order: null, in_squad: true, last4: [2, 9, 5, 12] },
  { code: 2, element: 8, name: 'Saka', position: 'MID', team_code: 301,
    team_name: 'Arsenal', price: 10.0, ep_next: 5.5, ep_horizon: 10.5,
    ownership: 30.0, league_eo: 22.0, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: null, free_kicks_order: null,
    corners_order: 1, in_squad: false, last4: [6, 1, 8, 3] },
]

const COMPONENTS = {
  gw: 5,
  players: [
    { code: 1, name: 'Salah', position: 'MID', team_name: 'Liverpool', ep: 6.4,
      fixtures: [{ gw: 5, opponent: 'EVE', home: true, kickoff_time: null,
                   components: [{ label: 'Minutes', points: 1.9 },
                                { label: 'Goals', points: 3.1 }],
                   pen_taker: 0.6,
                   minutes: { p_play: 0.98, p60: 0.9, xmins: 88 }, ep: 6.4 }] },
    { code: 2, name: 'Saka', position: 'MID', team_name: 'Arsenal', ep: 5.5,
      fixtures: [{ gw: 5, opponent: 'LIV', home: false, kickoff_time: null,
                   components: [{ label: 'Minutes', points: 1.8 },
                                { label: 'Goals', points: 2.2 }],
                   pen_taker: null,
                   minutes: { p_play: 0.95, p60: 0.85, xmins: 82 }, ep: 5.5 }] },
  ],
}

const MATRIX = {
  gws: [5, 6], source: 'dixon_coles',
  teams: [
    { code: 300, name: 'Liverpool', short_name: 'LIV', mean_attack: 0.2,
      mean_defence: 0.3,
      cells: [{ gw: 5, opponent: 'EVE', home: true, attack: 0.1,
                defence: 0.2 }] },
    { code: 301, name: 'Arsenal', short_name: 'ARS', mean_attack: 0.4,
      mean_defence: 0.5,
      cells: [{ gw: 5, opponent: 'LIV', home: false, attack: 0.9,
                defence: 0.8 }] },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockImplementation((path: string) => (
    path.startsWith('/api/components/') ? Promise.resolve(COMPONENTS)
      : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
        : Promise.reject(new Error(`unexpected ${path}`))
  ))
})

describe('ComparePanel', () => {
  it('asks for two to four players', () => {
    render(<ComparePanel gw={5} players={[PLAYERS[0]]} />)
    expect(screen.getByText(/pick at least two/i)).toBeInTheDocument()
  })

  it('puts one column per selected player', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    expect(await screen.findByTestId('compare-1')).toBeInTheDocument()
    expect(screen.getByTestId('compare-2')).toBeInTheDocument()
  })

  it('shows price, EO, ownership and xPts for each', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const salah = await screen.findByTestId('compare-1')
    expect(salah).toHaveTextContent('13.0')
    expect(salah).toHaveTextContent('61.5')
    expect(salah).toHaveTextContent('42.1')
    expect(salah).toHaveTextContent('6.4')
  })

  it('draws the EP component bars', async () => {
    const { container } = render(<ComparePanel gw={5} players={PLAYERS} />)
    await screen.findByTestId('compare-1')
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull()
  })

  it('shows a next-six fixture strip coloured by the matrix', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const salah = await screen.findByTestId('compare-1')
    expect(salah).toHaveTextContent('EVE')
  })

  it('refuses more than four', () => {
    const five = [...PLAYERS, ...PLAYERS, PLAYERS[0]]
    render(<ComparePanel gw={5} players={five} />)
    expect(screen.getByText(/at most four/i)).toBeInTheDocument()
  })
})
