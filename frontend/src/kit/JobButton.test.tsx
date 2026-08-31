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

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('../api/useJobStream', () => ({ useJobStream: () => stream }))
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  stream.status = 'idle'
  stream.lines = []
  stream.error = null
  stream.start.mockReset()
  stream.attach.mockReset()
  apiGet.mockReset()
  apiGet.mockResolvedValue(null)
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

  // A job outlives the tab that started it. A reload, or a second tab, must
  // find the run in progress rather than offering to start a second one that
  // the single-flight runner would only 409.
  describe('a job already running when the button mounts', () => {
    it('attaches to a run of its own kind', async () => {
      apiGet.mockResolvedValue({ id: 'j7', kind: 'advise', status: 'running' })
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(stream.attach).toHaveBeenCalledWith('j7'))
      expect(apiGet).toHaveBeenCalledWith('/api/jobs/current')
    })

    it('ignores a run of a different kind', async () => {
      apiGet.mockResolvedValue({ id: 'j7', kind: 'evaluate',
                                 status: 'running' })
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(apiGet).toHaveBeenCalled())
      expect(stream.attach).not.toHaveBeenCalled()
    })

    it('ignores a run that has already finished', async () => {
      apiGet.mockResolvedValue({ id: 'j7', kind: 'advise', status: 'done' })
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(apiGet).toHaveBeenCalled())
      expect(stream.attach).not.toHaveBeenCalled()
    })

    it('stays quiet when nothing is running', async () => {
      // 204 on an idle runner; the client hands that back as null.
      apiGet.mockResolvedValue(null)
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(apiGet).toHaveBeenCalled())
      expect(stream.attach).not.toHaveBeenCalled()
    })

    it('survives the probe failing', async () => {
      apiGet.mockRejectedValue(new Error('offline'))
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(apiGet).toHaveBeenCalled())
      expect(stream.attach).not.toHaveBeenCalled()
      // The button is still the button: a failed probe is not a failed job.
      expect(screen.getByRole('button', { name: 'Run advise' }))
        .not.toBeDisabled()
    })

    it('does not re-attach to a job it is already streaming', async () => {
      apiGet.mockResolvedValue({ id: 'j7', kind: 'advise', status: 'running' })
      stream.status = 'running'
      stream.jobId = 'j7'
      render(<JobButton kind="advise" />)
      await waitFor(() => expect(apiGet).toHaveBeenCalled())
      expect(stream.attach).not.toHaveBeenCalled()
      stream.jobId = null
    })
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
