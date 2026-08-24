import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Health from './Health'

const apiGet = vi.hoisted(() => vi.fn())
const apiPost = vi.hoisted(() => vi.fn())
vi.mock('../api/client', () => ({
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
    render(<MemoryRouter><Health /></MemoryRouter>)
    expect(await screen.findByText('player_gw')).toBeInTheDocument()
    expect(screen.getByText('4.5h ago')).toBeInTheDocument()
    expect(screen.getByText('missing')).toBeInTheDocument()
    expect(screen.getByText(/auc_p60/)).toBeInTheDocument()
    expect(screen.getByText(/Report: reports\/gw3-report.html/))
      .toBeInTheDocument()
    expect(screen.getByText(/add an odds key/i)).toBeInTheDocument()
    expect(screen.getByText('reports/gw3-advice.json')).toBeInTheDocument()
  })

  it('fires the refresh and re-run jobs', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1' })
    render(<MemoryRouter><Health /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /refresh data/i }))
    expect(apiPost).toHaveBeenCalledWith('/api/data/refresh', undefined)
    await userEvent.click(screen.getByRole('button',
      { name: /re-run advice/i }))
    expect(apiPost).toHaveBeenCalledWith('/api/advice/rerun', undefined)
  })

  it('reads back a rejected submission instead of crashing', async () => {
    apiPost.mockRejectedValue(
      new Error('2 jobs already queued — wait for one to finish'))
    render(<MemoryRouter><Health /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-run advice/i }))
    expect(await screen.findByText(/already queued/i)).toBeInTheDocument()
    // The page keeps working: the buttons come back rather than staying
    // disabled behind a job that never started.
    expect(screen.getByRole('button', { name: /re-run advice/i }))
      .not.toBeDisabled()
  })
})
