# Gaffer v5 "News" — Design

Approved approach: **A — layered news pipeline behind the existing seam**
(2026-08-26). Research basis: `research/2026-08-25-improvement-research.md`
finding 2 and the "biggest single lever" note (§ next-cycle): the zeros/
blanks stratum is where OpenFPL beats us (zeros RMSE 1.074 vs 0.818, v4a),
and the decomposition attributes it to minutes/news, not xG.

Brainstorm decisions: ingest **all three sources** (premierinjuries.com,
predicted lineups, Transfermarkt injury spells); **hybrid** architecture —
train only on what exists historically, keep news a prediction-time layer;
three-mode model **replaces** the heads and derives them; gate = **N1
benchmark + N2 shadow log**; **shrunken rates in, manager rotation out**.

## 1. Goal

Close the zeros/blanks gap from both ends: a trained three-mode minutes
model {DNP, sub, start} with congestion and shrunken-rate features (the
half that replays historically), and a structured news layer — injuries a
day before the official flag, predicted lineups, per-injury return curves —
applied at prediction time behind the existing `apply_availability` seam
(the half that cannot be replayed, so it ships instrumented). With news
sources down or `[news]` disabled, predictions are byte-identical to the
flags-only path.

## 2. Current state and seams (all kept)

- `models/minutes.py`: `MinutesModel` — three independent LightGBM heads
  (`p_play`, `p60`, `e_min`), incoherence patched by clipping p60 ≤ p_play.
  `apply_availability(pred, avail)` applies official FPL `status` /
  `chance_of_playing` as a prediction-time multiplier with a flat
  `RECOVERY = 0.7` geometric horizon relaxation.
- `advise.py:324` — the one production call site of `apply_availability`;
  the protected predict_components ordering is upstream of it and untouched.
- `features/engineer.py` — `feature_columns()` and the rolling-stat
  builders the mode model's new features join.
- `evaluation.py` — `RETURN_CATEGORIES` (zeros/blanks/tickers/haulers),
  `stratified_metrics`, the OpenFPL benchmark protocol and its stored
  artifact. Gate N1 runs on this, unchanged.
- Backtests never see news (it does not exist historically); the replay
  path stays flags-free, which is exactly the hybrid rule.

## 3. Sources and fetchers (`data/news/`)

New package, one module per source, each returning rows only it
understands, all cached under `data/raw/news/` and all tested through
`httpx.MockTransport` — no network in tests, ever.

- `premierinjuries.py` — scrape the injury/suspension table (player name,
  club, injury type, status, expected return date). Runs at most once per
  `cache_hours` (default 6); cache keyed by fetch date. Name→code mapping
  through the existing `data/names.py` normalizer with the same
  exactly-one-unclaimed-candidate rule the AGS layer uses; unmatched rows
  are dropped and counted, and a per-run match-rate below
  `NEWS_MIN_COVERAGE = 0.5` discards the whole batch (a shape change must
  not half-apply).
- `lineups.py` — one predicted-lineups source: Fantasy Football Scout's
  predicted line-ups page. The module owns the URL and the parse, so
  swapping providers later is a one-module change. Produces `p_start_hint` ∈ {1.0 predicted starter, 0.25 bench
  candidate, 0.0 not in squad} for the *next* fixture only — a lineup
  prediction says nothing beyond GW1 of the horizon.
- `transfermarkt.py` — per-injury-type empirical return-time spells,
  fetched rarely (a calibration input, not a live feed) by a CLI
  (`gaffer calibrate-injuries`) that writes the committed asset
  `src/gaffer/assets/injury_return_curves.json`: for each normalized
  injury type, P(returned by h gameweeks) for h = 0..8, fitted from spell
  distributions with a pooled fallback curve for unseen types. Live code
  reads only the asset; Transfermarkt is never fetched at advise time.

Scraping posture: one polite fetch per source per cache window, honest
User-Agent, and every parse failure degrades (see §7). The scrapers are
the maintenance surface we accepted; each is ~one page and independently
replaceable.

## 4. The normalizer (`data/news/normalize.py`)

`availability_frame(official, injuries, lineups) -> DataFrame` — one row
per player code:

`code, status, chance_of_playing, injury_type, expected_return_gw,
p_start_hint, source, fetched_at`

Precedence, explicit and rule-based (no trained corrector this cycle):

1. Official `status` in {s, u, n} (suspended/unavailable/not in squad) is
   authoritative — news never overrides a ban.
2. For {i, d} and unflagged players, premierinjuries rows sharpen the
   picture: a listed injury with a return date supplies `injury_type` and
   `expected_return_gw` even when the official flag has not caught up
   (that ~1-day head start is the point).
3. `p_start_hint` comes from lineups alone and only ever applies to the
   first gameweek of the horizon.
4. Where sources disagree on availability, the *most pessimistic* current-
   GW multiplier wins (advice that benches a surprise starter costs a few
   points; advice that captains a late scratch costs the week).

## 5. Availability v2 (`models/availability.py`)

`apply_availability` moves to its own module (minutes.py keeps a
re-export so the advise import is untouched) and consumes the normalized
frame:

- Current GW: official multiplier as today, tightened by
  `p_start_hint` for GW1 (`p_play ← min(p_play, hint)` when a hint exists;
  a 1.0 hint never *raises* p_play above the model — lineups gate, they
  don't inflate).
- Horizon decay: the flat `1 − (1 − f)·0.7^h` is replaced by the injury
  curve — `1 − (1 − f)·(1 − P(returned by h | injury_type))` from the
  asset, falling back to the pooled curve, falling back to the old 0.7
  geometric when there is no injury type at all (unflagged knocks,
  suspensions ending). The old constant remains as the terminal fallback,
  so behaviour without the asset is exactly today's.

## 6. Three-mode minutes model (`models/minutes.py`)

`ThreeModeModel` replaces `MinutesModel` (same constructor shape, same
output columns — nothing downstream moves):

- One 3-class LGBMClassifier over {DNP, sub, start}; labels from the FPL
  `starts` column (present throughout `train_seasons`, all ≥ 2022-23):
  start = started, sub = minutes > 0 and not started, DNP = 0 minutes.
- `P(60+ | start)` classifier fit on starters only; `E[min | start]` and
  `E[min | sub]` regressors fit on their modes.
- Derived, coherent by construction: `p_play = p_start + p_sub`;
  `p60 = p_start · P(60+|start)` (subs contribute ~nothing to 60′);
  `e_min = p_start·E[min|start] + p_sub·E[min|sub]`, clipped [0, 90].
  The p60 ≤ p_play clip becomes a no-op and is deleted.
- New features (all historical, engineered in `features/engineer.py`):
  congestion — days since last match and to the next, matches in the last
  14 days, *including cup fixtures* from a new `data/cups.py` ingester
  (FPL-Core-Insights cup fixture files joined to FPL team ids, committed
  to `data/raw/cups/` the way vaastav data is handled); shrunken rates —
  empirical-Bayes per-player start rate and minutes-per-appearance toward
  position×team priors (shrinkage k fitted on the holdout, one scalar).

## 7. Failure and degradation

Every layer is inert when its input is missing, and says so:

- A fetcher that fails (network, parse, coverage below the floor) returns
  an empty frame; the normalizer with all-empty news inputs reproduces the
  official-flags frame exactly; `apply_availability` on that frame is
  byte-identical to today (rail: `tests/test_v5_degradation.py`).
- `[news] enabled = false` skips the fetchers entirely.
- Advise prints one line per degraded source (`news: premierinjuries
  unavailable — official flags only`), mirroring the league/tier-EO
  pattern; advice never blocks on news.
- The asset missing → pooled curve missing → flat 0.7: three-deep
  fallback, each step tested.

## 8. Config

`[news]` (new section; defaults = shipped behaviour ON, individually
switchable): `enabled = true`, `injuries = true`, `lineups = true`,
`cache_hours = 6`, `min_coverage = 0.5`. The Transfermarkt curves are an
asset, not a runtime source, so they carry no flag.

## 9. Gates

**N1 — trained model, historical (orchestrator-run).** The v4a benchmark
protocol re-run with `ThreeModeModel` + congestion + shrunken rates, news
layer off (it cannot exist here). Pass: zeros-stratum RMSE improves by
≥ 0.05 vs the stored pre-v5 benchmark artifact (1.074 → ≤ 1.024), no
other stratum regresses by > 0.02, overall RMSE not worse. A mode model
that loses to the three heads ships nowhere — the old model is kept on a
branch until N1 passes, per the failing-half rule.

**N2 — news layer, forward (instrumented, verdict accrues).** Every
advise run with news active writes a shadow row per pool player:
`gw, code, p_play_news, p_play_flags, e_min_news, e_min_flags, run_at`
to `data/live/news_shadow.parquet` (the news-off predictions are one
extra `apply_availability` call on the flags-only frame — the model runs
once). `gaffer evaluate --news-shadow` scores completed gameweeks: Brier
on played-at-all, MAE on minutes, news vs flags, cumulative. The cycle
records the instrumentation and the first completed-GW smoke in §12; the
season-scale verdict accrues and feeds the future trained-corrector
decision (approach B, explicitly deferred).

## 10. Not in this cycle

Manager-level rotation random effect; trained news corrector (B); any
news influence on the backtest/replay path; historical news backfill;
price-change signals; using lineups beyond GW1 of the horizon; FotMob or
other secondary sources.

## 11. Testing

No network anywhere in tests (MockTransport for all three fetchers and
the cups ingester; fixture HTML/JSON snapshots checked into tests/data).
Unit: name-matching with the coverage floor; normalizer precedence table
(ban beats news, pessimism rule, hint-only-GW1); injury-curve decay chain
(typed → pooled → 0.7); ThreeModeModel coherence (p_play = p_start+p_sub,
derived p60/e_min, degenerate one-mode fits); shrunken-rate shrinkage
toward the prior at low n. Rails: all-sources-empty ⇒ byte-identical
availability output; `[news] enabled=false` ⇒ no fetch calls (spy);
protected predict_components/run_advise orderings untouched. Gates are
orchestrator-run with throwaway drivers as in v4c/v4d.

## 12. Outcome

Shipped 2026-08-26/27. Twelve plan tasks via five Opus implementer groups,
one FIX-FIRST adversarial round (nine fix commits), a FIX-AGAIN
re-verification round (two more), a production-smoke parser rewrite, and a
gate-driven feature withdrawal. Suite 1190 Python + 64 frontend, tsc clean.

### Gate N1 — FAIL on its improvement target; attributed by ablation

Baseline (pre-v5 benchmark, 2024-25 test): zeros 1.073, blanks 1.663,
tickers 1.621, haulers 5.184, overall 1.966. Full v5 first run: zeros
**1.084** — a regression where ≥0.05 improvement was required. The
orchestrator ablation (deterministic pipeline — the control reproduced the
baseline *exactly*):

| arm | zeros | overall |
|---|---|---|
| old heads, old features (control) | 1.073 | 1.966 |
| ThreeModeModel, old features | **1.069** | 1.966 |
| old heads, + congestion/mode-rate features | 1.082 | 1.970 |
| full v5 | 1.084 | 1.970 |

Attribution: the **feature blocks** cause the regression (cup congestion
data exists only from 2025-26 — one training season — so `matches_last_14d`
is partly a season indicator, exactly review finding I1; the benchmark's
2024-25 test period has no cup rows at all). The **model swap is
neutral-to-positive**. Per the failing-half rule the two blocks were
withdrawn from `MINUTES_FEATURES` (`a0f314f`); the builders, tests and the
`gaffer cups` CLI stay, for the tracker and for re-evaluation once cup
coverage spans the training window (natural re-trigger: 2027-28, when two
seasons of archive exist). `ThreeModeModel` ships under the plan's own rule
("ships nowhere if it *loses* to the three heads" — it wins on equal
features). Shipped-config official benchmark (`a0f314f`): zeros **1.069**,
blanks 1.665, tickers 1.633, haulers 5.186, overall 1.966 — strictly
no-worse, mild zeros gain, improvement target honestly missed. The trained
half cannot buy the zeros gap; v4a's decomposition said the gap is
team-news, and this cycle measured that claim from the other side.

### Gate N2 — instrumented and live

First production smoke (GW2, 2026-27): premierinjuries **77/83 matched
(93%), 61 dated returns, 25 percentage statuses**; the advise run banked
**612 shadow rows with 23 players moved by news** — including unflagged
players at p_play 0.55–0.68 whom the press has ruled out with dated
returns (the one-day head start, observed live). `gaffer evaluate
--news-shadow` correctly reports nothing to score until GW2 completes; the
verdict accrues across the season and feeds the deferred trained-corrector
decision (approach B).

The smoke also forced a parser rewrite (`cbfccf4`): the real
premierinjuries table is label-prefixed per cell (`Player X`, `Reason …`,
`Potential Return dd/mm/yyyy` / `No Return Date`, `Status Ruled Out` /
`NN%`) and has **no club column** — the shipped parser is label-driven,
every row matches through the all-clubs uniqueness rule, and percentage
statuses join the pessimism rule as an explicit current-week chance.
Spec §3's table description is superseded by this.

### Review round (FIX-FIRST → fixed → FIX-AGAIN → fixed)

Gating: **B1** the matcher's exact pass could hand a namesake at another
club an injury (uniqueness rule extended + `CLUB_ALIASES` for press
spellings); **B2** a stale past return date flipped a fit player to 50%
and ran an injury curve on him (stale rows now dropped whole). Important:
I4 DGW hint gated both fixtures (now at most one row per code); I5
`expected_return_gw` never reached the decay (now a hard zero-floor before
the return week); I6 shadow MAE averaged DGW minutes (now summed); I7
curve assets validated as CDFs + h=0 clamped to the official factor; I9
exception surface broadened to `httpx.HTTPError` + per-source empty
notices; I8 two unpinned rails pinned. Re-verification caught one NEW
defect in the nit commit (the shadow scorer's season key joined last
season's GW-N to this season's minutes — `evaluate_news_shadow` now cuts
the log to the current season) and the B1 residual (HTML entities never
unescaped — `html.unescape` added to all scrape paths, which also exposed
three stdlib-shadowing `html:` parameters).

### Dormant / deferred (recorded, not fixed)

- **Injury return curves are dormant**: no committed asset. The
  Transfermarkt club-level history page the spec assumed does not exist
  (probe: `/verletztespieler/` 404s; `/sperrenundverletzungen` is current
  injuries without durations); real spell histories are per-player pages
  (~hundreds of requests). The decay chain's terminal fallback (flat 0.7)
  is the tested, shipped behaviour. Follow-up: rework
  `calibrate-injuries` to per-player scraping, or drop the typed-curve
  rung.
- **Predicted line-ups degrade in production**: the FFS page parses zero
  rows (real page shape unverified guess). The source degrades exactly as
  designed — notice printed, advice unaffected. Follow-up: parse the real
  page or swap providers (one-module change by design).
- Cup archive coverage: 2025-26 (120 club-match rows) and 2026-27 only —
  no 2024-25 folders exist upstream, contra the plan's survey.
- The `matches_last_14d` season-indicator hazard (I1) is the recorded
  reason the congestion block is out of the model.
- `SHRINK_K_MODE = 8.0` pinned by convention; the grid run is not
  archived in-repo (same convention as v4b's SHRINK_K).
