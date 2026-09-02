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
- [x] DGW/BGW `chip_scenarios.toml` population — hook shipped here, populated in v10b from the *published* fixture list (scheduled doubles at p=1.0); the Crellin-style projections for *unannounced* rearrangements are still not a thing this tool does
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

### v9a — pitch view (done, merged `02cf26e` 2026-08-31)
Spec: `specs/2026-08-31-gaffer-v9a-pitch-view-design.md` (§4 outcome) · Plan: `plans/2026-08-31-gaffer-v9a-pitch-view.md`
- [x] FPL-style pitch as the This Week default: formation rows + bench strip, C/V armbands, shirt kits, difficulty-tinted next-fixture chips (odds-implied ticker), Table one toggle away
- [x] Asset cache `/api/assets/{shirt,photo}/{code}`: bootstrap allowlist, bundled SVG fallbacks, magic-byte poisoning guard, nosniff, no redirects, 2MB cap; photos banked for v9b
- [x] Serve-time identity in unprotected `web/identity.py` — banked advice artifacts byte-untouched (railed); every existing advice file gains the fields without a re-solve
- [x] Review FIX-FIRST → fixed: null-team plain-shirt fallback (was a blank gap), HTML-200 cache-poisoning guard; deferred: identity memoisation, weeks=2 tint window (recorded)
- Suite: 2746 Python + 498 frontend; protected diffs zero

### v9b — UI polish (done, merged `b8a289e` 2026-08-31)
Spec: `specs/2026-08-31-gaffer-v9b-ui-polish-design.md` · Plan: `plans/2026-08-31-gaffer-v9b-ui-polish.md`
- [x] Identity chips (PlayerCard horizontal variant) on Live, rival squads, review misses; portrait in ExplainModal from the v9a photo cache; review lanes stay text (codes discarded server-side — pinned so nobody fabricates the link)
- [x] kit/Skeleton + kit/Toast (aria-live outlet; star failure-only, pin/override/draft both halves); skeletons on all four job panels via JobButton.onRunning
- [x] Timeline difficulty chips (client-side join, absent-not-wrong on every missing link); empty-state audit; 390px pass — zero bare tables tree-wide (railed)
- [x] Review FIX-FIRST → fixed: per-code star revert (whole-array snapshot wiped concurrent stars), toast timer/id hygiene (recycled ids dismissed later toasts), the thirteen unwrapped tables
- Suite: 2746 Python (zero .py in diff, railed) + 553 frontend; chart-token + light-theme audit closed as already-clean (recorded, not padded)

### v9c — model debt (done, merged `41980e4` 2026-09-01)
Spec: `specs/2026-08-31-gaffer-v9c-model-debt-design.md` (§4 = arm numbers, club-leak measurement, replay verdict) · Plan: `plans/2026-08-31-gaffer-v9c-model-debt.md`
- [x] Red cards priced for the first time: `rc` in ROLL_STATS + shrunk rate (`SHRINK_K_CARD=20`) — arm run three times (two invalid runs recorded, not overwritten; the disconnected-lever lesson) → ship at −0.001/+0.001/0.000 vs 0.005
- [x] `team_code` retro-stamp leak closed for three consumers via as-of `club_code` (fixture join, 100% match rate, 0.94% of rows diverged — Ward-Prowse demo); understat own-side + congestion deliberately unswitched → **v9d residual**
- [x] `p_attacking_haul` split from the band's `p_haul` at the serving boundary (third decoration); labels railed
- [x] Job timeout/cancel via SIX orchestrator-authorized protected edits (jobs.py + routers/jobs.py + advise.py atomic write + B1 stdout guard) — live-verified: mid-run cancel 200, lane freed, replacement's log intact
- [x] Replay gate PASSES: branch 1857.3 (spread 25) vs re-run main 1874.3 (spread 107), paired deltas +27/−86/+8 — within seed noise
- Residuals: v9d two unswitched club consumers; SSE worker-pinning; cancel message reuses timeout wording; job-timeout name covers all 12 kinds
- Suite: 2825 Python + 554 frontend; the v9 queue closes

### v9d — debt close + calibration monitoring (done, merged `728236d` 2026-09-01)
Spec: `specs/2026-09-01-gaffer-v9d-design.md` (§5 = G1/G2 numbers) · Plan: `plans/2026-09-01-gaffer-v9d.md`
- [x] Club leak fully closed: Understat own-side + congestion cup lookup on `as_of_club` — G1: 0.92% rows changed with match rate **up** 98.79%→99.28%, congestion 0.10%; G2 replay identical arms, explained (no head claims the switched columns — hygiene ahead of any future claim)
- [x] Calibration monitoring: `gaffer evaluate --calibration` → per-GW + cumulative Brier/reliability for p_play/p60/p_cs/p_haul at fixture grain, as-of guarded by *first* kickoff; `GET /api/model/calibration` + Model-hub card; p_cs cumulative-only (20 clubs < 30 floor)
- [x] Per-kind abandon timeouts (fast kinds 120s) + a cancel that says "cancelled" — two authorized `web/jobs.py` line-groups; single-process contract documented + railed
- [x] Identity memo (mtime-keyed, locked, bounded) — four parquet loads/request → cached
- [x] Review FIX-FIRST (3 blockers: arbitrary-player clean sheets, DGW fan-out, permissive as-of) → re-verify caught 2 more (racy eviction — reproduced; join key one column short) → all fixed; G1 instrument itself needed two fixes before first valid run
- Residuals: SSE worker-pinning documented-not-rearchitected; per-head n divergence documented; N-1 cancel-sentinel channel (declined — protected)
- Suite: 2912 Python + 562 frontend

### v10 — minutes intelligence II (done, merged `b0cdc4e` 2026-09-02)
Spec: `specs/2026-09-01-gaffer-v10-minutes-design.md` (§Gates = G1/G2/G3 numbers, §Residuals) · Plan: `plans/2026-09-01-gaffer-v10.md`
- [x] The minutes model reaches the optimizer's own weights for the first time: bench slots, the reserve keeper and the vice priced by frailty in a two-pass solve, XI and captain pinned between passes so the hedge is priced against the man actually wearing the armband — **G3 +0.381 pts/week over the 21 autosub weeks**, and the reshaping is bench-only, which is the intended shape
- [x] `KEEPER_DNP` — the keeper's own denominator, fixed at G5 rather than left as a residual
- [x] Predicted-XI provider seam: the Fantasy Football Scout fetch becomes provider `ffs` with no behaviour change, RotoWire joins as `rotowire`, merged on the pessimism rule the module already applied within one source
- [x] F3a arm **withdrawn** on its pre-registered bar (+1.09% LL, −0.007 zeros) — measured, recorded, not shipped
- [x] `p_play` truth-table wiring documented and railed; the guard is a single short-circuit, so an absent *or uniform* `p_play` reproduces today's solve to the byte
- [x] G2 replay: identical arms, and predicted to be — `backtest.py` passes no `p_play`, so the replay cannot see §F1 at all and was demoted to a no-regression check before it ran; G3 is the gate that judged the feature
- Residuals: §F1's transfer-side reach waits for a sweep that can see `p_play`; a run whose scenario solves all fail serves an unweighted plan; what-if baselines are single-pass because `SolveState` is JSON and cannot carry a per-player dict (*v11*); `coherent_plan` appends a promoted captain to the bench after §F1b has ordered it; `captaincy_override` discards the frailty-weighted vice under league tilt
- Suite: 3047 Python + 562 frontend

### v10b — EO framing + season chip planner (done, merged `be87be9` 2026-09-02)
Spec: `specs/2026-09-01-gaffer-v10b-eo-chips-design.md` (§Gates = G1/G2) · Plan: `plans/2026-09-02-gaffer-v10b.md`
- [x] §F1 EO framing: top-10k EO beside league EO on the squad rows, a served captain sentence carrying the ±SE and the cover/attack reading, `most_captained` ingested as the fallback for the weeks the tier sample cannot cover, and an EO lens on the pitch (off by default)
- [x] §F2 season chip planner: the DGW/BGW detector this tree has never had, `GET /api/fixtures/outlook`, `data/chip_scenarios.toml` derived from the *published* fixture list inside `refresh-data`, and a Chips-tab Outlook segment carrying θ per week and the GW19 first-set expiry
- [x] `/api/chips/plan` carries θ at all for the first time: the router passed no thresholds and `ChipPlanRow` declared none, so it was computed and dropped — v9d's `odds_blend_weight` failure, repeated
- [x] No replay — nothing on the training or decision path moves, and on today's fixture list the scenario writer writes nothing, so both arms would be the same arm (recorded, not skipped)
- Pins: job kinds 12, config fields 48, routes 44 → 45 (two protected route-count pins moved under orchestrator authorization — the toll an absolute pin charges; **paid in v11**, which retired every absolute pin but one)
- [x] G2: adversarial review, fix-first, merge ritual
- Suite: 3130 Python + 591 frontend (G1)

### v11 — the UI trio (done, merged `57ef6c8` 2026-09-02)
Spec: `specs/2026-09-02-gaffer-v11-ui-design.md` (§Gates = G1/G2) · Plan: `plans/2026-09-02-gaffer-v11.md`
- [x] §F1 planner board: the solved horizon week by week — buys and sells with prices, hits and their cost, chip, and a bank trajectory the artifact never carried, derived at the router and blanked permanently by the first unpriced move; price warnings from `/api/prices/movers`, a finished endpoint the frontend had never once fetched; a prefill-and-switch handoff into the What-If lab that costs Planning's tabs their `defaultValue`
- [x] §F2 comparison deepen: most of it was already on the wire — `ComparePanel` already fetched the components and the fixture matrix — so the cycle's whole server-side contribution here is the field EO's **standard error**, which `routers/players.py` has looked up and dropped for two cycles
- [x] §F3 season dashboard: `season_summary` was already served, so no new endpoint; per-lane **win rates** added where the graded-counter rule lives rather than in the client, and `overall_rank` banked for the first time — a number that appeared nowhere in the tree
- [x] Route-pin restructure (spec §0): four files pinned the absolute path count, three of them protected; each becomes the by-name claim its own cycle is entitled to make, and the total lives in `test_v11_degradation.py` alone. Done in a cycle that adds no route, so every assertion keeps its verdict across the diff
- [x] No replay — the server-side diff is seven additive fields and the arithmetic that fills them; no solver call from any view
- Pins: job kinds 12, config fields 48, routes 45 → **45**
- Residuals: the bank trajectory re-does arithmetic the solver already did, because widening `plan_by_gw` means editing `advise.py`; `overall_rank` stays null on every already-banked row, because grades are banked and never re-derived; the explain payload (`routers/players.py`) still floors `p60` at 0.0 where the components payload now serves null — `_cell_or` reads every number on that model the same way and moving one alone is a change to a shipped view no rail asked for; recharts draws a one-point series as nothing at all, so the season charts are blank rather than a dot for a season one gameweek old (the honest empty states carry the meaning, and `dot` is a per-series decision the next cycle can revisit)
- [x] G2 fix round: `p60` inherits `p_play`'s absent-not-zero convention; a double's xMins total blanks on any null leg; the What-If handoff prefills a horizon that reaches the week it carries and says the solve still starts now; the calibration-trend assertions wait on the trend's own fetch; the bench empty state counts totals rather than gameweeks; the terms-vs-`ep` caption compares like with like at a per-term tolerance; the chart series are keyed by code, not by name; a move too broken to parse blanks the bank the way an unpriced one does; each new view carries its own 390px test
- [x] G2: adversarial review (2 blockers, 6 importants) → fix round → re-verify (caught the I5 fix comparing two equal-by-construction numbers) → micro-round → merged `57ef6c8`, ritual clean. Suite 3193 + 655
- Suite: 3193 Python + 655 frontend (G1, after the fix round)

### v12 W1 — hygiene (in progress, branch `feat/gaffer-v12`)
Spec: `specs/2026-09-01-gaffer-v12-program-design.md` (§1, §2 = the W1 gate) · Plan: `plans/2026-09-01-gaffer-v12-w1-hygiene.md`
- [ ] §2.11 one atomic write: the spec said six copies of the temp-then-rename idiom and there were **twenty**, in three families — so the helper serves text, parquet-through-`store` and raw bytes, and nineteen of the twenty migrated. Two latent bugs fixed by construction: `presser_log` had no pid in its temp name, `understat` and `chip_scenarios` had no `finally`
- [ ] §2.2 one set of EO constants: `differentials.py` held two of the three the spec said it exported and none of them in fractions; `TEMPLATE_EO` moved there rather than being found there, and this module's own two readers convert at the comparison because `league_eo` is a percent that gets served
- [ ] §2.3 season-guarded field EO: the keyword has existed since v10b and was optional, and `routers/players.py` forgot it — recorded as a residual twice, closed here, at the cost of two protected pins that asserted the bare call
- [ ] §2.4 rollover guard: `refresh` refuses on a mismatch and names both values and both keys; `/api/health` answers from the **banked** events snapshot, because that router is disk-only by contract, and `season_ok` is three-state so a cold clone is not an alarm
- [ ] §2.5 `track_pens` refusal, on both shapes of degraded run — all gameweeks broken, and no gameweeks at all — and never when there is nothing banked to protect
- [ ] §2.6 `top_n` in config — in the existing `[optimizer]`, not the spec's new `[solver]` (orchestrator ruling, so **W2 §3.4 and W5 §6.2 follow**), which makes it a *splatted* key: the field is named for the TOML key and the forgiving merge-over-default lives in the reader `build_pool` calls, because the splat validates nothing. Surfaced on Health with the caption that is the point of surfacing it, and the card clears the reader's cache so a config edit shows without a restart
- [ ] §2.1 `gaffer backup` + the eighth plist: **`data/raw/field/` is in the archive and the spec did not put it there** — the EO *log* is under `data/live/`, the sampled top-10k *squads* are not, and they are the only bytes in this tree no command can rebuild. The archive is renamed in from a `.part` sibling, so a full disk leaves no truncated file for the next prune to keep
- [ ] §2.7 `gaffer tidy`, honest about reclaiming 54 KB; the ~34 MB of timestamped API snapshots next door is out of the spec's scope and stayed out. It refuses a negative cutoff and refuses to run outside the project root, because "nothing to tidy" is what a clean tree also prints
- [ ] §2.8 LAN write protection: one middleware and a keyword-only `create_app(token=)`, so every existing caller and test is untouched; 403 rather than 401; the token compared as bytes so a non-ASCII one is a refusal and not a 500; the QR carries `?token=` so a scanning phone can write
- [ ] §2.9 the "as of" strip, mounted **once** in `AppShell` rather than six times in six hubs — which also covers `/league/rival/:id`, the route with no hub. Each of the five rows degrades on its own: a file that vanishes between the glob and the stat greys one cell rather than 500ing an endpoint every page calls
- [ ] §2.10 `gaffer mcp`: six read tools, five of them the router's own function. `whatif` is not — `POST /api/whatif` returns a job id — so it wraps `solve_whatif`, importing from a protected module without editing it, and runs the route's own `_validate` first so a bad request is a sentence rather than a MILP infeasibility. `mcp==2.1.1`, fifteen new transitive deps, pydantic 2.13.4 → 2.13.5
- [ ] Config-pin restructure: eight files pinned `len(fields(Config)) == 48`, seven protected — the same shape v10b hit with routes and v11 retired, and it had already cost v10 a designed config field. Each becomes the by-name claim its cycle is entitled to make; the total lives in `test_v12_w1_degradation.py` alone. The v9d `create_app()` source pin went the same way: it had forced `cli.ui` to spell one call as two branches to keep a grep matching
- [ ] No replay — nothing on the training path moves, and the two decision-path edits are a config-backed default that falls back to the shipped value and a constant merge in a module whose own docstring says it annotates and never decides
- Pins: job kinds 12, config fields 48 → **53**, routes 45 → **46**
- Residuals: `journal.py` keeps its own `os.replace` (import-only this cycle, named in the census rail alongside `backup.py`'s streamed-tarball rename); the spec's `[solver]` section does not exist — `top_n` went in `[optimizer]` by ruling, and W2/W5 must read it there; ~34 MB of timestamped API snapshots under `data/raw/` accumulate unswept and are outside §2.7; the served rollover check reads disk rather than the API, so it cannot see a season FPL has published and this machine has not fetched; the gate's live-`refresh` box is the orchestrator's, because `refresh` writes into `data/`
- Suite: 3354 Python + 680 frontend (G1, implementer-measured)


## Operational / housekeeping
- [x] Untrack `reports/` artifacts + `.claude/`; gitignore both (`31dc239`)
- [x] Set odds API key in `config.toml` `[odds]` (done 2026-08-25; G3 live spot-check recorded in v4b spec §13)

## Explicitly rejected (don't re-add)
- Price-change chasing · per-player finishing multipliers · big horizon extension · fabricated "EO thresholds"
