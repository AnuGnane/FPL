# gaffer v8b — the decision loop

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 3 of 7).
Goal: close the loop the whole app exists for — after each gameweek resolves, grade every decision the user made against the model's deadline-guarded counterfactual, in points AND in title odds, and keep a season-long ledger of where EV leaks.

## 0. Decisions

- **D1 — Bank the user's actual decisions per GW.** Nothing persists my picks/transfers/chips today (`fetch_my_team` fetches and discards). New module `src/gaffer/data/my_entry.py`: `bank_my_gw(client, entry_id, season, gw)` writes `data/raw/league/{season}/{entry}-{gw}.json` (the *exact* idiom `fetch_rival_picks_history` already uses — same directory, same shape, permanent) plus `data/raw/league/{season}/{entry}-history.json` (entry-history snapshot: per-GW points, rank, points_on_bench, transfers cost, chips — replace-on-write since it's cumulative). Banked automatically at review time; idempotent.
- **D2 — Grades are banked at review time, never re-derived.** `ADVICE_HISTORY_KEEP = 20` global means the model's pre-deadline advice for GW1 will be pruned within weeks. The review runs once a GW's `data_checked` flips, computes everything, and appends to `reports/decision_ledger.json` (atomic, replace-by-gw — the `league_sim_history` idiom). May's season review reads the ledger, not the history.
- **D3 — The counterfactual is the deadline-guarded advice, scored with real autosubs.** Reuse `journal.latest_run_per_gw()` verbatim (deadline guard + `post_deadline` flag) for "what the model said in time"; score every squad — mine, the model's, and hindsight's — with `backtest.score_gw` (autosubs, vice fallback, hit costs, bench-boost aware), imported not modified. `backtest.py` is edited-by-exception only: if a helper needs sharing, re-export — don't move.
- **D4 — Two currencies: points and Δwin%.** Points via `score_gw` on the `player_gw.parquet` slice. Title odds via v8c's engine: `build_inputs(cfg, client, gw=N)` rebuilds past inputs from banked component parquets; my `Entry.picks` is swapped for each counterfactual squad and `simulate_league` re-run same-seed (the paired-comparison pattern the what-if router already uses). Counterfactual pick lists carry `position` so `effective_picks` normalizes correctly. Δwin% is reported with its MC granularity (whole pp at n=2000) and is omitted (with a notice) for GWs where component parquets are gone.
- **D5 — The grading taxonomy (pre-registered, stable).** Per GW, four decision lanes, each graded independently:
  - **Transfers** (the set actually made vs the model's proposed set, including hits),
  - **Captaincy** (actual armband vs model's captain; vice counted only when it played),
  - **Bench order** (actual bench points lost vs the model's ordering — includes autosub consequences),
  - **Chip** (played/held vs `chip_table[].play_now`).
  Each lane gets `delta_pts` (my choice − model's choice, both scored on actuals) and `delta_pwin` (same, in title odds), plus a label: **Brilliant** (beat the model by ≥ +4 pts and Δwin% > 0), **Good** (≥ +1), **Aligned** (|Δ| < 1 or I followed the model), **Inaccuracy** (≤ −1), **Blunder** (≤ −4). A **Miss** row is added when the model flagged a move I didn't make and it returned ≥ 6 pts over its replacement. One 0–100 **GW accuracy** = 100 × (my XI points with my choices) / (my XI points had I taken the model's four lanes), capped at 100... no — defined exactly as `min(100, round(100 * my_score / model_score))` with `model_score` floored at 1; when I *beat* the model the score is 100 and the surplus is the "Brilliant" story. `post_deadline=True` GWs grade with an "advice was late" caveat flag carried on the row.
  - **EV-loss ledger**: season-running sums per lane in both currencies plus `points_on_bench` (from the entry API — reconciled against our own bench computation), and the **hindsight XI** (best legal XI + captain from my 15, scored with `score_gw`; the gap = "selection EV left on table").
- **D6 — Placement: Model hub, fifth tab "Review".** JournalTab stays untouched (its cumulative chart remains); the new ReviewTab renders per-GW grade cards (label chips per lane, the counterfactual point lines, accuracy dial), the season ledger table, and the hindsight XI row. `GET /api/review` serves the banked ledger (404-free: empty ledger ⇒ empty state with "run review"); `review` job kind (9th) + Model-hub button; CLI `gaffer review [--gw N]` (never raises, one line per GW reviewed); launchd `com.gaffer.review.plist` Tuesday 09:00 local (post-`data_checked` for weekend GWs; midweek GWs picked up the following Tuesday or by button).
- **D7 — Reconciliation is a hard gate, not a hope.** For every reviewed GW: `score_gw(my actual squad)` must equal FPL's official `entry_history.points − event_transfers_cost` (net of hits; chip weeks handled: BB scores 15, TC multiplier 3, FH squad read from that GW's picks). A mismatch marks the row `reconciled: false` with both numbers shown — never silently trusted. (The known simplified-autosub caveats in backtest.py:36-38 are the expected source; the flag tells us their real frequency.)

## 1. F1 — my-entry banking [data]

`src/gaffer/data/my_entry.py`: `bank_my_gw` (picks per GW, permanent, idempotent), `bank_my_history` (replace-on-write), `load_my_gw(season, gw)`, `load_my_history(season)`, `my_transfers_for_gw(history_or_client, gw)` (from `get_entry_transfers`, banked alongside). All never-raise with printed one-liners on failure (launchd context).

## 2. F2 — the grading engine [model/functionality]

`src/gaffer/review.py`:
- `actuals_for_gw(gw) -> DataFrame` — `player_gw.parquet` slice shaped for `score_gw` (`code,total_points,minutes,position`, DGW-aggregated).
- `model_decisions(gw)` — via `journal.latest_run_per_gw()`: xi/bench/captain/vice/buys/sells/hits/chip-play-now + `post_deadline`.
- `my_decisions(gw)` — from banked picks + transfers + history (chip, hits, bench order).
- `grade_gw(gw, *, cfg, client=None) -> dict` — the four lanes per D5, reconciliation per D7, hindsight XI, Δwin% when components exist (engine calls isolated so a dead client/absent parquet degrades to points-only with a notice).
- `hindsight_xi(squad15, actuals) -> (xi, captain, points)` — best legal formation + captain by actual points (exhaustive over formations; 15 players, trivial).
- `run_review(cfg, gw=None)` — reviews every `data_checked` GW not yet in the ledger (or `--gw`), banks my entry first, appends to `reports/decision_ledger.json`, prints one line per GW.
- `season_summary(ledger) -> dict` — per-lane season sums (pts + pp), accuracy series, biggest Brilliant/Blunder.

## 3. F3 — API & UI [functionality/ui]

- `GET /api/review` (new `routers/review.py`): ledger + season summary; empty ⇒ `{gws: [], summary: null}` (200, not 422 — an unreviewed season is not an error). Schemas: `ReviewLane`, `ReviewGw`, `ReviewSummary`, `Review`.
- `review` job kind + Model hub header button; ReviewTab as fifth Model tab (Quality/Journal/Review/History/Health): per-GW cards (lane chips with labels colored by existing semantic tokens, delta lines "you −3.2 pts / −1 pp vs model captain Salah", reconciliation badge when false, late-advice badge from D5), season ledger card (per-lane totals + accuracy sparkline), hindsight XI card ("best you could have fielded: 74 — you scored 61; bench cost 8, captaincy 5").
- Frontend types lockstep (JOB_KINDS 9 + labels + count pin).

## 4. Gates (pre-registered; orchestrator-run)

- **G1 (real review)** — `gaffer review` over the finished GWs (GW1, and GW2 once `data_checked`): ledger written with all four lanes; **reconciliation exact on ≥1 GW** (any `reconciled:false` row investigated and explained in the outcome before merge — chip/DGW/autosub caveat named); idempotent re-run (second run reviews nothing, prints so); Δwin% present for GWs with banked components, absent-with-notice otherwise.
- **G2 (rails)** — `tests/test_v8b_degradation.py`: no banked picks ⇒ review skips with printed line (never fabricates); no advice history for a GW ⇒ row marked `no_advice` (graded lanes null, not zero); dead API ⇒ banking degrades, grading of already-banked GWs proceeds; ledger corrupt ⇒ rewritten from scratch for reviewable GWs, never crashes the router; `/api/review` empty-state 200; job-kind pins both sides; protected-ordering pins copied forward.
- **G3 (suites + audit)** — full py+fe suites, tsc, build, zero protected diffs.

## 5. Constraints

Protected zero-diff list as v8a/v8c. `backtest.py` and `journal.py` are import-only this cycle (re-export rather than move; journal's row shape is pinned by existing tests). Never stage data/, reports/, models/, logs/, config.toml. New config: none required (review uses existing entry_id/league_id); `[review]` section deliberately deferred until a real knob exists.

## 6. Out of scope

Season-in-review page (May artifact — reads this ledger; grab-bag later); manager-form rolling score (derivative of the ledger, later); drill mode (needs point-in-time snapshots); grading mid-GW (review only touches `data_checked` GWs); feeding grades back into advice.

## 7. Outcome

(Filled at cycle end.)
