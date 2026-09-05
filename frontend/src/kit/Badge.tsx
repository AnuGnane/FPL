import type { ReactNode } from 'react'
import Chip, { type ChipTone } from './Chip'

/** v14: `Badge` is a one-cycle alias of `Chip` (spec §5). The old variant
 *  names map onto tones; new code writes `<Chip tone=…>`. `info` was the
 *  blue "this is a note" badge, and blue no longer carries data (rule 3),
 *  so it lands on neutral. Availability doubt should be `warn`, which this
 *  vocabulary cannot say — one more reason the sweep migrates call sites. */
export type BadgeVariant = 'positive' | 'negative' | 'info' | 'neutral'

export const BADGE_TONE: Record<BadgeVariant, ChipTone> = {
  positive: 'up', negative: 'down', info: 'neutral', neutral: 'neutral',
}

export interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  title?: string
}

export default function Badge(
  { children, variant = 'neutral', title }: BadgeProps,
) {
  return <Chip tone={BADGE_TONE[variant]} title={title}>{children}</Chip>
}
