import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  // The shell test only cares about routing, so every page stays pending:
  // a resolved empty body would feed the real hubs a payload they can't read.
  apiGet: vi.fn(() => new Promise(() => {})),
  apiPost: vi.fn(async () => ({ job_id: 'x', kind: 'advise' })),
}))

// One hook, both transports (v17h §6). `resetJobSlots` is stubbed alongside it
// because the shared setup clears the real hook's slots before every test and a
// mocked module has none.
vi.mock('./api/useJob', () => ({
  resetJobSlots: () => {},
  useJob: () => ({
    status: 'idle', lines: [], result: null, error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

describe('app shell', () => {
  it('lists every hub in the nav', () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    for (const label of ['This Week', 'Planning', 'Players', 'League', 'Live',
      'Model']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('navigates to Planning', async () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    await userEvent.click(screen.getByRole('link', { name: 'Planning' }))
    expect(await screen.findByRole('heading', { name: /planning/i }))
      .toBeInTheDocument()
  })
})
