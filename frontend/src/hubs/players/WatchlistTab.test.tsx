import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistTab from './WatchlistTab'
import type { WatchlistPanel } from '../../types'

const { apiGet, apiPost, apiDelete } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
}))

vi.mock('../../api/client', () => ({
  apiGet: (p: string) => apiGet(p),
  apiPost: (p: string, b: unknown) => apiPost(p, b),
  apiDelete: (p: string) => apiDelete(p),
  // The real `errorText` unwraps `detail.error` — the shape every write
  // endpoint refuses in (`api/client.ts:24-32`). A double that stringified
  // the Error instead would let the row print "Error: nope" and still pass a
  // test written about the server's sentence.
  errorText: (e: unknown) => String(
    (e as { detail?: { error?: unknown } })?.detail?.error ?? e,
  ),
  ApiError: class extends Error { status = 422; detail: unknown = null },
}))

const PANEL: WatchlistPanel = {
  rows: [
    { code: 100, name: 'Salah', note: 'if he starts', set_at: '2026-09-01T10:00:00+00:00' },
    { code: 200, name: 'Haaland', note: '', set_at: '2026-08-30T10:00:00+00:00' },
  ],
}

beforeEach(() => {
  apiGet.mockReset(); apiPost.mockReset(); apiDelete.mockReset()
  apiGet.mockResolvedValue(PANEL)
  apiPost.mockResolvedValue(PANEL)
  apiDelete.mockResolvedValue({ rows: [PANEL.rows[1]] })
})

describe('WatchlistTab', () => {
  it('lists every starred player with his note', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByText('Salah')).toBeInTheDocument()
    expect(screen.getByDisplayValue('if he starts')).toBeInTheDocument()
  })

  it('renders an empty note as an empty field, never as a placeholder value',
    async () => {
      render(<WatchlistTab onChange={vi.fn()} />)
      const field = await screen.findByLabelText('note for Haaland')
      expect(field).toHaveValue('')
    })

  it('saves a note through the same POST the star uses', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    const field = await screen.findByLabelText('note for Haaland')
    await userEvent.type(field, 'DGW target')
    await userEvent.click(screen.getByRole('button', { name: 'Save note for Haaland' }))
    await waitFor(() => {
      expect(apiPost).toHaveBeenCalledWith('/api/watchlist',
        { code: 200, note: 'DGW target' })
    })
  })

  it('saves on Enter, so a note is not a click away from a typed field',
    async () => {
      render(<WatchlistTab onChange={vi.fn()} />)
      const field = await screen.findByLabelText('note for Haaland')
      await userEvent.type(field, 'DGW target{Enter}')
      await waitFor(() => {
        expect(apiPost).toHaveBeenCalledWith('/api/watchlist',
          { code: 200, note: 'DGW target' })
      })
    })

  it('leaves focus alone when the manager moved it during the write',
    async () => {
      // The save button is disabled while the write is in flight, which in a
      // real browser drops focus to `<body>`, so it is restored when the
      // button comes back. That restore must not fire when focus is
      // somewhere the manager put it himself — taking it back mid-keystroke
      // is worse than the lost tab stop it repairs.
      //
      // The lost-focus branch itself is not testable here: jsdom does not
      // blur on `disabled`, and refuses both `blur()` and `body.focus()`
      // while the element is disabled, so focus cannot be moved off the
      // button at all. This case pins the half the suite can reach.
      let settle: (panel: WatchlistPanel) => void = () => {}
      apiPost.mockReturnValueOnce(
        new Promise<WatchlistPanel>((resolve) => { settle = resolve }))
      render(<WatchlistTab onChange={vi.fn()} />)
      const field = await screen.findByLabelText('note for Haaland')
      await userEvent.type(field, 'x')
      const save = screen.getByRole('button', { name: 'Save note for Haaland' })
      await userEvent.click(save)
      expect(save).toBeDisabled()
      const elsewhere = screen.getByRole('button', { name: 'Unstar Salah' })
      elsewhere.focus()
      settle(PANEL)
      await waitFor(() => expect(save).toBeEnabled())
      expect(elsewhere).toHaveFocus()
    })

  it('unstars through DELETE and tells the hub', async () => {
    const onChange = vi.fn()
    render(<WatchlistTab onChange={onChange} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Unstar Salah' }))
    await waitFor(() => {
      expect(apiDelete).toHaveBeenCalledWith('/api/watchlist/100')
      expect(onChange).toHaveBeenCalledWith([200])
    })
  })

  it('labels the date "noted", because saving a note resets it', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    // One label per row, and the fixture has two — so `findAllByText`, which
    // the plan wrote as `findByText` and which throws on the second match.
    expect(await screen.findAllByText(/Noted/)).toHaveLength(2)
    expect(screen.queryByText(/Watching since/)).toBeNull()
  })

  it('says what re-starring from the explorer does to a note', async () => {
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('watchlist-caveat'))
      .toHaveTextContent(/replaces the note/)
  })

  it('has an honest empty state', async () => {
    apiGet.mockResolvedValue({ rows: [] })
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state'))
      .toHaveTextContent('star')
  })

  it('has an empty state when the list cannot be read at all', async () => {
    apiGet.mockRejectedValue(new Error('cold'))
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
  })

  it('shows a failed save beside the row and keeps the typing', async () => {
    apiPost.mockRejectedValueOnce(Object.assign(new Error('nope'),
      { detail: { error: 'note is longer than 200 characters' } }))
    render(<WatchlistTab onChange={vi.fn()} />)
    const field = await screen.findByLabelText('note for Haaland')
    await userEvent.type(field, 'x')
    await userEvent.click(screen.getByRole('button', { name: 'Save note for Haaland' }))
    expect(await screen.findByTestId('watchlist-error-200'))
      .toHaveTextContent('longer than 200')
    expect(field).toHaveValue('x')
  })
})
