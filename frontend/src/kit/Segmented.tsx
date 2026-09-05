import type { ReactNode } from 'react'

export interface SegmentedOption<V extends string> {
  value: V
  label: ReactNode
  title?: string
}

export interface SegmentedProps<V extends string> {
  options: ReadonlyArray<SegmentedOption<V>>
  value: V
  onChange: (next: V) => void
  /** The group's accessible name. */
  label: string
  className?: string
}

/** One segment's classes: secondary chrome, accent text on the raised
 *  surface when active (spec §5). Exported so a control that must keep its
 *  own ARIA — the board's plan tabs, the EO lens toggle — matches
 *  class-for-class. */
export function segmentClass(active: boolean): string {
  return 'h-7 whitespace-nowrap px-2.5 text-xs font-medium leading-none '
    + (active ? 'bg-raised text-accent-text'
              : 'text-text-muted hover:text-text')
}

/** A toggle group: Pitch/Table, the position filters, the theme choice.
 *  `aria-pressed` per segment rather than a radio group, because every
 *  existing test and screen reader already reads these as pressed buttons. */
export default function Segmented<V extends string>(
  { options, value, onChange, label, className = '' }: SegmentedProps<V>,
) {
  return (
    <div
      role="group"
      aria-label={label}
      className={'inline-flex divide-x divide-border overflow-hidden '
        + `rounded-ctl border border-border ${className}`}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          title={option.title}
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={segmentClass(value === option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
