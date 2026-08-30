# gaffer v7-model — zeros, honest noise, and the first news verdict

Date: 2026-08-30 · Status: approved for planning (autonomous — see §0)
Branch: `feat/gaffer-v7-model`

## 0. Autonomy note

The user is away and delegated this cycle ("make any decisions assume how
and what i would do"). Decisions taken on their behalf, per the pattern of
v4a–v7-ui, all flagged here for review:

- D1: Scope = the two measurable model levers already queued (zeros gap,
  estimation-only σ) plus the N2 reading when GW2 closes and one deferred
  UI nit. No speculative features; everything behind a pre-registered gate.
- D2: A failed gate ships OFF behind its flag with the negative result
  recorded (the v5 N1 / v6 S1 pattern), never silently.
- D3: Merge to main + push only if every gate's shipping decision is
  clean-cut under its pre-registered rule and the adversarial review ends
  MERGE; anything ambiguous stays on the branch for the user.
- D4: No spend beyond compute; no config/key changes; protected files
  untouched as always.

## 1. Why this cycle

Fresh walk-forward evaluation (2026-08-29, `reports/evaluation.json`):
haulers RMSE 5.145 ≈ OpenFPL parity (5.142) — that battle is won. But
zeros RMSE is **1.063 vs 0.818** for OpenFPL, and — sharper — **the naive
last-5 baseline beats the model on the zeros stratum (1.042 vs 1.063)**.
The model over-forecasts players who end up playing 0 minutes. That is the
single largest remaining forecast gap and it is minutes-model territory,
not attack-model territory.

Second thread: v6's calibrated scenario noise failed gate S1 because
residual σ conflates forecast error with football's irreducible variance.
The pre-registered follow-up was an **estimation-only σ** (spread of an
ensemble of refits — how unsure the *model* is, not how random football
is). The opt-in serving path, asset format, and the honest gated-replay
driver (`s1b_driver.py`, still in the session scratchpad) all exist.

Third: GW2 finishes this weekend → the news layer's first scored N2
verdict via `gaffer evaluate --news-shadow`.

## 2. M1 — zeros (diagnose first, then gate)

### 2.1 Diagnostic (no gate; a report)

Decompose the zeros-stratum error on the 2025-26 walk-forward frame by
sub-population, so the intervention is chosen by evidence:

- flagged (official status i/s/u/n/d) vs unflagged rows;
- fringe (season start-share < 0.3) vs regulars;
- first-4-GWs-of-season vs rest (promoted/new-signing cold start);
- p_play decile calibration curve for the DNP mode specifically
  (predicted vs observed DNP rate per bin).

Artifact: printed table + `reports/zeros_diagnostic.json` (gitignored
path, i.e. under reports/). The diagnostic decides which interventions
below are attempted; any not supported by it are recorded as skipped.

### 2.2 Candidate interventions (at most two attempted, smallest first)

- **I1 DNP recalibration**: isotonic (or Platt, whichever the existing
  calibration layer uses) recalibration of the ThreeModeModel's DNP-mode
  probability, fitted walk-forward (no leakage: calibrator for slot t fits
  on slots < t). Cheapest; targets exactly "over-forecasting non-players".
- **I2 fringe features**: squad-appearance share and bench-unused share
  over recent windows (e.g. `unused_sub_r5`, `squad_share_r5`) appended to
  MINUTES_FEATURES — data already in `player_gw.parquet` (minutes==0 with
  appearance vs not in squad needs the FPL availability of bench data;
  if the distinction is not derivable from stored data, I2 is recorded
  infeasible and skipped — do NOT scrape anything new for it).
- **I3 hint symmetry** is explicitly REJECTED this cycle: raising p_play
  from FFS lineups reverses a deliberate v5 decision and needs a season of
  N2 shadow evidence, which does not exist yet.

### 2.3 Gate Z1 (pre-registered)

On the v4a evaluation harness (same walk-forward slots as the 2026-08-29
run): zeros RMSE must improve by ≥ 2% (1.063 → ≤ 1.042, i.e. at least to
the last-5 baseline) AND haulers RMSE must not regress by > 0.5% (≤ 5.171)
AND all-stratum RMSE must not regress by > 0.5%. Shipping rule: pass →
intervention ships on; fail → shipped OFF (feature list / calibrator flag
reverted), negative result recorded in §9. Each intervention is measured
alone before any combination.

## 3. M2 — estimation-only σ (gate S2)

- σ from a K=5 LightGBM seed-bagged ensemble of the attacking heads +
  minutes model: at each serve, σ_est(player) = std of the K EP readings.
  Fitted offline into the existing 13-cell (EP bin × xmins bin) table
  format on the 2025-26 walk-forward (same binning as v6:
  EP_EDGES [0,2,3,4,6], XMINS_EDGES [0,30,60,80], MIN_CELL_OBS 100,
  pooling cell → EP marginal → global) — a drop-in
  `scenario_noise.json` replacement asset, marked `"source":
  "estimation"`.
- Serving: the existing parked opt-in path (`CALIBRATED_NOISE_DEFAULT`,
  `noise_ep(..., table=)`, Newton mean-preserving recentre) — zero new
  serving code.
- Gate S2 (pre-registered, identical harness to S1): the s1b gated-replay
  driver, 2025-26, N=40 scenarios, seed 20260827+gw, heuristic arm vs
  estimation-σ arm. Ship (flip `CALIBRATED_NOISE_DEFAULT = True`) only if
  the estimation arm's total ≥ heuristic − 5 (a tie is a win for the
  better-founded noise model) AND captain sim-support on the current live
  advise stays ≥ 60% (the v6 failure symptom). Fail → asset committed with
  `"source": "estimation"`, default stays False, result recorded.
- The v6 residual-σ asset is superseded either way (replaced or annotated).

## 4. N2 — the first news verdict

When FPL marks GW2 `data_checked`: run `gaffer evaluate --news-shadow`,
record the scored verdict (zeros with/without news layer, movers hit rate)
in §9 and the Model hub's scoreboard. If GW2 is still open when the cycle
otherwise completes, record "pending — run after GW2" in §9 and do not
block the merge decision on it.

## 5. UI nit (from v7-ui deferred list)

Compare-card player names: give `Card` an optional `titleSize="lg"` (or a
`heading` slot) so ComparePanel renders the player's name prominently
(primary text size, not the 9px uppercase label), keeping `PosBadge`
adjacent. Frontend-only, tested.

## 6. Constraints

- Protected suites and files exactly as every cycle; `run_advise` ordering
  pins must hold; degradation rails sacred (asset absent → byte-identical
  serving).
- Long replays via nohup+caffeinate, Monitor-style polling of grep'd log
  lines; memoize `train_all`/`load_training_frame` across ablation arms
  where the E1/N1 driver pattern allows.
- No changes to the optimizer, odds blend, set pieces, or news fetchers.

## 7. Testing

- Diagnostic: unit-tested decomposition helpers (synthetic frame).
- I1/I2: walk-forward-leakage test (calibrator/feature builder for slot t
  must not see slot ≥ t); degradation test (no calibrator asset / feature
  columns absent → prior behaviour byte-identical).
- M2: asset-shape validator reused; ensemble builder tested on a toy
  frame (σ of identical models ≈ 0; σ grows with seed diversity);
  opt-in flip test pattern from v6 reused.
- Gates run by the orchestrator, never asserted by implementers.

## 8. Execution

Opus planner → grouped Opus implementers (M1 diagnostic+I1, M1 I2 if
supported, M2 ensemble+asset, N2+UI nit) → orchestrator-run gates →
adversarial review → fix rounds → merge per D3.

## 9. Outcome

Recorded at cycle end.
