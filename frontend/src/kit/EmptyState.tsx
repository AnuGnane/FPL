import { CircleDashed } from 'lucide-react'
import Button from './Button'

export interface EmptyStateProps {
  title: string
  detail: string
  /** The exact button label or shell command that populates this view. */
  action: string
  /** Present when the action is something the UI itself can do. */
  onAction?: () => void
}

export default function EmptyState(
  { title, detail, action, onAction }: EmptyStateProps,
) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center gap-2 border-y border-border
                 px-6 py-10 text-center"
    >
      <CircleDashed aria-hidden size={20} className="text-text-faint" />
      <p className="text-[15px] font-medium text-text">{title}</p>
      <p className="max-w-md text-text-muted">{detail}</p>
      {onAction
        ? <Button className="mt-2" onClick={onAction}>{action}</Button>
        : (
          <code className="tn mt-2 rounded-ctl border border-border bg-input
                           px-2 py-1 text-text-secondary">
            {action}
          </code>
          )}
    </div>
  )
}
