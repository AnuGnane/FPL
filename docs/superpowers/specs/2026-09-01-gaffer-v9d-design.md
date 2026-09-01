# gaffer v9d — debt close + calibration monitoring

Date: 2026-09-01. Branch: `feat/gaffer-v9d` off `50bc6a8`.

v9d clears the residuals v9c recorded and adds the one new thing that makes every
future model cycle better targeted: a standing calibration report. Four
workstreams, deliberately small.

## §0 Constraints (standing)

- Implementation by Opus subagents; the orchestrator reviews and runs gates.
- **Protected files** (zero unauthorized diffs): `src/gaffer/advise.py`,
  `set_pieces.py`, `optimize/**`, `web/jobs.py` *except* the two authorized
  line-groups named in §3, `web/routers/whatif.py`, `tests/test_advise.py`,
  `test_odds.py`, `test_web_jobs.py`, all pre-existing
  `tests/test_*_degradation.py`, `scripts/s2_replay.py`. `journal.py` /
  `backtest.py` import-only.
- Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`,
  `config.toml`, `src/gaffer/web/static/`. Never `git add -A`.
- Pins: `JOB_KINDS` stays 12; `Config` stays 48 fields (nothing here needs a
  new config key). Route count changes only where §4 says so, and the v9c pin
  test is protected — new pins go in `tests/test_v9d_degradation.py`.

## §1 Club-leak close (the two unswitched consumers)

`bps.py:129-136` names them. Both still key on retro-stamped `team_code`;
`engineer.as_of_club(df)` (engineer.py:53-70) is the read seam the three v9c
consumers already use.

**1a. `merge_understat_team` own side** (engineer.py:944-991). The own-side
merge at :976 joins on `["team_code", "_date"]`. Switch: build
`out["_club"] = as_of_club(out)` before the merge and join `keyed` (renamed
`team_code`→`_club`) on `["_club", "_date"]`, dropping `_club` with `_date`
afterwards. The **opponent side stays on `opp_code` untouched** — `opp_code`
is fixture-derived, not retro-stamped, and is not part of the leak. Keep
`validate="many_to_one"` on both merges.

**1b. `add_congestion` cup-tie club lookup** (`_recent_load`,
engineer.py:544-560). The per-club cup lookup reads `df["team_code"]` at :553.
Switch to `clubs = pd.to_numeric(as_of_club(df), errors="coerce")`. The guard
at :544 (`"team_code" not in df.columns`) stays as-is — `as_of_club` itself
falls back to `team_code` and needs the column present.

**Do not touch** the deliberate `team_code` at engineer.py:453-460 (rotation
probe frame; the comment forbids it).

**Measurement (gate G1)**: `scripts/v9d_club_eval.py`, patterned on
`scripts/v9c_club_eval.py` — for each of the two consumers report (a) the share
of historical player-rows where `as_of_club` ≠ stamped `team_code` *and* the
consumer's inputs actually change (for 1a: the own-side Understat feature
values differ; for 1b: the congestion count differs), and (b) a sanity check
that the switched join's match-rate (non-NaN own-side rows) does not fall
versus the unswitched join. Numbers go into §5 of this spec verbatim.

## §2 SSE / job-runner single-process guard

The dossier's finding: state lives on `app.state.job_runner` (app.py:51), one
per process; `cli.py:609` calls `uvicorn.run(create_app(), ...)` with an app
instance so `workers>1` is impossible *today*, but nothing says so. Scope —
documentation and rails, no re-architecture:

- A comment block at `cli.py:609` and on `JobRunner` (web/jobs.py, outside the
  protected line-groups — the class docstring is fine) stating the single-process
  contract and why (SSE streams, single lane, in-memory runs).
- Rail in `tests/test_v9d_degradation.py`: source-inspect `cli.py` and assert
  the `uvicorn.run` call passes a non-string app (i.e. no import-string +
  `workers=` drift can land silently).

## §3 Polish batch

**3a. Identity memoisation** (`web/identity.py`). Cache the three parquet-read
helpers (`_teams`, `_player_teams`, `_fixture_by_team` inputs, and whatever
`_difficulty_by_team` reads) keyed by `(path, mtime_ns, size)` of the backing
file, module-level dict, no TTL — a refreshed parquet changes mtime and misses
naturally. The "nothing here raises" contract holds: a `stat` failure means
just read the file uncached. Add a rail proving a second `with_identity` call
with unchanged files does zero `store.load` calls (spy), and a changed mtime
re-reads.

**3b. Cancel message wording** — **authorized edit, protected
`web/jobs.py`**, two line-groups:
- `_abandon_current` (web/jobs.py:294-296): when `older_than == 0.0` the error
  becomes `"cancelled — abandoned as a daemon, its thread still running"`;
  the timeout wording stays for `older_than > 0`. Provenance comment per the
  v9c convention.
- No other lines in the file move.

**3c. Per-kind abandon timeout**. `ADVISE_TIMEOUT_S` (web/jobs.py:30) is read
once, at `JobRunner.start` (:321), and covers all 12 kinds. Fix *without*
touching protected lines beyond the one read: add
`ABANDON_TIMEOUT_S: dict[str, float]` to `web/job_kinds.py` (default 1800.0,
`whatif`-style fast kinds 120.0 — set `advise-fast`, `snapshot`, `sensitivity`,
`track-pens` to 120.0; the rest 1800.0), and — **authorized edit,
third line-group** — the `:321` call site becomes
`self._abandon_current(ABANDON_TIMEOUT_S.get(run.kind, ADVISE_TIMEOUT_S))`
where `run` is the currently-running job. If the running job's kind is not
knowable at that point without restructuring, keep the constant and record
that in §5 instead — do not restructure protected code for this.

## §4 Calibration monitoring report

A standing per-GW reliability/Brier report so the next model cycle is chosen
on evidence. **No new job kind, no new config key.**

- New mode on the existing CLI: `gaffer evaluate --calibration` →
  `evaluate_calibration()` in `src/gaffer/evaluation.py`, saved under key
  `"calibration"` in `reports/evaluation.json` via the existing
  `save_evaluation` seam.
- What it computes, per completed (data_checked-gated, i.e. present in
  `player_gw.parquet`) gameweek of the current season and cumulatively:
  - Brier + reliability curve (existing `reliability()` primitive) for
    `p_play` (outcome: minutes > 0), `p60` (minutes ≥ 60 given played),
    `p_start` (started, if the starts column exists — else omit the head and
    say so in the payload), `p_cs` (team kept a clean sheet), and `p_haul`
    (outcome: goals + assists ≥ 2, matching the assemble-path "P(2+ returns)"
    definition — this is the attacking-haul probability, `p_attacking_haul` at
    the web boundary).
  - Per-head sample counts; a head with < 30 samples reports
    `"insufficient"` rather than a curve.
  - Predictions must be *as-of* predictions: source them from the banked
    advice artifacts / snapshot path if available for that GW, else refit
    strictly-before like `evaluate_current` does — whichever the planner
    finds already exists; never grade a prediction made after the outcome.
- Web: extend the Model hub. `GET /api/model/calibration` (new route on the
  existing model router; route-count pin moves by exactly +1 in the *new*
  degradation file) returning the banked payload, 200-with-empty when absent.
  Frontend: a "Calibration" card in the Model hub — per-head Brier trend
  (simple table, one row per GW) and a reliability strip; honest empty state
  ("Run evaluate --calibration after a graded gameweek").
- Wire `--calibration` into the existing `evaluate` job kind's runner if the
  job plumbing passes flags; if it doesn't, CLI-only is acceptable for v9d and
  the UI card says how to run it.

## §5 Gates

- **G1** — club measurement: `scripts/v9d_club_eval.py` numbers recorded here;
  match-rate must not regress; divergence share reported per consumer.
- **G2** — 3-seed replay, branch vs re-run main (CONVENTIONS §1), reusing the
  v9c worktree driver (generalize `scripts/v9c_replay.sh` into
  `scripts/replay_pair.sh` taking a branch name, or copy — planner's call).
  Pass = mean delta within the seed spread.
- **G3** — full suite green (2825 py + 554 fe baseline); new
  `tests/test_v9d_degradation.py` carries the new pins (routes, kinds still
  12, Config still 48); frontend suite extended for the Calibration card.
- **G4** — adversarial review, fix-first, then merge ritual (ff-only, push,
  `git show main:config.toml` fails, key-grep empty).

### G1 results (filled after measurement)

_TBD by the cycle._

### G2 results

_TBD by the cycle._
