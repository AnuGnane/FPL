# v18 — the polish programme

> **For agentic workers:** this is a *programme*, not a task plan. Each
> sub-cycle below (v18a … v18h) gets its own chat, its own spec, its own plan
> and its own branch, run the house way: grilling → spec with the gate written
> first → plan → superpowers:subagent-driven-development → gates → ff-merge →
> push → security ritual → docs → the tracker. Paste the **Prompt** block of
> the sub-cycle you are starting into a fresh chat. Nothing else from an
> earlier chat is needed.

**Goal:** close the findings of the 2026-09-12 final review
(`docs/superpowers/research/2026-09-12-final-review.md`) without changing a
single number the advice serves, so that the project's claims about itself
— a real gate, a pure build, honest errors, a suite with one home per rule,
docs that match the code — are true.

**Design:** `docs/superpowers/specs/2026-09-12-v18-polish-design.md`. Its
§1 holds the twelve rulings; read them before the sub-cycle's section here.

**Tech stack:** unchanged. Python 3.12 `src/gaffer`, pytest 9; React 18 +
TS + Tailwind v4 + vitest in `frontend/`. New in this programme: ruff (via
`uvx`, pinned in `pyproject.toml`), ESLint with `react-hooks`.

**Tracker:** `docs/superpowers/plans/2026-09-12-v18-tracker.md`.

---

## 1. Order and dependencies

Sequential, one branch in flight, ff-merged before the next starts. The
concrete reasons: v18b, v18c and v18d all edit `advise.py` or its callers;
v18e and v18f both edit the same hubs and both are screenshot-gated;
v18g collapses pins across rail files that v18b and v18d also touch.

| Sub-cycle | Name | Depends on | Size |
|---|---|---|---|
| v18a | the gate, back on | — | ½ day |
| v18b | the advice path tells the truth | v18a | 1½ days |
| v18c | measurement that has never run | v18a | 1 day |
| v18d | the core out of the web layer | v18b | 2 days |
| v18e | the loader, finished | — | 2 days |
| v18f | the surface, correct to the hand | v18e | 2 days |
| v18g | the suite, one home per rule | v18b, v18d | 1½ days |
| v18h | the docs, true | all | 1 day |

v18e touches only `frontend/` and could run in a second worktree after
v18a. Do not by default: one committing agent at a time was the v17h
lesson, and two screenshot control sets on one machine invite the
warm-cache confusion v17b and v17h both met.

---

## 2. What every sub-cycle does the same way

Everything in `plans/2026-09-07-v17-deepening-programme.md` §2 applies
unchanged — read first, branch naming, spec with the gate first, plan with
protected tasks kept for the orchestrator, gate run by the orchestrator,
ff-merge, push, the security ritual, the record in this order: spec
§Outcome, ROADMAP block, GUIDE §11 line, tracker row and hand-off note,
memory line. With four additions:

1. **Mutation-test every new rail before trusting it.** Plant the fault the
   rail exists to catch, watch it fail, revert. v17g and v17h both found
   rails that could not fire; this programme adds about fifteen.
2. **One committing agent at a time.** Reviewers may overlap freely.
3. **A "no diff" needs a same-code control.** If a screenshot pair differs,
   re-shoot the control second before reading the diff as real.
4. **Every implementer prompt carries a "where your judgement is wanted"
   section.** The plan's sketches are not sacred.

**Gates in this programme are of three kinds.**

- *Golden* (v18b, v18c, v18d): `.venv/bin/pytest -q -rs
  tests/test_golden_board.py tests/test_pipeline.py` → 54 passed, **0
  skipped**, fixture untouched since v18a's recording. About fifteen
  minutes.
- *Surface* (v18e, v18f, v18c's two pairs): the suites, the named rails,
  and `frontend/scripts/shots.sh v18<letter>-before` on `main` then
  `-after` on the branch, approved by the user.
- *Rule* (v18a, v18g, v18h): the named commands with their exact expected
  output, pasted into the spec's outcome.

**Pins.** Routes 51, job kinds 12, `Config` fields 62 for the whole
programme. A sub-cycle that moves one says so in its spec and bumps it in
its own commit. Never add a job kind.

**Security.** The odds key by name only, `[odds] api_key`. Subagents never
open `config.toml`.

---

## 3. The sub-cycles

### v18a — the gate, back on

**Goal.** The golden board gates again, loudly, and `CLAUDE.md` stops
misleading the agents that run the rest of the programme.

**Files.** `tests/data/golden_board/**` (re-recorded, one commit),
`tests/golden_client.py`, `tests/test_golden_board.py`,
`tests/test_pipeline.py`, `CLAUDE.md`.

**Tasks.**
1. *Orchestrator.* `python -m tests.golden_client --write` from the repo
   root; confirm no lever fell below its floor; commit
   `tests/data/golden_board` alone with the subject naming the 09-11
   retrain. Then `pytest -q -rs tests/test_golden_board.py
   tests/test_pipeline.py` → 54 passed, 0 skipped: the baseline.
2. *Implementer.* `golden_header_or_skip(repo)` in `golden_client.py`
   replacing the two copies (`test_pipeline.py:248-262`,
   `test_golden_board.py:245-256`) and the third wording. Ruling 1: the
   skip stays, with a sentence naming the first differing file and the
   `--write` command; a rail builds a scratch tree with one meta file
   altered and asserts the sentence. Mutation: break the sentence, watch
   the rail fail. `-rs` joins every documented gate command.
3. *Implementer.* `_wire()` imports `gaffer.advise` before the first
   `monkeypatch.setattr` (review §1.1). Test: `pytest -q
   tests/test_pipeline.py` alone passes.
4. *Implementer.* `golden_client.py:393`: `patch.object(live.time,
   "sleep", …)` instead of replacing the module's `time`.
5. *Orchestrator.* `CLAUDE.md`: the brief sentence, the v16 rail
   sentence, the layout line, `-rs` in the golden gate command.

**Gate.** As the spec's v18a section: four lines, all as written.

**Prompt.**
> Start v18a of the polish programme. Read `CLAUDE.md`, then
> `docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §2 and §3
> v18a, `docs/superpowers/specs/2026-09-12-v18-polish-design.md` §1
> rulings 1 and 12, and `docs/superpowers/research/2026-09-12-final-review.md`
> §1.1. Branch `v18a-gate` off `main`. Write the spec with the gate first,
> then the plan, then run it the house way. Task 1 is yours and comes
> first; nothing else runs until the baseline reads 54 passed, 0 skipped.

### v18b — the advice path tells the truth

**Goal.** Wiring errors raise, the solver switch is on the record, the two
halves read only `cfg`, the pure cores take a `now`, and the five v17
leftovers are gone.

**Files.** `src/gaffer/advise.py` (orchestrator), `optimize/milp.py`
(orchestrator), `ladder.py`, `served.py`, `inputs.py`,
`models/availability.py`, `artifacts.py`, `price_timing.py`,
`calibrate_noise.py`, `pipeline.py`, `cli.py`,
`report/templates/report.html.j2`, `tests/test_advise.py` (orchestrator),
`tests/test_golden_board.py`, `tests/golden_client.py`, new
`tests/test_advice_path.py`.

**Tasks.**
1. *Orchestrator.* `advise.py:1278`: `except (GafferError, ValueError)`.
   Rail: a monkeypatched `ladder_payload` raising `TypeError` propagates
   out of `build_advice`; raising `GafferError` is reported as today.
2. *Orchestrator.* `milp.py:977`: on fallback, record `solver="cbc"` in
   the solve's `opt` dict; nothing written when HiGHS solves. Rail: with
   `pulp.HiGHS` patched to raise, the state carries the key; unpatched,
   it does not.
3. *Implementer.* Thread the back-door reads: `served.price_falls` takes
   `price_timing` from its caller (`gather_inputs` passes
   `cfg.price_timing`); `models/availability.py:115` and
   `artifacts.load_availability` take the overrides value as a parameter;
   `price_timing.py:169` and `ladder.py:449,767,991` likewise. Extend the
   v17g purity rail so `config_in_force` raises the `BaseException`
   sentinel while either half runs; mutation: plant one call, watch it
   fire. `models/train.py:586` is the trainer, not the build path, and is
   out of scope.
4. *Implementer.* `now` parameters on `build_advice` and `ladder_payload`;
   the golden strips `wall_s` and adds `ladder_gwN.json` to `expected/`
   (re-recorded once here, with the reason: the ladder was never pinned).
   If the ladder JSON carries anything else volatile, the spec names it and
   the strip covers it.
5. *Implementer.* `calibrate_noise.py:443`: import `attacking_features`
   in `ensemble_rows`' own block; one test over a three-row frame with a
   bundle lacking `feature_cols`, un-stubbed.
6. *Implementer.* The template reads `restraint.hit_cost`; the CLI's
   second note echo (`cli.py:138-139`) goes; `advise.py:1360`'s docstring
   (orchestrator applies the one-line diff).

**Gate.** Golden byte-identical (with the ladder file added in task 4 and
recorded as the one deliberate fixture change); every rail shown to fire.

**Prompt.**
> Start v18b of the polish programme. Read `CLAUDE.md`, the programme §2
> and §3 v18b, the design's rulings 2, 3 and 4, the review's §1.2, §1.3 and
> §1.6, and the v18a hand-off note in the tracker. Branch
> `v18b-advice-path` off `main` at v18a's merge hash. Tasks 1, 2 and the
> docstring are yours; the rest go to implementers with a spec review and
> a code review between tasks.

### v18c — measurement that has never run

**Goal.** The calibration report grades real gameweeks, the health file's
two numbers exist, the pre-blend `e_goals` is on disk for the model cycle,
and the two scoring surfaces say what they score.

**Files.** `cli.py`, `tracking.py`, `artifacts.py`, `evaluation.py`,
`frontend/src/hubs/model/ReviewTab.tsx`, `JournalTab.tsx`,
`docs/GUIDE.md` §3 (one sentence), tests.

**Tasks.**
1. `cli.py:687` `season: str | None = None`; `cli.py:523` from
   `train_seasons[-1]`. Test: the CLI passes `None` through.
2. `tracking.compute_health` receives the ledger's `my_points` and
   `model_points` for the graded gameweek from `update_health`; test that
   both keys are numbers after a review with a graded row.
3. `e_goals_model` banked beside `e_goals` in `COMPONENT_COLS`; the
   blend untouched. Test: the column exists and equals the model output
   where `p_play < 0.1`.
4. The counterfactual sentence on both tabs, with a test each; the GUIDE
   §3 blend sentence.
5. *Orchestrator.* On this machine: `uv run gaffer evaluate --calibration`
   and the `jq` line; `gaffer review` and the health file; the two
   screenshot pairs.

**Gate.** As the spec's v18c section.

**Prompt.**
> Start v18c of the polish programme. Read `CLAUDE.md`, the programme §2
> and §3 v18c, the design's ruling 11, the review's §1.5 and §0, and the
> tracker's v18b note. Branch `v18c-measurement` off `main` at v18b's
> merge hash.

### v18d — the core out of the web layer

**Goal.** Nothing under `src/gaffer` outside `web/` imports the web layer;
no function-body import exists to dodge a cycle; one coercion module; every
path is `artifacts`'.

**Files.** New `src/gaffer/difficulty.py`, `refresh.py`, `whatif.py`,
`web/coerce.py`; `advise.py` and `ladder.py` (the import line),
`brief.py`, `served.py`, `web/identity.py`, `web/routers/meta.py`,
`web/routers/plan.py`, `web/routers/whatif.py` (orchestrator),
`web/routers/drafts.py`, `web/field_frame.py`, `web/routers/brief.py`,
`web/job_kinds.py`, `mcp_server.py`, `inputs.py`, `snapshot.py`,
`config.py`, `optimize/chip_policy.py`, `models/dnp_calibrate.py`,
`backtest.py`, `live_gw.py`, `review.py`, `data/understat.py`,
`journal.py`, `tracking.py`, `web/schemas.py` (banners only), the six
routers with `_fail`, new `tests/test_layering.py`.

**Tasks.** In this order, each gated on the golden before the next:
1. `difficulty.py`; `identity.py` wraps it; `advise.py`/`ladder.py` import
   it (orchestrator for the two import lines).
2. The plan timeline into `served.py`; `routers/plan.py` and `brief.py`
   call it.
3. `refresh.py` from `meta.py:458-493`; `job_kinds.py` imports it.
4. `whatif.py` from the router's `_validate`/`_summary` (orchestrator);
   `drafts.py` and `mcp_server.py` on it.
5. The seven lazy imports: move `predict_components`, `news_availability`,
   `MODEL_NAMES` to `models/`, `_formation_legal` to `optimize/`
   (orchestrator), drop `config.py:675`; hoist.
6. `web/coerce.py`; the six `_fail`s, two `_opt_float`, three `_num`
   replaced; messages byte-identical (the router tests are the instrument).
7. Paths into `artifacts`; banners in `schemas.py`.
8. `tests/test_layering.py`: the no-web-import rail, the acyclic
   top-level graph rail, the absent-lazy-import rail; each mutation-tested.

**Gate.** As the spec's v18d section; the golden after every task.

**Prompt.**
> Start v18d of the polish programme. Read `CLAUDE.md`, the programme §2
> and §3 v18d, the design's rulings 5 and 6, the review's §1.3 and §1.4,
> and the tracker's v18c note. Branch `v18d-layering` off `main` at v18c's
> merge hash. Run the golden after every task, not once at the end.

### v18e — the loader, finished

**Goal.** One transport for every artifact read, errors that look like
errors, and a page that cannot white-screen.

**Files.** `frontend/src/api/pageData.ts`, new `kit/Loaded.tsx`,
`kit/ErrorBoundary.tsx`, `App.tsx`, every hub and card with a raw
artifact read (review §2, first bullet), `api/invalidation.test.tsx`, new
`hubs/*.fetches.test.tsx` per hub.

**Tasks.**
1. *Orchestrator, first.* The per-hub fetch rails written against
   `main`'s behaviour and committed, so the control arm is in git.
2. `usePageData` exposes `status` from `ApiError`; `Loaded` over
   `PageData<T>`; `ErrorBoundary` around `<Routes>`.
3. Hub by hub — Planning, Players, League, Model, then the kit strips —
   convert the artifact reads; the liveness reads listed by name in the
   spec and left raw; the synthesised empties converted (ruling 7);
   `errorText` at every surviving catch; the stale-comment in `League.tsx`
   goes; the invalidation table gains its rows.
4. The table-driven 500/404 test.

**Where judgement is wanted.** Which reads are liveness (the spec's list
is a starting point, not a verdict); whether `Loaded` takes render props
or children; whether the Model hub's three `/api/review` readers should
share one `usePageData` call at the hub or three at the tabs (the cache
makes both one request; the spec prefers the tabs, for lazy mount).

**Gate.** Four parts, as the spec's v18e section.

**Prompt.**
> Start v18e of the polish programme. Read `CLAUDE.md`, the programme §2
> and §3 v18e, the design's ruling 7, the review's §2, the v17h spec's §2–§5
> for `usePageData`'s contract, and the tracker's latest note. Branch
> `v18e-loader` off `main`. Task 1 is yours and is committed before any
> conversion.

### v18f — the surface, correct to the hand

**Goal.** Dialogs, tables and rows usable from the keyboard and a screen
reader; six components cut at their natural seams; a linter; hygiene.

**Files.** `kit/ExplainModal.tsx`, `hubs/players/PinDialog.tsx`,
`kit/DataTable.tsx`, `kit/table.ts`, `hubs/this-week/LadderCard.tsx`,
`hubs/players/FixtureMatrix.tsx`, `hubs/this-week/SquadTable.tsx`,
`kit/Badge.tsx` (deleted), `kit/index.ts`, `types.ts`, `styles/theme.css`,
`kit/Button.tsx`, `App.tsx` (lazy routes), `package.json`, new
`eslint.config.js`, the six large components and their new siblings,
`api/useJob.test.tsx`, `kit/tokens.test.ts`.

**Tasks.** Two halves, each screenshot-gated.
1. *Hand and eye.* Radix `Dialog` for the two modals; `aria-sort`;
   `<Th scope="col">`; the rung toggle as a button; text equivalents on
   the tone-only chips; the two tokens; `Badge` and the two unused
   dependencies gone; the three hand types replaced; the non-null
   assertions narrowed; lazy routes; ESLint and `npm run check`; the five
   disables each fixed or reasoned.
2. *The cuts.* One task per component, tests moved with the code:
   `QualityTab` sections, `ChipsTab`'s `ChipOutlook` + `useWhatIfSubmit`,
   `PlannerBoard`'s `boardRequest` + `TraceMoves`, `League`'s `MarginFan`
   + `useSettingWrite` (also used by `LadderCard` and `SettingsTab`),
   `ComparePanel`'s `compareRows`, `LadderCard`'s `RungRow`.
3. `useJob.test.tsx` on `vi.useFakeTimers`; a console spy for the `act`
   warning.
4. `tokens.test.ts` extended, each rule mutation-tested.

**Gate.** As the spec's v18f section.

**Prompt.**
> Start v18f of the polish programme. Read `CLAUDE.md` (Frontend rules),
> the programme §2 and §3 v18f, the review's §2, and the tracker's v18e
> note. Branch `v18f-surface` off `main` at v18e's merge hash. Shoot the
> control set before the first commit.

### v18g — the suite, one home per rule

**Goal.** A linter with a committed config, one home for every pinned
count, behaviour where source text was pinned, an inner loop under three
minutes, and a suite that runs on a clone.

**Files.** `pyproject.toml` (`[tool.ruff]`, markers, `filterwarnings`),
`tests/conftest.py`, `tests/test_v12_w1_degradation.py` and every rail
file with the job-kind count (orchestrator), new
`tests/test_advise_order.py`, the four files with the verbatim seam pin
(orchestrator), `tests/test_v10_lineup_providers.py`, `scripts/archive/`,
`tests/data/gw2-advice.json`, `tests/test_report.py`,
`tests/test_chip_sanity.py`, `frontend/src/hubs/this-week/restraint-prose.fixture.json`,
new `tests/test_cli_smoke.py`, and the one `style:` commit across `src`
and `tests`.

**Tasks.**
1. `[tool.ruff]` and the `style:` auto-fix commit (imports, unused
   imports) — nothing else in that commit. Then the sixteen B023 by hand.
2. *Orchestrator.* The meta-rail's job-kind assertion; the copies
   collapsed to membership; pin-only commit.
3. *Orchestrator.* `test_advise_order.py` over the harness spies,
   mutation-tested; the four verbatim copies deleted.
4. The caches fixture; the lineup-providers `patch_view`.
5. `slow` marker; `filterwarnings`; the inner loop documented and timed.
6. `scripts/archive/` for the six; the tracked trimmed advice fixture;
   the prose fixture regenerated; the CLI smoke tests.

**Gate.** As the spec's v18g section.

**Prompt.**
> Start v18g of the polish programme. Read `CLAUDE.md` (Pins and protected
> files), the programme §2 and §3 v18g, the design's rulings 8, 9 and 10,
> the review's §3, and the tracker's latest note. Branch `v18g-suite` off
> `main`. Tasks 2 and 3 are yours, in pin-only commits.

### v18h — the docs, true

**Goal.** Every sentence the docs make about the code is true as of v18h,
and the user's three open decisions are recorded.

**Files.** `CLAUDE.md`, `README.md`, `docs/GUIDE.md`,
`docs/superpowers/ROADMAP.md`, `specs/2026-09-02-gaffer-v11-ui-design.md`,
`specs/2026-08-30-gaffer-v7-model-design.md`,
`specs/2026-08-30-gaffer-v7b-measurement-design.md`, the memory file.

**Tasks.** One row per line of the review's §4, in a checklist inside the
v18h spec; the README rewrite; the ROADMAP's v18 block with the closing
ledger transcribed from the tracker; GUIDE §11 and §12 as of v18h; the
three decisions (branches, incident, model cycle) with the user's answers.

**Gate.** As the spec's v18h section: no checklist row blank; every
`CLAUDE.md` command run once with its output pasted.

**Prompt.**
> Start v18h, the last sub-cycle of the polish programme. Read
> `CLAUDE.md`, the programme §2 and §3 v18h, the review's §4, and every
> hand-off note in the tracker. Branch `v18h-docs` off `main`. Before
> writing, ask the user the three questions in the design's ruling 12.

---

## 4. When a sub-cycle fails its gate

The v17 rule holds: the branch does not merge; the spec's §Outcome records
the failure with the numbers; the tracker's hand-off note says what was
learned; the next sub-cycle starts from the last merged hash. A golden diff
that is *explained* (v18b's ladder file) is recorded in the spec before the
fixture changes, never after.

---

## 5. Self-review

Every sub-cycle names its gate and the files it touches, and every
protected file in the review's findings has an orchestrator task here
(`advise.py`, `optimize/milp.py`, `web/routers/whatif.py`,
`tests/test_advise.py`, the rail files). No sub-cycle changes a served
number; the one deliberate fixture change (the ladder file, v18b) is
declared. The order puts the gate first, the truth of the advice path
second, and the docs last, so the docs describe a finished state.
