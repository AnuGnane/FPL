# gaffer v12 — the polish program (design)

**Date:** 2026-09-01
**Source:** `docs/superpowers/research/2026-09-01-polish-and-improvement-research.md`
**Shape:** one umbrella spec, five workstreams (W1–W5), one implementation
plan per workstream, executed back-to-back in order. Each workstream is
reviewed, gated, ff-merged to `main` and pushed before the next starts, so
`main` is shippable between workstreams and a failed gate withdraws one
stream, not the program.

**Authorization:** protected-file edits are enumerated per plan behind STOPs
in the usual way; the orchestrator holds standing authorization for this
program (user decision, 2026-09-01). Provenance comments `# v12 W<n> §<id>
(specs/2026-09-01-gaffer-v12-program-design.md)` on every authorized edit;
zero unauthorized diffs remains a gate.

**Execution:** Fable subagents for planning and implementation; the
orchestrator reviews and gates only.

## 0. Why this program

Single-GW point prediction is at its public ceiling (research doc, headline).
v12 therefore spends on: correctness of what exists (W1), signal already on
disk (W2), the decisions the solver can express (W3), the one data source
that changes what the tool can see (W4), and the interface (W5). Model work
is limited to gated ablations that ride on training runs already happening.

## 1. Conventions shared by every workstream

- **Empty states are honest.** Any view or report whose data does not exist
  yet renders a sentence saying what it is waiting for and when it will
  exist (a GW being `data_checked`, N snapshot dates, a collector run). It
  never renders zeros as if they were measurements.
- **Data-gated items get a ROADMAP checkbox** naming the condition that
  unblocks them.
- **Degradation.** Every new collector or reader gets a
  `tests/test_<name>_degradation.py` in the existing pattern: missing file,
  malformed file, empty result, partial result — each a named behaviour, none
  a crash.
- **Season guard.** Every new element-id-keyed read takes `season` and
  filters on it.
- **Atomic writes** use one shared helper (`gaffer/io.py::atomic_write`,
  new in W1) instead of the six copies of the idiom. Existing copies are
  migrated only where a workstream already touches the file.
- **Config.** New keys are added to `config.example.toml` with a comment
  and to the Settings whitelist (W5) if they are desk keys.
- **Provenance.** Every authorized edit to a protected file carries the
  provenance comment above.

## 2. W1 — hygiene

### 2.1 `gaffer backup`
- `gaffer backup [--to DIR] [--rsync TARGET]`. Tars `data/live/`,
  `reports/`, `models/` (field EO samples live in `data/live/field_eo_log.parquet`,
  so they are covered) into `<to>/gaffer-<YYYYMMDD-HHMM>.tar.gz`.
  Default `--to` is `[backup] dir` in config, falling back to
  `~/gaffer-backups`. `--rsync` (or `[backup] rsync_target`) copies the
  archive to a remote path with `rsync -a`. Keeps the last `[backup] keep`
  archives (default 14), deleting older ones **only in the local dir**.
- `scripts/com.gaffer.backup.plist` nightly at 23:45 (after prices at
  23:15). Added to the automation table in README and GUIDE.
- Health hub shows "last backup: <ts> (<size>)" from the newest archive's
  mtime, or "never" in the empty state.

### 2.2 One set of EO constants
- Canonical: `optimize/differentials.py` exports `DIFFERENTIAL_EO`,
  `ALTERNATIVE_EO`, `TEMPLATE_EO` in **fraction** units (0.30, 0.20, 0.70).
- `advise.py:461-464` deletes its own definitions and imports the canonical
  ones (authorized edit). The plan lists every reader of the three names
  and states, per reader, which unit the compared quantity is in; any reader
  that compares against a percent quantity is converted at the read site.
- Test: an import-time assertion that the three constants are in (0, 1),
  and a grep-style test that no other module defines a name ending in `_EO`
  with a numeric literal.

### 2.3 Season-guarded field EO
- `data/field.py::latest_field_eo(gw=None, *, season)` — `season` becomes
  required keyword. `load_field_eo()` gains `season` filtering. All callers
  (`routers/players.py:149` and any others the plan finds) pass
  `current_season`.
- Test: two seasons' rows in the log with overlapping element ids; the
  reader returns only the requested season's.

### 2.4 Season rollover guard
- `refresh` compares the API bootstrap's current season (derived from the
  events' deadline year pair) with `config.current_season`; on mismatch it
  exits non-zero with a message naming both values and the two keys to
  change (`current_season`, `train_seasons`).
- `meta` router exposes `season_ok: bool` and both values; Health renders a
  red banner when false.

### 2.5 `track_pens` refusal
- If every fetched row is degraded (the function's existing degraded
  marker), the tracker file is left untouched and the run logs
  `track_pens: refused to overwrite <path>: all N rows degraded`. Mirrors
  the `calibrate_noise` refusal pattern.

### 2.6 `DEFAULT_TOP_N` becomes visible
- `[optimizer] top_n = {GKP=8, DEF=22, MID=26, FWD=14}` in config; `milp.py`
  reads it (authorized edit, one line-group). Health shows the pool sizes.
  The solver trace (W5 §6.5) names any owned player who fell outside the
  pool.
- **Program-wide consequence of the 2026-09-02 ruling, and not a W2
  detail.** There is no `[solver]` section; every solver knob lives in
  `[optimizer]`, and `load_config` splats that section wholesale into
  `Config`. So a knob there is either **a real `Config` field** — which is
  what W1 makes `top_n` — or **listed in `config.NON_FIELD_OPTIMIZER_KEYS`
  and popped before the splat**, which is what W2's `price_timing` is. The
  two are mutually exclusive; the invariant is asserted in W2's tests (no
  name in that tuple is also a field). The tuple is named rather than
  derived from the field list so that a typo under `[optimizer]` — `horizen
  = 6` — still raises loudly instead of being swallowed.

### 2.7 `gaffer tidy`
- `gaffer tidy [--apply] [--older-than DAYS]` (default dry-run, 30 days).
  Targets: `data/live/backtest_log_*.parquet` not referenced by any
  `reports/*` ledger, and `logs/*.log` older than the cutoff. Dry-run
  prints the list and total size; `--apply` deletes. Never touches
  `availability_log`, `field_eo_log`, price log, or any ledger.

### 2.8 LAN write protection
- When `ui --lan` is used, every non-GET route requires header
  `X-Gaffer-Token: <token>` where token comes from `[web] token` or, if
  unset, is generated at startup and printed once. Localhost without
  `--lan` is unchanged. Front end reads the token from a `?token=` query
  parameter on first load and stores it in `localStorage`.

### 2.9 "As of" strip
- One component rendered at the top of every hub: last refresh, last odds
  fetch, last field scrape, last advise, last backup — each with age
  colouring (green < 1d, amber < 3d, red otherwise, grey for "never"). Data
  from a single `/api/meta/freshness` endpoint (new) that reads file
  mtimes and the ledgers' latest timestamps.

### 2.10 MCP server
- `gaffer mcp` runs a stdio MCP server (python `mcp` package, added to
  dependencies). Tools, each a thin wrapper over the existing router
  function with the same pydantic response models:
  - `projections(gw?, position?, team?, top?)`
  - `explain(code)` — the player explain payload
  - `whatif(transfers_in, transfers_out, chip?)` — read-only solve preview
  - `ledger(gw?)` — the advice ledger rows
  - `freshness()` — §2.9's payload
  - `health()`
- No write tools in v12. A `README` section documents adding the server to
  Claude Code (`claude mcp add gaffer -- gaffer mcp`).
- Test: each tool's schema round-trips and each returns the router's
  payload on a fixture state.

### 2.11 `gaffer/io.py::atomic_write`
- One helper (`tmp` in the same dir, `os.replace`). The six existing copies
  are migrated in W1 (this is the one place the "only where touched" rule
  is waived, so the helper has real callers from day one).

**W1 gate:** suite green; zero unauthorized protected diffs; `gaffer backup`
produces an archive that restores (test extracts and diffs a fixture tree);
`refresh` against the live API passes the rollover guard.

### G1 — suites, rails, pins (measured by the implementer)

- [x] `.venv/bin/pytest -q` — **3356 passed** (branch baseline 3193 + 163 new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — **680 passed, 1 skipped** (baseline 655 + 25 new)
- [x] `npm run build` — clean
- [x] Protected diff is exactly the authorized STOPs and nothing else:
      `advise.py` (§2.11 write, §2.2 constants), `optimize/differentials.py`
      (§2.2), `optimize/milp.py` (§2.6), and the ten protected test files of
      §2.3 and the pin restructure. Every line-group carries its `# v12 W1 §`
      provenance comment (four in the three source files). `set_pieces.py`,
      `web/jobs.py`, `routers/whatif.py`, `test_advise.py`, `test_odds.py`,
      `test_web_jobs.py` and `s2_replay.py` show zero diff — `whatif.py` is
      imported by the MCP server and not edited
- [x] Pins: job kinds still 12, **OpenAPI paths 45 → 46**
      (`/api/meta/freshness`, the cycle's only route), **config fields
      48 → 53** (`backup_dir`, `backup_rsync_target`, `backup_keep`, `top_n`,
      `web_token`)
- [x] Exactly one file in the suite pins each absolute count: routes in
      `test_v11_degradation.py`, config fields in `test_v12_w1_degradation.py`
- [x] `os.replace` census: nineteen of twenty copies migrated; the survivors
      are `gaffer/io.py` and `gaffer/journal.py` (import-only) — asserted by
      name as an equality so a twenty-first cannot appear quietly. `backup.py`
      streams a tarball rather than handing over bytes and so looked like a
      case the helper could not serve; `atomic_path` yields the temp path and
      serves it exactly
- [x] Rails: a failed write leaves the previous file intact in all three
      families; a bare `latest_field_eo()` is a `TypeError`; `season_ok` is
      `None` and not `False` on a clone with no events; `track-pens` refuses
      to overwrite a good report with an all-degraded or empty one, and writes
      freely when nothing is banked; `tidy` never names the shared backtest
      log, an S2 arm log, a corpus log or `advise.log`; `backup` writes no
      file rather than an empty archive; a LAN write without the header is a
      403 and a GET is not; `/api/meta/freshness` is five rows of "never" on a
      cold clone and never 0.0; every MCP tool answers `{"error": …}` rather
      than raising
- [x] Empty states: the freshness strip renders five grey rows on a rejecting
      fetch rather than disappearing; the Health season banner draws on
      `false` alone and not on `null`
- [x] 390px holds tree-wide with the new strip on every hub

### G1 — the gate's own two (spec §2)

- [x] `gaffer backup` produces an archive that restores: extracted into an
      empty tree and diffed against `reports/`, clean. (The plan's
      `pytest -k restore` selects nothing — the test is named
      `test_the_archive_extracts_to_a_tree_that_matches`; `-k "restore or
      extracts"` is the working selector.)
- [x] `gaffer refresh` against the live API passes the rollover guard. **Run
      by the orchestrator, 2026-09-02, on the dev tree** — not by the
      implementer: `refresh` writes into `data/`, which this cycle's staging
      rule forbids touching, and a network round trip is not something a build
      step should decide to make. The matching season refreshed **1236 rows**;
      a deliberately mismatched `current_season` was refused with exit 1 and
      the two-key remedy message. The guard's disk-side behaviour is covered
      by `tests/test_v12_season_rollover.py`. A refusal here means either the
      guard is wrong or `config.toml` genuinely names the wrong season —
      check which before "fixing" anything.

### G2 — review and merge (orchestrator only)

- [ ] Adversarial review, fix-first, re-verify.
- [ ] Merge ritual: ff-only, push, `git show main:config.toml` fails, key-grep
      empty — including the generated LAN token.

### No replay — recorded reasoning

W1 changes no feature, no model, no head and no objective term. The two items
that touch the decision path are `optimize/milp.py`'s `build_pool` default —
which reads the same four numbers from config instead of from the module, and
falls back to the module on anything unreadable, so a tree with no `[optimizer]
top_n` key solves byte-identically — and §2.2's EO constants, whose only readers
are annotation tables (`captain_table`, `transfer_alternatives`, `threat_board`)
and `transfer_tag`, none of which the optimizer consults. `differentials.py`'s
own docstring is the argument: *"This module annotates, it never decides."*

A replay would therefore compare two identical arms, which is v10's G2, v10b's
G2 and v11's G2 for the fourth time. **If the orchestrator wants one anyway, the
place to spend it is §2.6**: an `[optimizer] top_n` typo is the one change in W1
that could move a plan, and the rail that a missing section reproduces
`DEFAULT_TOP_N` exactly is the cheaper version of the same check.

### Live spot-checks (orchestrator, on the dev server)

- [ ] Every hub draws the "as of" strip, once, with five sources; a source with
      no file reads "never" in grey rather than "0h".
- [ ] `gaffer ui --lan` prints a token; a phone opened by scanning the QR (which
      now carries `?token=`) can star a watchlist player, and the same phone
      opened from the bare printed URL gets the 403 sentence rather than a
      silent failure.
- [ ] Model → Health shows the solver pool sizes with their caption, the last
      backup with its size and its UTC stamp, and — on a machine whose
      `config.toml` names the right season — no red banner. Editing
      `[optimizer] top_n` and reloading shows the new numbers without a
      restart.
- [ ] `claude mcp add gaffer -- gaffer mcp`, then ask Claude Code for the top
      five midfielders and for `health` on a tree with no advice: the first
      answers, the second answers, and neither kills the subprocess.
- [ ] `gaffer tidy` names five files and 54 KB. `gaffer backup` writes ~16 MB.

## 3. W2 — mine what we have

### 3.1 Flag-latency report
- Reads `availability_log.parquet` (columns include `season, gw, snap_date,
  code, status, chance_of_playing, llm_verdict, source`). For each
  (code, gw) whose status changed at least once before the deadline,
  compute days between the first change and the deadline, and whether the
  player then started (from the checked GW's minutes). Output: histogram of
  lead days by outcome; a table of the 20 worst "late flags" (started ≠
  final status).
- Surface: Model → Quality, new "Availability signal" section. Empty state
  until `snap_date.nunique() >= 14` **and** at least one covered GW is
  `data_checked`; the state says both numbers.
- CLI: `gaffer evaluate --flag-latency`. Snapshots taken after the
  gameweek's deadline are excluded — the log stamps a snapshot with
  `next_unfinished_gw`, so a Saturday row carries a gameweek whose deadline
  has passed. The payload lands in `reports/evaluation.json` under
  `flag_latency` rather than in a file of its own.

### 3.2 Presser-verdict grading
- Same section. For each row with a non-null `llm_verdict` (`source` names
  the news source, not the classifier — 160 of the live log's 169 verdict
  rows say `premierinjuries`; verdict classes today: `ruled_out`, `assess`,
  `knock`, `rotation_risk`), grade against the checked GW's start.
  Output: confusion matrix and precision/recall per verdict class. Shares
  `evaluate_news_shadow`'s actuals loader. Empty state until a
  `data_checked` gameweek carries a verdict banked before its deadline; GW2
  is checked and carries none.
- ROADMAP checkboxes: news-shadow (existing), flag-latency (14 dates),
  presser grading (a checked gameweek with a pre-deadline verdict — GW3 is
  the first candidate).

### 3.3 EO trend
- The trend is measured **gameweek to gameweek**, not day to day (plan A4,
  three measured reasons: `run_field_scrape`'s already-banked exit means one
  sample per gameweek; picks are frozen after the deadline, so a
  same-gameweek delta would be sampling noise; and EO is banked in percent
  with captaincy doubled, so the live maximum is 214.7). New reader
  `field_eo_trend(season, gw)` compares the latest sample of `gw` against
  the latest sample of the newest *earlier* gameweek and returns per-code
  `eo_first`, `eo_last`, `delta`, `gws_between` and `trend_available`.
  `deadline_eo = clip(eo_last + delta / gws_between, 0.0, 200.0)` — one
  gameweek forward, in **percent**, clamped at the ceiling the sampler can
  produce, not the spec's original [0, 1]. `hours_between` is not kept:
  `snap_date` carries no clock, so an hours figure would be fabricated.
  With fewer than two gameweeks in the log, `trend_available=False` and
  `deadline_eo == eo_last`.
- The EO lens on This Week and the captain table use `deadline_eo`; the
  UI shows an arrow (↑/↓/→) with the delta on hover. Rank tilt (λ) is
  unchanged.

### 3.4 Price-timing term
- The nightly price log plus the official predictor reading give, per
  owned player, `p_fall_tonight`. In the objective, a transfer-out of a
  player scheduled for a *later* GW in the horizon is charged
  `p_fall_tonight × 0.1 × itb_value` (authorized edit in `milp.py`,
  one term). No term for rises (rejected: price chasing). The term is worth
  `p × 0.1 × itb_value` — 0.008 points at the shipped `itb_value` — which is
  below the solver's default relative gap on a full horizon. It is a
  tie-breaker for equal sell timings and the replay is expected to show no
  diff. Config **`[optimizer] price_timing = false`**: the section by the
  program ruling of 2026-09-02 (there is no `[solver]`; solver knobs live in
  `[optimizer]`), the default by CONVENTIONS §6, with the flip rule
  pre-registered in the W2 gate.
- Test: with `p_fall_tonight = 1` and two otherwise-equal sell timings,
  the solver sells this week.
- Freshness (found at the W2 gate, 2026-09-02): `price_falls` drops the whole
  log when its newest banked day is not today, so the term has a **live
  window** — a reading banked on UTC day D predicts the change in the night
  D→D+1 and is stale from the next UTC midnight, at which point the table is
  empty by design. With the bank running once nightly at 23:15 local, that
  window was roughly 22:15 UTC to midnight UTC, and the scheduled Thursday
  `advise` at 18:00 local always read the previous day's log — the term was
  `{}` on every scheduled solve. **The first G1d replay was vacuous for this
  reason**: it came back byte-identical to `main` not because the term makes
  no difference but because the term never existed in it, and it was re-run
  after `gaffer prices` banked the day's reading. Fixed forward in
  `scripts/com.gaffer.advise.plist`, which now runs `gaffer prices` before
  `train` (`;` and not `&&`, so a failed fetch never costs the week its
  advice; `bank_prices` is keyed on `snap_date`, so the 23:15 run replaces
  the afternoon reading rather than doubling it). **Residual:** the web UI's
  advise button does not bank first, so a browser-started solve during the
  day still gets an empty table and an untimed sale — the pre-v12 behaviour,
  recorded rather than fixed, since a fetch on the advise path is a new job
  kind and W2 adds none.

### 3.5 xG-per-shot ablation
- Feature `us_npxg_per_shot = us_npxg90 / us_shots90` (0 when shots = 0,
  with a missing indicator). Added behind `[model] xg_per_shot` (default
  off). Gated ablation on the next `train`: kept (default on) only if the
  hauler bucket RMSE improves and no other bucket worsens by more than its
  seed-spread. Recorded in the model quality table like prior arms.

**§3.5 outcome (run 2026-09-02 on `feat/gaffer-v12`, `scripts/v12_xgps_arm.py`,
K=3 seed bases; both arms fit under the ensemble hyperparameters, so the v8a
sanity figure is not expected to reproduce). Verbatim driver lines:**

```
V12_ARM_LEVER ok
V12_ARM_DONE baseline 20260901 {"zeros": 1.064, "blanks": 1.677, "tickers": 1.654, "haulers": 5.198, "all": 1.971, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_ARM_DONE xg_per_shot 20260901 {"zeros": 1.059, "blanks": 1.667, "tickers": 1.613, "haulers": 5.219, "all": 1.97, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_ARM_DONE baseline 20260902 {"zeros": 1.06, "blanks": 1.672, "tickers": 1.63, "haulers": 5.217, "all": 1.972, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_ARM_DONE xg_per_shot 20260902 {"zeros": 1.067, "blanks": 1.67, "tickers": 1.641, "haulers": 5.198, "all": 1.97, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_ARM_DONE baseline 20260903 {"zeros": 1.065, "blanks": 1.671, "tickers": 1.65, "haulers": 5.206, "all": 1.971, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_ARM_DONE xg_per_shot 20260903 {"zeros": 1.064, "blanks": 1.676, "tickers": 1.676, "haulers": 5.191, "all": 1.97, "rows": 26919, "haulers_n": 2324, "zeros_n": 16279}
V12_VERDICT xg_per_shot {"seed_bases": [20260901, 20260902, 20260903], "base_mean": {"zeros": 1.063, "blanks": 1.67333, "tickers": 1.64467, "haulers": 5.207, "all": 1.97133}, "arm_mean": {"zeros": 1.06333, "blanks": 1.671, "tickers": 1.64333, "haulers": 5.20267, "all": 1.97}, "control_spread": {"zeros": 0.005, "blanks": 0.006, "tickers": 0.024, "haulers": 0.019, "all": 0.001}, "delta": {"zeros": 0.00033, "blanks": -0.00233, "tickers": -0.00133, "haulers": -0.00433, "all": -0.00133}, "regressions": {}, "decision": "keep"}
```

Reading, against the pre-registered rule above: the hauler bucket improved
(5.207 → 5.20267, Δ −0.00433) and no bucket worsened by more than its control
spread (`regressions: {}`), so the rule says **keep → `[model] xg_per_shot`
default on**. The honest caveat, recorded so nobody reads it as a win later:
the hauler delta is 0.23× the control spread (0.019) and every bucket's delta
is inside its spread — the arm is *indistinguishable from the baseline*, and
the flip is the rule's verdict on "no regression", not a measured gain. The
flip lands only with the fix for the serving-frame defect the W2 final review
found (the prediction frame did not build the columns; a flag flipped on
before that fix would have crashed `advise`) and takes effect on the next
`gaffer train`.

**Overturned by the replay, same day.** The G1d replay was re-run once the
first branch run turned out to be vacuous (§3.4 freshness bullet), and its
totals moved: the branch scored `[1874, 1834, 1799]` (mean 1835.7, spread 75)
against `main`'s `[1854, 1875, 1862]` (mean 1863.7, spread 21) — −28 on the
mean, outside the control spread, with the seed spread tripled. Two isolation
runs attributed it: with only the price term live the branch was byte-identical
to `main` (`[1854, 1875, 1862]`, hits `[18, 12, 18]` both sides); with only the
xG-per-shot head on it reproduced the −28 exactly (`[1874, 1834, 1799]`, hits
`[12, 17, 17]`). The backtest refits through `train_all → attacking_features()`,
so the head was a lever in the replay that the §3.5 rule never asked about.
**Verdict: the keep is withdrawn; `[model] xg_per_shot` ships `false`** with
these numbers (CONVENTIONS §6). Lesson for the ledger, alongside "estimation-σ
≠ outcome variance": a bucket-RMSE rule with no replay half is under-specified —
the outcome measure decides, and the next arm rule names both halves before it
runs. `raw`/`arm` logs: `logs/v12_xgps_arm.log`, `logs/v7b_v12w2-{main,price,xgps,both}.log`,
reports `reports/v7b_v12w2-*-s2026090{1,2,3}.json`.

**W2 gate:** suite green; §3.4 replay tolerance 5 vs main (the S1 rule);
§3.5 pre-registered outcome recorded either way; empty states verified
by test with an empty log.

**W2 gate — results (filled by the orchestrator).**

| # | Gate | Command | Result |
| --- | --- | --- | --- |
| G1a | Suite green | `.venv/bin/pytest -q` | ✅ 3467 passed (2026-09-02, at 754e1d1) |
| G1b | Frontend green + types | `cd frontend && npx vitest run && npx tsc --noEmit` | ✅ 686 passed, 1 skipped; tsc clean |
| G1c | Zero unauthorized protected diffs | `.venv/bin/pytest -q tests/test_v12_w2_degradation.py -k protected` and `git diff --stat <base> HEAD -- src/gaffer/optimize/` | ✅ only `milp.py` (+32/−1, the three authorized hunks) over ef8c5f3..754e1d1 |
| G1d | §3.4 replay, tolerance 5 vs `main` at the base commit, K=3 seed bases (CONVENTIONS §1), run with `price_timing = true` in the local `config.toml` — the shipped default is off and a replay of the off arm would be a replay of `main` | `scripts/v7b_replay.py --seed-bases 20260901,20260902,20260903` on each side, then `scripts/seed_stats.py` | ✅ **no diff**: `main` `[1854, 1875, 1862]` mean 1863.7 spread 21, hits `[18, 12, 18]`; branch with the term live (`price_timing = true`, `xg_per_shot = false`, same-day price log, 34 of the replay's transferred players carrying `p_fall > 0`) `[1854, 1875, 1862]`, hits identical. The first branch run was vacuous (stale log → empty table) and is recorded in §3.4's freshness bullet; the run with the xG head on is recorded in §3.5 |
| G1e | Empty states verified against an empty log | `.venv/bin/pytest -q tests/test_v12_w2_degradation.py` | ✅ 15 passed |
| G1f | Pins unmoved | the three-line measurement in the plan header | ✅ routes 46 / JOB_KINDS 12 / Config fields 53 |
| G2a | §3.5 outcome recorded either way (CONVENTIONS §6: a failing arm ships OFF with its numbers) | `caffeinate -i .venv/bin/python scripts/v12_xgps_arm.py`, then transcribe every `V12_ARM_DONE` and the `V12_VERDICT` line into spec §3.5 verbatim (CONVENTIONS §4) | ✅ transcribed; arm said keep, the replay overturned it — ships **off** with its numbers (§3.5) |
| G2b | Adversarial review → fix round → re-verify | | ✅ three rounds; the last found the serving-frame defect (bf21ce2), the ensemble head mix (e77a5b0), the deadline-day snapshot leak (9d54c7b), the midnight cache (b9092ed); re-verify approved, four minors tidied (baede07) |
| G3 | Post-merge ritual | `git show main:config.toml` fails; `git log -S<odds key> --all` is empty | ✅ merged `865f8dc` (2026-09-02); both checks clean |

**G1d is expected to show no diff at all**, and that is the pre-registered
prediction rather than a pass by luck: the price-timing charge is 0.008 points
at the shipped `itb_value` and the solver's default relative gap on a full
horizon is larger (plan A6). A replay that *does* move by more than the seed
spread is the surprising outcome and should be investigated before it is
accepted.

**The §3.4 flip rule, pre-registered here before the arm runs (CONVENTIONS
§2), per the coordinator's 2026-09-02 ruling.** `price_timing` ships `false`;
the default is changed to `true` in `config.example.toml` **iff** the
`price_timing = true` replay clears both halves:

> **FLIP iff** the on-arm's mean total is within the control's seed spread of
> the off-arm's mean (no regression: the term must not cost points), **and**
> hits are not up by more than 3 over the three bases.
>
> A *gain* is not required and must not be read as one. The term is 0.008
> points; any total difference in either direction is seed noise by
> construction, and the flip is a judgement that a correctly-signed cost with
> no measurable downside belongs on, not a claim that it won anything.

If the on-arm regresses beyond the spread, the flag stays `false` **and the
numbers are transcribed into spec §3.4 anyway** — CONVENTIONS §6: deleting a
failed arm loses the measurement that cost the hours.

**Applied 2026-09-02:** both halves cleared — the on-arm equalled the off-arm
total for total and hits for hits across all three bases — so `price_timing`
**flips to `true`** in `config.example.toml` and in the reader's default. It
is what the rule said it would be: a correctly-signed tie-breaker with no
measurable downside, not a gain.

## 4. W3 — decide

All of W3 is in `optimize/**` and `advise.py` (protected); each item is an
enumerated authorized edit.

### 4.1 `force_out`
- `SolveInput.force_out: list[int]` (codes). Constraint: each listed owned
  player has squad membership 0 from the first GW of the horizon. Distinct
  from `locked_out` (cannot be bought). Schema field on the what-if
  request; What-if and the planner board expose "must sell" on an owned
  player's row; the ledger records it.
- Infeasible (e.g. force_out with no affordable replacement) returns the
  existing infeasibility payload naming the constraint.

### 4.2 θ is the only chip decision
- `chips.py:46,60` flat thresholds are kept only as `flat_thresholds()`'s
  source; `advise.py:735` already uses `chip_thresholds_from_asset`. The
  change: wherever a flat threshold is consulted while θ is available, use
  θ; the chip caption states `threshold: θ (v4c)` or `threshold: flat
  fallback` and why (no priors asset, GW outside window).
- Test: with a priors asset present, no code path reads the flat values.

### 4.3 Top-3 distinct plans
- After the first solve, add a no-good cut on the set of transfer
  (in, out, gw) triples of the incumbent and re-solve; repeat to 3 plans
  or until the EP gap exceeds `[optimizer] alt_plan_max_gap` (default 2.0 pts
  over the horizon). Returned as `Plan.alternatives: list[Plan]` with
  `gap`. Board shows them as tabs "Plan A / B / C" with the gap and the
  differing moves highlighted. Sweep frequency tables are computed on plan
  A only (unchanged).

### 4.4 Availability-aware sweep
- `run_scenarios` gains a per-scenario availability draw: for each
  (code, gw), `available ~ Bernoulli(p_play)`; unavailable → EP 0 for
  that GW. Noise on EP is then applied as today conditional on available.
  Config `[scenarios] draw_availability = true`. `move_frequencies`
  unchanged; the UI's "bought in N%" now reflects availability risk.
- Gate: scenario support for the live captain must not fall below its
  current value by more than 10 points on the same inputs (S1 recorded a
  collapse 92% → 22% as the failure signature — this is the check).

### 4.5 Chip pairs and a real Free Hit
- `evaluate_chips` evaluates WC+BB (wildcard in GW g, bench boost in
  g+k, k ≤ horizon) as one option whose surplus is the joint solve minus
  baseline; shown as a single row "WC gN + BB gM". Only when a DGW is in
  the horizon (from `load_chip_scenarios`).
- `free_hit_gain` becomes a true re-solve: one-GW unconstrained squad for
  the FH week under the current budget (selling at sell prices), scored
  against the baseline's week. The approximation path is removed.

### 4.6 DGW captain
- Captain choice in a DGW uses the two-fixture point distribution (sum of
  the two fixtures' EP with the existing σ) — the disclaimed "ranking"
  number and its caption are removed.

**W3 gate:** 2025-26 gated replay, identical seeds, vs `main` at the
workstream's base commit: total points within tolerance 5, hits not up by
more than 3. §4.4's support check. Zero unauthorized diffs.

### W3 G1 — suites, rails, pins (measured by the implementer)

Measured on `feat/gaffer-v12-w3` at `ff2fa0e`. The comparison base is
`754e1d1` — W2's tip, which is where this branch was cut — and **not**
`merge-base(HEAD, main)`: W2 has not merged yet, so "since main" would score
W2's diff under W3's name. The audit rail in
`tests/test_v12_w3_degradation.py` pins the same base for the same reason.

- [x] `PYTHONPATH=src .venv/bin/pytest -q` — **3588 passed, 10 skipped**
      (3598 collected; branch baseline 3468 collected at `754e1d1`, + 130 new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — **703 passed, 1 skipped** across 72 files
      (baseline 686 + 1 skipped across 71 files, + 17 new)
- [x] `npm run build` — clean (965 modules, 846.52 kB / 238.42 kB gzipped)
- [x] Protected diff is exactly the seven authorized source files
      (`advise.py`, `optimize/milp.py`, `optimize/chips.py`,
      `optimize/chip_policy.py`, `optimize/scenarios.py`,
      `optimize/differentials.py`, `web/routers/whatif.py`) plus **four**
      authorized test files, not one: `tests/test_v10_degradation.py` (Task 8,
      the narrowed T10-A rail), and three orchestrator rulings of 2026-09-02 —
      `tests/test_advise.py` (the EO rail pinned a call's *spelling* rather
      than its claim; the closing paren was dropped),
      `tests/test_v12_w2_degradation.py` (W2's audit rail was scoped "since
      main" and fails on any later cycle's first protected commit; re-pinned
      to `ef8c5f3..754e1d1` at 7e1645f), and
      `tests/test_v12_w1_degradation.py` (the config pin's move, below).
      `set_pieces.py`, `web/jobs.py`, `test_odds.py`, `test_web_jobs.py` and
      `s2_replay.py` show **no diff at all**, and every authorized hunk
      carries `# v12 W3 §…` — 46 provenance lines across the six enumerated
      source files and the v10 rail
- [x] Pins: job kinds 12 → 12 (`job_kinds.py` shows no diff at all), routes
      **46 → 46** (45 at the program's spec commit; W1 §2.9 spent the one on
      `GET /api/meta/freshness`), config fields **53 → 55**
      (`alt_plan_max_gap`, `draw_availability`; 48 at `27f7933`, 53 after W1
      and W2). `git diff 754e1d1 -- src/gaffer/config.py config.example.toml`
      is exactly the two fields and their two documented keys
- [x] **The suite's absolute config-field pin moved to
      `tests/test_v12_w3_degradation.py`** (orchestrator ruling, 2026-09-02).
      A single number that every key-adding cycle must move belongs in the
      newest cycle's file; W1 keeps the by-name claim about its own five keys,
      and its rail-on-the-rail now names W3's file. The *route* total did not
      move with it — it stays in `tests/test_v11_degradation.py`, because W3
      adds no route and moving it would be a protected edit that bought
      nothing
- [x] LP golden: an empty `force_out`, an absent `no_good` and a bank read off
      a solved variable each build the pre-change model byte for byte
      (`tests/data/v12_w3_milp_golden.lp`, captured before the first edit to
      `milp.py`; re-run from Tasks 1, 5, 10 and 12)
- [x] Rails: no priors asset → every bar flat and every source says which kind
      of flat; no `chip_scenarios.toml` → no pair row and a five-column table;
      the availability draw off → the pre-v12 sweep on a fixed seed; no
      components frame → the captain ceiling stays `p_haul` and says why, and
      a captain with no band is an em dash rather than `0%`; an artifact with
      no `alternative_plans` → an empty tab strip and a full timeline
- [x] Security ritual (CONVENTIONS §8): `git diff 754e1d1 HEAD` names no
      `data/`, `reports/`, `models/`, `logs/`, `config.toml` or
      `web/static/` path (asserted by a rail, not only by eye);
      `git show main:config.toml` fails; the only `api_key` in the diff is
      `config.example.toml`'s commented placeholder

### W3 G2 — the gates (orchestrator only)

**Pre-registered rules, written before any arm ran.**

- [x] **The replay.** Three seed bases a side, branch against a re-run `main`
      (CONVENTIONS §1 — a banked number from an earlier cycle is not a valid
      comparison), run in the main tree after W2 has merged:

      ```bash
      mkdir -p logs
      caffeinate -i nohup bash scripts/replay_pair.sh v12w3 \
        > logs/v12w3_replay.log 2>&1 &
      grep -e V7B_ARM_DONE -e MULTISEED_DONE logs/v12w3_replay.log
      ```

      `SEEDS` defaults to `1876,1901,20260827`; both sides run
      `scripts/v7b_replay.py --arm heur --n 40 --chips`, differing only in
      `--tag`, which `scripts/seed_stats.py` verifies before it will
      aggregate. **One seed convention per write-up** — either the driver's
      default above or W2's `20260901,20260902,20260903`, named in the
      result, never a mixture.

      **Both sides at the shipped defaults, and `config.toml` identical
      between them.** The backtest refits through `train_all` →
      `attacking_features()`, so `[model] xg_per_shot` is a live lever on this
      replay; the price term is `{}` with `price_timing = false`, which is the
      fair comparison for §4.5. So: remove any `price_timing` or `[model]
      xg_per_shot` override from `config.toml` **before either side runs**,
      keep the file byte-identical across the two runs, and **state the values
      actually in force in the write-up**. A pair of arms run under two
      configs measures the config.

      **Verdict:** the branch mean total is within **5** of the main mean, and
      the branch mean hits are not more than the main mean **+ 3** (spec §4).
      Read against the seed spread, which v7b measured at 116 points on one
      arm — a delta inside the spread is a seed, not a change.

      **What this gate can see, pre-registered so the result is not
      re-interpreted afterwards:** `backtest.py` reaches exactly one W3
      change, `free_hit_gain` (via `evaluate_chips`). `force_out` is never
      set, θ was already wired into `_pick_chip`, the alternatives are
      computed in `advise`, the availability draw needs a `p_play` the
      replay's gate does not pass, and the chip pair needs a `dgw_gws` no
      caller but `advise` supplies. **So this is a measurement of §4.5 and a
      no-regression check on the other five** — v10's G2, demoted the same way
      and for the same kind of reason.

      **Result (run 2026-09-02, seeds `20260901,20260902,20260903`, both sides
      in the main tree with `config.toml` byte-identical: `price_timing = false`
      pinned explicitly, `xg_per_shot = false` and `draw_availability = false`
      at their then-shipped defaults; `scripts/replay_pair.sh` was not used —
      its main side imports the branch's `src` through the editable install —
      so each side ran from its own checkout, `main` at `865f8dc`, the branch
      detached at `63dc9fb`):**

      ```
      MULTISEED_DONE v12w3-main   {"totals": [1854, 1875, 1862], "mean": 1863.7, "spread": 21,  "seed_bases": [20260901, 20260902, 20260903]}
      MULTISEED_DONE v12w3-branch {"totals": [1798, 1917, 1872], "mean": 1862.3, "spread": 119, "seed_bases": [20260901, 20260902, 20260903]}
      ```

      Hits `main` `[18, 12, 18]` (mean 16.0), branch `[15, 12, 13]` (mean
      13.3). **Both halves clear: −1.3 on the mean (tolerance 5), hits down,
      not up.** The lever did exactly what was pre-registered and nothing else:
      `main` plays the free hit once (GW33 on every seed); the branch plays it
      in both halves (GW18+25, GW13+29, GW18+31), because the hits credit lifts
      its gain over `_pick_chip`'s floor on weeks the baseline paid for
      transfers. The honest caveat is the spread: 21 → 119. A chip-timing
      change is the highest-variance thing this harness measures, and K=3
      cannot say whether an earlier free hit is worth anything — only that the
      mean did not move. **Ships as built.** If anyone wants the sign, the next
      measurement is a K=10 run of §4.5 alone; it is not in this program.

- [x] **The captain-support check (§4.4).** On the live board, after an
      `advise` run:

      ```bash
      mkdir -p logs && caffeinate -i nohup .venv/bin/python \
        scripts/v12_w3_support.py > logs/v12_w3_support.log 2>&1 &
      grep -e W3_SUPPORT_LEVER -e W3_SUPPORT_DONE logs/v12_w3_support.log
      ```

      **Verdict:** `drop_pts <= 10`. The number is S1's failure signature —
      captain support 92% → 22%, after which the gate found no move clearing
      threshold and advised a plan carrying −20 in hits — watched for by name.
      A `W3_SUPPORT_LEVER` line must appear first; without it the run measured
      two identical arms and is void.

      **The arm was built OFF and this gate is what turns it on** (CONVENTIONS
      §6, orchestrator ruling 2026-09-02). The gate ran before the merge with
      `[scenarios] draw_availability = false` and `Config.draw_availability =
      False` in the tree, so no user's advice had drawn availability at the
      moment it ran; the flip landed on the branch afterwards and merges with
      it.

      **If it passes:** flip four things in one commit — the `Config` default,
      the `load_config` default, `config.example.toml`, and the two
      expectations in
      `tests/test_v12_w3_availability.py::test_the_config_key_defaults_off_and_reads_from_the_scenarios_section`
      / `::test_the_shipped_default_leaves_the_advice_path_on_the_pre_v12_sweep`
      — and record the measured `support_off` / `support_on` / `drop_pts` in
      this spec beside the rule.
      `tests/test_v12_w3_degradation.py::test_the_shipped_default_is_off_and_the_advice_run_passes_no_p_play`
      moves with them.

      **If it fails:** it stays off, and the negative result is recorded here
      anyway. Deleting the arm loses the measurement that cost the hours; the
      feature stays in the tree, stays tested, and stays off.

      **Result (run 2026-09-02 on the GW3 board, seed 20260828, n=40):**

      ```
      W3_SUPPORT_LEVER {"priced": 219, "covered": 219, "blanked_one_draw": 15}
      W3_SUPPORT_DONE {"gw": 3, "captain": 209036, "seed": 20260828, "n": 40, "support_off": 60.0, "completed_off": 40, "support_on": 52.5, "completed_on": 40, "drop_pts": 7.5, "passes": true}
      ```

      Lever verified first (219 of 219 priced players carry a `p_play`, 15
      blanked on one draw), then captain support 60.0 → 52.5 with every
      scenario completing on both arms: drop 7.5 against the ceiling of 10.
      **Passed → flipped** (`cd78254`): `Config.draw_availability = True`, the
      `load_config` default, `config.example.toml`, and the three tests named
      above. What the number is not: one board, one gameweek, one seed — and
      the replay is blind to this lever, so the live board is where it shows.
      `raw_optimum_agrees` will now read `False` more often (residual 2).

- [x] Zero unauthorized protected diffs (G1's audit, re-run on the merge —
      `pytest -q tests/test_v12_w3_degradation.py -k protected`; the base pin
      moved to `865f8dc` with the rebase, which is the merge-base, and the rail
      skips rather than lies if the SHA is unreachable).

**Residuals for the G2 write-up, recorded before it runs.**

1. **Re-score the alternatives under the incumbent's own `_decision_scales`.**
   §F1's second pass takes each plan's bench and vice coefficients from the
   plan it has just solved, so the incumbent and each alternative are scored
   under coefficient sets derived from different XIs. A small `Plan.gap` of
   either sign can be that rather than a real difference between the plans.
   `Plan.gap`'s docstring and the board's caption both name it and neither
   attributes a negative gap to the coherence constraint alone; the fix is not
   in W3.
2. **`raw_optimum_agrees` reads `False` more often** once §4.4 is switched on,
   because the sweep models a risk the raw solve does not. Information rather
   than instability (plan A6) — and a reason to re-read that line's wording on
   the report if the arm passes.
3. **The free hit still excludes horizon effects.** Pricing them needs a
   two-branch horizon solve; §4.5 asked for a true re-solve of the FH *week*,
   which is what shipped, and the docstring keeps the third approximation.
4. **The alternatives cost one MILP solve each on every weekly advise run** —
   up to four when `p_play` is informative, because §F1 solves twice — with
   `[optimizer] alt_plan_max_gap = 0` as the free off switch.

### W3 G3 — review and merge (orchestrator only)

- [x] Adversarial review, fix-first, re-verify — six review rounds across the
      workstream (T1–3, T4–7, T8–11, whole-W3, two re-verifies). The whole-W3
      pass found §4.6 undelivered in production: the banding call was handed
      the components frame, which has no `ep`, so the captain ceiling silently
      stayed `p_haul` under a stronger label, and a source-spelling test had
      pinned the bug. Fixed by banding the frame `save_components` already
      builds (`b8764f1`), the report header made conditional (`597e1a0`), and
      every W3 `in src` rail given a behavioural sibling or a stated reason
      (`63dc9fb`). Earlier rounds: the `renderBoard` fixture that did not
      exist, the golden LP that read the live price log, the plan's `kw` dict
      that would have deleted W2's term, D1 reverting W1's EO fix, `nan%` in
      the captain table, the pair judged against the single-chip bar, the
      gap computed across two objective frames when the sweep fails.
- [x] Merge ritual: ff-only into `main` at `3f4dfd2` (2026-09-02), pushed;
      `git show main:config.toml` fails; the key-grep over all history is
      empty; the protected audit re-run on the merge passes. Suite at the
      merge: **3614 Python / 706 frontend**, tsc clean; pins routes 46 /
      JOB_KINDS 12 / Config fields 55.

### W3 live spot-checks (orchestrator, on the dev server)

- [ ] Planning → Board: "Try these changes" lands on What-If with the week's
      sells in **Must sell** and its buys in Force in, `ban` empty, and the
      sentence under the button no longer says a sell rules out buying him
      back.
- [ ] What-If: a Must sell on a player you do not own is refused inline with
      "use ban"; on a free hit it is refused as "nothing to force out".
- [ ] Planning → Board: with alternatives banked, Plan A / B / C switch, the
      gap sentence names objective points, and the moves that differ from Plan
      A are marked. With none banked, no strip is drawn at all.
- [ ] Planning → Chips: every bar carries θ or `flat`, and "Wildcard now"
      names the bar its verdict was decided against — the two must agree about
      the wildcard, which before this cycle they did not.
- [ ] The chip table shows **no** `Wildcard + Bench Boost` row on today's
      fixture list, which is the correct empty state and not a bug.
- [ ] The HTML report's captain table reads `P(10+ pts)`, a candidate with no
      band reads as an em dash rather than 0%, and the alternatives table below
      still reads `P(2+ returns)`.

## 5. W4 — field

### 5.1 FPL-Core-Insights collector
- `gaffer core-insights` fetches the repository's per-season CSVs (player
  match stats incl. CBIT/defcon, ClubElo, fixtures incl. cups/Europe)
  keyed on FPL element id, joins to `code` via the season's element map,
  and writes `data/core_insights/<season>/{players,fixtures,elo}.parquet`.
  Twice-daily plist `com.gaffer.core-insights.plist` (06:30, 18:30).
- Degradation tests: repo unreachable, CSV schema drift (unknown column
  added / expected column missing), empty season.
- Health line: rows and latest date per table.

### 5.2 Gated minutes features (new arms)
- `role_wb_share`: share of the last 5 starts in which CBIT/defcon
  profile classifies the defender as wing-back (rule in the plan). DEF only.
- `density_pub_7d`: published fixtures (league + cup + Europe) in the
  seven days before kickoff, from §5.1 — **forward** fixtures from the
  published list, not the withdrawn cup-archive congestion arm; the spec
  and quality table say so.
- Each is a pre-registered arm on the minutes model with the v10 rule
  (autosub-week counterfactual and bucket RMSE); kept only if it clears.

### 5.3 Rank-distribution simulation
- Extend `league_sim`'s correlated sampler: the "field" is a synthetic
  population whose picks are drawn from field EO (§3.3's `deadline_eo`),
  correlated through the same player draws as the user's squad. Output
  per GW: `P(green arrow)`, `P(top-10k)` (needs the top-10k score
  threshold: use the historical distribution of top-10k weekly scores by
  GW from `build-history`, else empty state), and the user's expected
  overall-rank change. League hub → new "Field" panel.
- Test: a squad identical to the field's modal team has P(green) ≈ 0.5.

### 5.4 Set-piece overrides
- `data/set_pieces.yaml` (shipped as `data/set_pieces.toml` — TOML by the
  plan's Appendix B §3, since the tree has `tomllib` and no yaml)
  (untracked, example file tracked): per team,
  ordered takers for penalties, direct FKs, corners. `set_pieces.py` reads
  it before inference (authorized edit: one read hook); the UI shows a
  "manual" badge where the override applied.

**W4 gate:** collector degradation tests; §5.2 outcomes recorded; §5.3
sanity test; suite green.

### W4 G1 — suites, rails, pins (measured by the implementer)

Measured in the W4 worktree at `6a9601c`, and re-measured on the fix round
that closes the cycle. The orchestrator re-runs all of it on the merge commit;
these are the numbers it is checking against, not a substitute for that run.

- [x] **Python suite:** `PYTHONPATH=src .venv/bin/pytest tests/ -q` —
      **3829 passed, 13 skipped** at `6a9601c`, **3831 / 13** at `287dff1`
      after the fix round adds two rails (a `pen_table` and a `/api/players`
      frame value that is not an int until it is one), and **3836 / 13** at
      `e3121f2` after the §5.2 arm flip (all three measured, not carried
      forward). The skips are the built-asset tests, which skip in a worktree
      with no `web/static/` build; the main tree collects them.
- [x] **Frontend:** `cd frontend && npx vitest run` — **722 passed, 4 skipped**
      over 73 files; `npx tsc --noEmit` clean.
- [x] **Pins:** `46 12 55` — routes / `JOB_KINDS` / `fields(Config)`,
      **unchanged from W3's tip**. W4 adds no `Config` field, no route and no
      job kind: the collector is a CLI command and a plist, and the health
      card and the Field panel are additive fields on `Health` and
      `LeagueSimData`.

      ```bash
      .venv/bin/python -c "
      import os, tempfile, dataclasses
      os.chdir(tempfile.mkdtemp())
      from gaffer.web.app import create_app
      from gaffer.web.job_kinds import JOB_KINDS
      from gaffer.config import Config
      print(len(create_app().openapi()['paths']), len(JOB_KINDS),
            len(dataclasses.fields(Config)))"
      # 46 12 55
      ```

- [x] **Collector degradation rails** (`tests/test_v12_w4_degradation.py`,
      `tests/test_core_insights.py`): repo unreachable and a previous
      collection *not* truncated, unknown column added, expected column
      removed, key column removed, empty season, blank Elo column,
      cross-season read, torn parquet, cold-clone health line, and the
      season-root `players.csv` winning over the per-gameweek copy the tree
      lists first.
- [x] **§5.3 sanity** (`tests/test_v12_w4_rank.py`):
      `test_a_squad_exchangeable_with_the_field_is_a_coin_flip` — §5.3's "a
      squad identical to the field's modal team has P(green) ≈ 0.5", built as
      an exchangeability test at n=4000 with the band set from the measured
      seed spread of the eight-draw estimator (0.471–0.538 over sixty seeds),
      not from the model's intent.
- [x] **Audit rails.** W3's rail was open-ended (`W2_TIP..HEAD`) and had begun
      auditing W4 under W3's name; by orchestrator ruling (2026-09-03) it is
      closed at `W3_TIP = f903959`, W3's own merge tip. W4's rail reads
      `f903959..HEAD` while the cycle runs and its `W4_TIP` is pinned by the
      gate commit at close — the standing lesson from W3, banked again.

### W4 G2 — the gates (orchestrator only)

Implementers build the drivers and never run them (CONVENTIONS §7). Every
result below is unfilled on purpose.

- [x] **The no-regression season replay, and the config both sides are pinned
      to** (pre-registered 2026-09-03, CONVENTIONS §1). Both sides:
      `price_timing = false` **pinned** — with the shipped default now true, a
      fresh nightly price log would inject *today's* falls into a 2025-26
      replay and the run would not be reproducible; `xg_per_shot = false`;
      `draw_availability = true` (inert here — the backtest passes no
      `p_play`); **no `data/set_pieces.toml` on either side**; `config.toml`
      byte-identical; seeds `20260901,20260902,20260903`; and the **archive
      state**: `data/core_insights/` **present, 3 seasons (2024-25, 2025-26,
      2026-27), collected 2026-09-03 morning** on both sides. That last one
      is new to the pinned set and is now CONVENTIONS §1's: with `role` in
      `MINUTES_FEATURES` the backtest's minutes refit reads that archive, and
      the archive is untracked, machine-local and rewritten twice a day, so
      it is a config input that no `config.toml` diff can catch. Present with
      three seasons and absent are different runs; so are the same three
      seasons collected on different mornings.

      **Control, re-run at `f903959` rather than borrowed** (W3 moved chip
      timing, so the older `[1854, 1875, 1862]` is stale):

      ```
      MULTISEED_DONE v12w4-main {"totals": [1798, 1917, 1872], "mean": 1862.3, "spread": 119, "seed_bases": [20260901, 20260902, 20260903]}
      ```

      **Expected branch delta: exactly zero on every seed**, totals and hits.
      W4 adds no `[model]` flag and no `[optimizer]` key; the two feature
      builders run on every replay frame and cost time only. A non-zero delta
      is therefore a defect and points at one of three things: a builder
      reordering rows, `feature_columns()`'s new tail leaking into
      strip-and-re-derive, or a stray `data/set_pieces.toml`.

      - Branch totals / hits (run 2026-09-03 at `7f1bf89`, the last code commit
        before the arm flip, arms off): `MULTISEED_DONE v12w4-branch {"totals":
        [1798, 1917, 1872], "mean": 1862.3, "spread": 119}` — hits `[15, 12,
        13]` both sides. **Exactly zero on every seed, totals and hits**, as
        pre-registered. ✅

- [x] **Post-hoc: role-on replay.** Not a gate row — the gate above is the
      arms-off no-regression replay and stays that way. Pre-registered by the
      orchestrator on 2026-09-03, *before* the run, and copied here verbatim:

      > Not part of the plan's gate. Branch at e3121f2 (role in
      > MINUTES_FEATURES) vs control [1798, 1917, 1872] (f903959), same pinned
      > config + the same archive state (data/core_insights/ as collected
      > 2026-09-03 morning, 3 seasons). READ: the arm shipped under the
      > two-half rule and this replay cannot re-run that rule; it is a
      > season-scale sanity check. The flip is sent back for an explicit
      > re-decision (withdraw role, ship off with numbers) iff BOTH: every
      > seed is worse than its paired control seed, AND the mean is worse by
      > more than 5 (the tolerance). Otherwise the flip stands and the numbers
      > are recorded beside — never inside — the pre-registered arms-off gate.
      > Reason: K=3 with a 119 seed spread can only support a paired sign
      > test; a one- or two-seed loss is noise by construction.

      - Run 2026-09-03 at `035c8f0` (the branch tip: role in
        `MINUTES_FEATURES`, same pinned config, same archive):

        ```
        MULTISEED_DONE v12w4-roleon {"totals": [1813, 1847, 1846], "mean": 1835.3, "spread": 34, "seed_bases": [20260901, 20260902, 20260903]}
        ```

        Hits `[14, 15, 13]` vs control `[15, 12, 13]`. Paired deltas against
        the control's `[1798, 1917, 1872]`: **+15, −70, −26**; mean **−27.0**.
        **Verdict under the pre-registered read: the flip stands.** One
        condition holds (the mean is worse by more than 5) and the other does
        not (seed 20260901 is better, so it is not "every seed worse"), and
        the read required both. Recorded without softening: two of three seeds
        are worse, the mean is worse by 27, and the role arm's own seed spread
        is 34 against the control's 119 — the head with `role` in it plays a
        narrower season. This is the second time in the program that a
        minutes/attacking-head metric gain (here −1.9% starters log-loss and a
        +0.133 autosub-week delta) has not shown up as season points; §3.5 was
        the first. Residual, not a verdict: **a K=10 role-on-vs-off replay is
        the next measurement**, and if it lands negative beyond its own seed
        spread the arm is withdrawn with these numbers beside it. The user may
        re-decide on this record at any time.

- [x] **§5.2 arm outcomes, recorded either way (CONVENTIONS §6).**
      **Precondition: a `gaffer core-insights` collection.** Without one both
      arm columns are all-missing and the drivers measure nothing. The arm
      replays run on the **shifted window** and are **not** comparable to the
      no-regression replay above.

      ```bash
      mkdir -p logs && caffeinate -i nohup .venv/bin/python \
          scripts/v12_w4_arms.py > logs/v12_w4_arms.log 2>&1 &
      grep -e W4_COVERAGE -e W4_ARM_LEVER -e W4_ARM_DONE -e W4_VERDICT \
          logs/v12_w4_arms.log
      ```

      **The rule, both halves, pre-registered** (v10 §F3a, the orchestrator's
      2026-09-03 restatement). Keep an arm iff **(a)** the starters-slice
      `p_start` log-loss improves by ≥ 1% relative against *this run's own
      control* **and** zeros RMSE is no worse by more than 0.005, **and**
      **(b)** the mean points delta over the weeks an autosub actually fired
      is ≥ 0. **Either half failing is a withdrawal; neither half alone ships
      an arm.** **The coverage line is part of the result:** if
      `train_covered` is 0 the driver exits and the honest record is "not
      measurable on any window the archive covers" — which is neither a keep
      nor a withdrawal.

      - Coverage (`W4_COVERAGE`, run 2026-09-03 on the main tree after a
        collection of 2024-25/2025-26/2026-27): season_idx 0 and 1 (2022-23,
        2023-24) read all-NaN for both arms — the archive does not cover them
        and the Critical fix makes that missing rather than zero; season_idx 2
        (2024-25, the one covered training season) `role_wb_share` non-null
        0.134 (median 0.2, share-zero 0.33), `density_pub_7d` non-null 1.0
        (median 1.0); season_idx 3 (2025-26, the test season) role 0.167,
        density 1.0; `train_rows` 83513, `train_covered` 27283, `test_rows`
        29757, `test_covered` 29757. `W4_ARM_LEVER ok`.
      - Verbatim:

        ```
        W4_ARM_DONE baseline {"train_max_idx": 2, "test_idx": 3, "zeros": 0.917, "zeros_n": 18555, "haulers": 5.508, "all": 1.946, "p_start_ll_starters": 0.43723, "p_start_ll_all": 0.25265, "starters_n": 7815, "rows": 29757}
        W4_ARM_DONE role {"train_max_idx": 2, "test_idx": 3, "zeros": 0.919, "zeros_n": 18555, "haulers": 5.517, "all": 1.949, "p_start_ll_starters": 0.42889, "p_start_ll_all": 0.25168, "starters_n": 7815, "rows": 29757}
        W4_ARM_DONE density {"train_max_idx": 2, "test_idx": 3, "zeros": 0.923, "zeros_n": 18555, "haulers": 5.488, "all": 1.946, "p_start_ll_starters": 0.43584, "p_start_ll_all": 0.25358, "starters_n": 7815, "rows": 29757}
        W4_VERDICT role {"logloss_relative_gain": 0.01907, "zeros_cost": 0.002, "decision": "keep", "half": "a", "keep_also_requires": "half (b): scripts/v12_w4_autosub_cf.py, mean points delta over autosub w…
        W4_VERDICT density {"logloss_relative_gain": 0.00318, "zeros_cost": 0.006, "decision": "withdraw", "half": "a", "keep_also_requires": "half (b): scripts/v12_w4_autosub_cf.py, mean points delta over au…
        ```

      - `role`: starters log-loss 0.43723 → 0.42889 (−1.907% relative, clears
        the 1% bar); zeros 0.917 → 0.919 (+0.002, within 0.005). **Half (a):
        keep.**
      - `density`: 0.43723 → 0.43584 (−0.318%, below the bar); zeros 0.917 →
        0.923 (+0.006, over the bar). **Half (a): withdraw.**
      - Decision, per arm (after half (b) below): **`role` ships on**
        (`e3121f2`, `ROLE_FEATURES` appended to `MINUTES_FEATURES`, effective
        on the next `gaffer train`); **`density` withdrawn**, built on both
        seams and fed to no head, numbers kept.

- [x] **§5.2 decision half.** Same precondition, same window.

      ```bash
      mkdir -p logs && caffeinate -i nohup .venv/bin/python \
          scripts/v12_w4_autosub_cf.py > logs/v12_w4_autosub_cf.log 2>&1 &
      grep -e W4_CF_LEVER -e W4_CF_DONE logs/v12_w4_autosub_cf.log
      ```

      Read as the small sample it is — one season, fresh squads weekly, a
      per-week tendency and not a season total. A `W4_CF_LEVER` line must
      appear first; without it the run measured two identical arms and is
      void.

      - Run 2026-09-03: `W4_CF_LEVER ok`; 15 autosub weeks of 38. `role`
        autosub_mean_delta **+0.133** (pass), `density` **+0.333** (pass —
        moot, it fails half (a)). Recorded beside the rule, not inside it:
        over **all** 38 weeks the deltas are role **−0.211**, density
        **−0.895** (role: 23 weeks with a different XI, 29 with a different
        bench). That all-weeks number is why the post-hoc role-on replay
        above was run before the merge.

        ```
        W4_CF_DONE {"window": {"train_max_idx": 2, "test_idx": 3}, "rule": "KEEP an arm iff BOTH halves hold: (a) starters-slice p_start log-loss improves by >= 1% relative to THIS run's control AND zeros RMSE is not worse by more than 0.005 (this driver); AND (b) the mean points delta over the weeks in which an autosub actually fired is >= 0 (scripts/v12_w4_autosub_cf.py). Either half failing is a withdr…
        ```

- [x] **Zero unauthorized protected diffs.** Base is **`f903959`**, W3's merge
      tip, not `main` — a rail scoped to somebody else's range audits somebody
      else's work.

      ```bash
      git diff --stat f903959..HEAD -- \
        src/gaffer/advise.py src/gaffer/optimize src/gaffer/web/jobs.py \
        src/gaffer/web/routers/whatif.py tests/test_advise.py tests/test_odds.py \
        tests/test_web_jobs.py scripts/s2_replay.py \
        $(git ls-files 'tests/test_*_degradation.py' | grep -v v12_w4)
      # expected: only tests/test_v12_w3_degradation.py, whose W3-rail closure
      #   is the authorized edit of 2026-09-03; nothing else

      git diff -U0 f903959..HEAD -- src/gaffer/set_pieces.py \
        | grep '^[-+]' | grep -v '^[-+][-+]'
      # expected: exactly Task 17's two line-groups plus Task 20's one
      #   docstring sentence naming the club rule, and the provenance comment
      #   # v12 W4 §5.4 (specs/2026-09-01-gaffer-v12-program-design.md)
      ```

      W4's authorized protected set is **`src/gaffer/set_pieces.py` only**.

      - Result: ✅ only `tests/test_v12_w3_degradation.py` over the protected set; `set_pieces.py` = the two Task-17 groups + the Task-20 sentence + the club-aware/NaN-guard amendments inside the `order_of` group, all with provenance; W4's audit rail 2 passed on the merge.

- [x] **Pins on the merge commit.** Expected: **`46 12 55`** (G1's command).

      - Result: ✅ `46 12 55` at `e0bdf79`.

- [x] **Post-merge ritual (§7).** ff-only into `main` at `e0bdf79` (2026-09-03), pushed; `git show main:config.toml` fails; key-grep over all history empty; no `data/`/`reports/`/`logs/`/`models/` path in the tip. Suite at the merge: **3854 Python / 726 frontend**, tsc clean. W4's audit rail reads `f903959..HEAD`; W5's first authorized edit pins `W4_TIP = "e0bdf79"`, the way W4 pinned W3's.

      ```bash
      git show main:config.toml     # expected: fatal — path does not exist
      git log -S"$(grep -o 'odds_api_key.*' config.toml | head -1)" --all
      # expected: empty
      ```

      - Result: _(unfilled)_

**Residuals, recorded before the gate runs.**

1. **`density_pub_7d`'s window is seven calendar days, UTC**, not 168 hours.
   The hour-counted version put the ordinary week-earlier fixture in or out
   depending on which side of the boundary the later kickoff slot fell, so the
   count oscillated with the broadcaster rather than with the schedule. The
   fixture being predicted is excluded by its own calendar day rather than by
   timestamp equality, because one second of divergence between two publishers
   added +1 to every row in the frame.
2. **Both arms read today's published schedule, not a vintage of it.** The
   archive keeps no history of what was published when, so a tie rearranged in
   November sits on a historical row at its February date. The hindsight is
   one-directional (a rearrangement only moves a fixture later, so a training
   row's count is if anything understated) and **identical on both seams** —
   training and serving read the same file through the same function — so it
   cannot produce a train/serve skew. It would matter for a claim about what a
   manager knew in November; it does not for a feature both sides compute the
   same way.
3. **The synthetic field's captaincy is a second Bernoulli, `eo − 1`**, not a
   modelled armband: a manager holds the crowd's captain twice, once or not at
   all, and the pair's mean is `eo` exactly. The field is an ownership
   portfolio and not a set of legal squads — no budget, no position limits, no
   three-per-club — which widens a synthetic manager's week slightly and
   pushes every probability counted off it a shade toward 0.5. Drawing legal
   squads would need a solver per manager per gameweek for a second-order
   correction to a first-order quantity.
4. **`rank_slope` regresses a cumulative quantity on a weekly one.**
   `my_points` is one week; `overall_rank` is a season standing that drifts on
   its own, and the drift correlates with the gameweek index rather than with
   the week's score. The panel's number is therefore an association over the
   weeks graded so far, not the response to a marginal point. Differencing
   rank week to week removes the drift and is the obvious next version; it
   needs consecutive graded weeks the ledger does not yet have. The ledger also
   carries no season column, so the panel restricts to `gw <= plan gw` — right
   within a season, self-limiting at a rollover, and the real fix is a
   protected-file change.
5. **Corner and free-kick overrides change the served order and nothing
   else.** There is no free-kick or corner term in the model, so §5.4's file
   reaches expected points through `penalties` alone. The badge is a display
   fact by construction — it is derived from the orders actually served, so it
   cannot claim an override the row did not get.
6. **`pen_tracker.save_tracker_guarded` and `features/engineer.py`'s
   `pen_taker` are deliberately not overridden.** `gaffer track-pens` records
   what FPL published and must keep doing so; `pen_taker` is a training column
   built from match history. A user's opinion prices the coming week and does
   not rewrite the evidence.
7. **W4's own audit rail is open-ended until the gate closes it.** It reads
   `f903959..HEAD` during the cycle, which is correct while W4 is the tip and
   wrong the moment W5 starts; the gate commit pins `W4_TIP`. This is the
   third cycle to bank that lesson and the second to have to fix a predecessor's
   rail because of it.

## 6. W5 — interface

### 6.1 Tab state in the URL
- `?tab=` per hub, read on load, written on change; deep links work.
### 6.2 Settings tab (Model hub)
- Whitelist: `horizon, decay, lambda_tilt, chip θ priors path, top_n,
  bench_weights, itb_value, price_timing, draw_availability`. Read from
  the merged config; edits are written to `config.local.toml`, which
  `config.py` loads as an overlay after `config.toml`. The UI never reads
  or writes `config.toml`. A "restart to apply" notice where needed.
### 6.3 Watchlist list view; `captain_note` rendered on This Week beside the
  captain pick.
### 6.4 Frozen projections
- Every `advise` run writes `reports/projections/<season>-GW<gw>-<ts>.parquet`
  (the EP table it acted on). Review compares the ledger against the
  latest snapshot before the deadline, not a re-run; the Review row shows
  the snapshot timestamp.
### 6.5 "Why this move" trace
- Per transfer in the plan: EP gain over the horizon, hit cost, FT shadow
  price consumed, θ (if a chip), λ tilt contribution, price-timing charge.
  Exposed on the ledger row and the board; computed in `_decision_scales`'
  neighbourhood (authorized edit, read-only accounting — must not change
  any decision; test asserts the plan is byte-identical with the trace on
  and off).
### 6.6 `types.ts` generation
- `scripts/gen_types.py` emits `frontend/src/types.ts` from
  `web/schemas.py` (pydantic → JSON schema → TS via
  `json-schema-to-typescript`, pinned). A test regenerates to a temp file
  and asserts equality with the committed file.

**W5 gate:** suite green; §6.5 byte-identity test; a manual pass through
all six hubs with the "as of" strip and URL state.

### W5 G1 — suites, rails, pins (measured by the implementer)

Measured in the W5 worktree at `7be99b1`, the rename-count reconciliation that
precedes this block. Nothing is carried forward from W5's base `5bb7d0e`
(3854 Python / 723 passed + 4 skipped frontend over 73 files; pins `46 12 55`)
— every number below was re-run at that SHA. The orchestrator re-runs all of
it on the merge commit; these are the numbers it is checking against, not a
substitute for that run.

- [x] **Python suite:** `PYTHONPATH=src .venv/bin/pytest tests/ -q` —
      **4016 passed, 13 skipped** at `7be99b1`. The skips are the
      built-asset tests, which skip in a worktree with no `web/static/` build;
      the main tree collects them.
- [x] **Frontend:** `cd frontend && npx vitest run` — **792 passed, 4 skipped**
      over 79 files (78 passed, 1 skipped); `npx tsc --noEmit` clean.
- [x] **Pins:** `47 12 55` — routes / `JOB_KINDS` / `fields(Config)`. Routes
      **46 → 47**: one new path key, `/api/settings`, with GET and POST on the
      one key. `JOB_KINDS` and `fields(Config)` do not move — W5 adds no job
      kind, and `config.local.toml` is a loader change rather than a field. The
      nine whitelisted settings all already exist, as `Config` fields or as the
      module-level readers `web/settings_keys.py` names.

      ```bash
      .venv/bin/python -c "
      import os, tempfile, dataclasses
      os.chdir(tempfile.mkdtemp())
      from gaffer.web.app import create_app
      from gaffer.web.job_kinds import JOB_KINDS
      from gaffer.config import Config
      print(len(create_app().openapi()['paths']), len(JOB_KINDS),
            len(dataclasses.fields(Config)))"
      # 47 12 55
      ```

      The **single absolute route pin** is still in one file, which is what
      v11's restructure bought and what W5's STOP spent:

      ```bash
      grep -rnE '^\s*assert\s+len\(\s*(set\()?\s*paths\)?\s*\)\s*==\s*[0-9]+' tests/
      # tests/test_v11_degradation.py:368:    assert len(paths) == 47
      ```

      The **absolute `Config` field pin** stays where W3 put it:
      `tests/test_v12_w3_degradation.py:536`, `assert len(names) == 55`. W5
      pins neither total of its own — `tests/test_v12_w5_degradation.py` asserts
      `/api/settings` by name and `JOB_KINDS`/`fields(Config)` against the
      values Task 0 measured at `5bb7d0e`, and it carries v11's meta-test
      (`test_this_file_does_not_pin_the_absolute_route_count`) checked from
      inside the file it constrains.
- [x] **The W5 rails** (`tests/test_v12_w5_degradation.py`), five blocks:
      - *The cold clone reaches every new surface* — `/api/settings` on a tree
        with nothing in it is a 200 naming the file to copy, a settings **write**
        on that tree refuses rather than writing one, and the plan, review-ledger
        and watchlist surfaces still degrade exactly as they did.
      - *W5's routes, by name* — `/api/settings` present, GET and POST on the
        one path key, no `/api/trace`, `/api/projections` or `/api/config`
        invented beside it, and this file pins no absolute route count.
      - *The counts W5 did not move* — `len(JOB_KINDS) == 12` and
        `len(fields(Config)) == 55`, against Task 0's measurement rather than
        against W1's 45/12/48.
      - *The honesty rules, checked rather than asserted in prose* — both
        snapshot readers take `season` positionally with no default (a default
        makes the cross-season read the easy call); the trace returns `None`
        rather than a measured zero for an EP it cannot price, and `None`
        rather than `0.0` for the price charge when `price_timing` is off; the
        settings whitelist cannot reach `odds_api_key`, `web_token`,
        `entry_id`, `league_id`, `train_seasons` or `news_llm_command`; and no
        file this workstream wrote declares a `[solver]` table — checked as a
        TOML table header, and again behaviourally, since the whitelist's three
        sections are `optimizer`, `league` and `scenarios` and a save writes
        only into those.
      - *The protected-diff audit* — Block 5, below.

      The overlay's own guarantee lives beside these rather than in them:
      `tests/test_v12_w5_settings.py`'s
      `test_a_write_lands_in_the_overlay_and_never_in_config_toml`, and
      `tests/test_v12_w5_config_overlay.py`'s
      `test_it_reaches_a_section_config_toml_never_declared`.
- [x] **Audit rails.** W4's rail was left open at `HEAD` and would have started
      measuring W5's diff under W4's name; W5's first authorized edit closed it
      at `W4_TIP = "5bb7d0e"` — commit `e586180`, and
      `git log --oneline 5bb7d0e..HEAD -- tests/test_v12_w4_degradation.py`
      shows that one commit and no other. W5's own rail
      (`tests/test_v12_w5_degradation.py`, `W4_TIP = "5bb7d0e"`) reads
      `5bb7d0e..HEAD` while the cycle runs, excludes W5's own three degradation
      files by prefix rather than by name, and is non-vacuous: an empty range
      fails on the missing `tests/test_v11_degradation.py` rather than passing
      as clean. **W5 is the last workstream of v12, so the program close pins
      `W5_TIP`** — there is no next workstream to do it, and the lesson three
      cycles have now banked is that a rail with a floating end audits the next
      cycle's work under this one's name.

### W5 G2 — the gates (orchestrator only)

Implementers build the drivers and never run them (CONVENTIONS §7). Every
result below is unfilled on purpose.

- [ ] **No replay, and why.** W5 is interface-only. `src/gaffer/optimize/**`
      and `src/gaffer/advise.py` are untouched — the G2 diff below proves it,
      not a claim in prose — no `[optimizer]` key and no `[model]` flag was
      added, and the trace is accounting computed *after* the solve from the
      two artifacts the plan router already loads. There is therefore nothing
      a season replay could move, and **W5 pre-registers no replay**
      (CONVENTIONS §1: pre-registered before the fact, including the decision
      not to run one). The substitutes are §6.5's byte-identity test and the
      import-isolation test, which is the stronger of the two: byte-identity
      makes a decision change *detectable*, isolation makes it *impossible*.

      ```bash
      PYTHONPATH=src .venv/bin/pytest -q \
        tests/test_v12_w5_plan_trace.py::test_the_payload_is_byte_identical_with_the_trace_off \
        tests/test_v12_w5_trace.py::test_the_trace_module_is_imported_by_no_solver
      #   the payload with the trace on, with `trace` stripped from
      #   `weeks[*]` *and* from `alternatives[*].weeks[*]`, is byte-identical
      #   to the payload with TRACE off; and `gaffer.trace` is imported by
      #   nothing that solves — not advise.py, not backtest.py, and by no
      #   module under optimize/
      PYTHONPATH=src .venv/bin/pytest -q tests/test_v12_w5_gen_types.py \
        -k "the_one_the_models_produce or byte_for_byte or deterministically"
      #   the regenerate-no-diff half: schemas.json equals what the models
      #   produce, byte for byte, and the writer is deterministic
      ```

      - Result: _(unfilled)_

- [ ] **Zero unauthorized protected diffs.** Base is **`5bb7d0e`**, W4's merge
      tip on `main`, not `main` itself — a rail scoped to somebody else's range
      audits somebody else's work.

      ```bash
      git diff --stat 5bb7d0e..HEAD -- \
        src/gaffer/advise.py src/gaffer/set_pieces.py src/gaffer/optimize/ \
        src/gaffer/web/jobs.py src/gaffer/web/routers/whatif.py \
        tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
        scripts/s2_replay.py | cat
      # expected: empty — no src protected file may differ

      git diff --stat 5bb7d0e..HEAD -- \
        $(git ls-files 'tests/test_*_degradation.py' | grep -v v12_w5) | cat
      # expected: exactly TWO files, and no third:
      #   tests/test_v11_degradation.py     — Task 3's STOP: the docstring's
      #     46 -> 47, `assert len(paths) == 47`, `assert "/api/settings" in
      #     paths`, under the provenance comment
      #     `# v12 W5 §6.2 (specs/2026-09-01-gaffer-v12-program-design.md)`
      #   tests/test_v12_w4_degradation.py  — the `W4_TIP = "5bb7d0e"` pin and
      #     the two range reads that now end there, under the provenance
      #     comment `# v12 W5 (orchestrator ruling 2026-09-03): the W4 rail
      #     audits W4's range, not everyone's`
      # (W5's own three degradation files are excluded by the same prefix rule
      #  the rail uses; the plan's un-narrowed command lists five and is wrong)
      ```

      W5's authorized protected set is **exactly those two test files**.

      - Result: _(unfilled)_

- [ ] **The manual six-hub pass** (spec §6 gate: "a manual pass through all six
      hubs with the 'as of' strip and URL state"). W1 owns the strip; W5 owns
      the URL state. With `uv run gaffer ui`:

      | Hub | `?tab=` round-trips | strip renders | notes |
      | --- | --- | --- | --- |
      | This Week | n/a (no tabs) | ____ | ____ |
      | Planning | ____ | ____ | ____ |
      | Players | ____ | ____ | ____ |
      | League | ____ | ____ | ____ |
      | Live | n/a (no tabs) | ____ | ____ |
      | Model | ____ | ____ | ____ |

      Plus, on the Model hub: change one setting, confirm it lands in
      `config.local.toml`, confirm `config.toml` is byte-identical afterwards —
      both files are gitignored, so `git status` cannot be the check and
      `md5 config.toml` before and after is — and reset it.

      - Result: _(unfilled)_

- [ ] **Pins on the merge commit.** Expected: **`47 12 55`** (G1's command).

      - Result: _(unfilled)_

- [ ] **Post-merge ritual (§7).**

      ```bash
      git show main:config.toml            # expected: fatal — no such path
      git show main:config.local.toml      # expected: fatal — no such path
      git log -S"$(grep -o 'odds_api_key.*' config.toml | head -1)" --all | cat
      # expected: empty

      git log -p 5bb7d0e..HEAD | grep -nEi "api[_-]?key|secret|token|bearer" | cat
      # expected: NOT empty, and reviewed rather than waved through. The
      # settings whitelist names `web_token` and `odds_api_key` as keys the
      # endpoint must never reach, so hits inside tests/ and
      # src/gaffer/web/settings_keys.py are the guard being written down, not a
      # leak. Any hit outside those two places is a finding.

      git log --stat 5bb7d0e..HEAD \
        | grep -E "^ (data|reports|models|logs|config\.toml|config\.local\.toml)" | cat
      # expected: empty. `config.local.toml` is new to this list and has the
      # new way of getting there: the Settings tab writes it on every save, so
      # a developer testing the tab has an untracked file in the tree at the
      # moment he commits the tab.
      ```

      - Result: _(unfilled)_

### W5 G3 — review and merge (orchestrator only)

- [ ] Adversarial review, fix-first, re-verify.

      - Result: _(unfilled)_
- [ ] Merge ritual: ff-only into `main` at ___ , pushed;
      `git show main:config.toml` fails; the key-grep over all history is
      empty; the protected audit re-run on the merge passes. Suite at the
      merge: ___ Python / ___ frontend, tsc clean; pins routes ___ /
      `JOB_KINDS` ___ / `Config` fields ___ .

      - Result: _(unfilled)_

### W5 live spot-checks (orchestrator, on the dev server)

- [ ] §6.1 A `?tab=` link into each of Planning, Players, League and Model
      lands on that tab rather than on the hub's default, and the back and
      forward buttons walk the tabs rather than leaving the hub — the two are
      one check, because `replace: true` is what decides which of them holds.
- [ ] §6.2 A Settings save writes `config.local.toml` and leaves `config.toml`
      byte-identical, and the "as of" strip reflects the reload rather than the
      values the page fetched before the save.
- [ ] §6.3 A watchlist note written in the list view survives a star click in
      the explorer — the note, not the date: `watchlist.watch` replaces both,
      so the row should come back with its text and a reset "noted" stamp.
- [ ] §6.3 `captain_note` renders beside the captain on This Week when the tilt
      moved it, and nothing renders at all when the run wrote `""`.
- [ ] §6.4 The first Review row graded after the merge names its projection
      snapshot, and reads `(late)` only for one of the two causes the tooltip
      lists (**data-gated:** the first gameweek graded after the merge).
- [ ] §6.5 The planner's "why this move" disclosure shows the head plan's terms
      and the caption names the three it does not attribute; the price line
      prints its reason rather than a zero while the nightly price log is still
      short (**data-gated:** `[optimizer] price_timing` on *and* enough log for
      `owned_price_falls` to return a row per owned player).
- [ ] §6.6 `.venv/bin/python scripts/gen_types.py` after an edit to
      `web/schemas.py` produces a diff in `frontend/src/schemas.json` and
      `frontend/src/types.generated.ts` — and, left uncommitted, the two tests
      that catch it fail.

**Residuals, recorded before the gate runs.**

1. **The trace's price-timing charge is read from tonight's price log, not
   from the solve.** `owned_price_falls` is the same reader the objective uses,
   but a board drawn on Saturday against a Thursday plan multiplies a
   probability the solve never saw. Freezing it would mean writing it into the
   solve state from `advise.py`, which is protected, for a decoration.
2. **The trace does not attribute the squad-side terms.** The XI, captain and
   vice weightings and the three bench seats price the whole fifteen and a
   per-week autosub scale, not a swap, so a share of them assigned to one
   transfer would be invented. The week's lines therefore do not sum to its
   xPts, and the caption says so rather than leaving it to be discovered.
3. **The trace covers the head plan only.** Plans B and C came out of
   different solves, priced against different XIs and with their own
   free-transfer counts, so the strip says the numbers are Plan A's rather than
   showing terms that would silently be the wrong plan's.
4. **`projection_snapshot` fills forward only.** Grades are banked and never
   re-derived, so every ledger row banked before W5 keeps `null` for ever.
5. **`reports/projections/` is never pruned.** ~6–12 MB a season, gitignored.
   A future `gaffer tidy` target, deliberately not invented here.
6. **The watchlist's `set_at` is reset by every save**, because
   `watchlist.watch` replaces the note and the timestamp together. The column
   is labelled "noted" rather than "watching since" for that reason; fixing it
   means a second store field.
7. **The decision ledger has no season key.** After a rollover, a GW-N row
   could name last season's GW-N snapshot: the snapshot *reader* is
   season-guarded, the ledger is not. Nothing reads across a rollover today,
   and the fix is a ledger migration rather than a W5 line.
8. **`types.ts` is a split, not a rewrite, and the split carried away the
   client's field comments.** Thirty hand-written exports have no pydantic
   source and eleven models are narrowed by hand, so the generated half can
   never be the whole file. The split deleted 113 hand-written interfaces; 119
   of the 891 field sentences were recovered by reading `schemas.py`'s
   attribute docstrings, and the rest of the client-side commentary on those
   interfaces is gone. The follow-up is to move the sentences worth keeping
   into `schemas.py` field docstrings, where the generator can carry them,
   rather than back into a file it overwrites.
9. **W5's own audit rail is open-ended until it is pinned.** It reads
   `5bb7d0e..HEAD` during the cycle, which is correct while W5 is the tip. W5
   is v12's last workstream, so there is no next cycle to close it: the
   **program close** pins `W5_TIP`. This is the fourth cycle to bank the
   lesson and the third to have had to fix a predecessor's rail because of it.

## 7. Testing and gates, summarized

| Workstream | Gate beyond "suite green + zero unauthorized diffs" |
|---|---|
| W1 | backup restore test; live rollover guard |
| W2 | replay tolerance 5 (price-timing); ablation outcome recorded |
| W3 | replay tolerance 5, hits ≤ +3; captain support drop ≤ 10 pts |
| W4 | collector degradation; arm outcomes recorded; rank-sim sanity |
| W5 | trace byte-identity; manual six-hub pass |

Post-merge ritual after every workstream: `git show main:config.toml` fails;
`git log -S<odds key> --all` is empty.

## 8. Out of scope (do not add during execution)

Referee/weather; transformer news sentiment; Sarmanov/NB Dixon-Coles; price
chasing; per-player finishing multipliers; horizon extension; the withdrawn
minutes arms as-is; write tools on the MCP server; a UI that edits
`config.toml`.
