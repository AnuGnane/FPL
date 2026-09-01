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

### G1 results

_TBD by the cycle._

### G2 results

_TBD by the cycle._

### G3 results

_TBD by the cycle._
