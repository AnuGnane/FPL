import type { ReactNode } from 'react'

export interface PageHeaderProps {
  title: string
  /** Deadline, staleness, run stamp — whatever situates the page. */
  context?: ReactNode
  action?: ReactNode
}

export default function PageHeader({ title, context, action }: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-text">{title}</h1>
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
