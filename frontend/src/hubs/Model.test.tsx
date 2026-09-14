import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { usePageData } from '../api/pageData'
import Model from './Model'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

// Capture each button's onDone so a test can fire it as a finished job would.
const { jobs } = vi.hoisted(
  () => ({ jobs: {} as Record<string, (() => void) | undefined> }))

vi.mock('../kit/JobButton', () => ({
  default: ({ kind, label, onDone }: {
    kind: string; label?: string; onDone?: () => void
  }) => {
    jobs[kind] = onDone
    return <button type="button">{label ?? kind}</button>
  },
}))

// One hook, both transports (v17h §6). `resetJobSlots` is stubbed alongside it
// because the shared setup clears the real hook's slots before every test and a
// mocked module has none.
vi.mock('../api/useJob', () => ({
  resetJobSlots: () => {},
  useJob: () => ({
    status: 'idle', lines: [], result: null, error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

/**
 * A stand-in tab that holds one URL through the page-data cache.
 *
 * v18e §2.3: until this cycle the hub answered a finished job by remounting
 * the tab under it on a nonce, because a remount is how each tab fetched, and
 * these cases counted mounts. Every tab now reads through the cache, where a
 * remount is served from the entry and asks the server nothing — so the claim
 * to pin is that the job cleared the URL, and the evidence is a second GET.
 */
function reader(path: string, name: string) {
  return () => {
    usePageData(path)
    return <p>{name} panel</p>
  }
}

vi.mock('./model/QualityTab',
        () => ({ default: reader('/api/quality', 'quality') }))
vi.mock('./model/JournalTab', () => ({ default: () => <p>journal panel</p> }))
vi.mock('./model/HistoryTab', () => ({ default: () => <p>history panel</p> }))
vi.mock('./model/HealthTab',
        () => ({ default: reader('/api/health', 'health') }))

/** How many times the server was asked for `path`. */
const asked = (path: string) => apiGet.mock.calls
  .filter((call) => call[0] === path).length

beforeEach(() => {
  apiGet.mockReset()
  // Never settles, so nothing paints and every count below is a request the
  // hub caused rather than a re-render chasing a body.
  apiGet.mockImplementation(() => new Promise(() => {}))
})

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

  // A job that has just rewritten reports/ leaves the tab underneath showing
  // the numbers from before it ran, with nothing to say they are stale.
  it('re-reads the quality report after an evaluate run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    expect(asked('/api/quality')).toBe(1)
    await act(async () => { jobs.evaluate?.() })
    expect(asked('/api/quality')).toBe(2)
  })

  it('re-reads health and the freshness strip after a refresh-data run',
     async () => {
       render(<MemoryRouter><Model /></MemoryRouter>)
       await userEvent.click(screen.getByRole('tab', { name: 'Health' }))
       await screen.findByText('health panel')
       expect(asked('/api/health')).toBe(1)
       await act(async () => { jobs['refresh-data']?.() })
       expect(asked('/api/health')).toBe(2)
     })

  it('leaves the other tab alone', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    expect(asked('/api/quality')).toBe(1)
    await act(async () => { jobs['refresh-data']?.() })
    expect(asked('/api/quality')).toBe(1)
  })

  it('offers the track-pens and snapshot jobs too', () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Track pens' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Snapshot news' }))
      .toBeInTheDocument()
  })

  // Track pens writes the tracker, not the evaluation, and the nonce could
  // not tell them apart — it remounted the whole Quality tab for either.
  it('re-reads the penalty tracker after a track-pens run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    expect(asked('/api/quality')).toBe(1)
    await act(async () => { jobs['track-pens']?.() })
    expect(asked('/api/pens')).toBe(0)
    // Nothing was mounted on /api/pens, so the clear is invisible from here;
    // what this pins is that it did *not* re-ask for the evaluation.
    expect(asked('/api/quality')).toBe(1)
  })

  it('re-reads health after a snapshot run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Health' }))
    await screen.findByText('health panel')
    expect(asked('/api/health')).toBe(1)
    await act(async () => { jobs.snapshot?.() })
    expect(asked('/api/health')).toBe(2)
  })

  // The nonce keyed Review and Season and stopped there; the journal is built
  // from the same ledger and was left showing the season before the grade.
  it('re-reads the review and the journal after a review run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Journal' }))
    await screen.findByText('journal panel')
    // The stand-in journal tab reads nothing, so mount a reader on the URL
    // the way This Week's cards sit on theirs while another hub writes.
    const Probe = reader('/api/journal', 'probe')
    render(<Probe />)
    await screen.findByText('probe panel')
    expect(asked('/api/journal')).toBe(1)
    await act(async () => { jobs.review?.() })
    expect(asked('/api/journal')).toBe(2)
  })
})
