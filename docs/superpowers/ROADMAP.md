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

### v4b — model (forecasting quality) ← CURRENT
Goal: close the forecast gap v4a measured. Benchmark table in v4a spec §7 is the before-photo.
- [ ] Brainstorm → spec
- [ ] Implementation plan
- [ ] Understat xG ingestion (shot-level → per-90 rolling xG/xA/shots/key passes/xGChain/xGBuildup; team xGA/PPDA)
- [ ] Dixon-Coles time-decayed attack/defence team model replacing Elo (fixes CS calibration; scoreline distribution → CS, GC bands, saves)
- [ ] Odds devigging (Shin/power, not naive normalization)
- [ ] Odds into training as fitted convex-combination prior (replace fixed 0.7 blend; backfill historical closing odds)
- [ ] Anytime-goalscorer / assist odds → per-fixture λ for attacking EP
- [ ] Shrunken per-player rate features (empirical-Bayes toward position×team priors)
- [ ] Re-run `gaffer evaluate` benchmark + current; record before/after in spec §Outcome
- [ ] Merge gate: no regression on any stratified cell; CS log loss improved

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
