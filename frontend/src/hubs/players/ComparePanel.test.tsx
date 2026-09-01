import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ComparePanel from './ComparePanel'
import { difficultyBackground } from '../../kit'
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
    corners_order: null, in_squad: true, last4: [2, 9, 5, 12],
    field_eo: 78.0, field_se: 2.8, field_n: 300, field_class: 'shield',
    ep_lo: null, ep_hi: null,
    p_haul: null, p_blank: null },
  { code: 2, element: 8, name: 'Saka', position: 'MID', team_code: 301,
    team_name: 'Arsenal', price: 10.0, ep_next: 5.5, ep_horizon: 10.5,
    ownership: 30.0, league_eo: 22.0, available: true, status: 'a', news: '',
    chance_of_playing: null, penalties_order: null, free_kicks_order: null,
    corners_order: 1, in_squad: false, last4: [6, 1, 8, 3],
    field_eo: null, field_se: null, field_n: null, field_class: null,
    ep_lo: null, ep_hi: null,
    p_haul: null, p_blank: null },
]

const COMPONENTS = {
  gw: 5,
  players: [
    { code: 1, name: 'Salah', position: 'MID', team_name: 'Liverpool', ep: 6.4,
      ep_gw: 6.4, sigma: 1.1, ep_lo: 5.6, ep_hi: 7.2, p_haul: 0.2,
      p_blank: 0.1,
      fixtures: [{ gw: 5, opponent: 'EVE', home: true, kickoff_time: null,
                   components: [{ label: 'Minutes', points: 1.9 },
                                { label: 'Goals', points: 3.1 }],
                   pen_taker: 0.6,
                   minutes: { p_play: 0.98, p60: 0.9, xmins: 88 }, ep: 6.4 }] },
    { code: 2, name: 'Saka', position: 'MID', team_name: 'Arsenal', ep: 5.5,
      ep_gw: 5.5, sigma: 1.0, ep_lo: 4.8, ep_hi: 6.2, p_haul: 0.15,
      p_blank: 0.12,
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

  it('renders each compared player name at primary text size', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const name = await screen.findByRole('heading', { name: PLAYERS[0].name })
    expect(name).toHaveClass('text-lg')
    expect(name).not.toHaveClass('label')
  })

  it('keeps the position badge beside the name', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId(`compare-${PLAYERS[0].code}`)
    expect(within(card).getByRole('heading', { name: PLAYERS[0].name }))
      .toBeInTheDocument()
    expect(within(card).getByText(PLAYERS[0].position)).toBeInTheDocument()
  })

  it('makes the card heading the click-to-explain name', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId(`compare-${PLAYERS[0].code}`)
    const heading = within(card).getByRole('heading',
                                           { name: PLAYERS[0].name })
    expect(within(heading).getByRole('button', { name: PLAYERS[0].name }))
      .toBeInTheDocument()
  })
})

describe('the model’s own working', () => {
  it('sums the breakdown rows to the total it prints', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId('compare-1')
    const rows = within(card).getByTestId('breakdown-1')
    expect(rows).toHaveTextContent('Minutes')
    expect(rows).toHaveTextContent('Goals')
    // 1.9 + 3.1
    expect(within(card).getByTestId('breakdown-total-1'))
      .toHaveTextContent('5.00')
  })

  it('renders a negative term with its sign', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components/')
        ? Promise.resolve({ ...COMPONENTS, players: [
            { ...COMPONENTS.players[0],
              fixtures: [{ ...COMPONENTS.players[0].fixtures[0],
                           components: [{ label: 'Goals', points: 3.1 },
                                        { label: 'Cards', points: -0.4 }] }] },
            COMPONENTS.players[1]] })
        : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
          : Promise.reject(new Error(`unexpected ${path}`))
    ))
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const rows = within(await screen.findByTestId('compare-1'))
      .getByTestId('breakdown-1')
    expect(rows).toHaveTextContent('-0.40')
    // The bar for a negative term sits on the other side of the centre line.
    expect(rows.querySelector('.bg-rust')).not.toBeNull()
    expect(rows.querySelector('.bg-sage')).not.toBeNull()
  })

  it('prints an em dash for an unknown minutes pair, never a zero',
    async () => {
      // A frame banked with no minutes model has neither probability, and
      // 0.0 on *either* is a forecast it never made: p_play 0 says he will
      // not play, p60 0 says he will not see the hour out.
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/components/')
          ? Promise.resolve({ ...COMPONENTS, players: [
              { ...COMPONENTS.players[0],
                fixtures: [{ ...COMPONENTS.players[0].fixtures[0],
                             minutes: { p_play: null, p60: null,
                                        xmins: null } }] },
              COMPONENTS.players[1]] })
          : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
            : Promise.reject(new Error(`unexpected ${path}`))
      ))
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const line = within(await screen.findByTestId('compare-1'))
        .getByTestId('minutes-1-EVE')
      expect(line).toHaveTextContent('p —')
      expect(line).toHaveTextContent('p60 —')
      expect(line).not.toHaveTextContent('p 0.00')
      expect(line).not.toHaveTextContent('p60 0.00')
    })

  it('shows both fixtures of a double gameweek and one xMins total',
    async () => {
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/components/')
          ? Promise.resolve({ ...COMPONENTS, players: [
              { ...COMPONENTS.players[0],
                fixtures: [COMPONENTS.players[0].fixtures[0],
                           { ...COMPONENTS.players[0].fixtures[0],
                             opponent: 'BUR', home: false,
                             minutes: { p_play: 0.9, p60: 0.8,
                                        xmins: 70 } }] },
              COMPONENTS.players[1]] })
          : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
            : Promise.reject(new Error(`unexpected ${path}`))
      ))
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const card = await screen.findByTestId('compare-1')
      expect(within(card).getByTestId('minutes-1-EVE')).toBeInTheDocument()
      expect(within(card).getByTestId('minutes-1-BUR')).toBeInTheDocument()
      // 88 + 70 — xMins is the one of the three that adds.
      expect(within(card).getByTestId('minutes-total-1'))
        .toHaveTextContent('158')
    })

  it('blanks the double’s xMins total when one fixture has none',
    async () => {
      // plan.py's bank convention, on the one quantity here that sums: a
      // total missing one of its terms is not a smaller total, and 88′
      // beside two fixtures reads as the pair.
      apiGet.mockImplementation((path: string) => (
        path.startsWith('/api/components/')
          ? Promise.resolve({ ...COMPONENTS, players: [
              { ...COMPONENTS.players[0],
                fixtures: [COMPONENTS.players[0].fixtures[0],
                           { ...COMPONENTS.players[0].fixtures[0],
                             opponent: 'BUR', home: false,
                             minutes: { p_play: null, p60: null,
                                        xmins: null } }] },
              COMPONENTS.players[1]] })
          : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
            : Promise.reject(new Error(`unexpected ${path}`))
      ))
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const card = await screen.findByTestId('compare-1')
      const total = within(card).getByTestId('minutes-total-1')
      expect(total).toHaveTextContent('—')
      expect(total).not.toHaveTextContent('88')
    })

  it('flags a set-piece order and says nothing when there is none',
    async () => {
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const salah = await screen.findByTestId('compare-1')
      expect(within(salah).getByTestId('setpieces-1'))
        .toHaveTextContent('Pens 1')
      // Saka takes corners and nothing else; null is "the bootstrap does not
      // say", which draws nothing rather than a crossed-out badge.
      const saka = screen.getByTestId('compare-2')
      const flags = within(saka).getByTestId('setpieces-2')
      expect(flags).toHaveTextContent('Corners 1')
      expect(flags).not.toHaveTextContent('Pens')
    })

  it('annotates penalty duty under Goals rather than as a term', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const rows = within(await screen.findByTestId('compare-1'))
      .getByTestId('breakdown-1')
    expect(rows).toHaveTextContent(/penalty duty 0\.60/)
    expect(rows).not.toHaveTextContent(/^Penalties/m)
  })

  it('draws one series per player even when two share a name', async () => {
    // Keyed by name, one of the two Silvas overwrote the other's row and the
    // chart drew a single series for two ticked players.
    const { container } = render(<ComparePanel gw={5} players={[
      { ...PLAYERS[0], name: 'Silva' },
      { ...PLAYERS[1], name: 'Silva' }]} />)
    await screen.findByTestId('compare-1')
    // jsdom gives recharts' bar rectangles no geometry, so the claim is made
    // where it can be: two ticked players are two series and two cards, and
    // the legend prints the shared name twice rather than the chart drawing
    // one man twice.
    expect(container.querySelectorAll('.recharts-bar')).toHaveLength(2)
    expect(screen.getAllByText('Silva').length).toBeGreaterThanOrEqual(2)
  })

  it('keeps the grouped component chart', async () => {
    const { container } = render(<ComparePanel gw={5} players={PLAYERS} />)
    await screen.findByTestId('compare-1')
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull()
  })
})

describe('the fixture strip colours', () => {
  // A cell's `attack` is how easy the opponent is to score against and
  // `defence` is how hard a clean sheet is. Colouring every card by `attack`
  // told a goalkeeper's owner about his chances of scoring.
  const strip = (code: number) => within(
    screen.getByTestId(`compare-${code}`)).getAllByTitle(/^GW/)

  // Liverpool's fixture is easy to score in and hard to keep out: the two
  // axes disagree, which is the only case that can tell them apart.
  const SPLIT = {
    ...MATRIX,
    teams: [{ ...MATRIX.teams[0],
              cells: [{ gw: 5, opponent: 'EVE', home: true, attack: 0.1,
                        defence: 0.9 }] },
            MATRIX.teams[1]],
  }

  beforeEach(() => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components/') ? Promise.resolve(COMPONENTS)
        : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(SPLIT)
          : Promise.reject(new Error(`unexpected ${path}`))
    ))
  })

  // The chips carry the tint the rest of the app uses for a difficulty, so
  // the assertion is against `difficultyBackground` itself rather than against
  // a colour name: one function for one idea.
  const tint = (score: number) => difficultyBackground(score).slice(0, 20)

  it('reads a keeper off the clean-sheet axis', async () => {
    render(<ComparePanel gw={5} players={[
      { ...PLAYERS[0], position: 'GKP' }, PLAYERS[1],
    ]} />)
    await screen.findByTestId('compare-1')
    expect(strip(1)[0].getAttribute('style')).toContain(tint(0.9))
  })

  it('reads a defender off the clean-sheet axis too', async () => {
    render(<ComparePanel gw={5} players={[
      { ...PLAYERS[0], position: 'DEF' }, PLAYERS[1],
    ]} />)
    await screen.findByTestId('compare-1')
    expect(strip(1)[0].getAttribute('style')).toContain(tint(0.9))
  })

  it('reads a midfielder off the attacking axis', async () => {
    render(<ComparePanel gw={5} players={[PLAYERS[0], PLAYERS[1]]} />)
    await screen.findByTestId('compare-1')
    expect(strip(1)[0].getAttribute('style')).toContain(tint(0.1))
  })

  it('reads a forward off the attacking axis', async () => {
    render(<ComparePanel gw={5} players={[
      { ...PLAYERS[0], position: 'FWD' }, PLAYERS[1],
    ]} />)
    await screen.findByTestId('compare-1')
    expect(strip(1)[0].getAttribute('style')).toContain(tint(0.1))
  })

  it('draws nothing for a team the matrix has no cells for', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components/') ? Promise.resolve(COMPONENTS)
        : path.startsWith('/api/fixtures/matrix')
          ? Promise.resolve({ ...MATRIX, teams: [] })
          : Promise.reject(new Error(`unexpected ${path}`))
    ))
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId('compare-1')
    expect(within(card).queryAllByTitle(/^GW/)).toHaveLength(0)
  })
})

describe('the ownership trio', () => {
  it('carries the error bar and the sample size beside the field EO',
    async () => {
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const cell = within(await screen.findByTestId('compare-1'))
        .getByTestId('field-eo-1')
      expect(cell).toHaveTextContent('78.0%')
      expect(cell).toHaveTextContent('± 2.8')
      expect(within(cell).getByTitle(/300 sampled entries/))
        .toBeInTheDocument()
    })

  it('draws an em dash and no error bar when the log does not carry him',
    async () => {
      render(<ComparePanel gw={5} players={PLAYERS} />)
      await screen.findByTestId('compare-1')
      const cell = screen.getByTestId('field-eo-2')
      expect(cell).toHaveTextContent('—')
      expect(cell).not.toHaveTextContent('±')
    })

  it('drops the ± entirely when only the error is missing', async () => {
    // An older field log: an EO measured, no error recorded. 0.0 there would
    // be a claim of perfect precision — and "± —" is a plus-or-minus of
    // nothing, a symbol promising an interval the log never carried. The
    // absence says so in the figure's own title instead.
    render(<ComparePanel gw={5} players={[
      { ...PLAYERS[0], field_se: null, field_n: null }, PLAYERS[1]]} />)
    const cell = within(await screen.findByTestId('compare-1'))
      .getByTestId('field-eo-1')
    expect(cell).toHaveTextContent('78.0%')
    expect(cell).not.toHaveTextContent('±')
    expect(cell).not.toHaveTextContent('0.0')
    expect(within(cell).getByTitle(/No error was recorded/))
      .toBeInTheDocument()
  })
})

describe('the terms, the total and the two expected-points numbers', () => {
  // The reviewer's real-shape case, off the banked components: eleven terms
  // each rounded to 2dp, summing to 0.49, against an `ep` of 0.55. Every one
  // of those six hundredths is per-term rounding, and a caption saying the
  // total is a horizon figure would be inventing a discrepancy.
  const SMALL = [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.03, 0.02, 0.01,
                 0.01]

  function serve(points: number[], ep: number, epGw = ep, gws = [5]) {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/components/')
        ? Promise.resolve({ ...COMPONENTS, players: [
            { ...COMPONENTS.players[0], ep, ep_gw: epGw,
              fixtures: gws.map((g, i) => ({
                ...COMPONENTS.players[0].fixtures[0], gw: g,
                opponent: i === 0 ? 'EVE' : 'BUR',
                components: i === 0
                  ? points.map((p, n) => ({ label: `t${n}`, points: p }))
                  : [{ label: 't0', points: 0.5 }] })) },
            COMPONENTS.players[1]] })
        : path.startsWith('/api/fixtures/matrix') ? Promise.resolve(MATRIX)
          : Promise.reject(new Error(`unexpected ${path}`))
    ))
  }

  it('says nothing about a horizon when the gap is only term rounding',
    async () => {
      serve(SMALL, 0.55)
      render(<ComparePanel gw={5} players={PLAYERS} />)
      const card = await screen.findByTestId('compare-1')
      expect(within(card).getByTestId('breakdown-1'))
        .toHaveTextContent('These terms add up to the xPts above.')
      expect(within(card).queryByText(/sum to the horizon/)).toBeNull()
    })

  it('says which number is which when the total is a horizon and the xPts '
     + 'is one gameweek', async () => {
    // A two-fixture payload: the rows sum to 0.99 over GW5 and GW6, while the
    // xPts printed above them is GW5's 0.49. Twenty-two roundings cannot
    // explain half a point, and the caption has to name both numbers —
    // otherwise it is a sentence about one number differing from itself.
    serve(SMALL, 0.99, 0.49, [5, 6])
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId('compare-1')
    expect(within(card).getByTestId('breakdown-1')).toHaveTextContent(
      'The terms sum to the horizon (0.99); the xPts above is GW5 alone '
      + '(0.49).')
  })

  it('renders at 390px with no console error', async () => {
    // §Gates' 390px claim for this view: the Players hub's cold-clone rail
    // renders only its default tab, and Compare needs two ticked rows.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('innerWidth', 390)
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {},
      dispatchEvent: () => false,
    }))
    const { container } = render(<ComparePanel gw={5} players={PLAYERS} />)
    await screen.findByTestId('compare-1')
    // Each card is a full-width column at this width and the panel draws no
    // table, so nothing here can push the body sideways.
    expect(container.querySelectorAll('table')).toHaveLength(0)
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
    vi.unstubAllGlobals()
  })
})

// One template row so a band test states only the band.
function playerRow(over: Partial<PlayerRow>): PlayerRow {
  return { ...PLAYERS[0], ...over }
}

function renderCompare(players: PlayerRow[]) {
  render(<ComparePanel gw={5} players={players} />)
}

describe('the band beside xPts', () => {
  it('shows the band beside each compared player\u2019s xPts', async () => {
    renderCompare([playerRow({ code: 11, ep_next: 5.4, ep_lo: 4.1,
                               ep_hi: 6.8 }),
                   playerRow({ code: 22, ep_next: 3.0, ep_lo: null,
                               ep_hi: null })])
    expect(await screen.findByText('4.1\u20136.8')).toBeInTheDocument()
  })
})
