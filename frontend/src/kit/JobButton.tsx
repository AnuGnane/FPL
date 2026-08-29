import { useEffect, useRef } from 'react'
import { useJobStream } from '../api/useJobStream'
import { JOB_KIND_LABEL, type JobKind } from '../types'
import JobLog from './JobLog'

export interface JobButtonProps {
  kind: JobKind
  label?: string
  /** Fired once, on success, so the page can re-fetch its artifacts. */
  onDone?: () => void
}

export default function JobButton({ kind, label, onDone }: JobButtonProps) {
  const job = useJobStream()
  const fired = useRef(false)

  useEffect(() => {
    if (job.status === 'done' && !fired.current) {
      fired.current = true
      onDone?.()
    }
    if (job.status === 'running') fired.current = false
  }, [job.status, onDone])

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
