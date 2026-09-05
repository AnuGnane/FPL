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
 * is the content and has to read as such. The title is an `h3` regardless:
 * several sections side by side would otherwise emit a row of sibling `h2`s.
 */
export interface CardProps {
  title?: string
  /** Rich heading content; `title` stays the string form of the same thing. */
  heading?: ReactNode
  titleSize?: 'sm' | 'lg'
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-semibold text-text',
} as const

export default function Card({
  title, heading, titleSize = 'sm', action, children, className,
}: CardProps) {
  const shown = heading ?? title
  return (
    <section data-kit="section" className={`min-w-0 ${className ?? ''}`}>
      {(shown || action) && (
        <header className="mb-3 flex min-h-8 items-center justify-between
                           gap-3 border-b border-border pb-1.5">
          {shown && <h3 className={TITLE_CLASS[titleSize]}>{shown}</h3>}
          {action}
        </header>
      )}
      <div>{children}</div>
    </section>
  )
}
