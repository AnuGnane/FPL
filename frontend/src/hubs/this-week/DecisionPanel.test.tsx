import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DecisionPanel from './DecisionPanel'

const { apiGet, apiPost } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }))
vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p), apiPost: (p: string, b: unknown) => apiPost(p, b),
  errorText: (e: unknown) => String(e), ApiError: class extends Error {},
}))

const OPEN = { gw: 4, reason: null, text: '', at: null, state: 'open', deadline: null, grade: null }

beforeEach(() => { apiGet.mockReset(); apiPost.mockReset() })

describe('DecisionPanel', () => {
  it('says it opens at the deadline before it', async () => {
    apiGet.mockResolvedValue({ ...OPEN, state: 'before_deadline', deadline: '2099-09-11T17:30:00Z' })
    render(<DecisionPanel gw={4} />)
    expect(await screen.findByText(/opens at the deadline/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('offers the eight reasons and saves', async () => {
    apiGet.mockResolvedValue(OPEN)
    apiPost.mockResolvedValue({ ...OPEN, reason: 'injury', text: 'Rice out', at: 't' })
    render(<DecisionPanel gw={4} />)
    const group = await screen.findByRole('group', { name: 'Reason' })
    expect(group.querySelectorAll('button')).toHaveLength(8)
    await userEvent.click(screen.getByRole('button', { name: 'Injury' }))
    await userEvent.type(screen.getByLabelText('Note'), 'Rice out')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/decisions/4', { reason: 'injury', text: 'Rice out' }))
    expect(await screen.findByText(/Saved/)).toBeInTheDocument()
  })

  it('is read-only with the grade once graded', async () => {
    apiGet.mockResolvedValue({ ...OPEN, reason: 'gut', text: 'fancied Isak', at: 't',
      state: 'graded', grade: { lane: 'transfers', label: 'Blunder', delta_pts: -7 } })
    render(<DecisionPanel gw={4} />)
    expect(await screen.findByText('Gut')).toBeInTheDocument()
    expect(screen.getByText('fancied Isak')).toBeInTheDocument()
    expect(screen.getByText('Blunder')).toBeInTheDocument()
    expect(screen.getByText(/−7 pts|-7 pts/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
  })

  it('renders nothing when the request fails', async () => {
    apiGet.mockRejectedValue(new Error('down'))
    const { container } = render(<DecisionPanel gw={4} />)
    await new Promise((r) => { setTimeout(r, 0) })
    expect(container.textContent).toBe('')
  })
})
