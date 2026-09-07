# gaffer v17b — restraint narrated once, on the server

*Brainstormed and approved 2026-09-08 in the terminal, the second sub-cycle
of the v17 deepening programme
(`docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`, card `#c2`
of the 2026-09-07 architecture review). A prose cycle: no number the advice
serves changes, no route, no job kind, no `Config` field. The schema gains
two string fields and `npm run types` runs once.*

## 0. Why

The rung's name and the step's sentence are written in four places today
(2026-09-08, `main` at `2290a93`):

- `src/gaffer/ladder.py`: `rung_label` ("free transfers only"),
  `restraint_line`, `objective_line`, `served_note`.
- `frontend/src/hubs/this-week/MovesCard.tsx`: its own `rungLabel`
  ("Free transfers only"), `restraintText` (a different sentence shape from
  the CLI's), and `−${hits * 4} pts`.
- `frontend/src/hubs/this-week/LadderCard.tsx`: a second `rungLabel`
  ("No hits"), `stepText`.
- `src/gaffer/brief.py`: `rung_label` again for the facts, its own step
  projection, and `hit_points: hits * 4`.

The CLI, the brief and the two cards already disagree on the name of the
rung the advice serves, and two of the three hit prices are a literal that
the solver's `hit_cost` does not control. The review's deletion test: delete
`rung_label` and every surface still prints a name, each its own. That is
the shallow module.

## 1. The decisions the user made

1. **Lowercase prose is the label**: `bank`, `free transfers only`,
   `1 hit`, `2 hits`, `3 hits`, `no cap`. The CLI's and the brief's spelling
   today; the ladder table's Rung column and the moves card go lowercase,
   matching the lowercase chips beside them. "No hits" and "Free transfers
   only" disappear. No protected assertion string moves.
2. **The served `restraint.line` is the v16 CLI sentence, prefix included**:
   `restraint: free transfers only; the step to 1 hit was refused, 45% —
   Dubravka is 14% to play`. The CLI and MovesCard print it verbatim. The
   protected pin's string is unchanged; its fixture gains `line`.
3. **No client-side hit price.** MovesCard prints `hits × restraint.hit_cost`
   when the block carries a cost and the count alone when it does not (an
   advice banked before v16). The CLI and the brief read the served cost
   too, falling back to `Config`'s own default field, never a literal.
4. **The brief's facts carry each step's served `line`** (`{line, taken}`),
   not a second projection. `BRIEF_PROMPT_VERSION` goes 2 → 3.

## 2. Approach, and the two rejected

**Every string is born in `ladder.py` (chosen).** `build_ladder` writes
`label` on every rung and `line` on every step; `serve_rung` writes
`label`, `hit_cost` and `line` on the restraint block and `line` on the
objective block. Every consumer renders the string it is given. The four
helpers become private functions of `ladder.py` with one caller each.

*A prose module (rejected).* A new `src/gaffer/prose.py` holding the
labels and sentences, imported by the CLI, the brief and the router. That
is the same four dialects with a shared dictionary: each surface still
composes, and the browser cannot import it, so the two TS `rungLabel`s
would stay.

*Type the block in pydantic now (rejected).* `AdviceLatest.advice` is
`dict[str, Any]` on the wire and the restraint block is typed only in the
hand-written `frontend/src/types.ts`. Declaring `Restraint` models in
`schemas.py` this cycle would generate types nothing on the server
validates against; v17f types the served plan whole. `types.ts` gains the
optional fields.

## 3. The interface

### 3.1 The ladder payload (`build_ladder`, `LadderRung`, `LadderStep`)

- Every rung, distinct or `same_as`, carries `label: str` — the key's name
  in prose, from the one private table.
- Every step carries `line: str` beside `reason`:
  `"{below label} → {above label}: {taken|refused}, {share%} — {reason}"`,
  which is LadderCard's `stepText` today with the server's labels, e.g.
  `bank → free transfers only: taken, 72% — a Bench Boost is planned for
  GW6`.
- `load_ladder` backfills `label` and `line` on a banked ladder written
  before this cycle, so the route and the brief never see a rung without
  a name. A ladder written by this cycle is served as written.
- `LadderRung.label: str = ""` and `LadderStep.line: str = ""` in
  `schemas.py`, with docstrings citing v17b §3.1. `npm run types` once.

### 3.2 The served plan's blocks (`serve_rung`)

`serve_rung(ladder, objective, *, hit_cost: int, captain_note)` — the cost
per hit is an explicit argument, because the served block prices hits and
a ladder that did not build carries no cost of its own. The `restraint`
block becomes:

| key | value |
|---|---|
| `chosen`, `bar`, `steps`, `agrees`, `note` | unchanged |
| `label` | the chosen rung's label, `None` when `chosen` is `None` |
| `hit_cost` | the `hit_cost` argument, always present |
| `line` | the CLI sentence: `restraint: {label}; every step was taken`, or `restraint: {label}; the step to {above label} was refused, {share%} — {reason}`; when `chosen` is `None`, `restraint: {note}` |

Every `steps` entry carries the ladder's `line` (copied, not recomposed).

The `objective` block gains `line`: `the objective wanted: {buys} in;
{sells} out; {n} hit(s)`, `objective_line`'s sentence today.

### 3.3 The consumers

- **CLI** (`cli.py`): prints `restraint["line"]` when present, then
  `objective["line"]` when `agrees` is false. Its `Hits:` line prices
  `hits × cost`, where `cost` is the block's `hit_cost` when the block is
  present and `Config.hit_cost`'s default otherwise (the v4c fixture has no
  block, and the default is 4, so the byte rail is unchanged).
- **Ladder route** (`routers/ladder.py`): unchanged in shape; `served_note`
  stays the one function it imports. Rungs and steps arrive labelled from
  `load_ladder`.
- **Brief** (`brief.py`): facts become
  `restraint: {chosen_label: block.label, bar_pct, line: block.line,
  steps: [{line, taken}]}`, `hit_points: hits × cost` with the same fallback
  as the CLI, and `objective.line` beside `objective.agrees`. `rung_label` is
  no longer imported. The prompt's step sentence reads "every step's line,
  taken or refused". `BRIEF_PROMPT_VERSION = 3`.
- **MovesCard**: renders `restraint.line` when present (any `line`, not
  only when `chosen` is set), `objective.line` when `agrees` is false, and
  the hits line as `{hits} hit(s): −{hits × hit_cost} pts` only when
  `restraint.hit_cost` is a number, else `{hits} hit(s)` alone. `rungLabel`
  and `restraintText` are deleted.
- **LadderCard**: `r.label` in the Rung column, in the `same_as` cell and
  in the cap note; `s.line` in the steps list. `rungLabel` and `stepText`
  are deleted. `capText`, `withCurrent`, `costText`, `RungCost` stay.
- **`types.ts`**: `Restraint` gains `label?: string | null`,
  `hit_cost?: number | null`, `line?: string | null`; `RestraintStep` gains
  `line?: string`; `Objective` gains `line?: string | null`. All optional,
  because advice history predates them.

## 4. What sits behind the seam

Behind `label`, `line` and `hit_cost`: the rung key grammar (`hits{n}`,
`open`), the singular/plural rule, the arrow and the punctuation of a step,
the percent rounding, the prefix `restraint:`, and which refused step a
line names (the first). A reader of any surface needs none of them.

`ladder.py` keeps, private: `_rung_label`, `_step_line`, `_restraint_line`,
`_objective_line`. `served_note` stays public with its one caller (the
route) and reads `_rung_label`. The brief's `_pct` stays for the sims and
bar shares; its step projection goes.

Adapters of the block: the CLI, the brief, MovesCard — three readers of one
string. Adapters of the rung label: the ladder route's card and the brief's
`chosen_label`. A change of wording is one edit in `ladder.py` and every
surface, including the rail, follows.

## 5. Tests

Survive unchanged: the walk and reason tests in `tests/test_v16_ladder.py`
(`test_every_step_earned_reaches_the_top` through
`test_a_price_flag_below_half_does_not_count`), the captain and vice cases
of `serve_rung` (updated only to pass `hit_cost=4`), the brief checker
cases in `tests/test_v16_brief.py`, LadderCard's cap, cost, rebuild and
settings cases.

Rewritten, same file:
- `test_v16_ladder.py`: `test_rung_labels` and `test_the_cli_lines` become
  tests over the served fields (`label`, `line`, `steps[*].line`,
  `objective.line`); `test_the_served_note_names_both_bars` unchanged in
  substance; `test_build_ladder_carries_the_bar_the_chosen_rung_and_the_steps`
  also asserts every rung's `label` and every step's `line`; a new case
  asserts `load_ladder` backfills a v16 file.
- `test_v16_brief.py`: `FACTS` and `test_build_facts_has_the_spec_shape_and_rounding`
  take the new `restraint` shape; the cache-key test's version.
- `MovesCard.test.tsx`: the restraint case passes `line`s and asserts the
  served strings; the hit price case passes `hit_cost` and a second case
  asserts no price without it.
- `LadderCard.test.tsx`: the fixture's rungs carry `label` and its steps
  `line`; assertions read lowercase labels and the served step lines.

New:
- `tests/test_v17b_prose.py` — the rail the gate names. For every key in
  `RUNG_ORDER` it builds a ladder whose walk stops on that rung, serves it
  through `serve_rung`, prints it through the CLI (`_cli` as in
  `test_v16_restraint.py`), serves the ladder through `GET /api/ladder`,
  and asserts: the CLI's line is `restraint.line`; every route rung's
  `label` equals the served block's for the chosen key and the private
  table's for the rest; every route step's `line` equals the block's. It
  also asserts the committed fixture
  `frontend/src/hubs/this-week/restraint-prose.fixture.json` equals what it
  built, and prints how to rewrite it (`python -m tests.test_v17b_prose
  --write`) when it does not.
- `frontend/src/hubs/this-week/restraint-prose.test.tsx` — reads the same
  fixture, renders MovesCard with each block and LadderCard with each
  payload, and asserts the restraint line, the Rung cells and the step
  lines are the fixture's strings character for character. That is the
  cross-language half of gate 2: the card renders what it is served.

Die: the direct tests of `rung_label`, `restraint_line`, `objective_line`
(the functions are private); `rungLabel`, `restraintText`, `stepText` have
no tests of their own to lose.

Protected file touched, by ruling: `tests/test_v16_restraint.py`'s two
CLI fixtures gain `line` (and `label`, `hit_cost`) because the CLI now
prints the served line rather than composing it; the asserted strings do
not change. The orchestrator makes that diff in its own commit.

## 6. Gate (surface + artifact), stated before anything runs

Run by the orchestrator on the branch after the suites are green. All four
must hold:

1. **The artifact diff.** `uv run gaffer advise --fast` was run on the
   unchanged tree (branch at `2290a93`, `main`'s tip) before any code
   changed, and its `reports/gw{N}-advice.json` and `ladder_gw{N}.json`
   copied aside. After the implementation the same command runs again. A
   script diffs the two advice files with `generated_at` and `deadline`
   stripped and every key that is new on the after side ignored; the
   verdict rule is that the diff restricted to keys that existed before is
   empty, and the set of new keys is exactly `{restraint.label,
   restraint.hit_cost, restraint.line, restraint.steps[*].line,
   objective.line}` on the advice and `{rungs[*].label, steps[*].line}` on
   the ladder. Because both runs read the live FPL API minutes apart, a
   difference in a key fed by live data (prices, availability, news, odds)
   is recorded with the key named and does not fail the gate on its own;
   any difference under `restraint`, `objective`, `buys`, `sells`, `hits`,
   `xi`, `bench`, `captain`, `vice`, `plan_by_gw` or `expected_pts` fails
   it.
2. **One string, four surfaces.** `.venv/bin/pytest -q tests/test_v17b_prose.py`
   and `npx vitest run src/hubs/this-week/restraint-prose.test.tsx` pass
   for every key in `RUNG_ORDER`.
3. **No client prose.** `grep -rn "rungLabel\|hits \* 4" frontend/src`
   prints nothing; `grep -n "stepText\|restraintText" frontend/src -r`
   prints nothing; `grep -rn "hit_points\|\* 4" src/gaffer/brief.py
   src/gaffer/cli.py` matches only lines that read a served or config cost.
4. **Screenshots** `this-week` and `this-week-lower`, dark and light, from
   `frontend/scripts/shots.sh v17b`, approved by the user in the companion.
   `shots.sh` gains a `v17b*` stage listing those two views;
   `this-week-lower` is the This Week page captured in a window tall
   enough (1400×3400) to reach the ladder card, its steps and notes.

Also required, not part of the verdict rule: `.venv/bin/pytest -q` and
`cd frontend && npx tsc --noEmit && npx vitest run` green, vitest's
`Errors` line absent; `npm run types -- --check` exits 0.

Verdict: pass if all four hold on the first run after the implementation is
complete. A failure is fixed on the branch and the gate is rerun in full;
§Outcome records every run.

## 7. Pins and protected files

None of routes 51, job kinds 12, `Config` 59 move. `tests/test_v16_ladder.py`
and `tests/test_v16_brief.py` are not on the orchestrator-only list.
Protected and touched by the orchestrator only: `src/gaffer/advise.py`
(one call site: `serve_rung(..., hit_cost=int(cfg.hit_cost), captain_note=
captain_note)`, placed so the v16 source pins still find `served =
serve_rung(ladder, dict(` and `captain_note=captain_note)` in that order)
and `tests/test_v16_restraint.py` (the fixtures, §5). `kit/tokens.test.ts`
scans the two cards; the fixture JSON is data and the new vitest file
carries no styling.

## 8. Process

Branch `v17b-restraint-prose` off `main` at `2290a93`. Plan at
`docs/superpowers/plans/2026-09-07-v17b-restraint-prose.md`. Server tasks,
frontend tasks and the rail go to Opus implementers with a Fable spec
review and code review between tasks; the protected diffs, the type
regeneration commit, the gate and the docs are the orchestrator's. Then
ff-merge, push, the security ritual, and the record in the programme's
order.

## 9. Out of scope

Which rung is served, any number, the walk, the reasons. Moving the ladder
into the served plan (v17f). Pydantic models for the advice's blocks.
`capText` and the cap selects (v17e). The HTML report template's hit
sentence (`report.html.j2`, a literal 4 of its own; the template is not a
surface the card names).
Advice history files: they keep their v16 shape and every consumer
degrades to it.

## 10. Outcome

_(written after the gate)_
