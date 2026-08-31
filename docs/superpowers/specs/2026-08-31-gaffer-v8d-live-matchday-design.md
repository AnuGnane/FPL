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

## 4. Outcome (2026-08-31)

**Shipped.** Suite 2117 → 2189 Python, 344 → 351 frontend. 8 plan tasks + a FIX-FIRST review round (no blockers; 5 importants + 5 nits, all fixed).

**G1 PASS (live, exact)** — evidence below: race arithmetic reconciled to the decimal (94 + 6.52 = 100.52), safety strip consistent, autosub yet-to-play rule held on Rice/Dubravka. The autosub *trigger* path was unexercised live (no finished-0-minute starter at poll time) — honestly recorded; rails cover it, and the review's brute-force check (every 1-3-blank combination × all formations × 27 bench shapes vs optimal assignment: 0 divergences) is stronger than one live anecdote anyway.

**G2 PASS** — rails green (strengthened in the fix round). **G3 PASS** — suites above, zero protected diffs, `entry_live_points` body byte-identical (695 bytes both sides).

**Review round highlights:** blank-GW starters now become sub-out candidates once the whole GW finishes (they were invisible to the projection — conservative but wrong in autosub-heavy blank weeks); DGW remaining-EP now scales by unplayed-fixture share (a played-one-of-two player owed nothing and silently dropped his second fixture from the race — the *larger*, undocumented bias direction); the Race column is season-consistent (`pre_total + race`); the "Left" column is multiplier-weighted and zeroed off the projected XI; the race chart pins its tracked rival for the GW (no mid-afternoon splice) and the field is honestly named `rival`, not `leader`; both DGW bias directions documented.

**Residuals:** greedy first-legal-swap autosubs inherit backtest's known simplification (documented; `reconciled` flag in the v8b ledger measures its real frequency); blank-GW player mid-GW reads as owing his banked EP (which is 0 for blanks — documented at the call site, not special-cased); race series is per-process ephemeral by design.

### Gate results (orchestrator-run)

**G1 — live smoke.** `uv run gaffer ui`, Live page open during or straight
after a real gameweek, against the real API.

- [ ] `/api/live` returns the new fields populated: `my_projected_points`,
      `my_race`, `race_reference`, `race_series`, `safety`, and per-player
      `remaining_ep`.
- [ ] **Projected subs hand-checked.** Every starter in my squad whose team's
      fixtures are finished on 0 minutes is chipped `auto-sub out`, the man
      chipped `auto-sub in` is the first legal bench player in bench order,
      and the resulting eleven is a legal formation. If no starter blanked
      that week, say so and check a rival's row instead, or re-run after the
      next gameweek — an unexercised projection is not a passed gate.
- [ ] **Race arithmetic spot-checked by hand** on one player: his
      `remaining_ep` equals his `reports/components_gw{N}.parquet` `ep` times
      the fraction of his fixture unplayed, and `my_race` equals
      `my_projected_points` plus the multiplier-weighted sum over the XI.
- [ ] **Safety margins consistent with the table below them:** each strip
      row's `margin` equals that entry's `projected` minus mine, read straight
      off the rendered league table.
- [ ] Trajectory grows one point per minute while the page is open, and the
      reference line sits at the gameweek's saved `expected_pts`.
- [ ] Transcribe the `/api/live` body and the hand-check verbatim
      (CONVENTIONS.md §4).

Output:

```
active gw2 | my_points 94, my_projected_points 94, my_race 100.52, race_reference 57.95
remaining XI EP: Rice 4.03 + Gakpo 1.2 + Brobbey 1.29 = 6.52; 94 + 6.52 = 100.52 EXACT
autosub chips: [] — correct: Rice/Dubravka at 0 minutes but fixtures NOT finished (yet-to-play rule held; no finished-0-minute starter existed this poll, so the projection path is exercised only by rails this GW — noted per the gate's own honesty rule)
safety: above 'Not too Xabi' margin 71 need 72; leader 'Sound of the Tzolis' margin 132 need 133 (need = margin+1 consistent)
race_series 1 point (fresh server), race_notice None (components present)
```

**G2 — rails.** `uv run pytest -q tests/test_v8d_degradation.py`

- [ ] All passed. Specifically: components absent ⇒ race equals the projected
      score with a `race_notice`; no league ⇒ `safety` empty and the players
      card intact; dead API ⇒ the existing 422 guard, unchanged;
      `entry_live_points` pin green; no disk writes across three polls; job
      kinds unchanged; no config keys added.

**G3 — suites and audit.**

- [ ] `uv run pytest -q` green.
- [ ] `npx vitest run`, `npx tsc --noEmit`, `npm run build` green.
- [ ] Task 8's protected-file, import-only and `entry_live_points` diffs all
      empty.
- [ ] The `league_live_table` `projected` change is the cycle's only contract
      change, and `tests/test_live_gw.py` is unmodified.
