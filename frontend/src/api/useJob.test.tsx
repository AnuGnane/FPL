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
})
