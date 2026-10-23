// @vitest-environment node
// Read as a plain file: under the default jsdom environment `import.meta.url`
// is an http:// URL and readFileSync cannot resolve it.
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Holiday F-211: `npm run check` runs eslint with `--max-warnings 0` (holiday
// F-74), so a rule set to `warn` fails the check exactly as `error` does, and
// the config would be saying something about the check that is not true. The
// v18f `set-state-in-effect` override was the last; v19h fixed its sites.
const config = readFileSync(new URL('../eslint.config.js', import.meta.url), 'utf8')

describe('eslint.config.js', () => {
  it('sets no rule to warn, since --max-warnings 0 makes a warning fail the check', () => {
    const warns = config.match(/['"]warn['"]/g) ?? []
    expect(
      warns,
      'a rule is set to warn, but `npm run check` runs eslint with --max-warnings 0, ' +
        'so the warning fails the check: set it to error or remove it',
    ).toEqual([])
  })
})
