import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useJob } from './useJob'

afterEach(() => vi.unstubAllGlobals())

function stubSequence(responses: Array<[number, unknown]>) {
  let call = 0
  vi.stubGlobal('fetch', vi.fn(async () => {
    const [status, body] = responses[Math.min(call++, responses.length - 1)]
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    })
  }))
}

describe('useJob', () => {
  it('polls until the job is done and exposes the result', async () => {
    stubSequence([
      [202, { job_id: 'j1' }],
      [200, { id: 'j1', status: 'running', result: null, error: null }],
      [200, { id: 'j1', status: 'done', result: { delta_xpts: -2.8 },
              error: null }],
    ])
    const { result } = renderHook(() => useJob())
    await result.current.start('/api/whatif', { lock: [1] })
    await waitFor(() => expect(result.current.status).toBe('done'),
      { timeout: 4000 })
    expect(result.current.result).toEqual({ delta_xpts: -2.8 })
  })

  it('surfaces a job error', async () => {
    stubSequence([
      [202, { job_id: 'j2' }],
      [200, { id: 'j2', status: 'error', result: null,
              error: 'no legal squad satisfies those constraints' }],
    ])
    const { result } = renderHook(() => useJob())
    await result.current.start('/api/whatif', {})
    await waitFor(() => expect(result.current.status).toBe('error'),
      { timeout: 4000 })
    expect(result.current.error).toContain('no legal squad')
  })

  it('ignores a response for a job it has already moved on from', async () => {
    let releaseA = () => {}
    const held = new Promise<void>((resolve) => { releaseA = resolve })
    const json = (body: unknown) => new Response(JSON.stringify(body), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.includes('jobA')) {
        await held
        return json({ id: 'jobA', status: 'done',
                      result: { from: 'A' }, error: null })
      }
      return json({ id: 'jobB', status: 'running', result: null, error: null })
    }))

    const { result } = renderHook(() => useJob())
    act(() => result.current.attach('jobA'))
    // Let A's first poll go out, then move the hook onto B while it hangs.
    await new Promise((r) => setTimeout(r, 1200))
    act(() => result.current.attach('jobB'))
    releaseA()

    await new Promise((r) => setTimeout(r, 1500))
    expect(result.current.result).toBeNull()
    expect(result.current.status).toBe('running')
  }, 10000)

  it('surfaces a rejected submission without starting a poll', async () => {
    stubSequence([[429, { detail: '5 jobs already queued' }]])
    const { result } = renderHook(() => useJob())
    await result.current.start('/api/whatif')
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toContain('already queued')
  })

  it('re-attaches to a running job when the tab remounts', async () => {
    // Radix unmounts an unselected tab mid-solve; the run carries on server
    // side, and mounting again has to find it rather than show an idle form.
    let done = false
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const body = url.includes('/api/whatif')
        ? { job_id: 'j9' }
        : { id: 'j9', status: done ? 'done' : 'running',
            result: done ? { delta_xpts: 1.4 } : null, error: null }
      return new Response(JSON.stringify(body), {
        status: url.includes('/api/whatif') ? 202 : 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    const first = renderHook(() => useJob('whatif'))
    await first.result.current.start('/api/whatif', {})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob('whatif'))
    await waitFor(() => expect(second.result.current.status).toBe('running'))
    done = true
    await waitFor(() => expect(second.result.current.status).toBe('done'),
      { timeout: 4000 })
    expect(second.result.current.result).toEqual({ delta_xpts: 1.4 })
    act(() => second.result.current.reset())
  }, 15000)

  it('paints a job that finished while the tab was unmounted', async () => {
    stubSequence([
      [202, { job_id: 'j10' }],
      [200, { id: 'j10', status: 'running', result: null, error: null }],
      [200, { id: 'j10', status: 'done', result: { delta_xpts: -0.5 },
              error: null }],
    ])
    const first = renderHook(() => useJob('finished-slot'))
    await first.result.current.start('/api/whatif', {})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob('finished-slot'))
    await waitFor(() => expect(second.result.current.status).toBe('done'))
    expect(second.result.current.result).toEqual({ delta_xpts: -0.5 })
    act(() => second.result.current.reset())
  }, 15000)

  it('forgets a job the restarted server no longer knows about', async () => {
    stubSequence([
      [202, { job_id: 'j11' }],
      [200, { id: 'j11', status: 'running', result: null, error: null }],
      [404, { detail: 'no such job: j11' }],
    ])
    const first = renderHook(() => useJob('gone-slot'))
    await first.result.current.start('/api/whatif', {})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob('gone-slot'))
    await new Promise((r) => setTimeout(r, 200))
    expect(second.result.current.status).toBe('idle')
    second.unmount()
    // The id is dropped, so a third mount does not probe for it again.
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
      .length
    renderHook(() => useJob('gone-slot'))
    await new Promise((r) => setTimeout(r, 200))
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length)
      .toBe(calls)
  }, 15000)

  it('recovers nothing when no slot is named', async () => {
    stubSequence([
      [202, { job_id: 'j12' }],
      [200, { id: 'j12', status: 'running', result: null, error: null }],
    ])
    const first = renderHook(() => useJob())
    await first.result.current.start('/api/whatif', {})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob())
    await new Promise((r) => setTimeout(r, 200))
    expect(second.result.current.status).toBe('idle')
    second.unmount()
  }, 15000)

  it('unwraps a structured refusal rather than reporting the status', async () => {
    stubSequence([[422, { detail: { constraint: 'unknown_draft',
                                    error: 'no draft called ghost',
                                    players: [] } }]])
    const { result } = renderHook(() => useJob())
    await result.current.start('/api/drafts/compare', { names: ['ghost'] })
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('no draft called ghost')
  })
})
