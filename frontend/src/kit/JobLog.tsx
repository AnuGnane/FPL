import { useEffect, useRef } from 'react'
import type { JobStreamStatus } from '../api/useJobStream'

/** Lines kept on screen after a failure (spec §5). */
const FAILURE_TAIL = 20

export interface JobLogProps {
  status: JobStreamStatus
  lines: string[]
  error: string | null
}

export default function JobLog({ status, lines, error }: JobLogProps) {
  const box = useRef<HTMLPreElement | null>(null)

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight
  }, [lines.length])

  if (lines.length === 0 && !error) return null

  const shown = status === 'failed' ? lines.slice(-FAILURE_TAIL) : lines

  return (
    <div className="mt-3">
      {error && (
        <p role="alert" className="mb-2 rounded-card border border-rust-soft
                                   bg-card px-3 py-2 text-rust">
          {error}
        </p>
      )}
      {shown.length > 0 && (
        <pre
          ref={box}
          data-testid="job-log-lines"
          className="num max-h-56 overflow-auto rounded-card border
                     border-border bg-base p-3 text-xs text-text-secondary"
        >
          {shown.map((line, i) => <div key={`${i}-${line}`}>{line}</div>)}
        </pre>
      )}
    </div>
  )
}
