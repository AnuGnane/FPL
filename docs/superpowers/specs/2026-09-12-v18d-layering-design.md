# v18d — the core out of the web layer

**Cycle:** v18d, the fourth sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18d;
design `specs/2026-09-12-v18-polish-design.md`, rulings 5 and 6).
**Branch:** `v18d-layering` off `main` at `5bd6923`.
**Date:** 2026-09-12. **Plan:** the programme's §3 v18d task list, run in
three groups, the golden after each: (A) difficulty and the plan timeline;
(B) the refresh job body, the what-if validators, the cycle-dodging
imports; (C) the coercion module, the paths, the schema banners, the
layering rail.

## 1. Gate, stated before anything runs

1. **Golden after every group:** `.venv/bin/pytest -q -rs
   tests/test_golden_board.py tests/test_pipeline.py` → 58 passed, 0
   skipped; the four expected files and the Inputs byte-identical to
   v18c's recording (`afc6e7c`). No fixture change is expected in this
   cycle; one would be a finding, not a re-record.
2. **Routes 51**, `types.generated.ts` unchanged (`npm run types --
   --check` silent): no schema field moves.
3. **Rails in `tests/test_layering.py`,** each planted-fault tested:
   - no `from gaffer.web` / `import gaffer.web` outside `src/gaffer/web/`
     and the server-wiring lines of `src/gaffer/mcp_server.py` (which may
     import the app, never a router's handler);
   - the import graph built from *top-level* imports of every module under
     `src/gaffer` is acyclic;
   - the seven function-body imports the review named
     (`inputs.py` → `advise`, `snapshot.py` → `advise`, `config.py` →
     `price_timing`, `served.py` → `price_timing`, `artifacts.py` →
     `overrides`, `optimize/chip_policy.py` → `chips`,
     `models/dnp_calibrate.py` → `minutes`) are gone, and the private
     cross-module reaches (`backtest._formation_legal` from `live_gw` and
     `review`, `match_odds._code_for` from `understat`, `advise._cap` from
     `backtest`) are gone.
4. **Every router 4xx sentence unchanged:** the existing router tests are
   the instrument; `web/coerce.py` gets its own table.
5. Suites green; frontend untouched (no screenshot gate).

Verdict: all five, or no merge.

## 2. What the cycle must know

- `web/identity._difficulty_by_team` *calls the route handler*
  `meta.ticker(weeks=2)` (its docstring says why: one rating, not two);
  the core needs the same single rating, so the computation moves to
  `gaffer/difficulty.py` and **both** the route and the core call it. The
  identity module keeps its mtime cache around the core call.
- `brief.move_gains` imports the `plan` route handler for the timeline's
  first week; since v17f the router is a shape adapter over
  `artifacts.served_plan(gw)`. The brief reads the served plan directly; if
  the route does anything beyond `served_plan`, that goes into
  `served.py` and the route calls it.
- `routers/meta.run_data_refresh` is a job body imported by
  `web/job_kinds.py`; it moves to `gaffer/refresh.py` whole, the router
  keeps nothing of it. `job_kinds.py` is the caller.
- `routers/whatif._validate`/`_summary` are imported by `routers/drafts.py`
  and used by `mcp_server.py`; they move to `gaffer/whatif.py`. The router
  is orchestrator-only; the diff is a move with no edit.
- The lazy imports exist to dodge cycles that go through `advise.py`.
  Hoisting them means moving what they reach for: `predict_components`,
  `news_availability` and `MODEL_NAMES` from `advise.py` into `models/`
  (orchestrator: `advise.py` re-exports nothing; callers import from the
  new home), `_formation_legal` into `optimize/` (orchestrator), and
  `config.py:675`'s `owned_price_falls` re-export deleted (config must not
  depend on a feature).
- Six `_fail` definitions across the write routers; their messages are
  pinned by the router tests and must not change by a character.
- `journal.py:27`, `tracking.py:64,69` and `advise.py:102` spell
  `reports/` themselves; `artifacts.REPORTS` is the one home.

## 3. Outcome

_(filled at the gate)_
