# Gaffer v6 "Cockpit" — Design

Approved in brainstorm 2026-08-27. A combined cycle: two small, gate-measurable
model pieces (set-piece penalty EP, calibrated scenario noise) plus a four-piece
UI half that makes the advisor's decisions inspectable ("decision cockpit").
Everything degrades to today's behavior byte-identically when its input is
missing; degradation rails are part of the deliverable, as in v5.

## 1. M2 — Penalty-taker EP (prediction-time, incremental)

FPL's bootstrap already publishes taker orders per element:
`penalties_order`, `direct_freekicks_order`,
`corners_and_indirect_freekicks_order` and their `_text` notes (verified live
2026-08-27: 66 players carry a pens order). No scraping.

**Scope: penalties only.** DFK/corner orders are surfaced in the UI why-panel
as context but get no EP term this cycle — xA features already price
established takers, and a corner-taker delta is too small to validate.

**The double-count problem.** A player's xG features already contain the
penalties he historically took, so a naive additive term overpays Salah-types.
The term credits only the *increment* over what history priced in:

```
ep_pen(p) = (share_now(p) − share_hist(p)) · team_pens_pg(t) · PEN_CONVERSION
            · goal_points(position) · p_play(p)
```

- `share_now(p)`: 1.0 if `penalties_order == 1`, 0.15 if order 2, else 0.
  Order 2 is a hedge for rotation/absence of the first taker.
- `share_hist(p)`: player's trailing share of his team's penalties over the
  last 2 seasons + current, from Understat (`pens_taken ≈ goals − npg`;
  misses are invisible in player-match data — accepted approximation, noted
  in the module docstring). Team pens over the same window from the same
  frame. Zero-shot players (no history) get `share_hist = 0` — the term is
  maximal exactly where the model is blind (a new taker).
- `team_pens_pg(t)`: `LEAGUE_PENS_PG · attack_mult(t)` where
  `LEAGUE_PENS_PG` is computed from the ingested history (league penalties /
  team-games, all seasons pooled — one number, computed at predict time from
  the Understat frame, not hardcoded) and `attack_mult` is the team's
  Dixon-Coles attack strength ratio vs league mean, clamped to [0.6, 1.6].
- `PEN_CONVERSION = 0.78` (constant).
- `goal_points`: 10/6/5/4 for GK/DEF/MID/FWD per the scoring table already in
  the codebase.
- The whole term is clamped to **[−0.3, +0.8] xPts** — a safety bound, since
  no historical backtest can validate it (taker orders are serve-time-only
  data, same class as news).

Integration: a new `set_piece_ep(players, comp, understat_frame, dc_model)`
helper applied inside `predict_components` after the availability passes,
adding to the goals component (and therefore EP) with the term logged per
player. `predict_components`'s protected source-text tests must keep passing —
the insertion respects the pinned ordering windows.

**Rails:** taker fields missing/None for all players → term is identically
zero → components byte-identical to today (test). Understat frame unavailable
→ `share_hist = 0` path still bounded by the clamp.

**Gate P1 (audit, not replay):** taker orders don't exist historically, so no
backtest gate is possible — recorded honestly. Instead the cycle ships an
audit: `gaffer advise` logs every nonzero term ≥ 0.05 xPts (name, share_now,
share_hist, term), and the spec §8 outcome records the live distribution
(count, max, mean). Sanity bounds: established first-choice takers (share_hist
≈ 1) must sit near 0; the max must respect the clamp.

## 2. M3 — Calibrated scenario noise

Today `optimize/scenarios.noise_ep` uses the heuristic
`ep · (92 − xmins)/134 · N(0,1)` — never fitted to anything. Replace the scale
with an empirical residual table:

- **Calibration** (`gaffer calibrate-noise`, module
  `src/gaffer/calibrate_noise.py`): on the walk-forward benchmark predictions
  (the same machinery `evaluate` uses, 2024-25 test season), collect residuals
  `points − ep` per player-GW, bin by predicted EP (edges [0, 2, 3, 4, 6, ∞))
  × xmins (edges [0, 30, 60, 80, 90.1)), fit σ per cell (min 100 obs per
  cell, else pool to the EP-bin marginal, else global). Write
  `src/gaffer/assets/scenario_noise.json` with the bin edges, σ table, obs
  counts, run metadata. Validator: every σ finite, positive, < 10.
- **Serving:** `noise_ep` looks up σ(ep_bin, xmins_bin) and draws
  `max(0, ep + σ_scaled · N(0,1))` where `σ_scaled = σ · sqrt(horizon_week)`
  is NOT applied — per-GW cells are noised independently exactly as today;
  only the scale changes. Asset missing → current heuristic, byte-identical
  (rail test, monkeypatching the loader as the v5.1 rails do).
- One subtlety carried over from today's design: the heuristic's nailedness
  scaling exists so nailed players don't flip between sims. The empirical
  table keeps that property naturally (xmins-90 cells have small σ) — the
  gate checks it rather than assuming it.

**Gate S1 (replay):** 2025-26 replay, calibrated vs heuristic noise, same
seeds, D1-style: total points, hits, transfer count. Calibrated ships if
total is not worse by more than 5 points (noise shapes *robustness*, not EP —
parity is a pass; a win is a bonus). Both arms use the same trained models
(memoized, house style). If S1 fails, the asset still ships but the loader
defaults to the heuristic with the result recorded.

## 3. U1 — Chip workbench (new page)

New frontend page `ChipWorkbench.tsx` (+ route/nav "Chips"):

- **Chip table**: `chip_table` from the latest advice JSON rendered as
  gain-vs-threshold bars per (chip, gw), play-now rows highlighted.
- **Wildcard tab**: `wildcard_now.wc_squad` vs current squad — kept / out /
  in columns with names, positions, prices, EPs (the diff computed
  server-side).
- **Interactive re-solve**: lock / ban / force-in pickers (typeahead over the
  candidate pool) + chip selector, submitting to the existing
  `/api/whatif` job flow and rendering the returned baseline-vs-constrained
  delta. No new solver code — this is a front door onto What-If with
  `chip="wc"` prefilled.

New endpoint `GET /api/chips` (router `web/routers/chips.py`): latest advice
JSON's `chip_table`, `wildcard_now` resolved to names via the solve state,
plus the current-squad diff. 404 with a friendly detail when no advice run
exists.

## 4. U2 — Why-this-plan panel (ThisWeek page)

Two parts:

- **Per-player EP breakdown.** `run_advise` persists the components frame
  (per player: p_play, e_min, goals, assists, CS, saves, bonus, pen term —
  columns already computed in `predict_components`) to
  `reports/components_gw{N}.parquet` alongside the solve state. New endpoint
  `GET /api/components/{gw}` serves it; ThisWeek rows expand to show the
  decomposition for XI/bench/buys/sells.
- **Plan diff vs previous run.** `run_advise` appends each run's advice JSON
  to `reports/advice_history/` as `gw{N}-{UTC timestamp}.json`, keeping the
  newest 20 files (prune on write). New endpoint `GET /api/advice/diff`
  returns the structured diff of the two most recent runs *of the same GW*:
  buys/sells added/dropped, captain change, chip-recommendation change,
  expected-points delta. ThisWeek shows a "since last run" strip when a
  previous run exists; nothing otherwise (no error state).

## 5. U3 — News transparency panel (ThisWeek page)

New endpoint `GET /api/news/{gw}` (router `web/routers/news.py`) joining, for
every player the news layer *moved* (p_play_news ≠ p_play_flags in the latest
shadow rows for that GW):

- news vs flags p_play and e_min (from `data/live/news_shadow.parquet`,
  latest `run_at` per code),
- the source rows that fired: official flag (status + chance from bootstrap),
  injury-feed row (status, return date, raw reason text), lineup hint
  (xi/doubt/out) — from the normalized availability frame, which `run_advise`
  persists to `reports/availability_gw{N}.parquet` for this purpose,
- player name/team resolved server-side.

ThisWeek renders it as a "News moved N players" panel; each row shows the
per-source evidence (the Gibbs-White case reads: official 75% · FFS Out ·
news 0%). Empty/missing artifacts → panel hidden.

## 6. U4 — N2 scoreboard (Quality page)

`evaluation.json` already carries `news_shadow.by_gw` (Brier news vs flags,
minutes MAE news vs flags, rows per GW). Quality page gets a "News layer"
section: per-GW paired bars (news vs flags) for Brier and MAE plus the
overall verdict line, rendered only when `rows > 0` (first data after GW2
completes). No new backend — `/api/quality` already serves the file.

## 7. Cross-cutting

- **Branch/workflow:** branch `feat/gaffer-v6`; Opus implementer subagents,
  orchestrator reviews between groups; gates orchestrator-run; final
  adversarial review; ff-merge.
- **Ordering:** M2 → M3 (gates need lead time) → U2 artifacts (components /
  history / availability persistence, since U1/U3 endpoints read them) →
  endpoints → frontend pages.
- **Protected tests** stay green: run_advise ordering pins, predict_components
  window pins, degradation rails.
- **No new config.** All features are on by default and degrade silently;
  the noise asset and pen term have no knobs beyond their committed
  constants.
- **Artifacts hygiene:** `reports/` stays untracked; the only new committed
  asset is `scenario_noise.json`.

## 8. Verification

Suite green throughout (backend + frontend, tsc clean). Orchestrator-run:
Gate S1 replay (calibrated vs heuristic noise); Gate P1 live audit of pen
terms; a full `gaffer advise` + `gaffer ui` smoke walking all four UI pieces
against real artifacts. Rails: no taker data → byte-identical components; no
noise asset → heuristic; no history/availability/shadow artifacts → panels
hidden, advise unaffected. §9 records outcomes.

## 9. Outcome

(recorded at cycle end)

## 10. Not in this pass

DFK/corner EP terms; npxG feature migration (A2 — revisit if P1's audit shows
systematic drift); distributional EP (M1); EO forecasting (M4); news v2
corrector (M5 — awaits shadow evidence); any price-change modeling
(explicitly rejected).
