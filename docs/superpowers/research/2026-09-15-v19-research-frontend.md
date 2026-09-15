# v19 frontend research — UI/UX and functionality

Read: CLAUDE.md Frontend rules; GUIDE §5; v18f spec incl. "Left open"; v11 spec (no Outcome
section on disk); App.tsx, six hubs, kit/, api/, theme.css; four dark shots from
`.superpowers/shots/v18f-after/`.

## 1. Top 12 UI/UX findings

1. **No deadline countdown, and staleness hides the deadline.** `hubs/ThisWeek.tsx:180-182`
   — the context line is `deadline <toLocaleString>` *or* the staleness reason, never both,
   so in the shot the reader never learns when the deadline is. Always print a live "2d 4h
   to the GW5 deadline" plus the absolute time; leave staleness to the Callout at `:192`.
   **S. Pixels: yes (header line).**
2. **The board repeats a nine-line caveat per week column.** `planning/PlannerBoard.tsx:434-460`
   — three identical paragraphs, each taller than the plan above it (planning-board-dark.png).
   Hoist one copy under the column row, keeping the per-week button. **S. Pixels: yes.**
3. **This Week is one ~4,000px scroll with no wayfinding.** `hubs/ThisWeek.tsx:176-353` —
   eight stacked sections, no sticky context, nothing to jump with. Add a one-line sticky
   strip (GW · captain · moves · countdown) and section `id`s with an anchor row under the
   header. **M. Pixels: yes.**
4. **~35 hand-rolled tables have no phone layout.** Every `<table className={TABLE_CLASS}>`
   site (37; incl. `LadderCard.tsx:181`, `MovesCard.tsx:60`, `NewsPanel.tsx:56`,
   `WhyPanel.tsx:104,208`) gets only `overflow-x-auto`; the card mode in
   `kit/DataTable.tsx:104-166` is used by seven surfaces. Move This Week's four to
   `DataTable` or give `kit/table.ts` a stacked variant. **M. Pixels: no on desktop.**
5. **Seven items in the mobile tab bar, and no safe-area inset.** `kit/AppShell.tsx:45-68`
   — six hubs plus `ThemeToggle compact` at 11px across 375px, and a fixed `pb-16` ignoring
   `env(safe-area-inset-bottom)`. Move the theme control out of the bar and pad for the home
   indicator. **S. Pixels: mobile only.**
6. **`useIsMobile` is a hard 767px switch with no middle.** `kit/useMediaQuery.ts:26` and
   `AppShell.tsx:73` (`grid-cols-[200px_1fr]`). At 768–900px — landscape phone, iPad — the
   200px rail plus a wide table forces page-level horizontal scroll. Add an icon-only
   collapsed rail between `md` and `lg`. **M. Pixels: no at the gate's 1400px.**
7. **The main column is capped at 1180px whatever the screen.** `AppShell.tsx:88`
   (`max-w-[1180px] p-6`): on a 1440px+ laptop the 16-column Players table still scrolls
   sideways while 200px of viewport sits empty. Let wide tables opt out. **S. Pixels: >1400px.**
8. **No keyboard or landmark affordances beyond tab order.** No skip link in
   `frontend/index.html:20-23`, no id on `<main>` (`AppShell.tsx:88`), heading ladder jumps
   h1 (`kit/PageHeader.tsx:15`) to h3 (`kit/Card.tsx:42`). Add the skip link, `id="main"`,
   and a heading-level prop on `Card` defaulting to h2. **S. Pixels: no (focus-only link).**
9. **The "as of" strip is data you cannot act on.** `kit/FreshnessStrip.tsx:48-70` — five
   ages, no route from a rust cell to the job that fixes it. Link a stale cell to Model →
   Health and title it with the stamp. **S. Pixels: minimal.**
10. **The empty state names the action but is not the action.** `kit/EmptyState.tsx:25-32`
    prints the command as `<code>` unless `onAction` is given, and `ThisWeek.tsx:147-157`
    gives none — it renders the EmptyState and a *separate* JobButton below. Pass the
    button's start as `onAction`. **S. Pixels: cold tree only.**
11. **Explanatory prose outweighs the numbers.** `this-week/LadderCard.tsx:147-155` (five
    lines above the ladder every week), `PlannerBoard.tsx:221-248` (two paragraphs above the
    columns), plus finding 2. Keep the words; make them a "How to read this" disclosure,
    open on first visit, collapsed after. **S–M. Pixels: yes.**
12. **Live polls silently.** `hubs/Live.tsx:14,79-84` — 60s interval and an Auto-refresh
    checkbox, no stamp of the last successful poll and no manual refresh, so a stalled poll
    looks like a quiet gameweek. Add "updated 14:32 · Refresh". **S. Pixels: yes on Live.**

## 2. Functionality gaps

1. **Diff this week's advice against last week's** — `model/HistoryTab.tsx:48` lists past runs;
   nothing compares two. M.
2. **Act on a player from the squad** — `this-week/SquadTable.tsx`/`SquadPitch.tsx` offer no
   ban/lock/must-sell; the lab is reached only from `PlannerBoard.tsx:445` or by typing names
   into `planning/ConstraintsPanel.tsx:120`. M.
3. **"Why not him?"** — `this-week/WhyPanel.tsx` decomposes what you own, `players/ComparePanel.tsx`
   compares on request; nothing explains a highly-rated pool player the solver refused. L
   (needs a backend term).
4. **No global search or command palette** — search is local to `hubs/Players.tsx:129-135`. S–M.
5. **Nothing to take away** — no copy-the-moves, no print stylesheet, no link to
   `reports/gwN-report.html`. S.
6. **Pin/star only from Players** — `players/PinDialog.tsx` and the ☆ column are Explorer-only
   (`Players.tsx:78-118`); a news line on This Week cannot pin. S.
7. **The question box deferred at v16** (ROADMAP candidate 10) over the brief's facts
   document — `this-week/BriefCard.tsx`. L.
8. **No "what moved since I last looked"** — the freshness strip says how old, never what
   changed. M.

## 3. Code/design choices to revisit

1. `kit/PitchView.tsx` is exported at `kit/index.ts:24-25` and imported by nothing but its own
   test — This Week draws `this-week/SquadPitch.tsx`. Delete it or build SquadPitch on it.
2. `hubs/model/QualityTab.tsx` (546) is still the largest file after v18f's cut, with seven
   hand tables (`:54,165,196,267,361,394,436`); move the prop-taking sections out too.
3. `api/useJob.ts:238-254,261-288` — two mount-only effects, each with an `exhaustive-deps`
   disable and its own recovery path; fold into one effect keyed on a derived spec id.
4. The eight `set-state-in-effect` warnings recorded as a residual (v18f §3):
   `Players.tsx:74-76`, `PlannerBoard.tsx:82`, `api/pageData.ts:150-203`, plus SettingsTab,
   WhatIfSim, ExplainModal, DecisionPanel, Toast — mostly re-seed-from-payload, closed by a
   key-reset or `useSyncExternalStore`.
5. `hubs/Live.tsx:49-84` is the one read outside `usePageData`, hand-rolling data/error/status
   and the poll; give `usePageData` a `refreshMs` so the five-state contract is written once.
6. `types.ts` (308 lines, hand-written) still narrows generated shapes; audit the remainder
   against `types.generated.ts` — the drift check only guards the generated half.

## 4. What I would NOT change

- The ledger itself — hairline sections, one grey palette, tabular figures — reads well in both
  themes, and `kit/tokens.test.ts` is what keeps it honest.
- The caveat prose: collapse it, never cut it; it is what stops a number being misread.
- `api/pageData.ts`'s single-flight cache and `kit/Loaded.tsx`'s five states — v17h/v18e got
  these right; Live should join them, not replace them.

## 5. Numbers

Ten largest under `frontend/src` (non-test, non-generated), lines: QualityTab.tsx 546 ·
PlannerBoard.tsx 468 · League.tsx 426 · ComparePanel.tsx 399 · Players.tsx 379 ·
api/useJob.ts 359 · ReviewTab.tsx 357 · ThisWeek.tsx 355 · Live.tsx 351 · SeasonTab.tsx 323.
Total non-test source 14,169 lines; 114 test files. Vitest **1098 passed, 1 skipped** at the
last gate (v18f §3 / v18h); 1,028 literal `it(`/`test(` call sites.
`TODO`/`FIXME`/`eslint-disable`: **4 lines**, no TODO or FIXME anywhere — `types.banner.txt:1`
and `types.generated.ts:1` (generated banners), `api/useJob.ts:253,287` (mount-only, reason on
the line). Plus **8 ESLint warnings** (`react-hooks/set-state-in-effect`), zero errors.
