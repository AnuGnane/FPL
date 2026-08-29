import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import JobLog from './JobLog'

describe('JobLog', () => {
  it('renders nothing at all before a job has produced anything', () => {
    const { container } = render(
      <JobLog status="idle" lines={[]} error={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders every streamed line in the mono face', () => {
    render(<JobLog status="running" lines={['one', 'two']} error={null} />)
    expect(screen.getByText('one')).toBeInTheDocument()
    expect(screen.getByTestId('job-log-lines')).toHaveClass('num')
  })

  it('shows the failure message and the last twenty lines on failure', () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i}`)
    render(<JobLog status="failed" lines={lines} error="no models on disk" />)
    expect(screen.getByRole('alert')).toHaveTextContent('no models on disk')
    expect(screen.queryByText('line 19')).toBeNull()
    expect(screen.getByText('line 20')).toBeInTheDocument()
    expect(screen.getByText('line 39')).toBeInTheDocument()
  })

  it('keeps the whole scrollback while the job is still running', () => {
    const lines = Array.from({ length: 40 }, (_, i) => `line ${i}`)
    render(<JobLog status="running" lines={lines} error={null} />)
    expect(screen.getByText('line 0')).toBeInTheDocument()
  })
})
