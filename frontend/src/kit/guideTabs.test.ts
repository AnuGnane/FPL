// GUIDE §5 names every `?tab=` value the four tabbed hubs accept (holiday
// F-99). Each hub's `TABS` array is what `useTabParam` reads, so a tab added
// there and not to the GUIDE fails here rather than going undocumented.
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const read = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

const HUBS = ['Planning', 'Players', 'League', 'Model'] as const

function tabsOf(source: string): string[] {
  const match = /const TABS = \[([^\]]*)\]/.exec(source)
  if (!match) return []
  return [...match[1].matchAll(/'([^']+)'/g)].map((m) => m[1])
}

describe('GUIDE §5 tab values', () => {
  const guide = read('../../../docs/GUIDE.md')

  it.each(HUBS)('%s has a TABS array to read', (hub) => {
    expect(tabsOf(read(`../hubs/${hub}.tsx`)).length).toBeGreaterThan(0)
  })

  it.each(HUBS)('names every %s tab as a ?tab= value', (hub) => {
    const missing = tabsOf(read(`../hubs/${hub}.tsx`))
      .filter((tab) => !guide.includes('`?tab=' + tab + '`'))
    expect(missing).toEqual([])
  })
})
