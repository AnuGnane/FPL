import { useEffect, useState } from 'react'

export type ToastTone = 'positive' | 'negative'

export interface Toast {
  id: number
  tone: ToastTone
  text: string
}

/** Three, and the oldest goes first (plan A7). */
export const MAX_TOASTS = 3
/** Long enough to read a sentence, short enough not to sit over the page. */
export const DISMISS_MS = 6000

let nextId = 1
let live: Toast[] = []
const listeners = new Set<(toasts: Toast[]) => void>()

function emit(): void {
  for (const listener of listeners) listener(live)
}

/**
 * Raise a toast. Importable anywhere, including where no outlet is mounted.
 *
 * A module store rather than a React context, deliberately (plan A7): the
 * components that acknowledge a write — `PinDialog`, `OverridesCard`,
 * `DraftsTab` — are rendered bare by their own suites and by
 * `hubs/responsive.test.tsx`, none of which mount `AppShell`. A provider they
 * had to be wrapped in would be a provider every test file has to learn
 * about, and forgetting it would be a crash rather than a missing toast.
 *
 * The copy is the caller's job and the contract is spec D3's: say what
 * happened. "Could not save the pin — the server did not answer" is a
 * sentence; "Error!" is a noise.
 */
export function toast(tone: ToastTone, text: string): number {
  const id = nextId++
  // slice(-MAX) keeps the newest: a burst of failures leaves the three most
  // recent on screen rather than the three the user has already read.
  live = [...live, { id, tone, text }].slice(-MAX_TOASTS)
  emit()
  // Scheduled here rather than in an effect inside the outlet, so a toast
  // raised while nothing is mounted still expires instead of accumulating in
  // module state until the tab is closed.
  if (typeof window !== 'undefined') {
    window.setTimeout(() => dismissToast(id), DISMISS_MS)
  }
  return id
}

export function dismissToast(id: number): void {
  const next = live.filter((t) => t.id !== id)
  if (next.length === live.length) return
  live = next
  emit()
}

/** For tests. Module state outlives a test case exactly as `useJob`'s
 *  remembered map does, so `vitest.setup.ts` clears both. */
export function resetToasts(): void {
  live = []
  nextId = 1
  emit()
}

export function currentToasts(): Toast[] {
  return live
}

export function useToasts(): Toast[] {
  const [shown, setShown] = useState<Toast[]>(live)
  useEffect(() => {
    listeners.add(setShown)
    // Re-read on subscribe: a toast raised between render and effect would
    // otherwise never reach this outlet.
    setShown(live)
    return () => { listeners.delete(setShown) }
  }, [])
  return shown
}

/** One outlet, mounted once by `AppShell`. */
export default function ToastOutlet() {
  const shown = useToasts()
  return (
    <div
      data-testid="toast-outlet"
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-2 z-[60] flex
                 flex-col items-center gap-2 px-4"
    >
      {shown.map((t) => (
        <div
          key={t.id}
          data-testid="toast"
          data-tone={t.tone}
          className={'pointer-events-auto max-w-md rounded-card border '
            + 'bg-card px-3 py-2 shadow-lg '
            + (t.tone === 'negative'
              ? 'border-rust text-rust' : 'border-border text-text')}
        >
          {t.text}
        </div>
      ))}
    </div>
  )
}
