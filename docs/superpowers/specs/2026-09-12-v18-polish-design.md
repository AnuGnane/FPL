# v18 — the polish programme (design)

**Cycle:** v18, a programme of eight sub-cycles, v18a … v18h.
**Source:** `docs/superpowers/research/2026-09-12-final-review.md` (the
review this design answers; every finding below cites it by section).
**Plan:** `docs/superpowers/plans/2026-09-12-v18-polish-programme.md`;
tracker `docs/superpowers/plans/2026-09-12-v18-tracker.md`.
**Branches:** `v18<letter>-<slug>` off `main`, one at a time, ff-merged.
**Date:** 2026-09-12. **Status:** approved by the user 2026-09-12; running.

---

## 0. What this is, and the three ways it could have been done

The user asked for a final review and polish after v17. The review found
nothing that changes a number the advice serves and a great deal that
weakens the claims the project makes about itself: a gate that is silently
off, three faults on the advice path, a "pure" build that reads config and
the web layer behind its back, measurement that has never run, a frontend
loader finished on one hub of six, no linter, and docs that disagree with
the code in about thirty places, three of them in `CLAUDE.md`.

Three shapes were considered.

- **A. One polish branch.** Everything on `v18-polish`, one gate at the
  end. Fastest to start, but the house rule that every merge is gated
  separately exists because a single "no diff" over forty changes proves
  nothing about any one of them, and a failure at the end cannot be
  attributed. Rejected.
- **B. A programme of gated sub-cycles, v17-style.** Eight chats, each
  with its own spec, plan, branch and gate; the golden board for the
  backend, screenshot pairs and fetch rails for the frontend. Slower by a
  few days, but each merge is a fact. **Chosen.**
- **C. Hotfix the top five and stop.** The gate, the three faults, the
  `CLAUDE.md` sentences. Honest and small, but it leaves the frontend
  rendering errors as empties, the suite without a linter, and the README
  three cycles stale, which is the opposite of "final". Kept as the
  fallback if the user wants less: v18a and v18b *are* option C.

**The rule for the whole programme, as in v17: no sub-cycle changes a number
the advice serves.** The backend sub-cycles are gated on the golden board
being byte-identical to a recording made once, in v18a, and not touched
again. The frontend sub-cycles are gated on screenshot pairs and fetch-count
rails with a control arm committed first. Anything that would move a served
number (the bonus head, Dixon-Coles bounds, the odds cap on the *blend*) is
out of scope and named in §4 as the model cycle's.

---

## 1. Rulings the grilling settled

These are the decisions a reader would otherwise have to guess; each is a
choice, and the reason is written so the user can overrule it.

1. **A stale golden skips, loudly; an absent one skips too** (v18a). Today
   a board recorded under different models *skips*, and the suite reads
   green while the gate is off (review §1.1). The design offered a
   fail-on-stale rule; **the user ruled against it on 2026-09-12**, because
   a Thursday retrain would then cost a re-record commit every week. So the
   skip stays and is made loud: every documented gate command carries
   `-rs`, so the skip line and its file name print at gate time; the skip
   sentence names the file and the `--write` command; a rail asserts that
   sentence against a scratch tree with one meta file altered; and the
   hand-off note of every golden-gated sub-cycle quotes the `-rs` line. The
   board is re-recorded once, in v18a, because the 09-11 retrain moved it
   and v18b–v18d need the live-model half; after the programme it is
   re-recorded only when a refactor needs the gate, never on a schedule.
2. **The ladder catches the domain error only** (v18b). `GafferError` and
   `ValueError` (a degenerate draw) are caught and reported as today;
   `TypeError`, `KeyError`, `AttributeError` propagate. A miswired call
   then fails the golden, `test_pipeline` and the Thursday run loudly,
   which is what the v17g lesson asked for.
3. **The solver switch is recorded, not prevented** (v18b). When HiGHS
   fails and CBC solves, `state.opt` gains `solver: "cbc"`; when HiGHS
   solves, no key is written. The golden is therefore unchanged on a
   machine where HiGHS works, and the artifact says so on one where it did
   not.
4. **`build_advice` and `gather_inputs` read `cfg`, never
   `config_in_force()`** (v18b). The three back-door reads on the build
   path (review §1.3) are threaded through `cfg` or `Inputs`. The purity
   rail from v17g is extended so that a `config_in_force` call inside
   either half raises the `BaseException` sentinel. Routers and the CLI
   keep the cached view; `Inputs` gains no field unless a value is not
   already on `Config`, and no `Config` field is expected to be added (pin
   stays 62; if one is needed it moves in its own commit).
5. **Fixture difficulty and the plan timeline become core functions the
   routers call** (v18d), not the other way round. `gaffer/difficulty.py`
   owns `difficulty_by_team`; `served.py` owns the timeline the brief and
   the plan route both read. `web/identity.py`'s cache stays where it is
   and wraps the core function. `mcp_server.py` calls the same core
   functions. Routes stay at 51.
6. **`web/routers/whatif.py`'s validators move to `gaffer/whatif.py`**
   (v18d). The router is orchestrator-only; the orchestrator makes the
   diff, which is a move with no edit.
7. **Errors are errors; empties are 404s** (v18e). A component that today
   synthesises an empty body in `.catch` renders a `Callout tone="error"`
   with `errorText(e)` on any failure and its named empty state only when
   the server answered 404 (or the documented 422). `usePageData` exposes
   the status so the branch is data, not a catch.
8. **The single-home rule extends to the job-kind count** (v18g). The
   value stays 12. The meta-rail gains
   `test_only_one_file_pins_the_job_kind_count`; the other copies become
   membership checks. This edits orchestrator-only rail files; the
   orchestrator makes the diff, in a pin-only commit.
9. **Seam order becomes behaviour** (v18g). One `tests/test_advise_order.py`
   asserts the seven-seam order through `tests/gather_harness.py`'s
   call-order spies, mutation-tested by swapping two calls in a scratch
   copy. The four verbatim source-text copies are deleted; the straddling
   case `test_advise_source.py` documents stays as the one text pin.
10. **Ruff is the linter, with a small rule set** (v18g). `[tool.ruff]`
    with `select = ["E", "F", "B", "I"]`, line length matched to the code,
    and per-file ignores written with a reason. One `style:` commit applies
    the auto-fixes (imports, unused imports); the sixteen B023 sites are
    reviewed by hand and each fixed or ignored with a sentence. ESLint with
    `react-hooks` joins the frontend; the five existing disables are each
    kept with a reason or fixed.
11. **The backtest's season default stays a finished season** (v18c). The
    review's docs audit flagged `cli.py:523` `"2025-26"` as stale; it is
    not, because a backtest needs a completed season. It becomes
    `train_seasons[-1]` so it survives rollover. The *evaluate* default
    (`cli.py:687`) is the bug and becomes `None`.
12. **Branch deletion, the security incident and the model cycle were the
    user's decisions**, taken on 2026-09-12: the 31 fully merged branches
    are deleted before v18a's branch is cut; the model cycle (the 09-04
    review's items 3 and 4, the role replay, the news ablation) follows
    v18; the security incident stays with the user.

---

## 2. The sub-cycles

| Sub-cycle | Name | Half | Depends on | Size |
|---|---|---|---|---|
| v18a | the gate, back on | tests + `CLAUDE.md` | — | ½ day |
| v18b | the advice path tells the truth | backend | v18a | 1½ days |
| v18c | measurement that has never run | backend | v18a | 1 day |
| v18d | the core out of the web layer | backend | v18b | 2 days |
| v18e | the loader, finished | frontend | — | 2 days |
| v18f | the surface, correct to the hand | frontend | v18e | 2 days |
| v18g | the suite, one home per rule | tests + tooling | v18b, v18d | 1½ days |
| v18h | the docs, true | docs | everything | 1 day |

Sequential, one committing agent at a time (the v17h lesson). v18e could
start in a second worktree after v18a since it touches only `frontend/`,
and the gain is real; the cost is two screenshot control sets on one
machine and the OOM rule for concurrent runs. The default is sequential.

### v18a — the gate, back on

*What.* Re-record the golden board with `python -m tests.golden_client
--write` in its own commit (the models moved on 09-11; the reason in the
subject). Ruling 1: a stale board skips with a sentence naming the file and
the command, asserted by a rail; `-rs` in every documented gate command.
Fix `tests/test_pipeline.py`'s `_wire()` import order (review §1.1). One
`golden_header_or_skip` in `tests/golden_client.py` replacing the two
copies and the third wording. Replace the `time` hush at
`golden_client.py:393` with a `patch.object` on `sleep`. And the three
`CLAUDE.md` sentences agents obey: `advise` chains the brief since v17d;
`test_v16_restraint.py` holds the CLI restraint lines, not source-order
pins; the layout gains `pipeline.py`, `served.py`, `inputs.py` and
`config_in_force`.

*Gate, pre-registered.* `.venv/bin/pytest -q -rs tests/test_golden_board.py
tests/test_pipeline.py` → **54 passed, 0 skipped**. `.venv/bin/pytest -q
tests/test_pipeline.py` alone → passes. A scratch copy with one
`models/*.meta.json` altered → the golden tests **skip** with a message
containing the file name and `--write`, and the rail that asserts this
sentence is shown to fail when the sentence is broken. `pytest -q` with
`models/` renamed away → the live-model tests skip, the seam tests pass.
Verdict rule: all four lines as written, or the sub-cycle does not merge.

*Protected files.* `tests/test_pipeline.py` is not protected;
`tests/golden_client.py` is not protected; the golden fixture commit is
the orchestrator's.

### v18b — the advice path tells the truth

*What.* Rulings 2, 3 and 4. The `NameError` in
`calibrate_noise.ensemble_rows` (`:443`) fixed and given one un-stubbed
test over a tiny frame. `now: datetime | None = None` on `build_advice` and
`ladder_payload`, defaulting to the clock; the ladder JSON gains a byte gate
in the golden with `wall_s` stripped (or the spec records why not).
Leftovers: `report.html.j2:45` reads the served `hit_cost`; the advise note
printed once (the CLI's echo goes; the pipeline's stays because the web job
needs it); `advise.py:1360`'s docstring says what the function is.

*Gate.* Golden untouched after v18a → 54 passed, 0 skipped, byte-identical.
New rails, each mutation-tested before it is trusted (the v17g rule):
a planted `TypeError` inside the ladder call propagates out of
`build_advice`; a planted `GafferError` is reported as today; the purity
sentinel fires on a planted `config_in_force()` call in both halves; the
template renders `−5` for `hit_cost=5`; the CLI prints the note exactly
once; `ensemble_rows` runs on a model bundle without `feature_cols`.
Verdict: golden byte-identical and every rail shown to fire.

*Protected files.* `advise.py`, `optimize/milp.py`, `tests/test_advise.py`:
the orchestrator makes those diffs. `ladder.py`, `served.py`,
`models/availability.py`, `price_timing.py`, `calibrate_noise.py`,
`pipeline.py`, `cli.py`, the template: implementers.

### v18c — measurement that has never run

*What.* `cli.py:687` `season` defaults to `None`; `backtest`'s to
`train_seasons[-1]` (ruling 11). `tracking.update_health` passes the
ledger's points so `advice_pts`/`actual_pts` are populated, or the two
keys leave the schema — populate is the choice, because the ledger has
them. The pre-blend `e_goals` is banked as `e_goals_model` in
`artifacts.COMPONENT_COLS` so evaluations can read it (the blend itself is
untouched: changing it moves served numbers). One sentence on Model → Review
and Model → Journal naming the counterfactual each scores (the journal
scores the model's own XI gross; the ledger scores your squad with the
model's lanes applied). GUIDE §3's "70/30" becomes "a fitted market weight
(`models/blend.params.json`; 0.7 when unfitted)".

*Gate.* Golden byte-identical (advice, plan, solve_state; the components
parquet is not in the golden and gains a column). On this machine `uv run
gaffer evaluate --calibration` then `jq '.calibration.p_play.n'
reports/evaluation.json` → a positive integer (the user reads this number;
it is recorded in the spec's outcome). `reports/health.json` after `gaffer
review` carries two non-null points. Two screenshot pairs (Model → Review,
Model → Journal) with the new sentence and nothing else different.
Verdict: all three, plus the sentence approved by the user.

*Protected files.* `advise.py` if `COMPONENT_COLS` is written there
(it is in `artifacts.py`, not protected). `tracking.py`, `cli.py`,
`evaluation.py`, the two tabs: implementers.

### v18d — the core out of the web layer

*What.* Rulings 5 and 6. `gaffer/difficulty.py` with `difficulty_by_team`
(moved from `web/identity.py:305-308` + `routers/meta.py:403-417`, the
router calling it); the plan timeline into `served.py`, `routers/plan.py`
and `brief.py` calling it; `run_data_refresh` from `routers/meta.py:458-493`
to `gaffer/refresh.py`, `job_kinds.py` importing it from there;
`_validate`/`_summary` to `gaffer/whatif.py`; `mcp_server.py` on the core
functions. The seven cycle-dodging lazy imports hoisted after
`predict_components`, `news_availability` and `MODEL_NAMES` move to
`models/`, `_formation_legal` to `optimize/`, and `config.py:675`'s
`owned_price_falls` re-export goes. `web/coerce.py` with `fail`, `opt_int`,
`opt_float`, `finite` replacing the six `_fail`s and their cousins, messages
byte-identical. `journal.py:27`, `tracking.py:64,69` and `advise.py:102` read
their paths from `artifacts`. Section banners in `schemas.py`, one per hub,
no reordering.

*Gate.* Golden byte-identical. Routes 51. New rails: no `from gaffer.web`
import outside `src/gaffer/web/` and `src/gaffer/mcp_server.py`'s
server-wiring lines; the import graph built from top-level imports is
acyclic *and* the seven named function-body imports are absent (so a
regression cannot hide by going lazy again); every router 4xx sentence
unchanged (the existing router tests are the instrument; the coerce module
gets its own table). `types.generated.ts` unchanged (`npm run types --
--check` silent), because no schema field moves.

*Protected files.* `advise.py`, `optimize/**` (for `_formation_legal`),
`web/routers/whatif.py`: orchestrator. The rest: implementers.

### v18e — the loader, finished

*What.* Every artifact read in `hubs/` and `kit/` through `usePageData`;
the liveness reads (`Live.tsx`'s poll, the job probe) stay raw and are
listed by name. One `Loaded` kit component over `PageData<T>` with
`loading`, `error` and `empty` slots; the eight synthesised empties and
`Live.tsx:96-105` converted (ruling 7); `errorText` at every catch that
survives. An `ErrorBoundary` around `<Routes>` rendering a `Callout`.
`League.tsx`'s stale comment goes with its raw reads. A `*.fetches.test.tsx`
rail per hub, committed against `main`'s behaviour first so the control arm
is in git (the v17h method). The `invalidation.test.tsx` table gains a row
per newly-cached URL with a writer.

*Gate.* Four parts. (1) Fetch counts per hub, before and after, with the
control commit hash named; no hub fetches more, and the Model hub's
`/api/review` count on a three-tab walk falls from 3 to 1. (2) Twelve
screenshot pairs (six hubs, two themes) byte-identical, with the control
shot second when the first differs (the v17b/v17h league-sim lesson).
(3) For each converted component, a 500 renders the error callout and a
404 renders its named empty state — one table-driven test. (4) `grep -rn
"apiGet(" frontend/src/hubs frontend/src/kit` lists only the liveness
reads the spec names. Verdict: all four.

### v18f — the surface, correct to the hand

*What.* Radix `Dialog` for `ExplainModal` and `PinDialog` (focus trap and
return, `inert` background) and the unused `react-tooltip` dependency
removed or used; `aria-sort` on `DataTable` headers with the glyph
`aria-hidden`; `<Th>` emitting `scope="col"` through `kit/table.ts`; the
ladder rung toggle on a `<button aria-expanded>`; a text equivalent on the
fixture-matrix chip and on `SquadTable`'s tone-only chips. Hygiene:
`kit/Badge.tsx` deleted with its export and test; the three unreasoned
hand types in `types.ts` replaced by the generated names;
`--color-on-accent` and `--color-scrim` tokens replacing `text-white` and
`bg-black/70`; the non-null assertions narrowed once above the JSX.
`React.lazy` per hub with a `Loading` fallback. ESLint with
`react-hooks` and a `check` script (`tsc --noEmit && vitest run && npm run
types -- --check && eslint`). The six component cuts (review §2), each a
pure function with a table or a sub-component with its tests moved:
`QualityTab`'s four self-fetching sections, `ChipsTab`'s `ChipOutlook` and
the shared `useWhatIfSubmit`, `PlannerBoard`'s `boardRequest` and
`TraceMoves`, `League`'s `MarginFan` and the shared `useSettingWrite`,
`ComparePanel`'s `compareRows`, `LadderCard`'s `RungRow`.
`api/useJob.test.tsx` on fake timers, and the `act(...)` warning gone.

*Gate.* Twelve screenshot pairs byte-identical (the dialogs are not on a
first paint). `kit/tokens.test.ts` extended: no `text-white`, no
`bg-black`, no `Badge` export, every `<th>` in `kit/` has `scope` — each
new rule mutation-tested. `npm run check` green with zero ESLint errors.
`vitest run` count not lower than 986 with the moved tests counted;
`api/useJob.test.tsx` under 2 s and a console spy asserting no
`act(...)` warning. The build's first-paint chunk for This Week does not
contain recharts (read from `vite build`'s output; a documented check,
not a test). Verdict: all of it; the screenshots approved by the user.

### v18g — the suite, one home per rule

*What.* Rulings 8, 9, 10. `tests/conftest.py`'s autouse fixture clears the
seven caches `invalidate()` misses; the fourteen ad-hoc clears go.
`tests/test_v10_lineup_providers.py` pins `[news]` through `patch_view`
so the machine's overlay cannot reach it. A `slow` marker on the MILP and
LightGBM files; `-m "not slow and not golden"` documented as the inner
loop; `filterwarnings` for the PuLP deprecation with a note to migrate at
PuLP 4. `scripts/archive/` for the six drivers only closed specs
reference; the ten test-imported one-offs stay. A trimmed
`tests/data/gw2-advice.json` so `test_report.py` and `test_chip_sanity.py`
run on a clone. The 176 KB prose fixture regenerated with three-player
XIs. A `--help`-plus-stubbed-run smoke test for the six untested CLI
commands.

*Gate.* `uvx ruff check src tests` → 0 under the committed config, with
the ignore list in the spec. Meta-rail: a scratch test asserting
`len(JOB_KINDS) == 12` makes the new rail fail (mutation shown).
`test_advise_order.py` fails when two seams are swapped in a scratch
copy. `pytest -q -m "not slow and not golden"` under three minutes on this
machine and warnings under 100. `pytest -q` with `reports/` renamed away →
no new skips. Suite count reported before and after with the deleted
copies named. Verdict: all lines.

*Protected files.* Every `tests/test_v*_degradation.py` and
`tests/test_web_job_kinds*.py` touched for the pin collapse, and
`tests/test_advise.py`: orchestrator, pin-only commit.

### v18h — the docs, true

*What.* Every line of review §4, closed or explicitly kept: `CLAUDE.md`
(the orchestrator-only list gains `tests/test_served_plan.py`,
`tests/test_golden_board.py`, `tests/test_pipeline.py` and
`tests/golden_client.py`, or the spec says why not; the gate command
carries `-rs`; the pins table; the commands block); `docs/GUIDE.md`
(horizon "default 3, this machine runs 6"; the fitted blend; fourteen
settings; `core-insights` in §8; §11 to v18h; §12 rewritten as of v18h with
the closed residuals removed and the filled data-gated rows ticked; the
17→13/14 count settled from the v17h spec); `README.md` cut to setup and
reference (a five-line install block, `config.example.toml` named, the
deleted names gone, the Tests section from `CLAUDE.md`, `gaffer brief` in
the table, the cycle diary replaced by a pointer at the GUIDE);
`ROADMAP.md` ("Where things stand" leading with the current numbers, the
install box ticked, the three met rows ticked, the 09-04 items as
candidates 11–13 with the research files named by path, the §6 replay in
the Open index, the v18 block with the programme's closing ledger); the v11
spec's Outcomes written from its ROADMAP block; the v7/v7b "pending" lines
closed. The user's three decisions recorded (ruling 12).

*Gate.* A checklist in the spec with one row per review §4 line and a
column for the commit that closed it or the sentence that keeps it; the
suites green; `README.md` under 700 lines; every command in `CLAUDE.md`
run once and its output pasted into the spec's outcome. Verdict: no row
blank.

---

## 3. What every sub-cycle does the same way

Unchanged from the v17 programme (`plans/2026-09-07-v17-deepening-programme.md`
§2), with four additions learned there: **mutation-test every new rail
before trusting it**; **one committing agent at a time**; **a "no diff"
needs a same-code control** (shoot the control second when the first pair
differs); and **give implementers a "where your judgement is wanted"
section**, because the v17h sketch had two bugs the implementer found only
because it was told the sketch was not sacred.

Pins for the programme: routes **51**, job kinds **12**, `Config` fields
**62**. None is expected to move. The security rule stands: the odds key
by name only, `[odds] api_key`; subagents never open `config.toml`.

---

## 4. Out of scope, by name

- **The model cycle**: the bonus head seeing `e_goals`/position; bounding
  `p_cs_model`/`e_gc_model`; changing the odds-blend gate; `p_play` top-bin
  recalibration; the K ≥ 5 role replay; the news ablation. Each moves a
  served number and needs a replay under CONVENTIONS §9. The ROADMAP
  already names this as the cycle after; v18c banks the pre-blend column
  so that cycle can measure from day one.
- **`gaffer/ledgers.py`** unifying the five scoring modules. v18c captions
  the two surfaces; the unification is a candidate with a spec of its own.
- **A logging module** replacing 256 `print`s. The job UI reads that
  stream; changing it is a surface change with screenshots, not a polish.
- **A top-10k threshold scrape, the blended league stance, the in-app
  chat**: unchanged from the ROADMAP's candidate list.
- **The security incident** (`dd47c0a`): the rotation and any history
  rewrite are the user's; v18h records the answer.
- **Deleting the 31 fully-merged branches**: put to the user in v18h; the
  command is one line and reversible only from reflog.

---

## 5. Self-review

*Placeholders:* none; every sub-cycle has a gate with a verdict rule.
*Consistency:* ruling 1 and v18a's gate describe the same behaviour; ruling
3 and v18b's golden expectation agree (no key when HiGHS solves); ruling 11
corrects the review's own docs finding on the backtest default.
*Scope:* eight sub-cycles is the v17 size and rhythm; v18f is the largest
and could split at the component cuts if it runs long. *Ambiguity:* the
"stale fails" option was the one the user overruled; ruling 1 records the
choice and the reason. *Status:* the spec was reviewed and approved by the
user on 2026-09-12; the programme runs in one session, subagent-driven,
with per-sub-cycle specs kept short (gate first, outcome last) and the
programme's §3 task lists serving as each sub-cycle's plan, to keep usage
low as the user asked.
