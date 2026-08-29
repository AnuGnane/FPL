import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JournalTab from './JournalTab'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts')
  const { cloneElement, isValidElement } = await import('react')
  return {
    ...actual,
    // The chart itself needs the measured box: cloning it with a fixed one is
    // what the real container does once it has measured.
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div style={{ width: 400, height: 200 }}>
        {isValidElement(children)
          ? cloneElement(children as React.ReactElement<Record<string, unknown>>,
                         { width: 400, height: 200 })
          : children}
      </div>
    ),
  }
})

const JOURNAL = {
  built_at: '2026-08-29T09:00:00Z',
  rows: [
    { gw: 3, model_pts: 62, actual_pts: 55, delta: 7, model_captain: 'Salah',
      actual_captain: 'Haaland', model_buys: ['Wirtz'], model_sells: ['Isak'] },
    { gw: 4, model_pts: 48, actual_pts: 51, delta: -3, model_captain: 'Salah',
      actual_captain: 'Salah', model_buys: [], model_sells: [] },
  ],
  cumulative: [
    { gw: 3, model: 62, actual: 55, delta: 7 },
    { gw: 4, model: 110, actual: 106, delta: 4 },
  ],
}

beforeEach(() => {
  apiGet.mockReset()
  apiGet.mockResolvedValue(JOURNAL)
})

describe('JournalTab', () => {
  it('lists a row per scored gameweek', async () => {
    render(<JournalTab />)
    expect(await screen.findByText('62')).toBeInTheDocument()
    expect(screen.getByText('55')).toBeInTheDocument()
  })

  it('colours a gameweek the model won sage and one it lost rust', async () => {
    render(<JournalTab />)
    expect(await screen.findByText('+7')).toHaveClass('text-sage')
    expect(screen.getByText('-3')).toHaveClass('text-rust')
  })

  it('names both captains when they differ', async () => {
    render(<JournalTab />)
    expect(await screen.findByText('Haaland')).toBeInTheDocument()
  })

  it('draws the cumulative model-vs-you chart', async () => {
    const { container } = render(<JournalTab />)
    await screen.findByText('62')
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull()
  })

  it('flags a gameweek whose only advice run was late', async () => {
    apiGet.mockResolvedValue({
      ...JOURNAL,
      rows: [{ ...JOURNAL.rows[0], post_deadline: true }, JOURNAL.rows[1]],
    })
    render(<JournalTab />)
    const badge = await screen.findByText('late run')
    expect(badge).toHaveAttribute('title', expect.stringContaining('hindsight'))
    expect(badge).toHaveClass('text-rust')
  })

  it('leaves an in-time gameweek unflagged', async () => {
    render(<JournalTab />)
    await screen.findByText('62')
    expect(screen.queryByText('late run')).toBeNull()
  })

  it('shows an empty state until a gameweek has both sides', async () => {
    apiGet.mockResolvedValue({ rows: [], cumulative: [], built_at: null })
    render(<JournalTab />)
    expect(await screen.findByText(/nothing to compare yet/i))
      .toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
  })
})
