/**
 * v12 W5 §6.6 — the generated types are the committed schema's.
 *
 * `compile()` is called as a library rather than through `npx`: no network, no
 * subprocess, no `npx` resolution inside a test, and it runs wherever
 * `npm ci` has run.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile } from 'json-schema-to-typescript'
import { describe, expect, it } from 'vitest'

const HERE = dirname(fileURLToPath(import.meta.url))

export const OPTIONS = {
  bannerComment: '',
  additionalProperties: false,
  unreachableDefinitions: true,
  declareExternallyReferenced: true,
  style: { singleQuote: true, semi: false },
} as const

const BANNER = readFileSync(join(HERE, 'types.banner.txt'), 'utf8')

async function generate(): Promise<string> {
  const schema = JSON.parse(readFileSync(join(HERE, 'schemas.json'), 'utf8'))
  return BANNER + await compile(schema, 'GafferApi', OPTIONS)
}

describe('types.generated.ts', () => {
  it('is exactly what the committed schema compiles to', async () => {
    const fresh = await generate()
    const committed = readFileSync(join(HERE, 'types.generated.ts'), 'utf8')
    expect(committed).toBe(fresh)
  }, 60_000)

  it('is deterministic', async () => {
    expect(await generate()).toBe(await generate())
  }, 60_000)
})
