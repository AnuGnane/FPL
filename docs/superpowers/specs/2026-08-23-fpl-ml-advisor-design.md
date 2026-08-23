# FPL ML Advisor ("gaffer") — Design

- **Date:** 2026-08-23
- **Status:** Approved in brainstorming; pending final spec review
- **Season context:** 2026/27, GW1 finished (deadline was Fri 21 Aug). GW2 deadline: **Fri 28 Aug 2026, 17:30 UTC (18:30 UK)**. Per the user's decision, GW2 may pass without tool advice — we build it properly rather than rush.

## 1. Goal & success criteria

Build a machine-learning advisor that helps the user win their FPL mini-league by recommending, each gameweek: transfers (including whether to take -4 hits or bank free transfers), captain and vice-captain, starting XI and bench order, and chip timing — with differential awareness against their actual rivals.

**Success criteria:**

1. A full 2025/26 backtest in which the tool, given only information available at each deadline, produces a season score clearly above the average manager's and competitive with top-10k finishes.
2. Prediction accuracy that beats all three naive benchmarks (FPL's `ep_next`, last-5-match average, previous-season PPG) on held-out gameweeks, measured by RMSE/MAE and by decision metrics (average realized points of the model's captain pick and top-15 squad).
3. The weekly ritual is one command (`gaffer advise`) producing a terminal action list and an HTML report, with an automated Thursday run so a deadline is never missed.

## 2. Scope decisions (from brainstorming)

| Decision | Choice |
|---|---|
| Automation level | **Advisor only.** The tool never logs into FPL or executes transfers. The user applies advice in the official app. (Write endpoints require auth, violate ToS, and FPL login now sits behind SSO with bot protection.) |
| Prediction engine | **Train our own ML model** (position-specific LightGBM, component-based). |
| Timeline | **Build properly; no rushed GW2 advice.** Target a validated v1 in ~2 weeks. |
| Strategy objective | **Maximise expected points, with differential awareness** — flag low-ownership alternatives and rival threats; do not distort the core optimizer toward game-theory play. |
| Interface | **CLI + HTML report.** |
| Extras in scope | Chip strategy advice (including immediate early-wildcard assessment), price-change awareness, mini-league rival tracking, automated weekly run. |

## 3. System overview

Python 3.12 CLI application. Five stages, each independently testable, connected by files on disk:

```
refresh (FPL API + datasets) → features (rolling windows) → predict (E[pts] per player per GW)
                                                                      ↓
       report (CLI + HTML)  ←  advise (transfers/captain/chips)  ←  optimize (MILP)
```

**Stack:** `uv` for environment management; pandas + pyarrow for data; LightGBM + scikit-learn for models; HiGHS (`highspy`) for the MILP; Typer for the CLI; Jinja2 for the HTML report; pytest for tests.

**Repository layout:**

```
FPL/
├── pyproject.toml
├── config.toml                 # user's FPL entry ID, mini-league ID, horizon, decay, risk prefs
├── data/
│   ├── raw/                    # timestamped JSON snapshots of API responses
│   ├── history/                # multi-season training tables (parquet)
│   └── live/                   # current-season tables (parquet)
├── src/gaffer/
│   ├── api/                    # FPL API client: caching, retries, string→number parsing
│   ├── data/                   # ingestion, canonical tables, cross-season ID mapping
│   ├── features/               # rolling-window feature engineering
│   ├── models/                 # minutes model, component points models, training harness
│   ├── optimize/               # multi-period MILP + chip scenario evaluation
│   ├── report/                 # Jinja2 HTML report
│   └── cli.py                  # Typer entry point
├── models/                     # trained model artifacts, versioned by train date
├── reports/                    # generated gameweek reports
├── docs/superpowers/specs/     # this document and successors
└── tests/
```

**Setup inputs required from the user:** their FPL entry (team) ID and mini-league ID, stored in `config.toml`.

## 4. Data layer

### 4.1 Sources (all verified live on 2026-08-23)

1. **Official FPL API** (primary; public, no auth, no observed rate limiting; CDN-cached ~5 min):
   - `bootstrap-static/` — 609 players × 109 fields: form, xG/xA/xGI/xGC (+ per-90), ICT, ownership (`selected_by_percent`), transfer volume, prices, availability (`status`, `chance_of_playing_next_round`, `news`), set-piece orders, and the **new 2026/27 official price-predictor fields** (`price_change_percent`, `price_change_hourly_rate`, `price_change_projections` with per-night likelihoods, `price_change_calibrating`, `price_change_locked_until`). Also `game_config` with the machine-readable scoring table, `events` with deadlines, `teams`.
   - `fixtures/` — 380 fixtures with FDR (`team_h_difficulty` / `team_a_difficulty`) and kickoff times.
   - `element-summary/{id}/` — per-player: this season's per-GW history (includes per-GW xG family and defensive-contribution stats), remaining fixtures, prior-season totals.
   - `entry/{id}/`, `entry/{id}/history/`, `entry/{id}/transfers/`, `entry/{id}/event/{gw}/picks/` — the user's squad, bank, chips used, and full transfer log (purchase prices → correct sell prices).
   - `leagues-classic/{league_id}/standings/` (paginated) — rival entry IDs; rivals' picks via their `picks` endpoints (public once a GW's deadline passes; 404 before).
   - `event/{gw}/live/` and `event-status/` — live points and the data-finalization flag.
2. **vaastav/Fantasy-Premier-League** (historical training data): complete per-GW `merged_gw.csv` for 2016-17→2025-26. We train on **2022-23→2025-26** (the four seasons with per-GW xG). Not used for in-season updates (repo now updates only ~3×/year).
3. **FPL-Core-Insights** (enrichment; auto-updates twice daily, verified pushing today): per-GW player/match stats for 2024-25→2026-27 plus **ClubElo team Elo ratings**, all keyed to official FPL IDs. Our team-strength signal without depending on the flaky ClubElo API directly.

### 4.2 Storage and canonical tables

- Raw API responses archived as timestamped JSON in `data/raw/` (reproducibility and debugging).
- Processed tables as parquet: `players` (canonical, keyed by stable cross-season `code`), `player_gw` (one row per player per GW, training-ready), `teams` (with Elo), `fixtures`, `my_team`, `rivals`.
- No database; parquet + pandas is sufficient at this scale (~600 players × 38 GWs × 5 seasons).

### 4.3 Correctness rules at the boundary

- **ID mapping:** player element IDs reset every season; all cross-season joins use the stable `code` field. Team IDs map via team code. Eleven players were repositioned for 2026/27 — always take `element_type` from the current API, never from historical rows.
- **String-typed numerics:** `form`, `ep_next`, `selected_by_percent`, all `expected_*`, `ict_index`, `price_change_percent` etc. arrive as JSON strings; the API client parses them to numbers once, at ingestion.
- **Finalization gating:** a finished GW's data is ingested for training only after `event-status` reports it checked (new for 26/27: finalization happens ~09:00 UK the morning after the last match).
- **Politeness:** browser-like User-Agent, modest concurrency for the ~600 `element-summary` calls, respect the 5-minute CDN cache.

## 5. Prediction layer

Two-stage: predict *whether and how long each player plays*, then *what they do while on the pitch*. Published comparisons show minutes prediction is the main gap between open and commercial models, so it is a first-class model here.

### 5.1 Minutes model

LightGBM classifier over player × upcoming fixture producing P(start), P(plays 60+), P(cameo), E[minutes]. Features: recent start/minutes patterns and trends, rotation history, availability signals (`status`, `chance_of_playing_next_round`, injury flags parsed from `news` text), days since last match, fixture congestion, new-signing flag.

### 5.2 Component points models

We predict each scoring event separately and combine with the official scoring table from `game_config` (never hard-coded):

| Component | Model | Key features |
|---|---|---|
| Goals, assists | per-position LightGBM | rolling xG/xA/shots over 1/3/5/10/38-match windows, set-piece and penalty order, opponent strength (Elo, rolling xGC), home/away |
| Clean sheet / goals conceded | team-level model | team and opponent Elo, rolling team xG for/against |
| Defensive contribution (+2: DEF ≥10 CBIT; MID/FWD ≥12 CBIRT) | threshold-probability model | rolling tackles/CBI/recoveries per-90 (2025/26+ data only) |
| Saves (GK) | simple model | opponent shot volume, Elo gap |
| Bonus | BPS-proxy model | **refit early this season** — the 26/27 BPS rebalance (tackled penalty removed, CBI 1-per-3, GK save BPS restructured) invalidates old bonus distributions; shrink toward priors until enough 26/27 data accumulates |
| Cards, own goals | small negative priors | rolling card rates |

**Why component-based rather than one direct total-points model:** scoring rules changed across our training window (defensive contributions new in 25/26, GK goal value changed, BPS changed again for 26/27). A direct model learns a scoring system that no longer exists. Component models train each event only on seasons where its stat exists and always assemble totals with the current season's table. They are also interpretable — the report can decompose any prediction.

### 5.3 Outputs

- **Expected-points matrix:** every player × each of the next 6 GWs. Double/blank gameweeks handled naturally by summing per-fixture predictions within a GW.
- **Ceiling estimate:** P(haul) per player per GW from the component distributions — powers risk-aware captaincy and differential flags.

### 5.4 Training & validation protocol

- Time-ordered splits only (train past, validate later GWs). Never shuffled — shuffling leaks the future.
- Training seasons 2022-23→2025-26 with sample weights favouring recent seasons; cross-season rolling windows carry late-25/26 form into early-26/27 predictions; promoted teams handled via Elo plus a promoted flag.
- Benchmarks to beat: `ep_next`, last-5 average, previous-season PPG. Reference points: a good open implementation reaches ≈1.95 MAE on likely starters (near the estimated irreducible floor of ≈1.96) and matched the commercial gold standard on high-return players.
- Report accuracy stratified by realized-points bands (zeros / blanks / mid / hauls), plus decision metrics: realized points of the model's weekly captain pick and of its top-15-by-EP squad.
- **In-season:** automatic retrain after each finalized GW (seconds with LightGBM).

## 6. Decision layer

### 6.1 Multi-period MILP

Solved with HiGHS over a 6-GW horizon (configurable); only week 1 of the plan is acted on, and the tool re-plans each week.

**Objective:** maximize Σ over GWs of `decay^t ×` (starting-XI expected points + captain extra + vice weight + per-slot bench weights) − 4 × hits + a carried-free-transfer option value + a small in-the-bank term. Configurable defaults (conventional values from the community-standard solver, tunable via backtest): decay 0.85; vice weight 0.1; bench weights 0.10 (bench GK) / 0.25 / 0.08 / 0.02 (outfield slots 1-3, reflecting autosub likelihood); carried-FT value ≈1.5 pts; in-the-bank ≈0.05 pts per £1m.

**Constraints (exact 2026/27 rules, read from `game_config`/`game_settings` where exposed):** 15-man squad; budget with **correct per-player sell prices** computed from the user's purchase history (50% sell-on fee on profit); max 3 per club; XI formation bounds (1 GK, 3-5 DEF, 2-5 MID, 1-3 FWD); exactly one captain and one vice; free-transfer dynamics (1/GW, bankable to 5, banked FTs survive chip plays); per-GW transfer cap (20); at most one chip per GW.

### 6.2 Chip evaluation

Scenario solves: re-run the optimizer with each chip forced in each candidate GW (Wildcard, Free Hit, Bench Boost, Triple Captain) and report each chip's expected gain over the no-chip plan. 2026/27 specifics honored: two half-season chip sets; first set expires at the GW19 deadline; WC1/FH1 usable from GW2. The user's immediate question — whether the poor GW1 squad justifies an early wildcard — is the WC-now scenario vs. the transfer-patch plan, quantified, in the first report.

### 6.3 Differentials & rival tracking

After the optimal plan is found (never distorting it):

- Compute **effective ownership within the mini-league** from rivals' public picks (league standings → entry IDs → picks per GW).
- Captain comparison table: EV, P(haul), and rival ownership for the top candidates — safe pick vs. high-ceiling differential.
- Transfer alternatives within ~0.5 xPts of optimal but low rival ownership.
- **Threat board:** high-EO players rivals own and the user doesn't, with the expected-points risk of continuing without them.

### 6.4 Price integration

Use FPL's official price-predictor fields (no scraping, no reverse-engineering): annotate every recommended move with rise/drop projections and timing ("buy before midnight — 90% toward a rise"). A small nightly job polls at ~23:15 UK (changes land at 00:00 UK) and flags urgent action on planned moves. Early-season caveat: some players are `price_change_calibrating` or locked; the report labels these rather than guessing.

## 7. Interface

### 7.1 CLI (Typer)

```
gaffer advise      # full run → terminal action list + HTML report
gaffer refresh     # pull latest data (advise runs this automatically)
gaffer train       # retrain models (automatic after each finalized GW)
gaffer prices      # tonight's price-watch table
gaffer league      # mini-league rival analysis on demand
gaffer backtest    # replay a past season to validate model/optimizer changes
```

### 7.2 HTML report (one file per GW in `reports/`)

Action list with reasoning; xPts table with 6-GW fixture heatmap; captain comparison; differential picks; chip EV table; price alerts; rival threat board; and a **model-health panel** (last GW's predictions vs. reality, rolling accuracy, and a running "tool's plan vs. your actual choices" score).

### 7.3 Automation

macOS `launchd` jobs: (a) Thursday evening full run — refresh → retrain if a GW finalized → advise → report written; (b) nightly ~23:15 UK price check. Both idempotent and safe to re-run; failures leave the previous report in place and log the error.

## 8. Testing & evaluation

1. **Unit tests:** every optimizer output satisfies budget/formation/club/transfer rules; sell-price math against known cases; API-client parsing; and an explicit **leakage test** asserting features for GW *t* are computable from data strictly before GW *t*.
2. **Backtest harness (headline validation):** replay 2025/26 GW by GW — at each deadline, train only on data available then, predict, optimize, and follow the tool's own advice all season (transfers, hits, captains, chips). Score against the real season average, top-10k, and naive strategies. Also used as the regression suite for any future model change.
3. **Live tracking:** log every GW's predictions and advice; surface rolling accuracy and advice-vs-actual in the report.

## 9. Error handling & operational rules

- Retries with exponential backoff; on persistent API failure, fall back to the last raw snapshot and mark the report "stale data".
- Schema-drift detection: validate expected fields on every pull; warn loudly and refuse to advise on malformed data rather than advising on garbage.
- Graceful degradation: if enrichment sources (Core-Insights, Elo) are unavailable, the core pipeline runs on the FPL API alone with degraded features.
- Provisional data (bonus not yet added, `finished_provisional`) is never used for training; live-GW views may display it, labeled.

## 10. 2026/27 rule facts the system must honor

- Chips: WC/FH/BB/TC × two half-season sets; first set expires at GW19 deadline (2 Jan 2027); WC1/FH1 from GW2; no Assistant Manager chip (ignore legacy `mng_*` fields).
- Transfers: 1 FT/GW, bank to 5, −4 per extra, 20-per-GW cap; FTs survive chips.
- Scoring: defensive contribution +2 (DEF 10 CBIT; MID/FWD 12 CBIRT; GK excluded); GK goal = 10; otherwise per `game_config.scoring`.
- BPS rebalanced this season → bonus model must not trust pre-26/27 bonus distributions.
- Prices: change nightly at 00:00 UK, ±0.1 max per night, official predictor fields in the API; sell-on fee 50%.
- GW finalization ~09:00 UK next morning; deadlines vary by weekday — always read `deadline_time` from the API.
- No AFCON free-transfer allowance this season.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| FPL API changes mid-season | Raw snapshot archive + schema validation + the client is the only module touching the API. |
| Understat/FBref unavailable (both degraded in 2026) | Not dependencies: xG comes from the FPL API itself; Elo from Core-Insights. |
| vaastav repo stops entirely | Only needed once, for historical training data already downloadable today. |
| Model confidently wrong early season (small 26/27 sample) | Cross-season features, recency weighting, model-health panel showing live accuracy, human always in the loop. |
| Bonus model drift from BPS rebalance | Shrink to priors, refit weekly on 26/27 data only. |
| Optimizer recommends churn | FT option value and hit cost in the objective; "no move" is always a candidate. |

## 12. Out of scope

- Executing transfers or any authenticated FPL action (advisor only, by decision).
- Head-to-head league logic, draft FPL, Fantasy Challenge.
- Bookmaker-odds ingestion (paid/ToS-encumbered; revisit only if accuracy plateaus).
- Web dashboard (CLI + HTML report chosen; a dashboard could be layered later).
- Rank-simulation game theory (differential *awareness* only, per decision).

## 13. Key references

- OpenFPL — position-specific GBM ensembles, published accuracy vs. FPL Review: arXiv 2508.09992; github.com/daniegr/OpenFPL
- sertalpbilal/FPL-Optimization-Tools — multi-period MILP formulation conventions (decay, FT value, bench weights)
- alan-turing-institute/AIrsenal — Bayesian alternative (considered, not chosen)
- vaastav/Fantasy-Premier-League — historical per-GW data
- olbauday/FPL-Core-Insights — twice-daily current-season data + Elo
- Official endpoints verified 2026-08-23: `bootstrap-static`, `fixtures`, `element-summary`, `entry/*`, `leagues-classic`, `event/*/live`, `event-status`
