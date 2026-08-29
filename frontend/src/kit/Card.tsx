import type { ReactNode } from 'react'

export interface CardProps {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export default function Card({ title, action, children, className }: CardProps) {
  return (
    <section
      className={`rounded-card border border-border bg-card ${className ?? ''}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b
                           border-divider px-4 py-3">
          {title && <h2 className="label">{title}</h2>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
