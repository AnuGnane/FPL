import { useCallback, useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, errorText } from './client'

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
  // The job this hook is currently watching. A GET for a previous job (or for
  // any job after an unmount) can still be in flight, and must not paint.
  const watching = useRef<string | null>(null)

  const stop = useCallback(() => {
    watching.current = null
    if (timer.current !== null) {
      window.clearInterval(timer.current)
      timer.current = null
    }
  }, [])

  useEffect(() => stop, [stop])

  const poll = useCallback((jobId: string) => {
    stop()
    watching.current = jobId
    timer.current = window.setInterval(async () => {
      if (watching.current !== jobId) return
      try {
        const job = await apiGet<JobRecord>(`/api/jobs/${jobId}`)
        if (watching.current !== jobId) return
        setStatus(job.status)
        if (job.status === 'done') {
          setResult(job.result)
          stop()
        } else if (job.status === 'error') {
          setError(job.error ?? 'the job failed')
          stop()
        }
      } catch (e) {
        if (watching.current !== jobId) return
        setStatus('error')
        setError(errorText(e))
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
      setError(errorText(e))
    }
  }, [poll])

  // For callers that post the job themselves (the what-if page, so a
  // structured 422 lands next to its input instead of becoming a job error)
  // and only need the polling half.
  const attach = useCallback((jobId: string) => {
    setStatus('running')
    setResult(null)
    setError(null)
    poll(jobId)
  }, [poll])

  const reset = useCallback(() => {
    stop()
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [stop])

  return { status, result, error, start, attach, reset }
}
