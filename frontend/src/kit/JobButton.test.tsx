import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JobButton from './JobButton'

const { stream } = vi.hoisted(() => ({
  stream: {
    status: 'idle' as string,
    lines: [] as string[],
    result: null as unknown,
    error: null as string | null,
    jobId: null as string | null,
    start: vi.fn(),
    attach: vi.fn(),
    reset: vi.fn(),
  },
}))

// `resetJobSlots` is stubbed alongside the hook because the shared setup
// clears the real hook's slots before every test and a mocked module has none.
vi.mock('../api/useJob', () => ({
  resetJobSlots: () => {},
  useJob: () => stream,
}))

beforeEach(() => {
  stream.status = 'idle'
  stream.lines = []
  stream.error = null
  stream.start.mockReset()
  stream.attach.mockReset()
})

describe('JobButton', () => {
  // The kind is the hook's argument now (v17h §6), so the button's own click
  // carries nothing: what it starts is fixed when the hook is called.
  it('starts the job its hook was given', async () => {
    render(<JobButton kind="advise" />)
    await userEvent.click(screen.getByRole('button', { name: 'Run advise' }))
    expect(stream.start).toHaveBeenCalledWith()
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
    stream.status = 'error'
    stream.error = 'no models on disk'
    rerender(<JobButton kind="advise" onDone={onDone} />)
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(onDone).not.toHaveBeenCalled()
  })

  it('tells its host when the run starts and when it stops', async () => {
    // The card that hosts the button owns the panel the job fills, and the
    // button owns the stream — so the button has to say (plan A10).
    const seen: boolean[] = []
    stream.status = 'running'
    const { rerender } = render(
      <JobButton kind="sensitivity" onRunning={(r) => seen.push(r)} />)
    await waitFor(() => expect(seen).toContain(true))
    stream.status = 'done'
    rerender(<JobButton kind="sensitivity" onRunning={(r) => seen.push(r)} />)
    await waitFor(() => expect(seen[seen.length - 1]).toBe(false))
  })
})
