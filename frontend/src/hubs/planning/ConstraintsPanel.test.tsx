import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConstraintsPanel from './ConstraintsPanel'
import type { WhatIfRequest } from '../../types'

const EMPTY: WhatIfRequest = {
  lock: [], ban: [], force_in: [], force_out: [], max_hits: 0,
  chip: 'none', horizon: null,
}

describe('ConstraintsPanel', () => {
  it('offers a must-sell picker beside the other three', () => {
    render(<ConstraintsPanel value={EMPTY} onChange={vi.fn()} />)
    for (const label of ['Lock', 'Ban', 'Force in', 'Must sell']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('lists a forced-out player as a removable chip', () => {
    const onChange = vi.fn()
    render(<ConstraintsPanel value={{ ...EMPTY, force_out: [7] }}
                             onChange={onChange} />)
    // No name is known until one is picked, so the code stands in — the same
    // fallback the other three lists already use.
    expect(screen.getByLabelText('remove 7')).toBeInTheDocument()
  })

  it('says what a must-sell means, because ban and sell are not the same',
    () => {
      render(<ConstraintsPanel value={EMPTY} onChange={vi.fn()} />)
      expect(screen.getByTestId('force-out-note').textContent)
        .toMatch(/sells him.*bank/i)
    })
})
