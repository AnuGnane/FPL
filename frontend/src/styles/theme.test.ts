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

const TOKENS = [
  '--color-base', '--color-card', '--color-border', '--color-divider',
  '--color-text', '--color-text-secondary', '--color-text-muted',
  '--color-text-faint', '--color-sage', '--color-rust', '--color-info',
  '--color-pos-gkp', '--color-pos-def', '--color-pos-mid', '--color-pos-fwd',
]

/** The declarations between `opener` and the first `}` that follows it. */
function block(opener: string): string {
  const start = css.indexOf(opener)
  expect(start, `${opener} missing`).toBeGreaterThan(-1)
  const from = start + opener.length
  return css.slice(from, css.indexOf('}', from))
}

function valueOf(source: string, token: string): string {
  const found = new RegExp(`${token}:\\s*(#[0-9a-f]{6});`).exec(source)
  expect(found, `${token} has no hex value`).not.toBeNull()
  return found![1]
}

// WCAG 2.1 relative luminance and contrast, implemented here rather than
// pulled in: it is nine lines, and a theme test that needs a dependency to
// say whether the text is readable is a test nobody will keep running.
function channel(value: number): number {
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  return 0.2126 * channel(((n >> 16) & 255) / 255)
    + 0.7152 * channel(((n >> 8) & 255) / 255)
    + 0.0722 * channel((n & 255) / 255)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('light theme', () => {
  it('overrides every token exactly once for an explicit light choice', () => {
    const light = block('[data-theme="light"] {')
    for (const token of TOKENS) {
      expect(light.split(`${token}:`).length - 1,
             `${token} in [data-theme="light"]`).toBe(1)
    }
  })

  it('mirrors the same tokens under a light system preference', () => {
    expect(css).toContain('@media (prefers-color-scheme: light)')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(mirror.split(`${token}:`).length - 1,
             `${token} in the system mirror`).toBe(1)
    }
  })

  it('lets an explicit dark choice out of the system mirror', () => {
    // Without the :not() guard a user who chose dark on a light-set laptop
    // would get the light palette back the moment the media query matched.
    expect(css).toContain(':root:not([data-theme="dark"])')
  })

  it('agrees with itself: the mirror is the light block', () => {
    const light = block('[data-theme="light"] {')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(valueOf(mirror, token), token).toBe(valueOf(light, token))
    }
  })

  it('holds 4.5:1 for every text token on a light card', () => {
    const light = block('[data-theme="light"] {')
    const card = valueOf(light, '--color-card')
    for (const token of ['--color-text', '--color-text-secondary',
      '--color-text-muted']) {
      expect(contrast(valueOf(light, token), card),
             `${token} on card`).toBeGreaterThanOrEqual(4.5)
    }
  })
})
