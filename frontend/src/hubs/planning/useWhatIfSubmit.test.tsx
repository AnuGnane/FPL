import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Job } from '../../api/useJob'
import type { WhatIfRequest } from '../../types'
import { useWhatIfSubmit } from './useWhatIfSubmit'

// v18f §2.1: the two lines the lab and the chips panel both wrote. Tested
// here on a stub job, because what the hook owns is the POST and the handoff
// — each tab's own wording for a refusal stays in that tab's own file.

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }))

vi.mock('../../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 422
    detail: unknown = null
  },
  apiGet: vi.fn(),
  apiPost: (path: string, body: unknown) => apiPost(path, body),
  errorText: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}))

const REQUEST: WhatIfRequest = {
  lock: [1], ban: [], force_in: [], force_out: [2], max_hits: 1,
  max_transfers: null, chip: 'wc', horizon: 3,
}

function stubJob(): Job {
  return {
    status: 'idle', lines: [], result: null, error: null, jobId: null,
    start: vi.fn(), attach: vi.fn(), reset: vi.fn(),
  }
}

function Probe({ job, onError }: { job: Job
                                   onError: (e: unknown) => void }) {
  const submit = useWhatIfSubmit(job, onError)
  return <button type="button" onClick={() => submit(REQUEST)}>Re-solve</button>
}

beforeEach(() => {
  apiPost.mockReset()
})

describe('useWhatIfSubmit', () => {
  it('posts the request the caller handed it to the what-if route',
    async () => {
      apiPost.mockResolvedValue({ job_id: 'job-1' })
      const job = stubJob()
      render(<Probe job={job} onError={vi.fn()} />)
      await userEvent.click(screen.getByRole('button'))
      await waitFor(() => { expect(apiPost).toHaveBeenCalled() })
      expect(apiPost.mock.calls[0]).toEqual(['/api/whatif', REQUEST])
    })

  it('resets the slot and hands the new job id to it', async () => {
    // The reset is what stops the previous solve's result from standing
    // under the one now running.
    apiPost.mockResolvedValue({ job_id: 'job-2' })
    const job = stubJob()
    render(<Probe job={job} onError={vi.fn()} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(job.attach).toHaveBeenCalledWith('job-2') })
    expect(job.reset).toHaveBeenCalled()
  })

  it('hands a refusal to the caller rather than wording it', async () => {
    // Each tab says something different about a 422 — the lab reads the
    // structured body into its own card, the chips panel prints one sentence
    // — so the hook only carries the exception across.
    const refusal = new Error('locked players cannot also be banned')
    apiPost.mockRejectedValue(refusal)
    const job = stubJob()
    const onError = vi.fn()
    render(<Probe job={job} onError={onError} />)
    await userEvent.click(screen.getByRole('button'))
    await waitFor(() => { expect(onError).toHaveBeenCalledWith(refusal) })
    expect(job.attach).not.toHaveBeenCalled()
  })
})
