import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AdviceDiff } from '../../types'
import AdviceDiffRows from './AdviceDiffRows'

// Holiday F-154: the sentence lifted out of `WhyPanel` in v19e §2.2.

const EMPTY = {
  available: false, changed: false,
  buys_added: [], buys_dropped: [], sells_added: [], sells_dropped: [],
  captain_from: null, captain_to: null, chip_from: null, chip_to: null,
  ep_movers: [], ep_movers_count: 0, expected_pts_delta: 0,
} as unknown as AdviceDiff

describe('AdviceDiffRows', () => {
  it('says the same plan and prints no delta without a previous run', () => {
    const { container } = render(<AdviceDiffRows diff={EMPTY} />)
    expect(screen.getByText(/The same plan\./)).toBeInTheDocument()
    expect(container.textContent).not.toMatch(/xPts/)
  })

  it('writes the buys, the captain change and the delta as one sentence', () => {
    const diff = {
      ...EMPTY, available: true, changed: true,
      buys_added: [{ code: 1, name: 'Wirtz' }],
      buys_dropped: [{ code: 2, name: 'Saka' }],
      captain_from: { code: 3, name: 'Salah' },
      captain_to: { code: 4, name: 'Haaland' },
      expected_pts_delta: 1.5,
    } as unknown as AdviceDiff
    const { container } = render(<AdviceDiffRows diff={diff} />)
    expect(container.textContent).toContain(
      'buying Wirtz instead of Saka; captain Salah → Haaland.')
    expect(container.textContent).toMatch(/xPts/)
  })

  it('names the movers past the server threshold', () => {
    const diff = {
      ...EMPTY,
      ep_movers: [{ code: 5, name: 'Palmer', delta: -0.8 }],
      ep_movers_count: 1,
    } as unknown as AdviceDiff
    const { container } = render(<AdviceDiffRows diff={diff} />)
    expect(container.textContent).toContain(
      '1 player moved 0.5 xPts or more in the retrain — Palmer -0.8.')
  })
})
