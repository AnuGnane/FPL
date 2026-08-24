import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ThisWeek from './ThisWeek'

const apiGet = vi.fn()
const apiPost = vi.fn()
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const LATEST = {
  gw: 3,
  mode: 'weekly',
  deadline: '2099-09-11T17:30:00Z',
  advice: {
    gw: 3,
    xi: [{ code: 100, name: 'Salah', ep: 6.4, position: 'MID' },
         { code: 101, name: 'Bloke', ep: 1.9, position: 'DEF' }],
    bench: [{ code: 103, name: 'Sub', ep: 1.1, position: 'FWD' }],
    captain: { code: 100, name: 'Salah', ep: 6.4 },
    vice: { code: 101, name: 'Bloke', ep: 1.9 },
    buys: [{ code: 100, name: 'Salah', ep: 6.4, tag: 'cover' }],
    sells: [{ code: 102, name: 'Dud', ep: 1.2 }],
    hits: 1,
    expected_pts: 61.5,
    chip_table: [{ chip: 'bboost', gw: 5, gain: 9.5, per_week: 9.5 }],
    strategy: { lam: 0.25, gap: 84, weeks_left: 36, stance: 'chase',
                rival_name: 'Ten Hag Hive' },
  },
  staleness: {
    advice_gw: 3, current_gw: 4, generated_at: '2026-09-10T09:00:00Z',
    deadline: '2099-09-11T17:30:00Z', deadline_passed: false, stale: true,
    reason: 'this advice is for GW3; GW4 is the next deadline',
  },
}

const EXPLAIN = {
  code: 100, name: 'Salah', position: 'MID', team_name: 'Liverpool',
  ep_next: 6.4,
  fixtures: [{
    gw: 3, opponent: 'Arsenal', home: true,
    kickoff_time: '2026-09-12T14:00:00Z',
    components: [{ label: 'Attacking', points: 2.71 },
                 { label: 'Minutes', points: 1.83 }],
    minutes: { p_play: 0.95, p60: 0.88 },
    calibration_delta: 0.5,
    odds: { weight: 0.7, e_goals_against: 1.17, p_cs_model: 0.25,
            p_cs_blended: 0.31, e_gc_model: 1.4, e_gc_blended: 1.2 },
    ep: 6.4,
  }],
  next_fixtures: [{ gw: 3, opponent: 'Arsenal', home: true }],
  set_pieces: { penalties: 1, free_kicks: 1, corners: 2 },
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path === '/api/advice/latest') return LATEST
    if (path === '/api/chips/plan') {
      return { gw: 3, chips: [{ chip: 'bboost', weeks: [], best_gw: 5,
                                best_gain: 9.5, best_gain_per_week: 9.5,
                                weeks_scored: 3, now_gain: 4.0,
                                play_now_delta: -5.5 },
                               { chip: 'wildcard', weeks: [], best_gw: 4,
                                 best_gain: 6.2, best_gain_per_week: 3.1,
                                 weeks_scored: 3, now_gain: 9.0,
                                 play_now_delta: 2.8 }] }
    }
    if (path === '/api/players/100/explain') return EXPLAIN
    throw new Error(`unexpected GET ${path}`)
  })
})

function renderPage() {
  render(<MemoryRouter><ThisWeek /></MemoryRouter>)
}

describe('This Week', () => {
  it('shows the XI with captain and vice badges', async () => {
    renderPage()
    // Salah appears twice — in the XI and in the transfers card — so every
    // assertion about him has to be plural-safe.
    expect((await screen.findAllByText('Salah')).length).toBeGreaterThan(0)
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
    expect(screen.getAllByText('6.4').length).toBeGreaterThan(0)
    expect(screen.getByText('Sub')).toBeInTheDocument()
  })

  it('shows transfers with their attack/cover tag and the hit cost', async () => {
    renderPage()
    expect(await screen.findByText(/IN/)).toBeInTheDocument()
    expect(screen.getByText('cover')).toBeInTheDocument()
    expect(screen.getByText(/-4 pts/)).toBeInTheDocument()
  })

  it('shows the chip best-week hint and the league strategy banner', async () => {
    renderPage()
    // The window is stated, so "best" cannot be mistaken for the whole season.
    expect(await screen.findByText(/GW5 — best of the next 3 GWs/))
      .toBeInTheDocument()
    expect(screen.getByText(/playing now costs 5.5/)).toBeInTheDocument()
    expect(screen.getByText(/84 points behind Ten Hag Hive/))
      .toBeInTheDocument()
  })

  it('prices a wildcard per week, since it covers the rest of the window',
    async () => {
      renderPage()
      // 6.2 over two weeks beats 9.0 over three: the per-week figure is what
      // makes the weeks comparable, so it is the one shown.
      expect(await screen.findByText(/\+3.1\/wk/)).toBeInTheDocument()
      expect(screen.getByText(/GW4 — best of the next 3 GWs/))
        .toBeInTheDocument()
    })

  it('renders the page while the chip plan is still loading', async () => {
    let releaseChips: (value: unknown) => void = () => {}
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/advice/latest') return LATEST
      if (path === '/api/chips/plan') {
        return new Promise((resolve) => { releaseChips = resolve })
      }
      throw new Error(`unexpected GET ${path}`)
    })
    renderPage()
    expect(await screen.findByText('Starting XI')).toBeInTheDocument()
    expect(screen.getByText(/Working out the best chip weeks/))
      .toBeInTheDocument()
    releaseChips({ gw: 3, chips: [] })
    expect(await screen.findByText('No chips available.')).toBeInTheDocument()
  })

  it('keeps the page when the chip plan fails', async () => {
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/advice/latest') return LATEST
      if (path === '/api/chips/plan') throw new Error('solver exploded')
      throw new Error(`unexpected GET ${path}`)
    })
    renderPage()
    expect(await screen.findByText('Starting XI')).toBeInTheDocument()
    expect(await screen.findByText(/solver exploded/)).toBeInTheDocument()
  })

  it('offers a re-run when the advice is stale', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1' })
    apiGet.mockImplementation(async (path: string) => {
      if (path === '/api/advice/latest') return LATEST
      if (path === '/api/chips/plan') return { gw: 3, chips: [] }
      if (path.startsWith('/api/jobs/')) {
        return { id: 'j1', status: 'done', result: { gw: 4 }, error: null }
      }
      throw new Error(`unexpected GET ${path}`)
    })
    renderPage()
    const button = await screen.findByRole('button', { name: /re-run/i })
    await userEvent.click(button)
    await waitFor(() =>
      expect(apiPost).toHaveBeenCalledWith('/api/advice/rerun', undefined))
  })

  it('opens the explain modal from a player name', async () => {
    renderPage()
    const names = await screen.findAllByRole('button', { name: 'Salah' })
    await userEvent.click(names[0])
    expect(await screen.findByRole('dialog')).toHaveTextContent('Liverpool')
    expect(screen.getByText('Attacking')).toBeInTheDocument()
    expect(screen.getByText('2.71')).toBeInTheDocument()
  })
})
