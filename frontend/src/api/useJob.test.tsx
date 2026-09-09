import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

class FakeEventSource {
  static last: FakeEventSource | null = null
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  listeners: Record<string, Array<(e: Event) => void>> = {}
  closed = false
  readyState = 1

  constructor(public url: string) { FakeEventSource.last = this }

  addEventListener(name: string, fn: (e: Event) => void) {
    (this.listeners[name] ??= []).push(fn)
  }

  emit(name: string, data: string) {
    for (const fn of this.listeners[name] ?? []) {
      fn(new MessageEvent(name, { data }))
    }
  }

  /** What the browser does on a dropped connection it intends to retry. */
  fail(readyState: number) {
    this.readyState = readyState
    for (const fn of this.listeners.error ?? []) fn(new Event('error'))
  }

  close() { this.closed = true; this.readyState = 2 }
}

beforeEach(() => { FakeEventSource.last = null })

describe('useJob', () => {
  it('polls until the job is done and exposes the result', async () => {
    stubSequence([
      [202, { job_id: 'j1' }],
      [200, { id: 'j1', status: 'running', result: null, error: null }],
      [200, { id: 'j1', status: 'done', result: { delta_xpts: -2.8 },
              error: null }],
    ])
    const { result } = renderHook(() => useJob({ path: '/api/whatif' }))
    await result.current.start({ lock: [1] })
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
    const { result } = renderHook(() => useJob({ path: '/api/whatif' }))
    await result.current.start({})
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

    const { result } = renderHook(() => useJob({ path: '/api/whatif' }))
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
    const { result } = renderHook(() => useJob({ path: '/api/whatif' }))
    await result.current.start()
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

    const spec = { path: '/api/whatif', slot: 'whatif' }
    const first = renderHook(() => useJob(spec))
    await first.result.current.start({})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob(spec))
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
    const spec = { path: '/api/whatif', slot: 'finished-slot' }
    const first = renderHook(() => useJob(spec))
    await first.result.current.start({})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob(spec))
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
    const spec = { path: '/api/whatif', slot: 'gone-slot' }
    const first = renderHook(() => useJob(spec))
    await first.result.current.start({})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob(spec))
    await new Promise((r) => setTimeout(r, 200))
    expect(second.result.current.status).toBe('idle')
    second.unmount()
    // The id is dropped, so a third mount does not probe for it again.
    const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
      .length
    renderHook(() => useJob(spec))
    await new Promise((r) => setTimeout(r, 200))
    expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length)
      .toBe(calls)
  }, 15000)

  it('recovers nothing when no slot is named', async () => {
    stubSequence([
      [202, { job_id: 'j12' }],
      [200, { id: 'j12', status: 'running', result: null, error: null }],
    ])
    const first = renderHook(() => useJob({ path: '/api/whatif' }))
    await first.result.current.start({})
    await waitFor(() => expect(first.result.current.status).toBe('running'),
      { timeout: 4000 })
    first.unmount()

    const second = renderHook(() => useJob({ path: '/api/whatif' }))
    await new Promise((r) => setTimeout(r, 200))
    expect(second.result.current.status).toBe('idle')
    second.unmount()
  }, 15000)

  it('unwraps a structured refusal rather than reporting the status', async () => {
    stubSequence([[422, { detail: { constraint: 'unknown_draft',
                                    error: 'no draft called ghost',
                                    players: [] } }]])
    const { result } = renderHook(() => useJob({ path: '/api/drafts/compare' }))
    await result.current.start({ names: ['ghost'] })
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('no draft called ghost')
  })

  it('streams a kind job, and polls a path job, on the argument alone',
    async () => {
      stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      const streamed = renderHook(() => useJob({ kind: 'advise' }))
      await act(async () => { await streamed.result.current.start() })
      expect(FakeEventSource.last?.url).toBe('/api/jobs/j1/stream')

      FakeEventSource.last = null
      stubSequence([
        [202, { job_id: 'j2' }],
        [200, { id: 'j2', status: 'done', result: { ok: 1 }, error: null }],
      ])
      const polled = renderHook(() => useJob({ path: '/api/brief' }))
      await act(async () => { await polled.result.current.start() })
      await waitFor(() => expect(polled.result.current.status).toBe('done'),
        { timeout: 4000 })
      expect(FakeEventSource.last).toBeNull()
      expect(polled.result.current.result).toEqual({ ok: 1 })
    })

  it('calls a lost stream an error, in the one word both transports use',
    async () => {
      stubSequence([[202, { job_id: 'j3', kind: 'advise' }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      const { result } = renderHook(() => useJob({ kind: 'advise' }))
      await act(async () => { await result.current.start() })
      act(() => FakeEventSource.last!.fail(FakeEventSource.CLOSED))
      await waitFor(() => expect(result.current.status).toBe('error'))
      expect(result.current.error).toContain('stream lost')
    })

  it('re-attaches a kind job to the run already in flight, once on mount',
    async () => {
      stubSequence([[200, { id: 'j4', kind: 'advise', status: 'running' }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      renderHook(() => useJob({ kind: 'advise' }))
      await waitFor(() =>
        expect(FakeEventSource.last?.url).toBe('/api/jobs/j4/stream'))
      // Named, and counted: `/api/jobs/current` is the only route that answers
      // "what is the single-flight runner doing", and This Week's fetch rail
      // pins four of these against four buttons.
      const spy = globalThis.fetch as ReturnType<typeof vi.fn>
      expect(spy.mock.calls[0][0]).toBe('/api/jobs/current')
      expect(spy).toHaveBeenCalledOnce()
    })

  it('leaves a kind job alone when the run in flight is another kind',
    async () => {
      stubSequence([[200, { id: 'j5', kind: 'digest-friday',
                            status: 'running' }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      renderHook(() => useJob({ kind: 'advise' }))
      await new Promise((r) => setTimeout(r, 200))
      expect(FakeEventSource.last).toBeNull()
    })

  it('leaves a kind job alone when the run in flight has already finished',
    async () => {
      stubSequence([[200, { id: 'j6', kind: 'advise', status: 'done' }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      const { result } = renderHook(() => useJob({ kind: 'advise' }))
      await new Promise((r) => setTimeout(r, 200))
      expect(FakeEventSource.last).toBeNull()
      expect(result.current.status).toBe('idle')
    })

  // 204 on an idle runner; the client hands that back as null.
  it('stays idle when nothing is running', async () => {
    stubSequence([[200, null]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await new Promise((r) => setTimeout(r, 200))
    expect(FakeEventSource.last).toBeNull()
    expect(result.current.status).toBe('idle')
  })

  it('survives the mount probe failing', async () => {
    // A probe that cannot reach the server is not a failed job: the button it
    // sits behind must still offer the run.
    stubSequence([[503, { detail: 'offline' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await new Promise((r) => setTimeout(r, 200))
    expect(FakeEventSource.last).toBeNull()
    expect(result.current.status).toBe('idle')
    expect(result.current.error).toBeNull()
  })

  it('starts a job and opens the stream for the id it gets back', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    const posts = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
    expect(posts.map(([path]) => path)).toEqual(['/api/jobs/advise'])
    expect(FakeEventSource.last?.url).toBe('/api/jobs/j1/stream')
    expect(result.current.status).toBe('running')
  })

  it('collects streamed lines in order', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => {
      FakeEventSource.last!.emit('line', 'step one')
      FakeEventSource.last!.emit('line', 'step two')
    })
    await waitFor(() => expect(result.current.lines)
      .toEqual(['step one', 'step two']))
  })

  it('ends done and closes the stream', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => {
      FakeEventSource.last!.emit('end',
        JSON.stringify({ status: 'done', error: null, summary: "{'gw': 5}" }))
    })
    await waitFor(() => expect(result.current.status).toBe('done'))
    expect(FakeEventSource.last!.closed).toBe(true)
  })

  it('ends in error and keeps the reason the stream gave', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'evaluate' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'evaluate' }))
    await act(async () => { await result.current.start() })
    act(() => {
      FakeEventSource.last!.emit('end', JSON.stringify(
        { status: 'failed', error: 'no models on disk', summary: null }))
    })
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('no models on disk')
  })

  it('surfaces a 409 as the conflicting kind rather than a raw error',
    async () => {
      stubSequence([[409, { detail: { running_kind: 'advise',
                                      job_id: 'j0' } }]])
      vi.stubGlobal('EventSource', FakeEventSource)
      const { result } = renderHook(() => useJob({ kind: 'evaluate' }))
      await act(async () => { await result.current.start() })
      await waitFor(() => expect(result.current.error)
        .toBe('advise is already running'))
      expect(result.current.status).toBe('idle')
    })

  it('attaches to a job that is already running', async () => {
    stubSequence([[200, null]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    act(() => { result.current.attach('j9') })
    expect(FakeEventSource.last?.url).toBe('/api/jobs/j9/stream')
    await waitFor(() => expect(result.current.status).toBe('running'))
  })

  // A restarted server forgets its in-memory runs, so the stream 404s and the
  // EventSource closes for good. Without an onerror the hook sat in 'running'
  // for ever and the button never came back.
  it('fails the run when the stream closes for good', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => { FakeEventSource.last!.fail(FakeEventSource.CLOSED) })
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toMatch(/server may have restarted/i)
    expect(FakeEventSource.last!.closed).toBe(true)
  })

  it('leaves a transient drop to the browser to retry', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => { FakeEventSource.last!.fail(FakeEventSource.CONNECTING) })
    // Still running, still open: EventSource reconnects with Last-Event-ID and
    // the server replays out of its ring buffer.
    expect(result.current.status).toBe('running')
    expect(result.current.error).toBeNull()
    expect(FakeEventSource.last!.closed).toBe(false)
  })

  it('keeps the lines it had when the stream is lost', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => { FakeEventSource.last!.emit('line', 'step one') })
    act(() => { FakeEventSource.last!.fail(FakeEventSource.CLOSED) })
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.lines).toEqual(['step one'])
  })

  it('closes the stream when the tab that started it unmounts', async () => {
    // The teardown runs both halves because a spec picks one transport and the
    // cleanup cannot tell which. Without the stream half a tab switched away
    // mid-run left an EventSource open on a log nobody was reading.
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result, unmount } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    expect(FakeEventSource.last!.closed).toBe(false)
    unmount()
    expect(FakeEventSource.last!.closed).toBe(true)
  })

  it('does not fail a run that already ended', async () => {
    stubSequence([[202, { job_id: 'j1', kind: 'advise' }]])
    vi.stubGlobal('EventSource', FakeEventSource)
    const { result } = renderHook(() => useJob({ kind: 'advise' }))
    await act(async () => { await result.current.start() })
    act(() => {
      FakeEventSource.last!.emit('end',
        JSON.stringify({ status: 'done', error: null, summary: null }))
    })
    await waitFor(() => expect(result.current.status).toBe('done'))
    // Closing the source can itself fire an error; a finished job stays done.
    act(() => { FakeEventSource.last!.fail(FakeEventSource.CLOSED) })
    expect(result.current.status).toBe('done')
    expect(result.current.error).toBeNull()
  })
})
