# Gaffer roadmap & task tracker

One place to see what's shipped and what's left. Grouping comes from
`research/2026-08-25-improvement-research.md`. Update this file as cycles
progress: flip `[ ]` → `[x]`, link the spec/plan when they exist.

## Shipped

### v1 — core advisor (done)
- [x] LightGBM component models (minutes p_play/p60, goals, assists, CS via team model, saves, bonus)
- [x] Multi-period MILP squad/transfer/chip optimizer, 3-GW receding horizon
- [x] CLI (`gaffer advise`, `gaffer backtest`)

### v2 — calibration, odds, league (done)
- [x] Probability calibration layer
- [x] Bookmaker odds blend for CS (fixed 0.7 prediction-time blend)
- [x] League mode: rival tracking + rank-aware EP tilt
- [x] Penalty-save EP; scoring-table bonus multiplier
- [x] `gaffer live` in-gameweek tracker

### v3 / v3.1 — web UI + fixes (done)
- [x] Local FastAPI + React web UI (advise, squad, league, live pages)
- [x] Fix cycle (GW19/20 chip horizon, differential tagging, etc.)

### v4a — measure (done, merged `b36a430` 2026-08-25)
Spec: `specs/2026-08-25-gaffer-v4a-measure-design.md` · Plan: `plans/2026-08-25-gaffer-v4a-measure.md`
- [x] BPS restatement for 2026/27 rules (CBI per-3, tackled −1 removed) with fixture-join bonus re-derivation
- [x] Evaluation harness: stratified metrics (zeros/blanks/tickers/haulers), log loss, reliability bins
- [x] OpenFPL/FPLReview benchmark mode (walk-forward 2024-25)
- [x] Oracle (perfect-foresight) replay + h1/h3 decomposition
- [x] `gaffer evaluate` CLI + `/api/quality` + Model Quality UI page
- Key results: haulers RMSE 5.245 vs OpenFPL 5.142 (~2% gap, half the training data);
  zeros 1.074 vs 0.818 (team-news gap); CS head badly calibrated (LL 0.619);
  h3 beats h1 by 2.79 pts/GW; planning ceiling ≈175 pts/season; forecast gap dominates.

### v4b — model (done, merged `5c97fb1` 2026-08-25)
Spec: `specs/2026-08-25-gaffer-v4b-model-design.md` (§13 = full outcome) · Plan: `plans/2026-08-25-gaffer-v4b-model.md`
- [x] Understat ingestion (site moved to JSON endpoints mid-cycle — client rewritten; 44,797 player-match rows, 92.9% id-mapped, 20/20 clubs every season)
- [x] Dixon-Coles team head (G1: CS log loss 0.6076 → 0.5474 controlled, honest reliability bins; ξ=0.0065)
- [x] Shin devigging + football-data closing odds (1,520/1,520 fixtures matched)
- [x] Fitted odds blend: w=0.80 via 1-SE rule (raw argmin 1.0 won on noise vs a sharper odds source than serve time)
- [x] xG/team/shrunken features (G2: benchmark haulers 5.245 → 5.184, within 0.8% of OpenFPL; k=20)
- [x] AGS odds layer (G3 no-key half proven byte-identical; live spot-check pending the odds API key)
- [x] Final adversarial review: 4 blockers found + fixed + re-verified (MERGE verdict); deferred nits recorded in spec §13
- Suite: 711 Python + 58 frontend, tsc clean

### v4c — decide (done, merged `2e6c454` 2026-08-26)
Spec: `specs/2026-08-25-gaffer-v4c-decide-design.md` (§12 = full outcome) · Plan: `plans/2026-08-25-gaffer-v4c-decide.md`
- [x] Scenario re-solving: N=40 noised solves → move-frequency gating (D1: 1818 vs 1743 raw, fewer transfers/hits) + CLI/UI "% of sims"
- [x] FT/hit shadow price λ(k,t) DP (multi-spend recursion; plan's sketch was degenerate) — D2 pass: 1814 vs 1810, hits 16 vs 18
- [x] Chip optimal-stopping thresholds θ_t — D3 pass, the cycle's big win: +73 total, chip points 555 vs 432, nothing stranded
- [x] Objective craft: itb 0.08, convex bench curve, ft_use_penalty 0.2 (measured inside D2)
- [x] Replay-calibrated decision_priors.json asset + `gaffer calibrate-decisions`
- [ ] DGW/BGW `chip_scenarios.toml` population — hook shipped; data lands ~Jan (Crellin)
- [x] Final adversarial review: 8 blockers fixed (incl. wildcard FT-bank double-charge = the λ×θ anomaly mechanism, confirmed; calibrator decontaminated), re-measured: D2 +43, both-on 1865 (+55) — MERGE
- Suite: 944 Python + 62 frontend; advise wall-clock 62.8 s with the full stack on

## In progress

### v4d — compete (league mode v2)
Spec: `specs/2026-08-26-gaffer-v4d-compete-design.md` (approved 2026-08-26)
- [ ] z = deficit/σ risk dial (variance seeking iff behind), σ estimated from league history
- [ ] Rival covering: observed-squad cover weights consumed by tilt_ep v2
- [ ] EO-aware mean-variance captaincy at the advise captain-override seam
- [ ] Tier-resolved live EO in tracker (sampled top-10k, display only)
- [ ] Gate E1: league replay GW20–38 vs recorded rivals, injected gap grid

## Planned

### Later — news ingestion (own cycle, external-data heavy)
- [ ] premierinjuries.com / predicted-lineups ingestion for minutes model (the zeros/blanks gap)
- [ ] Three-mode minutes model {DNP, sub, start}, cup-fixture congestion features

## Operational / housekeeping
- [x] Untrack `reports/` artifacts + `.claude/`; gitignore both (`31dc239`)
- [x] Set odds API key in `config.toml` `[odds]` (done 2026-08-25; G3 live spot-check recorded in v4b spec §13)

## Explicitly rejected (don't re-add)
- Price-change chasing · per-player finishing multipliers · big horizon extension · fabricated "EO thresholds"
