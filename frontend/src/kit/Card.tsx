import type { ReactNode } from 'react'

/**
 * `titleSize` exists because a card is used for two different things: a
 * section of a page, whose title is chrome and belongs in the 9px uppercase
 * label voice, and a card *about* something — a player, in ComparePanel —
 * whose title is the content and has to read as such.
 *
 * The title is an `h3` regardless of `titleSize`: a card always sits under a
 * page heading, and several cards side by side (ComparePanel renders four)
 * would otherwise emit a row of sibling `h2`s that a screen reader reads as
 * four top-level sections of the page rather than four items within one.
 */
export interface CardProps {
  title?: string
  titleSize?: 'sm' | 'lg'
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-medium text-text',
} as const

export default function Card({
  title, titleSize = 'sm', action, children, className,
}: CardProps) {
  return (
    <section
      className={`rounded-card border border-border bg-card ${className ?? ''}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b
                           border-divider px-4 py-3">
          {title && <h3 className={TITLE_CLASS[titleSize]}>{title}</h3>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
