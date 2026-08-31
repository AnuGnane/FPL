import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PinDialog from './PinDialog'

const { FakeApiError, apiPost } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown
    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiPost: vi.fn() }
})

vi.mock('../../api/client', () => ({
  ApiError: FakeApiError,
  apiGet: vi.fn(),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
}))

const PANEL = { active: true, rows: [] }

function open(onClose = vi.fn(), onSaved?: (panel: unknown) => void) {
  render(
    <MemoryRouter>
      <PinDialog code={100} name="Salah" onClose={onClose}
                 onSaved={onSaved} />
    </MemoryRouter>,
  )
  return onClose
}

beforeEach(() => {
  apiPost.mockReset()
  apiPost.mockResolvedValue(PANEL)
})

describe('PinDialog', () => {
  it('posts both numbers and closes', async () => {
    const onClose = vi.fn()
    const onSaved = vi.fn()
    open(onClose, onSaved)
    await userEvent.type(screen.getByLabelText('probability of playing'), '1')
    await userEvent.type(screen.getByLabelText('expected minutes'), '85')
    await userEvent.type(screen.getByLabelText('why'), 'saw training')
    await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/overrides',
      { code: 100, p_play: 1, e_min: 85, note: 'saw training' }))
    expect(onSaved).toHaveBeenCalledWith(PANEL)
    expect(onClose).toHaveBeenCalled()
  })

  it('posts null for a field left blank', async () => {
    open()
    await userEvent.type(screen.getByLabelText('expected minutes'), '0')
    await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith(
      '/api/overrides',
      { code: 100, p_play: null, e_min: 0, note: '' }))
  })

  it('renders a structured 422 beside the fields and stays open', async () => {
    const onClose = vi.fn()
    apiPost.mockRejectedValue(new FakeApiError(422, {
      constraint: 'override_value',
      error: 'p_play must be between 0 and 1',
      players: [100],
    }))
    open(onClose)
    await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
    expect(await screen.findByText('p_play must be between 0 and 1'))
      .toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('falls back to the error message when the failure is unstructured',
    async () => {
      apiPost.mockRejectedValue(new Error('the server is down'))
      open()
      await userEvent.click(screen.getByRole('button', { name: 'Pin' }))
      expect(await screen.findByText('the server is down')).toBeInTheDocument()
    })

  it('is a labelled modal dialog that Escape closes', async () => {
    const onClose = open()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-label', 'Pin availability for Salah')
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalled()
  })

  it('closes on a backdrop click but not on a click inside', async () => {
    const onClose = open()
    await userEvent.click(screen.getByRole('dialog'))
    expect(onClose).not.toHaveBeenCalled()
    await userEvent.click(screen.getByTestId('modal-backdrop'))
    expect(onClose).toHaveBeenCalled()
  })
})
