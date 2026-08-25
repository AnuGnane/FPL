# Gaffer v4a "measure" — design spec

Date: 2026-08-25. Branch: feat/gaffer-v4a. Research basis:
`docs/superpowers/research/2026-08-25-improvement-research.md`.

## Goal

Before improving the model (v4b) or the decision layer (v4c), build the
instruments that tell us whether an improvement worked: fix the one component
the 2026/27 rule change silently broke (bonus), stand up a persistent
evaluation harness with stratified and calibration-first metrics benchmarked
against OpenFPL's published numbers, and decompose replay loss into
forecasting error vs optimization headroom.

Four workstreams: (1) bonus re-derivation under 2026/27 BPS, (2) a
`gaffer evaluate` command + `reports/evaluation.json` artifact, (3) a
perfect-foresight ("oracle") mode in the replay, (4) a Model Quality page in
the web UI.

## Context and constraints

- History (`data/history/player_gw.parquet`): seasons 2022-23 (season_idx 0)
  through 2025-26 (idx 3), per player-fixture rows with `bps`, `bonus`,
  `cbi`, `tackles`, `defcon`, `kickoff_time`, `opp_code`, `was_home`.
  2026/27 rows arrive via live ingestion and are already scored under the
  new rules — they pass through re-derivation untouched.
- 2026/27 BPS change (premierleague.com/en/news/4679946): the −1 BPS for
  being tackled is removed; clearances/blocks/interceptions earn 1 BPS per
  **three** actions (was per two). Historical `bonus`/`bps` therefore
  reflect old rules.
- We cannot correct the tackled −1 (no times-tackled column exists in any
  public source). Known approximation, documented in code: old-season BPS
  slightly underestimates new-rules BPS for players who are tackled often.
- The bonus multiplier in the scoring table (v2, commit `8a4a702`) is a
  scoring-rule constant, not a learned quantity — unchanged by this cycle.
  What changes is the bonus *model's* training target and BPS features.
- Standing project rules apply: Opus implementer subagents, orchestrator
  reviews only; TDD; no `git add -A`; raw-vs-tilted EP discipline untouched.

## 1. Bonus re-derivation under 2026/27 BPS

New module `src/gaffer/features/bps.py` (pure functions, no I/O):

- `adjust_bps(df) -> pd.Series`: per-row adjusted BPS
  `bps + floor(cbi/3) − floor(cbi/2)` (a non-positive delta). Applied only
  to rows with `season_idx < current`; current-season rows return `bps`
  unchanged. The caller passes which idx is current; the function does not
  read config.
- `rederive_bonus(df) -> pd.Series`: group rows into fixtures by
  `(season_idx, gw, kickoff_time, fixture_pair)` where `fixture_pair` is the
  unordered `{team_code, opp_code}` pair (both sides of one match share it).
  Within each fixture, rank by adjusted BPS descending and award bonus with
  FPL tie rules:
  - tie for 1st among k players → each gets 3; next award skips to what the
    (k+1)-th place would get (k=2 → 3,3,1; k≥3 → 3,3,3,…,0);
  - tie for 2nd among k → each gets 2, none get 1 (2,2 then 0);
  - tie for 3rd among k → each gets 1.
  Exactly the published FPL bonus procedure; property: awarded bonus per
  fixture sums to 6 except in tie cases, where it sums to ≥6 per the rules
  above (tests pin both the standard 6 and each tie shape).
- `apply_new_bps(df) -> pd.DataFrame`: convenience wrapper returning the
  frame with `bps` replaced by the adjusted series and `bonus` replaced by
  the re-derived series (old columns kept as `bps_old`/`bonus_old`).

Integration:

- `load_training_frame` (src/gaffer/models/train.py) applies
  `apply_new_bps` before feature engineering, so `bps_r3/r5/r38`,
  `bonus_r5/r38` and the bonus target are all consistent with 2026/27 rules.
- `BonusModel` (src/gaffer/models/components.py) keeps the season-recency
  floor. **Correction found during planning:** `cbi` counts only exist in
  our history from 2025-26, so re-derivation can only restate 2025-26 (and
  the current season arrives new-rules); older seasons keep an old-rules
  bonus target no matter what. The floor is therefore still the defense
  against mixed regimes — what this cycle improves is the data inside the
  floor's window (2025-26's target corrected for CBI per-3), not the
  window itself. The original design ("drop the floor, train on all
  seasons of a fully restated history") is only reachable if per-match CBI
  counts for 2022-25 are ever sourced.
- Prediction-time features come from the same adjusted history, so there is
  no train/serve skew.

Gate (v2-style, measured on the last-10-(season_idx,gw)-slot holdout with
re-derived truth): bonus MAE for the floor-window model trained on the
*restated* target must not regress vs the same model trained on the stored
old-rules target, both scored against re-derived truth; overall EP
`mae_starters` must not materially regress. Accept on measured improvement
or neutral-with-cleaner-semantics; record numbers in this spec's outcome
section.

## 2. `gaffer evaluate` — the standing harness

New module `src/gaffer/evaluation.py` + CLI command `gaffer evaluate
[--mode current|benchmark]` (default `current`). Both modes write
`reports/evaluation.json` (merging under a per-mode key, preserving the
other mode's last result) and print a readable table.

Return categories, exactly OpenFPL's: Zeros (0 pts), Blanks (1–2), Tickers
(3–4), Haulers (≥5), plus All. Categories are defined on **actual** points.

**current mode**: the existing last-10-slot holdout protocol (train on
everything before, predict the held-out slots) reporting:
- stratified RMSE and MAE per category (all players, and starters-only as a
  secondary cut);
- log loss for p_play, p60 and the CS head, plus 10-bin reliability data
  per head: for each bin, `n`, mean predicted, observed frequency;
- baselines scored on the identical yardstick: last-5-mean points and
  season-PPG (reusing the existing baseline scoring in the train/eval
  path).

**benchmark mode**: train on seasons ≤ 2023-24 (idx 0–1), predict every GW
of 2024-25 (idx 2) at 1-GW horizon, walking forward so each GW's features
use only prior data (reuse the replay's `horizon_feature_rows` machinery).
Report the same stratified table beside hardcoded reference constants from
OpenFPL (arXiv:2508.09992) and FPL Review's numbers as published there —
constants live in `evaluation.py` with citation comments:
Zeros 0.818/0.689, Blanks 1.291/1.189, Tickers 1.517/1.594, Haulers
5.142/5.172 (RMSE, OpenFPL/FPL Review), and the matching MAE set. Stated
caveat, printed with the table and stored in the JSON: identical test
season and categories, but OpenFPL trained on four seasons (2020-21→
2023-24) to our two, and feature sets differ — treat as a yardstick, not a
controlled comparison.

`evaluation.json` shape (informal):

```json
{
  "current":   {"run_at": "...", "git_sha": "...", "holdout_slots": 10,
                "stratified": {"all": {"zeros": {"rmse": 0.0, "mae": 0.0, "n": 0}, "...": {}},
                               "starters": {"...": {}}},
                "heads": {"p_play": {"log_loss": 0.0, "reliability": [{"n":0,"pred":0.0,"obs":0.0}]},
                          "p60": {}, "cs": {}},
                "baselines": {"last5": {"...": {}}, "season_ppg": {"...": {}}}},
  "benchmark": {"run_at": "...", "git_sha": "...", "test_season": "2024-25",
                "stratified": {"...": {}},
                "references": {"openfpl": {"...": {}}, "fplreview": {"...": {}}},
                "caveat": "..."},
  "decomposition": {"...": "see section 3"}
}
```

## 3. Hindsight ("oracle") decomposition

`run_backtest` (src/gaffer/backtest.py) gains `ep_source: str = "model"`:

- `"model"`: today's behavior, bit-identical (regression-tested).
- `"oracle"`: the EP matrix is each player's **actual** `total_points` in
  that GW (0 for players who did not play), fed through the identical MILP
  pipeline — same pool construction, same solver, same chip logic, league
  tilt off. Availability filtering still applies as of the decision time
  (the oracle knows scores, not injuries announced later — this keeps the
  oracle reachable-in-principle rather than clairvoyant about news; the
  simplification is documented).

CLI: `gaffer evaluate --decompose` runs the 2×2 — {model, oracle} ×
{h1, h3} — over the 2025/26 GW5–38 replay and writes to the
`decomposition` key of `evaluation.json`: per cell, total points, pts/GW,
hit count; plus the two derived numbers with their names spelled out:
`forecast_gap_h3 = oracle_h3 − model_h3` (what better forecasting can win)
and `planning_ceiling = oracle_h3 − oracle_h1` (the most multi-week
planning can ever be worth). Runtime is roughly two extra full replays;
the plan must tell the operator to run under `caffeinate` (machine sleep
has killed long runs twice).

Wired-correctly check (test, small fixture): with `ep_source="oracle"` at
h1, the chosen XI's actual score per GW must be ≥ the model-EP run's actual
score on the same fixture data.

## 4. Model Quality UI page

- Backend: `src/gaffer/web/routers/quality.py`, `GET /api/quality` returns
  the parsed `evaluation.json` (404-style GafferError → 422 with a "run
  gaffer evaluate" message when the artifact is missing). Schemas in
  `schemas.py`; `frontend/src/types.ts` mirrored.
- Frontend: new sidebar entry "Model Quality" (route `/quality`),
  `frontend/src/pages/Quality.tsx`:
  - stratified table, one column group per source (ours / OpenFPL / FPL
    Review) in benchmark section; ours vs baselines in current section;
  - reliability curves for p_play/p60/CS via the existing `LineChart`
    component (predicted on x, observed on y, diagonal reference);
  - decomposition 2×2 card with the two derived numbers and one-line
    explanations;
  - empty state matching the other pages' pattern when the endpoint 422s.
- No jobs: `gaffer evaluate` runs from the CLI only in this cycle (training
  runs are minutes-to-hours; the UI renders artifacts, it does not launch
  them — consistent with keeping the job registry small).

## 5. Testing

TDD per task. Protected behaviors:
- tie-rule table tests for `rederive_bonus` (standard 3/2/1; 3,3,1; 2,2;
  1,1 shapes) and the sums-to-6 property on non-tied fixtures;
- `adjust_bps` leaves current-season rows untouched;
- benchmark mode leaks nothing: a source-text or split-assertion test that
  training data in benchmark mode has `season_idx <= 1` and prediction
  features for GW g use only rows strictly before g;
- `ep_source="model"` is bit-identical to the pre-change replay on the
  smoke fixture;
- the oracle-dominance check from §3;
- API schema ↔ frontend types covered by vitest as in v3.

## 6. Out of scope (deferred to later cycles)

- CRPS/PIT distributional metrics (v4c, once scenario machinery yields real
  distributions); xG features, Dixon-Coles, odds work (v4b); scenario
  re-solving, chip thresholds, FT shadow prices (v4c); risk dial and rival
  covering (v4d); news ingestion for minutes (later); running OpenFPL's
  actual code on our data (revisit only if the published-numbers comparison
  proves misleading).
