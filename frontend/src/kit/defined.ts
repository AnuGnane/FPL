/**
 * Holiday F-220 — the test files' narrowing for a value a query or an index
 * read may not have found.
 *
 * typescript-eslint's `strict` set forbids the `!` assertion, which told the
 * compiler a value was there without checking. `defined` checks: a missing
 * value fails the test here, naming what was looked for, rather than as a
 * `TypeError` on the next line.
 */
export function defined<T>(value: T | null | undefined, what: string): T {
  if (value === null || value === undefined) throw new Error(`expected ${what} to be defined`)
  return value
}
