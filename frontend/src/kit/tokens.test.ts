// @vitest-environment node
// v14 (spec §7): the design rules that can be pinned mechanically. Reads the
// sources rather than rendering anything, so a class that drifts back in is
// caught wherever it lands.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const SRC = fileURLToPath(new URL('..', import.meta.url))

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return walk(path)
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : []
  })
}

// Holiday F-70: `App.tsx` and `api/` joined the scan, which CLAUDE.md had
// left to be checked by hand.
const FILES = [...walk(join(SRC, 'hubs')), ...walk(join(SRC, 'kit')),
  join(SRC, 'App.tsx'), ...walk(join(SRC, 'api'))]
const rel = (path: string) => path.slice(SRC.length)

function offenders(pattern: RegExp, allow: string[] = []): string[] {
  return FILES
    .filter((path) => !allow.some((a) => rel(path).endsWith(a)))
    .flatMap((path) => readFileSync(path, 'utf8').split('\n')
      .map((line, i) => (pattern.test(line) ? `${rel(path)}:${i + 1}` : null))
      .filter((hit): hit is string => hit !== null))
}

// Holiday F-82: CLAUDE.md's "Charts use the one grey palette", which the
// scan above never read. A colour prop names a token, the series palette,
// `currentColor` or `none`; a ternary passes only when both arms do, so a
// nested or computed colour fails closed. The braced value is read to its
// balanced close, so a prop split over two lines (League's `isYou(`) is seen.
const COLOUR = /^(var\(--color-[a-z0-9-]+\)|currentColor|none)$/
const PALETTE = /^SERIES_COLOURS\[[^\]]+\]$/

function colourArm(arm: string): boolean {
  const text = arm.trim()
  const quoted = /^(['"])(.*)\1$/.exec(text)
  return quoted ? COLOUR.test(quoted[2]) : PALETTE.test(text)
}

function colourValue(value: string): boolean {
  if (!value.startsWith('{')) return COLOUR.test(value.slice(1, -1))
  const expr = value.slice(1, -1).trim()
  const ask = expr.indexOf('?')
  if (ask < 0) return colourArm(expr)
  const arms = expr.slice(ask + 1).split(':')
  return arms.length === 2 && arms.every(colourArm)
}

function colourProps(path: string): Array<{ at: string, value: string }> {
  const text = readFileSync(path, 'utf8')
  const found: Array<{ at: string, value: string }> = []
  for (const match of text.matchAll(/\b(?:stroke|fill)=(["'{])/g)) {
    const start = match.index + match[0].length - 1
    let end = start + 1
    if (match[1] !== '{') end = text.indexOf(match[1], end) + 1
    else {
      for (let depth = 1; depth > 0 && end < text.length; end += 1) {
        if (text[end] === '{') depth += 1
        else if (text[end] === '}') depth -= 1
      }
    }
    const line = text.slice(0, match.index).split('\n').length
    found.push({ at: `${rel(path)}:${line}`, value: text.slice(start, end) })
  }
  return found
}

describe('the ledger rules (spec §3–§5)', () => {
  it('has no rounded-full, no card radius, no shadow, no gradient', () => {
    expect(offenders(/rounded-full|rounded-card|shadow-|gradient/)).toEqual([])
  })

  it('has no raw hex outside theme.css and the bundled plain shirt', () => {
    // The plain shirt is an inline SVG data URI whose two greys are part of
    // the drawing, not of the palette.
    // The three- and four-digit forms are a colour too (holiday F-70).
    expect(offenders(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3,4}\b(?![0-9a-fA-F])/,
      ['kit/PlayerCard.tsx'])).toEqual([])
  })

  it('uses the mono face only in the job log and the plan trace', () => {
    // Two files for the plan trace since v18f §2.1: the board draws the
    // disclosure and its charge lines, `TraceMoves` the move rows it wrote
    // twice. The rule is unchanged — the face follows the trace, and the
    // allowance follows the file the trace now lives in.
    expect(offenders(/font-mono/, ['kit/JobLog.tsx',
      'hubs/planning/PlannerBoard.tsx',
      'hubs/planning/TraceMoves.tsx'])).toEqual([])
  })

  it('names a face on every <code>, so none borrows the browser mono', () => {
    // v14 residual (holiday F-11): a bare <code> takes the user agent's
    // monospace face, which the font-mono scan above cannot see. The tag may
    // span lines, so this reads whole files rather than single lines.
    const bare = FILES.flatMap((path) => {
      const text = readFileSync(path, 'utf8')
      return [...text.matchAll(/<code\b[^>]*>/g)]
        .filter((m) => !/\bfont-(sans|mono)\b/.test(m[0]))
        .map((m) => `${rel(path)}:${text.slice(0, m.index).split('\n').length}`)
    })
    expect(bare).toEqual([])
  })

  it('uses tabular figures, never the retired num class', () => {
    expect(offenders(/["'` ]num["'` ]/)).toEqual([])
  })

  it('never names a retired colour', () => {
    expect(offenders(
      /(text|bg|border|from|to|ring)-(sage|rust|info|card)\b|--color-(sage|rust|info|card)\)/,
    )).toEqual([])
  })

  it('never names a class no token defines', () => {
    expect(offenders(/text-moss|text-amber|bg-surface/)).toEqual([])
  })

  it('composes Chip, and no longer knows the word Badge', () => {
    // v18f §2.2: the alias and its own allowance are gone with the file.
    expect(offenders(/<Badge\b|\bBadge,|\{ Badge\b/)).toEqual([])
  })

  it('draws fixture difficulty as a tone, never a ramp', () => {
    expect(offenders(/difficultyBackground/)).toEqual([])
  })

  // v18f §2.2. The four rules below each landed with the change that made
  // them true, which is the only order in which a rule is worth writing.
  it('names the scrim by its token, never Tailwind’s black', () => {
    // `--color-scrim`: the same rgba the two modals painted as `bg-black/70`,
    // owned by theme.css like every other colour in the app.
    expect(offenders(/bg-black/)).toEqual([])
  })

  it('names the text on the accent fill by its token, never white', () => {
    expect(offenders(/text-white/)).toEqual([])
  })

  it('has no Badge left to compose: not the file, not the export', () => {
    expect(existsSync(join(SRC, 'kit/Badge.tsx'))).toBe(false)
    expect(readFileSync(join(SRC, 'kit/index.ts'), 'utf8'))
      .not.toMatch(/\bBadge\b/)
  })

  it('pads a fixed bottom bar for the home indicator, never by a flat 4rem',
    () => {
      // v19c §2.6. `pb-16` was the height of the tab bar and nothing else, so
      // on a phone with a home indicator the last row of every hub sat under
      // the glass. The inset-aware form is the only bottom padding a page
      // above a fixed bar may carry.
      expect(offenders(/\bpb-16\b/)).toEqual([])
    })

  it('keeps a print block that drops the chrome a sheet of paper cannot use',
    () => {
      // v19d §2.4. The nav and the freshness strip are the two pieces of
      // chrome that cost a printed page a whole band at the top, and a print
      // rule is invisible in every screenshot gate — nothing but a rail
      // catches it going missing.
      const css = readFileSync(join(SRC, 'styles/theme.css'), 'utf8')
      const block = css.slice(css.indexOf('@media print'))
      expect(block).toMatch(/@media print/)
      expect(block).toMatch(/\bnav\b/)
      expect(block).toMatch(/freshness-strip/)
    })

  it('scopes every column header, by hand or through Th', () => {
    // A `<th>` with no `scope` leaves a screen reader to guess which cells
    // the header governs. `<Th>` emits it; the hand-written ones say it.
    // `<thead` is not a header cell, so the lookahead lets it past.
    expect(offenders(/<th(?![A-Za-z])(?!.*scope=)/)).toEqual([])
  })

  it('colours every chart from a token or the series palette', () => {
    // The shirt's two greys are part of the drawing (the hex rule's
    // allowance), so the shirt keeps its fill and stroke here too.
    const props = FILES.filter((path) => /\/(hubs|kit)\//.test(path))
      .filter((path) => !rel(path).endsWith('kit/PlayerCard.tsx'))
      .flatMap(colourProps)
    // The scan has to see the charts to vouch for them: recharts' series
    // props and the two ternaries the package named.
    expect(props.length).toBeGreaterThan(20)
    expect(props.some((p) => p.at.startsWith('hubs/League.tsx'))).toBe(true)
    expect(props.some((p) => p.at.startsWith('kit/Sparkline.tsx'))).toBe(true)
    expect(props.filter((p) => !colourValue(p.value)).map((p) => p.at))
      .toEqual([])
  })

  it('fails a colour prop that names neither a token nor the palette', () => {
    expect(colourValue('"#888"')).toBe(false)
    expect(colourValue("'#888'")).toBe(false)
    expect(colourValue("{'red'}")).toBe(false)
    expect(colourValue("{up ? 'var(--color-up)' : '#c33'}")).toBe(false)
    expect(colourValue("{a ? 'var(--color-up)' : b ? 'none' : 'none'}"))
      .toBe(false)
    expect(colourValue("{tone}")).toBe(false)
    expect(colourValue('"var(--color-text)"')).toBe(true)
    expect(colourValue('{SERIES_COLOURS[i % 4]}')).toBe(true)
    expect(colourValue("{rising ? 'var(--color-up)' : 'var(--color-down)'}"))
      .toBe(true)
  })
})

// Holiday F-88: the rail's patterns above name the retired classes, and
// Tailwind 4.1 scans every file under frontend/, so the tests would put those
// classes back in the bundle unless theme.css leaves them out of the scan.
describe("Tailwind's scan", () => {
  it('leaves the test files out, so their class literals stay out of the bundle', () => {
    const theme = readFileSync(join(SRC, 'styles/theme.css'), 'utf8')
    expect(theme).toContain('@source not "../**/*.test.ts";')
    expect(theme).toContain('@source not "../**/*.test.tsx";')
  })
})
