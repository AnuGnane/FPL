import type { ReactNode } from 'react'

/**
 * A section of the page (spec §5): a label band with a hairline under it and
 * an optional right-aligned action; the content sits on the page surface.
 * No border box, no fill, no radius — the ledger separates sections with
 * rules, not cards.
 *
 * Still named `Card` (and also exported as `Section`) because 35 files
 * compose it under that name and the spec allows the alias for one cycle.
 *
 * `titleSize` exists because a section is used for two different things: a
 * region of a page, whose title is chrome and belongs in the label voice,
 * and a panel *about* something — a player, in ComparePanel — whose title
 * is the content and has to read as such.
 *
 * `level` is the heading rank, and it is 2 by default since v19c §2.5: a
 * section of a page sits directly under `PageHeader`'s `h1`, and starting at
 * `h3` left a hole in the ladder that a screen reader reads as a missing
 * section. A section nested in another section's body says `level={3}`. The
 * class is the same either way, so the pixels do not move.
 */
export interface CardProps {
  title?: string
  /** v19d §2.1: the anchor the context strip jumps to. On the `<section>`
   *  itself, so the heading the reader lands on is the one that names it. */
  id?: string
  /** Rich heading content; `title` stays the string form of the same thing. */
  heading?: ReactNode
  titleSize?: 'sm' | 'lg'
  level?: 2 | 3
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-semibold text-text',
} as const

export default function Card({
  title, id, heading, titleSize = 'sm', level = 2, action, children,
  className,
}: CardProps) {
  const shown = heading ?? title
  const Heading = level === 2 ? 'h2' : 'h3'
  return (
    <section id={id} data-kit="section"
             className={`min-w-0 ${className ?? ''}`}>
      {(shown || action) && (
        <header className="mb-3 flex min-h-8 items-center justify-between
                           gap-3 border-b border-border pb-1.5">
          {shown && (
            <Heading className={TITLE_CLASS[titleSize]}>{shown}</Heading>
          )}
          {action}
        </header>
      )}
      <div>{children}</div>
    </section>
  )
}
