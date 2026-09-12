# v18a — the gate, back on

**Cycle:** v18a, the first sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md`; design
`specs/2026-09-12-v18-polish-design.md`, rulings 1 and 12).
**Branch:** `v18a-gate` off `main` at `04f24e5`. **Date:** 2026-09-12.
**Plan:** the programme's §3 v18a task list; this spec adds one task (2b)
found on the way.

## 1. Gate, stated before anything runs

1. `.venv/bin/pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py`
   on the branch → **54 passed, 0 skipped** (the baseline after the
   re-record, then again at the tip).
2. `.venv/bin/pytest -q tests/test_pipeline.py` **alone** → passes (the
   import-order fault gone).
3. A scratch tree with one `models/*.meta.json` altered →
   `golden_header_or_skip` skips with a sentence naming that file, the
   count, and `python -m tests.golden_client --write`; the rail that asserts
   this is shown to fail when the sentence is broken (mutation).
4. `pytest -q` with `models/` renamed away → the live-model tests skip, the
   seam tests pass.

Verdict: all four lines, or no merge.

## 2. What the cycle found on the way

- The board did not move: `--write` reproduced every expected file byte for
  byte, because the 09-11 retrain rebuilt the same models from the same
  frame; only the header's hashes and stamps changed.
- `--write` and `--inputs` recorded different Inputs. `write_expected` runs
  the board and then gathers once more **in the same scratch tree**, so the
  second gather reads the advice the first run wrote and records it as
  `prior_advice`; `--inputs` gathers in a fresh tree and records `null`.
  Task 2b makes `--write` gather in a fresh tree too. The committed fixture
  carries the `null` (re-recorded with `--inputs`, `a0bd45c`).

## 3. Outcome — PASS, first run

Run by the orchestrator on the branch tip (`a79428d`), 2026-09-12.

1. `pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py` →
   **56 passed, 0 skipped** in 15:20 (54 from the baseline on the fixture
   alone, plus the two new tests). The baseline on the re-recorded fixture
   before any code change: 54 passed, 0 skipped in 15:30.
2. `pytest -q -rs tests/test_pipeline.py` alone → **15 passed** in 5:19.
3. The rail `test_a_stale_board_skips_naming_the_file_and_the_command`
   passes; with the `--write` command dropped from the sentence it failed
   with `assert 'python -m tests.golden_client --write' in 'golden board
   recorded under a different models/team.joblib (1 input(s) differ)'`, then
   passed again restored. The second rail
   (`test_write_expected_gathers_the_inputs_in_a_fresh_scratch_tree`) failed
   with `assert 1 == 2` when the gather was pointed back at the run's root.
4. With `models/` renamed away: **48 passed, 8 skipped**, every skip reading
   `golden board needs models/ under … (absent); run gaffer train first`; the
   seam-level tests passed.

Verdict: merge. Pins unmoved (51 / 12 / 62).
