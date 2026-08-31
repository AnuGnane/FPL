import { useEffect, useRef } from 'react'
import { apiGet } from '../api/client'
import { useJobStream } from '../api/useJobStream'
import { JOB_KIND_LABEL, type JobKind } from '../types'
import JobLog from './JobLog'

export interface JobButtonProps {
  kind: JobKind
  label?: string
  /** Fired once, on success, so the page can re-fetch its artifacts. */
  onDone?: () => void
  /** Fired on every transition into and out of `running`, so the card that
   *  hosts the button can show a skeleton in the panel the job will fill.
   *  Optional: the button owns the stream, and lifting `useJobStream` into
   *  every caller to answer one question would be a refactor. */
  onRunning?: (running: boolean) => void
}

/** The shape of GET /api/jobs/current; 204 (nothing running) arrives as null. */
interface CurrentRun {
  id: string
  kind: JobKind
  status: string
}

export default function JobButton(
  { kind, label, onDone, onRunning }: JobButtonProps,
) {
  const job = useJobStream()
  const fired = useRef(false)
  const { attach, jobId } = job

  // A job outlives the tab that started it: an advise run is minutes long and
  // the runner holds it in memory, not in this component. Reload the page, or
  // open a second tab, and without this the button offers to start a run that
  // the single-flight runner can only answer with a 409. Ask once, on mount,
  // and if the run in flight is ours, watch it as though we had started it.
  useEffect(() => {
    let cancelled = false
    apiGet<CurrentRun | null>('/api/jobs/current')
      .then((run) => {
        if (cancelled || !run) return
        if (run.kind !== kind || run.status !== 'running') return
        if (run.id === jobId) return          // already streaming this one
        attach(run.id)
      })
      // A probe that cannot reach the server is not a failed job: leave the
      // button alone and let the click report the problem if it is still there.
      .catch(() => {})
    return () => { cancelled = true }
    // Mount only: re-attaching on every render would fight the stream we own.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  useEffect(() => {
    if (job.status === 'done' && !fired.current) {
      fired.current = true
      onDone?.()
    }
    if (job.status === 'running') fired.current = false
  }, [job.status, onDone])

  // A caller passing an inline arrow re-fires this on every render, which is
  // harmless: the callback is idempotent and sets a boolean.
  useEffect(() => {
    onRunning?.(job.status === 'running')
  }, [job.status, onRunning])

  const busy = job.status === 'running'
  return (
    <div>
      <button
        type="button"
        disabled={busy}
        onClick={() => job.start(kind)}
        className="rounded-card border border-border bg-card px-3 py-2
                   text-text-secondary hover:text-text disabled:opacity-50"
      >
        {busy ? `${label ?? JOB_KIND_LABEL[kind]} — running…`
              : label ?? JOB_KIND_LABEL[kind]}
      </button>
      <JobLog status={job.status} lines={job.lines} error={job.error} />
    </div>
  )
}
