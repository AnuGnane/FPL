// @vitest-environment node
// v14 (spec §7): the design rules that can be pinned mechanically. Reads the
// sources rather than rendering anything, so a class that drifts back in is
// caught wherever it lands.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, posix, relative, sep } from 'node:path'
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
// left to be checked by hand. Holiday F-127: so did `main.tsx`, and the two
// files beside `src/` (`index.html`, `vitest.setup.ts`), which `rel` prints
// as `../index.html`; `styles/` holds only theme.css and its tests.
const FILES = [...walk(join(SRC, 'hubs')), ...walk(join(SRC, 'kit')),
  join(SRC, 'App.tsx'), ...walk(join(SRC, 'api')), join(SRC, 'main.tsx'),
  join(SRC, '..', 'index.html'), join(SRC, '..', 'vitest.setup.ts')]
const rel = (path: string) => relative(SRC, path)

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
  it('reads main.tsx, index.html and vitest.setup.ts, so a move out of the scan is seen', () => {
    const names = FILES.map(rel)
    for (const name of ['App.tsx', 'main.tsx', '../index.html', '../vitest.setup.ts']) {
      expect(names).toContain(name)
    }
    for (const path of FILES) expect(existsSync(path)).toBe(true)
  })

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

// Holiday F-142: the rules above forbid values, but nothing noticed a token
// nobody reads, so a retired colour could live on in theme.css (v14 R11, the
// names F-58 closed). Every `--color-<name>` the theme defines is read
// somewhere: as a custom property outside its own definition (`var()`, an
// arbitrary value) or as a whole Tailwind utility, so `accent` is not read by
// `accent-text`. theme.css joins the sources it searches here only, not
// FILES, because the ledger scans above allow its hex by name and would
// otherwise read its definitions as offences.
const THEME = join(SRC, 'styles/theme.css')
const UTILITY = 'bg|text|border|fill|stroke|ring|outline|decoration|divide|from|via|to|placeholder|caret|accent|shadow'

function deadTokens(theme: string, sources: string[]): string[] {
  const names = [...new Set([...theme.matchAll(/--color-([a-z0-9-]+)\s*:/g)].map((m) => m[1]))]
  const read = [theme, ...sources].map((text) => text.replace(/--color-[a-z0-9-]+\s*:/g, ''))
  return names.filter((name) => {
    const property = new RegExp(`--color-${name}(?![a-z0-9-])`)
    const utility = new RegExp(`(?<![a-z0-9-])(?:${UTILITY})-${name}(?![a-z0-9-])`)
    return !read.some((text) => property.test(text) || utility.test(text))
  })
}

describe('the theme tokens', () => {
  it('defines no colour token that nothing reads', () => {
    const sources = [...FILES, THEME].map((path) => readFileSync(path, 'utf8'))
    expect(deadTokens(sources.pop() as string, sources)).toEqual([])
  })

  it('names a token defined but never read, and a longer name does not stand in', () => {
    const theme = '@theme {\n  --color-accent: #000;\n  --color-accent-text: #fff;\n  --color-unused: #111;\n}\n'
    expect(deadTokens(theme, ['<p className="bg-accent-text text-accent-text">']))
      .toEqual(['accent', 'unused'])
    expect(deadTokens(theme, ['<p className="hover:bg-accent/50 text-accent-text">',
      "style={{ color: 'var(--color-unused)' }}"])).toEqual([])
  })
})

// Holiday F-144: F-142's question asked of `kit/` itself. An export nobody
// imports is a retired name living on (v14 R11), so every named export of a
// kit module that is not a test appears as a whole word in another file
// under `src/`. A test counts as a reader, since some exports are seams kept
// for one (`PLAIN_SHIRT`); `index.ts` re-exporting a name counts too.
function allSources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return allSources(path)
    return /\.tsx?$/.test(name) ? [path] : []
  })
}

function exportedNames(text: string): string[] {
  const declared = [...text.matchAll(
    /^export\s+(?:default\s+)?(?:declare\s+)?(?:abstract\s+)?(?:async\s+)?(?:const|let|var|function\*?|class|type|interface|enum)\s+([A-Za-z_$][\w$]*)/gm,
  )].map((m) => m[1])
  const listed = [...text.matchAll(/^export\s+(?:type\s+)?\{([^}]*)\}/gm)]
    .flatMap((m) => m[1].split(','))
    .map((entry) => entry.trim().replace(/^type\s+/, '').split(/\s+as\s+/).pop()?.trim() ?? '')
    .filter((name) => name !== '' && name !== 'default')
  return [...new Set([...declared, ...listed])]
}

function unreadExports(modules: Record<string, string>, others: Record<string, string>): string[] {
  const all = { ...others, ...modules }
  return Object.entries(modules).flatMap(([file, text]) => exportedNames(text)
    .filter((name) => {
      const word = new RegExp(`(?<![\\w$])${name.replace(/\$/g, '\\$')}(?![\\w$])`)
      return !Object.entries(all).some(([path, source]) => path !== file && word.test(source))
    })
    .map((name) => `${file}: ${name}`))
}

describe('the kit exports', () => {
  it('exports nothing that no other file reads', () => {
    const sources = Object.fromEntries(allSources(SRC).map((path) => [rel(path), readFileSync(path, 'utf8')]))
    const modules = Object.fromEntries(Object.entries(sources)
      .filter(([path]) => /^kit\/[^/]+\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path)))
    expect(unreadExports(modules, sources)).toEqual([])
  })

  it('names an export no other file reads, and a longer name does not stand in', () => {
    const modules = {
      'kit/Fake.tsx': "export const unusedThing = 1\nexport function used() {}\nconst a = 2\nexport { a as aliased }\nexport default function Fake() {}\n",
    }
    const others = { 'hubs/Page.tsx': "import Fake, { used, aliased } from '../kit/Fake'\nconst unusedThingy = 3\n" }
    expect(unreadExports(modules, others)).toEqual(['kit/Fake.tsx: unusedThing'])
    expect(unreadExports(modules, { ...others, 'kit/Fake.test.tsx': 'unusedThing()' })).toEqual([])
  })
})

// Holiday F-146: v18f gave the rung's `<tr onClick>` a `<button>` label
// because a click on a plain element is not reachable by Tab and announces
// nothing (v18f §2.2), and nothing stopped the next `<div onClick>`. Each
// `onClick=` belongs to the nearest preceding `<tag`; a lowercase tag that is
// not natively interactive carries `role=`, `tabIndex` and `onKeyDown` in its
// opening tag, or is a row or cell whose body holds a `<button` (RungRow's
// shape). A capitalised tag is a component, checked where it renders. A
// regex over source text, as the scans above are, not a parser.
const NATIVE = new Set(['button', 'a', 'input', 'select', 'textarea', 'summary', 'label', 'option'])
const ROWLIKE = new Set(['tr', 'td', 'li'])

function openingTag(text: string, start: number): string {
  let depth = 0
  for (let i = start; i < text.length; i++) {
    if (text[i] === '{') depth++
    else if (text[i] === '}') depth--
    else if (text[i] === '>' && depth === 0) return text.slice(start, i + 1)
  }
  return text.slice(start)
}

function keyboardless(file: string, text: string): string[] {
  return [...text.matchAll(/\bonClick=/g)].flatMap((click) => {
    const tags = [...text.slice(0, click.index).matchAll(/<([A-Za-z][\w.]*)/g)]
    const last = tags.at(-1)
    if (last === undefined) return []
    const [, tag] = last
    if (/^[A-Z]/.test(tag) || NATIVE.has(tag)) return []
    const start = last.index as number
    const open = openingTag(text, start)
    if (/\brole=/.test(open) && /\btabIndex\b/.test(open) && /\bonKeyDown\b/.test(open)) return []
    if (ROWLIKE.has(tag)) {
      const close = text.indexOf(`</${tag}>`, start)
      if (text.slice(start, close === -1 ? undefined : close).includes('<button')) return []
    }
    const line = text.slice(0, click.index).split('\n').length
    return [`${file}:${line} <${tag}>`]
  })
}

describe('the click targets', () => {
  it('gives every click a keyboard path', () => {
    const scanned = FILES.filter((path) => path.endsWith('.tsx') && !rel(path).startsWith('api/')
      && !rel(path).startsWith('../') && rel(path) !== 'main.tsx')
    expect(scanned.flatMap((path) => keyboardless(rel(path), readFileSync(path, 'utf8')))).toEqual([])
  })

  it('names a div with a click and no keyboard path, and passes the shapes that have one', () => {
    expect(keyboardless('hubs/Fake.tsx', 'const a = 1\n<div className="x" onClick={() => go()}>go</div>'))
      .toEqual(['hubs/Fake.tsx:2 <div>'])
    expect(keyboardless('hubs/Fake.tsx', [
      '<div role="button" tabIndex={0} onClick={() => go()} onKeyDown={(e) => e.key === "Enter" && go()}>go</div>',
      '<tr onClick={toggle}><td><button type="button" onClick={toggle}>x</button></td></tr>',
      '<button type="button" onClick={go}>go</button>',
      '<Button onClick={go}>go</Button>',
    ].join('\n'))).toEqual([])
  })
})

// Holiday F-156: no hub reads another hub's files. `CLAUDE.md`'s layout puts
// the shared pieces in `kit/` and `api/`, the Python side has its acyclic
// rail (`tests/test_layering.py`, v18d), and `ladderText.ts` exists so that
// "neither card should have to import the other" (v17h §3). The hub entries
// at `hubs/*.tsx` import their own directory and are not read; tests are not
// read. `ALLOWED` holds the crossings still standing, each with its reason,
// and can only shrink: an entry that no longer crosses fails too.
const ALLOWED_CROSSINGS: Record<string, string> = {
  'hubs/planning/WhatIfTab.tsx -> hubs/this-week/LadderCard':
    'LadderCard moves with RungRow and ladderText, in a package of its own',
}

function hubCrossings(sources: Record<string, string>): string[] {
  return Object.entries(sources).flatMap(([file, text]) => {
    const own = /^hubs\/([^/]+)\/.+\.tsx?$/.exec(file)
    if (!own || /\.test\.tsx?$/.test(file)) return []
    return text.split('\n').flatMap((line, i) => [
      ...line.matchAll(/(?:from\s+|import\s*\(\s*)'(\.{1,2}\/[^']*)'/g),
    ].flatMap((m) => {
      const target = posix.normalize(posix.join(posix.dirname(file), m[1]))
      const theirs = /^hubs\/([^/]+)\//.exec(target)
      return theirs && theirs[1] !== own[1]
        ? [`${file}:${i + 1} -> ${target}`] : []
    }))
  })
}

function unallowed(crossings: string[]): string[] {
  return crossings.filter((c) => !(c.replace(/:\d+ -> /, ' -> ')
    in ALLOWED_CROSSINGS))
}

describe('the hub boundaries', () => {
  const sources = () => Object.fromEntries(allSources(SRC)
    .map((path) => [rel(path).split(sep).join('/'),
                    readFileSync(path, 'utf8')]))

  it('lets no hub import another hub’s files', () => {
    expect(unallowed(hubCrossings(sources())),
           'file:line -> target crossing into another hub').toEqual([])
  })

  it('holds only crossings that still stand', () => {
    const standing = new Set(hubCrossings(sources())
      .map((c) => c.replace(/:\d+ -> /, ' -> ')))
    expect(Object.keys(ALLOWED_CROSSINGS).filter((k) => !standing.has(k)))
      .toEqual([])
  })

  it('names a crossing on a fake pair and passes its own directory and the entries', () => {
    expect(hubCrossings({
      'hubs/model/Fake.tsx': "import X from '../this-week/X'\n"
        + "import Y from './Y'\nimport { Card } from '../../kit'\n",
      'hubs/model/Fake.test.tsx': "import X from '../this-week/X'\n",
      'hubs/Model.tsx': "import Z from './this-week/Z'\n",
      'kit/Fake.tsx': "import X from '../hubs/this-week/X'\n",
    })).toEqual(['hubs/model/Fake.tsx:1 -> hubs/this-week/X'])
  })
})
