import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlayerName from './PlayerName'

// vi.mock's factory is hoisted above the file body, so the spy is hoisted
// with it (the ExplainModal.test.tsx pattern).
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  apiGet.mockReset()
  // Never settles: the modal's loading state is enough to prove it opened,
  // and ExplainModal's own suite covers what it does with a payload.
  apiGet.mockReturnValue(new Promise(() => {}))
})

describe('PlayerName', () => {
  it('renders the name as the control', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.getByRole('button', { name: 'Salah' })).toBeInTheDocument()
  })

  it('carries the position dot when the row has one', () => {
    render(<PlayerName code={9} name="Salah" pos="MID" />)
    expect(screen.getByTestId('pos-dot-MID')).toBeInTheDocument()
  })

  it('leaves the dot out when the row carries no position', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.queryByTestId('pos-dot-MID')).toBeNull()
  })

  it('stays closed until it is clicked', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.queryByTestId('modal-backdrop')).toBeNull()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('opens the explain modal for its own player', async () => {
    render(<PlayerName code={9} name="Salah" />)
    await userEvent.click(screen.getByRole('button', { name: 'Salah' }))
    expect(await screen.findByRole('dialog',
                                   { name: 'Expected points explained' }))
      .toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/players/9/explain')
  })

  it("closes again on the modal's own control", async () => {
    render(<PlayerName code={9} name="Salah" />)
    await userEvent.click(screen.getByRole('button', { name: 'Salah' }))
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByTestId('modal-backdrop')).toBeNull()
  })
})
