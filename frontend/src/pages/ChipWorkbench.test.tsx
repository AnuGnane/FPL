import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ChipWorkbench from './ChipWorkbench'

const { FakeApiError, apiGet, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn(), apiPost: vi.fn() }
})

vi.mock('../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const CHIPS = {
  gw: 5,
  chips: [
    { chip: 'wildcard', gw: 5, gain: 9.4, per_week: 3.1, threshold: 8.0,
      play_now: true, note: null },
    { chip: 'bboost', gw: 6, gain: 2.0, per_week: 2.0, threshold: 4.0,
      play_now: false, note: null },
    { chip: 'freehit', gw: 7, gain: 5.0, per_week: 5.0, threshold: 4.0,
      play_now: true, note: 'conservative lower bound' },
  ],
  wildcard: {
    gain_over_horizon: 9.4,
    recommend: true,
    kept: [{ code: 100, name: 'Salah', position: 'MID', price: 13,
             ep: 6.4 }],
    dropped: [{ code: 101, name: 'Watkins', position: 'FWD', price: 9,
                ep: 4.1 }],
    added: [{ code: 102, name: 'Wirtz', position: 'MID', price: 8.5,
              ep: 5.2 }],
  },
}

const PLAYERS = [
  { code: 100, name: 'Salah', position: 'MID', price: 13.0, ep_next: 6.4 },
  { code: 102, name: 'Wirtz', position: 'MID', price: 8.5, ep_next: 5.2 },
]

beforeEach(() => {
  apiGet.mockReset()
  apiPost.mockReset()
  apiGet.mockImplementation((path: string) => {
    if (path.startsWith('/api/chips')) return Promise.resolve(CHIPS)
    if (path.startsWith('/api/players')) return Promise.resolve(PLAYERS)
    return Promise.resolve({})
  })
  apiPost.mockResolvedValue({ job_id: 'job-1' })
})

describe('ChipWorkbench', () => {
  it('shows every chip week against its own threshold', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    expect(await screen.findByRole('heading', { name: /chips/i }))
      .toBeInTheDocument()
    // Two matches on purpose: the tab button and the table row.
    expect(screen.getAllByText(/wildcard/i).length).toBeGreaterThan(1)
    expect(screen.getByText('9.4')).toBeInTheDocument()
    expect(screen.getAllByLabelText(/against a bar of 8/i).length)
      .toBeGreaterThan(0)
  })

  it('marks the weeks worth playing now', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await screen.findAllByText(/wildcard/i)
    const rows = screen.getAllByRole('row')
    const playNow = rows.filter((r) => r.className.includes('changed'))
    expect(playNow).toHaveLength(2)
  })

  it('lays the wildcard squad out as kept, out and in', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click((await screen.findAllByRole('button',
      { name: /wildcard/i }))[0])
    expect(screen.getByText('Salah')).toBeInTheDocument()
    expect(screen.getByText('Watkins')).toBeInTheDocument()
    expect(screen.getByText('Wirtz')).toBeInTheDocument()
    expect(screen.getByText(/9.4 expected points/)).toBeInTheDocument()
  })

  it('submits the constrained re-solve with the chip prefilled', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    const [path, body] = apiPost.mock.calls[0]
    expect(path).toBe('/api/whatif')
    expect((body as { chip: string }).chip).toBe('wc')
  })

  it('re-solves the chip whose row was picked, not the default', async () => {
    // The page opened on the wildcard; picking Bench Boost has to reach the
    // solver, or "Try it" answers a question about a different chip than the
    // one the reader is looking at.
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /bench boost/i }))
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as { chip: string }).chip).toBe('bb')
  })

  it('maps every chip the table can name onto its request code', async () => {
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: /free hit/i }))
    await userEvent.click(screen.getByRole('button', { name: /re-solve/i }))
    await waitFor(() => expect(apiPost).toHaveBeenCalled())
    expect((apiPost.mock.calls[0][1] as { chip: string }).chip).toBe('fh')
  })

  it('shows an empty state when no advice has been run', async () => {
    apiGet.mockRejectedValue(new FakeApiError(
      404, 'no advice on disk yet — run `gaffer advise` first'))
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    expect(await screen.findByText(/run `gaffer advise` first/))
      .toBeInTheDocument()
  })

  it('says so when there is no wildcard left to assess', async () => {
    apiGet.mockImplementation((path: string) => (
      path.startsWith('/api/chips')
        ? Promise.resolve({ ...CHIPS, wildcard: null })
        : Promise.resolve(PLAYERS)))
    render(<MemoryRouter><ChipWorkbench /></MemoryRouter>)
    await userEvent.click((await screen.findAllByRole('button',
      { name: /wildcard/i }))[0])
    expect(screen.getByText(/no wildcard available/i)).toBeInTheDocument()
  })
})
