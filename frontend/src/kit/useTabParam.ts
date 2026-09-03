import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * v12 W5 §6.1 — the open tab, in the query string.
 *
 * A drop-in for the `useState` a controlled `Tabs.Root` needs, so a hub reads
 * `const [tab, setTab] = useTabParam(TABS, 'quality')` and changes one line.
 *
 * Three decisions worth knowing:
 *
 * - An unknown `?tab=` opens the default rather than being honoured. Radix
 *   renders a root whose value matches no `Tabs.Content` as an empty panel
 *   with no error, so `/model?tab=board` — a Planning tab name on the Model
 *   hub — would otherwise be a blank page nobody could diagnose.
 * - The write is `replace: true`. Clicking six tabs is one navigation, not
 *   six: the back button should leave the hub, not walk backwards through the
 *   strip.
 * - Other parameters survive. The hub is not the only thing that may ever put
 *   something in the query string, and a setter that rebuilt the whole search
 *   would silently drop it.
 *
 * Requires a router in scope. Every hub is rendered inside one (App.tsx's
 * `Routes`, and `MemoryRouter` in every hub test).
 */
export function useTabParam(
  tabs: readonly string[], fallback: string,
): [string, (next: string) => void] {
  const [params, setParams] = useSearchParams()
  const asked = params.get('tab')
  const tab = asked !== null && tabs.includes(asked) ? asked : fallback
  const setTab = useCallback((next: string) => {
    setParams((prev) => {
      const out = new URLSearchParams(prev)
      out.set('tab', next)
      return out
    }, { replace: true })
  }, [setParams])
  return [tab, setTab]
}
