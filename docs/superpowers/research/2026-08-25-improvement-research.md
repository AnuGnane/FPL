# Improvement research — literature & community survey (2026-08-25)

Four parallel research sweeps: academic FPL/fantasy optimization, football
forecasting methodology, the FPL analytics community's applied state of the
art, and adjacent decision science (DFS portfolio theory, optimal stopping,
rank-game strategy). This document is the synthesis; sources inline.

## Urgent housekeeping (do before anything else)

- **2026/27 BPS rules changed**: the −1 BPS for being tackled is removed, and
  clearances/blocks/interceptions now earn 1 BPS per **three** actions (was
  per two). Any bonus component trained on 2025/26 data is miscalibrated —
  our scoring-table bonus multiplier (commit `8a4a702`) needs re-derivation.
  https://www.premierleague.com/en/news/4679946
- **FBref advanced stats are dead** (Opta data pulled 2026-01-20). Understat
  (shot-level xG, scrapable JSON) is now the primary free xG source; FotMob's
  undocumented JSON API is the Opta-derived fallback.
- FPL now ships an **official price-change predictor** (15-min updates) and
  price changes moved to 00:00 UK — do not build price prediction ourselves.

## The six convergent findings

### 1. Scenario re-solving: decide by move *frequency*, not one optimum
Ranked #1 or near-#1 by all four sweeps, from independent directions:
- Matthews et al. (AAAI 2012): sampling 40 candidate squads from *noisy* EP
  beat solving once against converged means (2034 vs 2022 pts); lookahead's
  real benefit was left-tail protection, not mean gain.
  https://ojs.aaai.org/index.php/AAAI/article/view/8259
- Michaud "resampled efficiency" / sample-average approximation: MILPs on
  point estimates are estimation-error maximizers; perturb inputs, re-solve,
  act on decisions that survive most scenarios.
- The community solver (solioanalytics/open-fpl-solver, ex-sertalpbilal) does
  exactly this in production: N randomized solves with **minutes-scaled
  noise** `Pts × (92 − xMins)/134 × N(0,1)`, aggregated into "% of sims that
  buy X / sell Y" tables. The community decides on that percentage.
- Rule: irreversible actions (chips, hits, wildcards) need a *higher*
  frequency threshold than reversible ones.

**Gaffer fit**: our MILP + saved solve-state already support re-solving; this
is a loop + aggregation table + UI column ("bought in 78% of sims").

### 2. Attacking EP: Understat xG features + de-vigged goalscorer odds
- OpenFPL (arXiv:2508.09992, MIT code) — free-data XGBoost/RF ensembles with
  Understat features — **matches FPL Review's paid model at 1-GW horizon and
  beats it on haulers/tickers**; loses only on zeros/blanks (minutes/news).
  Benchmark numbers: overall RMSE 2.048; haulers 5.142 vs 5.172.
  Decomposition: xG features buy the haul tail, minutes/news buys the zeros.
- Add xG/xA/shots/key passes/xGChain/xGBuildup + team xGA/PPDA as per-90
  rolling rates. Do **not** fit per-player finishing multipliers — KU Leuven
  (arXiv:2401.09940) shows finishing skill is unidentifiable at realistic
  shot volumes and public xG is biased by player subgroup.
- De-vig **anytime-goalscorer / assist odds** → λ = −ln(1−p) per fixture,
  divided by implied start prob. We already trust the market for CS and
  ignore it for the ~70% of points from goals/assists. Use Shin or power
  devigging, not naive normalization (Štrumbelj, IJF 2014; favourite-longshot
  bias distorts big favourites — exactly the teams FPL loads up on).
- Move odds into *training* as a fitted convex-combination prior (Egidi et
  al., arXiv:1802.08848) instead of the fixed 0.7 prediction-time blend;
  backfill historical closing odds to kill the train/serve skew.

### 3. Team model: Dixon-Coles instead of Elo
Elo loses to odds-based forecasts (Hvattum & Arntzen 2010) and only emits a
win probability. A time-decayed Dixon-Coles (or diagonally-inflated bivariate
Poisson) attack/defence model gives one coherent scoreline distribution from
which CS, goals-conceded bands, and saves all derive — and slots in as the
"historical" half of the odds convex combination. Tune the decay (published
ξ=0.0065 ≈ 1-yr half-life; over-decay hurts). penaltyblog has implementations.

### 4. Chip timing: declining reservation thresholds over the full season
- Our 3-GW window structurally cannot see the DGW/BGW that makes a chip worth
  2×. O'Brien et al. (PLoS ONE 2021, ~1M managers): bench boost returned
  23.2 pts to top-10k (79.4% of whom held it for DGW35) vs 13.8 to the field
  — chip *timing* dominates chip squad-optimization.
- Formulation (a genuine literature gap — no published paper): one-dim
  optimal stopping per chip. Precompute θ_t = E[max remaining surplus] by
  backward recursion over simulated future GW surplus distributions; play the
  chip iff this week's MILP surplus ≥ θ_t. θ_t declines to 0 at the half
  expiry (GW19 / GW38). Real-options logic: hurdle > break-even while
  optionality remains (Dixit & Pindyck); Bruss's odds theorem for the
  max-type framing.
- Encode unconfirmed DGWs the community's way: probability-weighted fixture
  scenario files (Ben Crellin's per-team probabilities, from ~Jan), weighted
  numbers of noised solves per scenario, pooled into one decision table
  (`binary_fixtures` pattern in open-fpl-solver).
- 2026/27 half-1 empirics (FFS survey n≈3.7k): WC1 by GW6 (77%), BB1 GW1-2
  (97.5% — knowingly -EV, no half-1 DGW), TC premium home fixture.

### 5. FT/hit valuation: shadow price from a tiny DP
- Community solver: `ft_value` 1.5 flat, but the better version is
  state-dependent diminishing `{2:2.0, 3:1.6, 4:1.3, 5:1.1}` — value of
  rolling the k-th FT.
- Theory match: energy-harvesting-with-finite-battery literature (resource
  arrives 1/GW, cap 5, overflow lost, concave utility) ⇒ double-threshold
  policy; marginal value λ(k,t) from a DP over (FTs held, GWs left);
  never idle at the cap; λ→small late season.
- Hit rule becomes: take the hit iff horizon EP gain > 4 + λ(k,t). Wildcard
  option value must be computed net of the FT-bank value it destroys.
- This is the principled answer to our backlog item "why doesn't multi-week
  planning beat h1" — the coupling belongs in shadow-price scalars, not in a
  longer MILP horizon. Supporting: Matthews depth≥4 degraded results;
  Bergman & Imbrogno (OR 2017) found partway-season planning beats
  full-season planning in a one-shot-resource pool. Community norm is
  horizon 8, decay 0.85–0.9 — worth one controlled experiment, but evidence
  says gains live in the scalars.
- Other objective craft worth copying: `ft_use_penalty` 0.2, `itb_value`
  0.08/£1m (O'Brien: £1m at GW19 ≈ +21.8 final pts), vice-captain weight
  0.1, convex bench weights {0.21, 0.06, 0.002}, no-transfers-in-last-2-GWs
  of the window, report the same plan under multiple decays.

### 6. Risk dial + rival covering (league mode v2)
- z = (deficit to target) / (σ of remaining-horizon margin). Under a normal
  approx, variance helps iff you're behind; the exchange rate is z EP of
  mean per unit of σ (Browne's goal-reaching portfolios; Anderson & Cabral
  contests; Skinner basketball; poker ICM — five literatures, one policy:
  cover when ahead, split when behind).
- Haugh & Singal (Mgmt Sci 2021): under rank payoffs, *risk-neutral*
  optimization already reduces to mean-variance vs the field — variance
  seeking is not a preference, it falls out of the payoff shape. Captaincy
  should be EO-aware mean-variance, not argmax EP.
- Mini-league advantage: we *observe* rivals' actual squads, so covering is
  computable, not estimated: add an overlap term signed by z (maximize
  overlap when ahead, minimize when behind). Çay's ownership-weighted
  objective (alpscode.com/blog/fpl-ownership-weight) is the cheap global-rank
  analogue.
- **We are ahead here**: no public tool optimizes rank/P(top-k); our λ tilt
  is novel, not catch-up.

## Evaluation upgrade (do first in wall-clock terms)
- Stratified metrics by return category (Zeros / Blanks ≤2 / Tickers 3-4 /
  Haulers ≥5) exactly as OpenFPL; benchmark against OpenFPL's published
  2024-25 table and a last-5 baseline (keep a dumb persistence baseline in
  the harness forever — arXiv:2505.02170's ARIMA-beats-ridge warning).
- CRPS for count components, log score for p_play/p60/CS, PIT histograms;
  select models on calibration, not aggregate MAE (Walsh & Joshi: +34.7% vs
  −35.2% ROI from changing only the selection criterion).
- **Hindsight decomposition** (Bonomo et al. two-model design): run the MILP
  with perfect-foresight EP vs our EP over a replay season. The gap tells us
  whether remaining loss is forecasting or optimization — and
  perfect-foresight-at-h1 vs -at-h3 bounds the *maximum* value of multi-week
  planning. Cheap; retargets the roadmap.

## Minutes model: it's a data problem, not a model problem
We're at published state of the art (two-stage p_play/p60 + rotation
features; no literature beats GBMs here). The commercial edge (OpenFPL's
zeros/blanks deficit) is **news ingestion**: premierinjuries.com / Ben
Dinnery (injury type + expected return, ~1 day ahead of the official flag),
Transfermarkt injury spells (empirical return-time distributions by injury
type), FFS/Hub predicted lineups. Also: model minutes as three modes
{DNP, sub, start}, manager-level rotation random effect, European/cup
fixtures ±4 days (olbauday/FPL-Core-Insights has cup fixtures joined to FPL
IDs). Hierarchical/empirical-Bayes shrunken per-player rates (toward
position×team priors) as GBM *features* fix the early-season noise regime.

## Explicitly rejected
- Price-change chasing (≈0.05 pts/GW per £1m, halved by sell-price rule;
  now an official FPL feature anyway).
- Per-player finishing-skill multipliers (unidentifiable).
- Big horizon extension as the primary fix (evidence favors shadow prices).
- AI-SEO "EO thresholds" circulating in 2026 search results (fabricated).

## Where gaffer is already validated
- 3-GW receding horizon: supported by Matthews (depth≥4 degraded) and
  Bergman & Imbrogno (partway planning wins) — with the caveat that chips/FT
  coupling must then live in season-level scalars (findings 4 & 5).
- Odds blending direction correct; needs devigging + train-time fit.
- Rank-aware league tilt: genuinely novel vs everything public.

## Suggested cycle grouping (for a future brainstorm)
- **v4a "measure"**: BPS re-derivation; stratified/calibration eval harness +
  OpenFPL benchmark; hindsight decomposition.
- **v4b "model"**: Understat xG features; Dixon-Coles replacing Elo; odds
  devigging + train-time convex blend + AGS/assist odds; shrunken-rate
  features.
- **v4c "decide"**: scenario re-solve with frequency tables; FT shadow price
  λ(k,t) DP + hit rule; chip reservation thresholds θ_t + weighted fixture
  scenarios; objective craft (itb_value, vcap, bench weights).
- **v4d "compete"**: z risk dial; rival covering/overlap term; EO-aware
  captaincy; tier-resolved live EO in the tracker.
- **later**: news ingestion for minutes (premierinjuries/lineups scraping —
  own cycle, external-data heavy).
