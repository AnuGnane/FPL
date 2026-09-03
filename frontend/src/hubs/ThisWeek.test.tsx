import {
  fireEvent, render, screen, waitFor, within,
} from '@testing-library/react'
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
    xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4,
           team_short: 'LIV', team_code: 14,
           next_fixture: { opponent_short: 'MUN', home: true,
                           kickoff_utc: '2026-09-12T14:00:00Z',
                           difficulty: 0.31 } }],
    bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6,
              team_short: 'ARS', team_code: 3, next_fixture: null }],
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
    in_squad: true, last4: [2, 9, 5, 12], element: 7,
    field_eo: 55.2, field_class: 'shield' },
  { code: 2, name: 'Gabriel', position: 'DEF', team_code: 301,
    team_name: 'ARS', price: 6.0, ep_next: 4.6, ep_horizon: 9.0,
    ownership: 30.0, league_eo: 12.0, available: true, status: 'a',
    news: '', chance_of_playing: null, penalties_order: null,
    free_kicks_order: null, corners_order: null, in_squad: true,
    last4: [], element: 8, field_eo: null, field_class: null },
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
    // v9a: the pitch is the default view, so the bare '61.5' that used to
    // come off the squad table's EO cell is now only the stat tile's value.
    expect(screen.getByText('61.5 pts')).toBeInTheDocument()
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
    // v9a: one click away rather than on screen at load — the table itself
    // is unchanged.
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
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
         .toHaveTextContent('+3pp')
     })

  it('asks only for a cached answer, never for a fresh fetch storm', async () => {
    apiPost.mockResolvedValue(null)
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/league/whatif',
      expect.objectContaining({ cached_only: true })))
  })

  it('is simply absent on a cold cache, which answers 204 as null', async () => {
    apiPost.mockResolvedValue(null)
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
    expect(screen.queryByTestId('captain-odds-chip')).not.toBeInTheDocument()
  })

  it('is simply absent when the simulation is not available', async () => {
    apiPost.mockRejectedValue(new Error('422'))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
    expect(screen.queryByTestId('captain-odds-chip')).not.toBeInTheDocument()
  })

  it('never blocks the page on it', async () => {
    apiPost.mockReturnValue(new Promise(() => {}))     // never resolves
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
  })
})


/** The advice fixture with named identity fields stripped, for the
 *  cold-backend case. */
function adviceWithout(fields: string[]) {
  const strip = (p: Record<string, unknown>) => {
    const out = { ...p }
    for (const f of fields) delete out[f]
    return out
  }
  const advice = {
    ...ADVICE.advice,
    xi: ADVICE.advice.xi.map(strip),
    bench: ADVICE.advice.bench.map(strip),
  }
  return { ...ADVICE, advice }
}

/** The one card that hosts both views. MovesCard and DigestCard draw tables
 *  of their own, so "is the table showing" has to be asked of this section
 *  and not of the page. */
async function squadCard(): Promise<HTMLElement> {
  const toggle = await screen.findByRole('button', { name: 'Pitch' })
  return toggle.closest('section') as HTMLElement
}

describe('the pitch and the table', () => {
  it('shows the pitch by default, with the bench on it', async () => {
    // D3: the pitch is This Week's default. The table is a click away and
    // stays the data-dense view.
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
    expect(screen.getByTestId('bench-strip')).toBeInTheDocument()
    expect(within(await squadCard()).queryByRole('table'))
      .not.toBeInTheDocument()
  })

  it('draws each XI player exactly once', async () => {
    // The regression A11 exists to prevent: two cards, both drawing the XI.
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await screen.findByTestId('pitch-row-MID')
    expect(within(screen.getByTestId('pitch-row-MID'))
      .getAllByText('Salah')).toHaveLength(1)
  })

  it('switches to the table and back', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
    expect(within(await squadCard()).getByRole('table')).toBeInTheDocument()
    expect(screen.queryByTestId('pitch-row-MID')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Pitch' }))
    expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
  })

  it('says which view is showing', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    const pitch = await screen.findByRole('button', { name: 'Pitch' })
    expect(pitch).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Table' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('carries the fixture chips onto the pitch', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByText(/MUN \(H\)/)).toBeInTheDocument()
  })

  it('renders the pitch when the advice carries no identity at all',
     async () => {
       // An advice payload served by a backend that could not read a single
       // snapshot: three undefined fields on every entry. The page is a page.
       apiGet.mockImplementation((path: string) => (
         path === '/api/advice/latest'
           ? Promise.resolve(adviceWithout(['team_short', 'team_code',
                                            'next_fixture']))
           : route(path)))
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       expect(await screen.findByTestId('pitch-row-MID')).toBeInTheDocument()
       expect(screen.getAllByText('Blank').length).toBeGreaterThan(0)
     })

  it('keeps the captain line and the odds chip above the pitch', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await screen.findByTestId('pitch-row-MID')
    const header = (await squadCard()).querySelector('header')!
    expect(header.textContent).toMatch(/Captain Salah/)
  })
})

describe('the captain against the field (v10b §F1a)', () => {
  const NOTE = 'The top 10k have 62.4% ± 2.8 of Salah — he is cover, '
    + 'not attack.'

  function withCaptainField(field: unknown) {
    return {
      ...ADVICE,
      advice: { ...ADVICE.advice, captain_field: field },
    }
  }

  it('prints the server’s sentence verbatim', async () => {
    // Verbatim is the assertion. The number is a claim about the data's
    // meaning and it is made once, where the data is; restating it here would
    // be a second voice saying the same thing a slightly different way.
    apiGet.mockImplementation((path: string) => (
      path === '/api/advice/latest'
        ? Promise.resolve(withCaptainField({
          code: 1, eo: 62.4, se: 2.8, n: 300, gw: 5,
          field_class: 'shield', note: NOTE,
        }))
        : route(path)))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('captain-field-note'))
      .toHaveTextContent(NOTE)
  })

  it('renders no sentence and an intact header without captain_field',
     async () => {
       // The cold-clone case, which is most weeks for most users.
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       await screen.findByTestId('pitch-row-MID')
       expect(screen.queryByTestId('captain-field-note')).toBeNull()
       const header = (await squadCard()).querySelector('header')!
       expect(header.textContent).toMatch(/Captain Salah/)
       expect(header.textContent).toMatch(/of sims/)
       expect(header.textContent).toMatch(/vice Gabriel/)
       expect(screen.getByRole('button', { name: 'Pitch' }))
         .toBeInTheDocument()
     })

  it('prints the modal captain and no percentage when the EO is null',
     async () => {
       const modalNote = 'The top 10k are captaining Haaland in GW5.'
       apiGet.mockImplementation((path: string) => (
         path === '/api/advice/latest'
           ? Promise.resolve(withCaptainField({
             code: 1, eo: null, se: null, n: null, gw: 5,
             field_class: null, note: modalNote,
             most_captained: { code: 9, name: 'Haaland', gw: 5 },
           }))
           : route(path)))
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       const note = await screen.findByTestId('captain-field-note')
       expect(note).toHaveTextContent(modalNote)
       expect(note.textContent).not.toMatch(/%/)
     })

  it('survives /api/players failing, because the sentence is not from there',
     async () => {
       apiGet.mockImplementation((path: string) => {
         if (path === '/api/advice/latest') {
           return Promise.resolve(withCaptainField({
             code: 1, eo: 62.4, se: 2.8, n: 300, gw: 5,
             field_class: 'shield', note: NOTE,
           }))
         }
         if (path.startsWith('/api/players')) {
           return Promise.reject(new Error('explorer is down'))
         }
         return route(path)
       })
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       expect(await screen.findByTestId('captain-field-note'))
         .toHaveTextContent(NOTE)
     })

  it('joins Field% onto the squad rows, and an em dash where it is unknown',
     async () => {
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
       const table = within(await squadCard()).getByRole('table')
       const salah = within(table).getByText('Salah').closest('tr')!
       expect(within(salah).getByText('55.2')).toBeInTheDocument()
       const gabriel = within(table).getByText('Gabriel').closest('tr')!
       // Never a 0: field EO's own contract is "never 0 for unknown".
       expect(within(gabriel).getAllByText('—').length).toBeGreaterThan(0)
     })
})

describe('the EO lens (v10b §F1c)', () => {
  const tinted = () => Array.from(document.querySelectorAll('[data-code]'))
    .filter((el) => (el as HTMLElement).style.borderColor !== '')

  it('is off on first render', async () => {
    // A14: off by default, and state rather than localStorage — persisting a
    // view preference is a real feature with real questions behind it.
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await screen.findByTestId('pitch-row-MID')
    expect(screen.getByRole('button', { name: /EO lens/ }))
      .toHaveAttribute('aria-pressed', 'false')
    expect(tinted()).toHaveLength(0)
  })

  it('tints the pitch when switched on and untints when switched off',
     async () => {
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       await screen.findByTestId('pitch-row-MID')
       const lens = screen.getByRole('button', { name: /EO lens/ })
       fireEvent.click(lens)
       await waitFor(() => expect(tinted().length).toBeGreaterThan(0))
       fireEvent.click(lens)
       await waitFor(() => expect(tinted()).toHaveLength(0))
     })

  it('is not offered in the table view, where there is nothing to tint',
     async () => {
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       fireEvent.click(await screen.findByRole('button', { name: 'Table' }))
       expect(screen.queryByRole('button', { name: /EO lens/ })).toBeNull()
     })
})

describe("the captain's own note (v12 W5 §6.3)", () => {
  // `captain_note` is written by `advise.py:160` and served *inside*
  // `AdviceLatest.advice`, which the server declares as `dict[str, Any]` — so
  // it has been on the wire since v4d and rendered only by the CLI and the
  // HTML report. The fixture puts it where the server does, on the envelope's
  // `advice`, exactly as `withCaptainField` does one describe above.
  function withCaptainNote(note: unknown) {
    return {
      ...ADVICE,
      advice: { ...ADVICE.advice, captain_note: note },
    }
  }

  function serve(body: unknown) {
    apiGet.mockImplementation((path: string) => (
      path === '/api/advice/latest' ? Promise.resolve(body) : route(path)))
  }

  it('renders the captain note the advice run wrote', async () => {
    serve(withCaptainNote("covering Dave's last armband"))
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByTestId('captain-note'))
      .toHaveTextContent("covering Dave's last armband")
  })

  it('draws nothing for the empty note the tilt writes when it changed nothing',
     async () => {
       // `league_mode.captaincy_note` returns "" — not null — when lam is 0 or
       // the armband did not move (`league_mode.py:425`). An empty chip is
       // worse than no chip.
       serve(withCaptainNote(''))
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       await screen.findByTestId('pitch-row-MID')
       expect(screen.queryByTestId('captain-note')).toBeNull()
       const header = (await squadCard()).querySelector('header')!
       expect(header.textContent).toMatch(/Captain Salah/)
     })

  it('draws nothing for a payload written before the field existed',
     async () => {
       render(<MemoryRouter><ThisWeek /></MemoryRouter>)
       await screen.findByTestId('pitch-row-MID')
       expect(screen.queryByTestId('captain-note')).toBeNull()
       const header = (await squadCard()).querySelector('header')!
       expect(header.textContent).toMatch(/Captain Salah/)
     })
})
