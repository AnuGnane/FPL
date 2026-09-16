import { ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'

/**
 * Prose a reader needs once, folded away after they have read it (v19d §2.3).
 *
 * The ladder's five lines and the board's two are right — they stop a number
 * being misread — and they also stand between the reader and the numbers on
 * every visit. Open on first paint, because the first visit is the one that
 * needs them; remembered closed, because the tenth does not.
 *
 * Not `<details>`: the print stylesheet has to force the content visible, and
 * a native disclosure's closed content is not in the box tree at all, so no
 * rule can bring it back. The content wrapper here is always rendered and
 * carries `hidden`, which `@media print` overrides.
 */
export interface DisclosureProps {
  summary: string
  /** A `localStorage` key, when the choice should outlive the visit. */
  storageKey?: string
  defaultOpen?: boolean
  children: ReactNode
}

/** The stored choice, or the default — including when storage itself throws
 *  (private mode, or a browser refusing site data). Showing the prose is a
 *  perfectly good answer to that, exactly as `useTheme` follows the system. */
function readOpen(key: string | undefined, fallback: boolean): boolean {
  if (key === undefined) return fallback
  try {
    const stored = localStorage.getItem(key)
    if (stored === 'open') return true
    if (stored === 'closed') return false
    return fallback
  } catch {
    return fallback
  }
}

export default function Disclosure(
  { summary, storageKey, defaultOpen = true, children }: DisclosureProps,
) {
  const [open, setOpen] = useState(() => readOpen(storageKey, defaultOpen))

  function toggle(): void {
    const next = !open
    setOpen(next)
    if (storageKey === undefined) return
    try {
      localStorage.setItem(storageKey, next ? 'open' : 'closed')
    } catch {
      // The choice still holds for this tab; it just will not outlive it.
    }
  }

  return (
    <div className="mb-3">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggle}
        className="flex items-center gap-1 text-text-muted hover:text-text"
      >
        <ChevronDown
          size={14}
          aria-hidden
          className={open ? 'rotate-180' : ''}
        />
        {summary}
      </button>
      {/* Always rendered so `@media print` can unhide it; `hidden` rather
          than a conditional for that one reason. */}
      <div data-disclosure hidden={!open}>{children}</div>
    </div>
  )
}
