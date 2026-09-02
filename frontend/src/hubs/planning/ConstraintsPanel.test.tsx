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
      const note = screen.getByTestId('force-out-note').textContent ?? ''
      expect(note).toMatch(/whole solve horizon/i)
      expect(note).toMatch(/credits the bank/i)
      // The claim this sentence used to make and must not: force_out pins
      // squad membership to 0 in *every* horizon week, so he cannot be bought
      // back at all.
      expect(note).not.toMatch(/bought back/i)
    })

  it('points the Must sell input at the note that explains it', () => {
    // The sentence is about one field but sat as loose text after four
    // pickers; a screen reader now reaches it from the field it describes.
    render(<ConstraintsPanel value={EMPTY} onChange={vi.fn()} />)
    expect(screen.getByLabelText('Must sell')
      .getAttribute('aria-describedby')).toBe('force-out-note')
    expect(screen.getByLabelText('Ban')
      .getAttribute('aria-describedby')).toBeNull()
  })
})
