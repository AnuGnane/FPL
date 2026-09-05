import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Button, { buttonClass } from './Button'

describe('Button', () => {
  it('is secondary by default: hairline, text colour, one height', () => {
    render(<Button>Rebuild</Button>)
    const b = screen.getByRole('button', { name: 'Rebuild' })
    expect(b).toHaveClass('border-border')
    expect(b).toHaveClass('h-7')
    expect(b).toHaveClass('rounded-ctl')
    expect(b).toHaveAttribute('type', 'button')
  })

  it('fills primary in accent with white text', () => {
    render(<Button variant="primary">Run advise</Button>)
    const b = screen.getByRole('button', { name: 'Run advise' })
    expect(b).toHaveClass('bg-accent')
    expect(b).toHaveClass('text-white')
    expect(b).not.toHaveClass('border-border')
  })

  it('draws ghost as text that goes accent on hover', () => {
    render(<Button variant="ghost">Close</Button>)
    expect(screen.getByRole('button', { name: 'Close' }))
      .toHaveClass('hover:text-accent-text')
  })

  it('passes disabled and aria through', () => {
    render(<Button disabled aria-pressed="true">EO lens</Button>)
    const b = screen.getByRole('button', { name: 'EO lens' })
    expect(b).toBeDisabled()
    expect(b).toHaveAttribute('aria-pressed', 'true')
  })

  it('exposes the class string for elements that are not buttons', () => {
    expect(buttonClass('primary')).toContain('bg-accent')
    expect(buttonClass('secondary', 'mt-2')).toContain('mt-2')
  })
})
