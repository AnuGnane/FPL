import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('names the action that populates the view', () => {
    render(
      <EmptyState
        title="No advice yet"
        detail="Nothing has been solved for this gameweek."
        action="Run advise"
      />,
    )
    expect(screen.getByText('No advice yet')).toBeInTheDocument()
    expect(screen.getByText(/Nothing has been solved/)).toBeInTheDocument()
    expect(screen.getByText('Run advise')).toBeInTheDocument()
  })

  it('renders the action as a button when given a handler', async () => {
    const onAction = vi.fn()
    render(
      <EmptyState title="No advice yet" detail="Nothing solved."
                  action="Run advise" onAction={onAction} />,
    )
    await userEvent.click(screen.getByRole('button', { name: 'Run advise' }))
    expect(onAction).toHaveBeenCalledOnce()
  })

  it('renders the action as a command when there is no handler', () => {
    render(<EmptyState title="No evaluation" detail="Never scored."
                       action="gaffer evaluate" />)
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('gaffer evaluate').tagName).toBe('CODE')
  })
})
