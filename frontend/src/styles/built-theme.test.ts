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

// The three dark soft values. Each may appear in the compiled sheet ONLY as
// the value of a `--color-*-soft` custom property — never as a literal
// border-color, which is what a re-baked opacity modifier looks like.
const SOFT = ['#86b38866', '#e0876f66', '#7da7c966']
const BASE = ['#86b388', '#e0876f', '#7da7c9']

describe.skipIf(css === null)('the compiled stylesheet', () => {
  it('carries the light overrides at top level, after the @layer tokens', () => {
    // Vite's minifier drops the quotes; accept the sheet either way.
    const at = [...indexesOf(css!, '[data-theme=light]'),
      ...indexesOf(css!, '[data-theme="light"]')]
      .filter((i) => depthAt(css!, i) === 0)
    expect(at.length, 'a top-level [data-theme=light] block').toBeGreaterThan(0)
    // Later than the last @layer, or the cascade would let a layered rule
    // win and the explicit light choice would not take.
    expect(Math.max(...at)).toBeGreaterThan(css!.lastIndexOf('@layer'))
  })

  it('keeps the soft tier as variables, not as baked border colours', () => {
    for (const value of SOFT) {
      for (const at of indexesOf(css!, value)) {
        // Walk back to the start of this declaration and require it to be a
        // custom property. A baked utility reads `border-color:#86b38866`.
        const from = Math.max(css!.lastIndexOf(';', at),
                              css!.lastIndexOf('{', at)) + 1
        expect(css!.slice(from, at), `${value} outside a variable`)
          .toMatch(/^--color-[a-z-]+-soft:\s*$/)
      }
    }
  })

  it('emits no border-color baked from a dark meaning colour', () => {
    for (const hex of BASE) {
      expect(css!, `border-color baked from ${hex}`)
        .not.toContain(`border-color:${hex}`)
    }
  })
})

// One visible line when there is nothing to check, rather than a silent pass.
describe.skipIf(css !== null)('the compiled stylesheet', () => {
  it.skip('is not built in this checkout', () => {})
})
