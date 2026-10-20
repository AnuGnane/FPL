// @vitest-environment node
/**
 * Holiday F-153 — every module under `kit/` and `api/` has a test of its own,
 * and since F-155 every module under `hubs/` too.
 *
 * v19h's code health and GUIDE §10: the shared components and the request
 * layer are what every hub leans on, and on 2026-10-19 eight of them had no
 * sibling test, so a change there was checked only by whichever hub happened
 * to render it. Each `.ts` or `.tsx` that is not itself a test or a `.d.ts`
 * has a `.test.ts` or `.test.tsx` of the same stem beside it; a fixture is
 * `.json` and is never scanned. `hubs/` joined once F-154 and F-155 had
 * given its last eight untested files tests.
 */
import { readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? walk(path) : [relative(SRC, path)]
  })
}

/** The modules in `files` with no `<stem>.test.ts(x)` in `files`. */
function untested(files: string[]): string[] {
  const present = new Set(files)
  return files
    .filter((file) => /\.tsx?$/.test(file) && !/\.(test|d)\.tsx?$/.test(file))
    .filter((file) => {
      const stem = file.replace(/\.tsx?$/, '')
      return !present.has(`${stem}.test.ts`) && !present.has(`${stem}.test.tsx`)
    })
}

describe('kit, api and hubs coverage', () => {
  it('gives every kit, api and hubs module a test of the same stem', () => {
    const files = [...walk(join(SRC, 'kit')), ...walk(join(SRC, 'api')),
                   ...walk(join(SRC, 'hubs'))]
    expect(files.length).toBeGreaterThan(0)
    expect(untested(files), 'modules with no sibling test').toEqual([])
  })

  it('names a module whose test is missing', () => {
    expect(untested([
      'kit/Chip.tsx', 'kit/Chip.test.tsx',
      'kit/useThing.ts', 'kit/useThing.test.tsx',
      'kit/Orphan.tsx', 'api/orphan.ts', 'api/client.test.ts',
      'hubs/live/Pitch.tsx', 'hubs/live/Pitch.test.tsx',
      'hubs/live/Orphan.tsx', 'hubs/live/board.fixture.json',
      'hubs/live/vendor.d.ts',
    ])).toEqual(['kit/Orphan.tsx', 'api/orphan.ts', 'hubs/live/Orphan.tsx'])
  })
})
