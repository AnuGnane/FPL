import '@testing-library/jest-dom/vitest'
import { beforeEach } from 'vitest'

// useJob remembers a running job id in module state so a remounted tab can
// re-attach to it (see the comment there). Module state survives a test case,
// so without this a job finished in one test is recovered by the next test's
// first mount and its result painted over a fresh page. Cleared centrally
// rather than per suite: any hub that mounts a tab is exposed to it.
//
// Imported here rather than at the top of the file, and deliberately. A
// static import would load useJob — and through it the real `api/client` —
// before the test file's own `vi.mock('../../api/client')` was registered, so
// the tab under test would hold a hook wired to the real `fetch` and no
// stubbed solve would ever come back. By the time a beforeEach runs the
// module graph is built and mocked, and this resolves to the same instance
// the component got.
beforeEach(async () => {
  const { resetJobSlots } = await import('./src/api/useJob')
  resetJobSlots()
})

// Node 22+ defines its own global `localStorage`, inert unless the process
// was started with --localstorage-file, and vitest's jsdom environment
// leaves pre-existing globals alone — in jsdom mode `window` *is* the
// global object, so jsdom's working implementation never lands and
// `localStorage` reads as undefined. Give the tests the small in-memory
// Storage a browser would have.
if (typeof localStorage === 'undefined') {
  const items = new Map<string, string>()
  const storage = {
    get length() { return items.size },
    clear: () => { items.clear() },
    getItem: (key: string) => (items.has(key) ? items.get(key)! : null),
    key: (index: number) => [...items.keys()][index] ?? null,
    removeItem: (key: string) => { items.delete(key) },
    setItem: (key: string, value: string) => { items.set(key, String(value)) },
  }
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: storage as unknown as Storage,
  })
}
