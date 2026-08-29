import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { useEffect } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Model from './Model'

vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: vi.fn(() => new Promise(() => {})),
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

vi.mock('../api/useJobStream', () => ({
  useJobStream: () => ({
    status: 'idle', lines: [], error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }),
}))

// The tabs count their own mounts: a refetch after a job is a remount here.
const { mounts } = vi.hoisted(() => ({ mounts: { quality: 0, health: 0 } }))

function counter(name: 'quality' | 'health') {
  return () => {
    // Counted on mount, not on render: a sibling's state change re-renders
    // this tab without it having refetched anything.
    useEffect(() => { mounts[name] += 1 }, [])
    return <p>{name} panel</p>
  }
}

vi.mock('./model/QualityTab', () => ({ default: counter('quality') }))
vi.mock('./model/JournalTab', () => ({ default: () => <p>journal panel</p> }))
vi.mock('./model/HistoryTab', () => ({ default: () => <p>history panel</p> }))
vi.mock('./model/HealthTab', () => ({ default: counter('health') }))

beforeEach(() => { mounts.quality = 0; mounts.health = 0 })

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
  it('refetches the quality tab after an evaluate run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    const before = mounts.quality
    await act(async () => { jobs.evaluate?.() })
    expect(mounts.quality).toBeGreaterThan(before)
  })

  it('refetches the health tab after a refresh-data run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Health' }))
    await screen.findByText('health panel')
    const before = mounts.health
    await act(async () => { jobs['refresh-data']?.() })
    expect(mounts.health).toBeGreaterThan(before)
  })

  it('leaves the other tab alone', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    const before = mounts.quality
    await act(async () => { jobs['refresh-data']?.() })
    expect(mounts.quality).toBe(before)
  })
})
