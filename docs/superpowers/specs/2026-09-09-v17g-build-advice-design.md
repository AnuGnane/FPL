# v17g — `build_advice` as a pure module

**Cycle:** v17g, the seventh sub-cycle of the v17 deepening programme
(`docs/superpowers/plans/2026-09-07-v17-deepening-programme.md`).
**Card:** `#c3` of `docs/superpowers/research/2026-09-07-architecture-review.html`.
**Branch:** `v17g-build-advice` off `main` at `74f8198`.
**Date:** 2026-09-09.

---

## 0. Why

`run_advise` is 659 lines behind the widest interface in the repo: a config,
an FPL client, the models on disk, the live data, the solver, the news
providers, `reports/`, and — because none of that can be assembled in a
test — **the source text itself**. Fifty-three `inspect.getsource` pins
string-match that body across thirteen files, and the only caller that runs
it end to end anywhere in the suite is `tests/golden_client.py`. The helpers
are unit-tested apart from the calls where the bugs live.

The split is at the seam that already exists (the client) plus the two the
card names. `gather_inputs(cfg, client)` does every fetch, every model load
and every prediction and returns a frozen `Inputs`. `build_advice(inputs,
cfg)` does every solve, the alternatives, the ladder, `serve_rung`, the
`SolveState` and the `Advice`, and touches no file and no socket.
`run_advise` is the composition and the artifact writes.

The prize is not tidiness. It is that a miswired call fails a test on a
Tuesday instead of a Thursday, and that thirty-five source pins become
assertions about what the code *did*.

---

## 1. Gate, stated before anything runs (CONVENTIONS §2, §7, §10)

Four parts. The orchestrator runs all four; an implementer runs none
(CONVENTIONS §7). **All four must hold.** Every command is run from the repo
root on the branch.

### Part 1 — the golden board is unmoved, and not re-recorded

```
.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py
git diff --stat tests/data/golden_board/expected tests/data/golden_board/header.json
```

**Verdict:** the first command reports **no failures and no skips**, and the
second prints **nothing**. This is a no-op refactor, so unlike v17f there is
no re-record and no permitted key: the expected `advice.json`, `state.json`
and `plan.json` are byte-identical to what `main` produces. A skip is a
failure — it means the inputs moved, not that the refactor is fine (v17c's
note). The suite grows by the new tests of part 2; the pre-existing count is
45.

### Part 2 — the same board, built from recorded `Inputs`, with no models

A second golden test runs `build_advice` on the recorded `Inputs` alone and
compares against **the same** `expected/advice.json` and `expected/state.json`,
volatile keys stripped exactly as part 1 strips them.

```
mv models models.off
.venv/bin/pytest -q tests/test_golden_board.py -k inputs
mv models.off models
```

**Verdict:** passed, **not skipped**, with `models/` absent. If it skips or
errors on a missing model the seam leaks and the part fails. The `models/`
and `data/history/` hash guard that gates part 1 must **not** guard this
test — that is the limit v17c recorded and this cycle lifts.

### Part 3 — the source pins are gone from `tests/test_advise.py`

```
grep -c "inspect.getsource" tests/test_advise.py          # must print 0
grep -rn "getsource(run_advise)\|getsource(advise.run_advise)" tests/  # nothing
```

**Verdict:** both hold, and every claim the thirty-five pins made is still
made — behaviourally, over `build_advice` and `gather_inputs`, in a test whose
name says the same sentence. The eighteen pins in the other twelve files
keep their claims by reading `tests/advise_source.py`'s `advise_source()`
(§2.4); they are not deleted and not weakened.

### Part 4 — `build_advice` is pure, statically and at run time

*Static:* a rail slices `inspect.getsource(build_advice)` and asserts none of
`open(`, `Path(`, `client.`, `load_`, `save_`, `store.`, `atomic_write`
appears in it.

*Run time:* a rail calls `build_advice` on the recorded `Inputs` with
`builtins.open` monkeypatched to raise, and asserts the advice equals the
expected one. A hidden read cannot pass this: `ladder._hit_bar`'s
`config_in_force()` swallows its own exception and falls back, so the run
would survive but the numbers would not (spec §2.3).

**Verdict:** both rails pass.

### What a failure means

A failure in part 1 or 2 is a behaviour change and the branch does not merge
until the diff is explained or reverted — never by re-recording the golden.
A failure in part 3 or 4 is incomplete work. No part of this gate may be
satisfied by editing an expected file.

### Pins

Routes **51**, job kinds **12**, `Config` fields **62**. **None move.** No
new route, no new job kind, no new config field. The golden fixture stays
under its 5,120 KB budget (980 KB today; the recorded `Inputs` adds roughly
1 MB).

---

## 2. The decisions the grilling settled

### 2.1 `build_advice` returns a frozen `Outputs`, not a `ServedPlan`

The programme's section says `-> ServedPlan`. That cannot hold: `Advice`
carries seventeen fields the served plan does not — the captain options, the
chip table, the wildcard assessment, the transfer alternatives, the threat
board, the price alerts, the strategy, the win probabilities, the mode, the
data-gap pair, the move frequencies, `raw_optimum_agrees`, the scenario
report, the demoted captain and the caps — and the `SolveState` is not in it
at all. Returning only the served plan would push all of that back out of the
pure half through extra return values, which is purity in name.

```python
@dataclass(frozen=True)
class Outputs:
    advice: Advice
    state: SolveState
    ladder: dict | None
```

Three fields, and they are exactly what `run_advise` banks and what the
golden compares. `Inputs` in, `Outputs` out — the card's "one frozen input,
one output", read literally.

### 2.2 The ladder moves behind a pure core

`build_ladder(gw)` reads the solve state back off disk, reads the *previous*
run's advice for `recommended_rung`, and writes `ladder_gw{n}.json`. All
three are forbidden inside `build_advice`, so `ladder.py` gains a pure core:

```python
def ladder_payload(state, *, gw, gws, hit_bar, seed, sigmas,
                   prior_advice, n_draws=LADDER_DRAWS) -> dict
```

and `build_ladder(gw)` becomes load → `ladder_payload` → `save_ladder`, so
the `ladder` job kind and every existing caller are untouched. `build_advice`
calls `ladder_payload` with the state it has just built in memory, and
`run_advise` saves the returned payload. The failure behaviour is unchanged:
a ladder that will not build is one printed line and the objective's plan
served, never the run's failure.

Two reads the pure core cannot make become inputs:

- **`sigma_table(gw)`** loads the components parquet that the same run wrote
  minutes earlier. `build_advice` has that frame as `inputs.components` and
  derives the σ map from it — the same frame, one fewer round trip through
  parquet.
- **`recommended_rung(load_advice(gw), rows)`** reads the advice file *for
  this gameweek as it stood before the run* — the previous run's, on a
  Thursday re-run, and absent on a first run. That is real behaviour and it
  becomes `inputs.prior_advice`, read once in `gather_inputs`. Nothing writes
  that file between the read and the use, so the value is identical.

### 2.3 `hit_bar` and the ladder seed come from `cfg`

`ladder._hit_bar()` and `build_ladder`'s seed default call `config_in_force()`
— a TOML read behind `cfg`'s back, and one of the four v17c named as "read
behind `cfg`'s back". v17e made both real `Config` fields, so `build_advice`
passes `cfg.hit_bar` and `cfg.scenarios_seed + SEED_OFFSET + gw` explicitly.
`build_ladder(gw)`'s own defaults are unchanged for its other callers.

### 2.4 The eighteen pins outside `test_advise.py` are redirected, not rewritten

Thirteen files hold `getsource(run_advise)` pins. The programme's gate names
only `tests/test_advise.py`; the other twelve — **eighteen pins, fourteen of
them in protected rails** — go red the moment `run_advise` becomes a
composition, and the programme does not mention them. Six of them pin the
same `fetch_rival_entries < tilt_ep < build_pool` chain, which straddles the
split.

They keep their claims through one helper:

```python
# tests/advise_source.py
def advise_source() -> str:
    """The weekly pipeline's source, in pipeline order. v17g §2.4: the
    ordering rails older cycles wrote against ``run_advise`` still ask the
    same question of the same text; the text now lives in three functions."""
    return "\n".join(inspect.getsource(f)
                     for f in (gather_inputs, build_advice, run_advise))
```

Concatenating in pipeline order preserves every ordering assertion that
straddles the split, every `in src`, every negative slice and the one
`ast.parse` (three top-level `def`s parse as a module).

For that to be true with **no edit to any pinned literal**, `build_advice`
unpacks `Inputs` into today's local names in its opening lines:

```python
gw, gws, deadline = inputs.gw, inputs.gws, inputs.deadline
players, comp, components = inputs.players, inputs.comp, inputs.components
...
```

so `build_pool(players, pool_ep, my_picks, gws)` and every other pinned line
reads exactly as it does today. It is a few lines of unpacking bought against
touching fourteen protected rails, and it makes the diff readable as what it
is: a move, not a rewrite.

The remaining `getsource` idiom is recorded as debt in the ROADMAP, not
smuggled out. Deleting the other eighteen is a later pass over eight other
cycles' honesty rails, not this one.

### 2.5 Both protocols are written; `optimize/**` is not touched

The card asks for `Predictions` and `Solver`. Both go in `src/gaffer/inputs.py`
as `typing.Protocol`s with their live adapters. The protocol is a structural
type and the adapter is a thin pass-through, so **no file under
`src/gaffer/optimize/` changes and no solve changes**.

```python
class Predictions(Protocol):
    def missing(self) -> list[str]: ...
    def components(self, *, pred_frame, tg_future, players, avail,
                   pens) -> pd.DataFrame: ...
    def calibration(self): ...

class Solver(Protocol):
    def solve(self, pool, state, **kw) -> Plan: ...
    def coherent(self, pool, state, decision, **kw) -> Plan: ...
    def scenarios(self, pool, state, xmins, **kw) -> ScenarioRun: ...
    def alternatives(self, pool, state, plan, *, max_gap, **kw) -> list: ...
```

`Predictions` is the three places `gather_inputs` touches `models/`: the
missing-model check that raises `SystemExit`, the component predictions, and
the optional calibration map. Adapters: `LiveModels` (reads `models/`) and
`RecordedComponents` (serves the fixture frames), so `gather_inputs` can run
with neither network nor models.

`Solver` is the four calls that produce a `Plan`. Chip pricing —
`chip_baseline`, `evaluate_chips`, `wildcard_now_assessment` — stays a direct
call: it answers a different question (what a chip is worth against a
baseline, not what to do this week), and a third protocol for it is
over-building. Adapters: `MilpSolver` (the default, calling
`solve_plan`, `coherent_plan`, `run_scenarios` and `alternative_plans` where
they already live, with the arguments they already take) and the tests'
`ScriptedSolver`.

Both defaults are constructed inside `run_advise`, so no caller of
`run_advise` changes and `pipeline.weekly_run` is untouched.

### 2.6 `components_frame` moves into `gather_inputs`

`components = components_frame(comp, scoring, cal, players, teams)` is
currently below the chips block, and it takes the **calibration model**. A
model object on the pure side makes part 2 unwinnable, so the call moves up
into `gather_inputs`, beside the prediction it belongs to. It is safe: the
existing comment already records that `comp` has not moved since
`rescale_pen_after_blend`, so the earlier call bands the identical frame. The
golden proves it.

`save_components` and `save_availability` move with it. The rule the split
follows: **gather saves what gather made; `run_advise` saves what build
made.** So `gather_inputs` banks the components and the availability frames,
and `run_advise` banks the state, the ladder, the advice and the history.
v16 §4's reason for banking the state before the payload — "the ladder solves
off the state" — dissolves, because the ladder now solves off the state in
memory; the files that land are the same files.

### 2.7 `Inputs` carries only what `build_advice` reads

A field exists on `Inputs` if and only if `build_advice` reads it. `teams`,
`events`, `scoring`, `season_idx`, `pens`, the fixture frames and the raw
bootstrap are gather-internal and do not cross the seam. A rail asserts the
rule by name (§6), which keeps the recording honest and small.

`ep_by` is kept as its own field rather than re-derived from `ep_named`: the
live code builds it from the pre-merge matrix, and a left merge that
duplicated a code would make the two disagree silently.

### 2.8 The recorded `Inputs` is a directory of parquet plus one JSON

`tests/data/golden_board/inputs/`: one parquet per frame and `scalars.json`
for the scalars, the league dicts, the strategy, the priors, the chip
scenarios and the prior advice. Readable, diffable, and the same store the
repo already uses; a pickle would be smaller and unreadable, and brittle
across the pandas versions this fixture is meant to outlive.

`save_inputs` / `load_inputs` live in `src/gaffer/inputs.py`, not in the test
tree: the recording is an adapter of the seam, and the review's test for a
real seam is two adapters, not a test helper. Integer-keyed dicts
(`league_eo`, `cover`, `cap_cover`, `rival_captains`, `rival_names`, the
strategy's `cover_weights`, `dgw_probs`) are restored as integers on load —
JSON has no integer keys and a silent string key would move the pool.

`python -m tests.golden_client --write` records the `Inputs` alongside the
expected files, so one command still re-records everything after a retrain.

---

## 3. The interface

```python
# src/gaffer/inputs.py  (new)

@dataclass(frozen=True)
class Inputs:
    """Everything ``build_advice`` needs and nothing it does not. v17g §2.7."""
    gw: int
    gws: list[int]
    deadline: str
    through: int | None
    gap_warning: str | None
    players: pd.DataFrame
    comp: pd.DataFrame
    components: pd.DataFrame
    ep_named: pd.DataFrame
    ep_by: dict[tuple[int, int], float]
    my: MyTeam | None
    league_eo: dict[int, float]
    cover: dict[int, float]
    cap_cover: dict[int, float]
    rival_captains: dict[int, int]
    rival_names: dict[int, str]
    strategy: Strategy | None
    win_probs: list[dict]
    priors: dict | None
    dgw_probs: dict[int, float]
    prior_advice: dict | None

@dataclass(frozen=True)
class Outputs:
    advice: Advice
    state: SolveState
    ladder: dict | None

class Predictions(Protocol): ...      # §2.5
class Solver(Protocol): ...           # §2.5
class LiveModels: ...                 # reads models/
class RecordedComponents: ...         # serves inputs/
class MilpSolver: ...                 # calls optimize/ unchanged

def save_inputs(inputs: Inputs, directory: Path) -> None
def load_inputs(directory: Path) -> Inputs
```

```python
# src/gaffer/advise.py

def gather_inputs(cfg: Config, client: FPLClient | None = None, *,
                  predictions: Predictions | None = None) -> Inputs
def build_advice(inputs: Inputs, cfg: Config, *,
                 solver: Solver | None = None) -> Outputs
def run_advise(cfg: Config, client: FPLClient | None = None) -> Advice
```

`run_advise` keeps its signature exactly, so `pipeline.weekly_run`, the CLI,
the job kind, the what-if router and `golden_client` are all unchanged.

---

## 4. What sits behind each seam

| Seam | Live adapter | Second adapter | What it hides |
|---|---|---|---|
| `FPLClient` (existing) | `FPLClient` | `RecordedClient` | the FPL API |
| `Inputs` | `gather_inputs` | `load_inputs` | fetches, models, predictions, `reports/` reads |
| `Predictions` | `LiveModels` | `RecordedComponents` | `models/*.joblib` |
| `Solver` | `MilpSolver` | `ScriptedSolver` (tests) | HiGHS, and the CBC fallback below it |

---

## 5. Tests

**New.** `tests/test_inputs.py` — the frozen values, the field rule of §2.7,
the save/load round trip including the integer-key restoration, the two
protocols each having two adapters, and `MilpSolver` passing its arguments
through untouched. `tests/advise_source.py` — the helper of §2.4, with its
own rail that it names three functions in pipeline order.

**Rewritten.** `tests/test_advise.py`: thirty-five source pins become
behavioural tests over `build_advice` and `gather_inputs` with a
`ScriptedSolver` and a small synthetic `Inputs`, keeping each test's sentence
name and its docstring's provenance. The three pins on `predict_components`
become calls with small frames.

**Extended.** `tests/test_golden_board.py`: the `Inputs` round trip on the
real recording, the build-from-`Inputs` equality of gate part 2, the
models-absent run, and the two purity rails of gate part 4.
`tests/test_ladder.py`: `ladder_payload` called directly, and `build_ladder`
still loading, delegating and saving.

**Redirected.** Eighteen pins in twelve files point at `advise_source()`.
No claim changes.

---

## 6. Pins and protected files

| File | Protected | Ruling |
|---|---|---|
| `src/gaffer/advise.py` | yes | The orchestrator writes every line, one task at a time, golden green after each. |
| `tests/test_advise.py` | yes | The orchestrator's; gate part 3 is its whole content. |
| `tests/test_odds.py` | yes | Five pins redirected to `advise_source()`; claims unchanged. Orchestrator's diff. |
| `tests/test_v4d_degradation.py` (2), `test_v5`, `test_v6`, `test_v7_model`, `test_v8a`, `test_v8c`, `test_v8f`, `test_v12_w3_degradation` | yes | Nine pins redirected the same way, in one ruling commit. |
| `src/gaffer/optimize/**` | yes | **Untouched.** `MilpSolver` calls it and changes nothing in it; the orchestrator checks `git diff --stat main -- src/gaffer/optimize` prints nothing before the merge. |
| `src/gaffer/web/jobs.py`, `web/routers/whatif.py`, `set_pieces.py`, `scripts/s2_replay.py`, `tests/test_web_jobs.py`, `tests/test_web_job_kinds*.py`, `tests/test_v16_restraint.py` | yes | Untouched. |

Unprotected and open to implementers: `src/gaffer/inputs.py` (new),
`src/gaffer/ladder.py`, `tests/golden_client.py`, `tests/test_golden_board.py`,
`tests/test_inputs.py` (new), `tests/advise_source.py` (new),
`tests/test_ladder.py`, `tests/test_v12_w3_alt_plans.py`,
`tests/test_v12_w3_chip_pairs.py`, `tests/test_v12_w3_dgw_captain.py`.

---

## 7. Out of scope

- **Any change to a solve.** No file under `optimize/` changes; no objective,
  no bound, no seed.
- **The replay driver.** `scripts/v7b_replay.py` and `scripts/s2_replay.py`
  do not call `run_advise` — verified: `grep -rn "run_advise" scripts/`
  prints nothing — so they neither gain nor lose anything here.
- **Deleting the eighteen pins outside `test_advise.py`.** Redirected, and
  recorded as debt (§2.4).
- **The frontend.** No schema change, no route change, no screenshot gate.
- **Re-recording the golden's responses.** The bundle and the expected files
  are untouched; only `inputs/` is added.

---

## 8. Process

Branch `v17g-build-advice` off `main` at `74f8198`. Plan at
`docs/superpowers/plans/2026-09-09-v17g-build-advice.md`. Implementers get
`inputs.py`, `ladder.py`'s pure core and the recording; the orchestrator
writes `advise.py` and `test_advise.py` one task at a time and runs the gate
after each. ff-merge on a pass, push, the security ritual from `CLAUDE.md`,
then the ROADMAP block, `docs/GUIDE.md` §11 and §10 (the golden now runs
without models), the tracker row, its boxes and the hand-off note, and the
memory line.

The odds key is referred to by name (`[odds] api_key`) and never by value, in
this spec, the plan, every subagent prompt and every commit. Subagents never
open `config.toml`.

---

## 9. Outcome

_(written when the gate has run)_
