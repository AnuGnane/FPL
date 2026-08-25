import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

vi.mock('./api/client', () => ({
  ApiError: class extends Error {},
  // The shell test only cares about routing, so every page stays pending:
  // a resolved empty body would feed the real pages a payload they can't read.
  apiGet: vi.fn(() => new Promise(() => {})),
  apiPost: vi.fn(async () => ({ job_id: 'x' })),
}))

describe('app shell', () => {
  it('lists every page in the sidebar', () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    for (const label of ['This Week', 'What-If Lab', 'League Race', 'Live',
      'Players', 'History', 'Model Quality', 'Runs & Health']) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument()
    }
  })

  it('navigates to the What-If Lab', async () => {
    render(<MemoryRouter><App /></MemoryRouter>)
    await userEvent.click(screen.getByRole('link', { name: 'What-If Lab' }))
    expect(await screen.findByRole('heading', { name: /what-if lab/i }))
      .toBeInTheDocument()
  })
})
