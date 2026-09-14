import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

/**
 * v18f §2.2. The recommended sets and nothing invented on top of them: the
 * house rules that can be checked mechanically already live in
 * `kit/tokens.test.ts`, and a second opinion about style here would be a
 * second place to argue with.
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
  reactHooks.configs.flat.recommended,
  {
    rules: {
      // `set-state-in-effect` is one of the React Compiler rules that
      // `eslint-plugin-react-hooks` v7 folded into its recommended set, and
      // eight effects in this tree trip it: the reset-on-prop-change in
      // `ExplainModal` and `DecisionPanel`, the re-seed-from-payload in
      // `Players`, `WhatIfSim`, `SettingsTab` and `PlannerBoard`, and the
      // subscribe-then-resync in `Toast` and `api/pageData`. Each is a real
      // question about how that component syncs, and each answer is a
      // behaviour change on a page under the screenshot gate — so they are
      // recorded as warnings and left to the cycle that means to work on
      // them, rather than silenced or rewritten in passing (v18f §2.2).
      'react-hooks/set-state-in-effect': 'warn',
    },
    languageOptions: {
      // The app is a browser page; the scripts beside it (`scripts/`, this
      // file, the vite and vitest configs) are node.
      globals: { ...globals.browser, ...globals.node },
    },
  },
)
