import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Chip from './Chip'

describe('Chip', () => {
  it('tints each tone with its own ink (rules 1, 2, 4)', () => {
    const { rerender } = render(<Chip tone="up">IN</Chip>)
    expect(screen.getByText('IN')).toHaveClass('bg-up-tint', 'text-up')
    rerender(<Chip tone="down">OUT</Chip>)
    expect(screen.getByText('OUT')).toHaveClass('bg-down-tint', 'text-down')
    rerender(<Chip tone="warn">75%</Chip>)
    expect(screen.getByText('75%')).toHaveClass('bg-warn-tint', 'text-warn')
    rerender(<Chip>attack</Chip>)
    expect(screen.getByText('attack')).toHaveClass('text-text-muted')
    expect(screen.getByText('attack')).not.toHaveClass('bg-up-tint')
  })

  it('is 2px-cornered and small', () => {
    render(<Chip>BB</Chip>)
    expect(screen.getByText('BB')).toHaveClass('rounded-chip')
    expect(screen.getByText('BB')).toHaveClass('text-[10px]')
  })

  it('exposes a title for hover context', () => {
    render(<Chip tone="warn" title="Knock - 75% chance">75%</Chip>)
    expect(screen.getByTitle('Knock - 75% chance')).toBeInTheDocument()
  })
})
