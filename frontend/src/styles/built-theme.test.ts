// @vitest-environment node
// The theme is written in tokens, but it *ships* as one compiled stylesheet,
// and the two can disagree: Tailwind resolves a slash opacity modifier at
// build time and bakes the dark hex into a literal border-color rule, which
// no amount of correctness in theme.css will undo. This suite reads what the
// build actually emitted.
//
// Build-optional: `npm run build` writes into the Python package's static/
// directory, which is gitignored, so a clean CI checkout has nothing to read.
// Absent output skips rather than fails; present output is held to the rules.
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { defined } from '../kit/defined'

const ASSETS = fileURLToPath(
  new URL('../../../src/gaffer/web/static/assets', import.meta.url),
)

function builtCss(): string | null {
  let names: string[]
  try {
    names = readdirSync(ASSETS).filter((n) => n.endsWith('.css'))
  } catch {
    return null
  }
  if (names.length === 0) return null
  return names.map((n) => readFileSync(`${ASSETS}/${n}`, 'utf8')).join('\n')
}

const css = builtCss()

/** How many unclosed `{` stand open at `index`. */
function depthAt(source: string, index: number): number {
  let depth = 0
  for (let i = 0; i < index; i += 1) {
    if (source[i] === '{') depth += 1
    else if (source[i] === '}') depth -= 1
  }
  return depth
}

/** Every index where `needle` starts, in order. */
function indexesOf(source: string, needle: string): number[] {
  const found: number[] = []
  for (let at = source.indexOf(needle); at !== -1;
    at = source.indexOf(needle, at + 1)) found.push(at)
  return found
}

// The dark tint values. Each may appear in the compiled sheet ONLY as the
// value of a `--color-*-tint` custom property — never as a literal
// background-color, which is what a re-baked opacity modifier looks like.
const TINT = ['#5fcf9424', '#f0876a24', '#e2b25a24', '#4f8ff724']
const BASE = ['#5fcf94', '#f0876a', '#e2b25a', '#4f8ff7']

describe.skipIf(css === null)('the compiled stylesheet', () => {
  it('carries the light overrides at top level, after the @layer tokens', () => {
    const sheet = defined(css, 'the compiled stylesheet')
    // Vite's minifier drops the quotes; accept the sheet either way.
    const at = [...indexesOf(sheet, '[data-theme=light]'),
      ...indexesOf(sheet, '[data-theme="light"]')]
      .filter((i) => depthAt(sheet, i) === 0)
    expect(at.length, 'a top-level [data-theme=light] block').toBeGreaterThan(0)
    // Later than the last @layer, or the cascade would let a layered rule
    // win and the explicit light choice would not take.
    expect(Math.max(...at)).toBeGreaterThan(sheet.lastIndexOf('@layer'))
  })

  it('keeps the tint tier as variables, not as baked colours', () => {
    const sheet = defined(css, 'the compiled stylesheet')
    for (const value of TINT) {
      for (const at of indexesOf(sheet, value)) {
        const from = Math.max(sheet.lastIndexOf(';', at),
                              sheet.lastIndexOf('{', at)) + 1
        expect(sheet.slice(from, at), `${value} outside a variable`)
          .toMatch(/^--color-[a-z-]+-tint:\s*$/)
      }
    }
  })

  it('emits no border-color baked from a dark meaning colour', () => {
    const sheet = defined(css, 'the compiled stylesheet')
    for (const hex of BASE) {
      expect(sheet, `border-color baked from ${hex}`)
        .not.toContain(`border-color:${hex}`)
    }
  })
})

// One visible line when there is nothing to check, rather than a silent pass.
describe.skipIf(css !== null)('the compiled stylesheet', () => {
  it.skip('is not built in this checkout', () => {})
})
