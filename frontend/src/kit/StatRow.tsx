import type { ReactNode } from 'react'

export interface StatRowProps {
  children: ReactNode
  /** Tiles per row at `md` and up; two below it. */
  cols?: 3 | 4
  className?: string
}

/** The hairline grid the stat tiles sit in (mockup A): a 1px `border` gap
 *  between tiles that stays a hairline however the tiles wrap, and no card
 *  box around any of them. */
export default function StatRow(
  { children, cols = 4, className = 'mb-4' }: StatRowProps,
) {
  return (
    <div
      data-testid="stat-row"
      className={'grid grid-cols-2 gap-px border border-border bg-border '
        + `${cols === 4 ? 'md:grid-cols-4' : 'md:grid-cols-3'} `
        + `[&>*]:bg-base ${className}`}
    >
      {children}
    </div>
  )
}
