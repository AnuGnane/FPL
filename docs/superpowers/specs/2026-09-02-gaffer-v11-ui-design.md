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

### G1 — suites, rails, pins (measured by the implementer)

- [x] `uv run pytest -q` — 3193 passed (branch baseline 3135 + 50 new + 8 from
      the G2 fix round)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — 655 passed, 1 skipped, 68 files (baseline 596 + 46
      new + 13 from the G2 fix round; run twice, both green)
- [x] `npm run build` — clean
- [x] Protected source diff EMPTY. The cycle's one protected edit is the route-
      pin restructure in three degradation files, authorized separately (Task
      11); no other protected file moved
- [x] Pins: job kinds still 12, config fields still 48, **OpenAPI paths 45 →
      45** — every serve-side change is an additive field on an existing model
- [x] Rails: an unpriced move — or one too broken to parse at all — blanks the
      bank for that week and every later one; a NaN `p60` serves null on both
      probabilities and on `xmins`; no field log →
      `field_eo`/`field_se`/`field_n` all null and never 0.0; today's one-row
      ledger → four lanes reading "never graded", zero
      wins and zero losses; a ledger row with no `overall_rank` still
      validates; `GET /api/review` still 200s on a clone with no ledger
- [x] Empty states on a cold clone for all three new views, each tested where
      the hub-level cold-clone rail cannot reach it (it renders only the
      default tab)
- [x] 390px and no-bare-tables hold tree-wide, including the two six-tab
      strips. None of the three new views draws a `<table>`, so the
      `wrapped()` sweep gained no caller — but the sweep is not the whole
      claim, and until the G2 fix round nothing asserted these three views
      at 390px at all: the hub-level rail renders only each hub's default
      tab, and none of the three is one. Each now carries its own 390px
      render test in its own file (`PlannerBoard`, `SeasonTab`,
      `ComparePanel`): no `<table>`, no console error, and for the board,
      the week strip owning its own `overflow-x-auto`
- [x] Exactly one file in the suite pins an absolute route count, asserted by
      a test rather than by hand

### G2 — review and merge (orchestrator only)

- [x] Adversarial review (2 blockers — p60 served 0.00 for an unmodelled
      player in the absent-never-zero view; DGW xmins total counted a missing
      fixture as zero — plus 6 importants incl. the deep-link solving the
      current week under a future week's constraints, unannounced) → fix
      round → re-verify (fixes confirmed red-first; caught the I5 fix
      over-correcting: the caption's operands swapped to two
      equal-by-construction quantities) → micro-round `5c68f20`.
      3193 py + 655 fe, tsc clean.
- [x] Merge ritual: ff-only, push, `git show main:config.toml` fails, key-grep
      empty.

### No replay — recorded reasoning

Nothing on the training or decision path changes, and this time the claim is
almost trivially checkable: the cycle's entire server-side diff is seven
additive fields on five existing pydantic models plus the arithmetic that fills
them. No feature builder, no model, no head, no solver call — spec §Non-goals
forbids one from any view and none was added. `season_summary` and
`grade_gw_from` are on the *review* path, which grades decisions after the fact
and feeds nothing back into one. A replay would compare two identical arms,
which is v10's G2 and v10b's G2 for the third time.

### Live spot-checks (orchestrator, on the dev server)

- [ ] Planning → Board draws one column per horizon week, no padding, and the
      bank reads across them; a plan with an unpriced move shows an em dash
      from that week onward rather than a confident number.
- [ ] "Try these changes" lands on What-If with the week's buys in `force_in`
      and its sells in `ban`, **without** starting a solve, and the sentence
      about what a sell means is visible without hovering.
- [ ] The five pre-existing Planning tabs still switch by click (the controlled
      `Tabs.Root` regression).
- [ ] Players → Compare shows a signed breakdown whose rows sum to the xPts
      above them, a minutes line, set-piece flags, tinted next-six chips that
      are still position-correct for a goalkeeper, and Field EO with its ±SE.
- [ ] Model → Season shows the gate sentence naming GW2 `data_checked` on
      today's ledger, and every lane reads "never graded" rather than 0%.
- [ ] `GET /api/plan/5`, `/api/players`, `/api/review` all still answer on a
      cold clone the way they did before.

### Residuals (left standing)

- Compare's expected-minutes total is captioned "Expected minutes across both
  fixtures". A double is the only multi-fixture week the fixture list has shown
  so far, but a triple gameweek makes "both" wrong — three fixtures, one
  total — and the wording would have to count the fixtures it is summing. The
  arithmetic is already general (it sums `here`, whatever its length, and
  blanks on any null); only the sentence assumes two.

### Outcomes

_TBD by the cycle._
