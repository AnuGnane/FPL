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
