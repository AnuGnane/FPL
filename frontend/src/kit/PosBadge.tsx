/**
 * A player's position, as identity rather than judgement.
 *
 * The hues live beside sage/rust/blue in the theme but never overlap them:
 * a MID is violet everywhere he appears, and that says nothing about whether
 * he is a good pick. Exported as CSS variables rather than Tailwind classes
 * so one map serves text, borders and backgrounds alike.
 */
export const POS_COLOR: Record<string, string> = {
  GKP: 'var(--color-pos-gkp)',
  DEF: 'var(--color-pos-def)',
  MID: 'var(--color-pos-mid)',
  FWD: 'var(--color-pos-fwd)',
}

/** The colour this position is drawn in, or null when it is not one of ours. */
export function posColor(pos: string | null | undefined): string | null {
  return POS_COLOR[(pos ?? '').trim().toUpperCase()] ?? null
}

export interface PosBadgeProps {
  pos: string | null | undefined
  /** `dot` is the tight-cell form: colour only, name carried by the title. */
  variant?: 'label' | 'dot'
  className?: string
}

export default function PosBadge(
  { pos, variant = 'label', className }: PosBadgeProps,
) {
  const key = (pos ?? '').trim().toUpperCase()
  // An artifact written without positions is an ordinary state, not a fault:
  // render nothing rather than a badge that says nothing.
  if (!key) return null
  const colour = POS_COLOR[key]

  if (variant === 'dot') {
    return (
      <span
        data-testid={`pos-dot-${key}`}
        title={key}
        aria-label={key}
        className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full
                    ${className ?? ''}`}
        // An unrecognised position gets the faint neutral, never a hue it
        // could be mistaken for.
        style={{ background: colour ?? 'var(--color-text-faint)' }}
      />
    )
  }

  return (
    <span
      data-testid={`pos-badge-${key}`}
      className={`num text-[10px] tracking-[0.08em]
                  ${colour ? '' : 'text-text-muted'} ${className ?? ''}`}
      style={colour ? { color: colour } : undefined}
    >
      {key}
    </span>
  )
}
