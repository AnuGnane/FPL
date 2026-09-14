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

Run 2026-09-13/14 on branch `v18d-layering`, seven code commits after the
spec (`6d67df4` … `27c5d67`). All five gate lines held; two rulings the spec
did not foresee are recorded below.

1. **Golden after every group: PASS three times.** `.venv/bin/pytest -q -rs
   tests/test_golden_board.py tests/test_pipeline.py` → `58 passed` after
   group A (`e74e5f0`, 18:04), after group B (`6431353`, 17:58) and after
   group C (`27c5d67`). No skip line, no fixture change; the four expected
   files and the Inputs are v18c's recording (`afc6e7c`) untouched.
2. **Routes 51; `npm run types -- --check` silent** (exit 0). No schema
   class or field moved; `schemas.py` gained 29 hub banners, comments only.
3. **Rails in `tests/test_layering.py`: three functions, nine tests,** each
   with a planted-fault twin under `tmp_path`, plus a live mutation by the
   orchestrator on the real tree (a `gaffer.web` import appended to
   `brief.py`, a function-body `price_timing` import replanted in
   `served.py`, an `advise` import appended to `config.py`): each fired,
   each reverted.
4. **Every router 4xx sentence unchanged:** the router tests passed
   throughout; `web/coerce.py` has its own table (`tests/test_web_coerce.py`).
5. **Suites green:** Python 4438 without the golden (4496 with it),
   frontend 988 (+1 skipped), `tsc` clean; frontend source untouched.

**Rulings made during the cycle.**

- *The what-if validators stay in the router* (against §2's fourth bullet
  and the design's ruling 6). `_validate` is built from `WhatIfRequest` and
  raises the 422; `_summary` returns `PlanSummary`. A core copy would import
  `web.schemas` — the very edge rail 1 forbids — or duplicate the sentences
  rail 4 pins. Their names went public (`validate`, `summary`) for `drafts`
  and the MCP server, which was the reach the move was for.
- *Rail 1 exempts the two surfaces whole,* `cli.py` (`gaffer ui`, `gaffer
  mcp`) and `mcp_server.py`, rather than "server-wiring lines": both exist to
  call the web layer. After group A they are the only importers of
  `gaffer.web` outside `web/`.
- *`snap_date` moved to a new leaf, `gaffer/clock.py`.* The `served →
  price_timing` hoist was blocked by `price_timing → price_log → snapshot →
  artifacts → served`, and the only thing the two price modules took from
  `snapshot` was the day key.
- *The override store's read half moved into `artifacts`* (`overrides_path`,
  `load_overrides`, `attach_overrides`, `OVERRIDE_COLS`, `opt_float`,
  `clipped`); `overrides.py` keeps the write half and imports the names
  back. That is what let `artifacts`, `snapshot` and `models/availability`
  import `attach_overrides` at the top.
- *`fit_dnp_calibrator` takes the inner model as a factory* (`inner=`) and
  lost its `seed` parameter, which the factory carries; the mode vocabulary
  (`DNP`, `SUB`, `START`, `MODE_COLS`, `mode_labels`, `SIXTY_MINUTES`) is
  `models/modes.py`, imported back into `minutes`.
- *`config.invalidate` walks a registry* (`config.on_invalidate`);
  `price_timing` registers its cache clear at import.
- *`chips` reads the wildcard bar off `chip_policy` at call time,* so the
  sentinel rails patch one binding.

**New names.** `gaffer/difficulty.py` (`rate_fixtures`,
`difficulty_by_team`, three frozen dataclasses), `gaffer/refresh.py`
(`run_data_refresh`), `gaffer/clock.py` (`snap_date`),
`gaffer/models/predict.py` (`MODEL_NAMES`, `predict_components`,
`news_availability`), `gaffer/models/modes.py`,
`gaffer/optimize/formation.py` (`XI_BOUNDS`, `formation_legal`),
`gaffer/web/coerce.py` (`fail`, `opt_float`, `opt_int`, `finite`),
`config.cap`, `config.on_invalidate`, `match_odds.code_for`,
`tracking.HEALTH_PATH`, `journal.JOURNAL_PATH` off `artifacts.REPORTS`.

**Left open.** `routers/meta.py` still spells `REPORTS / "health.json"`
for the health route (a web→tracking edge was not worth the one line);
`artifacts._history_stamp` (from `journal`), `journal._code_of_element`
(from `review`), `config._source_of` (from `routers/settings`) and
`data.cups._cached_get` (from `core_insights`) are private reaches the spec
did not name and the rail does not pin — v18g's single-home pass is the
place to decide them.
