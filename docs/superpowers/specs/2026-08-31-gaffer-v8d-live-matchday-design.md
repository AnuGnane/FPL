# gaffer v8d — live matchday

Date: 2026-08-31. Parent: `2026-08-30-gaffer-v8-research-proposal.md` (cycle 4 of 7). Lean cycle.
Goal: make the Live hub the Saturday-afternoon screen — who comes on if my player stays at 0, where my score is *going*, and what I need to hold or take each league place.

Prior art note: live bonus prediction (the proposal's v8d item 1) already shipped in v6 (`live_gw.provisional_bonus`, real 3/2/1 BPS tie rule, stands down once FPL awards) — not re-done here.

## 0. Decisions

- **D1 — All new computation is pure functions in `live_gw.py` + the live router; no new stores.** Live state is ephemeral by definition. `live_gw.py` and `web/routers/live.py` are NOT protected and are the natural seams. `entry_live_points`' no-autosub contract stays untouched (its callers pin it); projection is a *separate* additive function.
- **D2 — Auto-sub projection (F1).** `projected_subs(picks, points_of, minutes_of, finished_by_team, positions) -> list[{out_element, in_element, reason}]`: a starter whose team's fixture is FINISHED with 0 minutes is projected out; bench order walked with the same formation-legality rule as `backtest.score_gw` (first legal swap; bench GK only for GK). Yet-to-play starters are NOT projected out. Captain finished with 0 minutes ⇒ vice inherits the armband in the projection. Output feeds both my card (name the incoming player, "auto-sub projected") and the league table's `projected` column (which today ignores autosubs).
- **D3 — Live EP race (F2).** Per entry (me + tracked rivals): `race_point = live_points + Σ remaining_ep`, where `remaining_ep` per owned player = that GW's banked component EP (from `reports/components_gw{N}.parquet`, `ep` for the GW) scaled by the fraction of the fixture not yet played (not-started = 1.0, in-play = 1 − minutes/90 floored at 0, finished = 0), × multiplier, with projected autosubs (D2) substituting their EP when triggered. Served as a series: one snapshot per poll appended IN-MEMORY per server process (no disk) — the chart shows the session's trajectory plus the pre-GW reference line (`advice.expected_pts` when the advice gw matches). Absent components ⇒ race degrades to live points only, with a notice.
- **D4 — League safety score (F3).** For each adjacent rival (one above, one below, plus leader): `margin_now = (their live+projected) − (my live+projected)` and `need = points I must add beyond current projection to overtake/hold` — league-relative only (global safety needs field-wide live data we don't have; stated in the card). Rendered as a compact strip above the league-live table.
- **D5 — UI.** Live hub gains: race chart card (recharts LineChart, session series + reference line), safety strip, "projected auto-subs" chips in the Your-players card, and the league table's `projected` column now autosub-aware. Poll cadence unchanged (60s). Empty/degraded states for: no active GW, no components, no league.

## 1. Gates (orchestrator-run)

- **G1 (live smoke)** — against the real API during/after GW2: `/api/live` returns the new fields; projected subs match a hand-check of my squad (any finished-0-minute starters); race value = live + remaining-EP arithmetic spot-checked; safety margins consistent with the league table.
- **G2 (rails)** — `tests/test_v8d_degradation.py`: components absent ⇒ race = live points + notice; no league ⇒ safety absent, players card fine; dead API ⇒ existing 422 guard unchanged; `entry_live_points` byte-identical behaviour (pin copied); projection is display-only (no store writes anywhere in the new paths); job-kind count unchanged (no new kinds).
- **G3 (suites + audit)** — full py+fe suites, tsc, build, zero protected diffs.

## 2. Constraints

Protected zero-diff list as prior cycles. `live_gw.entry_live_points` and `league_live_table`'s existing output contract: additive only (new keys fine, existing semantics pinned by existing tests — EXCEPT `projected` which deliberately improves; its change is called out and its tests updated deliberately, never quietly). No disk writes from live paths. No config keys.

## 3. Out of scope

Event markers/goal annotations on the race chart (needs per-event timelines; later polish); global overall-rank safety (impossible without field-wide live data); persisting race history across restarts (ephemeral by design); autosub-aware *rival* EP (rivals get the same D2 projection for points but their remaining-EP uses their picks' components only when cheap — planner decides; degrade to live-points-only per rival if not).

## 4. Outcome

(Filled at cycle end.)
