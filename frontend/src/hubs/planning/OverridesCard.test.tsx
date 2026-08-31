import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverridesCard from './OverridesCard'

const { apiDelete, apiGet } = vi.hoisted(() => ({
  apiDelete: vi.fn(), apiGet: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
  apiDelete: (path: string) => apiDelete(path),
}))

const PANEL = {
  active: true,
  rows: [
    { code: 100, name: 'Salah', p_play: 1.0, e_min: 88, note: 'saw training',
      set_at: '2026-08-31T09:00:00+00:00', model_p_play: 0.82,
      model_e_min: 71.0 },
    { code: 101, name: 'Bloke', p_play: null, e_min: 20, note: '',
      set_at: '2026-08-31T09:05:00+00:00', model_p_play: null,
      model_e_min: null },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiDelete.mockReset()
  apiGet.mockResolvedValue(PANEL)
  apiDelete.mockResolvedValue({ active: true, rows: [PANEL.rows[1]] })
})

describe('OverridesCard', () => {
  it('lists a pin beside what the model had at the time', async () => {
    render(<MemoryRouter><OverridesCard /></MemoryRouter>)
    expect(await screen.findByText(/Salah/)).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/overrides')
    expect(screen.getByText(/p_play 1\.00 \(model had 0\.82\)/))
      .toBeInTheDocument()
    expect(screen.getByText(/saw training/)).toBeInTheDocument()
    // A pin with only expected minutes says only that.
    expect(screen.getByText(/minutes 20/)).toBeInTheDocument()
  })

  it('says the pins are stored but inert when the flag is off', async () => {
    apiGet.mockResolvedValue({ ...PANEL, active: false })
    render(<MemoryRouter><OverridesCard /></MemoryRouter>)
    expect(await screen.findByText(/saved but not being applied/))
      .toBeInTheDocument()
  })

  it('says so when nothing is pinned', async () => {
    apiGet.mockResolvedValue({ active: true, rows: [] })
    render(<MemoryRouter><OverridesCard /></MemoryRouter>)
    expect(await screen.findByText('Nothing pinned.')).toBeInTheDocument()
  })

  it('unpins through DELETE and repaints from the reply', async () => {
    render(<MemoryRouter><OverridesCard /></MemoryRouter>)
    await userEvent.click(await screen.findByRole('button',
      { name: 'unpin Salah' }))
    expect(apiDelete).toHaveBeenCalledWith('/api/overrides/100')
    await waitFor(() => expect(screen.queryByText(/saw training/))
      .not.toBeInTheDocument())
  })

  it('renders nothing at all when the panel cannot be read', async () => {
    apiGet.mockRejectedValue(new Error('nope'))
    const { container } = render(
      <MemoryRouter><OverridesCard /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 0))
    expect(container.textContent).toBe('')
  })
})
