# Polish & improvement research — after v11 (2026-09-01)

Two sweeps, synthesized: an external survey (literature since the Aug-25 doc,
competing tools, data sources, the 2026/27 rule changes) and a full codebase
audit (68 findings across correctness, unmined artifacts, model, optimizer,
UI, ops). Everything gaffer already has, and everything the Aug-25 doc
explicitly rejected, is filtered out. Verified in-tree where a claim was
load-bearing.

## The headline

**Single-GW point prediction is at its public ceiling; the remaining edge is
in decisions, data hygiene, and the interface — not in the models.**

- FPL Review's own "ultimate truth" study: even the best model lands at
  RMSE ≈ 2.8 / R² ≈ 0.15 per player-GW. Football is mostly noise at that
  grain.
- OpenFPL (arXiv 2508.09992), free data only, matches FPL Review's paid
  model: bucketed RMSE blanks 1.291 vs 1.189, tickers 1.517 vs 1.594, haulers
  5.142 vs 5.172. Gaffer's v4a stratified buckets already benchmark against
  this table.
- A Serie A pooling study weighting a structural Dixon-Coles model against the
  bookmaker market gives the structural model weight **0.000**. Gaffer already
  blends odds (Shin-devigged, v4b). More team-model work is near-zero ROI.
- Gaffer's own v10 finding says the same thing from the inside: the minutes
  model's value arrived through the *bench/autosub* weighting (+0.38 pts per
  autosub-week), i.e. a decision change, not a prediction change.

So this proposal spends most of its budget on tiers A, B, D and E below, and
keeps tier C (model) to the two or three items that have a measurable,
pre-registered target.

## What the audit found that is simply wrong today (Tier A — fix first)

All verified in-tree on 2026-09-01.

| # | Finding | Where | Why it matters |
|---|---|---|---|
| A1 | **No backup of banked artifacts.** `data/live/*`, `reports/*` ledgers, field-scrape samples are gitignored and irreplaceable — a disk failure erases the season's evidence base. | `.gitignore`, nothing in `scripts/` | Every graded verdict (v9d, v10, N2) depends on these. One `gaffer backup` (tar to a dated dir + optional rsync target) plus a launchd plist. |
| A2 | **`DIFFERENTIAL_EO` defined twice in different units**: `advise.py:461` = `0.3` (fraction) and `optimize/differentials.py:22` = `30.0` (percent). `TEMPLATE_EO` / `ALTERNATIVE_EO` likewise. | two files | Any future caller that imports the wrong one silently compares 0.3 against 30. One canonical constant, one unit. `advise.py` is protected — needs an authorized edit. |
| A3 | **Field EO read without a season filter** at `routers/players.py:149` (`latest_field_eo()`). | web router | Element ids remap every season (standing lesson). The first field scrape of a new season will mix two seasons' ids. Season-guard it like the other element-keyed logs. |
| A4 | **Season rollover is unguarded**: `train_seasons` / `current_season` can disagree with the API's live season with no warning. | `config.py`, `refresh` | Same landmine as A3, one level up. A refresh-time assertion that the API season matches `current_season` (or a loud banner in Health). |
| A5 | **`track_pens` overwrites a good tracker on a fully degraded run.** | `track_pens.py` | A single bad fetch loses the penalty-taker history. Refuse to write when every row degraded (the `calibrate_noise` refusal-bound pattern already in the repo). |
| A6 | **Run `gaffer evaluate --news-shadow`** once GW2 is `data_checked`. | ROADMAP's only open checkbox | Unblocks the `llm_classifier` keep/drop decision (N2). Data-gated, not code. |
| A7 | **`DEFAULT_TOP_N = {GKP 8, DEF 22, MID 26, FWD 14}`** truncates the solver pool undocumented (`optimize/milp.py:132`). | milp | Not wrong, but invisible: a player ranked 27th at MID can never be bought and the UI never says so. Surface it in Health / the solver trace, or make it a config key. |

Not a bug, dropped from the audit list after reading the source:
`CALIBRATED_NOISE_DEFAULT = True` is deliberate — S1 (residual σ) failed, S2
(estimation-only σ) passed under the pre-registered rule, and the docstring
records the escalation. Leave it.

## Data you already collect but never read (Tier B — cheapest new signal)

| # | Artifact | State | What to do with it |
|---|---|---|---|
| B1 | `data/live/availability_log.parquet` | Write-only. `snapshot.load_snapshot_log` has **zero callers**. | The single biggest unmined asset. It is a daily time-series of every player's flag/news/chance — exactly what a "news arrived N days before the flag" feature needs, and what the news-shadow evaluation (A6) should be scored against. First use: a *flag-latency* report (how many days before kickoff does the official flag settle?), then a p_play feature "days since status last changed". |
| B2 | Price log (`prices` nightly) | Banked, used only for the predictor reading. | Price *timing* term for the solver: not chasing rises (rejected), but the sell-price asymmetry — a planned sale next week of a player predicted to fall tonight loses £0.1m of budget. Small, real, and already computable from what is on disk. |
| B3 | Presser-log verdicts | Written by v5 news; never audited against outcomes. | Grade them: for each classifier verdict, did the player start? This is the same shape as A6 and should share the harness. |
| B4 | Field EO samples (Sat/Sun scrape) | Used as a level. | Keep the *trend*: EO at T-3d vs T-0. LiveFPL's EO lags the deadline; a per-player EO delta lets the captain/differential lens forecast deadline EO instead of reading a stale one. |
| B5 | `us_shots90` / `us_npxg90` | On disk from Understat. | xG-per-shot ratio as a feature (shot quality, not finishing skill — the rejected thing was per-player finishing multipliers). One ablation, keep if the hauler bucket moves. |

## New external data worth ingesting (Tier B, continued)

| # | Source | Why this one | Cost |
|---|---|---|---|
| B6 | **FPL-Core-Insights** (github.com/olbauday/FPL-Core-Insights) | CSVs keyed on **FPL element ids** (no name-matching), twice-daily, with CBIT/defcon counts, ClubElo, and cup/European fixtures joined to FPL ids. Solves the congestion problem that the withdrawn cup-archive arm could not (that arm failed on *archive* alignment; this is *forward* fixtures). | Low — a collector in the `understat`/`cups` mould. |
| B7 | Set-piece takers as a **manual YAML** | The set_pieces module infers from history; RotoWire / Fix / Squawka publish the confirmed takers each week. A hand-maintained override file beats any scraper for reliability. | Trivial code; five minutes a week of your time. |
| B8 | FotMob JSON (via a wrapper) | Opta-derived fallback for xG now that FBref is gone. Only if Understat goes down; nothing in-tree reads FBref today (verified), so no cleanup needed. | Defer. |
| — | Referee, weather | Unmeasured in any public study. **Don't build.** | — |
| — | OddsPapi / other aggregators | Pinnacle's public API died July 2025; the current odds provider works. Only if it breaks. | — |

## Model (Tier C — only with a pre-registered target)

| # | Idea | Target | Note |
|---|---|---|---|
| C1 | **News-layer ablation vs the plain FPL flag.** OpenFPL uses *only* the official availability flag and still wins the blanks bucket. Gaffer's v5/v6 news layer has never been ablated against "flag only". | Blanks-bucket RMSE, zeros RMSE (currently the worst cell: starters-zeros 3.559, n=79). | This is the most important experiment in the document. It could retire a whole subsystem or justify it. Runs on B1's log. |
| C2 | **p_play top-bin recalibration.** 0.936 predicted → 0.912 observed, n=1519. | Log score on p_play. | An isotonic step on the top bin; tiny, measurable. |
| C3 | Home/away rolling splits | Stratified buckets. | Cheap feature; not in any prior arm. |
| C4 | Role feature (wing-back vs CB, from CBIT/defcon in B6) | DEF buckets under the 2026/27 defcon points. | Depends on B6. |
| C5 | Fixture density from the *published* list (B6 cups) | Minutes buckets in Euro weeks. | Different framing from the withdrawn congestion arm; say so in the spec so the gate isn't confused with S-congestion. |
| — | Transformer news sentiment (~10% MSE gain, one paper) | — | Single unreplicated result. Skip until C1 says the news layer is worth anything. |
| — | Sarmanov / NB Dixon-Coles | — | Accuracy: no. Variance tails for scenarios: maybe later, after D6. |

## Optimizer & decisions (Tier D — where the edge is)

| # | Idea | Why |
|---|---|---|
| D1 | **Must-sell.** No way to tell the solver "this player leaves this week" (injury you know about, a rule the model hasn't seen). | The most common manual override there is, and today it needs a draft with a hand-built squad. |
| D2 | **Chip combinations + FH re-solve.** WC+BB in a DGW is unrepresentable; Free Hit is scored by approximation rather than a re-solve of the FH week. | The v4c θ machinery gives each chip a reservation value but cannot value a *pair*. Half-2 DGWs are where this pays. |
| D3 | **Retire the flat thresholds.** `WILDCARD_RECOMMEND_THRESHOLD = 8.0` and `CHIP_PLAY_THRESHOLD = 4.0` still live beside θ. | Two answers to one question. θ should be the only one; keep the flat values as a fallback when θ is unavailable, and say so in the UI. |
| D4 | **Top-N distinct plans via no-good cuts.** Instead of one plan plus a frequency table, N structurally different plans (each cut excludes the previous transfer set). | Solio's branching tree does this; it is a two-line addition to the MILP loop and a large UX win on the Planning board. |
| D5 | **Scenario sweep that sees p_play.** The sweep noises EP but not availability, so "what if X is out" is never sampled. | The whole point of the minutes model is availability uncertainty; the sweep is blind to it. |
| D6 | **Rank-distribution simulation from EO.** P(green arrow), P(top-10k) from a correlated sampler over the field's EO. | The v8c mini-league MC already has the correlated machinery for a 10-person league; extend it to the top-10k field using field EO. No public tool does this. |
| D7 | DGW captain / bench chosen on a real two-fixture distribution rather than the disclaimed "ranking" number. | Small, but the current caption admits the number is not a probability. |

## UI / UX (Tier E)

Ordered by how often it would bite you in a normal week.

| # | Idea |
|---|---|
| E1 | **Stale-data stamps on every hub** (currently 4 of 6 lack them). One shared "as of" strip: last refresh, last odds, last field scrape, last advise. |
| E2 | **Tab state in the URL.** Deep links into a hub tab; a reload keeps you where you were. |
| E3 | **Settings tab** for the 48 config keys that matter at the desk (horizon, decay, λ tilt, thresholds, top-N) with the config.toml as the source of truth. |
| E4 | Watchlist list view + render `captain_note` (it is computed and shown nowhere). |
| E5 | **Frozen, timestamped pre-deadline snapshot** of the projection table (Onside's pattern) so the Tuesday review compares against what you actually saw on Friday, not a re-run. |
| E6 | Inline "why this move" traces tied to the ledger row — the solver's shadow prices, θ, and λ contributions per transfer. |
| E7 | `types.ts` (1321 lines) hand-mirrored from `schemas.py` (1624) — generate it. Not visible, but it is the biggest silent drift risk in the front end. |
| E8 | **MCP server** over gaffer's projections and solver, so any Claude session (or this one) can ask "what does gaffer think of X" without the UI. Small (FastAPI already exposes it); high leverage for the way you actually work. |
| E9 | `--lan` exposes an unauthenticated write API. A shared-secret header on the write routes before the next time it is used away from localhost. |
| E10 | Retention: 28 stale replay parquets and 53 logs with no rotation. A `gaffer tidy` with a dry-run. |

## Already have — do not re-propose

Flagged by the external sweep as gaps; all present: sensitivity analysis (v8e),
correlated mini-league MC (v8c), Shin devig (v4b), bank-value term
(`itb_value`), stratified error buckets (v4a), BPS restatement (v4a), official
price-predictor ingest, drafts (12 vs Fix's 5), scenario re-solve frequency
tables (v4c), θ chip thresholds (v4c), FT shadow prices (v4c), λ rank tilt
(v4d), EO lens.

## Still rejected

Price-change chasing; per-player finishing multipliers; big horizon
extension; fabricated EO thresholds; referee/weather; the withdrawn minutes
arms as-is (congestion from the cup archive, tenure_start_share,
manager_tenure_matches, xi_churn_r5, started_last_match, f2_league, f2_cups,
shrunk_start_rate / min_per_app, composite-σ floors, residual-σ scenario
noise).

## Suggested cycles

- **v12 "hygiene"** (small, one sitting): A1–A5, A7, E1, E2, E9, E10.
  Nothing here needs a gate beyond the suite; A2 touches a protected file.
- **v13 "mine what we have"**: B1 (flag-latency report + feature), B3 presser
  audit, B4 EO trend, B2 price-timing term, then **C1 news ablation** as the
  cycle's gate. A6 runs first as data allows.
- **v14 "decide"**: D1, D3, D4, D5, D2 — in that order; D2 last because it is
  the only one whose value depends on the fixture list existing.
- **v15 "field"**: B6 ingest → C4/C5 features → D6 rank-distribution sim →
  D7. This is the cycle that changes what the tool *is*.
- **v16 "interface"**: E3–E8. E8 (MCP) could be pulled forward into v12 if
  you want it sooner; it is nearly free.

Model items C2/C3 ride along wherever a training run is already happening.
