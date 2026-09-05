import type { ReactNode } from 'react'

/** up/down: a direction (rule 1). warn: doubt (rule 2). neutral: a word
 *  that is information (rule 4). There is deliberately no accent tone —
 *  a chip is never something you click (rule 3). */
export type ChipTone = 'up' | 'down' | 'warn' | 'neutral'

const TONE: Record<ChipTone, string> = {
  up: 'bg-up-tint text-up',
  down: 'bg-down-tint text-down',
  warn: 'bg-warn-tint text-warn',
  neutral: 'border border-border text-text-muted',
}

export interface ChipProps {
  children: ReactNode
  tone?: ChipTone
  title?: string
  className?: string
}

export default function Chip(
  { children, tone = 'neutral', title, className = '' }: ChipProps,
) {
  return (
    <span
      title={title}
      data-tone={tone}
      className={'inline-flex items-center rounded-chip px-1.5 py-px '
        + `text-[10px] font-semibold leading-4 ${TONE[tone]} ${className}`}
    >
      {children}
    </span>
  )
}
