# Gaffer v4b "model" — design

Date: 2026-08-25 · Cycle: v4b of the v4 roadmap (`docs/superpowers/ROADMAP.md`)
· Research basis: `docs/superpowers/research/2026-08-25-improvement-research.md`
· Before-photo: v4a spec §7 tables (`specs/2026-08-25-gaffer-v4a-measure-design.md`)

## 1. Goal

Close the forecast gap v4a measured. The decomposition showed forecasting
dominates remaining loss (forecast_gap_h3 = 2405 pts vs planning_ceiling =
175). The two sharpest deficits:

- **CS head badly calibrated** — log loss 0.6190 on the current holdout.
- **Benchmark gaps vs OpenFPL (2024-25)**: haulers RMSE 5.245 vs 5.142;
  blanks 1.673 vs 1.291; zeros 1.074 vs 0.818 (zeros = team-news gap,
  explicitly out of scope for this cycle — that is the "later" news cycle).

Approach (user-approved "A: layered priors"): each new source is a
prior-generating layer; the existing GBM heads stay the supervised learners.
Every existing interface (`assemble_ep`, calibration, the three protected
source-text tests) survives unchanged.

Decisions locked in brainstorming: **one full cycle** (all five workstreams,
sequenced); **AGS odds best-effort on the-odds-api free tier** (graceful
degradation, assist props dropped); **own Understat scraper + cache** (no
third-party package, manual-override ID mapping).

## 2. What exists today (integration seams)

- `src/gaffer/models/team.py` — `TeamModel` (LGBM cs_clf + gc_reg on
  `TEAM_FEATURES` incl. `elo_diff`), `blend_team_odds` (fixed
  `ODDS_BLEND_WEIGHT = 0.7`, blends `p_cs`/`e_gc` where odds exist).
- `src/gaffer/data/odds.py` — the-odds-api client; `devig` (proportional),
  `invert_odds` (grid-search independent Poisson), `odds_frame`,
  `TEAM_ALIASES`, `poisson_win_prob`.
- `src/gaffer/data/elo.py` — `compute_elo`; `elo_diff`/`team_elo`/`opp_elo`
  feed TeamModel, AttackingModel, SavesModel.
- `src/gaffer/models/attacking.py` — per-position-group LGBM goals/assists
  on `ATTACK_FEATURES`, which already include FPL's own `xg_r*`/`xa_r*`
  (vaastav `merged_gw` carries FPL expected stats). Understat therefore
  contributes only its *marginal* signal: shots, key passes, xGChain,
  xGBuildup, npxG, and team-level xGA/PPDA.
- `src/gaffer/features/engineer.py` — `add_player_rolling` (shift(1)
  leakage discipline), `add_context`, `build_prediction_frame`,
  `feature_columns`.
- Protected source-text tests (must keep passing verbatim):
  - test_assemble: literal `ep_matrix(apply_calibration(assemble_ep(` in
    `run_advise`/`run_backtest`.
  - test_odds: `blend_team_odds(` appears before `comp.merge(tp`.
  - test_advise: `fetch_rival_entries(` < `tilt_ep(` < `pool = build_pool(`
    and literal `build_pool(players, pool_ep,`.
- Evaluation harness (`src/gaffer/evaluation.py`): `evaluate_current`,
  `evaluate_benchmark` (train idx≤1, walk-forward 2024-25), reports merged
  into `reports/evaluation.json`; `/api/quality` + Quality page render it.

## 3. Workstream 1 — historical closing odds (football-data.co.uk)

**New:** `src/gaffer/data/match_odds.py`

- Download per-season CSVs (`https://www.football-data.co.uk/mmz4281/{yy1}{yy2}/E0.csv`)
  for every season in the training window plus current; cache under
  `data/raw/football-data/{season}/E0.csv`; re-download the current season's
  file on refresh (it grows weekly), never the finished ones.
- Parse columns: `Date`, `HomeTeam`, `AwayTeam`, closing/average 1X2
  (prefer `AvgCH/AvgCD/AvgCA` closing averages; fall back `AvgH/AvgD/AvgA`,
  then `B365CH/...`, then `B365H/...` — first fully-present triple wins)
  and over/under 2.5 (`AvgC>2.5`/`AvgC<2.5`, same fallback chain).
- Team-name mapping: football-data uses its own short names ("Man United",
  "Nott'm Forest", "Wolves"). A dedicated `FOOTBALL_DATA_ALIASES` dict in
  `match_odds.py` mapping to FPL bootstrap names, same
  raise-on-unknown discipline as `resolve_team`.
- Join to our fixtures frame on (FPL home code, FPL away code, kickoff
  *date* in UK time) — date+teams is unique even in DGWs. Unmatched rows
  are counted and reported, not fatal.
- Output parquet `data/history/match_odds.parquet`:
  `[season_idx, gw, kickoff_time, home_code, away_code, p_home, p_draw,
  p_away, p_over25]` — probabilities already devigged (workstream 2).
- CLI: extend the existing data-refresh path so `gaffer refresh` (or the
  equivalent ingestion entry point) pulls/updates this parquet.

## 4. Workstream 2 — Shin devigging

**Modify:** `src/gaffer/data/odds.py`

- Add `shin_devig(prices: list[float]) -> list[float]`: solve for the
  insider-trading proportion z (Newton/bisection on the standard Shin
  identity) and return the implied true probabilities. For two-outcome
  markets Shin reduces cleanly; keep one implementation for n outcomes.
- `devig` (proportional) stays as documented fallback; all *match-odds*
  call sites (live `odds_frame`, historical `match_odds.py`) switch to
  `shin_devig`. Rationale: favourite–longshot bias distorts big favourites,
  exactly the teams FPL loads up on (Štrumbelj 2014).
- Property tests: outputs sum to 1, order preserved, longshot implied
  probability shrinks *more* than proportional devig would shrink it,
  degenerate inputs (equal prices, extreme favourite) do not diverge.

## 5. Workstream 3 — Dixon-Coles team model

**New:** `src/gaffer/models/dixon_coles.py` · **Modify:** `team.py` call
sites in train/assemble.

- Time-decayed Dixon-Coles: per-team attack αᵢ and defence βᵢ, home
  advantage γ, low-score dependence ρ, weights `exp(-ξ · Δdays)` from each
  match to the fit date. Fit by weighted MLE (scipy minimize, L-BFGS-B)
  over all historical fixtures up to the prediction cut. Identifiability:
  constrain mean(α) = 0 in log-space. Promoted teams with no history get
  the mean of the bottom-3 finishers' parameters.
- ξ default 0.0065/day (published ≈1-yr half-life); a small backtest grid
  {0.003, 0.0065, 0.01} scored by CS log loss on the current-mode holdout
  picks the shipped value — recorded in the spec outcome, then pinned.
- Output: for a fixture, the full scoreline pmf (goal cap 10) →
  `p_cs`, `e_gc`, P(win/draw/loss), and P(GC ≥ 2) bands. One coherent
  distribution serves CS, the −0.5/goal deduction, and saves context.
- **Replaces `TeamModel`'s GBM as the team predictor**: a `DixonColesModel`
  class exposing the same `fit(fixtures)` / `predict(team_future) ->
  [code, season_idx, gw, p_cs, e_gc]` frame contract, so
  `blend_team_odds(` → `comp.merge(tp` seam (protected test) is untouched.
  `TeamModel` stays in the codebase for one cycle as the fallback if the
  gate fails; the training path switches on a single constructor site.
- Elo: `compute_elo` **stays** — `elo_diff`/`team_elo`/`opp_elo` remain GBM
  features in attacking/saves/minutes heads (cheap, already validated).
  Only the team CS/GC head stops using it.
- DGWs: predict per fixture row (the team-future frame is already one row
  per fixture); no special handling needed beyond what exists.

## 6. Workstream 4 — fitted convex odds blend

**Modify:** `src/gaffer/models/team.py` (blend), artifacts persistence.

- Replace the constant `ODDS_BLEND_WEIGHT = 0.7` with a weight fitted at
  train time: on all historical fixtures with devigged closing odds
  (workstream 1), compute odds-implied `p_cs_odds = P(opponent scores 0)`
  from the odds-implied Poisson mus (reuse `invert_odds` on the historical
  triple + p_over25), and model `p_cs_model` from Dixon-Coles fitted with
  data strictly before each fixture (walk-forward by season half to keep it
  tractable). Fit w ∈ [0,1] minimizing log loss of
  `w·p_cs_odds + (1−w)·p_cs_model` against realized CS. One scalar; solved
  by golden-section/grid at 0.01 resolution.
- The fitted w is stored in the model artifact bundle and applied by
  `blend_team_odds` at prediction time (signature gains an optional
  `weight` argument defaulting to the artifact value; module constant
  remains as the no-artifact fallback). Rows without odds keep pure model
  output, exactly as today.
- This kills the train/serve skew: the weight is estimated on closing
  odds, the serve-time feed is also (approximately) closing odds.
- Report the fitted w in `gaffer evaluate` output and the spec outcome.

## 7. Workstream 5 — Understat ingestion + features

**New:** `src/gaffer/data/understat.py`, mapping override file
`src/gaffer/assets/understat_overrides.toml` (or json, matching existing
assets conventions).

- Scrape understat.com embedded JSON (`var playersData/teamsData/datesData =
  JSON.parse('...')` hex-escaped blobs) — no API, plain httpx GET + regex +
  `bytes.decode('unicode_escape')` style parsing, mirroring the raw-snapshot
  and retry discipline of `OddsClient`.
- Per **match** player stats come from `understat.com/match/{id}` roster
  JSON: xG, xA, npxG, shots, key_passes, xGChain, xGBuildup per player.
  Match ids per season from the league page `datesData`. ~380 pages per
  season, fetched once and cached permanently under
  `data/raw/understat/match/{id}.json`; only the current season fetches new
  matches on refresh. Politeness: ≥1s sleep between uncached requests.
- Team-level: `teamsData` from the league season page gives per-match xG,
  xGA, PPDA, deep completions → `data/history/understat_team.parquet`.
- Player parquet `data/history/understat_player.parquet`:
  `[season, season_idx, understat_id, player_name, team, date, minutes,
  shots, key_passes, npxg, xgchain, xgbuildup]`.
- **ID mapping** `map_understat_players(us_players, fpl_players) ->
  DataFrame[understat_id, code]`: exact match on normalized name
  (casefold, strip accents/punctuation) + same club first; then unique
  normalized full-name match across clubs (transfers); remainder resolved
  by the manual overrides file; still-unmatched players are logged with
  names and excluded (their rows contribute nothing rather than something
  wrong). The mapping report (matched/override/unmatched counts) prints on
  refresh.
- Join to `player_gw` on (code, season_idx, date-of-match); a player-match
  in FPL with no Understat row gets NaN stats (LightGBM handles NaN
  natively — no imputation).
- **Features** (in `features/engineer.py`, same shift(1) discipline):
  - Player rolling per-90 over windows r3/r5/r10/r38: `us_shots90`,
    `us_kp90`, `us_npxg90`, `us_xgchain90`, `us_xgbuildup90`
    (per-90 = rolling sum(stat) / rolling sum(minutes) × 90, computed from
    the shifted series; min_periods=1).
  - Team rolling r5/r38: own `us_xga`, own `ppda`, opponent `us_xga`,
    opponent `ppda` (opponent defensive weakness is the attacking signal).
  - Appended to `ATTACK_FEATURES`; team-level ones also to
    `SAVES_FEATURES` (shot volume against ≈ saves).
- **Shrunken-rate features** (small, pure-pandas): empirical-Bayes
  per-player `goals/90` and `assists/90` shrunk toward the position×team
  prior: `(sum stat + k·prior) / (sum 90s + k)` with k fitted once by
  maximizing out-of-sample correlation on the holdout (grid over
  {2, 5, 10, 20} nineties) — fixes the early-season small-sample regime.
  Added as `shrunk_goals90`, `shrunk_assists90` to `ATTACK_FEATURES`.
- Benchmark mode: Understat has full 2020-21…2024-25 coverage, so
  benchmark training/test frames get the same features — the OpenFPL
  comparison becomes more like-for-like.

## 8. Workstream 6 — AGS player-prop odds (best-effort)

**Modify:** `src/gaffer/data/odds.py` · touch: assemble/advise blend point.

- `OddsClient.get_player_goalscorer_odds(event_ids)` — the-odds-api
  per-event endpoint `events/{id}/odds` with
  `markets=player_goal_scorer_anytime`. Free tier: fetch only fixtures in
  the *next* GW, one snapshot per advise run, cached to raw dir; on 401/
  402/429-exhausted or missing market → return None and log, never raise
  (mirrors `get_epl_odds`'s no-key silence).
- AGS quotes are one-sided (back prices only), so Shin/proportional devig
  does not apply directly. Overround removal: within a fixture-team,
  scale implied `p_anytime` so that the team's total expected goals implied
  by `Σ −ln(1−p_i)` matches the devigged match-odds `mu` for that team
  (the market-consistent normalization). Players priced but not in FPL are
  dropped; FPL players unpriced get no odds signal.
- Convert: `λ_i = −ln(1−p_anytime_i)` per fixture → per-appearance
  `e_goals_odds = λ_i / p_play_i` capped at a sane 2.0.
- Blend at prediction time with the model's `e_goals` per player:
  `w_ags · e_goals_odds + (1−w_ags) · e_goals_model`, `w_ags` a config
  value default 0.5 (there is no historical AGS record to fit on — noted
  as a known limitation; revisit once a season of snapshots accumulates).
  Rows without AGS odds keep pure model output. The blend lives in a
  helper `blend_attacking_odds(...)` called in the advise path *before*
  `assemble_ep`'s inputs are built, keeping protected literals intact.
- Name matching: odds feed uses "Erling Haaland"-style full names →
  normalized-name + team match against bootstrap, unmatched logged and
  skipped. Config: `[odds] player_props = true|false` (default true;
  degrades silently to false without a key).

## 9. Evaluation & merge gates

Run after each landing stage, full suite at the end; all results appended
to spec §Outcome and `reports/evaluation.json` (harness from v4a, no
changes needed).

- **Gate G1 (Dixon-Coles + fitted blend)**: current-mode CS log loss
  < 0.6190 (v4a value) and CS reliability visibly closer to diagonal; no
  regression in stratified EP cells beyond noise (±2%).
- **Gate G2 (xG features + shrunken rates)**: benchmark haulers RMSE
  ≤ 5.245 and current-mode haulers RMSE ≤ 4.950 (i.e. not worse); target,
  not gate: haulers ≤ 5.17 (FPLReview parity).
- **Gate G3 (AGS)**: with AGS enabled on a live-odds week, EP deltas are
  bounded and plausible (spot check); with no key, byte-identical output
  to the no-AGS path (regression test with client returning None).
- **Global**: 475+ Python tests green, 58+ frontend, `tsc -b` clean; the
  three protected source-text tests untouched; `run_backtest` default path
  unchanged unless a gate-passing model change explains the diff.
- If G1 fails after the ξ grid: keep `DixonColesModel` behind a config
  flag, ship the fitted blend on the old TeamModel, record the negative
  result. If G2 fails: drop the offending feature block (features are
  additive; LightGBM intersect makes removal safe), record it.

## 10. Config & operational

- `config.toml` additions: `[odds] player_props` (bool, default true);
  `[understat] enabled` (bool, default true) — both degrade to
  model-only behaviour when data is unavailable.
- The user registers a free the-odds-api key (`[odds] api_key`) — gaffer
  works without it, AGS and live CS blending simply stay off.
- New data refresh steps folded into the existing ingestion entry point;
  first full Understat backfill (~5 seasons × 380 matches) runs under
  `caffeinate -i` and is resumable (cache-by-match-id makes re-runs cheap).
- No web/UI work: the Quality page re-renders whatever
  `reports/evaluation.json` holds.

## 11. Testing strategy

TDD throughout (per plan). Unit tests on: Shin devig properties;
Dixon-Coles on synthetic data (recover known α/β/γ/ρ within tolerance;
decay weighting shifts estimates toward recent form); scoreline pmf sums
to 1 and p_cs consistency; blend-weight fit on synthetic calibrated/
miscalibrated mixtures recovers the right w; football-data parsing +
alias resolution on fixture CSV snippets; Understat JSON parsing on a
saved raw sample; ID mapping (exact/cross-club/override/unmatched paths);
per-90 rolling leakage (a match's features never include that match);
shrinkage formula; AGS normalization against team mu; graceful-degradation
paths (no key, no market, no Understat data). Integration: end-to-end
train+predict on the existing test fixtures with all new sources absent →
identical behaviour to v4a (the degradation rail is itself a test).

## 12. Sequencing (locks the plan's task order)

1. football-data ingestion + Shin devig (data foundations, no model change)
2. Dixon-Coles model + fitted blend → **measure G1**
3. Understat scraper + ID mapping + parquets (backfill run)
4. xG/team/shrunken features into GBM heads → **measure G2**
5. AGS odds layer → **verify G3**
6. Full `gaffer evaluate` (current + benchmark), outcome tables into §13

## 13. Outcome

(Filled as gates are measured; completed at cycle end.)

### Ingestion (workstream 1)

football-data closing odds: **1,520/1,520 fixtures matched** across
2022-23…2025-26 (1,482 on the first run; the 38 missing were every Ipswich
fixture of 2024-25 — FPL renamed the club "Ipswich" → "Ipswich Town" between
seasons, bridged by `FPL_RENAMES` in `match_odds.py`, commit `208a695`).

### G1 — Dixon-Coles CS head (PASSED, controlled)

ξ grid on the current-mode holdout (last 10 (season, gw) slots, ~200
team-GW rows), CS log loss:

| ξ | CS log loss |
| --- | --- |
| 0.003 | 0.5510 |
| 0.0065 | 0.5506 |
| 0.01 | 0.5505 |

Flat to within noise → `DEFAULT_XI` pinned at the published 0.0065.

The v4a baseline (0.6190) was measured on the pre-GW1-2026/27 corpus, and
unchanged heads (p_play 0.2732→0.2996, p60 0.2563→0.2782) show the corpus
shift alone moves log losses. So G1 was decided by a **controlled re-run of
the GBM team head (`TEAM_MODEL = "gbm"`) on the identical corpus**:

- GBM CS log loss **0.6076**; worst reliability bins pred 0.046/obs 0.175
  and pred 0.153/obs 0.294.
- Dixon-Coles CS log loss **0.5506** (−9.4%); reliability bins track the
  diagonal through the populated range (e.g. pred 0.255/obs 0.272,
  pred 0.350/obs 0.333).

Stratified EP cells are bit-identical between the two runs **by design**:
`predict_components_simple` scores the CS head separately and uses constant
`DEFAULT_P_CS`/`DEFAULT_E_GC` in the EP assembly, so the no-regression check
on EP cells is unaffected by the team-head switch in this mode. The EP-level
effect of Dixon-Coles lands through the advise/backtest path instead.

`TEAM_MODEL` stays `"dixon_coles"`.

### G2 — pending (Task 21)

### G3 — pending (Task 23)
