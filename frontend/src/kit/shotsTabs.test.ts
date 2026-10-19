// @vitest-environment node
// `shots.sh` shoots every `?tab=` value the four tabbed hubs accept (holiday
// F-130), in F-99's shape (`guideTabs.test.ts`). A gate's screenshots come
// from the script, so a tab its lists never name is one no gate has seen.
// Read per hub: League's `whatif` row does not cover Planning's.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))
const read = (path: string) => readFileSync(path, 'utf8')

const HUBS = ['Planning', 'Players', 'League', 'Model'] as const

function tabsOf(source: string): string[] {
  const match = /const TABS = \[([^\]]*)\]/.exec(source)
  if (!match) return []
  return [...match[1].matchAll(/'([^']+)'/g)].map((m) => m[1])
}

function shotTabs(script: string): Set<string> {
  return new Set([...script.matchAll(/:\/([a-z-]+)\?tab=([a-z-]+)/g)]
    .map((m) => `${m[1]}?tab=${m[2]}`))
}

function unshot(script: string, hub: string, tabs: string[]): string[] {
  const shot = shotTabs(script)
  return tabs.filter((tab) => !shot.has(`${hub.toLowerCase()}?tab=${tab}`))
}

describe('shots.sh tab values', () => {
  const script = read(join(SRC, '..', 'scripts', 'shots.sh'))

  it.each(HUBS)('shoots every %s tab', (hub) => {
    const tabs = tabsOf(read(join(SRC, 'hubs', `${hub}.tsx`)))
    expect(tabs.length).toBeGreaterThan(0)
    expect(unshot(script, hub, tabs)).toEqual([])
  })

  it('names a tab missing from the script', () => {
    const script = '"planning-board:/planning?tab=board"\n"league-whatif:/league?tab=whatif"'
    expect(unshot(script, 'Planning', ['board', 'whatif'])).toEqual(['whatif'])
  })
})
