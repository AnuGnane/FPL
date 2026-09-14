# v18g — the suite, one home per rule

**Cycle:** v18g, the seventh sub-cycle of the polish programme
(`docs/superpowers/plans/2026-09-12-v18-polish-programme.md` §3 v18g;
design `specs/2026-09-12-v18-polish-design.md` rulings 8, 9, 10; the
review's §3; `CLAUDE.md` Pins and protected files; the tracker's v18f
note). **Branch:** `v18g-suite` off `main` at `1d90ba8`. **Date:**
2026-09-14. **Plan:** six tasks; 1 (the `style:` commit), 2 and 3 are the
orchestrator's in their own commits, the rest implementer briefs.

## 1. Gate, stated before anything runs

Six lines, all six or no merge.

1. **`uvx ruff check src tests` → `All checks passed!`** under the
   committed `[tool.ruff]`: `select = ["E", "F", "B", "I"]`,
   `line-length = 100`, and exactly these ignores, each with its reason in
   `pyproject.toml`: `B905` (`zip(strict=)` on 174 sites is noise, not
   safety; the code targets 3.11 and every zip here is over parallel
   columns the caller built), `E402` per-file for the tests that import a
   fixture module after setting a path (`tests/test_milp.py`,
   `test_core_insights.py`, `test_chips.py`, `test_understat.py`,
   `test_scenarios.py`, `test_policy.py`, `test_league.py`,
   `test_dixon_coles.py`, `test_features.py`, `test_v17e_config.py`,
   `test_odds.py`, `test_match_odds.py`) and for `src/gaffer/models/minutes.py`
   (the re-export at the bottom, v5), `E501` per-file for
   `tests/test_v16_brief.py` (ten prose sentences asserted verbatim) and
   `tests/test_golden_board.py`. Everything else fixed: the sixteen B023
   each fixed or carrying `# noqa: B023` with a sentence.
2. **The meta-rail pins the job-kind count in one file.**
   `tests/test_v12_w1_degradation.py` gains
   `test_only_one_file_pins_the_job_kind_count`; the fourteen other
   `len(JOB_KINDS) == 12` become membership checks. Mutation shown: a
   scratch `tests/test_zz_scratch.py` asserting `len(JOB_KINDS) == 12`
   makes the new rail fail; deleted after.
3. **Seam order is behaviour.** `tests/test_advise_order.py` asserts the
   seven-seam order through `tests/gather_harness.py`'s call-order spies;
   mutation shown by swapping two calls in a scratch copy of the harness
   (or of `advise.py`'s gather) and watching it fail. The four verbatim
   source-text copies (`test_v5_degradation.py:264`,
   `test_v6_degradation.py:82`, `test_v8a_degradation.py:294`,
   `test_v8c_degradation.py:233`, all named
   `test_run_advise_still_orders_every_protected_seam`) deleted; the
   straddling case `tests/test_advise_source.py` documents stays as the one
   text pin.
4. **The inner loop under three minutes, warnings under 100.**
   `.venv/bin/pytest -q -m "not slow and not golden"` on this machine;
   `slow` on every test file the timing run in §3 shows over 5 s wall
   (the MILP and LightGBM files); `filterwarnings` for PuLP's
   `constraints` mapping deprecation with a note to migrate at PuLP 4, and
   for any other warning family over 100 counts once named. The command
   goes into `CLAUDE.md`'s Commands block and the golden's line stays.
5. **The suite runs on a clone.** `mv reports reports.off && .venv/bin/pytest
   -q -rs tests/test_report.py tests/test_chip_sanity.py` → no skip
   naming `reports/`; a tracked, trimmed `tests/data/gw2-advice.json`
   (a real advice payload cut to three players a line and the chip table
   kept) is what they read. `reports.off` restored before anything else.
6. **Counts.** Suite count before (4438 without the golden) and after,
   with the deleted copies named and the new files named; frontend 1098
   untouched (`npm run check` green — no frontend change but the prose
   fixture, whose test still passes).

Alongside: no backend behaviour change — the golden gate (58 passed, 0
skipped) is run once at the end because `src/` is touched by the `style:`
commit and the B023 fixes; routes 51, kinds 12, Config 62.

## 2. What the cycle must know

### 2.1 Ruff (task 1, orchestrator)

`[tool.ruff]` as in gate line 1. The `style:` commit is `uvx ruff check
--fix --select I,F401,E401,B009 src tests` and nothing else — imports
sorted, unused imports gone (a `# noqa: F401` re-export stays), one import
per line. Then the by-hand rules in a second commit: B023 (16: `data/odds.py`
7, `optimize/scenarios.py` 2, `web/jobs.py` 3, `ladder.py` 1,
`sensitivity.py` 1, `tests/test_v9d_identity_cache.py` 2 — a loop variable
captured by a lambda or a nested def; bind it as a default argument or
build the closure in a helper), B011 (`assert False, msg` → `pytest.fail(msg)`),
B017 (`pytest.raises(Exception)` → the type, or `match=`), F811 (a
redefinition — usually a fixture imported and shadowed), B904 (`raise …
from exc`), B008 (a call in a default), E731, E712, E741, E701, B007, E501
(21 lines wrapped or the two files ignored as above). `optimize/**`,
`web/jobs.py`, `advise.py` and the rail files are orchestrator-only, so the
orchestrator makes these edits.

### 2.2 The job-kind pin (task 2, orchestrator)

Ruling 8. `tests/test_v12_w1_degradation.py:129`'s
`test_the_job_kinds_are_still_twelve` is the one home; the new
`test_only_one_file_pins_the_job_kind_count` scans `tests/` for
`len(JOB_KINDS) ==` (any spelling the review counted: `len(JOB_KINDS)`,
`len(list(JOB_KINDS))`) and asserts the only file is this one. Each of the
fourteen other rails (`test_v8d`, `v8e`, `v8f`, `v8g`, `v9a`, `v9c`, `v9d`,
`v10`, `v10b`, `v11`, `v12_w3`, `v12_w4`, `v12_w5`, `v13`) keeps its test
name and asserts membership of the kinds that cycle added
(`assert "review" in JOB_KINDS`), with the count sentence in the docstring
replaced by "the count is pinned in the v12 W1 meta-rail". A pin-only
commit: nothing but those assertions changes.

### 2.3 Seam order as behaviour (task 3, orchestrator)

Ruling 9. `tests/gather_harness.py` already records the order every
gather seam is called in (`order`, the `spy` helper). `tests/test_advise_order.py`
runs the harness's gather once and asserts the seven seams in the order
the deleted text pins wrote: the league fetch before the tilt before the
pool (`fetch_rival_entries` < `tilt_ep` < `build_pool`), `compute_strategy`
before the pool, pen priors before `news_availability` before
`Predictions.components`, and whatever else the four copies assert once
they are read side by side (they differ by cycle; the union is the rail).
The mutation: a scratch copy of the harness with two spies' recorded
order swapped, or `advise.gather_inputs` monkeypatched to call two seams
in the other order — the test fails, the scratch is deleted.

### 2.4 The caches fixture and the provider test (task 4)

`tests/conftest.py`'s autouse fixture also clears, before and after every
test: `gaffer.web.identity.clear_cache()`,
`gaffer.web.field_frame.clear_cache()`,
`gaffer.optimize.scenarios.scenario_noise.cache_clear()`,
`gaffer.web.routers.league._OVERVIEW.clear()`,
`gaffer.web.routers.league_sim._CACHE.clear()`,
`gaffer.web.routers.live.RACE_SERIES.clear()` and `RACE_RIVAL.clear()` —
the review's seven — imported lazily inside the fixture so `conftest`
does not import the web app at collection. The fourteen ad-hoc clears in
test files go (the ones in orchestrator-only files by the orchestrator, in
the pin-only commit). `tests/test_v10_lineup_providers.py` passes through
`patch_view` (`tests/conftest.py`) a `Config` with the `[news]` fields the
test means (`news_lineup_absence`, `news_lineup_absence_damp`,
`news_lineup_providers`) at module or fixture level, so
`lineups.py:488`'s `config_in_force()` never reads the machine's overlay —
the "unattributed flake" in v18b's note.

### 2.5 Speed (task 5)

`slow` marker registered beside `golden`; applied per file with
`pytestmark = pytest.mark.slow` to every file over 5 s in the timing table;
`filterwarnings` entries for the PuLP deprecation (`ignore:…constraints…
mapping…:DeprecationWarning` — read the exact text off a run) and any
other family over 100, each with a one-line reason; the loop timed before
and after and both numbers recorded in §3.

### 2.6 Archive, fixtures, CLI smoke (task 6)

`scripts/archive/` for `v9c_club_eval.py`, `v9c_rc_arm.py`, `v9c_replay.sh`,
`v9d_club_eval.py`, `v10_autosub_cf.py`, `v12_xgps_arm.py` — `git mv`, with
`scripts/replay_pair.sh`, `scripts/v9d_club_eval.py` and
`scripts/v12_w4_autosub_cf.py`'s references to them repointed or, where the
referrer is itself archived, left; a one-paragraph `scripts/archive/README.md`
naming the spec each belongs to. `tests/data/gw2-advice.json`: a copy of
this machine's `reports/gw2-advice.json` (or the latest) trimmed so every
player list keeps three entries and the chip table stays, under 40 KB;
`test_report.py`'s `REAL_PAYLOAD` and `test_chip_sanity.py`'s reader
point at it and their skips go. The prose fixture
`frontend/src/hubs/this-week/restraint-prose.fixture.json` (178 KB)
regenerated by `tests/test_v17b_prose.py`'s writer with three-player XIs
(read how it builds `_case`; the frontend test that reads it must still
pass). `tests/test_cli_smoke.py`: for `build-history`, `understat`,
`league-sim`, `backtest`, `calibrate-decisions`, `diagnose-zeros` — `--help`
exits 0 and names the command, and a stubbed run (the underlying function
monkeypatched to record its call) reaches it with the parsed arguments.

### 2.7 What does not change

No number the advice serves (golden once at the end). No pin value. No
frontend source but the fixture. The rails' names stay; only their
assertions collapse to membership.

## 3. Outcome

Run 2026-09-14 on `v18g-suite`, nine commits over `1d90ba8`. All six lines
held.

1. **Ruff.** `uvx ruff check src tests` → `All checks passed!` under the
   committed `[tool.ruff]`. The `style:` commit was the auto-fix and nothing
   else: 335 fixes over 205 files; four names left `src/` (two feature lists
   in `models/train`, `SEASON_LAST_GW` in `optimize/chips`, `MAX_DRAFTS` in
   `routers/drafts`, pandas in `sensitivity`), none reached through its
   module by a test or a patch. The by-hand commit closed 63: the sixteen
   B023 closures bind their loop names as defaults (called only inside the
   iteration that made them; the binding says so), B904 `from None` on the
   CLI's three echo-then-exit paths, B011 `pytest.fail`, B017 the type
   (`ValidationError`, `FrozenInstanceError`, `ValueError` for pyarrow's
   junk), the rest by hand. Two deviations from §2.1, recorded: three test
   files with a sectioned mid-file import block (`test_calibrate_decisions`,
   `test_chip_policy`, `test_estimation_noise`) had their block merged into
   the top import rather than an E402 ignore, and typer's declarative
   defaults are listed under `extend-immutable-calls` rather than B008
   rewritten at two of twenty-eight sites. `wired` keeps its F811 with the
   reason on the import line; a fixture imported and then named as a
   parameter is what the rule sees.
2. **One home for the job-kind count.** Seventeen homes, not fourteen: the
   new rail's scan (either spelling, any module prefix) found three more
   under `job_kinds.JOB_KINDS` (`test_v8b_degradation`,
   `test_v8c_degradation`, `test_web_job_kinds_v8b`), and they collapsed with
   the rest. Mutation shown: a scratch `tests/test_zz_scratch.py` asserting
   `len(JOB_KINDS) == 12` failed the rail (`Left contains 1 more item`);
   deleted. Pin-only commit `e096a01`.
3. **Seam order as behaviour.** `tests/test_advise_order.py`, four tests over
   the harness's call record: the seven seams (`pen_priors`,
   `news_availability`, `Predictions.components`, `write_shadow`,
   `blend_attacking_odds`, `apply_calibration`, `ep_matrix`) in order and
   each once; the league fetch after the EP matrix; a failing goalscorer-odds
   request costs the blend and nothing else (the printed line proves the path
   was taken). The four copies deleted; `test_advise_source`'s straddle pin
   gained `compute_strategy` before the pool, the other name the copies
   pinned across the split. Mutation shown: `pen_priors` and
   `news_availability` swapped in `gather_inputs` fails the first test;
   reverted.
4. **The inner loop.** `-m "not slow and not golden"`: before, 4486 passed,
   11,032 warnings in 191 s (the marker did not exist); after, **4349 passed,
   148 deselected, 4 warnings in 68 s**. `slow` on five files
   (`test_train` 80 s, `test_dixon_coles` 19 s, `test_estimation_noise` 9 s,
   `test_minutes` 7 s, `test_v7b_driver` 6 s; next is `test_advise` at 3.4 s).
   Five `filterwarnings` entries by message, each with its reason:
   `LpVariable.dicts` 10,927, `LpProblem.constraints` mapping 96,
   `LpVariable(name, …)` 2, `PULP_CBC_CMD` 1 (all PuLP 3.3, migrate at
   PuLP 4), NumPy's array-shape deprecation 2 (from joblib's unpickler,
   ignored by module). The four left are singletons in `src/` and one test.
   The command is in `CLAUDE.md`'s block.
5. **On a clone.** `mv reports reports.off && pytest -rs test_report.py
   test_chip_sanity.py` → `27 passed`, no skip; `reports/` restored.
   `tests/data/gw2-advice.json` 7,244 bytes, three per list, all twelve
   chip rows; it carries a rival's team name and entry id already tracked in
   the golden board's inputs, and nothing else that is not. The prose
   fixture 178,290 → 118,242 bytes with three-player XIs; its Python and
   frontend readers both pass. Six drivers under `scripts/archive/` with a
   README naming each spec; two live referrers repointed.
6. **Counts.** Python 4496 (4485 + 11 golden) → **4509**: +12
   `test_cli_smoke`, +4 `test_advise_order`, −4 copies, +1 meta-rail. The
   inner loop collects 4361. Frontend 1098 untouched; `npm run check` exit 0,
   8 warnings (the v18f residual). Pins 51 / 12 / 62.

Golden gate, once at the end: **58 passed, 0 skipped in 18:02** (`-rs`; no
skip line). Routes 51, kinds 12, Config 62.

Also: task 4's orchestrator half (the isolation clears in six rails) is its
own commit `29e6690`, not folded into the pin-only commit §2.2 promised would
change nothing else. The `test_v7_model_degradation` phrase pin
`"scenario_noise.cache_clear()" in src` is about `src/` and stands.
