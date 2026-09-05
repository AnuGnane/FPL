import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: string
  /** Deadline, staleness, run stamp — whatever situates the page. */
  context?: ReactNode
  action?: ReactNode
}

/** Title 18px, context line muted, actions right (spec §5). */
export default function PageHeader({ title, context, action }: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-lg font-semibold leading-tight text-text">{title}</h1>
        {context !== undefined && context !== null && (
          <p data-testid="page-context" className="mt-1 text-text-muted">
            {context}
          </p>
        )}
      </div>
      {action}
    </header>
  )
}
