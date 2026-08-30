// @vitest-environment node
// Read as a plain file: under the default jsdom environment `import.meta.url`
// is an http:// URL and readFileSync cannot resolve it.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// The design language is locked (spec §2). These are not "some colours the
// theme happens to have" — they are the contract every kit component styles
// against, so they are asserted by value, not by presence.
const css = readFileSync(new URL('./theme.css', import.meta.url), 'utf8')

describe('theme tokens', () => {
  it('imports tailwind and opens a @theme block', () => {
    expect(css).toContain('@import "tailwindcss"')
    expect(css).toContain('@theme {')
  })

  it('defines the locked surface and text colours', () => {
    for (const [name, value] of [
      ['--color-base', '#101216'],
      ['--color-card', '#16181d'],
      ['--color-border', '#23262d'],
      ['--color-divider', '#1e2127'],
      ['--color-text', '#f2f3f5'],
      ['--color-text-secondary', '#c8cbd2'],
      ['--color-text-muted', '#9ca3af'],
      ['--color-text-faint', '#6b7280'],
      ['--color-sage', '#86b388'],
      ['--color-rust', '#e0876f'],
      ['--color-info', '#7da7c9'],
    ]) {
      expect(css).toContain(`${name}: ${value};`)
    }
  })

  // Identity, not judgement: these four must never collide with the meaning
  // colours above, or a position badge starts reading as a verdict.
  it('defines the four position identity hues', () => {
    for (const [name, value] of [
      ['--color-pos-gkp', '#d4a95c'],
      ['--color-pos-def', '#6ea8d8'],
      ['--color-pos-mid', '#a48fd8'],
      ['--color-pos-fwd', '#d88fa8'],
    ]) {
      expect(css).toContain(`${name}: ${value};`)
    }
  })

  it('keeps the position hues distinct from the meaning colours', () => {
    const meaning = ['#86b388', '#e0876f', '#7da7c9']
    const position = ['#d4a95c', '#6ea8d8', '#a48fd8', '#d88fa8']
    for (const hue of position) expect(meaning).not.toContain(hue)
  })

  it('defines the mono numeral face and the 10px card radius', () => {
    expect(css).toContain("--font-mono: 'SF Mono', Menlo, monospace;")
    expect(css).toContain('--radius-card: 10px;')
  })
})
