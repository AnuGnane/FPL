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

// A job outlives the tab that started it. Radix unmounts an unselected tab,
// so switching away from the What-If Lab mid-solve tore down the hook, and
// switching back mounted a fresh one that had never heard of the run still
// grinding away on the server — an idle form where a result was about to
// land. JobButton solved the same problem by asking the backend, once on
// mount, whether the run it cares about is still going (kit/JobButton.tsx).
//
// It asks `/api/jobs/current`, which only knows the v7 kind-keyed runner.
// These jobs are anonymous JobRegistry submissions with no kind to ask about,
// so the id is remembered here instead and the same one-shot probe is made
// against `/api/jobs/{id}` — the endpoint the poll below already uses, which
// serves both runners.
//
// Keyed by slot, and only for callers that name one: two consumers sharing a
// bucket would recover each other's jobs, and the Drafts tab's DraftCompare
// arriving in the What-If Lab — which reads `result` as a WhatIfResult — is a
// worse bug than the one this fixes.
const remembered = new Map<string, string>()

/**
 * Forget every remembered job. For tests only.
 *
 * The map is module state, so it outlives a component, a test case and a test
 * file alike — which is the whole point in a browser and a leak in a runner.
 * Without this a finished compare from one test was re-probed and re-painted
 * by the next test's first mount, and the tab rendered two results. The
 * shared vitest setup calls it before each test.
 */
export function resetJobSlots(): void {
  remembered.clear()
}

/**
 * @param slot Names the recovery bucket. Given one, the hook re-attaches on
 *   mount to a job started under the same slot that is still running (or has
 *   since finished). Omitted, the hook forgets its job on unmount as before.
 *   Two consumers may share a slot only if they read `result` as the same
 *   shape.
 */
export function useJob(slot?: string) {
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
    if (slot) remembered.set(slot, jobId)
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
  }, [stop, slot])

  // The one-shot probe. A finished job is painted from the record the server
  // still holds rather than re-polled, so a tab reopened long after the solve
  // ended still shows what it produced. A 404 is a server that has been
  // restarted and forgotten the run: drop the id rather than probing for it
  // again on every future mount.
  useEffect(() => {
    if (!slot) return
    const jobId = remembered.get(slot)
    if (jobId === undefined) return
    let cancelled = false
    // Status is left alone until the probe answers, as JobButton leaves its
    // button alone: guessing 'running' would flash a spinner over a result
    // that has been sitting finished on the server for an hour.
    apiGet<JobRecord>(`/api/jobs/${jobId}`)
      .then((job) => {
        if (cancelled) return
        if (job.status === 'done') {
          setStatus('done')
          setResult(job.result)
        } else if (job.status === 'error') {
          setStatus('error')
          setError(job.error ?? 'the job failed')
        } else {
          setStatus(job.status)
          poll(jobId)
        }
      })
      .catch(() => { remembered.delete(slot) })
    return () => { cancelled = true }
    // Mount only: re-probing on every render would fight the poll we own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot])

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
    // Deliberately forgotten too: reset is a caller saying "that run is no
    // longer mine", and a remount must not resurrect it.
    if (slot) remembered.delete(slot)
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [stop, slot])

  return { status, result, error, start, attach, reset }
}
