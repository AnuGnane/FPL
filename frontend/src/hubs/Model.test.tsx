import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Model from './Model'

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: vi.fn(() => new Promise(() => {})),
  apiPost: vi.fn(),
}))

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

vi.mock('./model/QualityTab', () => ({ default: () => <p>quality panel</p> }))
vi.mock('./model/JournalTab', () => ({ default: () => <p>journal panel</p> }))
vi.mock('./model/HistoryTab', () => ({ default: () => <p>history panel</p> }))
vi.mock('./model/HealthTab', () => ({ default: () => <p>health panel</p> }))

describe('Model hub', () => {
  it('opens on the quality tab', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    expect(await screen.findByText('quality panel')).toBeInTheDocument()
  })

  it('lists all four tabs', () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    for (const name of ['Quality', 'Journal', 'History', 'Health']) {
      expect(screen.getByRole('tab', { name })).toBeInTheDocument()
    }
  })

  it('switches to the journal tab', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Journal' }))
    expect(await screen.findByText('journal panel')).toBeInTheDocument()
  })

  it('offers the evaluate and refresh-data jobs', () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Evaluate' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Refresh data' }))
      .toBeInTheDocument()
  })
})
