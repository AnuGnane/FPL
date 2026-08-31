# Gaffer roadmap & task tracker

One place to see what's shipped and what's left. Grouping comes from
`research/2026-08-25-improvement-research.md`. Update this file as cycles
progress: flip `[ ]` → `[x]`, link the spec/plan when they exist.
Measurement rules every cycle follows: `CONVENTIONS.md`.

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

### v4d — compete (done, league mode v2)
Spec: `specs/2026-08-26-gaffer-v4d-compete-design.md` (§12 = full outcome) · Plan: `plans/2026-08-26-gaffer-v4d-compete.md`
- [x] z-dial with tanh λ map + z_deadband 0.25 (review amendment), σ from league history with fallback chain [8, 30]
- [x] Observed-squad covering: threat-softmax weights → cover table → anchored tilt_ep v2 (normalized so chase can't discount hit_cost/ft_value/itb)
- [x] EO-aware captaincy with 0.15-xPts override margin; "last armband" notes in CLI/report
- [x] Tier-resolved live EO (300-sample top-10k, honest SE, graceful degradation)
- [x] Gate E1 PASS (adapted to shadow-rival replay — API rollover destroyed 2025-26 rival data): wins 3–3, gap-0 cost 0, −10 deficit converted +7; confounded pre-fix run recorded
- [x] Final adversarial review: FIX-FIRST, 4 blockers + 4 important fixed (whatif percent/fraction mismatch the sharpest), re-verified
- Suite: 1034 Python + 64 frontend, tsc clean

### v5 — news (done, minutes/news ingestion)
Spec: `specs/2026-08-26-gaffer-v5-news-design.md` (§12 = full outcome) · Plan: `plans/2026-08-26-gaffer-v5-news.md`
- [x] `data/news/` package: premierinjuries (label-driven parse of the real table, 77/83 matched, 61 dated returns live) + FFS lineups (degrading — real page shape pending) + precedence normalizer with percent statuses
- [x] Availability v2: per-injury-type horizon decay with return-gw zero-floor (curves DORMANT — Transfermarkt club-history page doesn't exist; flat 0.7 is the shipped, tested fallback)
- [x] ThreeModeModel {DNP, sub, start} replaces the heads (ablation: neutral-to-positive, ships); congestion + shrunken-mode features BUILT but withdrawn from the model per gate N1
- [x] Gate N1 FAIL on its ≥0.05 target, fully attributed by 3-arm ablation (features regress zeros — one-season cup coverage = season indicator; model swap wins); shipped config zeros 1.069 vs 1.073 baseline, nothing worse
- [x] Gate N2 instrumented + live smoke: 612 shadow rows, 23 players moved by news (unflagged players zeroed a day ahead of the flag); verdict accrues via `gaffer evaluate --news-shadow`
- [x] Final adversarial review: 2 blockers + 7 importants fixed; re-verify caught 1 new defect + 1 residual, both fixed
- Suite: 1190 Python + 64 frontend, tsc clean

### v5.1 — news completion (done, merged `388da4a` 2026-08-26)
Spec: `specs/2026-08-26-gaffer-v5.1-news-completion-design.md` (§5 = outcome)
- [x] FFS predicted-lineups parser on the real page (photo-code join, Scout Picks widget guard; 277 hints live)
- [x] Transfermarkt per-player calibration: 3381 spells, 504 players, 16 typed curves committed — typed decay live

### v6 — cockpit (done, pen EP + noise gate + decision-cockpit UI)
Spec: `specs/2026-08-27-gaffer-v6-cockpit-design.md` (§9 = full outcome) · Plan: `plans/2026-08-27-gaffer-v6-cockpit.md`
- [x] Penalty-taker EP: event-based share_hist (172 events, takers ≈0.83), constant 0.13 league rate + drift notice, (1−w) AGS delivery — Gate P1 audit PASS (max +0.61 new taker, incumbents ≈+0.1)
- [x] Calibrated scenario noise: fitted asset (13 cells, σ 1.953, Newton mean-preserving clip) — Gate S1 FAIL (heuristic 1785 vs calibrated 1761, −24 on ±5): residual σ conflates forecast error with irreducible variance; heuristic stays default, opt-in path parked for an estimation-only σ
- [x] Cockpit UI: chip workbench (threshold bars, wildcard diff, What-If re-solve), why-this-plan panel (EP breakdown + pen annotation + run diff), news transparency panel (per-source evidence), N2 scoreboard on Quality
- [x] Adversarial review FIX-FIRST (3 blockers) + re-verify FIX-AGAIN (3) — all fixed, third pass clean via gates
- Suite: 1338 Python + 88 frontend, tsc + build clean

### v7-ui — command centre (done, full UI redesign)
Spec: `specs/2026-08-29-gaffer-v7-ui-design.md` (§12–13 = smoke + outcome) · Plans: `plans/2026-08-29-gaffer-v7-ui.md`, `plans/2026-08-30-gaffer-v7-ui-polish.md`
- [x] Foundation: Tailwind v4 (locked dark design language as tested `@theme` tokens), Radix primitives, Recharts; 13-component kit incl. position-identity `PosBadge`
- [x] Job runner: single-flight streaming `JobRunner` (SSE + ring-buffer replay + heartbeat, thread-routed stdout) running advise/evaluate/refresh-data/news-shadow from the browser; legacy rerun endpoints deleted (single lane)
- [x] Six hubs replace 13 pages: This Week / Planning / Players / League / Live / Model; `frontend/src/pages/` deleted
- [x] New capabilities: 3-GW plan timeline, player compare, Dixon-Coles fixture matrix (winsorised 0–1 scale), decision journal with deadline guard + `late run` badge
- [x] Fully responsive (card-mode tables, bottom tab bar) + `gaffer ui --lan` with QR; cold-clone sweep suite (found + fixed config 500s)
- [x] Adversarial review FIX-FIRST (2 blockers + 11 importants + 9 nits) → re-verify MERGE → 9 residuals closed → editorial polish round from user walkthrough (position colours, 6 legacy components restyled onto the kit, 20-fix sweep)
- Suite: 1464 Python + 245 frontend, tsc + build + `uv lock --locked` clean; backend model code untouched

## In progress

### v8 queue (approved 2026-08-30, all seven cycles green-lit)
Proposal: `specs/2026-08-30-gaffer-v8-research-proposal.md`. Order fixed by dependency + data accrual;
user decisions recorded: LLM presser classifier runs via headless `claude -p` (user's Claude
subscription — no API key/spend, pluggable + degradable); v8f alerts approved; v8c top-10k
entry-API scrape approved.
- [x] v8a minutes intelligence — done 2026-08-31, spec §9 = outcome. G1 withdrew ALL six feature arms (zeros regressed on every one — the gap is news-shaped/serve-time, not historical-features); shipped instead: notable-absence damp (≥11 resolved starters, unflagged players only), `claude -p` presser classifier (no-tools pinned, chunked, shadow-first, serving OFF), P(start) eval metrics, manager-tenure asset (89 spells). Review blocker: mixed-dtype sort made serve-time priors one match stale + G5 taught that replay baselines must be re-banked after serving-default flips (banked 1876 was pre-Z1; branch ≡ main at 1844).
- [x] v8c field intelligence — done 2026-08-31, spec §8 = outcome. Field scrape live (300 top-10k squads banked GW2, weekend launchd job), correlated mini-league MC (shared weekly factor, measured corr 0.590/0.675; P(win) 36% ± 1.7, exp finish 5.6/50), what-if router, sword/shield EO. G2 caught 4 live-data defects + review caught 3 probability-layer blockers (BB snapshots, estimation-σ misuse, independence overclaim).
- [x] v8b decision loop — done 2026-08-31, spec §7 = outcome. Four graded lanes (transfers/captaincy/bench/chip) vs deadline-guarded advice, in pts + Δwin% (paired-seed league sim); reconciliation gate EXACT on GW1 real data; decision ledger + hindsight XI + season summary; Review tab (5th Model tab), 9th job kind, Tuesday launchd. Review blocker: pricing rebuilt a different counterfactual than grading — lanes now built once and priced identically. First fully-graded row lands when GW2 data_checked flips — eyeball it.
- [x] v8d live matchday — done 2026-08-31, spec §4 = outcome. Auto-sub projection (formation-legal walk, vice inheritance, blank/DGW-aware), live EP race chart w/ pinned rival + pre-GW reference, league safety strip, autosub-aware projected column. (Live bonus already existed since v6.) G1 live arithmetic exact; review: blank-GW + DGW-EP biases fixed, brute-force autosub equivalence 0 divergences.
- [x] v8e solver trust — done 2026-08-31, spec §4 = outcome. Editable availability pins (authoritative last pass, DGW-whole-first-GW, model reading banked), 20-solve sensitivity sweep (signed margin, seed-independent of the advice draws; first live result: modal plan 5/20 — coin-flip board), drafts CRUD+compare (min-horizon scoring), chip sanity rails. Review: both blockers were wrong sentences to the manager (backwards negative margin; FH draft mis-scoring); chip-frequency claim dropped as structurally impossible rather than faked.
- [x] v8g honest uncertainty — done 2026-08-31, spec §4 = outcome. Calibration cards (reliability curves incl. P(start), ledger-sourced scatter, biggest misses), outcome-variance EP bands + haul/blank chips (review caught the estimation-σ trap AGAIN — dead 0% chips/blank-100% certainty; now quadrature with OUTCOME_VAR_PER_EP, one uncertainty answer across tabs), counts-not-percentages confidence, compare radar. The cycle named for honesty needed its review most.
- [x] v8f daily companion — done 2026-08-31, spec §4 = outcome. Price log banked daily (626 rows, idempotent per UTC day), starred watchlist cloning the pin pattern, Friday briefing + Tuesday debrief as pure-reader artifacts with an osascript notification (both built on real GW1 data), real EP movers in the retrain diff (absent on the first run, 5 named on the second). Review FIX-FIRST with no blockers; the sharpest of the four was a NaT deadline parsed under a guard and then multiplied outside it. The queue closes — user must re-run `scripts/install_automation.sh` for the four new plists.

### v7d — cockpit polish (done, 2026-08-30)
Spec: `specs/2026-08-30-gaffer-v7d-cockpit-polish-design.md` (§9 = outcome + evidence) · Plan: `plans/2026-08-30-gaffer-v7d-cockpit-polish.md`
- [x] Fast advise: `gaffer advise --fast` + `advise-fast` job kind + This Week button — 78s vs ~6 min swept (rides the pinned `scenarios_n=0` rail; v7b proved the gate is a no-op under option (b))
- [x] Pen tracker card in Model hub (`GET /api/pens`, `track-pens` job kind + button); snapshot button; player names are the explain control in Compare + the explorer (`Card` heading slot)
- [x] Light theme: three-state toggle (system/dark/light), `[data-theme]` token overrides, boot script, WCAG-checked palette; review blocker = Tailwind v4 bakes opacity-modifier utilities to dark hex in the compiled CSS → soft tokens + a mutation-tested built-CSS guard (and: Tailwind's scanner reads comments — naming a class in prose regenerates it)
- [x] Z1 flip shipped separately (`826ff6b`): `DNP_CALIBRATION_DEFAULT = True` by user decision — takes effect at the next `gaffer train`
- Suite: 1636 Python + 302 frontend (+1 skip), tsc clean; protected files zero diffs

### v7c — foundations (done, 2026-08-30)
Spec: `specs/2026-08-30-gaffer-v7c-foundations-design.md` (§8 = outcome + evidence) · Plan: `plans/2026-08-30-gaffer-v7c-foundations.md`
- [x] F1 daily availability snapshot: `gaffer snapshot` → append-only `data/live/availability_log.parquet` (idempotent per UTC day, atomic rewrite, never raises); web job kind; launchd plist shipped — **run `scripts/install_automation.sh` to activate the 17:00 daily job**
- [x] F2 multi-seed standard: `v7b_replay.py --seed-bases a,b,c` + `MULTISEED_DONE` aggregate; `seed_stats.py` with config-mismatch guard (refused the q2-ctrl mix on first use — its 1786 is a chips-off control, not the S2 heur 1785); `CONVENTIONS.md` (8 rules) linked above
- [x] F3 pen-term tracker: `gaffer track-pens` → `reports/pen_tracker.json`; GW1: 2 pens, both by predicted first-choice takers (hit 1.00), 0.100/team-game vs served 0.13, instrument xg_gap (covered_rows 256)
- [x] Review: 1 blocker (confounded seed-spread evidence) + 4 importants (team_games retro-stamp bias, per-week Understat coverage, atomic log rewrite, gated-arm loop tests) — all fixed; residuals in spec §8
- Suite: 1619 Python + 251 frontend; protected files zero diffs; no frontend change

### v7b — measurement cycle (done, merged `8aeb3d6` 2026-08-30)
Spec: `specs/2026-08-30-gaffer-v7b-measurement-design.md` (§5–7 = results, corrections, evidence appendix)
- [x] Q2: D1 sign reversal attributed (single-seed) to the v5 minutes-head swap (+27 legacy vs −61 current, same harness); harness and frame ruled out; the swap itself still justified (+47 ungated)
- [x] Q1: 3-seed error bars — spread 116 swamps every arm gap; the S1/S2 ±120s were draw luck
- [x] Q3: composite-σ floors monotonically worse; no re-noised gate beats raw
- [x] Mechanical verdict: KEEP option (b) — all differences within seed noise; raw anchor 1914 reproduced and logged
- [ ] N2 first news verdict — still pending GW2 `data_checked`
- 12 replay runs + 1 probe; suite 1548; no serving changes

### v7-model — zeros + honest noise (done, merged `1b93b9d` 2026-08-30; user chose option (b))
Spec: `specs/2026-08-30-gaffer-v7-model-design.md` (§9 = gates + the three-way decision) · Plan: `plans/2026-08-30-gaffer-v7-model.md`
- [x] Zeros diagnostic: the error is regulars-who-sit (news-shaped), not fringe; I2 fringe features proven underivable from stored data
- [x] Gate Z1 FAIL — isotonic DNP recalibration ships OFF (zeros 1.063→1.053, bar was 1.042; strict Pareto improvement, user may flip)
- [x] Gate S2 PASS on the literal rule — estimation σ (K=5 bagged ensemble, global 0.069) replay 1908 vs heuristic 1785; **review's raw control scored 1914: the σ disables gating rather than sharpening it** → three-way decision (heuristic / estimation / no gating) escalated, merge withheld
- [x] Open finding: v4c D1 sign reversal — scenario gating was +75 in v4c, −129 on today's model; unbisected
- [ ] N2 first news verdict — pending GW2 `data_checked` (`gaffer evaluate --news-shadow`)
- Suite on branch: 1523 Python + 251 frontend, tsc clean; serving guards added (non-estimation asset refused when flag True; calibrate-noise refuses unsafe overwrite)

## Planned

### v9a — pitch view (spec written 2026-08-31, awaiting implementation)
Spec: `specs/2026-08-31-gaffer-v9a-pitch-view-design.md` — FPL-style XI + bench strip as the This Week default: formation rows, C/V armbands, shirt kits + team short-names via cached backend asset endpoints (URL patterns verified live), difficulty-tinted next-fixture chips off the odds-implied ticker. Photos cached this cycle, rendered in v9b.

### v9b — UI polish (backlog in v9a spec §0 D5)
PlayerCard identity across Live/League/Review · skeleton states for job-triggered panels · mobile pass on the v8 cards · action toasts (star/pin/override) · empty-state copy audit · chart-token unification · light-theme audit of v8 cards · difficulty tinting on Planning's horizon table.

### v9c — model debt (from the 2026-08-31 cross-cutting review; evidence-first, each needs its own gate)
- `rc_r38` is identically zero: `card_penalty`'s red-card term reads a rolling stat `engineer.py` never builds (`ROLL_STATS` has `yc`, not `rc`) — needs the feature added + an arm run, not a hotfix
- `team_code` retro-stamp leak: `data/live.py:169` stamps today's club over all history rows; three feature builders key on it (`_shrunk_ratio` club prior, manager-spell scoping, team Elo merge) — January transfers silently rewrite training rows; fix needs an as-of club column + replay evidence
- Two quantities named `p_haul` (attacking-returns Poisson in `assemble.py` vs total-points band in `uncertainty.py`) served on the same page — rename one end-to-end
- Job timeout/cancel: `ADVISE_TIMEOUT_S` has zero readers; one wedged job 409s every later job until restart — `web/jobs.py` is protected, so this is a deliberate orchestrator-authorized cycle
- SSE stream pins a threadpool worker per watched run for up to an hour (`routers/jobs.py:116-153`) — revisit alongside the timeout work

## Operational / housekeeping
- [x] Untrack `reports/` artifacts + `.claude/`; gitignore both (`31dc239`)
- [x] Set odds API key in `config.toml` `[odds]` (done 2026-08-25; G3 live spot-check recorded in v4b spec §13)

## Explicitly rejected (don't re-add)
- Price-change chasing · per-player finishing multipliers · big horizon extension · fabricated "EO thresholds"
