/**
 * The wire types, one command (v17a §3).
 *
 * `npm run types` writes `src/schemas.json` through `scripts/gen_types.py`
 * (the Python half) and then `src/types.generated.ts` from it (this half),
 * both from `src/gaffer/web/schemas.py`; the last two paths are from the repo
 * root, the first two from `frontend/`.
 * `npm run types -- --check` writes nothing and exits 1 naming every file
 * that drifted. `src/types.generated.test.ts` imports `render`, so the suite
 * diffs exactly what this writes and no option is restated there.
 *
 * Node runs this file as written (type stripping, unflagged since 22.18), so
 * only erasable syntax here: no enum, no namespace, no parameter properties.
 * The interpreter is the repo's `.venv/bin/python` and nothing else: a
 * system python3 without `gaffer` importable writes a stack trace, not a
 * schema.
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { compile, type JSONSchema } from 'json-schema-to-typescript'

/** The only definition of the compile options in the tree. */
export const OPTIONS = {
  bannerComment: '',
  additionalProperties: false,
  unreachableDefinitions: true,
  declareExternallyReferenced: true,
  style: { singleQuote: true, semi: false },
} as const

const FRONTEND = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const ROOT = resolve(FRONTEND, '..')
const SCHEMA = join(FRONTEND, 'src', 'schemas.json')
const BANNER = join(FRONTEND, 'src', 'types.banner.txt')
const TARGET = join(FRONTEND, 'src', 'types.generated.ts')
const PYTHON = join(ROOT, '.venv', 'bin', 'python')
const PY_SCRIPT = join(ROOT, 'scripts', 'gen_types.py')

const STALE = (path: string) => `${path} is stale — run \`npm run types\``
const rel = (path: string) => relative(ROOT, path)

/** The banner, then the schema compiled with `OPTIONS`. Pure. */
export async function render(schema: JSONSchema, banner: string): Promise<string> {
  return banner + await compile(schema, 'GafferApi', OPTIONS)
}

/** Runs the Python half with the flag forwarded; its exit status. */
function pythonHalf(check: boolean): number {
  if (!existsSync(PYTHON)) {
    console.error(`no interpreter at ${rel(PYTHON)}; create the venv first`)
    return 2
  }
  const args = check ? [PY_SCRIPT, '--check'] : [PY_SCRIPT]
  const run = spawnSync(PYTHON, args, { cwd: ROOT, stdio: 'inherit' })
  return run.status ?? 2
}

/** Writes `types.generated.ts`, or in check mode compares it; exit status. */
async function typesHalf(check: boolean): Promise<number> {
  const schema = JSON.parse(readFileSync(SCHEMA, 'utf8')) as JSONSchema
  const fresh = await render(schema, readFileSync(BANNER, 'utf8'))
  if (!check) {
    writeFileSync(TARGET, fresh)
    console.log(`wrote ${rel(TARGET)}`)
    return 0
  }
  const committed = existsSync(TARGET) ? readFileSync(TARGET, 'utf8') : ''
  if (committed === fresh) return 0
  console.log(STALE(rel(TARGET)))
  return 1
}

export async function main(argv: string[]): Promise<number> {
  const check = argv.length === 1 && argv[0] === '--check'
  if (argv.length > 0 && !check) {
    console.error('usage: npm run types [-- --check]')
    return 2
  }
  const py = pythonHalf(check)
  // In check mode a drifted schema (1) is reported and the check goes on to
  // the TypeScript file, so one run names every stale file. Anything else
  // non-zero (a missing venv, a usage error) stops here; compiling a schema
  // the Python half did not just write would report on the wrong file. In
  // check mode a traceback also exits 1 and reads as drift; the trace is
  // already on the terminal and the run exits 1 either way.
  if (py !== 0 && !(check && py === 1)) return py
  const ts = await typesHalf(check)
  return py || ts
}

// Only when this file is the entry point. Under vitest `process.argv[1]` is
// the worker, so importing `render` in a test runs nothing. realpathSync, not
// resolve: Node realpaths the main module, so under a symlinked checkout a
// plain resolve never matches and the check would pass vacuously (v17a code
// review). existsSync first: realpathSync throws on a path that is not
// there, and a runner whose argv[1] is not a file must skip `main`, not fail
// the import.
if (process.argv[1] && existsSync(process.argv[1])
    && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await main(process.argv.slice(2))
}
