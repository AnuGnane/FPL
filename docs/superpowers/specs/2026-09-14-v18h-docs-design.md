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
- [ ] R1 the orchestrator-only list gains `tests/test_served_plan.py`,
  `tests/test_golden_board.py`, `tests/test_pipeline.py`, `tests/test_advise_order.py`
  and `tests/test_layering.py` (the pins the older rails protected live
  there now); the pin table's `JOB_KINDS` row says `tests/test_v12_w1_degradation.py`
  (v18g); the suite count (~4500) and the frontend line (`npm run check`,
  ~1100 tests); the golden line's minutes (~18); the ruff line.
- [ ] R2 the review's other three `CLAUDE.md` rows (`advise` chains the
  brief; `test_v16_restraint.py`'s description; the layout naming
  `pipeline.py`, `served.py`, `inputs.py`, `config_in_force`) — v18a fixed
  them; verified, not re-edited.

### 2.2 `docs/GUIDE.md` (implementer, then the orchestrator's read)
- [ ] G1 `:4` "last updated" → 2026-09-14, after v18h.
- [ ] G2 the horizon: `config.py:108` defaults to **3**; the GUIDE's
  "six-gameweek" sentences (`:65`, `:89`, `:124` and any other) say the
  default is three and this machine's overlay sets six.
- [ ] G3 "nine settings" (`:409`) → fourteen (`settings_keys.WHITELIST`).
- [ ] G4 "seventeen became fourteen" (`:984`) → thirteen, per the commit.
- [ ] G5 §8 gains `gaffer core-insights`.
- [ ] G6 v18d's stale names: `routers/meta.ticker` (the rating's home is
  `difficulty.py`), `advise.predict_components` (`models/predict.py`),
  `run_data_refresh` (`refresh.py`), `_difficulty_by_team` (a one-line
  delegate to `difficulty.difficulty_by_team`) — grep, not the v18d
  spec's list.
- [ ] G7 §11's closing paragraph (4,425 + 986) → 4509 + 1098 as of v18h;
  §11's header says v18h; a v18h line.
- [ ] G8 §12 rewritten as of 2026-09-14: §12.0 says what `launchctl list`
  shows today (2 of 9 — `backup`, `core-insights` — see §3; the seven
  older jobs are not loaded on this machine; `install_automation.sh` is
  the fix and the user's to run); §12.4 drops the two residuals v17 closed
  (the trace's present-tense price line, v17f; `threshold_source`
  unrendered, `ChipsTab.tsx`); §12.2's table marks the rows whose
  condition has filled (presser grading, EO trend, review-row snapshot)
  and the flag-latency row past its expected date; the counts that moved.
- [ ] G9 the "70/30" row (`:104`): v18c already made it the fitted-weight
  sentence; verified.

### 2.3 `README.md` (implementer)
- [ ] M1 the ~1000 lines of v8e–v12 cycle diary go (GUIDE §5/§11 hold
  them); the file is the front door: what it is, clone / `uv sync` /
  Python 3.12 / `npm install`, the weekly ritual, the command table with
  `gaffer brief`, configuration, the UI, automation, tests (4509 / 1098,
  routes 51, Config 62, the inner loop and the golden), docs pointers.
- [ ] M2 names deleted by v17e (`serving_config`, `optimizer_top_n`,
  `NON_FIELD_OPTIMIZER_KEYS`) gone; "6 is the default" horizon corrected.

### 2.4 `docs/superpowers/ROADMAP.md` (orchestrator)
- [ ] O1 the v18 block with the closing ledger transcribed from the
  tracker (eight rows) after the v17 block's shape; "Where things stand"
  as of v18h.
- [ ] O2 the install box: what `launchctl` shows today.
- [ ] O3 the data-gated table: three rows met, one past due.
- [ ] O4 the 09-04 review's items 2–8 as candidates; the §6 replay in the
  Open index.
- [ ] O5 the three decisions (ruling 12) recorded with the user's answers
  of 2026-09-12: branches deleted before v18a; the model cycle follows
  v18; the incident stays with the user, undecided.

### 2.5 Specs (orchestrator)
- [ ] S1 `2026-09-02-gaffer-v11-ui-design.md` Outcomes, from the ROADMAP's
  v11 block.
- [ ] S2 the v7 and v7b specs' "N2 — pending": GW2's reading is banked
  (ROADMAP: flags ahead, one draw; GUIDE §12) — recorded with a pointer.

### 2.6 Tracker and memory (orchestrator)
- [ ] T1 ledger row, checklist, hand-off note; the memory file.

## 3. Outcome

_(filled at the gate: the checklist above with every row marked; the
command outputs.)_
