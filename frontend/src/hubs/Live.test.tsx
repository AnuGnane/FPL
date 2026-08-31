import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Live from './Live'

// vi.mock's factory is hoisted above the file body, so the spy has to be
// hoisted with it.
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

// jsdom measures every box at zero, so the real ResponsiveContainer renders
// nothing. Cloning the chart with a fixed box is what it does itself once it
// has measured, and it is the only way the race card's contents are assertable.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 220 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 220 })
          : children}
      </div>
    ),
  }
})

const ACTIVE = {
  active: true, gw: 3, my_points: 66, matches_in_play: 2,
  players: [{ element: 7, code: 100, name: 'Salah', position: 'MID',
              multiplier: 2, points: 9, provisional_bonus: 3, minutes: 90,
              status: 'playing', tier_eo: 143.5, tier_eo_se: 2.1,
              selected_by_percent: 45, projected_out: false,
              projected_in: false, sub_partner: null, sub_reason: null,
              remaining_ep: 0 },
            { element: 9, code: 102, name: 'Blank', position: 'FWD',
              multiplier: 1, points: 0, provisional_bonus: 0, minutes: 0,
              status: 'played', tier_eo: null, tier_eo_se: null,
              selected_by_percent: 2, projected_out: true, projected_in: false,
              sub_partner: 12, sub_reason: 'played', remaining_ep: 0 },
            { element: 12, code: 103, name: 'Sub', position: 'FWD',
              multiplier: 0, points: 4, provisional_bonus: 0, minutes: 60,
              status: 'playing', tier_eo: null, tier_eo_se: null,
              selected_by_percent: 3, projected_out: false, projected_in: true,
              sub_partner: 9, sub_reason: 'played', remaining_ep: 1.5 }],
  table: [{ entry: 1, name: 'You', pre_total: 106, live: 66, projected: 172,
            delta: 1, projected_live: 66, remaining_ep: 1.5, race: 67.5 }],
  notice: null,
  my_projected_points: 70,
  my_race: 71.5,
  race_reference: 61.5,
  race_series: [
    { at: '2026-08-31T14:00:00+00:00', you: 40, rival: 38 },
    { at: '2026-08-31T14:01:00+00:00', you: 71.5, rival: 44 },
  ],
  safety: [
    { entry: 3, name: 'Above', role: 'above', margin: 10, need: 11 },
    { entry: 2, name: 'Below', role: 'below', margin: -15, need: 0 },
  ],
  rival_name: 'Above',
  race_notice: null,
}

const NO_TIER = {
  ...ACTIVE,
  players: [{ ...ACTIVE.players[0], tier_eo: null, tier_eo_se: null,
              selected_by_percent: null }],
  notice: 'top-10k EO unavailable (429) — league EO only',
}

const NO_COMPONENTS = {
  ...ACTIVE,
  my_race: 70, race_reference: null, race_series: [], safety: [],
  race_notice: 'no component breakdown for GW3 — the race shows live points '
    + 'only',
}

const IDLE = {
  active: false, gw: null, my_points: 0, matches_in_play: 0, players: [],
  table: [], my_projected_points: 0, my_race: null, race_reference: null,
  race_series: [], safety: [], rival_name: null, race_notice: null,
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(ACTIVE)
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('Live', () => {
  it('shows points, provisional bonus and the projected table', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    // "66" is both your running total and your row in the live table.
    expect(screen.getAllByText('66')).toHaveLength(2)
    expect(screen.getByText(/2 match/)).toBeInTheDocument()
    expect(screen.getByText(/provisional/i)).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    expect(screen.getByText('172')).toBeInTheDocument()
    expect(screen.getByText('▲1')).toBeInTheDocument()
  })

  it('shows the race as a season total, like the projection beside it',
    async () => {
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      // 106 banked + 67.5 this gameweek. The bare 67.5 would read as a worse
      // score than the 172 next to it.
      expect(screen.getByText('173.5')).toBeInTheDocument()
    })

  it('polls every 60 seconds while a gameweek is live', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(apiGet).toHaveBeenCalledTimes(1)
    await act(() => vi.advanceTimersByTimeAsync(60000))
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('stops polling once the page unmounts', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    let unmount = () => {}
    await act(async () => {
      unmount = render(<MemoryRouter><Live /></MemoryRouter>).unmount
    })
    expect(apiGet).toHaveBeenCalledTimes(1)
    unmount()
    await act(() => vi.advanceTimersByTimeAsync(180000))
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('says nothing is on when no gameweek is live and stops polling',
    async () => {
      apiGet.mockResolvedValue(IDLE)
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      expect(screen.getByText(/no gameweek in progress/i)).toBeInTheDocument()
      await act(() => vi.advanceTimersByTimeAsync(120000))
      expect(apiGet).toHaveBeenCalledTimes(1)
    })

  it('shows the sampled top-10k EO with its error bar', async () => {
    apiGet.mockResolvedValue(ACTIVE)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Top 10k EO')).toBeInTheDocument()
    expect(screen.getByText('143.5% ±2.1')).toBeInTheDocument()
    expect(screen.getByText('45%')).toBeInTheDocument()
  })

  it('renders the table and a notice when tier EO is unavailable', async () => {
    apiGet.mockResolvedValue(NO_TIER)
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getAllByText('–').length).toBeGreaterThan(0)
    expect(screen.getByText(/top-10k EO unavailable/)).toBeInTheDocument()
  })

  // The suite runs on fake timers, under which RTL's `findBy*` never settles,
  // so these three flush with `act` like every test above them.
  it('heads the page with the live gameweek', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByRole('heading', { level: 1, name: /live/i }))
      .toBeInTheDocument()
  })

  it('offers an auto-poll toggle', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByRole('checkbox', { name: /auto-refresh/i }))
      .toBeInTheDocument()
  })

  it('shows an empty state between gameweeks', async () => {
    apiGet.mockResolvedValue({ active: false, gw: null, my_points: 0,
                               matches_in_play: 0, players: [], table: [] })
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/no gameweek in progress/i)).toBeInTheDocument()
  })

  it('heads the score with where it is going, not only where it is',
    async () => {
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      // "Projected" is both the new stat's label and the league table's
      // column header, so it is matched as a set rather than singly.
      expect(screen.getAllByText('Projected').length).toBeGreaterThan(0)
      expect(screen.getByText('70')).toBeInTheDocument()
      expect(screen.getByText('71.5')).toBeInTheDocument()
    })

  it('draws the race against the pre-gameweek plan', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/race to full time/i)).toBeInTheDocument()
    expect(screen.getByText(/plan 61.5/)).toBeInTheDocument()
  })

  it('waits for a second poll before drawing a trajectory', async () => {
    apiGet.mockResolvedValue({ ...ACTIVE, race_series: [ACTIVE.race_series[0]] })
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText(/builds as the page polls/i)).toBeInTheDocument()
  })

  it('prices each league place it can reach', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('One place above')).toBeInTheDocument()
    // "+11" is what I must add *on top of* the projection already shown, not
    // a total, and the copy has to say so.
    expect(screen.getByText(/need \+11 beyond your current projection/))
      .toBeInTheDocument()
    expect(screen.getByText('One place below')).toBeInTheDocument()
    expect(screen.getByText(/15 clear/)).toBeInTheDocument()
    expect(screen.getByText(/league places only/i)).toBeInTheDocument()
  })

  it('chips the projected auto-substitution on both players', async () => {
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    expect(screen.getByText('auto-sub out')).toBeInTheDocument()
    expect(screen.getByText('auto-sub in · played')).toBeInTheDocument()
  })

  it('says why the race is only live points when nothing is banked',
    async () => {
      apiGet.mockResolvedValue(NO_COMPONENTS)
      await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
      expect(screen.getByText(/no component breakdown for GW3/))
        .toBeInTheDocument()
      expect(screen.queryByText('One place above')).not.toBeInTheDocument()
    })

  it('opens the explain modal from a player chip', async () => {
    // The affordance Live's rows did not have: the name was bare text, so
    // there was nowhere to ask why the model still expects anything of him.
    apiGet.mockImplementation((path: string) => (
      path.includes('/explain')
        ? Promise.resolve({
          code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
          ep_next: 9, fixtures: [], next_fixtures: [],
          set_pieces: { penalties: null, free_kicks: null, corners: null },
        })
        : Promise.resolve(ACTIVE)))
    await act(async () => { render(<MemoryRouter><Live /></MemoryRouter>) })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Salah/ }))
    })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
