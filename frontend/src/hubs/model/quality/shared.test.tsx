import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { HeadMetrics } from '../../../types'
import { Reliability } from './shared'

// Holiday F-155: the one helper both sides of v18f §2.1's cut draw. The
// curve is recharts' to draw; what is pinned here is what the docstring says
// is printed rather than drawn — the log loss and the observation count.

// The neighbours' shim (`HoldoutSection.test.tsx`), until F-161 makes it one.
vi.mock('recharts', () => import('../../../kit/rechartsShim').then((m) => m.mockRecharts()))

const HEAD = {
  log_loss: 0.31,
  reliability: [{ pred: 0.2, obs: 0.25, n: 40 },
                { pred: 0.7, obs: 0.6, n: 60 }],
} as unknown as HeadMetrics

describe('Reliability', () => {
  it('prints the head, its log loss and the bins over their observations', () => {
    render(<Reliability label="Starts" head={HEAD} />)
    expect(screen.getByText('Starts — log loss 0.31')).toBeInTheDocument()
    expect(screen.getByLabelText('Starts reliability')).toBeInTheDocument()
    expect(screen.getByText(/2 populated bins over 100 observations/))
      .toBeInTheDocument()
  })

  it('says n/a and zero observations for a head with no bins', () => {
    render(<Reliability label="Cameo"
                        head={{ ...HEAD, log_loss: null, reliability: [] }} />)
    expect(screen.getByText('Cameo — log loss n/a')).toBeInTheDocument()
    expect(screen.getByText(/0 populated bins over 0 observations/))
      .toBeInTheDocument()
  })
})
