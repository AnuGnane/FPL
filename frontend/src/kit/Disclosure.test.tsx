import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Disclosure from './Disclosure'

const KEY = 'test-help'

afterEach(() => {
  vi.restoreAllMocks()
  try {
    localStorage.removeItem(KEY)
  } catch {
    // Nothing stored is nothing to clear.
  }
})

describe('Disclosure (v19d §2.3)', () => {
  it('shows its prose on a first visit, with nothing stored', () => {
    render(<Disclosure summary="How to read this"><p>the prose</p></Disclosure>)
    expect(screen.getByRole('button', { name: /how to read this/i }))
      .toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('the prose')).toBeVisible()
  })

  it('folds the prose away and remembers that it was closed', async () => {
    render(
      <Disclosure summary="How to read this" storageKey={KEY}>
        <p>the prose</p>
      </Disclosure>,
    )
    await userEvent.click(screen.getByRole('button'))
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('the prose')).not.toBeVisible()
    expect(localStorage.getItem(KEY)).toBe('closed')
  })

  it('opens closed on the next visit, having been closed on the last', () => {
    localStorage.setItem(KEY, 'closed')
    render(
      <Disclosure summary="How to read this" storageKey={KEY}>
        <p>the prose</p>
      </Disclosure>,
    )
    expect(screen.getByRole('button')).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders the prose when the browser refuses to say what was stored',
    () => {
      // Private mode, or site data blocked. The reader loses the memory of
      // their choice, never the words.
      vi.spyOn(localStorage, 'getItem').mockImplementation(() => {
        throw new Error('storage is blocked')
      })
      render(
        <Disclosure summary="How to read this" storageKey={KEY}>
          <p>the prose</p>
        </Disclosure>,
      )
      expect(screen.getByText('the prose')).toBeVisible()
    })

  it('keeps its content in the box tree while closed, so print can show it',
    () => {
      // The reason this is not a native `<details>` (v19d §2.4): a closed
      // `<details>` has nothing for `@media print` to unhide.
      const { container } = render(
        <Disclosure summary="How to read this" defaultOpen={false}>
          <p>the prose</p>
        </Disclosure>,
      )
      const content = container.querySelector('[data-disclosure]')
      expect(content).not.toBeNull()
      expect(content).toHaveAttribute('hidden')
    })
})
