import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppShell from '../kit/AppShell'
import League from './League'
import Model from './Model'
import Planning from './Planning'
import Players from './Players'
import ThisWeek from './ThisWeek'
import ChipsTab from './planning/ChipsTab'
import DraftsTab from './planning/DraftsTab'
import PlannerBoard from './planning/PlannerBoard'
import SensitivityCard from './planning/SensitivityCard'
import type { WhatIfRequest } from '../types'

const { apiGet, apiPost } = vi.hoisted(
  () => ({ apiGet: vi.fn(), apiPost: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

// One hook, both transports (v17h §6). `resetJobSlots` is stubbed alongside it
// because the shared setup clears the real hook's slots before every test and a
// mocked module has none.
vi.mock('../api/useJob', () => ({
  resetJobSlots: () => {},
  useJob: () => ({
    status: 'idle', lines: [], result: null, error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

// recharts' ResponsiveContainer measures with a ResizeObserver, which jsdom
// does not implement. The chart-bearing suites clone it with a fixed box; this
// file only cares about layout classes, so an inert observer is enough.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function phone() {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: true, media: query, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

/**
 * A width, answered honestly (v19c §2.6). `phone()` above says yes to every
 * query, which is enough when only one breakpoint is in play; the three shell
 * layouts are chosen by three different queries at once, so the tests below
 * need a stub that reads the width out of the query it was handed.
 */
function viewport(width: number) {
  vi.stubGlobal('matchMedia', (query: string) => {
    const min = /min-width:\s*(\d+)px/.exec(query)
    const max = /max-width:\s*(\d+)px/.exec(query)
    const matches = (!min || width >= Number(min[1]))
      && (!max || width <= Number(max[1]))
    return {
      matches, media: query, onchange: null,
      addEventListener: () => {}, removeEventListener: () => {},
      addListener: () => {}, removeListener: () => {},
      dispatchEvent: () => false,
    }
  })
}

beforeEach(() => {
  apiGet.mockReset()
  // The captaincy chip's league what-if is fire-and-forget and This Week
  // mounts it the moment a real payload lands (v19c §2.1's rail is the first
  // test here to serve one): an unmocked POST hands the effect `undefined`
  // and the hub dies in a passive effect rather than in an assertion.
  apiPost.mockReset()
  apiPost.mockRejectedValue(new Error('no sim'))
  // Every hub must survive a total absence of artifacts on a phone: the
  // cold-clone-on-mobile case, which is the one that used to crash.
  apiGet.mockRejectedValue(Object.assign(
    new Error('no advice on disk yet — run `gaffer advise` first'),
    { status: 422 }))
  phone()
  vi.stubGlobal('ResizeObserver', NoopResizeObserver)
})

afterEach(() => { vi.unstubAllGlobals() })

describe('hubs on a phone', () => {
  const hubs: Array<[string, () => JSX.Element]> = [
    ['This Week', ThisWeek],
    ['Planning', Planning],
    ['Players', Players],
    ['League', League],
    ['Model', Model],
  ]

  for (const [name, Hub] of hubs) {
    it(`${name} renders an empty state and no console error`, async () => {
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      render(<MemoryRouter><Hub /></MemoryRouter>)
      expect(await screen.findByRole('heading', { level: 1 }))
        .toBeInTheDocument()
      expect(spy).not.toHaveBeenCalled()
      spy.mockRestore()
    })
  }
})

describe('the freshness strip on a phone', () => {
  // v12 W1 §2.9. The strip is new chrome above every hub, mounted once in
  // AppShell — so if it were the one thing in the tree that did not wrap, it
  // would scroll the body sideways on all six hubs at once.
  it('wraps instead of scrolling the body, and leaves the hub heading in place',
    async () => {
      apiGet.mockResolvedValue({ rows: [
        { source: 'refresh', age_hours: 2, modified_at: null, path: null },
        { source: 'odds', age_hours: 30, modified_at: null, path: null },
        { source: 'field', age_hours: 100, modified_at: null, path: null },
        { source: 'advise', age_hours: null, modified_at: null, path: null },
        { source: 'backup', age_hours: null, modified_at: null, path: null },
      ] })
      render(
        <MemoryRouter>
          <AppShell><h1>This Week</h1></AppShell>
        </MemoryRouter>)
      const strip = await screen.findByTestId('freshness-strip')
      expect(strip.className).toMatch(/flex-wrap/)
      expect(strip.className).not.toMatch(/whitespace-nowrap|overflow-x/)
      // The heading is still rendered as the page body: the strip sits above
      // `{children}` and does not replace or displace it.
      expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
    })
})

describe('a phone screen scrolls nothing sideways', () => {
  const EMPTY_WHATIF: WhatIfRequest = {
    lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
    max_transfers: null, chip: 'none', horizon: null,
  }

  const CHIPS = {
    gw: 5,
    chips: [{ chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1,
              threshold: 8.0, play_now: true, note: null }],
    wildcard: null,
  }

  const REPORT = {
    available: true, gw: 5, k: 20, completed: 20, failures: 0, seed: 1,
    horizon: 5, wall_s: 10, generated_at: '2026-08-31T09:00:00+00:00',
    notice: null, modal: null, runner_up: null, margin: null, verdict: null,
    frequencies: [{ kind: 'buy', code: 100, gw: 5, label: 'buy',
                    name: 'Salah', count: 18, frequency: 0.9 }],
  }

  const COMPARE = {
    gw: 5, weeks: 4,
    rows: [{ name: 'the optimum', is_reference: true,
             solved_at: '2026-08-31T09:10:00+00:00', horizon_pts: 210.4,
             expected_pts: 61.5, delta_xpts: 0, hits: 0, chip: null,
             horizon: 4, buys: [], sells: [], captain: null, error: null }],
  }

  // The invariant, plus proof that it bit: a `for` over an empty NodeList
  // passes every assertion inside it, so a hub rendered against a rejecting
  // fetch would "satisfy" this without ever drawing a table. Every caller
  // states how many tables it expects to have checked.
  function wrapped(atLeast = 1) {
    const tables = [...document.querySelectorAll('table')]
    expect(tables.length).toBeGreaterThanOrEqual(atLeast)
    for (const table of tables) {
      // Each table owns its overflow. A page-level scrollbar means one of
      // them is pushing the body, and the reader loses the nav to find out
      // which.
      expect(table.closest('.overflow-x-auto')).not.toBeNull()
    }
  }

  const RACE = {
    league_id: 1, entry_id: 1,
    standings: [{ entry: 1, name: 'Mine', player_name: 'Me', rank: 1,
                  total: 300, event_total: 60, is_you: true },
                { entry: 2, name: 'Ten Hag Hive', player_name: 'Them',
                  rank: 2, total: 290, event_total: 55, is_you: false }],
    trajectory: [{ entry: 1, name: 'Mine',
                   points: [{ gw: 5, points: 60, total: 300 }] }],
    gap: [{ gw: 5, gap: 10 }],
    win_probability: [{ name: 'Mine', total: 300, p_win: 0.5 }],
    lam: 1, stance: 'balanced', lam_explained: 'leading',
  }

  const RIVALS = [{ entry: 2, name: 'Ten Hag Hive', player_name: 'Them',
                    rank: 2, total: 290, event_total: 55, overlap: 11,
                    differentials: 4 }]

  const HEALTH = {
    data: [{ source: 'bootstrap', path: 'data/live/bootstrap.json',
             present: true, modified_at: '2026-08-31T09:00:00+00:00',
             age_hours: 2.0 }],
    models: [{ name: 'minutes', saved_at: '2026-08-30T09:00:00+00:00',
               metrics: { rmse: 1.2 } }],
    launchd: { log: 'logs/gaffer.log', present: true,
               modified_at: '2026-08-31T09:00:00+00:00',
               last_line: 'advise ok' },
    odds_key_present: true, model_health: null,
    artifacts: [{ name: 'advice_gw5.json', bytes: 4096 }],
  }

  for (const [name, Hub] of [['Model', Model], ['Players', Players]] as
    Array<[string, () => JSX.Element]>) {
    it(`lets ${name}'s tab strip scroll within its own bounds`, async () => {
      render(<MemoryRouter><Hub /></MemoryRouter>)
      const strip = await screen.findByRole('tablist')
      // Five tabs do not fit in 390px, and Model has carried six since v11
      // added Season. The strip may scroll or wrap; what it may not do is
      // make the page wider than the phone.
      expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
    })
  }

  it("lets Planning's tab strip scroll within its own bounds", async () => {
    apiGet.mockResolvedValue({
      gw: 5, mode: 'weekly', deadline: '2099-09-18T17:30:00Z',
      advice: { expected_pts: 61.5, xi: [], bench: [], buys: [], sells: [],
                captain: null, vice: null },
      staleness: { advice_gw: 5, current_gw: 5,
                   generated_at: '2026-08-29T09:00:00Z',
                   deadline: '2099-09-18T17:30:00Z', deadline_passed: false,
                   stale: false, reason: 'current for GW5',
                   data_through_gw: 4, data_warning: null },
    })
    render(<MemoryRouter><Planning /></MemoryRouter>)
    const strip = await screen.findByRole('tablist')
    expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
  })

  function serveLeague() {
    apiGet.mockImplementation((path: string) => {
      if (path === '/api/league/race') return Promise.resolve(RACE)
      if (path === '/api/league/rivals') return Promise.resolve(RIVALS)
      // The other two degrade to their own empty states by design.
      return Promise.reject(new Error('not on this clone'))
    })
  }

  it("lets League's tab strip scroll within its own bounds", async () => {
    serveLeague()
    render(<MemoryRouter><League /></MemoryRouter>)
    const strip = await screen.findByRole('tablist')
    expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
  })

  it('wraps every table League draws with a real payload', async () => {
    // A populated fixture, deliberately: League against a rejecting fetch
    // renders an EmptyState and no table at all, so the invariant below only
    // means something once the standings and the win-probability table are
    // actually on the page.
    serveLeague()
    // v15 §6.1: the hub opens on the Leagues tab, and the tables this claim
    // is about are the Race tab's — so the deep link is the one to render.
    render(
      <MemoryRouter initialEntries={['/league?tab=race']}><League /></MemoryRouter>)
    await screen.findAllByText('Ten Hag Hive')
    wrapped(2)
  })

  it('wraps every table the Health tab draws', async () => {
    // The likeliest real body scroll on a phone: the data-freshness tables
    // carry filesystem paths, which do not wrap.
    // `/api/review` answered separately: the Model hub mounts Quality beside
    // Health, and `ReviewData.gws` is required on the wire — a blanket mock
    // that hands every path the health body gives the scatter section no such
    // key.
    apiGet.mockImplementation((path: string) => Promise.resolve(
      path === '/api/review' ? { gws: [], summary: null } : HEALTH))
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('tab', { name: 'Health' }))
    await screen.findAllByText(/bootstrap/)
    wrapped(2)
  })

  it('wraps the sensitivity table in its own scroller', async () => {
    apiGet.mockResolvedValue(REPORT)
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    await screen.findByText('Salah')
    wrapped()
  })

  it('wraps the chip table in its own scroller', async () => {
    apiGet.mockResolvedValue(CHIPS)
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await screen.findAllByText(/wildcard/i)
    wrapped()
  })

  it("lets the Chips tab's three-segment strip narrow rather than push",
     async () => {
       // v9b left this control alone at two buttons — "already fits; leave
       // it". v10b §F2c makes it three, which reopens that decision, so the
       // strip states how it narrows instead of being taken on trust.
       apiGet.mockResolvedValue(CHIPS)
       render(<MemoryRouter><ChipsTab /></MemoryRouter>)
       const strip = (await screen.findByRole('button',
         { name: 'Chip table' })).parentElement!
       expect(within(strip).getAllByRole('button')).toHaveLength(3)
       expect(strip.className).toMatch(/overflow-x-auto|flex-wrap/)
     })

  it("wraps the Outlook's own table in its own scroller", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.startsWith('/api/chips/plan')) {
        return Promise.resolve({ gw: 5, chips: [] })
      }
      if (path.startsWith('/api/fixtures/outlook')) {
        return Promise.resolve({
          from_gw: 5,
          weeks: [{ gw: 6, fixtures: 11,
                    doubles: [{ code: 14, short_name: 'LIV' }],
                    blanks: [] }],
          has_doubles: true, has_blanks: false, teams_known: true,
          note: null,
        })
      }
      return Promise.resolve(CHIPS)
    })
    render(<MemoryRouter><ChipsTab /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'Season outlook' }))
    await screen.findByTestId('outlook-week-6')
    wrapped()
  })

  it('wraps the draft compare table in its own scroller', async () => {
    apiGet.mockImplementation((path: string) => (
      path === '/api/drafts'
        ? Promise.resolve({ drafts: [] })
        : Promise.resolve({ id: 'j1', status: 'done', result: COMPARE,
                            error: null })))
    render(<MemoryRouter><DraftsTab current={EMPTY_WHATIF} /></MemoryRouter>)
    // No compare has run, so there is no table yet; the assertion here is
    // that the empty state itself draws none.
    await screen.findByTestId('empty-state')
    wrapped(0)
  })
})

describe('the four tables a phone reader meets (v19c §2.1)', () => {
  // A real-shaped payload, deliberately: a hub rendered against a rejecting
  // fetch draws no table either way, so "no table at 375" would pass on an
  // empty page and mean nothing. The same bodies serve both widths, and the
  // 1400 case is the control — the desktop `<table>` is still there.
  const ADVICE = {
    gw: 5, mode: 'weekly', deadline: '2099-09-18T17:30:00Z',
    advice: {
      gw: 5, deadline: '2099-09-18T17:30:00Z', expected_pts: 61.5, hits: 1,
      xi: [{ code: 1, name: 'Salah', position: 'MID', ep: 6.4,
             team_short: 'LIV', team_code: 14, next_fixture: null }],
      bench: [{ code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6,
                team_short: 'ARS', team_code: 3, next_fixture: null }],
      captain: { code: 1, name: 'Salah', ep: 6.4 },
      vice: { code: 2, name: 'Gabriel', ep: 4.6 },
      buys: [{ code: 3, name: 'Wirtz', ep: 6.1, frequency: 0.82 }],
      sells: [{ code: 4, name: 'Isak', ep: 3.2, frequency: 0.79 }],
      scenarios: { n: 200, completed: 200, seed: 7, captain_frequency: 0.74 },
    },
    staleness: {
      advice_gw: 5, current_gw: 5, generated_at: '2026-08-29T09:00:00Z',
      deadline: '2099-09-18T17:30:00Z', deadline_passed: false, stale: false,
      reason: 'current for GW5', data_through_gw: 4, data_warning: null,
    },
  }

  const PLAYERS = [
    { code: 1, name: 'Salah', position: 'MID', team_code: 300,
      team_name: 'LIV', price: 13.0, ep_next: 6.4, ep_horizon: 12.0,
      ownership: 42.1, league_eo: 61.5, available: true, status: 'a',
      news: '', chance_of_playing: null, penalties_order: 1,
      free_kicks_order: 1, corners_order: null, in_squad: true,
      last4: [2, 9, 5, 12], element: 7, field_eo: 55.2,
      field_class: 'shield' },
    { code: 2, name: 'Gabriel', position: 'DEF', team_code: 301,
      team_name: 'ARS', price: 6.0, ep_next: 4.6, ep_horizon: 9.0,
      ownership: 30.0, league_eo: 12.0, available: true, status: 'a',
      news: '', chance_of_playing: null, penalties_order: null,
      free_kicks_order: null, corners_order: null, in_squad: true,
      last4: [], element: 8, field_eo: null, field_class: null },
  ]

  const ref = (code: number, name: string) => ({
    code, name, position: 'MID', ep: 5.0, next_fixture: null,
    team_code: null, team_short: null,
  })

  const LADDER = {
    gw: 5, gws: [5, 6, 7], generated_at: '2026-09-04T13:00:00+00:00',
    free_transfers: 1, cap: { max_hits: 2, max_transfers: null },
    cap_source: 'config', cap_rung: 'hits0', cap_rung_requested: 'hits0',
    cap_note: null, recommended: 'hits0', recommended_note: null, notes: [],
    bar: 0.6, chosen: 'hits0', served_note: null, steps: [], n_draws: 200,
    seed: 7, sigma_source: 'bands', sigma_fallbacks: 0, wall_s: 31.2,
    note: null,
    rungs: [
      { key: 'bank', hits: 0, transfers: 0, cost: 0, same_as: null,
        horizon_hits: 0, horizon_cost: 0, label: 'bank',
        plan_by_gw: [{ gw: 5, hits: 0, buys: [], sells: [],
                       xi: [ref(1, 'Salah')], bench: [ref(2, 'Gabriel')],
                       captain: ref(1, 'Salah'), vice: ref(2, 'Gabriel'),
                       expected_pts: 60 }],
        week_pts: 60, horizon_pts: 180, objective: 170, mean_pts: 180,
        p10_pts: 160, p90_pts: 200, p_beats_bank: null, p_beats_top: 0.42,
        p_best: 0.2, vs_below: null },
      { key: 'hits0', hits: 0, transfers: 1, cost: 0, same_as: null,
        horizon_hits: 0, horizon_cost: 0, label: 'free transfers only',
        plan_by_gw: [{ gw: 5, hits: 0, buys: [ref(3, 'Wirtz')],
                       sells: [ref(4, 'Isak')], xi: [ref(1, 'Salah')],
                       bench: [ref(2, 'Gabriel')], captain: ref(1, 'Salah'),
                       vice: ref(2, 'Gabriel'), expected_pts: 63 }],
        week_pts: 63, horizon_pts: 186, objective: 176, mean_pts: 186,
        p10_pts: 165, p90_pts: 207, p_beats_bank: 0.71, p_beats_top: 0.5,
        p_best: 0.3, vs_below: null },
    ],
  }

  const PLAN = {
    gw: 5, bank: 1.4, alternatives: [], objective: null,
    weeks: [{ gw: 5, hits: 0, hit_cost: 0, bank: 1.4, expected_pts: 61.5,
              chip: null, trace: null,
              buys: [{ code: 3, name: 'Wirtz', position: 'MID',
                       price: 8.6 }],
              sells: [{ code: 4, name: 'Isak', position: 'FWD',
                        price: 9.1 }] }],
  }

  function serveThisWeek() {
    const bodies: Record<string, unknown> = {
      '/api/advice/latest': ADVICE,
      '/api/players': PLAYERS,
      '/api/ladder': LADDER,
    }
    apiGet.mockImplementation((path: string) => (
      path in bodies
        ? Promise.resolve(bodies[path])
        // Every other card degrades to its own empty state, which is the
        // isolation This Week is built on and not this rail's business.
        : Promise.reject(new Error(`absent: ${path}`))))
  }

  function section(name: string): HTMLElement {
    return screen.getByRole('heading', { name })
      .closest('[data-kit="section"]') as HTMLElement
  }

  /** This Week with the squad shown as a table rather than as the pitch: the
   *  table is the thing under test and the hub opens on the pitch. */
  async function renderThisWeek() {
    serveThisWeek()
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    await screen.findByRole('heading', { name: 'Recommended moves' })
    await userEvent.click(screen.getByRole('button', { name: 'Table' }))
  }

  it('stacks the moves, the squad and the rungs on a phone', async () => {
    viewport(375)
    await renderThisWeek()
    for (const name of ['Recommended moves', 'Squad', 'Transfer ladder']) {
      expect(within(section(name)).queryByRole('table')).toBeNull()
    }
    expect(screen.getByTestId('moves-stacked')).toBeInTheDocument()
    expect(screen.getByTestId('squad-stacked')).toBeInTheDocument()
    expect(screen.getByTestId('ladder-stacked')).toBeInTheDocument()
  })

  it('draws the same three as tables at 1400', async () => {
    viewport(1400)
    await renderThisWeek()
    for (const name of ['Recommended moves', 'Squad', 'Transfer ladder']) {
      expect(within(section(name)).getByRole('table')).toBeInTheDocument()
    }
    expect(screen.queryByTestId('moves-stacked')).toBeNull()
  })

  it('stacks a week of the board on a phone and lists it at 1400', async () => {
    // The board never drew a `<table>`: its columns are rows of paragraphs
    // side by side, five of them wide. The claim at 375 is that a column's
    // moves are a stacked list, and at 1400 that they are the move rows the
    // wide board has always drawn.
    viewport(375)
    apiGet.mockImplementation((path: string) => (
      path === '/api/plan/5'
        ? Promise.resolve(PLAN)
        : Promise.reject(new Error(`absent: ${path}`))))
    render(<MemoryRouter><PlannerBoard gw={5} /></MemoryRouter>)
    const week = await screen.findByTestId('board-week-5')
    expect(within(week).queryAllByRole('table')).toHaveLength(0)
    expect(within(week).getByTestId('board-stacked-5')).toBeInTheDocument()
    expect(within(week).getByText('8.6')).toBeInTheDocument()
    cleanup()

    viewport(1400)
    render(<MemoryRouter><PlannerBoard gw={5} /></MemoryRouter>)
    const wide = await screen.findByTestId('board-week-5')
    expect(within(wide).queryByTestId('board-stacked-5')).toBeNull()
    expect(within(wide).getByTestId('board-in-3')).toBeInTheDocument()
  })
})

describe('the shell at each of the three widths', () => {
  // The shell mounts FreshnessStrip, which fetches; these tests are about the
  // frame alone, so the fetch is left pending and the strip renders nothing
  // rather than settling after the assertions and warning about act().
  function render_shell() {
    apiGet.mockImplementation(() => new Promise(() => {}))
    render(
      <MemoryRouter>
        <AppShell><h1>This Week</h1></AppShell>
      </MemoryRouter>)
    return screen.getByTestId('nav')
  }

  it('gives the tab bar the six hubs and nothing else at 375', () => {
    // v19c §2.2. The seventh slot was the theme control, which squeezed six
    // destinations into a row sized for seven; it now sits at the top of the
    // page, where a phone reader can still reach it.
    viewport(375)
    const nav = render_shell()
    expect(nav).toHaveAttribute('data-mode', 'tabbar')
    expect(within(nav).getAllByRole('link')).toHaveLength(6)
    expect(within(nav).queryByRole('button', { name: /^Theme/ })).toBeNull()
    expect(screen.getByRole('button', { name: /^Theme/ })).toBeInTheDocument()
  })

  it('draws an icon rail on a tablet and the labelled sidebar on a desktop',
    () => {
      // v19c §2.3: 900 is a landscape phone or an iPad, where 200px of nav is
      // the reason the table beside it double-scrolled.
      viewport(900)
      const rail = render_shell()
      expect(rail).toHaveAttribute('data-mode', 'rail')
      // The labels are gone from the page but not from the accessibility
      // tree: an icon with no name is a link to nowhere a screen reader can
      // describe.
      expect(within(rail).getByRole('link', { name: 'Planning' }))
        .toBeInTheDocument()
      expect(rail.textContent).not.toMatch(/Planning/)
    })

  it('draws the labelled sidebar at 1400', () => {
    viewport(1400)
    expect(render_shell()).toHaveAttribute('data-mode', 'sidebar')
  })

  it('names the main landmark so the skip link has somewhere to land', () => {
    // v19c §2.5. The link itself is in index.html, before the bundle; its
    // target is the one thing React has to provide, in every layout.
    for (const width of [375, 900, 1400]) {
      viewport(width)
      render_shell()
      expect(screen.getByRole('main')).toHaveAttribute('id', 'main')
      cleanup()
    }
  })
})
