# v18b — the advice path tells the truth

**Cycle:** v18b, the second sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18b;
design `specs/2026-09-12-v18-polish-design.md`, rulings 2, 3 and 4).
**Branch:** `v18b-advice-path` off `main` at `ca6d25d`.
**Date:** 2026-09-12. **Plan:** the programme's §3 v18b task list.

## 1. Gate, stated before anything runs

1. The golden, untouched since v18a's recording except for the one
   declared addition (the ladder file, task 4): `.venv/bin/pytest -q -rs
   tests/test_golden_board.py tests/test_pipeline.py` → **all passed, 0
   skipped**, `expected/advice.json`, `plan.json` and `solve_state.json`
   byte-identical to `a0bd45c`.
2. Rails, each shown to fire by a planted fault before it is trusted:
   - a `ladder_payload` that raises `TypeError` propagates out of
     `build_advice`; one that raises `GafferError` is reported as today
     (one printed line, the objective's plan served);
   - with `pulp.HiGHS` patched to raise, the solve state's `opt` carries
     `solver: "cbc"`; unpatched, the key is absent;
   - the purity sentinel: a `config_in_force()` call planted inside
     `gather_inputs` or `build_advice` raises the `BaseException` sentinel;
   - `report.html.j2` renders `−5` for a week with one hit at
     `hit_cost=5`;
   - the CLI prints the brief's note exactly once;
   - `calibrate_noise.ensemble_rows` runs un-stubbed over a three-row
     frame with a bundle lacking `feature_cols`.
3. `build_advice(..., now=...)` and `ladder_payload(..., now=...)`: two
   calls with different `now` values differ only in `generated_at` (and
   the ladder's stamp), nothing else.

Verdict: line 1 byte-identical and every rail in line 2 shown to fire, or
no merge.

## 2. What the cycle must know

- The reads the sentinel will find are inside helpers, not in the two
  halves' own bodies: `served.price_falls` (`served.py:382-386`, reached
  through `trace_context`), `price_timing._owned_price_falls`
  (`price_timing.py:169`), the availability pass
  (`models/availability.py:114-117`, `overrides` defaulting from the
  view), and `artifacts.py:229-233,549-551` on the bank step. The three
  reads in `ladder.py` (`:449,:767,:991`) are on the router's
  `build_ladder` path, which is allowed to read the view; they are out of
  scope. `models/train.py:586` is the trainer; out of scope.
- The fix shape is "told, not read": the caller passes the value it
  already has on `cfg` (`price_timing`, `news_overrides`,
  `current_season`) as a keyword; the helper keeps its default of reading
  the view for the router and CLI callers that have no `cfg`. The two
  halves must then pass it everywhere, which is what the sentinel checks.
- `_owned_price_falls` is an `lru_cache` keyed on `(day, owned)`; if
  `price_timing` becomes a parameter it must join the key, or the cache
  can serve a table computed under the other switch.

- Ruling 2, refined on the way: the tuple is `(GafferError, ValueError,
  RuntimeError)`, not two. `optimize/milp.py` reports an infeasible rung as
  `RuntimeError("MILP not optimal")`, and
  `tests/test_advise.py::test_run_advise_builds_the_ladder_after_the_state_and_never_fails_on_it`
  pins that a rung that will not solve is one line, never the run's
  failure. `TypeError`, `KeyError` and `AttributeError` still propagate,
  which is what the ruling was for.

## 3. Outcome — PASS, first full run

Run by the orchestrator on the branch tip, 2026-09-12.

1. **Golden:** `pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py`
   → **58 passed, 0 skipped** in 18:13 (56 from v18a, plus the ladder
   comparison and the sealed-view rail). `expected/advice.json`,
   `plan.json` and `solve_state.json` byte-identical to `a0bd45c`; the
   recorded Inputs unchanged; `expected/ladder.json` added (`afefc31`) —
   the one declared fixture change.
2. **Rails, each shown to fire:** the ladder catch widened back to
   `Exception` → `test_a_programming_error_inside_the_ladder_propagates`
   fails; the `opt` line removed →
   `test_the_fallback_solver_is_recorded_on_the_state_and_highs_is_not`
   fails; a `config_in_force()` planted in `build_advice` → the sealed rail
   raises the sentinel (`tests/test_golden_board.py:759: _Read`); the
   `save_availability` hop reverted → the sentinel again, in 22 s; the
   `--write` command dropped from the recorder's sentence (v18a) and the
   `attacking_features` import reverted → `NameError` at
   `calibrate_noise.py:443`; the CLI's second echo restored → the note
   counted twice. The template rail renders `−5 pts` at `hit_cost=5`.
3. **Clocks:** two builds with different `now` differ only in
   `generated_at` (`test_two_builds_with_different_clocks_differ_only_in_their_stamp`);
   two ladder payloads likewise, plus `wall_s`
   (`test_ladder_payload_takes_its_clock`).

**Found on the way.** The sealed rail's first draft compared a board built
from a fresh `RecordedComponents` gather to the expected files and was ten
points off: the recorded adapter has no calibration model, which its
sibling's docstring already said. The rail now gathers under the seal,
compares the gathered components frame to the recorded one, and builds
from the recorded Inputs under the same seal. And the full suite exposed a
latent order dependence unrelated to this cycle: two fake FPL clients
(`tests/test_web_smoke.py`, `tests/test_web_league_sim.py`) never answered
`get_entry`/`get_entry_history`, and the v8c rail's fixture never patched
the league router's client — a warm `_OVERVIEW` cache from an earlier file
had stood in for all three. Verified against `main`'s source in a worktree
(4 failed there too). Fixed here; v18g's cache-clearing fixture is what
makes it impossible to reintroduce.

**Suite:** `pytest -q -m "not golden"` → 4434 passed, 11 deselected, in
three consecutive runs the first of which reported one failure whose name
the capture did not keep; the two runs after it were clean. Recorded as an
unattributed flake for v18g, whose cache-clearing fixture and random-order
run are the instruments for it.

Verdict: merge. Pins unmoved (51 / 12 / 62).
