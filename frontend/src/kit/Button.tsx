import type { ButtonHTMLAttributes } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost'

/** One height (28px), one radius, one text style; three fills (spec §5).
 *  Primary is the one place accent is a fill: the action the page is for. */
const BASE = 'inline-flex h-7 shrink-0 items-center justify-center gap-1.5 '
  + 'whitespace-nowrap rounded-ctl px-3 text-xs font-medium leading-none '
  + 'disabled:cursor-not-allowed disabled:opacity-50'

const VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-accent text-white hover:opacity-90',
  secondary: 'border border-border text-text hover:bg-raised',
  ghost: 'text-text-secondary hover:text-accent-text',
}

/** The class string alone, for an element that is not a <button> — a Radix
 *  trigger, a router Link — but has to look like one. */
export function buttonClass(variant: ButtonVariant = 'secondary',
                            extra = ''): string {
  return `${BASE} ${VARIANT[variant]} ${extra}`.trim()
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

export default function Button(
  { variant = 'secondary', className = '', type = 'button', ...rest }:
  ButtonProps,
) {
  return <button type={type} className={buttonClass(variant, className)}
                 {...rest} />
}
