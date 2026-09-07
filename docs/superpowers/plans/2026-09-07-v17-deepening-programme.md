# v17 — the deepening programme

> **For agentic workers:** this is a *programme*, not a task plan. Each
> sub-cycle below (v17a … v17h) gets its own chat, its own spec, its own plan
> and its own branch, run the house way: grilling → spec with the gate written
> first → plan → superpowers:subagent-driven-development → gates → ff-merge →
> push → security ritual → docs → the tracker. Paste the **Prompt** block of
> the sub-cycle you are starting into a fresh chat. Nothing else from an
> earlier chat is needed.

**Goal:** turn the seven candidates of the 2026-09-07 architecture review
(`docs/superpowers/research/2026-09-07-architecture-review.html`) into
merged code without changing a single number the advice serves.

**Architecture:** deepen shallow modules one at a time, in dependency order,
behind a golden board that proves each refactor is a no-op on the artifact.
Vocabulary is the review's: *module, interface, implementation, depth, seam,
adapter, leverage, locality*; the deletion test; one adapter is a
hypothetical seam, two is a real one.

**Tech stack:** unchanged. Python 3 `src/gaffer`, pytest; React 18 + TS +
Tailwind v4 + vitest in `frontend/`.

**Tracker:** `docs/superpowers/plans/2026-09-07-v17-tracker.md` — the one
checklist every chat updates on merge.

---

## 1. Order and dependencies

Strictly sequential. One branch in flight at a time, ff-merged before the
next starts. The reasons are concrete: four sub-cycles edit
`src/gaffer/web/schemas.py` and regenerate the whole of `schemas.json` and
`types.generated.ts`; pins move in their own commits and a second branch
would rebase over every one; v17f and v17g both live in `advise.py`.

| Sub-cycle | Candidate in the review | Depends on | Size |
|---|---|---|---|
| v17a | 6 — the wire types, one command | — | ½ day |
| v17b | 2 — restraint narrated once, on the server | v17a (schema change) | 1 day |
| v17c | the golden board harness (new; not in the review) | — | 1 day |
| v17d | 4 — one weekly pipeline module | v17c (its gate) | 1 day |
| v17e | 5 — the config in force, one interface | v17b (LadderCard), v17c | 2 days |
| v17f | 1 — the served plan, owned once | v17a, v17b, v17c | 3 days |
| v17g | 3 — build_advice as a pure module | v17d (one caller), v17f (output type) | 3 days |
| v17h | 7 — This Week's data fetched once; one job hook | v17f (payload shapes settle) | 2 days |

v17c and v17a have disjoint files and could run in parallel in two worktrees.
Do not: the gain is a day and the cost is a rebase over generated files.

---

## 2. What every sub-cycle does the same way

**Read first, in this order.** `CLAUDE.md`; this file, sections 2 and the
sub-cycle's own; the review card (anchor `#c<n>` in the HTML);
`docs/superpowers/plans/2026-09-07-v17-tracker.md` for the hand-off notes
the previous chat left; `docs/superpowers/CONVENTIONS.md`.

**Branch.** `v17<letter>-<slug>` off `main` at the hash the tracker's ledger
shows for the previous row. Never on `main`.

**Spec.** `docs/superpowers/specs/2026-09-07-v17<letter>-<slug>-design.md`,
via superpowers:brainstorming with the grilling walked for the deepened
interface: constraints, what sits behind the seam, how many adapters, what
tests survive, what tests die. The spec states the gate and its verdict rule
before anything runs (CONVENTIONS §2), and names every protected file the
work touches with the ruling (CLAUDE.md, *Pins and protected files*).

**Plan.** `docs/superpowers/plans/2026-09-07-v17<letter>-<slug>.md` via
superpowers:writing-plans. Tasks that touch a protected file, a pin, or run a
gate are the orchestrator's; the rest go to Opus implementers with a spec
review and a code review between tasks.

**Gate.** The orchestrator runs it, never the implementer (CONVENTIONS §7).
Every gate in this programme is one of two kinds:

- *Golden board* (v17d–v17g): `.venv/bin/pytest -q tests/test_golden_board.py`
  passes on the branch with the golden files untouched, and the verdict rule
  says which keys may differ (usually none). Built by v17c.
- *Surface* (v17a, v17b, v17e, v17h): the suites, a named rail that pins the
  new rule, and screenshots through `frontend/scripts/shots.sh v17<letter>`
  approved by the user in the companion.

A refactor that "should not change anything" is gated by showing the lever
was exercised, not by an empty diff on an empty board (CONVENTIONS §10). The
golden board is chosen to carry a restraint step, a hit, a chip row and a
league tilt for that reason.

**Merge.** ff-merge only, after the gate and the user's approval. Then push,
then the security ritual from `CLAUDE.md` (both greps and the `git show`),
every time.

**Record.** In this order: the spec's §Outcome with the gate numbers; the
ROADMAP block `### v17<letter> — <name> (done, merged <hash> <date>)` under
Shipped with pins and suite sizes; one line in `docs/GUIDE.md` §11; the
tracker row and its hand-off note; the memory file's v17 line.

**Pins.** Routes 51, job kinds 12, `Config` fields 59 at the start of the
programme. A sub-cycle that moves one says so in its spec, bumps it in its
own commit, and writes the new value into the tracker's ledger. Never add a
job kind.

**Security.** The odds key lives only in the untracked `config.toml`. Refer
to it by name (`[odds] api_key`), never its value, in any file, prompt, plan
or summary. Subagents never open `config.toml`.

---

## 3. The sub-cycles

### v17a — the wire types, one command

**Card:** `#c6`. **Files:** `scripts/gen_types.py`, `frontend/package.json`,
`frontend/src/types.generated.test.ts`, `CLAUDE.md`,
`tests/test_v12_w5_gen_types.py`.

**Deepened interface.** `npm run types` writes `schemas.json` and
`types.generated.ts` from one `OPTIONS`; `npm run types -- --check` exits 1
on drift and 0 otherwise. `frontend/src/types.ts` stays hand-written; its
narrowings are a real seam with a written reason per model and are out of
scope.

**Out of scope.** Any change to what the schema contains. Generating
`types.ts`.

**Gate (surface).** Verdict rule, all three must hold:
1. Hand-edit one line of `types.generated.ts`; `npm run types -- --check`
   exits 1 and names the file. Run `npm run types`; the check exits 0 and
   `git diff --stat` is empty.
2. `tests/test_v12_w5_gen_types.py` and `types.generated.test.ts` pass with
   `OPTIONS` defined once and imported by the test.
3. `CLAUDE.md`'s regeneration block is one command.

**Pins.** None move.

**Prompt.**

```
Start sub-cycle v17a of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17a, then card #c6 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md.
Branch v17a-types off main. Brainstorm and grill the interface (one command,
one OPTIONS, a --check mode), write the spec with the gate in section v17a
stated before anything runs, write the plan, then run it subagent-driven:
Opus implementers, Fable spec review and code review between tasks. Run the
gate yourself. On pass: ff-merge, push, the security ritual from CLAUDE.md,
then the spec outcome, ROADMAP block, GUIDE §11 line, tracker row and
hand-off note, memory. The odds key: by name only, never its value.
```

---

### v17b — restraint narrated once, on the server

**Card:** `#c2`. **Files:** `src/gaffer/ladder.py` (not protected; the
served `restraint` block is built in its `serve_rung`, and `advise.py`,
which is protected, only passes it through), `src/gaffer/brief.py`, `src/gaffer/cli.py`, `src/gaffer/web/routers/ladder.py`,
`src/gaffer/web/schemas.py`, `frontend/src/hubs/this-week/MovesCard.tsx`,
`frontend/src/hubs/this-week/LadderCard.tsx`, their tests,
`tests/test_v16_ladder.py`.

**Deepened interface.** Every rung the server serves carries `label`; every
step carries `line` beside the `reason` it already carries; the `restraint`
block carries `hit_cost` and `line`. `rung_label`, `restraint_line`,
`objective_line`, `served_note` and the brief's `_pct` become the
implementation behind those fields. Both TS `rungLabel` functions, `stepText`
and the `hits * 4` literal in MovesCard are deleted; the cards render
strings.

**Out of scope.** Changing which rung is served or any number. Moving the
ladder into the ServedPlan (that is v17f).

**Gate (surface + artifact).** Verdict rule, all four must hold:
1. On the current board, `gaffer advise --fast` before and after the branch
   writes advice JSON whose diff, restricted to keys that existed before, is
   empty. New keys (`label`, `line`, `hit_cost`) are the only additions.
2. A new rail asserts the CLI's restraint line, the ladder route's labels,
   MovesCard's text and LadderCard's text for the served rung are the same
   string, for every rung key in `RUNG_ORDER`.
3. `grep -rn "rungLabel\|hits \* 4" frontend/src` prints nothing.
4. Screenshots `this-week` and `this-week-lower`, dark and light, approved.

**Pins.** None move. Schema change → `npm run types`.

**Prompt.**

```
Start sub-cycle v17b of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17b, then card #c2 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md (v17a's
hand-off note says how to regenerate types). Branch v17b-restraint-prose off
main. Grill the deepened interface (the rung carries its own name; the step
its own line; the restraint block its hit cost) and which of ladder.py's
helpers become implementation. Spec with the four-part gate stated first,
plan, subagent-driven implementation; advise.py is orchestrator-only, so if
the served block needs a change there, that diff is yours. Run the gate
yourself, including the before/after artifact diff and the screenshots
through the companion. On pass: ff-merge, push, security ritual, docs,
tracker. The odds key: by name only, never its value.
```

---

### v17c — the golden board harness

**Card:** none; this is the gate tool for v17d–v17g. **Files:**
`tests/data/golden_board/` (recorded FPL responses for one gameweek, the
entry's picks, the league standings), `tests/golden_client.py` (a recorded
`FPLClient` adapter), `tests/test_golden_board.py`,
`reports/`-shaped goldens under `tests/data/golden_board/expected/`.

**Deepened interface.** `RecordedClient(dir)` is the second adapter behind
the seam `run_advise(cfg, client)` already has (the first is the live
`FPLClient`); one adapter was a hypothetical seam, two make it real.
`golden_config()` returns the `Config` the golden was recorded under: news
off, `scenarios_seed` fixed, `scenarios_n` at the shipped value, the odds
section absent, the caps and `hit_bar` at values that make the walk take at
least one step and refuse at least one. The test runs `run_advise` and
compares the advice JSON and the solve state to the expected files with
`generated_at` and every path stripped.

**What the golden must carry** (CONVENTIONS §10, the lever verified): at
least one restraint step taken and one refused, an objective with ≥1 hit, a
chip row, a league tilt, a bench with a vice, and a plan of six weeks. Choose
the recorded gameweek and the caps until it does; write the counts into the
golden's header.

**Models.** `run_advise` loads `models/*.joblib`, which are untracked. The
test records the SHA-256 of every model file it used in the golden's header
and *skips* with that reason when the files on disk differ or are absent. So
the gate runs on the machine that recorded it, and a retrain invalidates the
golden knowingly (re-record, in its own commit, with the reason). v17g
removes this limit by recording at the `Inputs` level.

**Out of scope.** Any change to `advise.py`. Any change to how tests are
run in CI.

**Gate.** Verdict rule: `.venv/bin/pytest -q tests/test_golden_board.py`
passes twice from a clean checkout with the same models; the header's lever
counts are all ≥ 1; the fixture directory is under 5 MB; the security grep
finds nothing in the recorded responses (an entry id is fine, the key is not
there because the odds section is absent).

**Pins.** None move. No new route, kind or field.

**Prompt.**

```
Start sub-cycle v17c of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17c, then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md.
There is no review card; this builds the golden board that gates v17d–v17g.
Branch v17c-golden-board off main. Grill the recorded-client adapter and
golden_config; spec with the gate stated first (the lever counts the golden
must carry, the model-hash skip rule); plan; subagent-driven implementation.
Recording the responses and choosing the gameweek and caps is yours, not an
implementer's, and you run the gate. Do not edit src/gaffer/advise.py. On
pass: ff-merge, push, security ritual, docs, tracker; the hand-off note must
say how to re-record after a retrain. The odds key: by name only, never its
value; the recorded config has no [odds] section.
```

---

### v17d — one weekly pipeline module

**Card:** `#c4`. **Files:** new `src/gaffer/pipeline.py`,
`src/gaffer/web/routers/advice.py`, `src/gaffer/web/job_kinds.py`,
`src/gaffer/cli.py` (`advise`, `brief`), `scripts/com.gaffer.advise.plist`
(unchanged if the CLI now chains the brief), `tests/test_v16_restraint.py`
(the CLI pins), new `tests/test_pipeline.py`.

**Deepened interface.** `pipeline.weekly_run(cfg, *, client=None, log=print)
-> RunResult` runs train → advise → render → brief and returns what each step
produced, never raising past the brief (which already never raises). The CLI
`advise` command, the `train_and_advise` job kind and therefore launchd all
call it. `routers/advice.py` keeps request handling only and is no longer
imported by `job_kinds.py`.

**Out of scope.** Changing any step's behaviour. A new job kind (the pins
forbid it; the pipeline is a function, not a kind).

**Gate (golden board + parity).** Verdict rule:
1. `tests/test_golden_board.py` passes unchanged.
2. A parity test runs `weekly_run` through the CLI entry and through the job
   kind on the golden board with `news_llm_command` pointed at a stub that
   prints fixed prose; both produce identical advice JSON and a brief that
   passes `check_brief`.
3. `grep -rn "routers.advice" src/gaffer/web/job_kinds.py` prints nothing.
4. The Thursday plist unchanged still yields a brief (the CLI chains it), and
   GUIDE §12.4's open note about the plist is closed.

**Pins.** Job kinds 12 unchanged (assert it in the spec). Routes unchanged.

**Prompt.**

```
Start sub-cycle v17d of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17d, then card #c4 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md (v17c's
note says how the golden board runs). Branch v17d-pipeline off main. Grill
the interface pipeline.weekly_run(cfg) -> RunResult and what each caller
keeps; spec with the four-part gate stated first, including the stubbed LLM
command; plan; subagent-driven implementation. web/jobs.py and cli's
protected pins are orchestrator-only: those diffs are yours. Run the gate
yourself. On pass: ff-merge, push, security ritual, docs (close the GUIDE
§12.4 plist note), tracker. The odds key: by name only, never its value.
```

---

### v17e — the config in force, one interface

**Card:** `#c5`. **Files:** `src/gaffer/config.py`,
`src/gaffer/web/settings_keys.py`, `src/gaffer/web/routers/settings.py`,
`src/gaffer/web/routers/meta.py`, the four modules that open `config.toml`
themselves (listed at `config.py:323-336`), `src/gaffer/web/schemas.py`
(settings rows gain `options`), `frontend/src/hubs/this-week/LadderCard.tsx`,
`frontend/src/hubs/model/SettingsTab.tsx`, `tests/test_v13_degradation.py`
only if a field count moves.

**Deepened interface.** `config_in_force() -> Config` is the one read, cached,
with `invalidate()` the one clearing; the four private readers become
accessors on the returned view (or fields, if the grilling decides so, which
moves the `Config` pin). `SettingKey` gains `options` and imports its bounds
from `config`'s constants; the one refusal sentence lives in `config.py`.
LadderCard renders its selects from the `/api/settings` rows it already posts
to; `HIT_BARS`, `NO_CAP` and the `?? 0.6` default leave the card.

**Out of scope.** Renaming any TOML key. The settings overlay's file format.

**Gate (golden board + surface).** Verdict rule:
1. `tests/test_golden_board.py` passes unchanged.
2. A rail asserts that no module outside `config.py` opens `config.toml` or
   `config.local.toml` (grep over `src/gaffer`), that every `WHITELIST`
   entry's bounds equal the `config` constants, and that every entry reads
   and writes through the one interface.
3. `grep -n "HIT_BARS\|NO_CAP\|?? 0.6" frontend/src/hubs/this-week/LadderCard.tsx`
   prints nothing; the card's selects show server-supplied options in a test.
4. Screenshots `this-week-lower` and `settings`, dark and light, approved.

**Pins.** `Config` fields 59 unless the grilling turns the four readers into
fields (then bump in its own commit and record). Routes unchanged.

**Prompt.**

```
Start sub-cycle v17e of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17e, then card #c5 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md. Branch
v17e-config-in-force off main. Grill the one read interface and one
invalidation, whether the four private readers become fields (which moves
the Config pin) or accessors, and SettingKey.options. Spec with the four-part
gate stated first, plan, subagent-driven implementation; test_v13 and the
Config pin are orchestrator-only. Run the golden board and the screenshots
yourself. On pass: ff-merge, push, security ritual, docs, tracker. The odds
key: by name only, never its value; subagents never open config.toml.
```

---

### v17f — the served plan, owned once

**Card:** `#c1`. **Files:** `src/gaffer/advise.py` (protected),
`src/gaffer/ladder.py` (`serve_rung`), `src/gaffer/artifacts.py`,
`src/gaffer/web/routers/plan.py`, `src/gaffer/web/routers/meta.py`,
`src/gaffer/tracking.py`, `src/gaffer/web/schemas.py`,
`tests/test_v16_restraint.py` (protected pins), `tests/test_advise.py`
(protected), `tests/test_v12_w5_plan_trace.py`, new
`tests/test_served_plan.py`.

**Deepened interface.** `ServedPlan` (a frozen dataclass or pydantic model)
owns `weeks`, `moves`, `bank` per week, `restraint`, `objective` and the
`trace`; `serve_rung(ladder, objective) -> ServedPlan`; advise writes it
whole; `artifacts.served_plan(gw) -> ServedPlan` reads it back, and
`artifacts.advice_gws()` enumerates. `routers/plan.py` becomes a shape
adapter: no coercers, no bank recurrence, no second trace. `meta.py` and
`tracking.py` stop knowing the filename.

**Out of scope.** Changing which rung is served, the trace's accounting, or
the ladder's walk. The pure `build_advice` split (v17g).

**Gate (golden board + route parity).** Verdict rule:
1. `tests/test_golden_board.py` passes unchanged on every pre-existing key of
   the advice JSON; new keys are listed in the spec.
2. `GET /api/plan/{gw}` on the golden board, recorded before the branch,
   equals the response after, byte for byte after `generated_at` is stripped.
3. `tests/test_v16_restraint.py`'s source-order pins are replaced, in a
   commit that names the ruling, by a round-trip test (build → write → load →
   equal) in `tests/test_served_plan.py`.
4. `grep -rn "advice.json" src/gaffer --include=*.py` matches only
   `artifacts.py`.

**Pins.** Routes 51 unchanged. The v16 pins move by ruling, recorded.

**Prompt.**

```
Start sub-cycle v17f of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17f, then card #c1 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md, where
v17b's note names the restraint fields and v17c's the golden board. Branch
v17f-served-plan off main. Grill the ServedPlan interface and what the plan
router keeps; decide with the user whether ServedPlan is a dataclass or a
pydantic model (it is on the wire). Spec with the four-part gate stated
first, including the recorded /api/plan response; plan; subagent-driven
implementation. advise.py, serve_rung's return, test_advise.py and the v16
pins are orchestrator-only: those diffs and the ruling commit are yours. Run
the golden board yourself. On pass: ff-merge, push, security ritual, docs,
tracker. The odds key: by name only, never its value.
```

---

### v17g — build_advice as a pure module

**Card:** `#c3`. **Files:** `src/gaffer/advise.py` (protected; split into
`gather_inputs` and `build_advice`), new `src/gaffer/inputs.py` (the frozen
`Inputs` and the `Predictions` / `Solver` protocols), `tests/test_advise.py`
(protected; the 35 `getsource` pins), `tests/test_golden_board.py`,
`tests/data/golden_board/inputs/` (the recorded `Inputs`), `src/gaffer/pipeline.py`.

**Deepened interface.** `gather_inputs(cfg, client) -> Inputs` does every
fetch, every model load and every prediction; `build_advice(inputs, cfg) ->
ServedPlan` does every solve, the alt plans, the ladder, `serve_rung` and the
state, with no file or network access. `run_advise` is the composition and
is what `pipeline.weekly_run` calls. Two adapters per new seam: the live
predictor and a recorded `Inputs`; the HiGHS solver and the CBC fallback
already present.

**Out of scope.** Any change to a solve. The replay driver (it does not use
`run_advise`; assert that in the spec).

**Gate (golden board, now without models).** Verdict rule:
1. `tests/test_golden_board.py` passes unchanged through `run_advise`.
2. A second golden test runs `build_advice` on the recorded `Inputs` and
   equals the same expected files, and does *not* skip when `models/` is
   absent (move the models to a temp name and run it).
3. `tests/test_advise.py`'s `getsource` pins are replaced, in a commit that
   names the ruling, by tests over `build_advice`; the count of
   `inspect.getsource` in that file falls to 0.
4. `grep -n "open(\|Path(\|client\." src/gaffer/advise.py` inside
   `build_advice` prints nothing.

**Pins.** None move. The protected-file rule for `advise.py` stays; what
changes is that its body is now tested through an interface.

**Prompt.**

```
Start sub-cycle v17g of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17g, then card #c3 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md (v17f's
note names ServedPlan; v17c's the golden board). Branch v17g-build-advice
off main. Grill the Inputs shape and the two protocols; the spec states the
four-part gate first, including the models-absent run. Plan; subagent-driven
implementation for inputs.py and the golden's Inputs recording; every line of
advise.py and test_advise.py is yours, one task at a time, golden green after
each. On pass: ff-merge, push, security ritual, docs, tracker. The odds
key: by name only, never its value.
```

---

### v17h — This Week's data fetched once; one job hook

**Card:** `#c7`. **Files:** `frontend/src/api/` (`usePageData.ts` new,
`useJob.ts`, `useJobStream.ts`), `frontend/src/kit/JobButton.tsx`,
`frontend/src/hubs/ThisWeek.tsx`, `frontend/src/hubs/this-week/*.tsx`,
`frontend/src/hubs/Planning.tsx`, `Players.tsx`, `League.tsx`, their tests.

**Deepened interface.** `usePageData(gw)` holds one in-flight request per
endpoint, shared across hubs; `squadRows(advice, players, components)` is a
pure function with its own table-driven test; `useJob({ kind } | { path })`
streams when a stream exists and polls otherwise, with one recovery probe.
`capLine` prop-drilling goes.

**Out of scope.** Any server change. Any visual change: the screenshots must
match the v17e set.

**Gate (surface).** Verdict rule:
1. `ThisWeek.test.tsx` renders the hub with at most three mocked endpoints.
2. A vitest fetch counter shows This Week's first render issues each endpoint
   once; the count before and after is written in the spec.
3. `grep -rn "useJobStream" frontend/src --include=*.tsx` matches only the
   hook's own file and test.
4. Screenshots of all six hubs, dark and light, approved and visually
   identical to v17e's set.

**Pins.** None move. Frontend suite size recorded.

**Prompt.**

```
Start sub-cycle v17h of the deepening programme. Read CLAUDE.md, then
docs/superpowers/plans/2026-09-07-v17-deepening-programme.md sections 2 and
v17h, then card #c7 of docs/superpowers/research/2026-09-07-architecture-review.html,
then the tracker docs/superpowers/plans/2026-09-07-v17-tracker.md. Branch
v17h-page-data off main. This candidate is marked Speculative: grill first
whether per-card fetching is deliberate for cards that reload after a job,
and record the answer in the spec before designing usePageData and the one
useJob. Spec with the four-part gate stated first, plan, subagent-driven
implementation. Run the fetch count and the six-hub screenshots yourself.
On pass: ff-merge, push, security ritual, docs, tracker, and close the
programme: the ROADMAP's v17 block gets the ledger table. The odds key: by
name only, never its value.
```

---

## 4. When a sub-cycle fails its gate

Ship nothing. Record the numbers in the spec's §Outcome, leave the branch,
write the tracker's hand-off note with what was learned, and move to the
next sub-cycle only if it does not depend on the failed one. A failed
refactor is not shipped off behind a flag (CONVENTIONS §6 is for arms with a
measured effect; a refactor has none to keep).

## 5. Self-review

Spec coverage: seven cards → seven sub-cycles, plus the harness they need.
Placeholder scan: every gate has a verdict rule with a command or a grep.
Type consistency: `ServedPlan` is named the same in v17f and v17g;
`weekly_run` the same in v17d and v17g; `RecordedClient` and
`golden_config` the same in v17c, v17d, v17g.
