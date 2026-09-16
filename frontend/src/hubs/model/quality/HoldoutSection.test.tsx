import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CurrentEvaluation } from '../../../types'
import HoldoutSection from './HoldoutSection'

// Moved beside the section in v19h §2.1, with the fixture the tab's own file
// held for it. The section takes its evaluation by props, so these cases
// render it directly: nothing here needs the tab's fetch.

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

const table = {
  zeros: { rmse: 0.9, mae: 0.4, n: 900 },
  blanks: { rmse: 1.4, mae: 0.8, n: 400 },
  tickers: { rmse: 1.6, mae: 1.2, n: 200 },
  haulers: { rmse: 5.3, mae: 4.4, n: 100 },
  all: { rmse: 2.1, mae: 1.0, n: 1600 },
}

const current = {
  run_at: '2026-08-25T00:00:00+00:00', git_sha: 'abc1234',
  holdout_slots: 10,
  stratified: { all: table, starters: table },
  heads: {
    p_play: {
      log_loss: 0.2732,
      reliability: [{ n: 40, pred: 0.9, obs: 0.88 },
                    { n: 60, pred: 0.2, obs: 0.25 }],
    },
    p60: { log_loss: 0.2563, reliability: [{ n: 10, pred: 0.5, obs: 0.5 }] },
    cs: { log_loss: 0.5511, reliability: [{ n: 10, pred: 0.3, obs: 0.28 }] },
  },
  baselines: { last5: table, last38_ppg: table },
} as CurrentEvaluation

const RELIABILITY = [{ n: 100, pred: 0.2, obs: 0.25 },
                     { n: 200, pred: 0.9, obs: 0.88 }]

function withHeads(keys: string[]) {
  return {
    ...current,
    heads: Object.fromEntries(keys.map(
      (key) => [key, { log_loss: 0.2732, reliability: RELIABILITY }])),
  } as CurrentEvaluation
}

describe('HoldoutSection', () => {
  it('shows the holdout table beside the baselines', () => {
    render(<HoldoutSection current={current} />)
    expect(screen.getByRole('heading', { name: /holdout/i }))
      .toBeInTheDocument()
    expect(screen.getByText(/last-10-slot holdout/i)).toBeInTheDocument()
    expect(screen.getAllByText('Haulers').length).toBeGreaterThan(0)
    expect(screen.getByText(/last-5 mean/i)).toBeInTheDocument()
    expect(screen.getByText(/last-38 mean/i)).toBeInTheDocument()
  })

  it('draws a reliability curve per probability head', () => {
    render(<HoldoutSection current={current} />)
    expect(screen.getByLabelText('P(plays) reliability')).toBeInTheDocument()
    expect(screen.getByLabelText('P(60+ minutes) reliability'))
      .toBeInTheDocument()
    expect(screen.getByLabelText('P(clean sheet) reliability'))
      .toBeInTheDocument()
  })

  it('draws a reliability curve for p_start, which nothing rendered before',
     () => {
       render(<HoldoutSection
         current={withHeads(['p_play', 'p60', 'cs', 'p_start'])} />)
       expect(screen.getByLabelText('P(starts) reliability'))
         .toBeInTheDocument()
     })

  it('omits a head the evaluation does not carry', () => {
    render(<HoldoutSection current={withHeads(['p_play'])} />)
    expect(screen.getByLabelText('P(plays) reliability')).toBeInTheDocument()
    expect(screen.queryByLabelText('P(starts) reliability')).toBeNull()
  })

  it('says how many observations each curve rests on', () => {
    // The bins carry n; a curve over forty rows and one over forty thousand
    // look identical without it.
    render(<HoldoutSection current={withHeads(['p_play'])} />)
    expect(screen.getByText(/over 300 observations/)).toBeInTheDocument()
  })
})
