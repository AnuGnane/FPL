# gaffer v11 — the UI trio

Date: 2026-09-02. Branch: `feat/gaffer-v11` off `be87be9` (v10b).

Frontend-heavy cycle. Python changes are limited to serving whatever the
three views need; nothing on the training or decision path moves.

## §0 Constraints (standing)

- Implementation by Opus subagents; orchestrator reviews and runs gates.
- **Protected files**: `src/gaffer/advise.py`, `set_pieces.py`,
  `optimize/**`, `web/jobs.py`, `web/routers/whatif.py`,
  `tests/test_advise.py`, `test_odds.py`, `test_web_jobs.py`, all
  pre-existing `tests/test_*_degradation.py`, `scripts/s2_replay.py`.
  `journal.py` / `backtest.py` import-only. No protected edits anticipated;
  a route addition follows the v10b precedent (STOP, orchestrator authorizes
  the historical pin literals).
- Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`,
  `config.toml`, `src/gaffer/web/static/`. Never `git add -A`.
- Pins: `JOB_KINDS` 12; `Config` 48; route moves deliberate and pinned in
  `tests/test_v11_degradation.py`. **Also do the route-pin residual**: each
  historical degradation file's absolute count assert is this cycle replaced
  by a path-existence assert for the routes that cycle added, with ONE
  absolute count pin living in the newest file only — the plan enumerates
  the exact edits per protected file for orchestrator authorization (this
  pays the authorization toll once and retires the recurring collision).

## §F1 — transfer planner board (Planning hub)

A GW-by-GW column view of the current plan. One column per horizon week
(plus chip weeks the plan names): planned buys/sells with prices, hits
taken, bank trajectory, chip, and price-change warnings inlined from the
watchlist/price signals already served. Sources are all existing: the
advice artifact's plan/timeline (Timeline.tsx already reads it), the
price endpoints, the watchlist. Interactions stay honest: a "try changes"
button deep-links into the What-If Lab with constraints prefilled (the
ChipsTab "Try it" pattern) — the board never pretends to re-solve locally.
Empty states: no advice yet; a plan whose horizon ends (fewer columns is
fine, never pad).

## §F2 — comparison deepen (Players hub)

The existing ComparePanel gains the model's reasoning per player:
- EP component breakdown (the `BREAKDOWN_COLS` the artifact already
  carries: minutes/goals/assists/cs/gc/bonus/…), rendered as a stacked
  breakdown per player with signed components.
- `p_play` / `p60` / xmins line; set-piece and pen-taker flags.
- Next-6 ticker strip with the difficulty chips (v9b Timeline pattern).
- The three ownership numbers (global / league EO / field EO ±SE) with
  the absent-not-zero convention throughout.
Server: verify what the compare/players payloads already carry and extend
additively; a new endpoint only if the existing ones genuinely lack the
columns (route-pin process applies).

## §F3 — season review dashboard (Model hub, beside Review)

Built now with honest empty states (user-approved), filling as gameweeks
grade:
- Rank trajectory vs decision quality over the graded `ReviewGw` rows
  (lanes, points_on_bench, accuracy, hindsight — schemas.py:1106-1131).
- Cumulative "points left on bench" and per-lane win rates with the
  graded-counter honesty rule (a lane never measured is never "never
  wrong").
- The calibration trend alongside (v9d's `calibration` key — per-GW Brier
  already served at /api/model/calibration).
- Empty state names the gate: "The first grades land when FPL marks GW2
  data_checked — the Tuesday review job banks them automatically."
Server: the review ledger and calibration payloads exist; a thin
aggregation endpoint only if client-side derivation would duplicate
grading semantics (prefer serving derived numbers next to the ledger the
way season_summary already does — reuse it, never re-derive).

## Non-goals

- No new solver calls from any view; no model changes; no new job kinds;
  no drag-and-drop plan editing (deep-link to What-If is the interaction).

## §Gates

- **G1** — suite green (3135 py + 596 fe baseline); `tests/test_v11_degradation.py`
  rails: every view's empty state on a cold clone (no advice, no ledger,
  no calibration, no field log); the route-pin restructure holds the total
  and the per-cycle existence asserts; responsive 390px + no-bare-tables
  hold tree-wide including the three new views.
- **G2** — adversarial review, fix-first, re-verify; merge ritual.
- **No replay** — nothing on the training/decision path. Recorded here.

### Outcomes

_TBD by the cycle._
