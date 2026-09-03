import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HealthTab from './HealthTab'

const apiGet = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation(async (path: string) => {
    if (path.startsWith('/api/jobs/')) {
      return { id: 'j1', status: 'done', result: { rows: 7 }, error: null }
    }
    return {
      data: [{ source: 'player_gw', path: 'data/live/player_gw.parquet',
               present: true, modified_at: '2026-09-10T09:00:00+00:00',
               age_hours: 4.5 },
             { source: 'odds', path: 'data/live/odds/', present: false,
               modified_at: null, age_hours: null }],
      models: [{ name: 'minutes', saved_at: '2026-09-10T08:00:00+00:00',
                 metrics: { rows: 113000, auc_p60: 0.81 } }],
      launchd: { log: 'logs/advise.log', present: true,
                 modified_at: '2026-09-10T09:05:00+00:00',
                 last_line: 'Report: reports/gw3-report.html' },
      odds_key_present: false,
      model_health: { gw: 2, mae_starters: 1.4, captain_actual: 12 },
      artifacts: [{ name: 'reports/gw3-advice.json', bytes: 2048 }],
    }
  })
})

describe('Runs & Health', () => {
  it('shows freshness, models, launchd and the odds notice', async () => {
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.getByText('4.5h ago')).toBeInTheDocument()
    expect(screen.getByText('missing')).toBeInTheDocument()
    expect(screen.getByText(/auc_p60/)).toBeInTheDocument()
    expect(screen.getByText(/Report: reports\/gw3-report.html/))
      .toBeInTheDocument()
    expect(screen.getByText(/add an odds key/i)).toBeInTheDocument()
    expect(screen.getByText('reports/gw3-advice.json')).toBeInTheDocument()
  })

  it('starts no job of its own', async () => {
    // The Model hub's JobButtons are the single control. This tab carrying a
    // second pair, posting past the single-flight runner to the legacy
    // registry, is what let two advise runs write reports/ at once.
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    await screen.findByText('player_gw')
    expect(screen.queryByRole('button', { name: /refresh data/i })).toBeNull()
    expect(screen.queryByRole('button', { name: /re-run advice/i })).toBeNull()
    expect(apiPost).not.toHaveBeenCalled()
  })
})

describe('Core insights collection', () => {
  const withCoreInsights = (core: unknown) => {
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/jobs/')) {
        return { id: 'j1', status: 'done', result: { rows: 7 }, error: null }
      }
      return {
        data: [{ source: 'player_gw', path: 'data/live/player_gw.parquet',
                 present: true, modified_at: '2026-09-10T09:00:00+00:00',
                 age_hours: 4.5 }],
        models: [],
        launchd: { log: 'logs/advise.log', present: false,
                   modified_at: null, last_line: null },
        odds_key_present: true,
        artifacts: [],
        core_insights: core,
      }
    })
  }

  it('says what it is waiting for when nothing is collected', async () => {
    // A clone that has never run the collector must name the season and the
    // command, not render three zeros that look like a measurement.
    withCoreInsights({ season: '2026-27', collected: false, tables: [],
                       waiting_for: 'gaffer core-insights' })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText(/Not collected yet \(2026-27\)/))
      .toBeInTheDocument()
    expect(screen.getByText(/gaffer core-insights/)).toBeInTheDocument()
  })

  it('falls back to a named wait when the field is absent altogether', async () => {
    // An older backend, or a payload built before the field existed.
    withCoreInsights(null)
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText(/Not collected yet \(—\)/))
      .toBeInTheDocument()
    expect(screen.getByText(/a collector run/)).toBeInTheDocument()
  })

  it('distinguishes an empty table from a table with no date', async () => {
    // The 2026-27 Elo table is legitimately empty (the archive publishes a
    // blank elo column), and "—" beside a zero reads as a missing timestamp
    // rather than as an archive that has nothing to give.
    withCoreInsights({
      season: '2026-27',
      collected: true,
      waiting_for: null,
      tables: [
        { table: 'elo', rows: 0, latest: null },
        { table: 'fixtures', rows: 380, latest: '2026-09-12' },
        { table: 'players', rows: 5400, latest: 'GW4' },
      ],
    })
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    expect(await screen.findByText('elo')).toBeInTheDocument()
    expect(screen.getByText(/the archive publishes none yet/))
      .toBeInTheDocument()
    expect(screen.getByText('2026-09-12')).toBeInTheDocument()
    expect(screen.getByText('GW4')).toBeInTheDocument()
    expect(screen.queryByText(/Not collected yet/)).toBeNull()
  })
})
