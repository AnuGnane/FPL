# Final review — gaffer after v17, 2026-09-12

Read-only audit of `main` at `5a01f29` (tree clean, in sync with
`origin/main`), three days after the v17 deepening programme closed. Four
parallel read-only audits (backend, frontend, suite and tooling, docs) fed
this document; every headline claim below was re-verified by hand before it
was written down. Nothing was modified. `config.toml` was not opened.

The question this answers: **what is still weak, and what would a final
polish cycle do?** The design that follows from it is
`docs/superpowers/specs/2026-09-12-v18-polish-design.md`.

## Executive summary

1. **The engineering is in good shape and the v17 programme did what it
   said.** Both suites are green (Python 4420 passed / 5 skipped in 10:50;
   frontend 986 passed / 1 skipped in 15 s; `tsc` clean). The three pins
   verify (routes 51, `JOB_KINDS` 12, `Config` 62). All nine launchd jobs
   are loaded and the nightly backup has run every night since 2026-09-08.
   `run_advise` is a 31-line composition of two halves, the served plan is
   one value, and This Week reads its data once.
2. **The gate the whole programme rests on is currently off.** The golden
   board's five live-model tests skip because the 2026-09-11 launchd retrain
   moved every `models/*.meta.json` (§1.1). A green full run today does not
   include the board-level parity check, and the skip is silent unless
   `-rs` is passed. Nothing merged since 09-11 was gated on it; nothing was
   merged since 09-11, so nothing is lost, but the next refactor would be.
3. **Two faults hide in the advice path.** `build_advice` still wraps the
   ladder in the exact `except Exception` v17g named as its lesson
   (`advise.py:1278`), and the MILP falls from HiGHS to CBC on any exception
   without recording it (`optimize/milp.py:977`). A `NameError` sits in
   `calibrate_noise.ensemble_rows` (`calibrate_noise.py:443`) that no test
   reaches because the only tests stub the function out.
4. **`build_advice` is pure in name.** Three config reads still happen
   behind `cfg`'s back on the build path, and both `advise.py` and
   `ladder.py` import fixture difficulty from `gaffer.web.identity`, which
   calls a FastAPI route handler through an mtime-keyed web cache (§1.3).
5. **Measurement that has never run.** The calibration report still
   hard-codes last season (`cli.py:687`), so `reports/evaluation.json`
   has said "no graded gameweeks" since 2026-09-01 while the ledger holds
   three graded weeks. `reports/health.json`'s two nulls are structural. The
   pre-blend `e_goals` is not banked, so every evaluation reading the
   components artifact carries the odds-cap artifact the 09-04 review
   measured.
6. **The frontend's loader conversion stopped at one hub.** Twelve files use
   `usePageData`; roughly seventy raw client reads remain, several URLs are
   read through both paths, and eight components render a server error as a
   healthy empty state (§2).
7. **There is no linter anywhere.** Ruff reports 769 findings (575
   auto-fixable) including the `NameError` above and 16 loop-variable
   closures; ESLint is not installed although five `eslint-disable` comments
   assume it runs.
8. **The docs have drifted in about thirty places,** including three
   statements in `CLAUDE.md` that agents obey every cycle: the CLI `advise`
   *does* chain the brief since v17d, the v16 rail no longer holds source
   pins, and the layout omits the four modules v17 created.

Nothing in this list changes a number the advice serves. That is the
property a polish cycle should keep, and the design keeps it.

## 0. State

| Surface | Reading (2026-09-12) |
|---|---|
| `main` | `5a01f29`, clean, `origin/main` identical |
| Python suite | 4420 passed, 5 skipped, 12,844 warnings, 10 min 50 s |
| Frontend suite | 986 passed, 1 skipped, 14.6 s; `tsc --noEmit` clean; one `act(...)` warning from `api/useJob.test.tsx` |
| Pins | routes 51 (`tests/test_v11_degradation.py:369`), `JOB_KINDS` 12, `Config` 62 (`tests/test_v13_degradation.py:37`) |
| launchd | 9 of 9 `com.gaffer` jobs loaded, all last exit 0; installed plists differ from `scripts/` only by the `__PROJECT_DIR__` substitution |
| Backups | `~/gaffer-backups/` has one ~7 MB tarball per night since 2026-09-08 |
| Reports | GW4 advice, ladder, brief and report written 2026-09-11 13:35; brief note 09-12 10:51 |
| Ledger | GW1–3 graded; GW3 carries `overall_rank` and a `projection_snapshot` |
| Calibration | `reports/evaluation.json` calibration block dated 2026-09-01, `season: 2025-26`, `gameweeks: []` |
| Logs | zero `error`/`traceback` lines in any job log (the only hits are in v9c/v16 cycle logs) |
| Branches | 26 local and 5 remote feature branches, all fully merged into `main` |
| Disk | `data/raw` 181 MB of API snapshots; `reports/projections/` 14 files; neither pruned by `tidy` |

## 1. Backend

### 1.1 The golden gate is off

`tests/test_golden_board.py:264,271,278,285` and `tests/test_pipeline.py:259`
skip with *"golden board recorded under a different
`models/attacking.meta.json` (8 input(s) differ); re-record with `python -m
tests.golden_client --write`"*. The board was re-recorded on 2026-09-08
(`77d1d59`); the Thursday retrain on 09-11 rewrote every model. The v17c
hand-off note says a skip "means the inputs moved, not that the refactor is
fine". Only the v17g seam-level half (recorded `Inputs`, no models) still
runs. The documented gate command does not pass `-rs`, so the skip prints as
`5 skipped` and nothing names the cause.

Two related fragilities the hand-off notes recorded, now diagnosed:

- `tests/test_pipeline.py` fails alone with `'list' object has no attribute
  'drop'` because `_wire()` (`:21`) patches
  `gaffer.models.train.load_training_frame` and then, at `:26`, imports
  `gaffer.advise` for the first time *while the patch is live*, so
  `advise.py:73`'s `from gaffer.models.train import load_training_frame`
  binds the stub for the rest of the process. One `import gaffer.advise`
  before the first `setattr` fixes it.
- The golden-skip helper is written twice (`test_pipeline.py:248-262`,
  `test_golden_board.py:245-256`) with a third wording at
  `test_golden_board.py:230,310,324,500`.

### 1.2 Faults on the advice path

- **The ladder swallow.** `advise.py:1278` `except Exception` around the
  whole `ladder_payload(...)` call; the comment (`:1279-1285`) says a
  miswired call "would look" like a bench swap and leans on the golden board
  to notice — which is off (§1.1). The fix is to catch the domain error and
  let programming errors raise.
- **The silent solver switch.** `optimize/milp.py:977` `except Exception:
  pass` then `PULP_CBC_CMD`. A solver change changes numbers; nothing in the
  solve state records which solver produced them.
- **The `NameError`.** `calibrate_noise.py:443` evaluates
  `attacking_features()` as a `getattr` default; the name is imported only
  inside a *different* function (`:375`), not in `ensemble_rows`' own import
  block (`:421-423`). `gaffer calibrate-noise` would crash on the first
  bundle whose model lacks `feature_cols`. The two tests that reach the
  function stub it (`tests/test_estimation_noise.py:242,266`).
- **Clock reads inside the pure cores.** `advise.py:1232` `datetime.now()`
  in `build_advice`; `ladder.py:815,955,966` `perf_counter`/`now()` in
  `ladder_payload`. The golden strips `generated_at` but does not pin
  `reports/ladder_gwN.json` at all (`tests/data/golden_board/expected/`
  holds advice, plan and solve_state), so the rung table has no byte gate.

### 1.3 The build path is not yet pure

- **Config behind `cfg`'s back**, on the path `build_advice` documents as
  pure: `served.py:386` (`price_falls`, reached from `gather_inputs` at
  `advise.py:822`), `models/availability.py:115`, `artifacts.py:551`,
  `price_timing.py:169`, `ladder.py:449,767,991`, `models/train.py:586`.
  v17c's note asked v17e to collapse these; v17e collapsed the *readers* to
  one cached view but the build path still consults the view rather than
  its `cfg`.
- **Core imports web.** `advise.py:828` and `ladder.py:232` import
  `_difficulty_by_team` from `gaffer.web.identity`, which calls the
  `meta.ticker` route handler (`web/identity.py:305-308`,
  `web/routers/meta.py:403-417`) through the identity module's mtime-keyed
  `_CACHE` (`web/identity.py:50`). `brief.py:106` imports the `plan` route
  handler for the timeline. A router change can move advice.
- **Lazy imports that exist only to dodge cycles** (hoisting any creates a
  top-level cycle): `inputs.py:126,134` → `advise` (the seam importing the
  pipeline it feeds; `predict_components` at `advise.py:415-500` is model
  code living in the orchestrator), `snapshot.py:151`, `config.py:675` →
  `price_timing` (config depending on a feature), `served.py:383`,
  `artifacts.py:550`, `optimize/chip_policy.py:183,200`,
  `models/dnp_calibrate.py:133`. Private reaches across modules:
  `live_gw.py:184` and `review.py:628` → `backtest._formation_legal`,
  `data/understat.py:573` → `match_odds._code_for`, `backtest.py:58` →
  `advise._cap`.

### 1.4 The web layer

- **Job bodies and business logic in routers.** `web/routers/meta.py:458-493`
  is the `refresh-data` job body, imported by `web/job_kinds.py:23`;
  `web/routers/drafts.py:28` imports `_summary`/`_validate` from
  `routers/whatif.py`; `web/field_frame.py:47` imports from
  `routers/players.py`; `web/routers/brief.py:12` imports the `digest`
  handler; `mcp_server.py` calls six route handlers directly.
- **Six `_fail` definitions** (`whatif.py:33`, `overrides.py:28`,
  `watchlist.py:25`, `drafts.py:49`, `decisions.py:24`, `settings.py:59`),
  two `_opt_float`, three `_num`.
- **Paths outside `artifacts.py`**: `journal.py:27`, `tracking.py:64,69`,
  `advise.py:102` (a second `REPORTS`), plus the `data/raw/*` roots in nine
  `data/` modules.
- **`web/schemas.py`** (2319 lines, 161 models) has one section banner
  (`:1903`). No dead models — every class is reachable from a route.
- **Five modules score "model vs me" into four files** (`review.py`,
  `journal.py`, `decisions.py`, `tracking.py`, `evaluation.py`); the journal
  and the ledger give opposite signs for GW2 and neither surface says which
  counterfactual it scores (09-04 review item 6, still open).
- **`print` is the only logger**: 256 calls, one `getLogger`, zero
  `log.info`. The advise note is printed twice (`pipeline.py:76-78` and
  `cli.py:138-139`).

### 1.5 The 2026-09-04 review's eight items, today

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | install automation | **done** | 9 jobs loaded; nightly backups since 09-08 |
| 2 | calibration season default | **open** | `cli.py:687` `season: str = "2025-26"`; also `cli.py:523` for `backtest`; `evaluation.py:823` accepts `None` |
| 3 | bonus head sees goals | open (model cycle) | `models/components.py:111-112` unchanged; `advise.py:456-462` |
| 4 | bound Dixon-Coles | open (model cycle) | `advise.py:474-475` copies `p_cs_model` unclipped; no numeric rail |
| 5 | fringe `e_goals` out of the artifact | **open** | `data/odds.py:688-695` gate is `p_play > 0`; `e_goals_odds` not in `artifacts.COMPONENT_COLS` (`:41-48`) |
| 6 | journal vs ledger captions | **open** | no "counterfactual" sentence on either surface |
| 7 | GKP calibration delta | done by data | `by_pos` has four keys after the 09-11 retrain; `calibrate.py:40-65` unchanged, so it is not guaranteed |
| 8 | GUIDE "70/30" | **open** | `docs/GUIDE.md:104`; `models/blend.params.json` serves 0.8 |

Items 3 and 4 change served numbers and belong to the model cycle the
ROADMAP already names as next. The rest change nothing the advice serves.

### 1.6 Leftovers from the v17 hand-off notes — all still present

`report/templates/report.html.j2:45` prices hits at a literal 4 (the served
`hit_cost` exists); the advise note double-print; `advise.py:1360`'s
docstring still says "the whole weekly pipeline"; `gather_inputs` is 271
lines (`advise.py:585-855`) with end-to-end coverage only through the golden;
`tests/golden_client.py:393` still replaces `live`'s `time` with a namespace
that has only `sleep`.

## 2. Frontend

- **The loader conversion stopped at This Week.** Twelve files call
  `usePageData`; about seventy raw `apiGet`/`apiPost` calls remain in hubs.
  Some URLs are read through both paths: `/api/league/leagues`
  (`ThisWeek.tsx:98` cached, `League.tsx:108` raw), `/api/components/{gw}`
  and the fixture matrix (`ComparePanel.tsx:115-117`, `FixtureMatrix.tsx:16`
  raw), `/api/settings` (`LadderCard.tsx:168` cached, `SettingsTab.tsx:137`
  raw). The Model hub fetches `/api/review` from three tabs
  (`ReviewTab.tsx:225`, `SeasonTab.tsx:131`, `QualityTab.tsx:860`) and
  re-asks on every tab switch because Radix unmounts the unselected tab.
  The invalidation rail (`api/invalidation.test.tsx`) protects only the
  cached half. `League.tsx:102-104` records a reason ("no cached card is
  watching them") that is no longer true.
- **Errors rendered as healthy empties.** `JournalTab.tsx:54`,
  `ReviewTab.tsx:226`, `SeasonTab.tsx:132`, `FixtureMatrix.tsx:18`,
  `FreshnessStrip.tsx:40`, `QualityTab.tsx:862,972`, `DraftsTab.tsx:27`
  synthesise an empty body in `.catch`; `Live.tsx:96-105` shows the
  cold-clone message for any error including a 500 mid-gameweek. The user
  reads "run `gaffer review`" when the server is down. `errorText` exists
  (`api/client.ts:24`) and 22 catches use `e.message` instead.
- **Stale-response races** on parameterised reads without a liveness guard:
  `Players.tsx:115-122`, `League.tsx:112-125`, `ComparePanel.tsx:114-119`,
  `Timeline.tsx:38-42` (its sibling effect at `:59-71` is guarded),
  `RivalDetail.tsx:63`. `PlannerBoard.tsx:85-99` documents and guards the
  hazard; `usePageData` already has the counter that removes the class.
- **Accessibility.** `@radix-ui/react-dialog` and `react-tooltip` are
  installed and never imported; the two modals are hand-rolled with no focus
  trap or focus return (`kit/ExplainModal.tsx:46-60`,
  `players/PinDialog.tsx:93-105`). `LadderCard.tsx:326-330` is a `<tr
  onClick>` with no keyboard path. `kit/DataTable.tsx:174-180` has no
  `aria-sort`. Four `scope=` attributes across 38 tables. Fixture-matrix
  chips carry difficulty as tone only. Tabs, roving tabindex on the board,
  `aria-pressed`, `:focus-visible` are all correct.
- **No error boundary** (`App.tsx`, `main.tsx`); the comment at
  `ThisWeek.tsx:126-129` describes the white screen it would catch. No
  route-level code splitting, so recharts ships on This Week's first paint.
  No `lint`, `check` or `test:run` script; ESLint absent with five
  `eslint-disable-next-line` comments (`api/useJob.ts:250,283`,
  `hubs/ThisWeek.tsx:92`, …).
- **Large components with natural cuts** (each a `squadRows`-style pure
  function or a sub-component): `model/QualityTab.tsx` (1053; four
  self-fetching sections), `planning/ChipsTab.tsx` (520; two unrelated
  components, and `solve()` at `:184-200` duplicates `WhatIfTab.tsx:42`),
  `planning/PlannerBoard.tsx` (520; the same move-row markup twice),
  `League.tsx` (481; `MarginFan` pure SVG; the "POST `/api/settings` then
  invalidate" written four times across `League.tsx:141-158`,
  `LadderCard.tsx:210-224`, `SettingsTab.tsx:145`),
  `players/ComparePanel.tsx` (452), `this-week/LadderCard.tsx` (411,
  already well cut).
- **Hygiene.** `kit/Badge.tsx` (the v14 "one-cycle alias") has no importer
  outside its test; `types.ts:280,282,290` carry three narrowings with no
  written reason, one field-for-field equal to the generated
  `SquadPlayerRef`; `kit/Button.tsx:12` `text-white` and the two `bg-black/70`
  overlays are Tailwind palette colours, not tokens; twelve non-null
  assertions (`SeasonTab.tsx:155-239` has seven). `api/useJob.test.tsx` waits
  on real timers (13.6 s of the 15 s suite) and is the source of the
  `act(...)` warning. Seven kit/api files have no test.

## 3. Suite and tooling

- **Duplicated pins.** `len(JOB_KINDS) == 12` in at least fourteen files
  (eighteen counting other spellings), and the seven-seam
  `run_advise` ordering pinned verbatim four times
  (`test_v5_degradation.py:268`, `test_v6:86`, `test_v8a:298`,
  `test_v8c:231`). The meta-rail (`test_v12_w1_degradation.py:73-126`)
  enforces single-home for routes and Config but not for job kinds. Post-v17g
  the ordering is testable behaviourally through `tests/gather_harness.py`'s
  call-order spies.
- **Source-text pins remain: 106 sites in 46 files.** Twenty-two
  `advise_source()` and 84 `inspect.getsource`. The ones that pin literals or
  absences should stay; the ones that pin call order can go behavioural.
- **Caches `conftest.py` does not clear** (cleared ad hoc in 14 test files):
  `optimize/scenarios.py:160`, `web/routers/league.py:62`,
  `web/identity.py:50`, `web/routers/league_sim.py:48,58`,
  `web/routers/live.py:31,43`, `calibrate_injuries.py:48`.
- **A test reads the machine's config.** `tests/test_v10_lineup_providers.py`
  passes `providers=` but not `absence=`, so `lineups.py:488-491` reads
  `config_in_force()` — the "flake" in v17e's note is environment
  dependence.
- **Tests that depend on untracked artifacts.** `test_report.py:49` and
  `test_chip_sanity.py:185-191` read `reports/gw*-advice.json`; on a fresh
  clone they never run.
- **No lint or format config** in either half; no pre-commit; no CI. Ruff
  (`uvx ruff check src tests`): 769 findings, 575 fixable — I001 260,
  RUF100 65, F401 49, C408 44, B023 16, F821 1.
- **Speed.** No `slow` marker, no random order, no `filterwarnings`; 12,844
  warnings are mostly PuLP's `constraints` mapping deprecation. The golden
  file is 7.5 min alone; `test_train.py` fits LightGBM for real; 24 files
  solve the real MILP.
- **`scripts/`.** Six drivers referenced only by closed specs
  (`v9c_club_eval.py`, `v9c_rc_arm.py`, `v9c_replay.sh`, `v9d_club_eval.py`,
  `v10_autosub_cf.py`, `v12_xgps_arm.py`); ten other one-offs are imported
  by tests through one path constant each.
- **Fixtures.** `tests/data` is 2.3 MB, all golden. The 176 KB
  `restraint-prose.fixture.json` trim (v17b note) is still open.
- **Six CLI commands have no test naming them**: `build-history`,
  `understat`, `league-sim`, `backtest`, `calibrate-decisions`,
  `diagnose-zeros`.

## 4. Docs

- **`CLAUDE.md`**: `:15-16` says the CLI `advise` does not chain the brief —
  false since v17d (`cli.py:59-60` → `pipeline.py:70-79`); `:49-50` describes
  `test_v16_restraint.py` as source-order pins that v17f moved and v17g
  replaced; the layout at `:39-42` omits `pipeline.py`, `served.py`,
  `inputs.py` and `config_in_force`; the orchestrator-only list predates
  `test_served_plan.py`, `test_golden_board.py` and `test_pipeline.py`, which
  now carry the pins it protected.
- **`docs/GUIDE.md`**: `:4` "last updated 2026-09-05, after v14"; `:65,89,124`
  a six-gameweek horizon where `config.py:100` defaults to 3 (six is this
  machine's overlay; `README.md:172` calls 6 "the default"); `:104` "70/30"
  (fitted 0.8); `:409` "nine settings" (fourteen); `:984` "seventeen became
  fourteen" vs the commit's thirteen; §8 omits `core-insights`; §12 opens
  "as of 2026-09-03"; §12.0 is headed as if the jobs were not installed;
  §12.4 lists two residuals v17 closed (the trace's present-tense price line,
  closed by v17f; `threshold_source` unrendered, rendered at
  `ChipsTab.tsx:125-128`); §12.2's table has three rows whose condition has
  filled (presser grading, EO trend, review-row snapshot) and two whose
  counts moved.
- **`README.md`** (1693 lines): about a thousand lines of v8e–v12 cycle
  diary duplicating GUIDE §5/§11; names deleted by v17e (`serving_config`,
  `optimizer_top_n`, `NON_FIELD_OPTIMIZER_KEYS`); a Tests section three
  cycles stale (4042/795, routes 47, Config 55); no clone/`uv sync`/Python
  version block; `gaffer brief` absent from the command table.
- **`ROADMAP.md`**: the install box (`:40-42`) still open; three data-gated
  rows met; the 09-04 review's items 2–8 are a parenthetical at `:34-36`, not
  candidates; the §6 informational replay is named as next at `:33` but absent
  from the Open index; "Where things stand" leads with v16's numbers.
- **Specs**: `2026-09-02-gaffer-v11-ui-design.md:176` Outcomes is `_TBD by
  the cycle._`; the v7 and v7b specs still say the GW2 news-shadow reading
  is pending. Every other spec records its verdict; the thirty cycle
  citations sampled in code all resolve.

## 5. What to do next, ranked

1. **Turn the gate back on** and make its skip loud: re-record the golden
   in its own commit; fix `test_pipeline.py`'s import order; one skip helper.
2. **Fix the three faults** — the ladder swallow, the silent solver switch,
   the `NameError` — each with a test that fires.
3. **Make `build_advice` pure in fact**: thread the three config reads
   through `Inputs`/`cfg`; move fixture difficulty and the plan timeline out
   of the web layer; give the pure cores a `now`.
4. **Run the measurement that never ran**: the season defaults, the health
   nulls, the pre-blend `e_goals` column, the counterfactual captions.
5. **Finish the frontend loader** and stop rendering errors as empties; then
   the dialogs, `aria-sort`, `scope`, the keyboard row, an error boundary.
6. **Give the repo a linter** and one style commit; single-home the job-kind
   pin; make the seam order a behavioural test; a `slow` marker and
   `filterwarnings`.
7. **A docs truth pass** — `CLAUDE.md` first, because agents obey it.
8. **Put to the user**: deleting 31 fully-merged branches; the open
   security incident; whether the model cycle (bonus head, Dixon-Coles
   bounds) follows this one.

Deliberately not here: the model items (3 and 4 of the 09-04 list), the
`ledgers.py` unification, a logging module, the blended league stance, the
in-app chat. Each moves a number or a subsystem and needs its own gate.
