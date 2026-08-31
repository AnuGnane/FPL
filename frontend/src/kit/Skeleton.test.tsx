import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Skeleton from './Skeleton'

describe('Skeleton', () => {
  it('occupies a card frame and says what is being waited on', () => {
    render(<Skeleton title="Solving" label="Solving the board…" />)
    expect(screen.getByTestId('skeleton')).toBeInTheDocument()
    // The frame is the point (plan A8): the panel that is about to appear has
    // a border, and the wait for it must not collapse the layout.
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Solving')
    expect(screen.getByRole('status')).toHaveTextContent('Solving the board…')
  })

  it('draws the number of bars it was asked for', () => {
    const { container } = render(<Skeleton lines={5} />)
    expect(container.querySelectorAll('[data-testid="skeleton-bar"]'))
      .toHaveLength(5)
  })
})
