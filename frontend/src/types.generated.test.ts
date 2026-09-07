/**
 * v12 W5 §6.6, v17a §3.4 — the generated types are the committed schema's.
 *
 * `render` is imported from the script `npm run types` runs, so this diffs
 * exactly what that command writes and restates none of its options. Called
 * as a library rather than through a subprocess: no interpreter, no `npx`
 * resolution inside a test, and it runs wherever `npm ci` has run.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { render } from '../scripts/gen_types'

const HERE = dirname(fileURLToPath(import.meta.url))
const BANNER = readFileSync(join(HERE, 'types.banner.txt'), 'utf8')

function fresh(): Promise<string> {
  const schema = JSON.parse(readFileSync(join(HERE, 'schemas.json'), 'utf8'))
  return render(schema, BANNER)
}

describe('types.generated.ts', () => {
  it('is exactly what the committed schema compiles to', async () => {
    const committed = readFileSync(join(HERE, 'types.generated.ts'), 'utf8')
    expect(committed).toBe(await fresh())
  }, 60_000)

  it('is deterministic', async () => {
    expect(await fresh()).toBe(await fresh())
  }, 60_000)
})
