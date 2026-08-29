import type { ReactNode } from 'react'

export type BadgeVariant = 'positive' | 'negative' | 'info' | 'neutral'

const VARIANT: Record<BadgeVariant, string> = {
  positive: 'text-sage border-sage/40',
  negative: 'text-rust border-rust/40',
  info: 'text-info border-info/40',
  neutral: 'text-text-muted border-border',
}

export interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  title?: string
}

export default function Badge(
  { children, variant = 'neutral', title }: BadgeProps,
) {
  return (
    <span
      title={title}
      className={`inline-flex items-center rounded border px-1.5 py-0.5
                  text-[11px] leading-none ${VARIANT[variant]}`}
    >
      {children}
    </span>
  )
}
