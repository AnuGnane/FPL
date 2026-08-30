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
  /**
   * Rich heading content. When given it is what the `h3` renders, so a card
   * *about* something can carry that thing's own control — ComparePanel's
   * click-to-explain player name — rather than a copy of its name as text.
   * `title` stays the string form of the same thing and may be passed with
   * it; `heading` wins visually, and the `h3` (and its `titleSize` class) is
   * the same element either way.
   */
  heading?: ReactNode
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
  title, heading, titleSize = 'sm', action, children, className,
}: CardProps) {
  const shown = heading ?? title
  return (
    <section
      className={`rounded-card border border-border bg-card ${className ?? ''}`}
    >
      {(shown || action) && (
        <header className="flex items-center justify-between gap-3 border-b
                           border-divider px-4 py-3">
          {shown && <h3 className={TITLE_CLASS[titleSize]}>{shown}</h3>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
