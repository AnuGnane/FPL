// Holiday F-185: a test that writes to console.error or console.warn fails
// unless the message belongs to a family listed here. On 2026-10-22 vitest
// passed 1,295 tests and printed 57 stderr blocks nobody read; the guard makes
// a new one a failure instead of noise. Each entry names the package that
// empties it, so the list only ever shrinks (F-186, F-187).

interface ExpectedMessage {
  pattern: RegExp
  reason: string
}

export const EXPECTED: readonly ExpectedMessage[] = [
  {
    pattern: /React Router Future Flag Warning/,
    reason: 'react-router-dom 6.26 warns once per router mount until the v7 '
      + 'future flags are set; F-187 sets them and removes this entry.',
  },
  {
    pattern: /not wrapped in act\(/,
    reason: 'sixteen state updates across nine test files land outside act(); '
      + 'F-186 closes them at source and removes this entry.',
  },
]

type Method = 'error' | 'warn'
const METHODS: readonly Method[] = ['error', 'warn']

let seen: string[] = []
let originals: Partial<Record<Method, (...args: unknown[]) => void>> = {}

/** Whether a console message belongs to a family the guard tolerates. */
export function isExpected(message: string): boolean {
  return EXPECTED.some((entry) => entry.pattern.test(message))
}

/** Throws naming the first message no entry of `EXPECTED` matches. */
export function assertExpected(messages: readonly string[]): void {
  const stray = messages.find((message) => !isExpected(message))
  if (stray !== undefined) {
    throw new Error(
      `unexpected console output (add a fix, or an EXPECTED entry with its reason): ${stray}`,
    )
  }
}

/**
 * Replaces console.error and console.warn with recorders that keep each
 * call's first argument and still print it. A plain wrapper rather than a
 * vi.spyOn, so a test's own spy (ErrorBoundary's, for one) wraps it and its
 * mockRestore puts the recorder back rather than the real console.
 */
export function startConsoleGuard(): void {
  seen = []
  originals = {}
  for (const method of METHODS) {
    const original = console[method] as (...args: unknown[]) => void
    originals[method] = original
    console[method] = (...args: unknown[]) => {
      seen.push(String(args[0]))
      original.apply(console, args)
    }
  }
}

/** Restores the console, then runs `assertExpected` over what was recorded. */
export function stopConsoleGuard(): void {
  for (const method of METHODS) {
    const original = originals[method]
    if (original !== undefined) console[method] = original
  }
  originals = {}
  const messages = seen
  seen = []
  assertExpected(messages)
}
