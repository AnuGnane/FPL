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

const FILES = [...walk(join(SRC, 'hubs')), ...walk(join(SRC, 'kit'))]
const rel = (path: string) => path.slice(SRC.length)

function offenders(pattern: RegExp, allow: string[] = []): string[] {
  return FILES
    .filter((path) => !allow.some((a) => rel(path).endsWith(a)))
    .flatMap((path) => readFileSync(path, 'utf8').split('\n')
      .map((line, i) => (pattern.test(line) ? `${rel(path)}:${i + 1}` : null))
      .filter((hit): hit is string => hit !== null))
}

describe('the ledger rules (spec §3–§5)', () => {
  it('has no rounded-full, no card radius, no shadow, no gradient', () => {
    expect(offenders(/rounded-full|rounded-card|shadow-|gradient/)).toEqual([])
  })

  it('has no raw hex outside theme.css and the bundled plain shirt', () => {
    // The plain shirt is an inline SVG data URI whose two greys are part of
    // the drawing, not of the palette.
    expect(offenders(/#[0-9a-fA-F]{6}\b/, ['kit/PlayerCard.tsx'])).toEqual([])
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
})
