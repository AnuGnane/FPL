import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useJobStream } from './useJobStream'

const { apiPost } = vi.hoisted(() => ({ apiPost: vi.fn() }))

vi.mock('./client', () => ({
  ApiError: class FakeApiError extends Error {
    status = 0
    detail: unknown = null
  },
  apiGet: vi.fn(),
  apiPost: (path: string, body?: unknown) => apiPost(path, body),
}))

class FakeEventSource {
  static last: FakeEventSource | null = null
  listeners: Record<string, Array<(e: MessageEvent) => void>> = {}
  closed = false

  constructor(public url: string) { FakeEventSource.last = this }

  addEventListener(name: string, fn: (e: MessageEvent) => void) {
    (this.listeners[name] ??= []).push(fn)
  }

  emit(name: string, data: string) {
    for (const fn of this.listeners[name] ?? []) {
      fn(new MessageEvent(name, { data }))
    }
  }

  close() { this.closed = true }
}

beforeEach(() => {
  apiPost.mockReset()
  FakeEventSource.last = null
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => { vi.unstubAllGlobals() })

describe('useJobStream', () => {
  it('starts a job and opens the stream for the id it gets back', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1', kind: 'advise' })
    const { result } = renderHook(() => useJobStream())
    await act(async () => { await result.current.start('advise') })
    expect(apiPost).toHaveBeenCalledWith('/api/jobs/advise', undefined)
    expect(FakeEventSource.last?.url).toBe('/api/jobs/j1/stream')
    expect(result.current.status).toBe('running')
  })

  it('collects streamed lines in order', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1', kind: 'advise' })
    const { result } = renderHook(() => useJobStream())
    await act(async () => { await result.current.start('advise') })
    act(() => {
      FakeEventSource.last!.emit('line', 'step one')
      FakeEventSource.last!.emit('line', 'step two')
    })
    await waitFor(() => expect(result.current.lines)
      .toEqual(['step one', 'step two']))
  })

  it('ends done and closes the stream', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1', kind: 'advise' })
    const { result } = renderHook(() => useJobStream())
    await act(async () => { await result.current.start('advise') })
    act(() => {
      FakeEventSource.last!.emit('end',
        JSON.stringify({ status: 'done', error: null, summary: "{'gw': 5}" }))
    })
    await waitFor(() => expect(result.current.status).toBe('done'))
    expect(FakeEventSource.last!.closed).toBe(true)
  })

  it('ends failed and keeps the error', async () => {
    apiPost.mockResolvedValue({ job_id: 'j1', kind: 'evaluate' })
    const { result } = renderHook(() => useJobStream())
    await act(async () => { await result.current.start('evaluate') })
    act(() => {
      FakeEventSource.last!.emit('end', JSON.stringify(
        { status: 'failed', error: 'no models on disk', summary: null }))
    })
    await waitFor(() => expect(result.current.status).toBe('failed'))
    expect(result.current.error).toBe('no models on disk')
  })

  it('surfaces a 409 as the conflicting kind rather than a raw error',
    async () => {
      const conflict = Object.assign(new Error('conflict'), {
        status: 409, detail: { running_kind: 'advise', job_id: 'j0' },
      })
      apiPost.mockRejectedValue(conflict)
      const { result } = renderHook(() => useJobStream())
      await act(async () => { await result.current.start('evaluate') })
      await waitFor(() => expect(result.current.error)
        .toBe('advise is already running'))
      expect(result.current.status).toBe('idle')
    })

  it('attaches to a job that is already running', async () => {
    const { result } = renderHook(() => useJobStream())
    act(() => { result.current.attach('j9') })
    expect(FakeEventSource.last?.url).toBe('/api/jobs/j9/stream')
    await waitFor(() => expect(result.current.status).toBe('running'))
  })
})
