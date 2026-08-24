import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import PitchView from './PitchView'
import type { PlayerRef } from '../types'

vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

const GROUPED: PlayerRef[] = [
  { code: 1, name: 'Raya', ep: 3.9, position: 'GKP' },
  { code: 2, name: 'Gabriel', ep: 4.6, position: 'DEF' },
  { code: 3, name: 'Salah', ep: 6.4, position: 'MID' },
  { code: 4, name: 'Haaland', ep: 7.8, position: 'FWD' },
]

describe('PitchView', () => {
  it('lays the XI out one row per position, in pitch order', () => {
    const { container } = render(
      <PitchView xi={GROUPED} captain={3} vice={4} />,
    )
    const rows = container.querySelectorAll('.pitch-row')
    expect(rows).toHaveLength(4)
    expect(rows[0].textContent).toContain('Raya')
    expect(rows[3].textContent).toContain('Haaland')
    expect(screen.getByTitle('Captain')).toBeInTheDocument()
    expect(screen.getByTitle('Vice-captain')).toBeInTheDocument()
  })

  it('still shows every player when the payload carries no position', () => {
    // Advice JSON written before v3.1 has no `position`. Grouping by line is
    // impossible, but rendering nothing at all is the worse answer.
    const flat = GROUPED.map(({ position, ...rest }) => rest)
    render(<PitchView xi={flat} captain={3} vice={4} />)
    for (const player of GROUPED) {
      expect(screen.getByText(player.name)).toBeInTheDocument()
    }
    expect(screen.getByTitle('Captain')).toBeInTheDocument()
  })

  it('appends the unpositioned players below the lines it can group', () => {
    const mixed: PlayerRef[] = [GROUPED[0], { code: 9, name: 'Mystery', ep: 2 }]
    const { container } = render(
      <PitchView xi={mixed} captain={1} vice={9} />,
    )
    const rows = container.querySelectorAll('.pitch-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('Raya')
    expect(rows[1].textContent).toContain('Mystery')
  })
})
