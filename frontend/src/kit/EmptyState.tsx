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
    <div className="flex flex-col items-center gap-2 rounded-card border
                    border-border bg-card px-6 py-10 text-center">
      <span aria-hidden className="text-2xl text-text-faint">◍</span>
      <p className="text-base text-text">{title}</p>
      <p className="max-w-md text-text-muted">{detail}</p>
      {onAction
        ? (
          <button
            type="button"
            onClick={onAction}
            className="mt-2 rounded-card border border-border bg-base px-3 py-2
                       text-text-secondary hover:text-text"
          >
            {action}
          </button>
          )
        : (
          <code className="mt-2 rounded-card border border-border bg-base px-2
                           py-1 font-mono text-text-secondary">
            {action}
          </code>
          )}
    </div>
  )
}
