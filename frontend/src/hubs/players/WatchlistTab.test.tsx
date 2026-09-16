import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistTab from './WatchlistTab'
import type { WatchlistPanel } from '../../types'

const { ApiError, apiGet, apiPost, apiDelete } = vi.hoisted(() => {
  // `usePageData` narrows on `instanceof ApiError` to fill `status`, and this
  // tab splits a failed read on that status (v18e ruling 7) — so a refusal
  // meant as the cold clone's has to be thrown as one.
  class ApiError extends Error {
    status: number
    detail: unknown = null
    constructor(status: number, message: string) {
      super(message)
      this.status = status
    }
  }
  return {
    ApiError, apiGet: vi.fn(), apiPost: vi.fn(), apiDelete: vi.fn(),
  }
})

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
  ApiError,
}))

const PANEL: WatchlistPanel = {
  rows: [
    {
      code: 100, name: 'Salah', note: 'if he starts',
      set_at: '2026-09-01T10:00:00+00:00',
      starred_at: '2026-08-10T10:00:00+00:00',
    },
    {
      code: 200, name: 'Haaland', note: '',
      set_at: '2026-08-30T10:00:00+00:00',
      starred_at: '2026-08-12T10:00:00+00:00',
    },
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

  it('labels a row that has a note "noted", because saving a note resets it',
    async () => {
      // One label per row, and only the fixture's first row has a note — so
      // `findAllByText`, which the plan wrote as `findByText` and which throws
      // on the second match.
      render(<WatchlistTab onChange={vi.fn()} />)
      expect(await screen.findAllByText(/Noted 2026-09-01/)).toHaveLength(1)
      expect(screen.queryByText(/Watching since/)).toBeNull()
    })

  it('labels a row with no note "starred", off the date the star went on',
    async () => {
      // v19h §2.2: `starred_at` is the older of the two dates and survives
      // every later write, so it is what "how long have I watched him" means.
      render(<WatchlistTab onChange={vi.fn()} />)
      expect(await screen.findAllByText(/Starred 2026-08-12/)).toHaveLength(1)
    })

  it('says what re-starring from the explorer does to a note', async () => {
    // Which, since the note tri-state landed server-side, is nothing. The old
    // caveat warned about a wipe that no longer happens, and a warning about
    // a fixed bug is a reason not to use a working button.
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('watchlist-caveat'))
      .toHaveTextContent(/no longer touches a note/)
  })

  it('has an honest empty state', async () => {
    apiGet.mockResolvedValue({ rows: [] })
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state'))
      .toHaveTextContent('star')
  })

  it('has an empty state when the list cannot be read at all', async () => {
    apiGet.mockRejectedValue(new ApiError(422, 'cold'))
    render(<WatchlistTab onChange={vi.fn()} />)
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument()
  })

  // v18e ruling 7: a page must never render a failure as a healthy empty.
  it('says the server broke rather than that the list is unavailable',
    async () => {
      apiGet.mockRejectedValue(new ApiError(500, 'boom'))
      render(<WatchlistTab onChange={vi.fn()} />)
      const callout = await screen.findByText(/boom/)
      expect(callout.closest('[data-tone="error"]')).toBeInTheDocument()
      expect(screen.queryByText(/watchlist unavailable/i))
        .not.toBeInTheDocument()
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
