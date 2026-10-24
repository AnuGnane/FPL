import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

/**
 * v18f §2.2. The recommended sets and nothing invented on top of them: the
 * house rules that can be checked mechanically already live in
 * `kit/tokens.test.ts`, and a second opinion about style here would be a
 * second place to argue with. `strict` (holiday F-220) is typescript-eslint's
 * own shipped set, the recommended set's stricter sibling, not a rule invented
 * here.
 *
 * `npm run check` runs this last, after `tsc`, `vitest` and the type
 * generator's own drift check.
 */
export default tseslint.config(
  {
    // The build output, the bundle the Python package serves, and the file
    // the generator writes — none of them hand-edited, all of them linted by
    // whoever wrote the tool that emits them.
    ignores: ['dist', '../src/gaffer/web/static', 'src/types.generated.ts'],
  },
  js.configs.recommended,
  tseslint.configs.recommended,
  tseslint.configs.strict,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: {
      // The app is a browser page; the scripts beside it (`scripts/`, this
      // file, the vite and vitest configs) are node.
      globals: { ...globals.browser, ...globals.node },
    },
  },
)
