import { useCallback, useEffect, useRef, useState } from 'react'
import type { JobKind } from '../types'
import { apiPost } from './client'

export type JobStreamStatus = 'idle' | 'running' | 'done' | 'failed'

export interface JobStreamEnd {
  status: 'done' | 'failed'
  error: string | null
  summary: string | null
}

// EventSource rather than the v6 one-second poll: these jobs print progress
// for minutes, and the whole point of the button is watching it happen. The
// browser reconnects on its own and sends Last-Event-ID, which the server
// answers out of the 500-line ring buffer (spec §5).
export function useJobStream() {
  const [status, setStatus] = useState<JobStreamStatus>('idle')
  const [lines, setLines] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const source = useRef<EventSource | null>(null)

  const close = useCallback(() => {
    source.current?.close()
    source.current = null
  }, [])

  useEffect(() => close, [close])

  const attach = useCallback((id: string) => {
    close()
    setJobId(id)
    setStatus('running')
    setError(null)
    const stream = new EventSource(`/api/jobs/${id}/stream`)
    stream.addEventListener('line', (event) => {
      setLines((prev) => [...prev, (event as MessageEvent).data as string])
    })
    stream.addEventListener('end', (event) => {
      const end = JSON.parse((event as MessageEvent).data) as JobStreamEnd
      setStatus(end.status)
      setError(end.error)
      close()
    })
    // EventSource reports transient drops and permanent failures through the
    // same event; only readyState tells them apart. CONNECTING means the
    // browser is retrying by itself — it re-sends Last-Event-ID and the server
    // replays out of its ring buffer, so there is nothing to do and nothing to
    // say. CLOSED means it has given up: a restarted server has forgotten its
    // in-memory runs and the stream 404s for good. Without this the hook sat
    // in 'running' for ever and the button never came back.
    stream.addEventListener('error', () => {
      if (source.current !== stream) return   // already ended; close() fires this
      if (stream.readyState !== EventSource.CLOSED) return
      setStatus('failed')
      setError('stream lost — the server may have restarted')
      close()
    })
    source.current = stream
  }, [close])

  const start = useCallback(async (kind: JobKind) => {
    setLines([])
    setError(null)
    try {
      const { job_id } = await apiPost<{ job_id: string; kind: JobKind }>(
        `/api/jobs/${kind}`, undefined)
      attach(job_id)
    } catch (e) {
      const detail = (e as { status?: number; detail?: unknown })
      if (detail.status === 409 && detail.detail
          && typeof detail.detail === 'object') {
        const running = (detail.detail as { running_kind?: string }).running_kind
        setError(`${running} is already running`)
      } else {
        setError(e instanceof Error ? e.message : String(e))
      }
      setStatus('idle')
    }
  }, [attach])

  const reset = useCallback(() => {
    close()
    setStatus('idle')
    setLines([])
    setError(null)
    setJobId(null)
  }, [close])

  return { status, lines, error, jobId, start, attach, reset }
}
