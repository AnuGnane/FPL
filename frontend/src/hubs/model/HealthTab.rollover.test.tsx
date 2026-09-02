import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HealthTab from './HealthTab'

// v12 W1 §2.4. `season_ok` has three states and the banner draws on one of
// them. The temptation a reviewer will reach for is `!data.season_ok`, which
// would paint a red mismatch warning on every cold clone — where the honest
// answer is "no data yet, cannot tell".
const apiGet = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const base = {
  data: [{ source: 'player_gw', path: 'data/live/player_gw.parquet',
           present: true, modified_at: '2026-09-10T09:00:00+00:00',
           age_hours: 4.5 }],
  models: [],
  launchd: { log: 'logs/advise.log', present: false, modified_at: null,
             last_line: null },
  odds_key_present: false,
  model_health: null,
  artifacts: [],
}

function serve(extra: Record<string, unknown>) {
  apiGet.mockImplementation(async () => ({ ...base, ...extra }))
}

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
})

describe('the season-rollover banner', () => {
  it('names both seasons when the config and the banked data disagree',
     async () => {
    serve({ season_ok: false, season_config: '2025-26',
            season_ingested: '2026-27' })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const banner = await screen.findByTestId('season-mismatch')
    expect(banner).toHaveTextContent('2026-27')
    expect(banner).toHaveTextContent('2025-26')
    expect(banner).toHaveTextContent('current_season')
    expect(banner).toHaveTextContent('train_seasons')
  })

  it('stays away when they agree', async () => {
    serve({ season_ok: true, season_config: '2026-27',
            season_ingested: '2026-27' })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.queryByTestId('season-mismatch')).toBeNull()
  })

  it('stays away when the season cannot be told', async () => {
    serve({ season_ok: null, season_config: '2026-27',
            season_ingested: null })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.queryByTestId('season-mismatch')).toBeNull()
  })

  it('stays away when an older server sends no such fields', async () => {
    serve({})
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.queryByTestId('season-mismatch')).toBeNull()
  })
})

describe('the last-backup line', () => {
  // v12 W1 §2.1. A backup nobody can see is a backup nobody notices has
  // stopped running, so this line is always drawn — with the command that
  // fixes it when there is nothing to report.
  it('names the stamp and the size', async () => {
    serve({ last_backup: { path: '/h/gaffer-backups/gaffer-20260901-2345.tar.gz',
                           modified_at: '2026-09-01T23:45:00+00:00',
                           bytes: 16_400_000 } })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const line = await screen.findByTestId('last-backup')
    expect(line).toHaveTextContent('2026-09-01 23:45')
    expect(line).toHaveTextContent('16.4 MB')
  })

  it('says never, and says what to run, when there is none', async () => {
    serve({})
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const line = await screen.findByTestId('last-backup')
    expect(line).toHaveTextContent('never')
    expect(line).toHaveTextContent('gaffer backup')
  })
})

describe('the solver pool', () => {
  // v12 W1 §2.6. The four numbers that decide who the solver may consider at
  // all, on the one page a user reads to find out what this install is doing.
  it('prints one position per served entry', async () => {
    serve({ solver_top_n: { GKP: 8, DEF: 22, MID: 26, FWD: 14 } })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const pool = await screen.findByTestId('solver-pool')
    expect(pool).toHaveTextContent('GKP 8')
    expect(pool).toHaveTextContent('DEF 22')
    expect(pool).toHaveTextContent('MID 26')
    expect(pool).toHaveTextContent('FWD 14')
  })

  it('is absent rather than empty when the server sends nothing', async () => {
    // The router answers `null` when the read fails, and an older server
    // sends no such key at all. Either way there is no number to show, and a
    // "Solver pool" heading over a blank line would read as "zero".
    serve({})
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.queryByTestId('solver-pool')).toBeNull()
  })
})
