import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SensitivityCard from './SensitivityCard'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

// The card's action is a JobButton, whose own stream and /api/jobs/current
// probe belong to its own test. Stub it down to the one fact this file cares
// about: which kind it was asked to run.
vi.mock('../../kit/JobButton', () => ({
  default: ({ kind, onRunning }:
    { kind: string; onRunning?: (running: boolean) => void }) => (
    // The real button owns the stream and reports the transition (plan A10);
    // the stub reports it on a click, which is the only fact this file needs.
    <button type="button" onClick={() => onRunning?.(true)}>run {kind}</button>
  ),
}))

const REPORT = {
  available: true, gw: 5, k: 20, completed: 20, failures: 0, seed: 20260831,
  horizon: 5, wall_s: 41.2, generated_at: '2026-08-31T09:00:00+00:00',
  notice: null,
  frequencies: [
    { kind: 'buy', code: 100, gw: 5, label: 'buy', name: 'Salah',
      count: 18, frequency: 0.9 },
    { kind: 'captain', code: 101, gw: 5, label: 'captain', name: 'Haaland',
      count: 12, frequency: 0.6 },
    // Filtered out: not one of the move kinds the card lists.
    { kind: 'hold', code: 0, gw: 5, label: 'no transfer', name: '',
      count: 4, frequency: 0.2 },
  ],
  modal: null, runner_up: null, margin: 1.24,
  verdict: 'nine of ten re-solves bought Salah',
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(REPORT)
})

describe('SensitivityCard', () => {
  it('renders the verdict, the shares and the margin line', async () => {
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/nine of ten re-solves/))
      .toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/sensitivity')
    expect(screen.getByText('90%')).toBeInTheDocument()
    expect(screen.getByText('18/20')).toBeInTheDocument()
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText(/best differing plan is 1\.2 expected/))
      .toBeInTheDocument()
  })

  it('lists only the move kinds it can price, most frequent first', async () => {
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    await screen.findByText('Salah')
    expect(screen.queryByText('no transfer')).not.toBeInTheDocument()
    const names = screen.getAllByRole('row').slice(1)
      .map((row) => row.textContent)
    expect(names[0]).toContain('Salah')
    expect(names[1]).toContain('Haaland')
  })

  it('says the runner-up is ahead when the margin is negative', async () => {
    // The counts and the true board disagreeing is the one thing this line
    // must not state backwards.
    apiGet.mockResolvedValue({ ...REPORT, margin: -1.24 })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/1\.2 expected points ahead/))
      .toBeInTheDocument()
    expect(screen.getByText(/not the highest-scoring one/))
      .toBeInTheDocument()
  })

  it('adds the noise caveat to the negative margin without eating it',
     async () => {
    // I1. A margin inside the noise on a *negative* margin is two facts, not
    // one: the runner-up is ahead, and the ordering is not solid. The caveat
    // used to be spliced in where the "most frequent plan is not the
    // highest-scoring one" clause goes, so the noisiest case was the one
    // where the card stopped saying which plan actually scored more.
    apiGet.mockResolvedValue({ ...REPORT, margin: -0.4, decision_sigma: 1.2 })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/0\.4 expected points ahead/))
      .toBeInTheDocument()
    expect(screen.getByText(/not the highest-scoring one/))
      .toBeInTheDocument()
    expect(screen.getByText(/the ranking is not solid/)).toBeInTheDocument()
  })

  it('says how wrong the forecast might be, not how much football varies',
     async () => {
    apiGet.mockResolvedValue({ ...REPORT, margin: 0.4, decision_sigma: 1.2 })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/how wrong the forecast/))
      .toBeInTheDocument()
  })

  it('says every re-solve agreed when there is no margin', async () => {
    apiGet.mockResolvedValue({ ...REPORT, margin: null })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/reached the same decision/))
      .toBeInTheDocument()
  })

  it('shows the notice and no table when nothing has been swept', async () => {
    apiGet.mockResolvedValue({
      available: false, gw: 5, k: 0, completed: 0, failures: 0, seed: null,
      horizon: 0, wall_s: null, generated_at: null,
      notice: 'no sensitivity report for GW5 — run it',
      frequencies: [], modal: null, runner_up: null, margin: null,
      verdict: null,
    })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/no sensitivity report for GW5/))
      .toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('says the fetch failed rather than that nothing has been swept',
    async () => {
      apiGet.mockRejectedValue(new Error('nope'))
      render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
      expect(await screen.findByText(/could not be read/))
        .toBeInTheDocument()
      expect(screen.queryByText(/No sensitivity report yet/))
        .not.toBeInTheDocument()
    })

  it('stamps the report with when it was swept', async () => {
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/2026-08-31 09:00/)).toBeInTheDocument()
  })

  it('says how many solves the sweep lost', async () => {
    // A report of twelve completed solves out of twenty is a different
    // report from one of twenty, and the shares below are out of twelve.
    apiGet.mockResolvedValue({ ...REPORT, completed: 18, failures: 2 })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/2 of the 20 re-solves failed/))
      .toBeInTheDocument()
  })

  it('counts the re-solves the report says it ran', async () => {
    apiGet.mockResolvedValue({ ...REPORT, k: 40, completed: 40 })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByText(/re-solved 40 times/)).toBeInTheDocument()
  })

  it('leaves out a timing it was not given', async () => {
    apiGet.mockResolvedValue({ ...REPORT, wall_s: null, seed: null })
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    await screen.findByText(/nine of ten re-solves/)
    expect(screen.queryByText(/Swept in/)).not.toBeInTheDocument()
  })

  it('offers the sensitivity job as its action', async () => {
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'run sensitivity' }))
      .toBeInTheDocument()
  })

  it('pulses the card body while the sweep runs', async () => {
    // The one panel of the four with a real stream under it (plan A9): the
    // skeleton and JobButton's own log show together.
    apiGet.mockResolvedValue(REPORT)
    render(<MemoryRouter><SensitivityCard /></MemoryRouter>)
    await screen.findByText(/nine of ten re-solves/)
    fireEvent.click(screen.getByText(/run sensitivity/))
    expect(await screen.findByTestId('skeleton')).toBeInTheDocument()
    // The answer it is about to replace is gone, not pulsing underneath.
    expect(screen.queryByText(/nine of ten re-solves/)).not.toBeInTheDocument()
  })
})
