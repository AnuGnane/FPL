# gaffer v2 — accuracy pass, rank-aware league mode, planner validation

Date: 2026-08-24. Status: approved by user (brainstorm 2026-08-24).
Builds on: `2026-08-23-fpl-ml-advisor-design.md` (v1, merged to main at `2533119`, 96 tests).

## 1. Goals

1. **Accuracy**: close the known −1.1 pt bias on 60+ minute starters; add set-piece
   awareness; ingest bookmaker match odds as team-strength features.
2. **Win the mini-league**: automatic rank-aware strategy that tilts squad selection
   toward differentials when chasing and cover when defending, driven by the
   standings of league 1794743.
3. **Validate the planner**: backtest the multi-week horizon and chips — the two
   headline features v1's replay never exercised.
4. **Completeness**: GW1 initial-squad advice, chip-half straddle fix, `gaffer live`,
   penalty-save points, bonus multiplier from scoring table, dead-code sweep.

Out of scope: goalscorer/player-prop odds (paid tier), Monte Carlo rank simulation,
authenticated FPL endpoints (tool stays advisor-only), UI beyond CLI + HTML report.

## 2. Phase A — accuracy

### 2.1 Calibration layer (`src/gaffer/models/calibrate.py`)

*Rewritten to describe what shipped. This section originally specified
isotonic regression; it was redesigned twice during gate A — see the GATE A
OUTCOME note in §7 for the historical record and the measured numbers.*

- Post-assembly correction: an **additive, p60-gated, per-position delta**.
  `CalibrationModel` stores one scalar per position group (GKP/DEF/MID/FWD)
  and `apply()` adds `p60 * delta` to the assembled `ep`. It is not a
  monotone remap of ep — it is a level correction, which is what the measured
  bias actually was.
- The delta is the *conditional* bias `E[actual - ep | 60+ minutes]`, fit on
  60-minute appearances only. The correction decomposes as
  `E[bias] = P(60+ minutes) * E[bias | 60+ minutes]`, and `apply()` supplies
  the first factor from `p60`, so what is fit has to be the second. Fitting on
  every appearance would mix cameos into the conditional and double-count the
  gate.
- Fit in `train_all` on genuinely out-of-sample predictions: the last
  **10 `(season_idx, gw)` slots** present are held out, every component is
  refit on the rows strictly before them, those slots are predicted and
  assembled, and the delta is learned from those predictions. The holdout is
  a gameweek-slot boundary rather than a whole season on purpose: some
  component stats exist only in the newest season (`tackles`/`cbi` arrived in
  2025/26), so a season-wise holdout left `DefconModel` with zero eligible
  rows and crashed the refit.
- The inner refit runs the **simple component path** (constant `p_cs` /
  `e_gc`), so the fitted delta absorbs that path's level error as well as the
  components' own. Accepted, gate-A-measured approximation — see
  `fit_calibration`'s docstring.
- Applied as the final step of the EP pipeline in `advise` and the backtest,
  AFTER `assemble_ep`, BEFORE `ep_matrix` (per-fixture, so DGWs still sum).
  `p_haul` stays uncalibrated (it is a probability, not EP).
- Persistence via existing `save_model`/`load_model` (joblib + meta sidecar),
  name `calibration`. If the artifact is missing, EP passes through unchanged
  (identity fallback) — old model directories keep working. A frame with too
  few distinct slots to spare the holdout also returns the identity model.

### 2.2 Set-piece features (`features/engineer.py`, `models/attacking.py`)

*Rewritten to describe what shipped. This section originally specified a
`pens_missed` history proxy; it was removed at gate A — see the GATE A
OUTCOME note in §7.*

- Live: bootstrap fields `penalties_order`, `direct_freekicks_order`,
  `corners_and_indirect_freekicks_order` → features `pen_taker` (1.0 if
  order==1, 0.5 if order==2, 0.0 if order>=3) and `setpiece_taker`
  (the same scoring applied to the better of the two set-piece orders).
  Added to `build_players` and threaded into prediction frames.
- History: **nothing**. Both features are NaN on every historical row. The
  orders are only ever observable on a live bootstrap snapshot, so absence of
  evidence stays NaN rather than being manufactured into a feature; LightGBM
  splits on missing natively and simply ignores the column until snapshots
  accumulate.
- The `pens_missed` proxy the original spec called for was measured and
  dropped: over the real 113k-row history it produced 1770 non-null values
  whose `nunique()` was 1 — a constant-where-present column that could only
  add split noise to the attacking model.
- Forward fix: `refresh_live` snapshots the three bootstrap order fields into
  the live `player_gw` rows, and **accumulates** them — a row for a gameweek
  the parquet already holds keeps the order recorded then, and only rows for a
  new gameweek take today's bootstrap. Retrains therefore learn the real
  feature from a growing record of who was on set pieces *at the time*, not
  from today's assignment stamped backwards over the season.
- Features appended to the attacking models' feature list for MID/FWD and
  GKP_DEF groups alike (defenders take corners too).

### 2.3 Odds ingestion (`src/gaffer/data/odds.py`)

- `OddsClient(api_key)` for The Odds API v4: sport `soccer_epl`, markets `h2h`
  and `totals`, EU region, one GET per advise run, raw JSON snapshotted to
  `data/raw/` like other pulls. Config: `[odds] api_key = "..."` (optional).
- Conversion: de-vig the h2h probabilities (proportional normalization), then
  invert an independent-Poisson model: find (μ_home, μ_away) matching the
  win/draw/win probabilities and the totals line (least-squares over a small
  grid; deterministic, unit-tested against hand-checked cases).
- Output frame: `[team_code, gw, odds_e_goals_for, odds_e_goals_against]`,
  matched to fixtures by team name mapping (explicit alias table, hard error on
  an unmapped team so silent mismatches cannot happen).
- Team model: the two new columns join `TEAM_FEATURES`; training rows (history)
  have them NaN, prediction rows have them populated when a key is configured.
  Missing key / request failure / stale cache → NaN → current Elo-driven
  behavior. Never blocks the advise run.
- AMENDED during implementation (Task 8 review): all-NaN training columns mean
  LightGBM never learns splits on them, making the feature inert as originally
  specified. Fix: odds enter predictions by DIRECT BLENDING at prediction time —
  where odds exist, `p_cs = 0.7·exp(−odds_e_goals_against) + 0.3·model` and
  `e_gc = 0.7·odds_e_goals_against + 0.3·model` (pinned `ODDS_BLEND_WEIGHT =
  0.7`); rows without odds keep pure model output. The odds frame carries
  `opp_code` so double gameweeks merge per-fixture without fan-out, and each
  week's frame is persisted to `live/odds/gw{N}.parquet` so accumulated history
  can later train the model-feature path properly (deferred).
- Budget: ≤ 4 requests per weekly run, free tier 500/month. Cache the pull per
  (date, gw) so re-runs in the same day cost nothing.

## 3. Phase B — rank-aware league mode

### 3.1 Strategy computation (`src/gaffer/league_mode.py`)

- Inputs: league standings (existing `fetch_rival_entries`), my entry total,
  gameweeks remaining `W` (to GW38), per-GW score sigma `SIGMA = 18.0` (pinned
  constant; future: estimate from tracked history).
- Gap `g`: leader_total − my_total if I am not first (chasing, λ ≥ 0), else
  my_total − second_total (defending, λ ≤ 0).
- Pinned formula: `lam = sign × LAMBDA_CAP × clamp(|g| / (2 · SIGMA · sqrt(W)) − 0.5, 0, 1)`
  with `LAMBDA_CAP = 0.5`; sign = +1 chasing, −1 defending. λ = 0 when W = 0 is
  impossible (no advice after GW38); guard W ≥ 1.
- Output dataclass `Strategy(lam, gap, weeks_left, stance, rival_name)` where
  stance ∈ {"chase", "defend", "neutral"} (neutral when λ == 0).

### 3.2 Objective tilt

- Rival effective ownership `eo ∈ [0, ~2]` (existing `effective_ownership`,
  captaincy-weighted, league-only), normalized to `eo1 = min(eo, 1.0)` for the
  tilt (multiplier tail above 1 is captaincy, already handled by captain EO in
  the report).
- Tilted EP entering `build_pool`: `ep_tilt = ep × (1 + lam × (1 − eo1))`.
  Chasing (λ>0): a 0%-owned player gains up to +50% weight, a 100%-owned player
  gains nothing. Defending (λ<0): symmetric penalty on differentials.
- Regression guarantee: λ = 0 ⇒ `ep_tilt == ep` exactly ⇒ v1 solutions
  reproduced bit-for-bit. Property-tested.
- The advice payload and report always show RAW ep; the strategy panel shows λ,
  stance, gap, and tags each recommended transfer "attack" (bought player
  eo1 < 0.3) or "cover" (eo1 ≥ 0.7).

### 3.3 Win-probability panel

- For each rival: `P(I finish above them) = Phi((my_total − their_total) / (SIGMA · sqrt(2 · W)))`
  (normal approximation, independent scores). Shown in the report's league
  section with the standings. Explicitly labeled an approximation.

## 4. Phase C — planner validation + completeness

### 4.1 Backtest v2 (`backtest.py`)

- `run_backtest(..., horizon=1, chips=False)`; CLI flags `--horizon`, `--chips`.
- horizon > 1: solve `gws=[gw..min(gw+horizon−1, 38)]` each week, execute only
  the first GW's moves (receding horizon), predictions for future GWs use the
  same model snapshot.
- chips=True: each week, evaluate available chips via `evaluate_chips` against
  the same thresholds the live tool uses (wildcard: gain ≥ 8.0; others:
  play when gain ≥ 4.0, pinned `CHIP_PLAY_THRESHOLD = 4.0`); play at most one
  chip per week; track the two half-season sets with `chips_available_for`.
  Free hit in-replay: solve the week with `owned` ignored (fresh 15 at current
  prices, budget = squad sell value + bank), squad reverts next week.
- Log gains `chip` column; summary reports {total, per_gw, hits, chips_played}.
- Gate: horizon-6 + chips replay of 2025/26 GW5–38 ≥ v1's 55.94/GW. If not,
  investigate before trusting multi-week advice (explicit stop-and-look gate).
- Runtime budget: ≤ ~45 min accepted for the manual command; default flags
  keep the fast v1 behavior.

### 4.2 Completeness items

1. **GW1 advice**: `run_advise` catches the no-squad `GafferError` from
   `fetch_my_team` and falls back to an initial-squad solve
   (`owned_codes=[]`, `free_transfers=15`, bank 1000), rendering a "build this
   15" report. Chips/league sections degrade (no rival picks at GW0: league
   panel omitted).
2. **Chip-half straddle**: `evaluate_chips` receives per-GW availability —
   `chips_available_for` evaluated for each GW in the horizon, so a horizon
   crossing GW19/20 offers second-half chips for GW20+ rows.
3. **`gaffer live`**: reads `get_event_status` + `get_event_live` + my/rival
   picks for the current GW; prints my live points (provisional bonus from
   current BPS top-3 per fixture), each rival's, and the projected table.
   Read-only, no persistence. Degrades with a clear message outside an active GW.
4. **Rules completeness**: keeper penalty-save EP = p_pen_faced × save-rate
   constant × `penalties_saved` points from the scoring table — implemented as
   a small constant-rate component (pinned: 0.06 expected pens faced/GW,
   30% save rate) rather than a trained model; bonus multiplier read from
   scoring table (currently 1, future-proof); `e_min` removed from component
   frames if still unused after calibration work; drop other confirmed-dead
   code (`get_event_live`/`get_event_status` become used by `gaffer live`).

## 5. Contracts & invariants (unchanged from v1 unless stated)

- Positional assembly for player components; merge only team frames on
  `(team_code, season_idx, gw, opp_code)`.
- Calibration applies per-fixture pre-`ep_matrix`; identity when artifact absent.
- Tilt applies only at pool-construction; raw ep everywhere else.
- Odds features are optional NaN-able columns; no code path may hard-require them.
- All new network I/O follows FPLClient conventions: retries, fail-fast 4xx
  (except 429), raw snapshots, graceful degradation in `run_advise`.

## 6. Testing

- TDD per task. Odds client via httpx MockTransport fixtures. Poisson inversion
  unit-tested against hand-computed cases. λ formula table-tested (gap/weeks →
  expected stance). λ=0 regression test asserts identical MILP solutions.
  Backtest chips logic tested on synthetic small pools. `gaffer live` tested
  with mocked event-live payloads. Existing 96 tests must stay green.

## 7. Milestone gates

- **Gate A** (after Phase A): re-run `scripts/eval_milestone.py` with
  calibration + new features on 2025/26 GW30–38. Must beat v1 on
  mae_starters/captain_pts/top15_pts AND 60+ bias |mean residual| < 0.4.
  Odds features cannot be holdout-tested (no historical odds) — verified by
  smoke test + graceful-degradation tests only; noted honestly at the gate.
- GATE A OUTCOME (2026-08-24, user-approved): calibration redesigned twice
  during the gate (isotonic → additive p60-gated per-position delta fit on
  60-minute appearances; decomposition `E[bias] = P(60+)·E[bias|60+]`).
  Final: mae_starters 2.427 (v1 2.356), captain_pts 5.78 (tie — ranking-movers
  are live-only by design), top15_pts 81.6 (+1.0), bias_60 −0.483 (from −1.11),
  beats both baselines on all five shared metrics. The original criteria set
  mae_starters and bias_60 targets that are in direct tension (removing signed
  bias inflates absolute error); ACCEPTED as the better model for the MILP's
  decisions (XI totals + level truth) with the ranking provably unchanged.
  Also fixed at the gate: latent train_all crash (calibration holdout now the
  last 10 gameweek slots, not the newest season; DefconModel constant fallback
  DEFCON_PRIOR=0.13) and removal of the pens_missed history proxy (constant-
  where-present noise; pen_taker is live-order-only, learns as snapshots
  accumulate).
- **Gate C** (after Phase C): horizon-6 + chips 2025/26 replay ≥ 55.94/GW.

## 8. Rollout

Branch `feat/gaffer-v2`. Subagent-driven execution: Opus implementers, Fable
orchestrates/reviews. Phases A → B → C; user reviews at both gates. Odds key
setup is a user action documented in README when Phase A lands.
