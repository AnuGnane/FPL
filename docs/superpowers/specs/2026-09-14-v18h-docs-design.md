# v18h — the docs, true

**Cycle:** v18h, the last sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18h;
design `specs/2026-09-12-v18-polish-design.md` ruling 12; the review's
`research/2026-09-12-final-review.md` §4; every hand-off note in
`plans/2026-09-12-v18-tracker.md`). **Branch:** `v18h-docs` off `main` at
`adfdbba`. **Date:** 2026-09-14. No code changes: `src/`, `tests/` and
`frontend/` are untouched, so the golden gate is not run and the suite is
run once to quote its numbers.

## 1. Gate, stated before anything runs

Two lines.

1. **No checklist row blank.** Every row of §2 carries `done`, with the
   file and what changed, or `left` with the reason. A row the cycle finds
   false in the review's own claim says so rather than editing to match.
2. **Every `CLAUDE.md` command run once with its output pasted** in §3 —
   the ones that read (`--help` where a command's real run would rewrite
   this week's served advice or spend odds quota: `gaffer advise`,
   `gaffer brief`; the ruling is recorded in §3), the suite, the inner
   loop, the golden's line quoted from v18g's run of an hour earlier
   (18:02, 58 passed, 0 skipped; the tree is byte-identical outside
   `docs/`), `gaffer ui` started and stopped, the frontend `check`, the
   types check.

## 2. The rows (review §4, the tracker's "for v18h" notes, ruling 12)

### 2.1 `CLAUDE.md` (orchestrator)
- [x] R1 the orchestrator-only list gains `tests/test_served_plan.py`,
  `tests/test_golden_board.py`, `tests/test_pipeline.py`, `tests/test_advise_order.py`
  and `tests/test_layering.py` (the pins the older rails protected live
  there now); the pin table's `JOB_KINDS` row says `tests/test_v12_w1_degradation.py`
  (v18g); the suite count (~4500) and the frontend line (`npm run check`,
  ~1100 tests); the golden line's minutes (~18); the ruff line.
- [x] R2 the review's other three `CLAUDE.md` rows (`advise` chains the
  brief; `test_v16_restraint.py`'s description; the layout naming
  `pipeline.py`, `served.py`, `inputs.py`, `config_in_force`) — v18a fixed
  them; verified, not re-edited.
  → done — `CLAUDE.md`: the five pin-carrying files in the orchestrator-only list, the `JOB_KINDS` row's one home, the meta-rail sentence, the suite/inner-loop/ruff/`npm run check` lines (`7a468db`)
  → done — verified in place, v18a's edits stand

### 2.2 `docs/GUIDE.md` (implementer, then the orchestrator's read)
- [x] G1 `:4` "last updated" → 2026-09-14, after v18h.
- [x] G2 the horizon: `config.py:108` defaults to **3**; the GUIDE's
  "six-gameweek" sentences (`:65`, `:89`, `:124` and any other) say the
  default is three and this machine's overlay sets six.
- [x] G3 "nine settings" (`:409`) → fourteen (`settings_keys.WHITELIST`).
- [x] G4 "seventeen became fourteen" (`:984`) → thirteen, per the commit.
- [x] G5 §8 gains `gaffer core-insights`.
- [x] G6 v18d's stale names: `routers/meta.ticker` (the rating's home is
  `difficulty.py`), `advise.predict_components` (`models/predict.py`),
  `run_data_refresh` (`refresh.py`), `_difficulty_by_team` (a one-line
  delegate to `difficulty.difficulty_by_team`) — grep, not the v18d
  spec's list.
- [x] G7 §11's closing paragraph (4,425 + 986) → 4509 + 1098 as of v18h;
  §11's header says v18h; a v18h line.
- [x] G8 §12 rewritten as of 2026-09-14: §12.0 says what `launchctl list`
  shows today (2 of 9 — `backup`, `core-insights` — see §3; the seven
  older jobs are not loaded on this machine; `install_automation.sh` is
  the fix and the user's to run); §12.4 drops the two residuals v17 closed
  (the trace's present-tense price line, v17f; `threshold_source`
  unrendered, `ChipsTab.tsx`); §12.2's table marks the rows whose
  condition has filled (presser grading, EO trend, review-row snapshot)
  and the flag-latency row past its expected date; the counts that moved.
- [x] G9 the "70/30" row (`:104`): v18c already made it the fitted-weight
  sentence; verified.
  → done — 2026-09-14, after v18h
  → done — three by default, bounded 1–8; **the review's premise was wrong**: this machine's effective horizon is also 3 (`config.example.toml` ships 3), so the GUIDE's six-week sentences were simply false and now say three
  → done — fourteen, with the v13/v15/v16 additions named
  → left — the review's claim is false: v17h's spec says PASS at 14, the ROADMAP row says 17 → 14, `ThisWeek.fetches.test.tsx` asserts 14 today; the sentence stands
  → done — `gaffer core-insights [--refresh N]`
  → done — none of the four names is in the GUIDE (the tracker's note over-counted); the only `routers/meta.py` mention was in the old README, now gone
  → done — header and TOC say v18h; the v18h entry; 4,509 + 1,098
  → done — §12 as of 2026-09-14; §12.0 around the real `launchctl` output (2 of 9, the seven named, the install script the user's); §12.2 four rows filled (presser grading, EO trend, review-row snapshot, Elo 2026-27) and flag latency past due; §12.4 the two v17 residuals dropped, disk numbers refreshed, a v17/v18 residuals group
  → done — verified, v18c's fitted-weight sentence stands

### 2.3 `README.md` (implementer)
- [x] M1 the ~1000 lines of v8e–v12 cycle diary go (GUIDE §5/§11 hold
  them); the file is the front door: what it is, clone / `uv sync` /
  Python 3.12 / `npm install`, the weekly ritual, the command table with
  `gaffer brief`, configuration, the UI, automation, tests (4509 / 1098,
  routes 51, Config 62, the inner loop and the golden), docs pointers.
- [x] M2 names deleted by v17e (`serving_config`, `optimizer_top_n`,
  `NON_FIELD_OPTIMIZER_KEYS`) gone; "6 is the default" horizon corrected.
  → done — 1693 → 413 lines; all 27 subcommands checked against `--help`; the key named by field only
  → done — the three v17e names gone; horizon 3

### 2.4 `docs/superpowers/ROADMAP.md` (orchestrator)
- [x] O1 the v18 block with the closing ledger transcribed from the
  tracker (eight rows) after the v17 block's shape; "Where things stand"
  as of v18h.
- [x] O2 the install box: what `launchctl` shows today.
- [x] O3 the data-gated table: three rows met, one past due.
- [x] O4 the 09-04 review's items 2–8 as candidates; the §6 replay in the
  Open index.
- [x] O5 the three decisions (ruling 12) recorded with the user's answers
  of 2026-09-12: branches deleted before v18a; the model cycle follows
  v18; the incident stays with the user, undecided.
  → done — the v18 block with the eight-row ledger before the v17 block; "Where things stand" as of v18h
  → done — 7 of 9 (09-03), 9 of 9 (09-08), 2 of 9 (09-14); the user's to run
  → done — three met, flag latency past due
  → done — items 3, 4, 7 as candidates 11–13 (2, 6, 8 closed by v18c); the §6 replay in the Open box list
  → done — in "Where things stand"

### 2.5 Specs (orchestrator)
- [x] S1 `2026-09-02-gaffer-v11-ui-design.md` Outcomes, from the ROADMAP's
  v11 block.
- [x] S2 the v7 and v7b specs' "N2 — pending": GW2's reading is banked
  (ROADMAP: flags ahead, one draw; GUIDE §12) — recorded with a pointer.
  → done — from the ROADMAP's v11 block
  → done — both specs point at the GW2 reading (flags ahead, one draw)

### 2.6 Tracker and memory (orchestrator)
- [x] T1 ledger row, checklist, hand-off note; the memory file.
  → done — the tracker's row, checklist and hand-off note in the docs commit on `main`; the memory file

## 3. Outcome

Run 2026-09-14. Both lines held: every row above carries its verdict (two
`left` with the reason — G4 the review was wrong, and the extra GUIDE §3
row the implementer found, the missing `defcon` model, was added), and
every `CLAUDE.md` command ran once:

```
$ uv run gaffer advise --help          → Usage: gaffer advise [OPTIONS]   (help only: a real
$ uv run gaffer brief --help           → Usage: gaffer brief [OPTIONS]      run rewrites this
                                          week's served advice and spends odds quota — the user's)
$ uv run gaffer ui --no-open-browser --port 8927
                                       → "gaffer UI on http://127.0.0.1:8927"; GET /api/health 200; stopped
$ .venv/bin/pytest -q                  → 4509 passed, 4 warnings in 1289.93s (0:21:29)
$ .venv/bin/pytest -q -m "not slow and not golden"
                                       → 4361 passed, 148 deselected, 4 warnings in 74.06s
$ .venv/bin/pytest -q -rs tests/test_golden_board.py tests/test_pipeline.py
                                       → 58 passed in 1082.86s (0:18:02), 0 skipped — v18g's run of the same tree
                                          outside docs/; the full run above includes the eleven golden tests
$ uvx ruff check src tests             → All checks passed!
$ cd frontend && npm run check         → Test Files 114 passed; Tests 1098 passed | 1 skipped; 0 errors, 8 warnings; exit 0
$ cd frontend && npm run types -- --check   → exit 0
```

One thing learned: `npm run check` run while the full pytest suite was
running failed one test (`SettingsTab > saves one key at a time`: the
typed value read `35`, the field's `3` plus the typed `5` — a `clear` that
lost the race under load). It passed alone and passed in the re-run on an
idle machine, quoted above. The test is load-sensitive, not wrong;
recorded in the tracker's hand-off note.
