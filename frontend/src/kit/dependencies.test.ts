// @vitest-environment node
// Holiday F-183: `package.json` and the sources agree both ways, as F-182
// holds `pyproject.toml` to the Python imports. Every dependency and
// devDependency is named somewhere a tool reads it, and every bare specifier
// the sources import is declared. Reads the files, renders nothing.
//
// "Named" is wider than an import. A `types` entry (tsconfig's list, a
// `/// <reference types>`) names its package or its `@types/` twin, a
// vitest environment names its package (`jsdom`), and a command an npm
// script runs names the package whose `bin` the lock records for it (`tsc`
// is typescript, `eslint` is eslint).
import { builtinModules } from 'node:module'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const ROOT = fileURLToPath(new URL('../..', import.meta.url))
const read = (path: string) => readFileSync(join(ROOT, path), 'utf8')

const PKG = JSON.parse(read('package.json')) as {
  dependencies: Record<string, string>
  devDependencies: Record<string, string>
  scripts: Record<string, string>
}
const LOCK = JSON.parse(read('package-lock.json')) as {
  packages: Record<string, { bin?: Record<string, string> }>
}
const DECLARED = [...Object.keys(PKG.dependencies), ...Object.keys(PKG.devDependencies)]

// Declared, named by no file: the typings tsc loads by convention for the
// packages they type. Value: why it is declared.
const TYPINGS: Record<string, string> = {
  '@types/react': "react's types, which react 18 does not ship",
  '@types/react-dom': "react-dom's types, which react-dom 18 does not ship",
}

function walk(dir: string): string[] {
  return readdirSync(join(ROOT, dir)).flatMap((name) => {
    const path = `${dir}/${name}`
    if (statSync(join(ROOT, path)).isDirectory()) return walk(path)
    return /\.tsx?$/.test(name) ? [path] : []
  })
}

const FILES = [
  ...walk('src'),
  ...readdirSync(join(ROOT, 'scripts')).filter((n) => n.endsWith('.ts')).map((n) => `scripts/${n}`),
  'vite.config.ts', 'eslint.config.js', 'vitest.setup.ts',
  ...readdirSync(ROOT).filter((n) => /^tsconfig.*\.json$/.test(n)),
  'src/styles/theme.css', 'index.html',
].filter((path) => existsSync(join(ROOT, path)))

// A specifier cut to its package: scope and name, no subpath.
function packageOf(spec: string): string {
  const parts = spec.split('/')
  return spec.startsWith('@') ? parts.slice(0, 2).join('/') : parts[0]
}

const isBare = (spec: string) => !/^[./]/.test(spec) && !/^[a-z]+:\/\//.test(spec)
const isBuiltin = (spec: string) => spec.startsWith('node:') || builtinModules.includes(packageOf(spec))

const IMPORT_PATTERNS = [
  /^\s*(?:import|export|\})[^'"\n]*\sfrom\s+['"]([^'"]+)['"]/gm, // a from clause, one line or the close of many
  /^\s*import\s+['"]([^'"]+)['"]/gm, // a side-effect import
  /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g, // a dynamic import
  /^\s*@import\s+['"]([^'"]+)['"]/gm, // theme.css's import
]

function matches(text: string, patterns: RegExp[]): string[] {
  return patterns.flatMap((re) => [...text.matchAll(re)].map((m) => m[1]))
}

// Every bare specifier imported, with the files that import it.
function imported(): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const path of FILES) {
    for (const spec of matches(read(path), IMPORT_PATTERNS)) {
      if (!isBare(spec) || isBuiltin(spec)) continue
      const pkg = packageOf(spec)
      found.set(pkg, [...new Set([...(found.get(pkg) ?? []), path])])
    }
  }
  return found
}

function typesEntries(): string[] {
  const refs = FILES.flatMap((path) => matches(read(path), [/\/\/\/\s*<reference\s+types="([^"]+)"/g]))
  const lists = FILES.filter((path) => path.endsWith('.json')).flatMap((path) => {
    const list = (JSON.parse(read(path)) as { compilerOptions?: { types?: string[] } })
      .compilerOptions?.types
    return list ?? []
  })
  return [...refs, ...lists]
}

function environments(): string[] {
  return FILES.flatMap((path) => matches(read(path), [
    /\benvironment:\s*['"]([^'"]+)['"]/g, // vitest's config
    /@vitest-environment\s+(\S+)/g, // a file's own
  ]))
}

// The package each npm script command runs, by the `bin` the lock records.
function scriptBins(): string[] {
  const bins = new Map<string, string>()
  for (const [path, entry] of Object.entries(LOCK.packages)) {
    if (!path.startsWith('node_modules/') || path.slice(13).includes('node_modules/')) continue
    for (const bin of Object.keys(entry.bin ?? {})) bins.set(bin, path.slice(13))
  }
  const words = Object.values(PKG.scripts).flatMap((cmd) => cmd.split(/\s*(?:&&|\|\||;)\s*/))
    .map((cmd) => cmd.trim().split(/\s+/)[0])
  return words.flatMap((word) => (bins.has(word) ? [bins.get(word)!] : []))
}

function named(): Set<string> {
  const types = typesEntries().map(packageOf).flatMap((pkg) => [pkg, `@types/${pkg}`])
  return new Set([...imported().keys(), ...types, ...environments().map(packageOf), ...scriptBins()])
}

describe('package.json and the sources agree both ways (holiday F-183)', () => {
  it('names every dependency somewhere or holds it in TYPINGS', () => {
    const seen = named()
    expect(DECLARED.filter((pkg) => !seen.has(pkg) && !(pkg in TYPINGS))).toEqual([])
  })

  it('declares every bare specifier that is not a node builtin', () => {
    const stray = [...imported()].filter(([pkg]) => !DECLARED.includes(pkg))
    expect(stray).toEqual([])
  })

  it('holds TYPINGS to declared packages that nothing names', () => {
    const seen = named()
    expect(Object.keys(TYPINGS).filter((pkg) => !DECLARED.includes(pkg) || seen.has(pkg))).toEqual([])
  })

  it('reads the scan wide enough to find the packages it must', () => {
    const seen = named()
    for (const pkg of ['react', 'tailwindcss', '@tailwindcss/vite', 'typescript', 'jsdom', '@types/node']) {
      expect(seen.has(pkg), pkg).toBe(true)
    }
  })

  it('cuts a specifier to its package', () => {
    expect(packageOf('@testing-library/jest-dom/vitest')).toBe('@testing-library/jest-dom')
    expect(packageOf('react-dom/client')).toBe('react-dom')
    expect(packageOf('vitest/globals')).toBe('vitest')
    expect(isBuiltin('node:fs')).toBe(true)
    expect(isBuiltin('fs')).toBe(true)
    expect(isBuiltin('react')).toBe(false)
  })
})
