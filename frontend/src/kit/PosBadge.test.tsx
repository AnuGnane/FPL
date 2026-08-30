import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PosBadge, { POS_COLOR, posColor } from './PosBadge'

describe('PosBadge', () => {
  it('prints the position in its own identity hue', () => {
    render(<PosBadge pos="MID" />)
    const badge = screen.getByTestId('pos-badge-MID')
    expect(badge).toHaveTextContent('MID')
    expect(badge.style.color).toBe('var(--color-pos-mid)')
  })

  it('uppercases a lowercase position from the payload', () => {
    render(<PosBadge pos="fwd" />)
    expect(screen.getByTestId('pos-badge-FWD').style.color)
      .toBe('var(--color-pos-fwd)')
  })

  it('renders the dot variant as colour only', () => {
    render(<PosBadge pos="DEF" variant="dot" />)
    const dot = screen.getByTestId('pos-dot-DEF')
    expect(dot).toHaveAttribute('title', 'DEF')
    expect(dot.style.background).toBe('var(--color-pos-def)')
    expect(dot).toHaveTextContent('')
  })

  it('gives an unknown position muted text and no hue', () => {
    render(<PosBadge pos="AM" />)
    const badge = screen.getByTestId('pos-badge-AM')
    expect(badge.className).toContain('text-text-muted')
    expect(badge.style.color).toBe('')
  })

  it('renders nothing at all when the payload carries no position', () => {
    const { container } = render(<PosBadge pos={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('exports every position hue as a distinct variable', () => {
    expect(Object.keys(POS_COLOR)).toEqual(['GKP', 'DEF', 'MID', 'FWD'])
    expect(new Set(Object.values(POS_COLOR)).size).toBe(4)
    expect(posColor('gkp')).toBe('var(--color-pos-gkp)')
    expect(posColor('striker')).toBeNull()
  })
})
