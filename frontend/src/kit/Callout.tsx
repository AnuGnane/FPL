import { TriangleAlert } from 'lucide-react'
import type { HTMLAttributes, ReactNode } from 'react'

/** note: information (rule 4). warn: doubt — a data warning, a stale feed
 *  (rule 2), the amber strip with the icon spec §5 asks for. error: a job
 *  that failed or a save the server refused, in `down` ink — the one use of
 *  `down` that is not a direction (plan R4). */
export type CalloutTone = 'note' | 'warn' | 'error'

const TONE: Record<CalloutTone, string> = {
  note: 'border-border bg-raised text-text-secondary',
  warn: 'border-warn bg-warn-tint text-text',
  error: 'border-down bg-down-tint text-down',
}

export interface CalloutProps extends HTMLAttributes<HTMLDivElement> {
  tone?: CalloutTone
  children: ReactNode
}

export default function Callout(
  { tone = 'note', children, className = '', ...rest }: CalloutProps,
) {
  return (
    <div
      data-tone={tone}
      className={`flex gap-2 rounded-ctl border-l-2 px-3 py-2 ${TONE[tone]} `
        + className}
      {...rest}
    >
      {tone === 'warn' && (
        <TriangleAlert aria-hidden size={14}
                       className="mt-0.5 shrink-0 text-warn" />
      )}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}
