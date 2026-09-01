# gaffer v10 — minutes intelligence II: decisions + coverage

Date: 2026-09-01. Branch: `feat/gaffer-v10` off `728236d` (v9d).

The v8a record is the starting point: six historical-feature arms all
withdrawn, and the remaining zeros error judged news-shaped and serve-time
(models/train.py:76-98). v10 therefore does not chase new historical features
by default. It has three fronts: minutes reach *decisions*, external coverage
gets a second source, and one cheap pre-registered arm re-tests the single
unclaimed feature pair.

## §0 Constraints (standing)

- Implementation by Opus subagents; the orchestrator reviews and runs gates.
- **Protected files**: `src/gaffer/advise.py`, `set_pieces.py`,
  `web/jobs.py`, `web/routers/whatif.py`, `tests/test_advise.py`,
  `test_odds.py`, `test_web_jobs.py`, all pre-existing
  `tests/test_*_degradation.py`, `scripts/s2_replay.py`. `journal.py` /
  `backtest.py` import-only. **`optimize/**` is protected except the F1
  line-groups the plan must enumerate for orchestrator authorization** —
  the v9d T6 pattern: exact lines, exact replacement text, a STOP before
  writing, provenance comments `# v10 §F1x (specs/...)`.
- Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`,
  `config.toml`, `src/gaffer/web/static/`. Never `git add -A`.
- Pins: `JOB_KINDS` stays 12. `Config` moves 48 → 49 **only if** F2a needs a
  key (see F2a; avoid if the existing `[news]` switches suffice); any move is
  deliberate and pinned in `tests/test_v10_degradation.py`. The v9d pins are
  protected.

## §F1 — minutes reach decisions

Today `p_play` affects decisions only through `ep` and scenario noise. The
MILP's bench value is a static population curve
(`DEFAULT_BENCH_CURVE = [0.21, 0.06, 0.002]`, optimize/milp.py:281-292),
bench order is pure EP-descending (milp.py:337-339), and vice is a flat hedge
(`vice_weight`, :280). Those weights are population averages standing in for
per-player probabilities the model already computes.

- **F1a per-slot autosub weighting.** The bench slot's objective weight
  becomes `curve_weight × mean(1 − p_play over the XI it covers)`, normalised
  so a fully-fit XI reproduces today's curve exactly (the curve values stay
  the calibrated population base; p_play modulates around them,
  `xi_frailty = mean(1 − p_play_XI) / POPULATION_DNP` with a documented
  `POPULATION_DNP` derived from the same replay data that fitted the curve —
  the planner fixes the exact normalisation so that *identical* p_play across
  the pool is decision-identical to main). GK slot reads the XI keeper only.
  Since bench choice and XI choice are jointly optimised, the plan must state
  how the weight enters without making the objective quadratic — acceptable
  answer: two-pass (solve as today, compute frailty from the chosen XI,
  re-weight bench slots, re-solve with XI fixed free-choice bench), which
  keeps the MILP linear and the edit small.
- **F1b bench order by autosub value.** Order by `ep × p_play` (GK still
  last, milp.py:337-339). Rail: a 90%-fit starter of equal EP outranks a 50%
  doubt; ties preserve today's order.
- **F1c vice weighting.** The vice term's flat `vice_weight` scales by the
  captain's `(1 − p_play)`, floor at today's value when p_play is missing.
- p_play enters `optimize` as data the caller passes (advise.py is protected
  — the planner finds the existing seam: the pool/ep structures advise
  already hands to `solve`, extended additively with a default that
  reproduces today's behaviour byte-for-byte when absent).
- **Gate G2 (replay)**: 3-seed `scripts/replay_pair.sh v10`. Expectation:
  totals may move (this is a decision change); pass = branch mean not worse
  than main mean minus half the seed spread.
- **Gate G3 (counterfactual)**: offline 2024-25 scoring of bench-order and
  autosub outcomes — weeks where an autosub actually fired — branch vs main,
  using review.py's lane-scoring definitions (import-only). Must not regress.

## §F2 — external coverage

- **F2a second predicted-XI provider.** `data/news/lineups.py` gains a
  provider seam: the FFS fetch becomes provider "ffs"; add provider
  "rotowire" (public lineups page; the planner verifies fetchability with one
  manual fetch during planning and picks an alternative public source if the
  markup is hostile). Same degradation contract per provider: `None` →
  empty frame → flags-only byte-identical (v5/v8a rails pattern). Agreement
  logic in `normalize.availability_frame`'s inputs: both agree → hint kept;
  disagree on start/out → the more conservative hint (min p_start_hint);
  one silent → the other alone (today's behaviour). No new Config field if
  the existing `[news] lineups` bool can gate both providers; a per-provider
  kill needs a documented Config move (48 → 49, `lineup_providers` list) —
  planner decides and says why.
- **F2b presser shadow.** The LLM presser classifier stays off. Its would-be
  factor (`presser_log.would_factor`) joins the news-shadow parquet columns
  so `gaffer evaluate --news-shadow` can score it once rows accrue — columns
  additive, absent-safe.

## §F3 — the one cheap arm

- **F3a SHRUNK_MODE_FEATURES arm.** `shrunk_start_rate` / `shrunk_min_per_app`
  (engineer.py:1030, built v5, claimed by no head) added to `MINUTES_FEATURES`
  as an ablation arm on the 2024-25 walk-forward benchmark (z1/v8a driver
  pattern; the driver must raise on identical arms — v9c lesson). Pre-registered
  bar: ship only if starters-slice `p_start` log-loss improves ≥ 1% with zeros
  RMSE not worse; otherwise withdraw and record numbers in the
  `MINUTES_FEATURES` docstring per convention (train.py:51-104).

## Non-goals

- Training on the availability_log corpus (rows only exist since GW1 2025-26;
  stays the v11+ item the v8a spec D4 already names).
- Any change to the availability multiplier chain semantics
  (models/availability.py order of operations is untouched).
- Optimizer changes beyond the three F1 line-groups.

## §Gates

- **G1** — F3a arm numbers recorded here; ship/withdraw per the bar.
- **G2** — replay pair as in §F1. Results recorded here.
- **G3** — counterfactual autosub/bench-order scoring recorded here.
- **G4** — suite green (2912 py + 562 fe baseline); `tests/test_v10_degradation.py`
  rails: provider-down byte-identity, absent-p_play optimizer byte-identity,
  arm-lever guard; pins (kinds 12, Config 48-or-49-with-reason, route count
  unchanged).
- **G5** — adversarial review, fix-first, re-verify; merge ritual.

### The `p_play` seam — decision

Plan Task 10's STOP. §F1 assumed an existing seam by which `p_play` would
reach `solve_plan`; plan A8's search found none — `build_pool`'s `players` is
the bootstrap frame and the FPL API carries no such column, `pool_ep` is a
`dict[(code, gw), float]` whose values `_solve_once` coerces with `float()`,
and every other structure the solver sees is assembled inside `advise.py`.

**Decided: option A.** One authorized line-group in `src/gaffer/advise.py`,
enumerated in the plan under "Task 10A". A `{code: {gw: p_play}}` dict is
built from `comp` after `build_pool` (grouped mean per `(code, gw)` — the
`shadow_rows` rule, because "did he turn out at all" is one outcome across a
double gameweek) and passed to `policy.coherent_plan` — **and to nothing
else**.

**Amended at G5 (fix-round, I2).** The group as first written put `p_play` on
`solve_kw`, which the raw optimum and the scenario sweep share, and then
stripped it again at the sweep's call. The result was a two-pass raw optimum
compared against a single-pass sweep. `decide()` reports that comparison to
the user as `raw_optimum_agrees`, so the two objectives disagreeing about a
bench would have surfaced as a stability warning about something that is not
instability. The wiring is now: raw optimum single-pass, sweep single-pass,
**`coherent_plan` weighted** — the plan that is actually recommended. Every
user-facing comparison is then between like and like.

Three consequences, recorded because they change what the gates and the
feature mean:

- **`backtest.py` is untouched.** It is import-only this cycle and passes no
  `p_play`, so **G2 cannot see §F1 at all** and is a no-regression check on
  the seed spread rather than a measurement of the feature. **G3 is the gate
  that judges §F1** — its driver calls `solve_plan(..., p_play=...)`
  directly and is independent of this decision.
- **Scenarios stay single-pass**, now by construction rather than by a strip:
  they are handed `solve_kw`, which no longer contains the keyword. Scenarios
  are N noised re-solves measuring how stable a move is; doubling the slowest
  part of an advise run to price a bench the sweep never reads would be a cost
  with no reader.
- **§F1 does not reach the transfer side.** The moves are chosen by a sweep
  that cannot see `p_play`; only the squad built around them is weighted by
  it. This is the documented cost of the amendment and is carried in
  §Residuals rather than worked around.

### G1 results — **run, withdraw**

`scripts/v10_shrunk_arm.py`, 2024-25 walk-forward benchmark, one fit per arm,
16279 zeros rows and 7820 starter rows. `V10_ARM_LEVER ok` printed first.

| arm | zeros RMSE | all RMSE | p_start LL (starters) | p_start LL (all) |
| --- | --- | --- | --- | --- |
| baseline | 1.063 | 1.969 | 0.45976 | 0.28130 |
| shrunk_modes | 1.070 | 1.971 | 0.45474 | 0.28082 |

Relative log-loss gain **+1.09%** (bar: >= 1%, passes). Zeros cost **+0.007**
(guard: <= 0.005, fails). **Decision: withdraw** — `shrunk_start_rate`,
`shrunk_min_per_app`.

Read the two together, which is what the bar is for. On the starters slice
truth is almost always 1.0, so the log-loss is close to `-mean(log p_start)` —
a confidence score an arm can improve by calling more players starters, with
the ones it is wrong about landing in the zeros stratum. A 1.1% confidence
gain bought with 0.007 of zeros RMSE is that mechanism, not a better model.

The control's 1.063 sits beside v8a's banked 1.066 as a sanity check only,
never as the comparison (CONVENTIONS §1).

**What it settles.** v5's N1 measured these columns bundled with congestion and
blamed the congestion half. Measured alone, on a window whose cup archive is
empty, the mode rates are a small regression too — so they were never the
problem and were never the answer, and the next cycle can stop wondering.
Recorded in `MINUTES_FEATURES`' docstring. The builders stay wired.

### G2 results

**Not run — the orchestrator runs this.** Driver: `scripts/replay_pair.sh v10`.

Preflight, both answered, because both change what the result means:

- **`bench_curve` is configured** — `config.toml:13` gives
  `[0.21, 0.06, 0.002]`, so §F1a's bench slots exist in the replay and a null
  delta would not be a null effect for that reason (plan A9).
- **`backtest.py` passes no `p_play`** — `grep -c p_play src/gaffer/backtest.py`
  is 0; `src/gaffer/advise.py` is 12. Task 10 authorized option A, which wires
  the *advise* path only. **G2 therefore cannot see §F1 and is a
  no-regression check on the seed spread, not a measurement of the feature.**
  G3 is the gate that judges §F1.

Rule: three seed bases a side, read as mean ± spread; pass is the branch mean
not worse than the main mean minus half the seed spread. Record wall-clock per
side beside the totals.

### G3 results

**Not run — the orchestrator runs this.** Driver: `scripts/v10_autosub_cf.py`,
built and smoke-tested (parses; `review.score_squad`'s `xi/bench/captain/vice/
hits` signature confirmed; `_p_play_lookup` reachable; a `bench_curve` is in
`OPT_KW` so §F1a is live in the measurement).

Rule: the mean delta over weeks where an autosub actually fired must not
regress. A large positive delta on a handful of weeks is not a win either —
the week count prints beside the mean so it is read as the small sample it is.
Expect one benchmark fit plus ~114 solves (the branch arm's are two-pass).

## §Residuals

Known and deliberately not fixed this cycle. Each is a thing a later reader
would otherwise have to rediscover from the code.

- **§F1's transfer-side reach waits for a sweep that can see `p_play`** (I2,
  above). The fix is not a two-pass raw optimum — that trades a real
  inconsistency for a fake instability warning — it is `run_scenarios`
  learning the keyword, at N times the second pass's cost, which needs its own
  measurement before it is worth paying.
- **What-if baselines are single-pass by omission.** The web re-solves rebuild
  their solver bundle from `SolveState.opt`, which is serialized JSON and
  cannot carry a per-player dict, so a what-if board is priced without §F1
  while the advice it is compared against is priced with it. *v11: p_play into
  SolveState so what-if matches advice.*
- **`policy.coherent_plan` appends a promoted captain to the bench.** When the
  plurality captain is not in the re-solved XI he is swapped into it and the
  man he displaced is appended to `bench` — at the end, after §F1b has ordered
  it by autosub value. Pre-existing (v4c), in a protected file, and the
  appended man is the lowest-EP XI player of his position, so last is usually
  where he belongs anyway.
- **`captaincy_override` discards the frailty-weighted vice under league
  tilt.** §F1c prices the vice by how likely the captain is to leave the
  armband unused; when the league-mode tilt then overrides the captain, the
  vice that came back from the solve was chosen against a different captain's
  frailty. Pre-existing interaction between v8c's tilt and v10's weight,
  reachable only in league mode with the tilt active.

The keeper's own denominator (`KEEPER_DNP`) was a residual of the same kind
and is not one any more: it was fixed at G5. See B2.
