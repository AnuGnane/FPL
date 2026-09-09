import { readFileSync } from 'node:fs'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DecisionPanel from '../hubs/this-week/DecisionPanel'
import { invalidate } from './pageData'

/**
 * A write must not leave a cached card stale (v17h §5).
 *
 * Before v17h every navigation refetched, so no write could strand a panel.
 * With one body per URL held until something clears it, a write whose GET
 * nobody invalidates is a page showing the value the user just changed away
 * from — and the writer is often in a different hub from the reader, which is
 * why this is a table and not a code review.
 *
 * Two instruments, because they catch different mistakes. The table below
 * holds the spec to the source and would catch a *future* writer added with
 * no invalidation beside it; the two cases under it drive the mechanism and
 * prove it actually re-reads, which reading source can never show.
 */

/** file → the URLs its write must clear. Spec §5, transcribed. */
const TABLE: Record<string, string[]> = {
  'src/hubs/this-week/LadderCard.tsx': ["'/api/settings'"],
  'src/hubs/model/SettingsTab.tsx': ["'/api/settings'"],
  'src/hubs/League.tsx': ["'/api/settings'", "'/api/league/leagues'"],
  'src/hubs/this-week/DecisionPanel.tsx': ['`/api/decisions/${gw}`'],
  'src/hubs/players/PinDialog.tsx': ["'/api/overrides'"],
  // The spec put the unpin on the Players hub, where the pin *dialog* lives.
  // The DELETE is the planning card's, and the reader it disturbs — the Why
  // panel's pin list — is the same one either way.
  'src/hubs/planning/OverridesCard.tsx': ["'/api/overrides'"],
}

describe('every write clears the cached reads it disturbs', () => {
  for (const [file, urls] of Object.entries(TABLE)) {
    for (const url of urls) {
      it(`${file} invalidates ${url}`, () => {
        const source = readFileSync(file, 'utf8')
        expect(source).toContain(`invalidate(${url})`)
      })
    }
  }
})

const { apiGet, apiPost } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPost: vi.fn(),
}))
vi.mock('./client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  apiDelete: (path: string) => apiGet(path),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

// `open` is the one state with the reason control and the save button on it:
// before the deadline the panel is a sentence and after the grade it is
// read-only, and neither can write.
const NOTE = { gw: 5, reason: null, text: '', at: null, state: 'open',
               deadline: '2020-01-01T00:00:00Z', grade: null }

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(NOTE)
  apiPost.mockReset()
  apiPost.mockResolvedValue({ ...NOTE, reason: 'gut', text: 'took the rung' })
})

describe('the mechanism, not only the source', () => {
  it('re-reads the note after the decision panel saves one', async () => {
    render(<DecisionPanel gw={5} />)
    await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(1) })
    fireEvent.click(screen.getByRole('button', { name: 'Gut' }))
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(2) })
    expect(apiGet).toHaveBeenLastCalledWith('/api/decisions/5')
  })

  // The cross-hub half of §5, with the writer stood in for by the call it
  // makes: a card mounted on a URL some other hub has just written re-reads
  // it where it stands, without being told by whoever wrote it.
  it('re-reads for a card mounted on a URL another hub just wrote',
     async () => {
       render(<DecisionPanel gw={5} />)
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(1) })
       invalidate('/api/decisions/5')
       await waitFor(() => { expect(apiGet).toHaveBeenCalledTimes(2) })
     })
})
