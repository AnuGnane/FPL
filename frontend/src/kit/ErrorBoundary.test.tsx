import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ErrorBoundary from './ErrorBoundary'

function Boom({ throws }: { throws: boolean }) {
  if (throws) throw new Error('captain is undefined')
  return <p>the page</p>
}

describe('ErrorBoundary', () => {
  it('states the message instead of unmounting the tree', () => {
    // React logs the caught error itself; the test asserts on the callout.
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ErrorBoundary><Boom throws /></ErrorBoundary>)
    const box = screen.getByText(/captain is undefined/)
      .closest('[data-tone]')!
    expect(box).toHaveAttribute('data-tone', 'error')
    expect(screen.getByRole('button', { name: 'Reload page' }))
      .toBeInTheDocument()
    quiet.mockRestore()
  })

  it('clears the error when the reset key changes, so navigation recovers',
     () => {
       const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
       const view = render(
         <ErrorBoundary resetKey="/"><Boom throws /></ErrorBoundary>,
       )
       expect(screen.getByText(/captain is undefined/)).toBeInTheDocument()
       view.rerender(
         <ErrorBoundary resetKey="/planning"><Boom throws={false} /></ErrorBoundary>,
       )
       expect(screen.getByText('the page')).toBeInTheDocument()
       quiet.mockRestore()
     })
})
