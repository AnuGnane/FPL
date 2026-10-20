/**
 * Holiday F-153 — StatRow's hairline grid (mockup A): two tiles a row below
 * `md`, four or three at it, a 1px border gap between them and its children
 * the tiles themselves.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatRow from './StatRow'

describe('StatRow', () => {
  it('lays four tiles a row at md by default, two below it', () => {
    render(<StatRow><p>tile</p></StatRow>)
    const row = screen.getByTestId('stat-row')
    expect(row).toHaveClass('grid-cols-2', 'md:grid-cols-4', 'gap-px')
    expect(row).not.toHaveClass('md:grid-cols-3')
  })

  it('lays three a row when asked', () => {
    render(<StatRow cols={3}><p>tile</p></StatRow>)
    const row = screen.getByTestId('stat-row')
    expect(row).toHaveClass('md:grid-cols-3')
    expect(row).not.toHaveClass('md:grid-cols-4')
  })

  it('renders its children inside the grid and takes a margin override', () => {
    render(<StatRow className="mb-0"><p>tile</p></StatRow>)
    const row = screen.getByTestId('stat-row')
    expect(row).toContainElement(screen.getByText('tile'))
    expect(row).toHaveClass('mb-0')
    expect(row).not.toHaveClass('mb-4')
  })
})
