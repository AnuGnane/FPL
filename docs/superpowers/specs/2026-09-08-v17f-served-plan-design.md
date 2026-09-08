# v17f — the served plan, owned once

Sub-cycle six of the deepening programme
(`plans/2026-09-07-v17-deepening-programme.md` §3, review card `#c1` of
`research/2026-09-07-architecture-review.html`). Branch `v17f-served-plan`
off `main` at `cabc590` (v17e's docs commit over the merge `0f1a934`).

## 0. Why

"What does the user see for GW7?" is answered across four modules, and the
shape of a served week is written four times. `advise.py` hands
`serve_rung` an anonymous nine-key dict; `serve_rung` returns a thirteen-key
dict; `Advice` is splatted from it nine fields at a time; and
`routers/plan.py` re-parses the file with three coercers (`_int`, `_float`,
`_price`), prices every move from the pool a second time, runs the bank
forward because the artifact carries no money, and computes the trace
three times over — the served weeks, the objective's week, and never the
alternatives, whose banks it runs anyway. `meta.py` globs the advice
filename and `tracking.py` hard-codes it.

The deletion test: after this cycle `plan.py` is a shape adapter of about
forty lines with no arithmetic in it; the coercers, `_prices`, the bank
loop, `_trace_inputs`, `_thresholds`, `_price_falls`, `attach_trace` and
the `TRACE` flag are gone; `serve_rung` returns one typed value; the
advice filename is spelled in `artifacts.py` and nowhere else in
`src/gaffer`.

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

The orchestrator runs it on the branch; implementers never do. Four parts,
all required, in this order.

1. **Golden board, key-aware.** The branch's advice gains keys (§2.4), so
   the whole-dict equality in `tests/test_golden_board.py` cannot pass on
   the recorded `expected/advice.json` as it stands. The verdict rule:
   run the golden pipeline on the branch with the fixture untouched, strip
   exactly the new keys listed in §2.4 from the branch's advice with a
   scratchpad script whose key list is transcribed into §10, and the
   result must equal
   `expected/advice.json` byte for byte after `strip_volatile`; the solve
   state must equal `expected/solve_state.json` with nothing stripped;
   every lever count must equal the header's. Then `expected/advice.json`
   is re-recorded with `.venv/bin/python -m tests.golden_client --write`
   in its own commit whose subject says why, and
   `.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py`
   passes with none skipped. A key that differs in *value* fails the gate.
2. **Route parity.** Before any served-plan code changes,
   `tests/golden_client.py` learns to record `GET /api/plan/4` over the
   golden run into `expected/plan.json` (`generated_at` stripped, the
   `PlanTimeline` as the route serialises it), and `tests/test_golden_board.py`
   gains a golden-marked test that serves the route over the golden run and
   compares. That file is recorded on `main`'s code, in the first commit of
   the branch. The branch must reproduce it byte for byte; the file is not
   re-recorded in this cycle. Two runs of identical code differ in one
   player's EP by 0.01 on live inputs (v17b's lesson), which is why the
   route is served over the *recorded* client and the expected file is
   compared after the same `strip_volatile`.
3. **The v16 pins.** The three source-order tests in
   `tests/test_v16_restraint.py`
   (`test_advice_carries_the_two_blocks_with_safe_defaults`,
   `test_the_state_is_saved_then_the_ladder_then_the_served_plan`,
   `test_the_objective_dict_is_the_solvers_own_week_one`) are replaced, in
   one commit whose subject names this ruling, by the round-trip test in
   `tests/test_served_plan.py`: build a `ServedPlan`, write it the way
   advise writes (`json.dumps(asdict(Advice(...)))`), read it back through
   `artifacts.served_plan`, equal. The three CLI tests in that file stay.
4. **The filename.** `grep -rn "advice.json" src/gaffer --include='*.py'`
   matches only `artifacts.py`. Today it also matches `advise.py:1235`,
   `tracking.py:49`, `meta.py:125,229` and one docstring in
   `report/render.py:4`, which is reworded.

Then the suites (`.venv/bin/pytest -q`; `cd frontend && npx tsc --noEmit &&
npx vitest run`, reading vitest's `Errors` line as a failure), and
screenshots through `frontend/scripts/shots.sh v17f` (planning-board,
this-week) approved by the user.

## 2. The decisions the grilling settled

### 2.1 `ServedPlan` is pydantic, frozen

Chosen over a frozen dataclass for three reasons. The value comes off disk
written by whatever `gaffer advise` last ran, so one validation at the
loader replaces the router's coercers and per-field degradation. The v17b
hand-off asks this cycle to type the served plan whole for the frontend,
and a pydantic model is emitted into `schemas.json` and
`types.generated.ts` by the one command; a dataclass would need a pydantic
twin in `schemas.py`, the shape written twice again. And pydantic is
already a core dependency (`evaluation.py`, `optimize/chips.py`).

The cost: `Advice` stays a dataclass serialised by `asdict`, so a pydantic
value cannot nest inside it. The served fields stay flat on the advice
JSON, which the gate requires anyway, and `Advice` is built from one
`**served.model_dump()` rather than nine named splats.

### 2.2 The trace is computed at write time

The router's own docstring on `_price_falls` says the honest version
freezes what the solve saw and that only the writer can do it. Advise has
every trace input in hand (the pool, `opt_kw`, `ft_lambda`, the chip rows,
`lam`, `cover`, the price-fall table it charged) and computes the trace
once for the served weeks and the objective's week. The artifact carries
it; the router does no accounting. On the golden board the write-time and
read-time numbers are the same inputs through the same `trace_plan`, which
is what part 2 of the gate checks.

The write-time trace is guarded the way the read-time one was: a trace
that throws leaves `trace=None` on every week and prints one line; it never
fails the advice.

### 2.3 A file written before v17f is backfilled by the loader

`artifacts.served_plan(gw)` validates the file and, when it carries no
`price` on its moves, no `bank` on its weeks or no `trace`, loads the solve
state and runs the same `priced`, `banked` and `traced` functions advise
runs at write time. One implementation, two callers — the real seam. The
price-fall read for an old file is present tense, as it is today, and the
week note says so through the same `trace_plan` sentence. A file written
by this cycle is served as written; the solve state is not opened.

### 2.4 What the advice JSON gains, and what it keeps

Every pre-existing key keeps its value. New keys, all additive:

| Where | Key | Value |
|---|---|---|
| top level | `generated_at` | the run's ISO stamp, the same one the solve state carries; the loader need not open the state for a timestamp |
| top level | `bank` | the starting bank in millions (`SolveState.bank / 10`, one decimal), `None` when unknown |
| every week of `alternative_plans[*].plan_by_gw` | `price`, `hit_cost`, `chip`, `bank` | as `plan_by_gw`'s weeks; no trace |
| every move (`buys`, `sells`, `xi`, `bench`, `captain`, `vice`, and inside every week) | `price` | buy price for an in, sell value for an out, in millions; `None` when the pool cannot price it |
| every week of `plan_by_gw` | `hit_cost` | hits × the solve's price per hit |
| every week of `plan_by_gw` | `chip` | the chip table's `play_now` chip for that gameweek, or `None` |
| every week of `plan_by_gw` | `bank` | the bank after that week's moves, `None` from the first unpriced move on |
| every week of `plan_by_gw` | `trace` | the `PlanWeekTrace` block, or `None` |
| `objective` | `week` | the objective's week one as a week (priced, banked, traced), so the board's objective column is carried, not rebuilt |

The served alternatives keep the advice's own `alternative_plans` key and
`{gap, plan_by_gw}` shape: the JSON already has a top-level `alternatives`
key (the captain-alternatives table), and one key with new fields inside
it is one shape, not two. `xi` and `bench` moves gain `price` because they
go through the same `priced` pass; the head week's armband on the board is
the captain's `price`, which the router used to look up again.

The write is `model_dump(exclude_unset=True)`: a key the writer never set
is not on disk, so a move advise never tagged carries no `tag`, and the
XI's moves carry no `frequency`. A rail in `tests/test_served_plan.py`
pins it.

`strip_volatile` already strips `generated_at` at every depth, so the
golden comparison sees none of the timestamps.

### 2.5 The alternatives live inside `ServedPlan`

Each is its gap plus priced, banked weeks with no trace, typed from the
rows advise builds today under the same `alternative_plans` key, and
backfilled the same way. The router assigns the `Plan B` labels by position, which is
shape, and nothing else.

### 2.6 What the router keeps

`GET /api/plan/{gw}`: `served_plan(gw)`, a 404 naming the command on a
missing artifact, the map from `ServedWeek` to `PlanGw`, the armband on
the head week only, the labels, and the objective's week only when
`restraint.agrees` is `False`. The `PlanTimeline` schema and its four
models are untouched, so the wire is unchanged. `PlanMove.price`, `PlanGw.bank`
and `PlanGw.trace` are now copied from the served value rather than
computed.

### 2.7 The degradation ruling

The loader keeps every rule about *numbers*: an unpriced move blanks the
bank from that week on; an unknown bank or gap is `None`, never `0.0`; a
captain or vice that cannot name a player (absent, not a dict, no integer
code) is `None`, a missing armband and not a missing plan; a
week with no moves is a week with no moves. Every field but `gw` has a
default so a partial file — and every test fixture written against the
old router — loads.

What it drops is the tolerance for a file that is not the shape any
`gaffer advise` ever wrote: a non-numeric
`hits`, a plan entry that is not a dict, a chip table that is not a list, a
`gap` that is not a number. Such a file fails validation, and the route
answers 404 with the field named in the detail. The one older shape a real
writer produced — `plan_by_gw` keyed by gameweek — is accepted by a
before-validator on `plan_by_gw`.

### 2.8 `meta.py` and `tracking.py` stop knowing the filename

`artifacts.advice_gws() -> list[int]` enumerates the gameweeks with an
advice file, ascending. The history route iterates it and reads each
advice through `load_advice` as today. `update_health` takes the captain
code through `load_advice(gw)`, `0` when there is no advice or no captain;
`served_plan` there would trace a whole plan for one integer.

### 2.9 `gen_types.py` emits a re-exported model

The generator emits only models whose `__module__` is `schemas`. This
cycle adds one tuple to `schemas.py`, `WIRE_EXPORTS = (ServedMove,
ServedWeek, ServedObjective, ServedRestraint, ServedAlternative,
ServedPlan)`, and the generator includes a `BaseModel` named in it as if
it were defined there. `types.ts` drops its hand-typed `Restraint` and
`Objective` and takes the generated `ServedRestraint` and
`ServedObjective`; its `Advice` interface picks the served fields from the
generated `ServedPlan`. `schemas.json` and `types.generated.ts` are
regenerated and committed with the schema change.

## 3. Approach, and the two rejected

**Chosen.** A new core module owns the value and the three pure functions
that fill it; advise composes, the loader validates and backfills, the
router adapts shape. Two callers of one implementation for pricing, bank
and trace.

**Rejected: nest `served` under `Advice` as a block.** It would put the
served fields on the wire twice (flat for every existing reader, nested
for the new one) or move them, which breaks the golden's pre-existing
keys and every dict reader. The flat keys *are* the served plan; the
model's field names say so.

**Rejected: keep the trace at read time in the loader.** It keeps the
router honest but makes the loader open the solve state on every read and
leaves the price charge present tense for a fresh file, which the router's
own docstring calls the wrong answer.

## 4. The interface

`src/gaffer/served.py`, new. Frozen pydantic models
(`model_config = ConfigDict(frozen=True, extra="ignore")`):

```
ServedMove:        code, name, position, ep, price=None, tag=None, frequency=None
ServedWeek:        gw, hits=0, hit_cost=0, buys=[], sells=[], expected_pts=0.0,
                   chip=None, bank=None, trace: PlanWeekTrace | None = None
ServedObjective:   buys=[], sells=[], hits=0, expected_pts=0.0, line=None,
                   week: ServedWeek | None = None
ServedRestraint:   chosen=None, label=None, bar=None, steps=[], agrees=True,
                   note=None, hit_cost=None, line=None
ServedStep:        below, above, share, taken, reason="", reason_kind="", line=None
ServedAlternative: gap=None, plan_by_gw=[]
ServedPlan:        gw, generated_at=None, bank=None, buys=[], sells=[], hits=0,
                   xi=[], bench=[], captain=None, vice=None, captain_note=None,
                   expected_pts=0.0, plan_by_gw=[], objective=None,
                   restraint=None, alternative_plans=[]
```

`PlanWeekTrace` moves from `web/schemas.py` to `served.py` with
`PlanMoveTrace` (both unchanged) and `schemas.py` re-exports them, so the
core module does not import the web layer. `ServedRestraint.steps` is a
list of `ServedStep`, the seven keys the ladder writes (v17b's `line`
included).

Functions, each a value in and a value out:

```
priced(plan, buy: dict[int, float], sell: dict[int, float]) -> ServedPlan
banked(plan, start: float | None) -> ServedPlan
traced(plan, *, gws, ep_by, positions, names, opt: dict, free_transfers,
       lam, cover, thresholds, ft_lambda, price_timing, price_fall) -> ServedPlan
pool_prices(pool) -> tuple[dict[int, float], dict[int, float]]
trace_inputs(pool) -> tuple[dict, dict, dict]
thresholds(chip_table) -> dict[int, float]
chip_by_gw(chip_table) -> dict[int, str]
```

The last four are the router's `_prices`, `_trace_inputs`, `_thresholds`
and `_chip_by_gw` moved whole, with their docstrings, so the write path
and the backfill read the pool the same way.

`src/gaffer/ladder.py`: `serve_rung(ladder, objective: ServedObjective
input, *, hit_cost, captain_note) -> ServedPlan`. The objective input is
the nine-key dict advise builds today, validated into a `ServedPlan`-shaped
value at the top of `serve_rung`; the rung choice, the armband rule and
the prose are unchanged. `recommended_rung` and `served_note` keep their
dict inputs (they read the file through `load_advice`).

`src/gaffer/artifacts.py`: `advice_path(gw) -> Path`, `advice_gws() ->
list[int]`, `served_plan(gw) -> ServedPlan` (raises `GafferError` on a
missing file, the same sentence `load_advice` raises; raises `GafferError`
naming the field on a file that will not validate). `load_advice`
unchanged.

`src/gaffer/advise.py` (orchestrator): the objective input is built once
as a dict in `serve_rung`'s shape; `served = serve_rung(...)`; the tags
and frequencies become `ServedMove` fields through one `decorated(served,
tags, freqs)` call in `served.py`; then `priced`, `banked`, `traced`; the
alternatives are `ServedAlternative` values built from `alt_rows`;
`Advice(..., **served.model_dump())` with the served field names matching
`Advice`'s; `atomic_write(advice_path(gw), ...)`.

## 5. What sits behind the seam

The rung choice and the restraint walk (unchanged, `ladder.py`). The
pricing of a move from the pool's `cost` and `sell` columns. The bank
recurrence, one decimal, blanking from the first unpriced move. The trace
over the objective's own terms (`trace.py`, unchanged). The chip and θ
lookups over the chip table. Which file the plan lives in, and which
gameweeks have one.

Adapters: two — advise (write) and `served_plan` (read with backfill). The
router, `meta.py`, `tracking.py`, the brief and the digest are callers,
not adapters.

## 6. Tests

New `tests/test_served_plan.py`:

- the round trip (gate part 3): build → `Advice(**model_dump())` →
  `json.dumps(asdict(...))` → `served_plan(gw)` → equal;
- `priced`: a move the pool cannot price is `None`, NaN and a missing
  column leave a side unpriced;
- `banked`: the v11 rules (the difference per week, unchanged with no
  moves, blank from the first unpriced move on, the start survives a
  broken trajectory, `None` start is `None` not zero), on the served
  weeks, the objective's week and each alternative;
- `traced`: the trace lands on the served weeks and the objective's week
  and never on an alternative; a trace that throws costs the trace and not
  the plan (moved from the router test);
- the loader backfills a pre-v17f file from the solve state and leaves a
  v17f file's numbers as written; a file that will not validate is a
  `GafferError` naming the field; `plan_by_gw` keyed by gameweek loads;
- `advice_gws` enumerates ascending and ignores a stem that is not a
  number;
- `serve_rung` returns a `ServedPlan` with the objective's plan when the
  ladder is `None` (the v16 rule, now typed);
- `schemas.WIRE_EXPORTS` names the six models and `gen_types` emits them.

Rewired, surviving: `tests/test_v11_plan_bank.py`,
`tests/test_v16_plan_objective.py`, `tests/test_v12_w3_plan_alternatives.py`,
`tests/test_v12_w5_plan_trace.py`, `tests/test_web_plan.py`'s route tests,
and the plan tests in `tests/test_v11_degradation.py` and
`tests/test_v12_w3_degradation.py` patch `gaffer.artifacts.load_advice`
and `gaffer.artifacts.load_solve_state` instead of the router's names;
their old-shape fixture dicts exercise the backfill.

Die, by ruling (§2.7): in `tests/test_web_plan.py`
`test_a_non_numeric_hits_count_reads_as_none_taken`,
`test_a_non_numeric_ep_on_a_move_reads_as_zero`,
`test_a_move_with_no_code_is_dropped_not_fatal`,
`test_a_plan_entry_that_is_not_a_dict_is_skipped`,
`test_a_chip_row_with_a_null_gameweek_is_ignored`,
`test_a_chip_table_that_is_not_a_list_costs_only_the_chips`,
`test_a_non_numeric_hit_cost_falls_back_to_four`,
`test_a_plan_entry_with_no_gameweek_is_skipped`; in
`tests/test_v11_degradation.py`
`test_a_move_too_broken_to_parse_blanks_the_bank_the_same_way` and
`test_a_buys_key_that_is_not_a_list_blanks_it_too`; in
`tests/test_v12_w3_plan_alternatives.py`
`test_a_malformed_alternatives_key_costs_a_tab_and_not_the_board` and
`test_an_alternative_that_is_not_a_dict_is_dropped_and_the_rest_stand`; in
`tests/test_v12_w3_degradation.py`
`test_a_malformed_alternative_costs_a_tab_and_not_the_board`; in
`tests/test_v12_w5_plan_trace.py`
`test_the_payload_is_byte_identical_with_the_trace_off` (the flag is
gone) and `test_a_trace_that_throws_costs_the_trace_and_not_the_plan`
(moved). Each becomes, where the rule survives in a new form, a test in
`tests/test_served_plan.py`; the rest are deleted with the ruling cited in
the commit subject.

`tests/test_v16_restraint.py`: the three source pins replaced (gate part
3); the CLI tests stay. `tests/test_v17b_prose.py` and
`tests/test_v16_ladder.py` call `serve_rung` and read its result by key;
they read attributes instead. `tests/test_advise.py` pins the literal
`expected_pts=round(raw_xi_pts(first, ep_by), 2)`, which survives in the
objective input.

Frontend: `types.test.ts` gains the six generated names; `Timeline.test.tsx`
unchanged (the wire is unchanged); `tokens.test.ts` unchanged.

## 7. Pins and protected files

Routes 51, job kinds 12, `Config` fields 62: unchanged. No route is added
(`/api/plan/{gw}` keeps its path and model); no job kind.

Protected, orchestrator diffs: `src/gaffer/advise.py` (the served block,
the write), `src/gaffer/ladder.py` (`serve_rung`'s return; the rest of the
file is not protected but the return is by the prompt's ruling),
`tests/test_advise.py` (if a pin moves; expected none),
`tests/test_v16_restraint.py` (gate part 3), `tests/test_v11_degradation.py`
and `tests/test_v12_w3_degradation.py` and `tests/test_v12_w5_degradation.py`
(the rewire and the deaths in §6). `tests/test_v12_w1_degradation.py` is
untouched.

## 8. Process

Every task has an Opus implementer, a spec review and a code review
between tasks. The orchestrator's tasks: the route recording on `main`'s
code (first commit), `serve_rung` and the advise block, the pin ruling,
the golden re-record, the gate, the merge. Subagents never open
`config.toml`; the odds key is `[odds] api_key` by name only.

Order matters for one reason: the recorded `expected/plan.json` must be
written by `main`'s router before `plan.py` changes, so the recording is
Task 0 and is committed before any served-plan code.

## 9. Out of scope

Which rung is served, the trace's accounting, the ladder's walk, the chip
table's shape, `Advice` as a dataclass and its `asdict` readers (v17g),
the This Week fetch count (v17h),
`report.html.j2`'s literal 4 (open since v17b).

## 10. Outcome

_(filled by the orchestrator after the gate runs)_
