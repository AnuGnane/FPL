import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HealthTab from './HealthTab'

const apiGet = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
vi.mock('../../api/client', () => ({
  ApiError: class extends Error {},
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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
      jobs: [{ label: 'advise', schedule: 'Thu 18:00', log: 'logs/advise.log',
               modified_at: '2026-09-10T09:05:00+00:00', age_hours: 4.0,
               interval_hours: 168, overdue: false },
             { label: 'field', schedule: 'Sat, Sun 18:30',
               log: 'logs/field.log', modified_at: '2026-09-01T12:30:00+00:00',
               age_hours: 220.0, interval_hours: 84, overdue: true }],
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

  it('lists every installed job and names the one that has stopped',
     async () => {
       // v19a §2.3. A launchd job that stops is invisible everywhere else: the
       // artifacts it writes simply age, and nothing on any page says which
       // timer stopped writing them.
       render(<MemoryRouter><HealthTab /></MemoryRouter>)
       expect(await screen.findByText('advise')).toBeInTheDocument()
       expect(screen.getByText('field')).toBeInTheDocument()
       expect(screen.getByText('Thu 18:00')).toBeInTheDocument()
       expect(screen.getByText('Sat, Sun 18:30')).toBeInTheDocument()
       expect(screen.getByText('9d')).toBeInTheDocument()
       // The word, not only the colour.
       expect(screen.getByText('overdue')).toHaveClass('text-down')
       expect(screen.getByText('ok')).toBeInTheDocument()
     })

  it('says no job is installed rather than drawing an empty table',
     async () => {
       apiGet.mockImplementation(async () => ({
         data: [], models: [], artifacts: [], odds_key_present: true,
         model_health: null, jobs: [],
         launchd: { log: 'logs/advise.log', present: false, modified_at: null,
                    last_line: null },
       }))
       render(<MemoryRouter><HealthTab /></MemoryRouter>)
       expect(await screen.findByText(/No launchd jobs were found/))
         .toBeInTheDocument()
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

describe('The model’s two free readings', () => {
  // v19g §2.1 and §2.2. Both lines are read-only over what is already banked,
  // and both are absent — not zero — on a clone that has never trained or
  // never advised.
  const withModel = (calibration: unknown, teamModel: unknown) => {
    apiGet.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/jobs/')) {
        return { id: 'j1', status: 'done', result: null, error: null }
      }
      return {
        data: [], models: [], artifacts: [], odds_key_present: true,
        model_health: null, jobs: [],
        launchd: { log: 'logs/advise.log', present: false,
                   modified_at: null, last_line: null },
        calibration, team_model: teamModel,
      }
    })
  }

  const FITTED = {
    by_pos: { GKP: 0.43, DEF: 1.06, MID: 1.15, FWD: 0.99 },
    fitted_positions: ['GKP', 'DEF', 'MID', 'FWD'],
    missing: [], min_rows: 200, saved_at: '2026-09-11T13:43:00+00:00',
  }

  const BAND = {
    gw: 6, min_e_gc_model: 0.044, max_p_cs_model: 0.957,
    fixtures: 20, zero_odds_fixtures: 20,
  }

  it('names every position’s calibration delta', async () => {
    withModel(FITTED, null)
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const line = await screen.findByTestId('calibration-by-pos')
    // Two decimals, and the model's own order rather than the dict's.
    expect(line.textContent).toContain('GKP 0.43')
    expect(line.textContent).toContain('DEF 1.06')
    expect(line.textContent).toContain('MID 1.15')
    expect(line.textContent).toContain('FWD 0.99')
    expect(line.textContent).not.toContain('not fitted')
  })

  it('says a position is not fitted rather than leaving it blank', async () => {
    // The failure this line exists for: an unfitted position is the identity,
    // which on a page of numbers is a delta of zero unless it is named.
    withModel({
      ...FITTED,
      by_pos: { DEF: 1.06, MID: 1.15, FWD: 0.99 },
      fitted_positions: ['DEF', 'MID', 'FWD'], missing: ['GKP'],
    }, null)
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    const line = await screen.findByTestId('calibration-by-pos')
    expect(line.textContent).toContain('GKP not fitted (n < 200)')
    expect(screen.getByText(/GKP not fitted/)).toHaveClass('text-warn')
  })

  it('renders nothing at all when no calibration is banked', async () => {
    withModel(null, null)
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    await screen.findByText('Models')
    expect(screen.queryByTestId('calibration-by-pos')).toBeNull()
  })

  it('names the week’s goals-conceded band and its zero-odds count',
     async () => {
       withModel(null, BAND)
       render(<MemoryRouter><HealthTab /></MemoryRouter>)
       const line = await screen.findByTestId('team-model-band')
       expect(line.textContent).toContain('horizon through GW6')
       expect(line.textContent).toContain('min e_gc 0.044')
       expect(line.textContent).toContain('max p_cs 0.957')
       expect(line.textContent)
         .toContain('20 of 20 fixtures without market odds')
     })

  it('leaves the band silent when nothing has been banked', async () => {
    withModel(null, null)
    render(<MemoryRouter><HealthTab /></MemoryRouter>)
    await screen.findByText('Models')
    expect(screen.queryByTestId('team-model-band')).toBeNull()
  })

  it('keeps the zero-odds count in plain ink when every fixture has a market',
     async () => {
       // Doubt is doubt and no doubt is not: a count of nought priced on the
       // model alone is the healthy state and must not read as a warning.
       withModel(null, { ...BAND, zero_odds_fixtures: 0 })
       render(<MemoryRouter><HealthTab /></MemoryRouter>)
       const line = await screen.findByTestId('team-model-band')
       expect(line.textContent)
         .toContain('0 of 20 fixtures without market odds')
       expect(screen.getByText(/0 of 20 fixtures/))
         .toHaveClass('text-text-muted')
     })
})
