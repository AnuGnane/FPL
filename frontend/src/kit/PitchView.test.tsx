import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PitchView from './PitchView'

const XI = [
  { code: 1, name: 'Raya', position: 'GKP', ep: 3.9 },
  { code: 2, name: 'Gabriel', position: 'DEF', ep: 4.6 },
  { code: 3, name: 'Salah', position: 'MID', ep: 6.4 },
  { code: 4, name: 'Haaland', position: 'FWD', ep: 7.1 },
]

describe('PitchView', () => {
  it('lays the XI out one row per position line', () => {
    render(<PitchView xi={XI} captain={4} vice={3} />)
    expect(screen.getAllByTestId(/pitch-row-/)).toHaveLength(4)
    expect(within(screen.getByTestId('pitch-row-MID'))
      .getByText('Salah')).toBeInTheDocument()
  })

  it('badges the captain and the vice', () => {
    render(<PitchView xi={XI} captain={4} vice={3} />)
    expect(screen.getByTitle('Captain')).toHaveTextContent('C')
    expect(screen.getByTitle('Vice-captain')).toHaveTextContent('V')
  })

  it('puts players with no position into one loose row', () => {
    render(<PitchView xi={[{ code: 9, name: 'Mystery', position: '', ep: 1 }]}
                      captain={0} vice={0} />)
    expect(screen.getByTestId('pitch-row-OTHER')).toBeInTheDocument()
  })

  it('calls back with the code when a player is clicked', () => {
    const clicks: number[] = []
    render(<PitchView xi={XI} captain={4} vice={3}
                      onSelect={(code) => clicks.push(code)} />)
    screen.getByRole('button', { name: /Salah/ }).click()
    expect(clicks).toEqual([3])
  })
})
