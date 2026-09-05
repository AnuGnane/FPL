import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Callout from './Callout'

describe('Callout', () => {
  it('is a grey note by default', () => {
    render(<Callout>Your pins are in this plan</Callout>)
    const box = screen.getByText('Your pins are in this plan').parentElement!
    expect(box).toHaveAttribute('data-tone', 'note')
    expect(box).toHaveClass('border-border', 'bg-raised')
    expect(box.querySelector('svg')).toBeNull()
  })

  it('warns in amber with an icon and passes role through', () => {
    render(<Callout tone="warn" role="alert">model has no data</Callout>)
    const box = screen.getByRole('alert')
    expect(box).toHaveClass('border-warn', 'bg-warn-tint')
    expect(box.querySelector('svg')).not.toBeNull()
    expect(box).toHaveTextContent('model has no data')
  })

  it('states an error in down ink (plan R4)', () => {
    render(<Callout tone="error" data-testid="err">no models on disk</Callout>)
    expect(screen.getByTestId('err')).toHaveClass('border-down', 'text-down')
  })
})
