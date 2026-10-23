// @vitest-environment node
// Read as a plain file: under the default jsdom environment `import.meta.url`
// is an http:// URL and readFileSync cannot resolve it.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Holiday F-212: `tsc` is the first line of `npm run check`, and these five
// flags were turned on when they cost four `override` keywords between them;
// each stays on or this fails, so none is dropped silently.
const FLAGS = [
  'noUnusedLocals',
  'noUnusedParameters',
  'noFallthroughCasesInSwitch',
  'noImplicitReturns',
  'noImplicitOverride',
] as const

const tsconfig = JSON.parse(
  readFileSync(new URL('../tsconfig.json', import.meta.url), 'utf8'),
) as { compilerOptions: Record<string, unknown> }

describe('tsconfig.json', () => {
  it.each(FLAGS)('turns %s on', (flag) => {
    expect(tsconfig.compilerOptions[flag], `${flag} must be true in tsconfig.json`).toBe(true)
  })
})
