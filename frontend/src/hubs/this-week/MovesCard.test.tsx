import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MovesCard from './MovesCard'

const BUYS = [{ code: 1, name: 'Wirtz', ep: 6.1, frequency: 0.82, tag: 'attack' }]
const SELLS = [{ code: 2, name: 'Isak', ep: 3.2, frequency: 0.79 }]

describe('MovesCard', () => {
  it('lists buys as IN and sells as OUT with their sim percentages', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.getByText('Wirtz').closest('tr')).toHaveTextContent('IN')
    expect(screen.getByText('Isak').closest('tr')).toHaveTextContent('OUT')
    expect(screen.getByText('82%')).toBeInTheDocument()
  })

  it('colours the in row sage and the out row rust', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={0} />)
    expect(screen.getByText('IN')).toHaveClass('text-sage')
    expect(screen.getByText('OUT')).toHaveClass('text-rust')
  })

  it('prices hits explicitly', () => {
    render(<MovesCard buys={BUYS} sells={SELLS} hits={2} />)
    expect(screen.getByText('-8 pts')).toBeInTheDocument()
  })

  it('says to bank the transfer when there are no moves', () => {
    render(<MovesCard buys={[]} sells={[]} hits={0} />)
    expect(screen.getByText(/bank the free transfer/i)).toBeInTheDocument()
  })

  it('renders an em dash for a move with no simulation frequency', () => {
    render(<MovesCard buys={[{ code: 3, name: 'Rice', ep: 5.0 }]} sells={[]}
                      hits={0} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
