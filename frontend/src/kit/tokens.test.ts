// @vitest-environment node
// v14 (spec §7): the design rules that can be pinned mechanically. Reads the
// sources rather than rendering anything, so a class that drifts back in is
// caught wherever it lands.
import { readFileSync, readdirSync, statSync } from 'node:fs'
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
    expect(offenders(/font-mono/, ['kit/JobLog.tsx',
      'hubs/planning/PlannerBoard.tsx'])).toEqual([])
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

  it('composes Chip, not Badge, everywhere but the alias itself', () => {
    expect(offenders(/<Badge\b|\bBadge,|\{ Badge\b/, ['kit/Badge.tsx',
      'kit/index.ts'])).toEqual([])
  })

  it('draws fixture difficulty as a tone, never a ramp', () => {
    expect(offenders(/difficultyBackground/)).toEqual([])
  })
})
