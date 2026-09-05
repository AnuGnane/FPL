import { Monitor, Moon, Sun } from 'lucide-react'
import Segmented from './Segmented'
import { THEMES, type Theme, useTheme } from './useTheme'

const LABEL: Record<Theme, string> = {
  system: 'System', dark: 'Dark', light: 'Light',
}

const ICON: Record<Theme, typeof Monitor> = {
  system: Monitor, dark: Moon, light: Sun,
}

export interface ThemeToggleProps {
  /** The tab-bar form: one icon-only button that cycles the three states. */
  compact?: boolean
}

/**
 * The theme control, in the two shapes the shell has room for: a segmented
 * row in the sidebar footer, one cycling icon button in the phone's bottom
 * bar, its state carried by the aria-label.
 */
export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const [theme, choose] = useTheme()

  if (compact) {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
    const Icon = ICON[theme]
    return (
      <button
        type="button"
        aria-label={`Theme: ${theme}`}
        onClick={() => choose(next)}
        className="flex flex-col items-center gap-0.5 px-3 py-2 text-[11px]
                   text-text-muted hover:text-text"
      >
        <Icon aria-hidden size={16} />
      </button>
    )
  }

  return (
    <Segmented
      label="Theme"
      value={theme}
      onChange={choose}
      className="w-full [&>button]:flex-1"
      options={THEMES.map((option) => ({ value: option, label: LABEL[option] }))}
    />
  )
}
