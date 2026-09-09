import { useCallback, useEffect, useRef, useState } from 'react'
import type { JobKind } from '../types'
import { apiGet, apiPost, errorText } from './client'

export type JobStatus = 'idle' | 'queued' | 'running' | 'done' | 'error'

export interface JobRecord {
  id: string
  status: 'queued' | 'running' | 'done' | 'error'
  result: unknown
  error: string | null
}

/** The terminal event of a streamed run. `failed` is the wire's word for what
 *  this hook calls `error` (v17h §6). */
export interface JobStreamEnd {
  status: 'done' | 'failed'
  error: string | null
  summary: string | null
}

/** The shape of GET /api/jobs/current; 204 (nothing running) arrives as null. */
interface CurrentRun {
  id: string
  kind: JobKind
  status: string
}

const POLL_MS = 1000

/**
 * Which job, and therefore which transport (v17h §6).
 *
 * `kind` is the v7 kind-keyed runner: it has a ring buffer and
 * `/api/jobs/{id}/stream`, so the hook streams and recovers through
 * `/api/jobs/current`. Anything else is an anonymous `JobRegistry`
 * submission, whose ids that stream route 404s on
 * (`src/gaffer/web/routers/jobs.py:137`), so the hook polls and recovers
 * through the id it remembered under `slot`. `path` is optional because the
 * what-if lab and the chips workbench post the job themselves — so a
 * structured 422 lands next to the input rather than becoming a job error —
 * and only ever call `attach`.
 */
export type JobSpec =
  | { kind: JobKind; path?: never; slot?: never }
  | {
      kind?: never
      path?: string
      /** Names the recovery bucket. Given one, the hook re-attaches on mount
       *  to a job started under the same slot that is still running (or has
       *  since finished). Omitted, the hook forgets its job on unmount. Two
       *  consumers may share a slot only if they read `result` as the same
       *  shape. */
      slot?: string
    }

export interface Job {
  status: JobStatus
  /** The captured log. Always empty for a polled job: the anonymous runner
   *  keeps no ring buffer to replay. */
  lines: string[]
  /** The job record's result. Always null for a streamed job: the kind-keyed
   *  runner reports through its log and its terminal `end` event. */
  result: unknown
  error: string | null
  jobId: string | null
  /** Starts the job this hook names. Rejects for a spec with neither a
   *  `kind` nor a `path`, which is a caller that should be using `attach`. */
  start: (body?: unknown) => Promise<void>
  attach: (jobId: string) => void
  reset: () => void
}

// A job outlives the tab that started it. Radix unmounts an unselected tab,
// so switching away from the What-If Lab mid-solve tore down the hook, and
// switching back mounted a fresh one that had never heard of the run still
// grinding away on the server — an idle form where a result was about to
// land. The kind probe below solves the same problem by asking the backend,
// once on mount, whether the run it cares about is still going.
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

export function useJob({ kind, path, slot }: JobSpec): Job {
  const [status, setStatus] = useState<JobStatus>('idle')
  const [lines, setLines] = useState<string[]>([])
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  const source = useRef<EventSource | null>(null)
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

  const close = useCallback(() => {
    source.current?.close()
    source.current = null
  }, [])

  // Both, because a spec picks one transport but the teardown cannot know
  // which one this hook ended up using (v17h §6).
  useEffect(() => () => { stop(); close() }, [stop, close])

  const poll = useCallback((id: string) => {
    stop()
    watching.current = id
    setJobId(id)
    if (slot) remembered.set(slot, id)
    timer.current = window.setInterval(async () => {
      if (watching.current !== id) return
      try {
        const job = await apiGet<JobRecord>(`/api/jobs/${id}`)
        if (watching.current !== id) return
        setStatus(job.status)
        if (job.status === 'done') {
          setResult(job.result)
          stop()
        } else if (job.status === 'error') {
          setError(job.error ?? 'the job failed')
          stop()
        }
      } catch (e) {
        if (watching.current !== id) return
        setStatus('error')
        setError(errorText(e))
        stop()
      }
    }, POLL_MS)
  }, [stop, slot])

  // EventSource rather than the v6 one-second poll: these jobs print progress
  // for minutes, and the whole point of the button is watching it happen. The
  // browser reconnects on its own and sends Last-Event-ID, which the server
  // answers out of the 500-line ring buffer (spec §5).
  const watch = useCallback((id: string) => {
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
      setStatus(end.status === 'failed' ? 'error' : 'done')
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
      setStatus('error')
      setError('stream lost — the server may have restarted')
      close()
    })
    source.current = stream
  }, [close])

  // A job outlives the tab that started it: an advise run is minutes long and
  // the runner holds it in memory, not in this component. Reload the page, or
  // open a second tab, and without this the button offers to start a run that
  // the single-flight runner can only answer with a 409. Ask once, on mount,
  // and if the run in flight is ours, watch it as though we had started it.
  useEffect(() => {
    if (kind === undefined) return
    let cancelled = false
    apiGet<CurrentRun | null>('/api/jobs/current')
      .then((run) => {
        if (cancelled || !run) return
        if (run.kind !== kind || run.status !== 'running') return
        watch(run.id)
      })
      // A probe that cannot reach the server is not a failed job: leave the
      // button alone and let the click report the problem if it is still there.
      .catch(() => {})
    return () => { cancelled = true }
    // Mount only: re-attaching on every render would fight the stream we own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  // The one-shot probe. A finished job is painted from the record the server
  // still holds rather than re-polled, so a tab reopened long after the solve
  // ended still shows what it produced. A 404 is a server that has been
  // restarted and forgotten the run: drop the id rather than probing for it
  // again on every future mount.
  useEffect(() => {
    if (!slot) return
    const id = remembered.get(slot)
    if (id === undefined) return
    let cancelled = false
    // Status is left alone until the probe answers, as the kind probe above
    // leaves its button alone: guessing 'running' would flash a spinner over a
    // result that has been sitting finished on the server for an hour.
    apiGet<JobRecord>(`/api/jobs/${id}`)
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
          poll(id)
        }
      })
      .catch(() => { remembered.delete(slot) })
    return () => { cancelled = true }
    // Mount only: re-probing on every render would fight the poll we own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot])

  const start = useCallback(async (body?: unknown) => {
    if (kind !== undefined) {
      setLines([])
      setError(null)
      try {
        // `undefined`, not `body`: POST /api/jobs/{kind} declares no body
        // param, so anything sent is discarded rather than refused, and a
        // caller who passed one would never learn it went nowhere (v17h §6).
        const { job_id } = await apiPost<{ job_id: string; kind: JobKind }>(
          `/api/jobs/${kind}`, undefined)
        watch(job_id)
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
      return
    }
    if (path === undefined) {
      // A spec with neither is a caller that posts the job itself and only
      // ever attaches, so there is nothing here to start (v17h §6).
      throw new Error('useJob: this job has no kind and no path to start')
    }
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
  }, [kind, path, watch, poll])

  const attach = useCallback((id: string) => {
    if (kind !== undefined) {
      watch(id)
      return
    }
    // For callers that post the job themselves (the what-if page, so a
    // structured 422 lands next to its input instead of becoming a job error)
    // and only need the polling half.
    setStatus('running')
    setResult(null)
    setError(null)
    poll(id)
  }, [kind, watch, poll])

  const reset = useCallback(() => {
    stop()
    close()
    // Deliberately forgotten too: reset is a caller saying "that run is no
    // longer mine", and a remount must not resurrect it.
    if (slot) remembered.delete(slot)
    setStatus('idle')
    setLines([])
    setResult(null)
    setError(null)
    setJobId(null)
  }, [stop, close, slot])

  return { status, lines, result, error, jobId, start, attach, reset }
}
