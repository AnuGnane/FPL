import { useEffect, useRef } from 'react'
import { useJob } from '../api/useJob'
import { JOB_KIND_LABEL, type JobKind } from '../types'
import Button, { type ButtonVariant } from './Button'
import JobLog from './JobLog'

export interface JobButtonProps {
  kind: JobKind
  label?: string
  /** Fired once, on success, so the page can re-fetch its artifacts. */
  onDone?: () => void
  /** Fired on every transition into and out of `running`, so the card that
   *  hosts the button can show a skeleton in the panel the job will fill.
   *  Optional: the button owns the stream, and lifting `useJob` into every
   *  caller to answer one question would be a refactor. */
  onRunning?: (running: boolean) => void
  /** `primary` for the action the page is for (Run advise); secondary
   *  otherwise. */
  variant?: ButtonVariant
}

export default function JobButton(
  { kind, label, onDone, onRunning, variant = 'secondary' }: JobButtonProps,
) {
  // A kind, so the hook streams and owns the mount probe that finds a run
  // already in flight (v17h §6).
  const job = useJob({ kind })
  const fired = useRef(false)

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
      <Button variant={variant} disabled={busy} onClick={() => job.start()}>
        {busy ? `${label ?? JOB_KIND_LABEL[kind]} — running…`
              : label ?? JOB_KIND_LABEL[kind]}
      </Button>
      <JobLog status={job.status} lines={job.lines} error={job.error} />
    </div>
  )
}
