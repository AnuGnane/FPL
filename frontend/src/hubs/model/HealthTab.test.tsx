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
