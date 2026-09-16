import { useEffect, useState } from 'react'

// jsdom has no matchMedia, and a component that throws in a test because of
// a layout concern is worthless. Absent matchMedia the answer is always false,
// which is the desktop layout — the one every existing test expects.
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const list = window.matchMedia(query)
    const onChange = () => setMatches(list.matches)
    onChange()
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/** Tailwind's `md` breakpoint is the desktop/mobile line (spec §8). */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 767px)')
}

/**
 * The tablet band (v19c §2.3): wide enough for a sidebar beside the page, too
 * narrow to spend 200 px on one. A landscape phone and an iPad both land here,
 * and both were double-scrolling — the page sideways inside a rail that had
 * already taken the room the table needed.
 */
export function useIsCompact(): boolean {
  return useMediaQuery('(min-width: 768px) and (max-width: 1023px)')
}

/**
 * Past the gate's screenshot width (v19c §2.4). The cap is lifted only beyond
 * 1440 because at 1400 exactly the 1180 px cap still binds — 1400 less the
 * 200 px sidebar is 1200 — so lifting it there would move desktop pixels the
 * sub-cycle promised not to move.
 */
export function useIsWide(): boolean {
  return useMediaQuery('(min-width: 1441px)')
}
