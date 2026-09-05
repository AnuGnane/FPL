// @vitest-environment node
// Read as a plain file: under the default jsdom environment `import.meta.url`
// is an http:// URL and readFileSync cannot resolve it.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// v14 (spec §3): the dark ledger. The @theme block is the dark palette and
// the source of every token name; light is an override of the same names.
// Asserted by value, not by presence — these are the contract every kit
// component styles against.
const css = readFileSync(new URL('./theme.css', import.meta.url), 'utf8')

const DARK: Array<[string, string]> = [
  ['--color-base', '#121418'],
  ['--color-raised', '#181b20'],
  ['--color-input', '#1b1f25'],
  ['--color-border', '#262a31'],
  ['--color-divider', '#1c1f25'],
  ['--color-text', '#e4e6ea'],
  ['--color-text-secondary', '#c3c7ce'],
  ['--color-text-muted', '#8a909b'],
  ['--color-text-faint', '#5f6570'],
  ['--color-up', '#5fcf94'],
  ['--color-up-tint', '#5fcf9424'],
  ['--color-down', '#f0876a'],
  ['--color-down-tint', '#f0876a24'],
  ['--color-warn', '#e2b25a'],
  ['--color-warn-tint', '#e2b25a24'],
  ['--color-accent', '#4f8ff7'],
  ['--color-accent-text', '#7fb0ff'],
  ['--color-accent-tint', '#4f8ff724'],
  ['--color-pos-gkp', '#d9b064'],
  ['--color-pos-def', '#7fb4e6'],
  ['--color-pos-mid', '#b39ee8'],
  ['--color-pos-fwd', '#e59ab5'],
  ['--color-turf', '#1b3a2b'],
  ['--color-turf-line', '#ffffff1f'],
]

// Retired names kept for one cycle (spec §3, plan R11): same value as the
// name that replaced them, so a class not yet swept renders identically.
const ALIASES: Array<[string, string]> = [
  ['--color-sage', '--color-up'],
  ['--color-rust', '--color-down'],
]

const TOKENS = [...DARK.map(([name]) => name), ...ALIASES.map(([name]) => name)]

/** The declarations between `opener` and the first `}` that follows it. */
function block(opener: string): string {
  const start = css.indexOf(opener)
  expect(start, `${opener} missing`).toBeGreaterThan(-1)
  const from = start + opener.length
  return css.slice(from, css.indexOf('}', from))
}

function valueOf(source: string, token: string): string {
  const found = new RegExp(
    `${token}:\\s*(#[0-9a-f]{6}(?:[0-9a-f]{2})?);`,
  ).exec(source)
  expect(found, `${token} has no hex value`).not.toBeNull()
  return found![1]
}

// WCAG 2.1 relative luminance and contrast, nine lines rather than a
// dependency, so the test keeps running.
function channel(value: number): number {
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1, 7), 16)
  return 0.2126 * channel(((n >> 16) & 255) / 255)
    + 0.7152 * channel(((n >> 8) & 255) / 255)
    + 0.0722 * channel((n & 255) / 255)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('theme tokens', () => {
  it('imports tailwind and opens a @theme block', () => {
    expect(css).toContain('@import "tailwindcss"')
    expect(css).toContain('@theme {')
  })

  it('defines every dark token by value', () => {
    const theme = block('@theme {')
    for (const [name, value] of DARK) {
      expect(valueOf(theme, name), name).toBe(value)
    }
  })

  it('keeps every retired name as a literal copy of its replacement', () => {
    for (const scope of ['@theme {', '[data-theme="light"] {',
      ':root:not([data-theme="dark"]) {']) {
      const source = block(scope)
      for (const [alias, real] of ALIASES) {
        expect(valueOf(source, alias), `${alias} in ${scope}`)
          .toBe(valueOf(source, real))
      }
    }
  })

  it('defines no soft tier: tints replaced it', () => {
    expect(css).not.toMatch(/--color-[a-z]+-soft/)
  })

  // Identity, not judgement: these four must never collide with the meaning
  // colours, or a position badge starts reading as a verdict.
  it('keeps the position hues distinct from the meaning colours', () => {
    const meaning = ['#5fcf94', '#f0876a', '#e2b25a', '#4f8ff7', '#7fb0ff']
    for (const hue of ['#d9b064', '#7fb4e6', '#b39ee8', '#e59ab5']) {
      expect(meaning).not.toContain(hue)
    }
  })

  it('defines the two radii and no card radius larger than a control', () => {
    expect(css).toContain('--radius-chip: 2px;')
    expect(css).toContain('--radius-ctl: 3px;')
    expect(css).not.toContain('--radius-card: 10px;')
    expect(css).not.toContain('--radius-card')
  })

  it('defines the faces, the tabular utility and the 13px base', () => {
    expect(css).toContain("--font-mono: 'SF Mono', Menlo, monospace;")
    expect(css).toMatch(/\.tn\s*\{[^}]*font-variant-numeric:\s*tabular-nums/)
    expect(css).not.toMatch(/\.num[^}]*font-family/)
    expect(css).not.toMatch(/\.num\b/)
    expect(css).toMatch(/body\s*\{[^}]*font-size:\s*13px/)
  })

  it('draws the one label style at 10px, .08em, uppercase, muted', () => {
    const label = block('.label {')
    expect(label).toContain('font-size: 10px')
    expect(label).toContain('letter-spacing: 0.08em')
    expect(label).toContain('text-transform: uppercase')
    expect(label).toContain('color: var(--color-text-muted)')
  })

  it('focuses in accent (rule 3)', () => {
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:[^;]*var\(--color-accent\)/)
  })
})

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
    expect(css).toContain(':root:not([data-theme="dark"])')
  })

  it('agrees with itself: the mirror is the light block', () => {
    const light = block('[data-theme="light"] {')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(valueOf(mirror, token), token).toBe(valueOf(light, token))
    }
  })

  it('keeps the light turf and its markings', () => {
    const light = block('[data-theme="light"] {')
    expect(valueOf(light, '--color-turf')).toBe('#2f6b45')
    expect(valueOf(light, '--color-turf-line')).toBe('#ffffff47')
  })

  // Both surfaces: muted text sits on the page base and on the raised band
  // (table headers, hover rows), and a token that only clears 4.5:1 on one
  // is unreadable on the other.
  it('holds 4.5:1 for every text token on both light surfaces', () => {
    const light = block('[data-theme="light"] {')
    for (const surface of ['--color-base', '--color-raised']) {
      const hex = valueOf(light, surface)
      for (const token of ['--color-text', '--color-text-secondary',
        '--color-text-muted', '--color-up', '--color-down', '--color-warn',
        '--color-accent-text']) {
        expect(contrast(valueOf(light, token), hex),
               `${token} on ${surface}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })

  it('keeps the faint tier at its 3.5:1 floor on the raised surface', () => {
    const light = block('[data-theme="light"] {')
    expect(contrast(valueOf(light, '--color-text-faint'),
                    valueOf(light, '--color-raised')))
      .toBeGreaterThanOrEqual(3.5)
  })

  it('is applied by a boot script before the bundle runs', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url),
                              'utf8')
    expect(html).toContain("localStorage.getItem('gaffer-theme')")
    expect(html).toContain("setAttribute('data-theme'")
    expect(html).toContain('try {')
    expect(html).toContain('catch')
    expect(html.indexOf("localStorage.getItem('gaffer-theme')"))
      .toBeLessThan(html.indexOf('/src/main.tsx'))
  })
})
