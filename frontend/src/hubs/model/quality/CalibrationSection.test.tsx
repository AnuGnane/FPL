import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CalibrationSection from './CalibrationSection'

// Moved beside the section in v18f §2.1, with the fixture and the harness the
// tab's own file used to hold for it. The two cases that are really about the
// *tab* — that a failed calibration read leaves the holdout card standing,
// and that the two cards keep distinct titles — stay in `QualityTab.test.tsx`,
// because neither claim can be made from here.

const { FakeApiError, apiGet } = vi.hoisted(() => {
  class FakeApiError extends Error {
    status: number
    detail: unknown

    constructor(status: number, detail: unknown) {
      super(typeof detail === 'string' ? detail : 'failed')
      this.status = status
      this.detail = detail
    }
  }
  return { FakeApiError, apiGet: vi.fn() }
})

vi.mock('../../../api/client', () => ({
  ApiError: FakeApiError,
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

// The v9d card. Its own fetch, its own empty state, and a footer that is as
// much the point as the table: a calibration report whose omissions and
// exclusions are hidden is a plausible-looking grade of hindsight.
const CAL_HEAD = {
  status: 'scored', n: 400, brier: 0.1234, log_loss: 0.4,
  reliability: [{ n: 200, pred: 0.2, obs: 0.25 },
                { n: 200, pred: 0.9, obs: 0.88 }],
}
const CAL_INSUFFICIENT = {
  status: 'insufficient', n: 12, brier: null, log_loss: null, reliability: [],
}

function calibrationPayload(over: Record<string, unknown> = {}) {
  return {
    available: true, run_at: '2026-09-01T00:00:00Z', git_sha: 'abc1234',
    season: '2025-26',
    // p_cs has no per-gameweek entry: one clean sheet per club-fixture is
    // about twenty rows a week, under the report's sample floor.
    gameweeks: [{ gw: 1, n: 400,
                  heads: { p_play: CAL_HEAD, p60: CAL_HEAD,
                           p_haul: CAL_INSUFFICIENT } }],
    cumulative: { p_play: CAL_HEAD, p60: CAL_HEAD, p_cs: CAL_HEAD,
                  p_haul: CAL_INSUFFICIENT },
    omitted: { p_start: 'not banked' },
    per_gw_omitted: { p_cs: 'graded per club-fixture — scored in the '
                            + 'cumulative row only' },
    excluded: [{ gw: 2, reason: 'written after kickoff' }],
    missing: [3],
    note: null,
    ...over,
  }
}

function renderWithCalibration(calibration: unknown) {
  apiGet.mockImplementation(() => Promise.resolve(calibration))
  render(<CalibrationSection />)
}

beforeEach(() => {
  apiGet.mockReset()
})

describe('v9d calibration by gameweek', () => {
  it('prints the server’s own sentence when nothing has been graded',
    async () => {
      renderWithCalibration({
        available: false, run_at: null, git_sha: null, season: null,
        gameweeks: [], cumulative: {}, omitted: {}, per_gw_omitted: {},
        excluded: [], missing: [],
        note: 'Run `gaffer evaluate --calibration` after a graded gameweek.',
      })
      expect(await screen.findByText(/after a graded gameweek/))
        .toBeInTheDocument()
      // CLI-only: JOB_KINDS maps a kind to a zero-argument callable, so there
      // is no flag a button could pass.
      expect(screen.getByText('gaffer evaluate --calibration'))
        .toBeInTheDocument()
    })

  it('renders one row per graded gameweek with each head’s Brier',
    async () => {
      renderWithCalibration(calibrationPayload())
      expect(await screen.findByRole('heading',
                                     { name: 'Calibration by gameweek' }))
        .toBeInTheDocument()
      expect(screen.getByRole('rowheader', { name: 'GW1' })).toBeInTheDocument()
      expect(screen.getAllByText('0.1234').length).toBeGreaterThan(0)
    })

  it('says "not enough data" rather than leaving a blank cell', async () => {
    // A blank reads as "perfect" at a glance, which is the worst possible
    // default for a calibration table.
    renderWithCalibration(calibrationPayload())
    expect((await screen.findAllByText(/not enough data \(12\)/)).length)
      .toBeGreaterThan(0)
  })

  it('shows p_cs cumulatively rather than a column of refusals', async () => {
    // Twenty club-fixtures a gameweek against a thirty-row floor: a per-week
    // p_cs column could only ever read "not enough data", which looks like a
    // fault in the model rather than arithmetic about the grain.
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText('cumulative only')).toBeInTheDocument()
    expect(screen.getByText(/Per gameweek: p_cs/)).toBeInTheDocument()
  })

  it('names the omitted head and why it is omitted', async () => {
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText(/Omitted: p_start — not banked/))
      .toBeInTheDocument()
  })

  it('shows an excluded gameweek with its reason', async () => {
    renderWithCalibration(calibrationPayload())
    expect(await screen.findByText(/Excluded: GW2 — written after kickoff/))
      .toBeInTheDocument()
    expect(screen.getByText(/No banked components: GW3/)).toBeInTheDocument()
  })
})
