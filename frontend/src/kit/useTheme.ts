import { useCallback, useEffect, useState } from 'react'

/**
 * Three states, not two. "system" is the absence of a choice — no attribute
 * on <html>, so theme.css's `prefers-color-scheme` mirror decides — and it
 * is what a fresh install gets. The other two are the user overruling their
 * machine, which is the whole reason a toggle exists.
 */
export type Theme = 'system' | 'dark' | 'light'

export const THEMES: Theme[] = ['system', 'dark', 'light']

export const THEME_KEY = 'gaffer-theme'
/** Shared verbatim with the boot script in index.html. */

/** The stored choice, or "system" — including when storage itself throws. */
export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return stored === 'dark' || stored === 'light' ? stored : 'system'
  } catch {
    // Private mode, or a browser configured to refuse site data. Following
    // the system is a perfectly good answer to that.
    return 'system'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

/** The current theme and a setter that persists it. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => { applyTheme(theme) }, [theme])

  const choose = useCallback((next: Theme) => {
    setTheme(next)
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // The choice still applies to this tab; it just will not outlive it.
    }
  }, [])

  return [theme, choose]
}
