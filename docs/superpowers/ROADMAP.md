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

## In progress

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

## Planned

### v4c — decide (optimization quality)
- [ ] Scenario re-solving: N noised solves → move-frequency tables ("bought in 78% of sims") + UI column
- [ ] FT/hit shadow price λ(k,t) from small DP; hit rule `gain > 4 + λ`
- [ ] Chip optimal-stopping thresholds θ_t (backward recursion, declining to expiry)
- [ ] Probability-weighted DGW/BGW fixture scenarios (Crellin-style)
- [ ] Objective craft: itb_value, vice-captain weight, convex bench weights, ft_use_penalty

### v4d — compete (league mode v2)
- [ ] z = deficit/σ risk dial (variance seeking iff behind)
- [ ] Rival covering: overlap term signed by z (we observe actual rival squads)
- [ ] EO-aware mean-variance captaincy
- [ ] Tier-resolved live EO in tracker

### Later — news ingestion (own cycle, external-data heavy)
- [ ] premierinjuries.com / predicted-lineups ingestion for minutes model (the zeros/blanks gap)
- [ ] Three-mode minutes model {DNP, sub, start}, cup-fixture congestion features

## Operational / housekeeping
- [ ] Untrack `reports/` artifacts + `.claude/scheduled_tasks.lock` (user commit 5efb1a0); gitignore `reports/`
- [ ] Set odds API key in `config.toml` `[odds]` (free tier at the-odds-api.com)

## Explicitly rejected (don't re-add)
- Price-change chasing · per-player finishing multipliers · big horizon extension · fabricated "EO thresholds"
