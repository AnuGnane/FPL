import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JobButton from './JobButton'

const { stream } = vi.hoisted(() => ({
  stream: {
    status: 'idle' as string,
    lines: [] as string[],
    error: null as string | null,
    jobId: null as string | null,
    start: vi.fn(),
    attach: vi.fn(),
    reset: vi.fn(),
  },
}))

vi.mock('../api/useJobStream', () => ({ useJobStream: () => stream }))

beforeEach(() => {
  stream.status = 'idle'
  stream.lines = []
  stream.error = null
  stream.start.mockReset()
})

describe('JobButton', () => {
  it('starts the kind it was given', async () => {
    render(<JobButton kind="advise" />)
    await userEvent.click(screen.getByRole('button', { name: 'Run advise' }))
    expect(stream.start).toHaveBeenCalledWith('advise')
  })

  it('uses an explicit label over the default one', () => {
    render(<JobButton kind="evaluate" label="Score the model" />)
    expect(screen.getByRole('button', { name: 'Score the model' }))
      .toBeInTheDocument()
  })

  it('disables itself and says so while the job runs', () => {
    stream.status = 'running'
    render(<JobButton kind="advise" />)
    const button = screen.getByRole('button', { name: /running/i })
    expect(button).toBeDisabled()
  })

  it('renders the streamed log', () => {
    stream.status = 'running'
    stream.lines = ['step one']
    render(<JobButton kind="advise" />)
    expect(screen.getByText('step one')).toBeInTheDocument()
  })

  it('calls back once when the job finishes', async () => {
    const onDone = vi.fn()
    const { rerender } = render(<JobButton kind="advise" onDone={onDone} />)
    stream.status = 'done'
    rerender(<JobButton kind="advise" onDone={onDone} />)
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce())
  })

  it('does not call back when the job fails', async () => {
    const onDone = vi.fn()
    const { rerender } = render(<JobButton kind="advise" onDone={onDone} />)
    stream.status = 'failed'
    stream.error = 'no models on disk'
    rerender(<JobButton kind="advise" onDone={onDone} />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(onDone).not.toHaveBeenCalled()
  })
})
