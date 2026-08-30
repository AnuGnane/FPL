import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle'
import { THEME_KEY } from './useTheme'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeToggle', () => {
  it('offers all three states as one labelled group', () => {
    render(<ThemeToggle />)
    const group = screen.getByRole('group', { name: 'Theme' })
    expect(group).toBeInTheDocument()
    for (const name of ['System', 'Dark', 'Light']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('marks the current state as pressed', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'System' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Dark' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('applies and persists the state it is clicked into', async () => {
    render(<ThemeToggle />)
    await userEvent.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
    expect(screen.getByRole('button', { name: 'Light' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('goes back to system, which clears the attribute', async () => {
    render(<ThemeToggle />)
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }))
    await userEvent.click(screen.getByRole('button', { name: 'System' }))
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('is one icon-only cycling control when compact', () => {
    render(<ThemeToggle compact />)
    expect(screen.getByRole('button', { name: 'Theme: system' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Light' })).toBeNull()
  })

  it('cycles system to dark to light and round again', async () => {
    render(<ThemeToggle compact />)
    await userEvent.click(screen.getByRole('button', { name: 'Theme: system' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    await userEvent.click(screen.getByRole('button', { name: 'Theme: dark' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    await userEvent.click(screen.getByRole('button', { name: 'Theme: light' }))
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })
})
