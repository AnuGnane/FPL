# v18f — the surface, correct to the hand

**Cycle:** v18f, the sixth sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18f;
design `specs/2026-09-12-v18-polish-design.md` v18f; the review's §2,
bullets four to seven; `CLAUDE.md` Frontend rules; the tracker's v18e
note). **Branch:** `v18f-surface` off `main` at `1d558ba`. **Date:**
2026-09-14. **Plan:** four tasks, the cuts first (pure moves, so the
screenshots and the fetch rails have nothing to say about them), then the
hand-and-eye pass, then the job test, the token rules landing with the
change that makes each true.

## 1. Gate, stated before anything runs

Five parts, all five or no merge.

1. **Twelve screenshot pairs byte-identical against a same-time control.**
   `frontend/scripts/shots.sh v18f-before` from a `main` worktree
   (`PYTHONPATH=<worktree>/src`, its own `npm run build`) shot minutes
   before `v18f-after` on the branch (v18e's lesson: an earlier control
   differs by the clock). The two dialogs are not on a first paint, so the
   Radix swap is invisible here by construction; the lazy routes must be
   too (the fallback must not be in the shot — the script's virtual-time
   budget is 15 s). Approved by the orchestrator in the user's absence,
   images kept.
2. **`kit/tokens.test.ts` extended, each new rule mutation-tested live by
   the orchestrator:** no `text-white`, no `bg-black`, no `Badge` export
   from `kit/index.ts` and no `kit/Badge.tsx`, every `<th` in `kit/` and
   `hubs/` carries `scope=` (or comes from `<Th>`, which emits it). A rule
   whose planted fault does not fail the suite is not a rule.
3. **`npm run check` green** — `tsc --noEmit && vitest run && npm run
   types -- --check && eslint .` — with **zero ESLint errors** under
   `eslint.config.js` (`@eslint/js` recommended, `typescript-eslint`
   recommended, `eslint-plugin-react-hooks`); the five
   `eslint-disable` comments each fixed or carrying its reason on the line
   (`types.generated.ts` and `types.banner.txt` are generated and keep
   theirs).
4. **The suite not smaller, and the job test fast.** `vitest run` ≥ 1058
   passed with the moved tests counted; `api/useJob.test.tsx` under 2 s on
   `vi.useFakeTimers`, with a `console.error` spy asserting no `act(...)`
   warning. Read vitest's `Errors  N error` line as a failure.
5. **The first-paint chunk carries no recharts.** After `npm run build`,
   the entry chunk `src/gaffer/web/static/assets/index-*.js` does not
   contain the string `recharts` (it is imported by League, Live, four
   Model tabs and two Players panels, never by This Week — so `React.lazy`
   per hub puts it in their chunks). A documented check, pasted into §3,
   not a test.

Alongside: the six fetch rails and the twelve-pair rule mean no hub asks
for anything new; Python untouched (no backend change; routes 51).

## 2. What the cycle must know

### 2.1 The cuts (task 1 and 2, pure moves)

Each cut is a pure function with its own table test, or a sub-component
with its tests moved beside it; the parent's own test count may fall as
the moved tests are counted in the new file. Nothing visible changes.

- `hubs/model/QualityTab.tsx` (1060 lines): the four self-fetching sections
  — `CalibrationSection`, `PensSection`, `ScatterSection` (+`ScatterBody`,
  `scatterPoints`), `MissesSection` — each to `hubs/model/quality/<Name>.tsx`
  with the helpers only it uses (`StratifiedTableView`, `Reliability`,
  `brierCell` go with calibration; `InstrumentCell` with pens); `QualityTab`
  keeps the layout and the sections that take props.
- `hubs/planning/ChipsTab.tsx` (519): `ChipOutlook` (+`teamLabel`,
  `ThetaTrack`) to `hubs/planning/ChipOutlook.tsx`; the `solve()` at
  ~184-200 that duplicates `WhatIfTab.tsx:42` becomes one
  `hubs/planning/useWhatIfSubmit.ts` both tabs call.
- `hubs/planning/PlannerBoard.tsx` (514): the request the board sends
  (`boardRequest`, a pure function of the board's state → the POST body)
  to `hubs/planning/boardRequest.ts` with a table test; the move-row
  markup written twice becomes one `TraceMoves` component in
  `hubs/planning/TraceMoves.tsx`.
- `hubs/League.tsx` (483): `MarginFan` (pure SVG) to
  `hubs/league/MarginFan.tsx`; the "POST `/api/settings` then invalidate"
  written in `League.tsx:141-158`, `LadderCard.tsx:210-224` and
  `SettingsTab.tsx:145` becomes one `api/useSettingWrite.ts` (`write(key,
  value)` → the POST, the toast, and the invalidations the table names for
  that caller — the table rows in `api/invalidation.test.tsx` move with the
  calls, or the hook takes the extra URLs as an argument so each row stays
  where the writer is).
- `hubs/players/ComparePanel.tsx` (451): `compareRows` (the rows the panel
  derives from the two players' components) to
  `hubs/players/compareRows.ts` with a table test.
- `hubs/this-week/LadderCard.tsx` (411): the rung row (`<tr>` at ~326 and
  its `Expanded` sibling) to `hubs/this-week/RungRow.tsx`.

### 2.2 Hand and eye (task 3)

- **Dialogs.** `kit/ExplainModal.tsx` and `hubs/players/PinDialog.tsx` on
  `@radix-ui/react-dialog` (`Root`, `Portal`, `Overlay`, `Content`,
  `Title`, `Close`): focus trap and return, `Escape`, the overlay click,
  `inert` background — Radix's, not the hand-rolled `useEffect`s. The
  overlay keeps its look through a new token, `--color-scrim`, replacing
  `bg-black/70`; `Button`'s primary text through `--color-on-accent`,
  replacing `text-white` (`styles/theme.css` gains the two; no other
  colour). `ExplainModal` keeps `usePageData(open ? path : null)` (v18e).
  `@radix-ui/react-tooltip`, imported nowhere, is removed from
  `package.json`.
- **Tables.** `kit/table.ts` gains `<Th>` (emits `scope="col"`, takes
  `numeric`, and `sort?: 'ascending' | 'descending' | 'none'` → `aria-sort`
  with the glyph `aria-hidden`); `kit/DataTable.tsx` uses it; every hand
  `<th>` under `hubs/` and `kit/` goes through it or carries `scope`.
- **The rung toggle.** `LadderCard`'s `<tr onClick>` (now `RungRow`)
  becomes a `<button aria-expanded>` in its first cell with the row's
  click preserved for the mouse; keyboard opens it.
- **Text equivalents.** `FixtureMatrix`'s chip carries the difficulty as
  text for a screen reader (`aria-label` or visually-hidden text: "easy",
  "medium", "hard" from the same tone map); `SquadTable`'s tone-only chips
  (`up`/`down`/`warn`) the same.
- **Hygiene.** `kit/Badge.tsx`, its test and its export deleted (its one
  importer, if any, moves to `Chip`); `types.ts`'s `ChipSquadPlayer` and
  `AdvicePlayerRef` replaced by the generated `SquadPlayerRef` and the
  generated ref they duplicate, and `HealthData`'s narrowing given its
  written reason or removed; the ten non-null assertions narrowed once
  above the JSX (`const summary = data.summary; if (summary === null)
  return …`).
- **Lazy routes.** `React.lazy` per hub in `App.tsx` inside a `Suspense`
  with the kit's `Loading` fallback, under the `ErrorBoundary` (v18e).
- **ESLint and `check`.** `eslint.config.js` (flat), `npm run check`, and
  `npm run lint`; the five disables: `ThisWeek.tsx:92` and `useJob.ts:250,
  283` each fixed (a stable callback, or the dependency named) or the
  reason kept on the line.

### 2.3 The job test (task 4)

`api/useJob.test.tsx` on `vi.useFakeTimers()` with `vi.advanceTimersByTime`
in `act`, the two 4 s `waitFor`s gone; a `console.error` spy in
`beforeEach` asserting no call whose first argument matches `act(`.

### 2.4 What does not change

No backend file. No number, sentence, colour or layout on any hub's happy
path (part 1). No route, no fetch (the six rails). `Chip`'s tones stay
four; the two new tokens are the only additions to `theme.css`.

## 3. Outcome

_(filled at the gate)_
