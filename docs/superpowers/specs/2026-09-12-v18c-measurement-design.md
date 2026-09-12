# v18c — measurement that has never run

**Cycle:** v18c, the third sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18c;
design `specs/2026-09-12-v18-polish-design.md`, ruling 11).
**Branch:** `v18c-measurement` off `main` at `f890c02`.
**Date:** 2026-09-12. **Plan:** the programme's §3 v18c task list.

## 1. Gate, stated before anything runs

1. The golden, untouched: `.venv/bin/pytest -q -rs tests/test_golden_board.py
   tests/test_pipeline.py` → all passed, 0 skipped; `expected/advice.json`,
   `solve_state.json`, `plan.json`, `ladder.json` byte-identical to v18b's
   recording. The recorded Inputs are re-recorded once with `--inputs`,
   because the components frame gains a column (`e_goals_model`) and the
   sealed rail compares that frame to the recording; the diff is declared
   as one added column and nothing else.
2. On this machine, after the branch is built: `uv run gaffer evaluate
   --calibration` then `jq '.calibration.p_play.n' reports/evaluation.json`
   → a positive integer, recorded here. Before the change the block has
   read `n: 0`, `season: 2025-26` since 2026-09-01.
3. `uv run gaffer review` then `jq '.advice_pts, .actual_pts'
   reports/health.json` → two numbers, not `null`.
4. Rails: the CLI passes `None` for `evaluate`'s season and
   `train_seasons[-1]` for `backtest`'s; `compute_health` receives the
   ledger's points; `e_goals_model` is banked beside `e_goals` and equals
   the model output where `p_play < 0.1`; each tab renders its
   counterfactual sentence (one test each).
5. Two screenshot pairs (Model → Review, Model → Journal), dark and light,
   differing only by the new sentence; the sentence approved by the user.

Verdict: all five, or no merge.

## 2. What the cycle must know

- `cli.py:687` `season: str = "2025-26"` on `evaluate` is the bug:
  `evaluation.evaluate_calibration(season=None)` already grades the
  configured season. `cli.py:523` on `backtest` is *not* a bug — a backtest
  needs a finished season — but a literal will rot at rollover, so it
  becomes `train_seasons[-1]`.
- `tracking.compute_health(..., advice_pts=None, actual_pts=None)` has one
  caller, `update_health` (`tracking.py:53`), which passes neither; the
  ledger (`reports/decision_ledger.json`, `gws[]`) carries `my_points` and
  `model_points` for the graded gameweek. Populate from the newest graded
  row; a ledger with no graded row leaves them `None` as today.
- `data/odds.py:688-695` blends `e_goals` with the market's per-appearance
  rate wherever `p_play > 0`; the pre-blend value is lost. Bank it as
  `e_goals_model` in `artifacts.COMPONENT_COLS` (`artifacts.py:41-48`); the
  blend itself is untouched (changing it moves served numbers — the model
  cycle's).
- The two counterfactuals: `journal.py` scores the model's own recommended
  XI gross (no hit cost); `review.py` scores *your* squad with each lane
  swapped to the model's. GW2 reads +8 to the model in one and +3 to you in
  the other. One sentence on each tab says which it is.
- GUIDE §3's "70/30" becomes the fitted weight sentence.

## 3. Outcome — PASS, with two gate lines corrected on the way

Run by the orchestrator on the branch tip, 2026-09-12.

1. **Golden:** 58 passed, 0 skipped in 18:11; the four expected files
   byte-identical to v18b's recording; the Inputs re-recorded once
   (`afc6e7c`), the diff exactly one file, `inputs/components.parquet`,
   which gained the `e_goals_model` column.
2. **Calibration on this machine:** `uv run gaffer evaluate --calibration`
   grades **GW2 (n=618) and GW3 (n=652)** for `p_play`, `p60` and `p_haul`,
   with `p_cs` in the cumulative row (about 20 club-fixtures a gameweek,
   under the 30-sample floor). Before: `season: 2025-26`, `gameweeks: []`,
   unchanged since 2026-09-01. The gate line's `jq` path was wrong (the
   counts live under `gameweeks[].heads.<head>.n`); the numbers are the ones
   above.
3. **Health:** the gate line named `gaffer review` as the trigger; it is
   not — `update_health(gw - 1)` runs from `gather_inputs` on the advise
   path (`advise.py:627-629`), and `review` had nothing new to grade. A
   post-deadline `advise` would overwrite the served GW4 artifact, so the
   function was called directly: `update_health(3)` →
   `advice_pts: 63, actual_pts: 70`, matching the review tab's GW3 row. The
   file fills on its own at the next advise run.
4. **Rails:** 4 CLI, 2 tracking, 5 components-artifact, 2 vitest, all
   green; the golden's sealed rail compares the gathered frame with the new
   column to the re-recorded one.
5. **Screenshots:** four pairs under `.superpowers/shots/v18c-{before,after}`,
   the control shot from a `main` worktree served through its own source
   path; each pair differs by the one sentence and nothing else (checked by
   eye on `review-dark` and `journal-light`). The user was not present;
   approved by the orchestrator under the user's standing instruction to run
   the programme, with the images kept for the user's review.

Suite: 4445 → **4458** Python (with the golden), 986 → **988** frontend.
Verdict: merge. Pins unmoved (51 / 12 / 62).
