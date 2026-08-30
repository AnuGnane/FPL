import { THEMES, type Theme, useTheme } from './useTheme'

const ICON: Record<Theme, string> = {
  system: '◐',
  dark: '☾',
  light: '☀',
}

const LABEL: Record<Theme, string> = {
  system: 'System',
  dark: 'Dark',
  light: 'Light',
}

export interface ThemeToggleProps {
  /** The tab-bar form: one icon-only button that cycles the three states. */
  compact?: boolean
}

/**
 * The theme control, in the two shapes the shell has room for.
 *
 * Segmented on desktop, where the sidebar footer can hold three labelled
 * options and showing which one is live is worth the width. Compact on
 * mobile, where the bottom bar has six hubs already and a seventh slot is
 * all there is: one button, cycling, its state carried by the aria-label
 * rather than by three of anything.
 */
export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const [theme, choose] = useTheme()

  if (compact) {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
    return (
      <button
        type="button"
        aria-label={`Theme: ${theme}`}
        onClick={() => choose(next)}
        className="flex flex-col items-center gap-0.5 rounded-card px-3 py-2
                   text-[11px] text-text-muted hover:text-text"
      >
        <span aria-hidden>{ICON[theme]}</span>
      </button>
    )
  }

  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex gap-1 rounded-card border border-border p-1"
    >
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={theme === option}
          onClick={() => choose(option)}
          className={`flex flex-1 items-center justify-center gap-1
                      rounded-card px-1.5 py-1 text-[11px] ${theme === option
                        ? 'bg-card text-text' : 'text-text-muted hover:text-text'}`}
        >
          <span aria-hidden>{ICON[option]}</span>
          {LABEL[option]}
        </button>
      ))}
    </div>
  )
}
