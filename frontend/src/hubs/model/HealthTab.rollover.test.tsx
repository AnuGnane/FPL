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
