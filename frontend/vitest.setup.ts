import '@testing-library/jest-dom/vitest'

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
