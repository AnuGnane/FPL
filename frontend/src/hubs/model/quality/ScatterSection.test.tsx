import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScatterSection from './ScatterSection'

// Moved beside the section in v18f §2.1, out of the tab's `v8g calibration`
// block. The reliability-curve cases in that block belong to `CurrentSection`,
// which takes props and stayed in `QualityTab.tsx`; these four are this
// card's own.

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../../../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
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

function mockReview(body: unknown) {
  apiGet.mockImplementation(() => Promise.resolve(body))
}

beforeEach(() => {
  apiGet.mockReset()
  mockReview({ gws: [] })
})

describe('your points against the model’s', () => {
  it('plots both axes off the ledger, in the same unit', async () => {
    // B3. Both series are squads hand-scored off the same actuals frame:
    // mine net of hits, and mine with every comparable lane taken from the
    // model. The old card put `advise.raw_xi_pts` — an untilted EP sum over
    // the model's chosen eleven, before captaincy — on one axis and the
    // entry's official net score on the other, and drew a y = x line through
    // them.
    mockReview({ gws: [
      { gw: 1, my_points: 61, model_points: 58, no_advice: false,
        lanes: [], misses: [], notices: [] },
      { gw: 2, my_points: 44, model_points: 52, no_advice: false,
        lanes: [], misses: [], notices: [] },
      { gw: 3, my_points: 39, model_points: null, no_advice: true,
        lanes: [], misses: [], notices: [] },
    ] })
    render(<ScatterSection />)
    const chart = await screen.findByLabelText('your points against the '
                                               + 'model’s')
    expect(chart).toBeInTheDocument()
    // GW3's advice was pruned, so there is no model squad to score it
    // against — two graded weeks, not three.
    expect(screen.getByText(/2 graded gameweeks/)).toBeInTheDocument()
  })

  it('keeps the card and states the reason when nothing is graded yet',
     async () => {
    mockReview({ gws: [
      { gw: 1, my_points: 39, model_points: null, no_advice: true,
        lanes: [], misses: [], notices: [] }] })
    render(<ScatterSection />)
    expect(await screen.findByText(/No graded gameweek yet/))
      .toBeInTheDocument()
    expect(screen.queryByLabelText('your points against the model’s'))
      .toBeNull()
  })

  it('will not draw a trend through a single point', async () => {
    mockReview({ gws: [
      { gw: 1, my_points: 61, model_points: 58, no_advice: false,
        lanes: [], misses: [], notices: [] }] })
    render(<ScatterSection />)
    expect(await screen.findByText(/1 graded gameweek so far/))
      .toBeInTheDocument()
    expect(screen.queryByLabelText('your points against the model’s'))
      .toBeNull()
  })

  it('names the command that grades a gameweek in the scatter empty state',
    async () => {
      mockReview({ gws: [] })
      render(<ScatterSection />)
      expect(await screen.findByText(/No graded gameweek yet/))
        .toBeInTheDocument()
      expect(screen.getAllByText('gaffer review').length).toBeGreaterThan(0)
    })
})
