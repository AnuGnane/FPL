import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, apiGet, apiPost } from './client'

export type JobStatus = 'idle' | 'queued' | 'running' | 'done' | 'error'

export interface JobRecord {
  id: string
  status: 'queued' | 'running' | 'done' | 'error'
  result: unknown
  error: string | null
}

const POLL_MS = 1000

// Polling, not websockets: at localhost latency a one-second poll is
// indistinguishable from a push and costs one trivial GET (spec §2.1).
export function useJob() {
  const [status, setStatus] = useState<JobStatus>('idle')
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => stop, [stop])

  const poll = useCallback((jobId: string) => {
    stop()
    timer.current = window.setInterval(async () => {
      try {
        const job = await apiGet<JobRecord>(`/api/jobs/${jobId}`)
        setStatus(job.status)
        if (job.status === 'done') {
          setResult(job.result)
          stop()
        } else if (job.status === 'error') {
          setError(job.error ?? 'the job failed')
          stop()
        }
      } catch (e) {
        setStatus('error')
        setError(e instanceof Error ? e.message : String(e))
        stop()
      }
    }, POLL_MS)
  }, [stop])

  const start = useCallback(async (path: string, body?: unknown) => {
    setStatus('queued')
    setResult(null)
    setError(null)
    try {
      const { job_id } = await apiPost<{ job_id: string }>(path, body)
      poll(job_id)
    } catch (e) {
      setStatus('error')
      setError(e instanceof ApiError && typeof e.detail === 'string'
        ? e.detail
        : e instanceof Error ? e.message : String(e))
    }
  }, [poll])

  const reset = useCallback(() => {
    stop()
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [stop])

  return { status, result, error, start, reset }
}
