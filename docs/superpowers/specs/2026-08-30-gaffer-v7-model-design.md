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

### M1 diagnostic (run 2026-08-30, git 1f18b34, 10 holdout slots, n=4929)

The zeros error is NOT a fringe problem — it is a regulars problem:

| stratum | n | rmse | mean_ep |
|---|---|---|---|
| fringe (start-share < 0.3) | 3810 | 0.471 | 0.184 |
| regular | 782 | **2.245** | 1.710 |
| cold start (first 4 GWs) | 318 | 1.558 | 1.188 |
| settled | 4611 | 1.021 | 0.446 |
| recent absence | 3671 | 0.198 | 0.101 |
| recent presence | 1181 | **2.131** | 1.690 |
| flagged | 0 | — | (official status is a live bootstrap field, not stored historically — stratum underivable) |

DNP reliability is only mildly miscalibrated; the material cell is
decile 0 (nailed starters, n=1134): predicted DNP 6.3% vs observed 7.9% —
regulars DNP more than the model thinks, which is precisely the
late-team-news population OpenFPL's feeds catch. Mid deciles slightly
over-predict DNP (+0.01–0.03). Interpretation: I1 recalibration corrects
the right sign but the magnitude is small; Z1 unlikely to clear its 2%
bar. Run anyway per the plan — pre-registered, cheap, and a negative
result is a result. The structural fix for this population is news-driven
(the N2 corrector once the shadow log has a season), not calibration.

**I2 recorded infeasible** (per plan Interpretations §I-C): every
registered element has a row every gameweek (2025-26 GW10: 747 rows,
29–45 per club — full squad lists), all zero-minute rows carry
bps/starts/cs/gc of 0, and no column separates an unused substitute from
a player never named; `unused_sub_r5` / `squad_share_r5` are underivable
and spec §2.2 forbids scraping for them.

### Gate Z1 — FAIL (pre-registered rule applied; I1 ships OFF)

Arms on the v4a harness, 2026-08-30 (`logs/z1_arms.log`):
OFF arm reproduced the 2026-08-29 baseline exactly (zeros 1.063,
haulers 5.145, all 1.986 — harness validity check). ON arm (isotonic DNP
recalibration): zeros **1.053** (−0.9%), haulers 5.149 (guard pass,
≤5.171), all 1.992 (guard pass). The bar was ≤1.042; verdict FAIL.

Exactly what the diagnostic predicted: right sign (the calibrator lifts
the nailed-starter DNP rate toward the observed 7.9%), insufficient
magnitude — the regulars-who-sit error is news-shaped, not
calibration-shaped. `DNP_CALIBRATION_DEFAULT` stays `False`; the
calibrator, leakage rails, and z1_arms driver stay in the tree.

*User decision available later:* the ON arm is a strict Pareto
improvement over shipped (better zeros, guards passed) but fails the
pre-registered bar; per §0 D2/D3 an ambiguous call ships OFF and is left
to the user. Flipping is one constant.

### M2 design call (orchestrator, §0 D1 authority)

Seed-only LightGBM refits proved fully deterministic under `LGB_KW`
(no subsample/colsample; verified empirically by the implementer —
identical models seed to seed), so seeded ensemble members 1–4 carry
`ENSEMBLE_KW = {subsample 0.8, subsample_freq 1, colsample_bytree 0.8}`;
member 0 remains the served fit, byte-identical. σ_est therefore measures
the spread of resampled refits around the served model — an approximate
bootstrap — rather than a symmetric seed ensemble. Accepted: it is a
legitimate (arguably better-founded) estimation-uncertainty measure, the
serving path is untouched, and gate S2's shipping rule is outcome-based.

(Remaining outcome recorded at cycle end.)
