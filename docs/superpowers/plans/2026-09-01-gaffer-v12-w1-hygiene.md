# Gaffer v12 W1 Implementation Plan — hygiene

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the correctness of what already exists. One atomic-write helper with real
callers, one set of EO constants, a season-guarded field read, a rollover guard that
refuses rather than mis-trains, a tracker that will not overwrite good data with
degraded data, a solver pool size a human can see, two housekeeping commands
(`backup`, `tidy`), write protection when the UI is served to the LAN, one "as of"
strip on every hub, and an MCP server that lets Claude Code read this tree.

**Architecture:** eleven spec items, and the honest shape is not the spec's shape in
five places. Three of those five make W1 **larger** than budgeted and two of them make
it a protected-file cycle where the spec expected almost none.

- **§2.11 is the big one.** The spec says the atomic-write idiom has *six* copies. It
  has **twenty**, in three distinct families (JSON/text, parquet-through-`store`, raw
  bytes), and one of the twenty is inside `advise.py`, which is protected. Worse: two
  assertions in the **protected** `tests/test_v9c_degradation.py` read
  `inspect.getsource()` and require the literal strings `os.replace` and `os.getpid()`
  to appear in `advise.py` and `digest.py`. Migrating either module to a shared helper
  deletes those strings. So §2.11 is not a refactor, it is a refactor plus a STOP
  (A1, A2).
- **The pin toll is the config-field count, and it is v10b's route-pin residual
  repeating verbatim.** `len(dataclasses.fields(Config)) == 48` is asserted in **seven
  protected degradation files** plus one unprotected file. W1 adds five config fields.
  v11 retired the absolute *route* pin down to one file and left the *config* pin
  untouched, because v11 added no config field and had no reason to look. W1 adds
  five, so it pays the toll — and it pays it the way v11 did, by restructuring rather
  than by moving eight numbers (A8).
- **§2.3 was already half-shipped and the other half is blocked by two protected
  pins.** `latest_field_eo(gw=None, *, season=None)` has taken a `season` keyword
  since v10b. Making it *required* is four characters, and it breaks
  `tests/test_v10b_degradation.py:133` and `tests/test_v8c_degradation.py:72`, both of
  which call it with no arguments on purpose and say so in their docstrings. v11's A2
  refused this exact change for this exact reason. W1 does it, behind a STOP (A4).
- **§2.2's canonical module does not have the three constants the spec says it
  exports.** `optimize/differentials.py` defines `DIFFERENTIAL_EO = 30.0` and
  `ALTERNATIVE_EO = 20.0` and no `TEMPLATE_EO` at all. `advise.py` defines
  `DIFFERENTIAL_EO = 0.3` and `TEMPLATE_EO = 0.7` and no `ALTERNATIVE_EO`. The two
  `DIFFERENTIAL_EO`s are the same threshold on the same quantity in different units,
  which is exactly why one of them must go — but the merge moves `TEMPLATE_EO` *into*
  `differentials.py` rather than finding it there, and it converts
  `differentials.py`'s **own two readers**, which compare against a percent (A3).
- **§2.1's backup set misses the one irrecoverable thing in the tree.** The spec says
  field EO samples are covered because they live in `data/live/field_eo_log.parquet`.
  The *log* does. The sampled **squads** do not: `save_field_sample` writes
  `data/raw/field/<season>/gw<N>.json`, 228 KB today, and a past gameweek's top-10k
  picks cannot be re-fetched from anywhere. W4 §5.3's rank-distribution sim reads
  them. `data/raw/field/` goes in the archive and the plan says why (A9).

Two more, smaller: the rollover guard cannot call the FPL API from `/api/health`
because `meta.py` is disk-only by contract, so the served half reads the banked events
snapshot (A5); and the MCP `whatif` tool cannot wrap "the existing router function"
because `POST /api/whatif` returns `JobAccepted` with a 202 — it wraps `solve_whatif`,
importing from a protected module without editing it (A13).

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, tomllib, typer,
pytest; React 19 + TypeScript + vitest. New runtime dependency: `mcp==2.1.1`.

**Branch:** `feat/gaffer-v12`, cut at `27f7933` (the spec commit) off `main`.
Authoritative spec: `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md`,
§1 (shared conventions) and §2 (W1). Measurement rules:
`docs/superpowers/CONVENTIONS.md`.

```bash
git rev-parse --abbrev-ref HEAD      # feat/gaffer-v12
git rev-parse HEAD                   # 27f7933...  (docs: v12 program design)
```

**Protected — must show zero *unauthorized* diffs (Task 18 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/whatif.py`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
**every** pre-existing `tests/test_*_degradation.py` — `test_degradation.py`, v4c, v4d,
v5, v6, v7_model, v8a, v8b, v8c, v8d, v8e, v8f, v8g, v9a, v9c, v9d, v10, v10b,
**v11** — and `scripts/s2_replay.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`. This cycle imports
from neither and **does not migrate `journal.py`'s copy of the atomic-write idiom**
(A15). `src/gaffer/web/routers/whatif.py` is protected but *importable*, and Task 14
imports `solve_whatif` from it without editing a line.

**Five STOPs.** The spec's §Authorization grants the orchestrator standing
authorization for this program; that is not the same as this plan's implementer having
it. Each STOP below enumerates its exact line-groups and waits.

| STOP | Task | Files | Why |
| --- | --- | --- | --- |
| 1 | **T4** | `src/gaffer/advise.py`, `tests/test_v9c_degradation.py` | advise's own atomic write, and the two source-grep pins the migration invalidates (A2) |
| 2 | **T5** | `src/gaffer/advise.py` | §2.2 deletes advise's two EO constants and imports the canonical ones. `tests/test_advise.py` is **not** in this STOP: it imports `transfer_tag`, not the constants, and every boundary it asserts (29.9 → attack, 30.0 → "", 70.0 → cover) is unchanged by the merge |
| 3 | **T6** | `tests/test_v10b_degradation.py`, `tests/test_v8c_degradation.py` | §2.3 makes `season` required, which is what those two pins deny (A4) |
| 4 | **T9** | `src/gaffer/optimize/milp.py` | §2.6's one line-group: `build_pool` reads the config default |
| 5 | **T15** | seven protected degradation files | the config-field pin moves 48 → 53 (A8) |

**If a task concludes a sixth protected edit is required, it STOPs and reports rather
than widening the diff.**

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never
stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml` or
`src/gaffer/web/static/`.

**Gate rule (CONVENTIONS §7):** implementers build and never run the gates. Task 18 is
the checklist with G1 measured and G2 unfilled.

**Frontend test runner: `npx vitest run`.** `package.json` maps `test` to bare
`vitest`, which is watch mode, and it hangs an agent forever.

**Python: `.venv/bin/pytest`.** There is no bare `python` on PATH; use
`.venv/bin/python`. `uv run pytest` also works and is what the older plans wrote.

**Pins, measured at `27f7933`:**

| Pin | At `27f7933` | After W1 | Why it moves |
| --- | --- | --- | --- |
| `len(create_app().openapi()["paths"])` | 45 | **46** | §2.9's `GET /api/meta/freshness`, the cycle's only new route |
| `len(dataclasses.fields(Config))` | 48 | **53** | `backup_dir`, `backup_rsync_target`, `backup_keep`, `top_n`, `web_token` |
| `len(JOB_KINDS)` | 12 | **12** | `backup`, `tidy` and `mcp` are CLI commands; none is a background lane |

```bash
# how all three were measured; re-run before writing Task 16's pins
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# 45 12 48
```

**Suite baselines (this branch at `27f7933`, measured): 3193 Python tests collected;
frontend 655 passed (ROADMAP's v11 G1 figure — re-measure, the ROADMAP is not a test
runner).** Re-measure both before Task 1 and write the numbers into this header,
because every task's final run is judged against them:

```bash
.venv/bin/pytest -q --collect-only | tail -1     # measured: 3193 tests collected
cd frontend && npx vitest run                    # record: <N> passed, <M> skipped
```

**Spec §1's five shared conventions, and where each one lands in W1:**

| §1 convention | Where |
| --- | --- |
| Empty states are honest | T13's strip (five grey "never" rows, and it stays visible when its own fetch fails), T7's banner (drawn on `False` alone, never on `null`), T10's Health line ("never — run `gaffer backup`") |
| Data-gated items get a ROADMAP checkbox | **W1 has none.** Every item here works on a cold clone the day it ships; nothing waits on a GW being `data_checked`, on N snapshot dates, or on a collector run. Said out loud so its absence is a finding rather than an omission — W2 §3.1 and §3.2 are where those checkboxes belong |
| Degradation tests for every new collector or reader | W1 adds five readers — `optimizer_top_n`, `season_from_events`, `backup.latest_backup`, `tidy.candidates`, `meta.freshness` — and no collector. Each has a missing-file, malformed-file, empty-result and partial-result case in T16's blocks 3, 4 and 6 |
| Season guard on every element-id-keyed read | T6. It is the only element-keyed read W1 touches, and it was already the tree's oldest open one |
| Atomic writes through one helper | T1-T4, and the "only where a workstream already touches the file" rule is waived here by the spec itself, which is why the migration is nineteen files rather than none |

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

**Provenance comment — every authorized edit to a protected file:**

```
# v12 W1 §<id> (specs/2026-09-01-gaffer-v12-program-design.md)
```

---

## Ambiguities the spec left open, and how this plan settles them

Fifteen. Five are findings rather than decisions, and three of those five make the
cycle bigger than the spec budgeted for.

### A1 — the atomic-write idiom has twenty copies, not six, in three families

Measured, not estimated:

```bash
grep -rn "os\.replace" --include='*.py' src/
```

Twenty write sites. They are not interchangeable, and a helper that only serves one
family would leave the other two behind — which is how six became twenty in the first
place.

**Family A — JSON or text through `Path.write_text`, with a `try/finally` unlink
(14 sites):**

| # | Site | Lines | Writes |
| --- | --- | --- | --- |
| 1 | `src/gaffer/digest.py` | 85-89 | `reports/digest_<kind>.json` |
| 2 | `src/gaffer/pen_tracker.py` | 302-306 | `reports/pen_tracker.json` |
| 3 | `src/gaffer/evaluation.py` | 267-272 | `reports/evaluation.json` |
| 4 | `src/gaffer/overrides.py` | 115-119 | `reports/overrides.json` |
| 5 | `src/gaffer/watchlist.py` | 98-102 | `reports/watchlist.json` |
| 6 | `src/gaffer/drafts.py` | 89-94 | `reports/drafts.json` |
| 7 | `src/gaffer/sensitivity.py` | 90-94 | `reports/sensitivity_gw<N>.json` |
| 8 | `src/gaffer/review.py` | 1095-1106 | `reports/decision_ledger.json`, **inside `_ledger_lock`** |
| 9 | `src/gaffer/league_sim.py` | 681-694 | `reports/league_sim_history.json`, **inside `_HISTORY_LOCK`** |
| 10 | `src/gaffer/data/my_entry.py` | 85-89 | `data/raw/league/<season>/<entry>-*.json` |
| 11 | `src/gaffer/data/field.py` | 102-106 | `data/raw/field/<season>/gw<N>.json` |
| 12 | `src/gaffer/data/understat.py` | 290-292 | the match cache — **no `try/finally`** |
| 13 | `src/gaffer/data/chip_scenarios.py` | 78-88 | `data/chip_scenarios.toml` — already a private `_atomic_write`, **no `try/finally`** |
| 14 | `src/gaffer/advise.py` | 993-998 | `reports/gw<N>-advice.json` — **PROTECTED**, Task 4 |

**Family B — parquet through `store.save`, replaced under `store.DATA_DIR` (4 sites):**

| # | Site | Lines | Writes |
| --- | --- | --- | --- |
| 15 | `src/gaffer/snapshot.py` | 127-134 | `live/availability_log.parquet` |
| 16 | `src/gaffer/price_log.py` | 129-135 | `live/price_log.parquet` |
| 17 | `src/gaffer/data/field.py` | 185-191 | `live/field_eo_log.parquet` |
| 18 | `src/gaffer/data/news/presser_log.py` | 89-95 | `live/presser_log.parquet` — **and its temp name carries no pid** |

**Family C — raw bytes (1 site):**

| # | Site | Lines | Writes |
| --- | --- | --- | --- |
| 19 | `src/gaffer/web/routers/assets.py` | 142-146 | banked shirt/photo images |

**Not migrated (1 site):**

| # | Site | Lines | Why |
| --- | --- | --- | --- |
| 20 | `src/gaffer/journal.py` | 225-229 | **import-only** this cycle (A15) |

**Settled: one primitive, three thin wrappers, in a new `src/gaffer/io.py`.** The
primitive is a context manager `atomic_path(path)` that yields the pid-suffixed
sibling temp and does the `os.replace` plus the `finally` unlink; `atomic_write`
handles `str` and `bytes`, `atomic_save` handles the store-relative parquet family.
One `os.replace` in the tree (plus `journal.py`'s and, until authorized, `advise.py`'s).

Two latent bugs are fixed by the migration rather than separately, and both are named
in the commit because a silent fix is a fix nobody can review:

- **`presser_log.py:89` shares one `.tmp`.** Every other site in the tree carries the
  pid, and the comment explaining why is copy-pasted at eight of them: two writers
  sharing one temp each unlink the other's file and the loser's `os.replace` raises
  `FileNotFoundError`. The presser log is written by a scheduled snapshot job and by a
  hand `gaffer snapshot`, which is exactly two writers.
- **`understat.py:290` and `chip_scenarios.py:86` have no `try/finally`**, so a write
  that raises between `write_text` and `os.replace` leaves the temp file behind for
  ever. `understat`'s cache directory is permanent by design, which makes an orphan
  there permanent too.

### A2 — the migration invalidates two assertions in a protected file, and there is no honest way around it

`tests/test_v9c_degradation.py:339-375` holds two tests that read module source:

```python
source = inspect.getsource(advise_mod)
start = source.index('f"gw{gw}-advice.json"')
window = source[start - 600:start + 600]
assert "os.replace" in window
assert "os.getpid()" in window
assert ".tmp" in window
```

and

```python
source = inspect.getsource(digest_mod)
assert "os.replace" in source and "os.getpid()" in source
```

Both strings vanish from both modules the moment the write becomes
`atomic_write(path, text)`.

There is a tempting way to keep them passing: `inspect.getsource` returns comments, so
a comment reading *"through `gaffer.io.atomic_write`: pid-suffixed temp
(`os.getpid()`) plus `os.replace`"* satisfies both greps. **Rejected.** An assertion
that passes because of a comment is an assertion that has stopped testing anything,
and the next person to read it will believe the module still does the thing itself.

**Settled: Task 4 is a STOP that rewrites both assertions to follow the idiom to where
it moved.** The *claim* each test defends is unchanged — the advice artifact is
written atomically, and the reference implementation it borrowed from still exists —
so the rewrite is a redirection, not a weakening: the source grep moves onto
`gaffer.io`, and each of the two modules gains an assertion that it calls the helper
rather than writing the file itself. That is a stronger test than the one it replaces,
because "calls `atomic_write`" cannot be satisfied by a comment.

### A3 — §2.2's canonical module holds two of the three names, and the merge is a unit conversion at four read sites

The spec says *"Canonical: `optimize/differentials.py` exports `DIFFERENTIAL_EO`,
`ALTERNATIVE_EO`, `TEMPLATE_EO` in fraction units"*. Two of the three are there and
one is not:

| Name | `advise.py` | `optimize/differentials.py` |
| --- | --- | --- |
| `DIFFERENTIAL_EO` | `0.3` (L461) | `30.0` (L22) |
| `TEMPLATE_EO` | `0.7` (L464) | **absent** |
| `ALTERNATIVE_EO` | **absent** | `20.0` (L25) |

The two `DIFFERENTIAL_EO`s are the same threshold on the same quantity — rival/league
effective ownership — in different units, which is the whole justification for merging
them. `TEMPLATE_EO` is *moved into* `differentials.py`, not found there, and the plan
says so rather than letting an implementer hunt for it.

**Every reader, and the unit of the quantity it compares against:**

| # | Reader | Line | Compared quantity | Unit today | After |
| --- | --- | --- | --- | --- | --- |
| 1 | `advise.transfer_tag` | 478 | `eo = (eo_pct or 0.0) / 100.0` | **fraction** | unchanged — already divides |
| 2 | `advise.transfer_tag` | 480 | same `eo` | **fraction** | unchanged |
| 3 | `differentials.captain_table` | 50 | `df["league_eo"]` | **percent** | `× 100` at the read site |
| 4 | `differentials.transfer_alternatives` | 73 | `df["league_eo"]` | **percent** | `× 100` at the read site |

`threat_board`'s `min_eo: float = 50.0` (L79) is a **parameter default, not a
constant**, it is percent, and it is not one of the three names. It is left alone and
named here so nobody "tidies" it into the set.

**Settled: the constants become fractions in `differentials.py`; its own two readers
multiply by 100 at the comparison.** Multiply at the read site rather than divide the
column, because `league_eo` is on the returned frame — `captain_table` and
`transfer_alternatives` both emit it — and dividing it would change a served number.
The conversion is `DIFFERENTIAL_EO * 100`, evaluated in the comparison, with a comment
saying which side is which unit.

The spec's second test — *"a grep-style test that no other module defines a name
ending in `_EO` with a numeric literal"* — has exactly two names in the tree that are
not the three (`FIELD_EO_PATH`, `FIELD_EO_COLS` in `data/field.py`), and neither is a
numeric literal, so the grep is written to match `= <number>` rather than the bare
suffix.

### A4 — §2.3 is one keyword and two protected pins, and v11 already refused it once

`latest_field_eo(gw=None, *, season=None)` has taken `season` since v10b
(`data/field.py:202-250`); the guard, the "no fallback" rule and the reasoning are
already written in the function. What §2.3 asks for is that the keyword become
**required**, and that `load_field_eo()` filter too.

Three call sites:

| Caller | Line | Today | After |
| --- | --- | --- | --- |
| `web/field_frame.py` | 196 | `latest_field_eo(gw, season=season)` | unchanged — already seasoned |
| `web/routers/players.py` | 149 | `latest_field_eo()` | `latest_field_eo(season=load_config().current_season)` |
| (tests) | — | see below | see below |

The blockers are both protected:

- `tests/test_v10b_degradation.py:123-133`,
  `test_the_explorers_own_call_is_unchanged`, whose docstring is *"`routers/players.py`
  calls `latest_field_eo()` with no arguments and must keep getting the largest
  gameweek in the file, season or no season"* and whose body asserts exactly that,
  over a two-season fixture.
- `tests/test_v8c_degradation.py:72`, `assert latest_field_eo() == {}` on a bare tree.

v11's plan A2 looked at this same line, wanted it, and refused: *"Closing it means
moving a protected pin for a bug that cannot fire for eleven months."* v12 §2.3 orders
it closed, which is authorization to plan it, not authorization to make the edit.

**Settled: Task 6 is a STOP with both files enumerated.** v10b's test is *rewritten*
rather than deleted — its subject was the explorer's call, and the explorer's call is
what changed, so the new assertion is that the explorer passes `current_season` and
gets this season's row rather than last season's larger gameweek. That is the bug the
original test was standing next to. v8c's is a one-word edit: `latest_field_eo()`
becomes `latest_field_eo(season="2026-27")` and still returns `{}`, because the tree
is bare.

Two unprotected tests call it bare and are updated in the same task without ceremony:
`tests/test_v10b_field_season.py:52,83` and `tests/test_field_store.py:126,133,144`.

### A5 — the rollover guard has two halves and only one of them may touch the network

§2.4 asks `refresh` to compare the API bootstrap's season with `config.current_season`,
and the `meta` router to expose `season_ok`. The first is straightforward: `refresh`
already holds `client.get_bootstrap()`'s payload one frame down
(`data/live.py:157`), so the comparison costs no extra call.

The second cannot be done the same way. `routers/meta.py`'s module docstring is
*"Everything here is disk-only except the explicit data-refresh job"*, and `/api/health`
is polled by a tab. A network call there would make a page load depend on the FPL API
being up, which is the opposite of what a health page is for.

**Settled: the served half reads the banked events snapshot,
`data/live/events.parquet`, which `save_snapshots` writes on every refresh and which
carries `deadline_time` (`data/bootstrap.py:93-113`).** So `/api/health` answers "the
last refresh ingested season X; your config says Y", which is the honest thing a
disk-only endpoint can say and is exactly the state that matters — a mismatch means
the data on disk is not the data the config describes.

**Deriving the season from the events.** FPL's own bootstrap carries no season string.
The rule: take the **minimum** deadline year across the events (GW1's, which is
August), call it `Y`, and the season is `f"{Y}-{(Y + 1) % 100:02d}"`. Minimum rather
than GW1's row specifically, because a partially-published season can be missing rows
and `min` degrades to the earliest week there is. An events frame with no parseable
deadline yields `None`, and `None` is **not** a mismatch — it is "cannot tell", and a
red banner drawn from "cannot tell" is a false alarm on a cold clone.

### A6 — §2.5's "every fetched row is degraded" is a per-gameweek marker, and there is a second overwrite hazard the spec does not name

`track_pens` never raises. Its degraded marker is per gameweek, not per row:
`safe_gw_block` (`pen_tracker.py:200-210`) returns `{"gw": N, "error": str(exc)}` for a
week that would not read, and `track_pens` already partitions them
(`good` / `broken`, L275-283).

So the spec's condition, translated: `report["gws"]` is non-empty and **every** block
in it carries `"error"`.

The hazard the spec does not name: `track_pens` also returns an **empty** report — no
gameweeks at all, one note — when `data/live/player_gw.parquet` or the events file is
missing (L263-267), or when no gameweek is finished (L270-272). Writing that over a
good `reports/pen_tracker.json` loses a season's tracking to a missing parquet, which
is the same failure with a different cause.

**Settled: the refusal fires on both, it lives in the CLI, and it names which case it
is.** In the CLI because that is where `calibrate_noise`'s refusal lives
(`cli.py:498-511`) and §2.5 says to mirror it — and because `save_tracker` is a dumb
writer that other things may one day want to call with a deliberately empty report.
The two messages differ:

```
track_pens: refused to overwrite reports/pen_tracker.json: all 3 rows degraded
track_pens: refused to overwrite reports/pen_tracker.json: the report is empty
  (no live season on disk — run `gaffer refresh` first)
```

and **neither fires when there is no existing tracker to protect** — a first run on a
cold clone must write its empty report, or the file never comes into existence.
`calibrate_noise` gets this right the same way: it reads the destination first and only
refuses if something is already there.

### A7 — there is no `[solver]` section: the knob goes in `[optimizer]`, by orchestrator ruling

`config.example.toml` already has `[optimizer]`, and it holds `horizon`, `decay`,
`bench_weight`, `ft_value`, `itb_value`, `hit_cost`, `ft_use_penalty`, `bench_curve` —
every solver knob this project has. §2.6 asks for `[solver] top_n`, §3.4 for `[solver]
price_timing`, and §6.2's Settings whitelist names `top_n` and `price_timing` beside
`horizon` and `itb_value`. So the spec puts solver knobs in two sections for one
subject.

**Settled by the orchestrator (2026-09-02): no new section. `top_n` goes in
`[optimizer]`, keeping the spec's key name.** This plan's earlier draft followed the
spec's `[solver]` on the grounds that renaming it would desynchronise W2 and W5; the
ruling reverses that, so **W2 §3.4's `price_timing` and W5 §6.2's whitelist read from
`[optimizer]` too** — that is a cross-workstream consequence, not a W1-local one, and it
is recorded here because W1 is the workstream that establishes the section.

**And the ruling changes the implementation, not just the name.** `load_config`
**splats** `[optimizer]` — `**raw.get("optimizer", {})` at `config.py:145` — where
`[odds]`, `[league]`, `[news]` and `[digest]` are read key by key. Three consequences,
and an implementer who misses the first will name the field wrong:

1. **The dataclass field must be called `top_n`, not `solver_top_n`.** The splat passes
   the TOML key straight through as a keyword argument, so the field name *is* the key
   name. (`[backup]` and `[web]`, which are new sections, are still read key by key —
   the splat applies to `[optimizer]` alone.)
2. **A dict-valued splatted field is not new here.** `bench_curve: list[float] | None`
   is already a non-scalar read this way, which is the precedent that makes the ruling
   cheap.
3. **The splat does no validation, so the forgiving read happens elsewhere.** A
   malformed `top_n` in `[optimizer]` reaches `Config.top_n` exactly as written — the
   merge-over-default that turns a typo into the shipped value lives in the module-level
   `optimizer_top_n()` reader, which is what `build_pool` calls and what decides an
   actual solve. `Config.top_n` is what W5's Settings tab will edit. The two are pinned
   against each other in Task 9's tests so the difference cannot rot into a
   disagreement.

### A8 — the config-field pin is v10b's route-pin residual, repeating, and W1 pays it the same way v11 did

W1 adds five `Config` fields. `len(dataclasses.fields(Config)) == 48` is asserted in
**eight** places:

| # | File | Line | Form | Protected? |
| --- | --- | --- | --- | --- |
| 1 | `tests/test_v8f_degradation.py` | 301 | `assert len(names) == 48` | **yes** |
| 2 | `tests/test_v8g_degradation.py` | 283 | `assert len(names) == 48` | **yes** |
| 3 | `tests/test_v9c_degradation.py` | 323 | `assert len(dataclasses.fields(Config)) == 48` | **yes** |
| 4 | `tests/test_v9d_degradation.py` | 421 | same | **yes** |
| 5 | `tests/test_v10_degradation.py` | 422 | same | **yes** |
| 6 | `tests/test_v10b_degradation.py` | 266 | same | **yes** |
| 7 | `tests/test_v11_degradation.py` | 330 | same | **yes** |
| 8 | `tests/test_v10_config_providers.py` | 86 | same | no |

This is the identical shape v10b hit with routes and v11 retired: an **absolute** count
in seven protected files, so that any cycle entitled to add a config key must first buy
seven authorizations. `tests/test_v10_config_providers.py`'s module docstring is the
cost, written down at the time: v10 **abandoned a designed config field** because
*"tests/test_v9c_degradation.py:323 and tests/test_v9d_degradation.py:421 both pin
`len(dataclasses.fields(Config)) == 48`, both files are protected, and the plan's own
Task 2 pre-registered this grep as a stop."* A pin that changes a design is a pin
charging more than it is worth.

**Settled: Task 15 is a STOP that applies v11's route-pin restructure to the config
pin, verbatim in method.** Each historical file's absolute count becomes the by-name
claim that cycle is entitled to make about its own keys — and in five of the eight
files **that claim is already written on the line above**, which is what makes this a
deletion rather than an invention:

- `test_v8f_degradation.py:296-300` already asserts `"digest_notify" in names` and that
  no other `watch`/`digest`/`price_log` name exists. The count on L301 adds nothing its
  neighbours do not already say.
- `test_v8g_degradation.py:277-281` already asserts no `band`/`uncertainty`/`confidence`
  name exists.
- `test_v10_config_providers.py:87-88` already asserts `news_lineup_providers` is absent.
- `test_v10_degradation.py:423-424` already asserts `lineup_providers()` returns the
  default.
- `test_v9c/v9d/v10b/v11` have the bare count and nothing else, so each gains the
  one-line by-name claim its docstring already makes in prose.

The single absolute pin moves to `tests/test_v12_w1_degradation.py` and reads 53, with
a rail asserting it is the only one — the same rail v11 wrote for routes.

**Unlike v11, W1 cannot do this against an unchanged number.** v11 restructured the
route pin in a cycle that added no route, deliberately, so every assertion kept its
verdict. W1 adds five keys and must restructure in the same cycle, because doing it
first would mean a separate authorization round for a no-op. So the diff asks the
reviewer two questions at once, and the mitigation is that **the count moves in exactly
one file** — the seven others lose a number rather than gaining a different one, and
each by-name replacement is checkable against its own docstring without knowing what 53
is.

### A9 — the backup set as specced misses the only irrecoverable directory in the tree

Measured, today:

| Path | Size | In §2.1's set? | Recoverable if lost? |
| --- | --- | --- | --- |
| `data/live/` | 960 K | yes | partly — the logs are not |
| `reports/` | 1.5 M | yes | no — banked grades are never re-derived |
| `models/` | 14 M | yes | yes, by `gaffer train` (hours) |
| `data/history/` | 3.3 M | no | yes, by `gaffer build-history` |
| `data/raw/field/` | 228 K | **no** | **no** |
| `data/raw/tier_eo/` | 8 K | **no** | **no** |
| `data/raw/league/` | 28 K | no | yes, from the FPL API |
| `data/raw/news/` | 67 M | no | mostly not, but see below |
| `data/raw/understat/` | 12 M | no | yes, by re-scraping (slow) |
| `data/raw/vaastav/` | 24 M | no | yes, by download |
| `data/raw/*.json` snapshots | ~34 M | no | n/a — they *are* the archive of calls |

The spec's sentence *"field EO samples live in `data/live/field_eo_log.parquet`, so
they are covered"* is half right. The **log** is there. The **sampled squads** are
not: `save_field_sample` writes `data/raw/field/<season>/gw<N>.json`
(`data/field.py:42-44,65-89`), and `data/field.py:43` says out loud why they live
under `raw/` — *"these are raw API payloads, not derived frames."* A past gameweek's
top-10k picks cannot be fetched again from anywhere, and W4 §5.3's rank-distribution
simulation is specified to read them.

**Settled: the archive is `data/live/`, `reports/`, `models/`, `data/raw/field/` and
`data/raw/tier_eo/`.** The two additions are 236 KB against a 16 MB archive. Everything
else stays out, and the README says which of them is recoverable by which command, so
the omission is a documented decision rather than a gap.

`data/raw/news/` is the awkward one and it stays out: 67 MB is four times the rest of
the archive combined, it is a scrape cache, and the *derived* thing that matters — the
availability corpus a news model will train on — is `data/live/availability_log.parquet`
and `data/live/presser_log.parquet`, both inside the set. Recorded in the README rather
than left to be discovered.

**Sizing:** ~16.5 MB uncompressed, so `keep = 14` is on the order of 100-200 MB of
archives depending on how parquet compresses. Worth saying in the README next to the
`keep` key, because a user who points `--to` at a synced folder should know.

### A10 — `gaffer tidy` reclaims 54 KB today, and the 34 MB next door is out of scope

§2.7's first target is *"`data/live/backtest_log_*.parquet` not referenced by any
`reports/*` ledger"*. Measured against the actual tree:

- 33 files match `data/live/backtest_log_*.parquet`.
- The convention that defines "referenced" is `scripts/v7b_replay.py:37`: a run writes
  `live/backtest_log_v7b_<tag>.parquet` **and** `reports/v7b_<tag>.json`, as a pair.
- 28 of the 33 have their companion report. **Five do not**, totalling **54 KB**:

```
backtest_log_v7b_v8a-g5-main.parquet
backtest_log_v7b_v9c-main-s1876.parquet
backtest_log_v7b_v9c-main-s1901.parquet
backtest_log_v7b_v9c-main-s20260827.parquet
backtest_log_v7b_v9d-main-s20260827.parquet
```

Three findings the spec does not have, and all three change the rule:

1. **`data/live/backtest_log.parquet` — no tag — must never be touched.** It is the
   shared log `run_backtest` writes (`backtest.py:624`) and `/api/history` reads
   (`routers/meta.py:147-148`). The glob `backtest_log_*.parquet` does not match it,
   which is luck rather than design, so the rail asserts it explicitly.
2. **The rule scopes to the `v7b_` prefix.** `scripts/s2_replay.py:71` writes
   `live/backtest_log_s2_<mode>.parquet` and writes **no companion report at all** — its
   evidence is an `S2_ARM_DONE` line in `logs/`. A rule reading "no report ⇒ orphan"
   deletes every S2 arm log the moment it is written. None exist today; the fix costs
   one prefix.
3. **The prize is not here.** `data/raw/` is 150 MB, of which roughly 34 MB is
   timestamped API snapshots (`bootstrap-*.json` at 1.7 MB × 20, `fixtures-*`, `odds-*`,
   `ags-*`, `entry-*`) that accumulate on every call and that nothing prunes, plus 67 MB
   of `raw/news/`. §2.7's two targets total 54 KB of backtest logs and 224 KB of
   `logs/`.

**Settled: implement §2.7's two targets exactly, and record the 34 MB as a finding
rather than widening the command.** Silently adding `data/raw/` to a delete command is
the single most dangerous unrequested change available in this cycle. It goes in the
README's residuals and the ROADMAP so the orchestrator can spec it deliberately.

**And two files `logs/*.log` must never take:** `logs/advise.log` is read by
`/api/health` (`routers/meta.py:38`, `LaunchdHealth.last_line`), and any log a launchd
job currently appends to is a live file handle. The rule is "older than the cutoff",
and an actively-appended log is by definition not older than the cutoff — but
`advise.log` is dated 27 Aug and the default cutoff is 30 days, so it will qualify in
one week's time and the health page will go blank. It is excluded by name.

### A11 — LAN write protection is a middleware and a keyword, not a per-route dependency

§2.8 requires a header on **every** non-GET route when `--lan` is used. There are
~10 non-GET routes across nine routers and one of them (`whatif.py`) is protected, so a
per-route `Depends` is both a wide diff and an impossible one.

**Settled: one `@app.middleware("http")` in `create_app`, and `create_app` gains a
keyword-only argument.**

```python
def create_app(*, token: str | None = None) -> FastAPI:
```

`None` means no enforcement, which is every existing caller and every existing test —
so the entire suite is untouched and `create_app()` still means what it meant. The CLI
passes a token only under `--lan`.

The middleware refuses with **403**, not 401: 401 invites a browser credential prompt
for a scheme this app does not implement. `OPTIONS` and `HEAD` pass with `GET`, because
a preflight that fails closed makes every write look like a network error rather than a
refusal.

**Token source:** `[web] token` in config (a new `Config.web_token` field), or — when
unset — `secrets.token_urlsafe(16)` generated at CLI startup and printed **once**,
inside the existing LAN banner beside the QR code. Printed once and not stored: writing
a generated token into `config.toml` would be the UI writing config, which spec §8
forbids by name.

**Front end:** `client.ts`'s `request()` is the one chokepoint every call goes through
(`apiGet`, `apiPost`, `apiDelete` all delegate to it), so the header is added there.
The token is read from `?token=` on first load and stored under `gaffer-token`,
following `useTheme`'s `THEME_KEY` idiom verbatim, `try/catch` included, because a
browser refusing site data must degrade to "this tab works, the next one will not"
rather than throwing.

### A12 — the "as of" strip mounts once, in `AppShell`, and that has three consequences worth writing down

§2.9 says *"one component rendered at the top of every hub"*. Three places could host it
and two are wrong:

- **In each of the six hubs** — six mounts, six fetches of one endpoint, and six places
  to forget it. It is also seven, not six: `/league/rival/:id` is a route with no hub
  wrapper.
- **In `kit/PageHeader`** — every hub uses it, but it is also a *component*, remounting
  on every navigation, so the strip would re-fetch on every hub change and flicker.
- **In `kit/AppShell`** — wraps `<Routes>` (`App.tsx:12-24`), stays mounted across every
  navigation, and covers the rival-detail route for free. One mount, one fetch.

**Settled: `AppShell`, above `{children}`, in both the mobile and desktop branches.**
And the three consequences:

1. **`kit/AppShell.test.tsx` does not mock `../api/client`.** It renders `AppShell`
   directly, so the strip would issue a real `fetch` into jsdom. The task adds the mock
   that every other suite already has.
2. **`AppShell.test.tsx:24` asserts `screen.getAllByRole('link')).toHaveLength(6)`.**
   The strip must contain **no anchors**. It is text and colour; there is nothing to
   link to.
3. **The strip is its own empty state.** A failed fetch renders every row as "never" in
   grey rather than disappearing, because a strip that vanishes on a cold clone teaches
   the reader that its absence means "fine".

**The five sources, and where each one's timestamp actually comes from** — the spec
says "file mtimes and the ledgers' latest timestamps" and does not say which is which:

| Row | Source | Kind |
| --- | --- | --- |
| refresh | `data/live/player_gw.parquet` | mtime |
| odds | newest `data/live/odds/gw*.parquet` | mtime — the same file `/api/health` already grades |
| field | `data/live/field_eo_log.parquet` | mtime |
| advise | newest `reports/gw*-advice.json` | mtime |
| backup | newest `<backup dir>/gaffer-*.tar.gz` | mtime |

All five are mtimes. No ledger timestamp is used, and the reason is that every one of
these five artifacts is rewritten whole by the job that produces it, so the mtime *is*
the run stamp — whereas a timestamp parsed out of a file's contents can be stale in a
file that was rewritten, which is a subtler lie than a stale mtime. Ages are computed
server-side and served as hours, so the colouring rule (green < 24, amber < 72, red
otherwise, grey for absent) is one implementation and not two.

### A13 — the MCP `whatif` tool cannot wrap the router function, and the dependency resolves to `mcp==2.1.1`

§2.10 says each tool is *"a thin wrapper over the existing router function with the same
pydantic response models"*. True for five of the six:

| Tool | Wraps | Response model |
| --- | --- | --- |
| `projections` | `routers.players.players(position, team, search, sort)` | `list[PlayerRow]` |
| `explain` | `routers.players.explain(code)` | `PlayerExplain` |
| `ledger` | `routers.review.review()` | `Review` |
| `freshness` | `routers.meta.freshness()` (new, Task 13) | `Freshness` |
| `health` | `routers.meta.health()` | `Health` |
| `whatif` | **not the router function** | **none exists** |

`POST /api/whatif` is `status_code=202, response_model=JobAccepted`
(`routers/whatif.py:182-183`): it queues a job on the runner and returns an id. An MCP
tool returning a job id would be useless, and polling one from a stdio server would put
the runner's lifecycle inside a subprocess.

The synchronous body exists and is exported: `solve_whatif(req: WhatIfRequest, gw: int)
-> dict` (`whatif.py:110`), which returns the baseline, the constrained solve and their
diff. `whatif.py` is protected and **importing is not editing**.

**Settled: `whatif` wraps `solve_whatif`, returns its `dict`, and the tool's docstring
says it is read-only and starts no job.** The spec's "same pydantic response models"
holds for the five that have one; the sixth returns the dict the job body returns,
which is the same payload the UI eventually renders.

**The dependency, resolved rather than assumed:**

```bash
.venv/bin/python -c "import mcp"          # ModuleNotFoundError
grep -n mcp pyproject.toml                # nothing
```

Not installed, not pinned. Resolved against this project's current dependency set:

```
mcp==2.1.1
```

and it brings fifteen transitive packages that are not in the tree today —
`mcp-types`, `httpx2`, `httpcore2`, `sse-starlette`, `python-multipart`, `jsonschema`,
`jsonschema-specifications`, `referencing`, `rpds-py`, `attrs`, `cryptography`, `cffi`,
`pyjwt`, `opentelemetry-api`, `truststore` — and **bumps `pydantic` 2.13.4 → 2.13.5**.
`httpx2` is a separate distribution from the `httpx` 0.28.1 this project uses; they
coexist. `starlette` and `uvicorn` resolve to the versions already installed.

The pydantic bump is the only thing in that list that touches shipped behaviour (every
schema in `web/schemas.py` is a pydantic model), which is why Task 14's verification
runs the **whole** suite rather than only the MCP tests.

### A14 — three pins, two of which move, and the route one moves in the file v11 built for it

Routes 45 → **46**: `GET /api/meta/freshness`, the cycle's only new path. It is added to
`routers/meta.py`, whose `APIRouter(prefix="/api")` makes the decorator
`@router.get("/meta/freshness")`.

Because v11 finished the route-pin restructure, the number lives in exactly one place:
`tests/test_v11_degradation.py:349`. That file is protected, so moving 45 → 46 is an
edit to it — the toll v11 reduced from four files to one. It is folded into Task 15's
STOP rather than given a sixth STOP of its own, since it is the same kind of edit to the
same kind of file for the same reason.

`test_v11_degradation.py:350-351` also asserts no path starts with `/api/board`,
`/api/season` or `/api/compare`. `/api/meta/freshness` collides with none of them, so
that assertion is left exactly as it is.

Config 48 → **53**: `backup_dir`, `backup_rsync_target`, `backup_keep`, `top_n`,
`web_token`. `top_n` sits in the existing `[optimizer]` section by orchestrator ruling
(A7), which is why it is named for its TOML key rather than for its subject. Job kinds 12 → **12**: `backup`, `tidy` and `mcp` are CLI commands. Two of
them could plausibly be job kinds one day; none is today, and a thirteenth kind would
also need a row in `ABANDON_TIMEOUT_S` or `SLOW_ABANDON_KINDS`, which
`test_v9d_degradation.py` pins as jointly exhaustive and which is protected.

### A15 — `journal.py` keeps its own copy, and the plan says so rather than leaving a hole

`journal.py:225-229` is the twentieth site. `journal.py` is **import-only** for this
cycle, so it is not migrated, and after W1 the tree holds `gaffer/io.py`'s single
`os.replace` plus `journal.py`'s.

**Settled: it is left, it is recorded as a residual in the README and the ROADMAP, and
Task 16's rail counts `os.replace` sites and asserts the surviving set by name** — so a
twenty-first copy cannot appear quietly, and the one exception is visible in the
assertion rather than tolerated by a `>=`.

Two other things the rail must tolerate rather than fail on: `advise.py`'s copy if Task
4's STOP is not authorized, and the `dataclasses.replace` calls in `review.py:905`,
`cli.py:35` and `web/job_kinds.py:74`, which are a different function with a similar
name.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/io.py` | Create | T1: `atomic_path`, `atomic_write`, `atomic_save`. |
| `tests/test_v12_io.py` | Create | T1: the primitive, both wrappers, the failure paths. |
| `src/gaffer/digest.py` | Modify (L82-90) | T2: migrate. |
| `src/gaffer/pen_tracker.py` | Modify (L297-307) | T2: migrate. |
| `src/gaffer/evaluation.py` | Modify (L263-273) | T2: migrate. |
| `src/gaffer/overrides.py` | Modify (L112-120) | T2: migrate. |
| `src/gaffer/watchlist.py` | Modify (L95-103) | T2: migrate. |
| `src/gaffer/drafts.py` | Modify (L86-95) | T2: migrate. |
| `src/gaffer/sensitivity.py` | Modify (L86-95) | T2: migrate. |
| `src/gaffer/review.py` | Modify (L1093-1107) | T2: migrate, inside the lock. |
| `src/gaffer/league_sim.py` | Modify (L677-695) | T2: migrate, inside the lock. |
| `src/gaffer/data/my_entry.py` | Modify (L76-90) | T2: migrate. |
| `src/gaffer/data/field.py` | Modify (L99-107) | T2: migrate the sample writer. |
| `src/gaffer/data/understat.py` | Modify (L288-293) | T2: migrate; gains the `finally` it never had. |
| `src/gaffer/data/chip_scenarios.py` | Modify (L72, L78-88) | T2: the private helper is deleted. |
| `src/gaffer/web/routers/assets.py` | Modify (L130-147) | T2: migrate the bytes writer. |
| `tests/test_digest.py` | Modify (L465-480) | T2: the `os.replace` spy follows the idiom. |
| `tests/test_review_ledger.py` | Modify (L350-360) | T2: same. |
| `tests/test_watchlist.py` | Modify (L145-160) | T2: same. |
| `tests/test_v10b_chip_scenarios.py` | Modify (L100-115) | T2: same (not a degradation file). |
| `tests/test_understat.py` | Modify (L392-398) | T2: the source grep follows the idiom. |
| `src/gaffer/snapshot.py` | Modify (L124-136) | T3: migrate. |
| `src/gaffer/price_log.py` | Modify (L126-136) | T3: migrate. |
| `src/gaffer/data/field.py` | Modify (L182-192) | T3: migrate. |
| `src/gaffer/data/news/presser_log.py` | Modify (L88-96) | T3: migrate; gains the pid it never had. |
| `src/gaffer/advise.py` | **Modify — PROTECTED** | T4: migrate (STOP 1). |
| `tests/test_v9c_degradation.py` | **Modify — PROTECTED** | T4: the two source pins follow the idiom (STOP 1). |
| `src/gaffer/optimize/differentials.py` | Modify (L22-27, L50, L73) | T5: the canonical three, in fractions. |
| `src/gaffer/advise.py` | **Modify — PROTECTED** | T5: delete L461-465, extend the L68 import (STOP 2). |
| `tests/test_v12_eo_constants.py` | Create | T5: the range assertion and the grep. |
| `src/gaffer/data/field.py` | Modify (L195-250) | T6: `season` required, `load_field_eo` filters. |
| `src/gaffer/web/routers/players.py` | Modify (L147-151) | T6: pass `current_season`. |
| `tests/test_v10b_degradation.py` | **Modify — PROTECTED** | T6: the explorer's call changed (STOP 3). |
| `tests/test_v8c_degradation.py` | **Modify — PROTECTED** | T6: one keyword (STOP 3). |
| `tests/test_v10b_field_season.py`, `tests/test_field_store.py` | Modify | T6: unprotected callers. |
| `tests/test_v12_field_season_required.py` | Create | T6: two seasons, overlapping elements. |
| `src/gaffer/data/bootstrap.py` | Modify (after L113) | T7: `season_from_events`. |
| `src/gaffer/cli.py` | Modify (L100-110) | T7: `refresh` refuses on mismatch. |
| `src/gaffer/web/routers/meta.py` | Modify (L155-215) | T7: `season_ok` on Health. |
| `src/gaffer/web/schemas.py` | Modify (`Health` L816-824) | T7: three fields. |
| `frontend/src/hubs/model/HealthTab.tsx` | Modify | T7: the red banner. |
| `tests/test_v12_season_rollover.py` | Create | T7. |
| `src/gaffer/cli.py` | Modify (L571-582) | T8: the `track-pens` refusal. |
| `tests/test_v12_track_pens_refusal.py` | Create | T8. |
| `src/gaffer/config.py`, `config.example.toml` | Modify | T9: `[optimizer] top_n`. |
| `src/gaffer/optimize/milp.py` | **Modify — PROTECTED** | T9: one line-group (STOP 4). |
| `src/gaffer/web/routers/meta.py`, `schemas.py`, `HealthTab.tsx` | Modify | T9: pool sizes on Health. |
| `tests/test_v12_top_n.py` | Create | T9. |
| `src/gaffer/backup.py` | Create | T10: the archive, the rsync, the prune. |
| `src/gaffer/cli.py` | Modify | T10: `gaffer backup`. |
| `scripts/com.gaffer.backup.plist`, `scripts/install_automation.sh` | Create/Modify | T10. |
| `tests/test_v12_backup.py` | Create | T10: the restore test the gate names. |
| `src/gaffer/tidy.py` | Create | T11: the two target sets. |
| `src/gaffer/cli.py` | Modify | T11: `gaffer tidy`. |
| `tests/test_v12_tidy.py` | Create | T11. |
| `src/gaffer/web/app.py` | Modify (L47-52) | T12: `token=` and the middleware. |
| `src/gaffer/cli.py` | Modify (L584-635) | T12: generate, print, pass. |
| `frontend/src/api/client.ts` | Modify | T12: the header and the store. |
| `tests/test_v12_lan_token.py`, `frontend/src/api/token.test.ts` | Create | T12. |
| `src/gaffer/web/routers/meta.py` | Modify | T13: `GET /api/meta/freshness`. |
| `src/gaffer/web/schemas.py` | Modify | T13: `Freshness`, `FreshnessRow`. |
| `frontend/src/kit/FreshnessStrip.tsx` | Create | T13. |
| `frontend/src/kit/AppShell.tsx` | Modify (L38-80) | T13: mount once, both branches. |
| `frontend/src/kit/AppShell.test.tsx` | Modify (L1-15) | T13: the client mock (A12). |
| `src/gaffer/mcp_server.py` | Create | T14: six tools. |
| `pyproject.toml`, `uv.lock` | Modify | T14: `mcp>=2.1.1`. |
| `tests/test_v12_mcp.py` | Create | T14. |
| seven protected degradation files | **Modify — PROTECTED** | T15: the config pin (STOP 5). |
| `tests/test_v12_w1_degradation.py` | Create | T15 + T16: the sole pins, the rails. |
| `README.md`, `docs/GUIDE.md` | Modify | T17. |
| the spec's §2 | Modify | T18: the gate checklist. |
| `docs/superpowers/ROADMAP.md` | Modify | T18. |

---

## Task 1 — one atomic write, three shapes of caller

**Files:**
- Create `src/gaffer/io.py`
- Create `tests/test_v12_io.py`

**Read A1 before starting.** The helper is written to fit twenty existing call sites,
not to be elegant on its own. Three shapes exist in the tree and all three must go
through one `os.replace`.

- [ ] **Write the failing test.** Create `tests/test_v12_io.py`:

```python
"""One atomic write, and the three shapes of caller it has to fit.

Twenty sites in this tree write a file by putting it beside the destination and
renaming it. They fall into three families and the helper serves all three,
because a helper that only served the JSON one would leave the parquet writers
open-coding the same rename — which is how six copies became twenty.

The pid in the temp name is not decoration. Eight sites carry the same comment
explaining it: two writers sharing one ``.tmp`` each unlink the other's file in
their ``finally``, and the loser's ``os.replace`` then raises FileNotFoundError.
A nightly launchd job and a hand-run command are exactly two writers.

The ``finally`` is not decoration either. ``understat.py`` and
``chip_scenarios.py`` were written without one, so a write that raised between
the temp and the rename left the temp file behind for ever — permanently, in
understat's case, whose cache directory is never swept.
"""

from __future__ import annotations

import os

import pandas as pd
import pytest

from gaffer import io as gio


def test_text_lands_whole(tmp_path):
    path = tmp_path / "out.json"
    gio.atomic_write(path, '{"a": 1}')
    assert path.read_text() == '{"a": 1}'


def test_bytes_land_whole(tmp_path):
    """``routers/assets.py`` banks images; a str-only helper would have left
    that one site open-coded."""
    path = tmp_path / "shirt.png"
    gio.atomic_write(path, b"\x89PNG\r\n")
    assert path.read_bytes() == b"\x89PNG\r\n"


def test_the_parent_directory_is_created(tmp_path):
    path = tmp_path / "deep" / "deeper" / "out.json"
    gio.atomic_write(path, "{}")
    assert path.read_text() == "{}"


def test_the_temp_name_carries_the_pid(tmp_path):
    """Asserted on the name the context manager yields rather than on a
    leftover file, because there is never a leftover file to look at."""
    seen = []
    with gio.atomic_path(tmp_path / "out.json") as tmp:
        seen.append(tmp.name)
        tmp.write_text("{}")
    assert str(os.getpid()) in seen[0]
    assert seen[0].endswith(".tmp")
    assert seen[0].startswith("out.json.")


def test_no_temp_file_survives_a_successful_write(tmp_path):
    gio.atomic_write(tmp_path / "out.json", "{}")
    assert [p.name for p in tmp_path.iterdir()] == ["out.json"]


def test_no_temp_file_survives_a_failed_write(tmp_path):
    """The ``finally`` two of the twenty sites never had."""
    with pytest.raises(ValueError):
        with gio.atomic_path(tmp_path / "out.json") as tmp:
            tmp.write_text("half")
            raise ValueError("boom")
    assert list(tmp_path.iterdir()) == []


def test_a_failed_write_leaves_the_previous_file_exactly_as_it_was(tmp_path):
    """The whole point of the idiom, asserted once so the twenty call sites do
    not each have to."""
    path = tmp_path / "out.json"
    path.write_text("the old one")
    with pytest.raises(ValueError):
        with gio.atomic_path(path) as tmp:
            tmp.write_text("the new one")
            raise ValueError("boom")
    assert path.read_text() == "the old one"


def test_two_writers_do_not_share_a_temp_name(tmp_path, monkeypatch):
    """The failure the pid exists to prevent, reproduced by moving the pid."""
    names = set()
    for pid in (111, 222):
        monkeypatch.setattr(gio.os, "getpid", lambda pid=pid: pid)
        with gio.atomic_path(tmp_path / "out.json") as tmp:
            names.add(tmp.name)
            tmp.write_text("{}")
    assert len(names) == 2


def test_a_frame_lands_under_the_store_directory(tmp_path, monkeypatch):
    """The parquet family. ``store.DATA_DIR`` is read at call time, not bound
    at import, because four call sites say so in their docstrings: a test that
    redirects the data directory must redirect both paths together."""
    from gaffer.data import store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    gio.atomic_save(pd.DataFrame({"a": [1, 2]}), "live/thing.parquet")
    assert len(store.load("live/thing.parquet")) == 2


def test_a_failed_frame_write_leaves_the_banked_file_intact(tmp_path,
                                                            monkeypatch):
    """The reason the parquet writers rewrite through a temp at all: parquet
    has no append, so every daily write re-emits the whole log, and a write
    that died in place would cost a season to save an afternoon."""
    from gaffer.data import store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    gio.atomic_save(pd.DataFrame({"a": [1, 2]}), "live/thing.parquet")

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", boom)
    with pytest.raises(OSError):
        gio.atomic_save(pd.DataFrame({"a": [9]}), "live/thing.parquet")
    assert len(store.load("live/thing.parquet")) == 2
    assert not list(tmp_path.glob("live/*.tmp"))
```

Run it: `.venv/bin/pytest -q tests/test_v12_io.py` — every test fails on
`ModuleNotFoundError: gaffer.io`.

- [ ] **Implement `src/gaffer/io.py`:**

```python
"""One atomic write, for the twenty places that were doing it themselves.

Spec §1 and §2.11 (specs/2026-09-01-gaffer-v12-program-design.md). The spec
said six copies; there were twenty, in three families — JSON and text through
``write_text``, parquet through ``store.save``, and raw bytes — and a helper
serving only the first would have left the other two open-coded, which is how
six became twenty.

Two things in here are load-bearing and were arrived at the hard way by the
sites this replaces:

* **the pid in the temp name.** Two writers sharing one ``.tmp`` each unlink
  the other's file in their ``finally``, and the loser's ``os.replace`` then
  raises ``FileNotFoundError``. A nightly launchd job and a hand-run command
  are exactly two writers, and ``data/live/presser_log.parquet`` was written
  without a pid until this change;
* **the ``finally``.** A write that raises between the temp and the rename
  leaves the temp behind for ever otherwise. ``understat.py`` and
  ``chip_scenarios.py`` were both written without one, and understat's cache
  is permanent by design, so its orphans were too.

``os.replace`` is atomic within a directory on POSIX, which is why the temp is
always a *sibling* of the destination and never in ``/tmp``.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pandas as pd


@contextmanager
def atomic_path(path: Path | str) -> Iterator[Path]:
    """Yield a sibling temp path; replace ``path`` with it on a clean exit.

    The caller writes to the yielded path however it likes — text, bytes, a
    parquet writer, anything that takes a filename. On a clean exit the temp
    replaces the destination in one step; on any exception the destination is
    left exactly as it was and the temp is removed.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.{os.getpid()}.tmp")
    try:
        yield tmp
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write(path: Path | str, data: str | bytes) -> Path:
    """Write ``data`` whole, or leave what was there untouched."""
    dest = Path(path)
    with atomic_path(dest) as tmp:
        if isinstance(data, bytes):
            tmp.write_bytes(data)
        else:
            tmp.write_text(data)
    return dest


def atomic_save(frame: pd.DataFrame, rel: str) -> Path:
    """``store.save`` a frame at a store-relative path, atomically.

    ``store.DATA_DIR`` is read here rather than bound at import, so a test
    that redirects the data directory redirects the temp and the destination
    together — the trade four of the migrated call sites state in their own
    docstrings.
    """
    from gaffer.data import store

    dest = store.DATA_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_rel = f"{rel}.{os.getpid()}.tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(frame, tmp_rel)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest
```

`atomic_save` does not reuse `atomic_path`, deliberately: `store.save` takes a
*relative* path and joins it itself, so the temp name has to be built in the store's
vocabulary rather than the filesystem's. The duplication is four lines and the
alternative is a `store.save` that takes an absolute path, which is a change to a module
every reader in the tree uses.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_io.py
.venv/bin/pytest -q
```

The full suite must be unchanged: nothing imports `gaffer.io` yet.

- [ ] **Commit.**

```bash
git add src/gaffer/io.py tests/test_v12_io.py && git commit -m "$(cat <<'EOF'
feat: one atomic write, for the twenty places doing it themselves

The spec said six copies of the temp-file-plus-os.replace idiom. There are
twenty, in three families — text through write_text, parquet through store.save,
and raw bytes — so the helper serves all three. A helper that only served the
JSON writers would have left the parquet ones open-coding the same rename, which
is how six became twenty.

Two details are load-bearing and both were learned by the sites this replaces:
the pid in the temp name, because two writers sharing one .tmp each unlink the
other's file and the loser's os.replace raises; and the finally, because a write
that dies between the temp and the rename otherwise leaves the temp for ever.

No callers yet. They arrive in the next three commits.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the fourteen text and bytes writers

**Files:**
- Modify `src/gaffer/digest.py`, `pen_tracker.py`, `evaluation.py`, `overrides.py`,
  `watchlist.py`, `drafts.py`, `sensitivity.py`, `review.py`, `league_sim.py`
- Modify `src/gaffer/data/my_entry.py`, `data/field.py`, `data/understat.py`,
  `data/chip_scenarios.py`
- Modify `src/gaffer/web/routers/assets.py`
- Modify `tests/test_digest.py`, `tests/test_review_ledger.py`,
  `tests/test_watchlist.py`, `tests/test_v10b_chip_scenarios.py`,
  `tests/test_understat.py`

**Read A1's family-A table before starting.** Fourteen sites move here — the thirteen
unprotected family-A ones plus the single family-C bytes writer. **Ten of them are
mechanical. Four are not**, and those four have their own steps at the end.

- [ ] **The mechanical shape.** Every family-A site looks like this:

```python
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
```

and becomes:

```python
    atomic_write(path, json.dumps(payload, indent=1, allow_nan=False))
```

with `from gaffer.io import atomic_write` at the top and the local `import os` deleted
**only if nothing else in the module uses it** — check each with
`grep -n "os\." <file>` before deleting the import.

The per-site comment ("Per-writer temp name: two writers sharing one `.tmp` …")
**goes**, at every site. Its content now lives in `gaffer/io.py`'s docstring, and eight
copies of a paragraph explaining a helper's internals, sitting at the call sites of that
helper, is the documentation equivalent of the duplication this task removes. What each
site keeps is the sentence about *its own* file — why this artifact is written whole,
who reads it concurrently — because that part is local knowledge.

- [ ] **Do the ten straightforward ones**, in this order, running
`.venv/bin/pytest -q` after each so a break is attributable:
`digest.py`, `pen_tracker.py`, `evaluation.py`, `overrides.py`, `watchlist.py`,
`drafts.py`, `sensitivity.py`, `data/my_entry.py`, `data/field.py` (the **sample**
writer at L99-107 only — the parquet one at L182-192 is Task 3),
`web/routers/assets.py` (which passes `bytes`, so `atomic_write(path, data)` with no
change of shape).

- [ ] **`review.py` (L1093-1107) — the write is inside a lock and stays inside it.**
The lock spans the read-modify-write, not the rename, and the comment saying so is
correct and stays:

```python
    from gaffer import artifacts

    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = ledger_path()
    # The lock spans the read as well as the write: the race this guards is
    # the read-modify-write, not the rename, which was already atomic.
    with _ledger_lock(lock_path()):
        rows = [r for r in load_ledger() if int(r["gw"]) != int(row["gw"])]
        rows.append(dict(row))
        rows.sort(key=lambda r: int(r["gw"]))
        atomic_write(path, json.dumps({"gws": rows}, indent=1,
                                      allow_nan=False))
    return path
```

Note the `tmp = ...` line moves **into** the `with` block by disappearing. It used to sit
above it, which was harmless and is now impossible to get wrong.

- [ ] **`league_sim.py` (L677-695) — the same shape**, with `_HISTORY_LOCK` instead:

```python
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = history_path()
    # The lock spans the read as well as the write: the race this guards is
    # the read-modify-write, not the rename, which was already atomic.
    with _HISTORY_LOCK:
        rows = [r for r in load_sim_history() if int(r["gw"]) != int(gw)]
        rows.append({"gw": int(gw), "p_win": sim.p_win, "p_top3": sim.p_top3,
                     "exp_finish": sim.exp_finish, "run_at": str(run_at),
                     "n": sim.n, "seed": sim.seed})
        rows.sort(key=lambda r: int(r["gw"]))
        atomic_write(path, json.dumps({"gws": rows}, indent=1,
                                      allow_nan=False))
    return path
```

- [ ] **`data/understat.py` (L288-292) — this one gains a `finally` it never had.**
The three lines become one:

```python
        path.parent.mkdir(parents=True, exist_ok=True)
        # The date is re-applied on read rather than stored: it is a date
        # object, JSON has no such type, and the caller always knows it.
        atomic_write(path, rows.drop(columns=["date"]).to_json(
            orient="records"))
        return rows
```

The behaviour change is real and is in the commit message: this cache is permanent by
design (the docstring at L253-262 says so), so an orphaned temp here was permanent too.

- [ ] **`data/chip_scenarios.py` — the private helper is deleted, not wrapped.**
`_atomic_write` (L78-88) is this cycle's helper under a different name and with no
`finally`. Delete the whole function and change the one caller at L72:

```python
        _atomic_write(target, "\n".join(lines) + "\n")
```
becomes
```python
        atomic_write(target, "\n".join(lines) + "\n")
```

Its docstring's cross-reference — *"``field.py:100-107``'s reasoning"* — is now stale in
two ways (the reasoning moved, and `field.py:100` is about to move too), which is
exactly the rot this task exists to stop. It goes with the function.

- [ ] **Five tests reach into the idiom and must follow it.** None is protected; all
five patch or grep for `os.replace` in a module that no longer contains it:

| File | Line | Today | After |
| --- | --- | --- | --- |
| `tests/test_digest.py` | 471-477 | `monkeypatch.setattr("gaffer.digest.os.replace", spy)` | `"gaffer.io.os.replace"` |
| `tests/test_review_ledger.py` | 356 | `real = R.os.replace` | `from gaffer import io as gio; real = gio.os.replace` |
| `tests/test_watchlist.py` | 156 | `real_replace = os.replace`, patched on the module | patch `gaffer.io.os.replace` |
| `tests/test_v10b_chip_scenarios.py` | 109 | same shape | same |
| `tests/test_understat.py` | 392-398 | `assert "os.replace" in inspect.getsource(UnderstatClient.match_players)` | `assert "atomic_write" in ...` |

`test_understat.py`'s docstring keeps its claim word for word — *"a scrape killed
mid-write must leave either the old file or the new one, never a truncated one"* — and
gains a sentence saying the guarantee now comes from `gaffer.io.atomic_write`. The
assertion gets **stronger**, not weaker: `"atomic_write" in source` cannot be satisfied
by a comment mentioning `os.replace`, which is the trap A2 describes.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_digest.py tests/test_review_ledger.py \
  tests/test_watchlist.py tests/test_v10b_chip_scenarios.py \
  tests/test_understat.py tests/test_drafts.py tests/test_overrides.py \
  tests/test_sensitivity.py tests/test_league_sim.py
.venv/bin/pytest -q
```

**A failure in any `tests/test_*_degradation.py` means the migration was not
behaviour-preserving: stop and report.** Expect exactly one such failure, in
`tests/test_v9c_degradation.py`, and it is Task 4's — if it appears now, note it and
carry on; if anything *else* in a degradation file fails, stop.

- [ ] **Commit.**

```bash
git add src/gaffer/digest.py src/gaffer/pen_tracker.py \
  src/gaffer/evaluation.py src/gaffer/overrides.py src/gaffer/watchlist.py \
  src/gaffer/drafts.py src/gaffer/sensitivity.py src/gaffer/review.py \
  src/gaffer/league_sim.py src/gaffer/data/my_entry.py \
  src/gaffer/data/field.py src/gaffer/data/understat.py \
  src/gaffer/data/chip_scenarios.py src/gaffer/web/routers/assets.py \
  tests/test_digest.py tests/test_review_ledger.py tests/test_watchlist.py \
  tests/test_v10b_chip_scenarios.py tests/test_understat.py \
  && git commit -m "$(cat <<'EOF'
refactor: fourteen writers stop open-coding the rename

The JSON, text and bytes half of §2.11's migration. Every site keeps the
sentence about its own artifact — who reads it concurrently, why it is written
whole — and loses the paragraph explaining the helper's internals, which is now
in one place instead of eight.

Two behaviour changes, both fixes rather than side effects. understat's match
cache and chip_scenarios' TOML writer had no `finally`, so a write that raised
between the temp and the rename left the temp behind — permanently in understat's
case, whose cache is never swept. Both now get one.

chip_scenarios' private _atomic_write is deleted rather than wrapped: it was this
helper under another name, and its docstring pointed at a line in field.py that
this cycle also moves.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — the four parquet writers

**Files:**
- Modify `src/gaffer/snapshot.py` (L124-136)
- Modify `src/gaffer/price_log.py` (L126-136)
- Modify `src/gaffer/data/field.py` (L182-192)
- Modify `src/gaffer/data/news/presser_log.py` (L88-96)

**Read A1's family-B table.** These four differ from family A in one way that matters:
the path is *store-relative*, `store.save` joins it, and `store.DATA_DIR` must be read
at call time so a test that redirects it redirects both halves together. All four say so
in their own docstrings and all four are right.

- [ ] **The shape.** Each site's tail:

```python
    # Per-writer temp name: two writers sharing one ".tmp" each unlink the
    # other's file, and the loser's os.replace raises FileNotFoundError.
    tmp_rel = f"{SNAPSHOT_PATH}.{os.getpid()}.tmp"
    tmp = store.DATA_DIR / tmp_rel
    try:
        store.save(merged, tmp_rel)
        os.replace(tmp, store.DATA_DIR / SNAPSHOT_PATH)
    finally:
        tmp.unlink(missing_ok=True)
    return int(len(rows))
```

becomes:

```python
    atomic_save(merged, SNAPSHOT_PATH)
    return int(len(rows))
```

The `store.DATA_DIR`-at-call-time sentence stays in each module's docstring — it is
still true, and it is still the thing a test author needs to know — but it now points at
the helper.

- [ ] **`presser_log.py` (L88-95) gains the pid it never had.** Today:

```python
    tmp_rel = PRESSER_PATH + ".tmp"
```

Every other site in the tree carries `os.getpid()`. The presser log is written by the
scheduled snapshot job and by a hand-run `gaffer snapshot`, which is exactly the two
writers the pid exists for. The migration fixes it by construction, and the commit
message says so rather than letting it look like a formatting change.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_field_store.py tests/test_field_scrape.py \
  tests/test_price_log.py tests/test_snapshot.py tests/test_presser_log.py
.venv/bin/pytest -q
```

If any of those five test files does not exist under that name, find it with
`grep -rln "append_snapshot\|append_prices\|append_field_eo\|append_presser" tests/`
and run what you find. Do not skip the step.

- [ ] **Commit.**

```bash
git add src/gaffer/snapshot.py src/gaffer/price_log.py \
  src/gaffer/data/field.py src/gaffer/data/news/presser_log.py \
  && git commit -m "$(cat <<'EOF'
refactor: the four parquet logs share the rename too

Append-by-rewrite through a temp file, four times, with the store-relative path
handling that made them different enough from the JSON writers to be copied
rather than shared. gaffer.io.atomic_save covers it.

presser_log gains a pid in its temp name, which every other writer in this tree
has had all along. It is written by the nightly snapshot job and by a hand-run
`gaffer snapshot`: two writers sharing one ".tmp", each unlinking the other's
file in its finally, and the loser's os.replace raising FileNotFoundError. That
is the exact failure the pid was introduced for elsewhere.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — **STOP** — advise's own atomic write, and the two pins that read its source

**Files (both protected):**
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Modify `tests/test_v9c_degradation.py` — **PROTECTED**

> ### STOP
>
> **Do not start this task.** Report to the orchestrator that Task 4 is ready, paste the
> enumeration below, and wait for explicit authorization. Spec §2.11 says the six copies
> are migrated in W1 and this plan found twenty; neither the spec nor this plan is the
> authorization. If it does not arrive, the cycle ships with nineteen of twenty migrated,
> `advise.py` keeps its copy, and Task 16's rail names `advise.py` alongside `journal.py`
> in the surviving set — which is a recorded residual, not a failure.

**Why it cannot be skipped quietly:** the rail in Task 16 asserts the *exact* set of
modules still containing `os.replace`. Leaving `advise.py` out of the migration is fine;
leaving it out of the assertion is how the twenty-first copy appears next cycle.

### Edit 1 — `src/gaffer/advise.py:982-998`

**Before** (the v9c comment block is kept verbatim except for its last two lines, which
describe an implementation that is moving):

```python
    REPORTS.mkdir(exist_ok=True)
    # v9c orchestrator-authorized protected edit (review I1): atomic advice
    # artifact write. Three docstrings in web/jobs.py and routers/jobs.py now
    # rest on "every job kind writes its artifacts idempotently", which is what
    # makes abandoning a wedged job safe — but a plain write_text is not
    # idempotent under a re-run, it is *interruptible*, and the abandoned
    # thread that keeps running is exactly the caller that can be halfway
    # through this line while its replacement reads the file. The house idiom
    # (digest.py): pid-suffixed temp so two writers cannot share one, and
    # os.replace to make the swap atomic.
    advice_path = REPORTS / f"gw{gw}-advice.json"
    tmp = advice_path.with_name(f"{advice_path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(asdict(advice), indent=1, default=str))
        os.replace(tmp, advice_path)
    finally:
        tmp.unlink(missing_ok=True)
```

**After:**

```python
    REPORTS.mkdir(exist_ok=True)
    # v9c orchestrator-authorized protected edit (review I1): atomic advice
    # artifact write. Three docstrings in web/jobs.py and routers/jobs.py now
    # rest on "every job kind writes its artifacts idempotently", which is what
    # makes abandoning a wedged job safe — but a plain write_text is not
    # idempotent under a re-run, it is *interruptible*, and the abandoned
    # thread that keeps running is exactly the caller that can be halfway
    # through this line while its replacement reads the file.
    #
    # v12 W1 §2.11 (specs/2026-09-01-gaffer-v12-program-design.md): the idiom
    # this borrowed from digest.py is now gaffer.io.atomic_write, and the
    # guarantee is unchanged — a pid-suffixed sibling temp so two writers
    # cannot share one, and os.replace to make the swap atomic.
    advice_path = REPORTS / f"gw{gw}-advice.json"
    atomic_write(advice_path, json.dumps(asdict(advice), indent=1,
                                         default=str))
```

Plus `from gaffer.io import atomic_write` in the import block. **Do not delete
`import os` from `advise.py`** without grepping — `grep -n "os\." src/gaffer/advise.py`
— it is a 1000-line module with other users.

### Edit 2 — `tests/test_v9c_degradation.py:339-375`

Two tests. Both keep their names, their docstrings' first paragraphs and their claims;
what changes is where the claim is checked, because the implementation moved.

**`test_the_advice_artifact_is_written_through_a_temp_and_os_replace`** (L339-370).
The window grep at L365-370 goes; the claim becomes two assertions that are strictly
harder to satisfy:

```python
    import inspect

    import gaffer.advise as advise_mod
    import gaffer.io as io_mod

    source = inspect.getsource(advise_mod)
    start = source.index('f"gw{gw}-advice.json"')
    window = source[start - 600:start + 600]
    # v12 W1 §2.11 (specs/2026-09-01-gaffer-v12-program-design.md). The idiom
    # moved into gaffer.io, so the grep follows it. `atomic_write` in the
    # window is a *stronger* assertion than `os.replace` was: a comment
    # mentioning os.replace would have satisfied the old one, and a comment
    # cannot satisfy this one, because the name has to be called.
    assert "atomic_write(" in window
    # And the non-atomic form is gone, not merely joined.
    assert 'f"gw{gw}-advice.json").write_text' not in source
    # The guarantee itself, checked where it now lives.
    helper = inspect.getsource(io_mod)
    assert "os.replace" in helper and "os.getpid()" in helper
```

**`test_the_digest_writer_this_borrowed_from_still_uses_the_same_idiom`**
(L372-375). Its whole subject was "if digest.py stops being the reference, advise's
comment becomes a lie". After this cycle the reference is `gaffer.io`, and the test says
so — the function is renamed to match, because a test whose name says `digest` while it
asserts about `io` is the lie it was written to catch:

```python
def test_the_helper_this_borrowed_from_still_uses_the_same_idiom():
    """If ``gaffer.io`` ever stops being the reference, the comment in
    ``advise.py`` pointing at it becomes a lie. Cheap to notice here.

    v12 W1 §2.11: this used to name ``digest.py``, which was the house
    reference until twenty copies of its four lines were replaced by one
    helper. ``digest.py`` is now a caller like every other.
    """
    import inspect

    import gaffer.digest as digest_mod
    import gaffer.io as io_mod

    assert "os.replace" in inspect.getsource(io_mod)
    assert "os.getpid()" in inspect.getsource(io_mod)
    assert "atomic_write(" in inspect.getsource(digest_mod)
```

### Verification

```bash
.venv/bin/pytest -q tests/test_v9c_degradation.py
.venv/bin/pytest -q tests/ -k degradation
.venv/bin/pytest -q

# the whole point: one os.replace outside gaffer/io.py and journal.py
grep -rn "os\.replace" --include='*.py' src/ | grep -v "dataclasses.replace"
# expect: src/gaffer/io.py (x2), src/gaffer/journal.py (x1), and their comments
```

- [ ] **Commit** — one commit for both files, so the migration and the pins that
describe it are reviewable together:

```bash
git add src/gaffer/advise.py tests/test_v9c_degradation.py \
  && git commit -m "$(cat <<'EOF'
refactor: the advice artifact writes through the shared helper

The twentieth and last migrated copy of the idiom, and the only one behind an
orchestrator authorization: advise.py is protected, and two assertions in the
protected test_v9c_degradation.py read its source for the literal strings
os.replace and os.getpid.

Those assertions follow the idiom rather than pinning its old shape. There was a
way to leave them alone — inspect.getsource returns comments, so a comment naming
os.replace would keep both greps passing — and it was refused: an assertion that
passes because of a comment has stopped testing anything, and the next reader
would believe the module still does the write itself. `atomic_write(` in the
window cannot be satisfied by a comment, and the guarantee is now checked where
it lives.

journal.py keeps its own copy: it is import-only this cycle. That is a recorded
residual and the rail names it, so a twenty-first copy cannot appear quietly.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — **STOP** — one set of EO constants, in one unit

**Files:**
- Modify `src/gaffer/optimize/differentials.py` — **PROTECTED** (`optimize/**`)
- Modify `src/gaffer/advise.py` — **PROTECTED**
- Create `tests/test_v12_eo_constants.py`

> ### STOP
>
> **Do not start this task.** Report to the orchestrator that Task 5 is ready, paste the
> enumeration below, and wait for explicit authorization. **Note that this task edits
> two protected files, not one** — `optimize/**` is protected in its entirety, and the
> canonical constants live inside it, so even the "canonical" half of §2.2 is an
> authorized edit. The spec's §2.2 names only `advise.py:461-464`.
>
> If authorization does not arrive, nothing here ships: a half-merge that changed
> `differentials.py`'s units while `advise.py` kept its own would leave two constants of
> the same name in two units with no test able to tell them apart, which is worse than
> the duplication.

**Read A3 before starting.** The spec is wrong about what `differentials.py` contains,
and the merge is a *unit conversion at two read sites*, not a re-export.

### The complete enumeration

| # | File | Lines | Today | After |
| --- | --- | --- | --- | --- |
| 1 | `optimize/differentials.py` | 22-26 | `DIFFERENTIAL_EO = 30.0`, `ALTERNATIVE_EO = 20.0` | both in fractions, plus `TEMPLATE_EO = 0.70` |
| 2 | `optimize/differentials.py` | 50 | `df["league_eo"] < DIFFERENTIAL_EO` | `< DIFFERENTIAL_EO * 100` |
| 3 | `optimize/differentials.py` | 73 | `df["league_eo"] < ALTERNATIVE_EO` | `< ALTERNATIVE_EO * 100` |
| 4 | `advise.py` | 461-465 | its own `DIFFERENTIAL_EO = 0.3` and `TEMPLATE_EO = 0.7` with their docstrings | deleted |
| 5 | `advise.py` | 68-69 | `from gaffer.optimize.differentials import (captain_table, threat_board, …)` | the same import, extended by the two names |

**Untouched, and named so nobody tidies them in:**

| Thing | Where | Why it stays |
| --- | --- | --- |
| `threat_board(..., min_eo: float = 50.0)` | `differentials.py:79` | a parameter default, not a module constant, and not one of the three names |
| `advise.transfer_tag`'s `eo = (eo_pct or 0.0) / 100.0` | `advise.py:477` | it already converts; the constants it compares against were already fractions |
| `FIELD_EO_PATH`, `FIELD_EO_COLS` | `data/field.py:46,48` | names ending in `_EO`-something that are a path and a column list, not thresholds |

### Edit 1 — `src/gaffer/optimize/differentials.py:22-26`

```python
# v12 W1 §2.2 (specs/2026-09-01-gaffer-v12-program-design.md). Three
# thresholds on effective ownership, in one place and in one unit. They were
# in two places and two units: advise.py carried DIFFERENTIAL_EO = 0.3 and
# TEMPLATE_EO = 0.7 as fractions, this module carried DIFFERENTIAL_EO = 30.0
# and ALTERNATIVE_EO = 20.0 as percentages, and the two DIFFERENTIAL_EOs were
# the same threshold on the same quantity — which is a coincidence waiting to
# stop being one.
#
# Fractions, because that is the unit a probability-shaped quantity should be
# in and because a reader who sees 0.30 cannot mistake it for a count. The two
# comparisons in this module read `league_eo`, which is a *percentage* on the
# frame, so they multiply at the point of comparison rather than dividing the
# column: `league_eo` is returned to callers and rescaling it would change a
# served number.
DIFFERENTIAL_EO = 0.30
"""Rival EO below which a captain pick is a genuine rank differential."""

ALTERNATIVE_EO = 0.20
"""Rival EO below which a same-position swap counts as 'being brave'."""

TEMPLATE_EO = 0.70
"""At or above it, buying a player is covering one the league already owns.

Moved here from ``advise.py`` rather than found here: this module is the
canonical home for EO thresholds and was missing the third.
"""
```

### Edit 2 — `differentials.py:50` and `:73`

```python
    # league_eo is a percentage on this frame (captaincy can push it past 100);
    # the constant is a fraction. Convert here rather than rescaling the
    # column, which is returned to the caller.
    df["differential"] = ((df["league_eo"] < DIFFERENTIAL_EO * 100)
                          & (df["p_haul"] >= median_haul))
```

```python
    alts = df[(df["position"] == rec["position"]) & (df["code"] != buy_code)
              & (df["ep"] >= rec["ep"] - margin)
              # fraction constant, percent column — see captain_table.
              & (df["league_eo"] < ALTERNATIVE_EO * 100)]
```

### Edit 3 — `advise.py:461-465` deleted, `advise.py:68-69` extended

Delete:

```python
DIFFERENTIAL_EO = 0.3
"""Below this league-EO fraction a buy is an attacking punt on the field."""

TEMPLATE_EO = 0.7
"""At or above it, buying is covering a player the league already owns."""
```

and extend the existing import (this module already imports from
`optimize.differentials`, so no new dependency direction is created):

```python
# v12 W1 §2.2 (specs/2026-09-01-gaffer-v12-program-design.md): the two
# thresholds transfer_tag reads used to be defined here, in fractions, while
# optimize/differentials.py carried a DIFFERENTIAL_EO of its own in percent.
# One set now, in one unit, in the module that owns EO thresholds.
from gaffer.optimize.differentials import (DIFFERENTIAL_EO, TEMPLATE_EO,
                                           captain_table, threat_board,
                                           transfer_alternatives)
```

(Match the existing import's exact trailing names — read L68-69 before editing; this
plan reproduces them but the third name must be verified, not trusted.)

`transfer_tag`'s body is **unchanged**. It already divides `eo_pct` by 100 at L477, so
it already compares a fraction to a fraction. That is why `tests/test_advise.py` needs
no edit and is not in this STOP.

- [ ] **Write the failing test first** (it can be written and run before authorization —
it fails on the *current* tree, which is the point). Create
`tests/test_v12_eo_constants.py`:

```python
"""One set of EO thresholds, in one unit.

Two modules defined a constant called DIFFERENTIAL_EO. They meant the same
threshold on the same quantity — rival effective ownership — and they held 0.3
and 30.0. Nothing was wrong on either side, and nothing would have gone wrong
until somebody changed one of them.

The unit is the fraction, because that is what a share should be and because a
reader who sees 0.30 cannot read it as a count. `league_eo` on the frames stays
a percentage, so the two comparisons inside differentials.py multiply at the
point of comparison — the conversion is at the read site, which is the rule §2.2
sets.
"""

from __future__ import annotations

import pathlib
import re

import pandas as pd

from gaffer.optimize.differentials import (ALTERNATIVE_EO, DIFFERENTIAL_EO,
                                           TEMPLATE_EO, captain_table,
                                           transfer_alternatives)


def test_all_three_constants_are_fractions():
    """The import-time claim §2.2 asks for. A value of 30.0 here would clamp
    every fraction-shaped comparison in the tree to True."""
    for value in (DIFFERENTIAL_EO, ALTERNATIVE_EO, TEMPLATE_EO):
        assert 0.0 < value < 1.0


def test_the_three_hold_the_values_they_always_held():
    """The merge is a move and a rescale, not a re-tuning. Any change to these
    numbers is a decision somebody has to make on purpose."""
    assert (DIFFERENTIAL_EO, ALTERNATIVE_EO, TEMPLATE_EO) == (0.30, 0.20, 0.70)


def test_no_other_module_defines_an_EO_threshold():
    """§2.2's grep. Matches a name ending in _EO assigned a numeric literal, so
    FIELD_EO_PATH (a string) and FIELD_EO_COLS (a list) do not count and the
    parameter default `min_eo=50.0` does not either — it is a parameter, not a
    module constant, and it is named here so a later reader knows it was seen.
    """
    pattern = re.compile(r"^[A-Z_]*_EO\s*=\s*-?\d", re.MULTILINE)
    hits = {p.as_posix() for p in pathlib.Path("src").rglob("*.py")
            if pattern.search(p.read_text())}
    assert hits == {"src/gaffer/optimize/differentials.py"}


def _ep(league_eo_pct):
    return pd.DataFrame({
        "code": [1, 2], "name": ["A", "B"], "position": ["MID", "MID"],
        "ep": [6.0, 5.9], "p_haul": [0.3, 0.3],
    }), {1: league_eo_pct, 2: league_eo_pct}


def test_the_captain_table_still_reads_a_percentage_column():
    """The regression the rescale could have caused: `league_eo` on the frame
    is a percent, the constant is now a fraction, and a comparison that forgot
    to convert would mark every player in the league a differential."""
    ep, eo = _ep(45.0)          # 45% owned: not a differential
    out = captain_table(ep, [1, 2], eo)
    assert not out["differential"].any()

    ep, eo = _ep(5.0)           # 5% owned: is one
    out = captain_table(ep, [1, 2], eo)
    assert out["differential"].all()


def test_the_alternatives_still_read_a_percentage_column():
    ep, eo = _ep(45.0)
    assert transfer_alternatives(ep, 1, eo).empty
    ep, eo = _ep(5.0)
    assert len(transfer_alternatives(ep, 1, eo)) == 1


def test_the_league_eo_column_is_returned_in_percent_unchanged():
    """Why the conversion is at the read site and not on the column: this
    number is served, and rescaling it would move a figure on a page."""
    ep, eo = _ep(45.0)
    assert captain_table(ep, [1, 2], eo)["league_eo"].tolist() == [45.0, 45.0]
```

Run it before authorization: `.venv/bin/pytest -q tests/test_v12_eo_constants.py` — the
import fails on `TEMPLATE_EO`, and `test_no_other_module_defines_an_EO_threshold` fails
naming `advise.py`. Both are the finding, stated as a test.

- [ ] **Verify (after authorization).**

```bash
.venv/bin/pytest -q tests/test_v12_eo_constants.py tests/test_advise.py \
  tests/test_report.py tests/test_league_mode.py
.venv/bin/pytest -q
```

`tests/test_advise.py` is protected and pins `transfer_tag`'s four boundaries
(29.9/30.0/69.9/70.0). **It must pass untouched.** If it does not, the merge changed a
threshold rather than moving one: stop and report.

- [ ] **Commit.**

```bash
git add src/gaffer/optimize/differentials.py src/gaffer/advise.py \
  tests/test_v12_eo_constants.py && git commit -m "$(cat <<'EOF'
refactor: one set of EO thresholds, in fractions, in the module that owns them

Two modules defined DIFFERENTIAL_EO. They meant the same threshold on the same
quantity and held 0.3 and 30.0, and nothing was wrong until somebody changed one.

The spec said differentials.py already exported all three; it exported two, in
percent, and had never heard of TEMPLATE_EO — which moves here from advise.py
rather than being found here. All three are fractions now, and this module's own
two comparisons convert at the read site, because `league_eo` on those frames is
a percentage that gets returned to the caller and rescaling it would move a
number on a page.

transfer_tag's body does not change: it already divided by 100 before comparing,
which is why the protected test_advise.py passes untouched and is not part of
this authorization.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — **STOP** — the field EO read has to be told which season

**Files:**
- Modify `src/gaffer/data/field.py` (L195-250)
- Modify `src/gaffer/web/routers/players.py` (L147-151)
- Modify `tests/test_v10b_degradation.py` — **PROTECTED**
- Modify `tests/test_v8c_degradation.py` — **PROTECTED**
- Modify `tests/test_v10b_field_season.py`, `tests/test_field_store.py` — unprotected
- Create `tests/test_v12_field_season_required.py`

> ### STOP
>
> **Do not start this task.** Report to the orchestrator that Task 6 is ready, paste the
> enumeration below, and wait for explicit authorization for the two protected test
> edits. v11's plan A2 examined this exact change and refused it, in writing, because it
> moves these two pins. v12 §2.3 orders it; that is the spec, not the authorization.
>
> If authorization does not arrive: the keyword stays optional, `players.py` passes
> `season=` anyway (which needs no protected edit and closes the actual bug), and the
> residual — "`season` is still optional, so a caller can still forget" — is recorded
> in the README and the ROADMAP. That is a smaller win, not a failure.

**Read A4 before starting.** Most of §2.3 already shipped in v10b. What is left is
making the keyword impossible to forget, plus filtering `load_field_eo`.

### The complete enumeration

| # | File | Lines | Today | After | Protected? |
| --- | --- | --- | --- | --- | --- |
| 1 | `data/field.py` | 195-200 | `load_field_eo()` | `load_field_eo(*, season: str \| None = None)` | no |
| 2 | `data/field.py` | 202-203 | `latest_field_eo(gw=None, *, season: str \| None = None)` | `season: str` required | no |
| 3 | `data/field.py` | 236-247 | the `if season is not None:` guard | unconditional | no |
| 4 | `web/routers/players.py` | 149 | `latest_field_eo()` | `latest_field_eo(season=load_config().current_season)` | no |
| 5 | `tests/test_v10b_degradation.py` | 123-133 | `test_the_explorers_own_call_is_unchanged` | rewritten: the explorer's call is what changed | **yes** |
| 6 | `tests/test_v8c_degradation.py` | 71-73 | `assert latest_field_eo() == {}` | `latest_field_eo(season="2026-27") == {}` | **yes** |
| 7 | `tests/test_v10b_field_season.py` | 52, 83 | bare calls | seasoned | no |
| 8 | `tests/test_field_store.py` | 126, 133, 144 | bare calls | seasoned | no |

### Edit A — `data/field.py`

`load_field_eo` gains the filter, and it filters **before** returning rather than
leaving it to callers:

```python
def load_field_eo(*, season: str | None = None) -> pd.DataFrame:
    """Every banked row, or an empty frame with the right columns.

    v12 W1 §2.3: ``season`` narrows the log before anything reads it.
    Optional here and *required* on :func:`latest_field_eo`, deliberately —
    this one is the raw reader the scrape's own tests use to count what was
    banked, where "everything" is a legitimate question. The derived reader
    answers a question about *a* season, where it is not.

    A log with no ``season`` column is a log written before the column
    existed; a named season over such a log is empty, not "everything", for
    the same reason ``latest_field_eo`` has no fallback — "whatever is there"
    is exactly the answer the season keyword exists to prevent.
    """
    if not store.exists(FIELD_EO_PATH):
        return pd.DataFrame(columns=FIELD_EO_COLS)
    log = store.load(FIELD_EO_PATH)
    if season is None:
        return log
    if "season" not in log.columns:
        return log.iloc[0:0]
    return log[log["season"].astype(str) == str(season)]
```

`latest_field_eo`'s signature becomes `(gw: int | None = None, *, season: str)` and its
body drops the `if season is not None:` wrapper — the filter is now unconditional and
delegated:

```python
    try:
        frame = load_field_eo(season=season).copy()
    except Exception:  # noqa: BLE001 — a display read never blocks a page
        return {}
    if frame.empty:
        return {}
```

The v10b comment block at L236-247 is **kept**, with its first sentence rewritten from
"A named season is filtered first; an unnamed one keeps today's behaviour byte for
byte" to say that the keyword is now required and why. The rest of it — that `element`
is season-scoped, that `max(gw)` after a rollover picks last season's, that there is no
fallback — is the reasoning this task is completing, not replacing.

### Edit B — `web/routers/players.py:147-151`

```python
    # Pure display: an unreadable log is a missing column, never a 500. The
    # explorer must render on a clone that has never run a scrape.
    #
    # v12 W1 §2.3: seasoned. This call was bare for two cycles and v10b
    # recorded it as a residual — `element` is season-scoped, so after a
    # rollover the largest gameweek in the log is last season's and every row
    # on this page would have carried a different footballer's ownership.
    # `load_config` can raise on a clone with no config.toml, which is why it
    # is inside the try with the read.
    try:
        field_eo = latest_field_eo(season=load_config().current_season)
    except Exception:  # noqa: BLE001
        field_eo = {}
```

Check the import: `players.py` must import `load_config`. `grep -n "load_config"
src/gaffer/web/routers/players.py` — add `from gaffer.config import load_config` if it
is absent.

### Edit C — `tests/test_v10b_degradation.py:123-133` (PROTECTED)

The test's subject was the explorer's call. The explorer's call is what changed, so the
test follows its subject rather than defending a call shape that no longer exists. Same
fixture, opposite expectation, and the docstring says why the expectation flipped:

```python
def test_the_explorer_reads_this_season_and_not_the_larger_gameweek(clone,
                                                                    monkeypatch):
    """v12 W1 §2.3 (specs/2026-09-01-gaffer-v12-program-design.md).

    This was ``test_the_explorers_own_call_is_unchanged``, and it asserted the
    opposite: that ``routers/players.py`` called ``latest_field_eo()`` bare and
    kept getting the largest gameweek in the file, season or no season. v10b
    wrote it that way because the change was out of that cycle's scope and the
    bug could not fire until a rollover; v11's plan A2 looked at it again and
    left it for the same reason. v12 §2.3 closes it.

    The fixture is v10b's, unchanged, and it is the rollover in miniature: two
    seasons, one element id, two different footballers. Last season's row has
    the larger gameweek number, so "newest" and "this season's" disagree — and
    the explorer must now pick the second.
    """
    store.save(pd.DataFrame([
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 411, "eo": 90.0, "se": 1.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 10.0, "se": 1.0, "n": 300},
    ]), "live/field_eo_log.parquet")
    assert latest_field_eo(season="2026-27")[411]["eo"] == 10.0
    assert latest_field_eo(season="2025-26")[411]["eo"] == 90.0
    # And the keyword cannot be forgotten any more, which is the half of §2.3
    # that needed the signature to change rather than the call.
    with pytest.raises(TypeError):
        latest_field_eo()
```

Confirm `pytest` is imported in that file before adding the `raises`; add the import if
not.

### Edit D — `tests/test_v8c_degradation.py:71-73` (PROTECTED)

One keyword. The claim — a missing log reads empty — is untouched:

```python
def test_the_latest_read_of_a_missing_log_is_empty(bare):
    # v12 W1 §2.3: `season` is a required keyword now. The claim is unchanged;
    # a bare tree has no rows for any season.
    assert latest_field_eo(season="2026-27") == {}
    assert not store.exists(FIELD_EO_PATH)
```

`test_the_explorer_column_is_absent_rather_than_zero` at L64-69 goes through
`GET /api/players` rather than calling the reader, so it needs **no** edit — but it
does need to still pass, and it will only pass if Edit B's `try` catches the
`GafferError` a clone with no `config.toml` raises. That is why `load_config()` is
inside the `try`.

- [ ] **Write the new test.** Create `tests/test_v12_field_season_required.py`:

```python
"""Which season's ownership is on the page.

`element` is a season-scoped id — FIELD_EO_COLS says so — so a log holding two
seasons holds two different footballers under one number. The reader used to
take `season` as an optional keyword, which meant a caller could forget it and
get "whatever gameweek number is largest", which after a rollover is last
season's final week.

Required, now. The failure this prevents is silent: every ownership figure on
the players page would be a real number about the wrong player, and nothing on
the page could say so.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.data.field import (FIELD_EO_COLS, latest_field_eo, load_field_eo)


@pytest.fixture()
def two_seasons(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame([
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 411, "eo": 90.0, "se": 1.0, "n": 300},
        {"season": "2025-26", "gw": 38, "snap_date": "2026-05-24",
         "element": 7, "eo": 55.0, "se": 2.0, "n": 300},
        {"season": "2026-27", "gw": 2, "snap_date": "2026-08-31",
         "element": 411, "eo": 10.0, "se": 1.0, "n": 300},
    ], columns=FIELD_EO_COLS), "live/field_eo_log.parquet")
    return tmp_path


def test_the_reader_returns_only_the_named_seasons_rows(two_seasons):
    """The spec's own test: two seasons, overlapping element ids, one answer."""
    assert set(latest_field_eo(season="2026-27")) == {411}
    assert latest_field_eo(season="2026-27")[411]["eo"] == 10.0


def test_the_other_season_is_still_readable_and_is_not_the_default(two_seasons):
    table = latest_field_eo(season="2025-26")
    assert set(table) == {411, 7}
    assert table[411]["eo"] == 90.0


def test_the_larger_gameweek_number_does_not_win(two_seasons):
    """The whole bug in one line: 38 > 2, and 38 is last season's."""
    assert latest_field_eo(season="2026-27")[411]["gw"] == 2


def test_the_keyword_cannot_be_omitted(two_seasons):
    with pytest.raises(TypeError):
        latest_field_eo()


def test_a_season_with_no_rows_is_empty_and_never_falls_back(two_seasons):
    """No fallback, restated as a test: "whatever is newest" is exactly the
    answer this keyword exists to prevent."""
    assert latest_field_eo(season="2027-28") == {}


def test_the_raw_reader_filters_too(two_seasons):
    assert len(load_field_eo()) == 3
    assert len(load_field_eo(season="2026-27")) == 1
    assert len(load_field_eo(season="2027-28")) == 0


def test_a_log_written_before_the_season_column_reads_empty_for_any_season(
        tmp_path, monkeypatch):
    """The older-log case. Empty rather than everything, for the same reason
    there is no fallback: a log that cannot say which season it is about
    cannot answer a question about one season."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    store.save(pd.DataFrame([
        {"gw": 2, "snap_date": "2026-08-31", "element": 411,
         "eo": 10.0, "se": 1.0, "n": 300}]), "live/field_eo_log.parquet")
    assert load_field_eo(season="2026-27").empty
    assert latest_field_eo(season="2026-27") == {}


def test_no_log_at_all_is_empty_rather_than_a_raise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert latest_field_eo(season="2026-27") == {}
    assert load_field_eo(season="2026-27").empty
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_field_season_required.py \
  tests/test_v10b_field_season.py tests/test_field_store.py \
  tests/test_v8c_degradation.py tests/test_v10b_degradation.py \
  tests/test_web_players_v8c.py tests/test_v11_field_se.py
.venv/bin/pytest -q

grep -rn "latest_field_eo()" src/ tests/
# expect: nothing. A bare call is now a TypeError, so a survivor is a test
# that never ran.
```

- [ ] **Commit.**

```bash
git add src/gaffer/data/field.py src/gaffer/web/routers/players.py \
  tests/test_v10b_degradation.py tests/test_v8c_degradation.py \
  tests/test_v10b_field_season.py tests/test_field_store.py \
  tests/test_v12_field_season_required.py && git commit -m "$(cat <<'EOF'
fix: the field EO read has to be told which season

`element` is a season-scoped id, so a log holding two seasons holds two
footballers under one number, and the reader's `max(gw)` after a rollover picks
last season's final week. The keyword to prevent that has existed since v10b and
was optional, and routers/players.py forgot it — for two cycles, recorded as a
residual twice, because the bug cannot fire until August.

Required now, which is the part that needed two protected test edits: v10b's
degradation file asserted in so many words that the explorer called it bare and
got the largest gameweek, and v8c's called it bare on an empty tree. The first is
rewritten around the same two-season fixture with the opposite expectation, and
its docstring records that the assertion flipped and why; the second gains a
keyword and keeps its claim.

load_field_eo filters too, and a log written before the season column reads empty
for a named season rather than everything — the same "no fallback" rule, for the
same reason.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the season rollover guard

**Files:**
- Modify `src/gaffer/data/bootstrap.py` (after L113)
- Modify `src/gaffer/cli.py` (`refresh`, L100-110)
- Modify `src/gaffer/web/routers/meta.py` (`health`, L155-215)
- Modify `src/gaffer/web/schemas.py` (`Health`, L816-824)
- Modify `frontend/src/hubs/model/HealthTab.tsx`
- Modify `frontend/src/types.ts`
- Create `tests/test_v12_season_rollover.py`
- Create `frontend/src/hubs/model/HealthTab.rollover.test.tsx`

**Read A5 before starting.** Two halves, and only the CLI half may touch the network.

- [ ] **Write the failing test.** Create `tests/test_v12_season_rollover.py`:

```python
"""The August failure, caught in August rather than in October.

FPL's bootstrap carries no season string. What it carries is 38 events with
deadlines, and GW1's is in August of the season's first year — so the season is
derivable and the config's claim about it is checkable.

The check matters because every downstream failure of a rollover is silent.
`current_season` is written into every row `refresh_live` banks and every model
`train` fits; a stale value does not raise, it labels this season's data as last
season's and trains on the mixture. The first symptom is a model that has
quietly got worse.

Two rules that are not obvious and are the reason this is a whole task:

* the **minimum** deadline year across the events, not GW1's row. A partially
  published season can be missing rows, and `min` degrades to the earliest week
  there is;
* an events table with no parseable deadline yields `None`, and `None` is *not*
  a mismatch. "Cannot tell" and "wrong" are different states, and a red banner
  drawn from the first is a false alarm on every cold clone.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data.bootstrap import season_from_events


def _events(*deadlines):
    return pd.DataFrame([{"gw": i + 1, "deadline_time": d}
                         for i, d in enumerate(deadlines)])


def test_an_august_first_deadline_names_the_season():
    assert season_from_events(
        _events("2026-08-14T17:30:00Z", "2026-08-21T17:30:00Z")) == "2026-27"


def test_the_year_pair_wraps_at_the_century():
    assert season_from_events(_events("2099-08-14T17:30:00Z")) == "2099-00"


def test_the_earliest_deadline_decides_not_the_first_row():
    """Rows out of order, and a season that is only half published: `min`
    answers both without knowing about either."""
    assert season_from_events(
        _events("2027-05-24T15:00:00Z", "2026-08-14T17:30:00Z")) == "2026-27"


def test_an_unparseable_deadline_is_skipped_rather_than_fatal():
    assert season_from_events(
        _events("not a date", "2026-08-14T17:30:00Z")) == "2026-27"


def test_no_parseable_deadline_at_all_is_None_and_not_a_guess():
    assert season_from_events(_events("not a date")) is None
    assert season_from_events(_events()) is None


def test_a_frame_without_the_column_is_None():
    assert season_from_events(pd.DataFrame({"gw": [1]})) is None


# --- the CLI half ---------------------------------------------------------

def test_refresh_refuses_when_the_api_disagrees_with_the_config(
        tmp_path, monkeypatch, capsys):
    """Non-zero exit, and a message naming both values and both keys — the
    two things a user needs in order to fix it without reading the source."""
    import typer

    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2025-26"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": [{"id": 1,
                                "deadline_time": "2026-08-14T17:30:00Z"}]}

    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    with pytest.raises(typer.Exit) as exc:
        cli.refresh()
    assert exc.value.exit_code == 1
    out = capsys.readouterr().out
    assert "2025-26" in out and "2026-27" in out
    assert "current_season" in out and "train_seasons" in out


def test_refresh_proceeds_when_they_agree(tmp_path, monkeypatch):
    """The guard is a guard, not a gate: the happy path is unchanged, and
    `refresh_live` is still called exactly once."""
    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = ["2025-26"]\ncurrent_season = "2026-27"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": [{"id": 1,
                                "deadline_time": "2026-08-14T17:30:00Z"}]}

    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    monkeypatch.setattr(
        "gaffer.data.live.refresh_live",
        lambda *a, **k: calls.append(1) or pd.DataFrame({"code": [1]}))
    cli.refresh()
    assert calls == [1]


def test_refresh_proceeds_when_the_season_cannot_be_derived(tmp_path,
                                                            monkeypatch):
    """"Cannot tell" never blocks a refresh. A bootstrap FPL has not opened
    for the new season yet is a normal July state, and refusing to ingest in
    July would be the guard causing the outage it exists to prevent."""
    from gaffer import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = []\ncurrent_season = "2026-27"\n')

    class Client:
        def get_bootstrap(self):
            return {"events": []}

    calls = []
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: Client())
    monkeypatch.setattr(
        "gaffer.data.live.refresh_live",
        lambda *a, **k: calls.append(1) or pd.DataFrame({"code": [1]}))
    cli.refresh()
    assert calls == [1]


# --- the served half ------------------------------------------------------

def test_health_reports_both_values_from_the_banked_events(tmp_path,
                                                           monkeypatch):
    """Disk only. `/api/health` is polled by a tab, and a page that goes blank
    when the FPL API is down is the opposite of a health page."""
    from fastapi.testclient import TestClient

    from gaffer.data import store
    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        '[data]\ntrain_seasons = []\ncurrent_season = "2025-26"\n')
    store.save(pd.DataFrame([{"gw": 1,
                              "deadline_time": "2026-08-14T17:30:00Z"}]),
               "live/events.parquet")
    body = TestClient(create_app()).get("/api/health").json()
    assert body["season_ok"] is False
    assert body["season_config"] == "2025-26"
    assert body["season_ingested"] == "2026-27"


def test_health_on_a_clone_with_no_events_says_nothing_rather_than_alarm(
        tmp_path, monkeypatch):
    """No data is not a mismatch. `season_ok` is None — three states, not two,
    and the banner draws on False alone."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    body = TestClient(create_app()).get("/api/health").json()
    assert body["season_ok"] is None
    assert body["season_ingested"] is None
```

- [ ] **Implement `season_from_events`** in `src/gaffer/data/bootstrap.py`, after
`build_events`:

```python
def season_from_events(events: pd.DataFrame) -> str | None:
    """``"2026-27"`` from the events' deadlines, or ``None`` if unknowable.

    v12 W1 §2.4 (specs/2026-09-01-gaffer-v12-program-design.md). FPL's
    bootstrap carries no season string; what it carries is deadlines, and the
    earliest of them is in August of the season's first year.

    The **minimum** parseable year, not the first row's: a partially published
    season can be missing rows, and ``min`` degrades to the earliest week there
    is without needing to know that.

    ``None`` for an empty frame, a missing column, or deadlines that will not
    parse — and ``None`` means *unknown*, never *mismatched*. A guard that
    treated the two the same would refuse to ingest every July, which is the
    outage it exists to prevent.
    """
    if "deadline_time" not in getattr(events, "columns", ()):
        return None
    stamps = pd.to_datetime(events["deadline_time"], errors="coerce",
                            utc=True, format="mixed").dropna()
    if stamps.empty:
        return None
    year = int(stamps.min().year)
    return f"{year}-{(year + 1) % 100:02d}"
```

`format="mixed"` because the banked column is written from JSON strings and pandas 2.x
otherwise warns per row; `utc=True` because FPL deadlines carry `Z`.

- [ ] **Implement the CLI half** — `cli.py`'s `refresh`, which already holds the
bootstrap one frame down. Fetch it here instead, so the comparison costs no extra call
and `refresh_live` gets the client it already got:

```python
@app.command()
def refresh():
    """Pull latest FPL data into data/live/."""
    from gaffer.api.client import FPLClient
    from gaffer.config import load_config
    from gaffer.data.bootstrap import build_events, season_from_events
    from gaffer.data.live import refresh_live

    cfg = load_config()
    client = FPLClient()
    # v12 W1 §2.4. Every downstream failure of a rollover is silent:
    # `current_season` is stamped onto every row banked here and every model
    # trained afterwards, so a stale value does not raise — it labels this
    # season's rows as last season's and trains on the mixture. The first
    # symptom is a model that has quietly got worse.
    #
    # `None` is "cannot tell" and never blocks: a bootstrap FPL has not opened
    # for the new season is a normal July state.
    ingested = season_from_events(build_events(client.get_bootstrap()))
    if ingested is not None and ingested != cfg.current_season:
        typer.echo(
            f"Refusing to refresh: the API is serving {ingested} and "
            f"config.toml says {cfg.current_season}.\n"
            f"A rollover needs two keys changed together in [data]: set "
            f"current_season = \"{ingested}\" and append "
            f"\"{cfg.current_season}\" to train_seasons.")
        raise typer.Exit(1)
    df = refresh_live(client, cfg.current_season, len(cfg.train_seasons))
    typer.echo(f"Refreshed {len(df)} player-GW rows.")
```

The message names both values **and** both keys **and** what to do with each, because
"seasons disagree" without the remedy is a message that sends the user to the source.

- [ ] **Implement the served half.** `schemas.py`'s `Health` gains three fields:

```python
    season_ok: bool | None = None
    """Does the banked data's season match ``config.current_season``?

    Three states, not two. ``None`` is *cannot tell* — no events snapshot, or
    deadlines that will not parse — and it is not an alarm: a cold clone has
    no data to disagree with. The banner draws on ``False`` alone.
    """
    season_config: str | None = None
    """What ``config.toml`` says this season is."""
    season_ingested: str | None = None
    """What the last refresh actually banked, derived from the events' own
    deadlines. Read off disk, never off the API: this endpoint is polled by a
    tab and must not depend on FPL being up."""
```

and `meta.health()` fills them, next to the existing `odds_key` block which already has
the "no config.toml is a valid state" shape:

```python
    # v12 W1 §2.4. Disk only, by this module's own contract: the events
    # snapshot is what the last refresh banked, so the comparison answers "is
    # the data on disk the data the config describes" — which is the state
    # that matters — without a network call on a page-load path.
    season_config = season_ingested = None
    season_ok = None
    try:
        season_config = load_config().current_season
    except Exception:  # noqa: BLE001 — no config.toml is a valid state here
        season_config = None
    try:
        season_ingested = season_from_events(
            store.load("live/events.parquet"))
    except Exception:  # noqa: BLE001 — no snapshot yet is a valid state too
        season_ingested = None
    if season_config and season_ingested:
        season_ok = season_config == season_ingested
```

with `from gaffer.data.bootstrap import season_from_events` at the top of `meta.py`.

- [ ] **The banner.** `frontend/src/types.ts`'s `HealthData` gains the three fields
(`season_ok: boolean | null`, `season_config: string | null`,
`season_ingested: string | null`), and `HealthTab.tsx` renders **above** the Data
freshness card, on `season_ok === false` only:

```tsx
      {data.season_ok === false && (
        <div
          data-testid="season-mismatch"
          className="mb-4 rounded-card border border-rust bg-card px-4 py-3
                     text-rust"
        >
          <p className="font-semibold">Season mismatch</p>
          <p className="mt-1 text-text-secondary">
            {`The last refresh banked ${data.season_ingested}; config.toml says
              ${data.season_config}. Set [data] current_season to
              ${data.season_ingested} and append ${data.season_config} to
              train_seasons — both, together. Until then every row ingested
              carries the wrong season label and every model trained on them
              trains on the mixture.`}
          </p>
        </div>
      )}
```

`=== false`, never `!data.season_ok`, because `null` is "cannot tell" and a falsy check
would paint the banner on every cold clone. This is the same three-state discipline the
tree uses for `field_eo`, and it is the one thing a reviewer will try to "simplify".

- [ ] **The frontend test.** Create
`frontend/src/hubs/model/HealthTab.rollover.test.tsx`: the banner renders on `false`
with both seasons named; it does **not** render on `true`; it does **not** render on
`null`; and it does not render when the fields are absent entirely (an older server).

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_season_rollover.py tests/test_web_meta.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
```

If `tests/test_web_meta.py` does not exist, find the health tests with
`grep -rln "api/health" tests/` and run those.

- [ ] **Commit** (`feat: refresh refuses to ingest a season the config does not name`,
staging exactly `src/gaffer/data/bootstrap.py src/gaffer/cli.py
src/gaffer/web/routers/meta.py src/gaffer/web/schemas.py frontend/src/types.ts
frontend/src/hubs/model/HealthTab.tsx
frontend/src/hubs/model/HealthTab.rollover.test.tsx
tests/test_v12_season_rollover.py`, with the standing trailers).

---

## Task 8 — `track_pens` will not overwrite a good report with a degraded one

**Files:**
- Modify `src/gaffer/cli.py` (`track_pens_cmd`, L571-582)
- Create `tests/test_v12_track_pens_refusal.py`

**Read A6 before starting.** The spec says "if every fetched row is degraded"; the
tracker has no row-level marker. It has a per-gameweek one, and it has a second failure
mode the spec does not name.

- [ ] **Write the failing test.** Create `tests/test_v12_track_pens_refusal.py`:

```python
"""A degraded run does not get to delete a good one.

`track_pens` never raises — it is a standing report and a report that dies on one
bad file is a report nobody runs — so every failure comes back as a *shape*: a
gameweek block carrying `error`, or a report with no gameweeks and one note. Both
shapes are then written straight over reports/pen_tracker.json, and a season of
tracking is gone because one parquet would not read.

`calibrate_noise` already refuses in this situation and this mirrors it, including
the part that is easy to get wrong: **the refusal only fires when there is
something to protect.** A first run on a cold clone must write its empty report,
or the file never comes into existence at all.
"""

from __future__ import annotations

import json

import pytest
import typer

from gaffer import cli


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    return tmp_path


def _banked(clone, text="the good one"):
    path = clone / "reports" / "pen_tracker.json"
    path.write_text(json.dumps({"season": "2026-27", "gws": [{"gw": 1}],
                                "season_totals": {"note": text},
                                "notes": []}))
    return path


def _report(monkeypatch, report):
    monkeypatch.setattr("gaffer.pen_tracker.track_pens", lambda season: report)


def test_a_run_whose_every_gameweek_is_broken_refuses(clone, monkeypatch,
                                                      capsys):
    path = _banked(clone)
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad parquet"},
                                  {"gw": 2, "error": "bad parquet"}]})
    with pytest.raises(typer.Exit) as exc:
        cli.track_pens_cmd(season="2026-27")
    assert exc.value.exit_code == 1
    out = capsys.readouterr().out
    assert "refused to overwrite" in out
    assert "pen_tracker.json" in out
    assert "2 rows degraded" in out
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the good one"


def test_one_good_gameweek_among_the_broken_is_enough_to_write(clone,
                                                               monkeypatch):
    """The partial case is the one `safe_gw_block` was built for: one bad week
    is that week's problem, and the season line still covers the rest. Refusing
    here would throw away the very degradation the tracker handles well."""
    path = _banked(clone)
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {"note": "the new one"},
                          "gws": [{"gw": 1, "error": "bad"}, {"gw": 2}]})
    cli.track_pens_cmd(season="2026-27")
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the new one"


def test_an_empty_report_refuses_and_says_which_note_caused_it(clone,
                                                              monkeypatch,
                                                              capsys):
    """The second hazard, which the spec does not name: no gameweeks at all,
    because the live parquet is missing. Same loss, different cause."""
    path = _banked(clone)
    _report(monkeypatch, {"season": "2026-27", "gws": [], "season_totals": {},
                          "notes": ["no live season on disk — run "
                                    "`gaffer refresh` first"]})
    with pytest.raises(typer.Exit):
        cli.track_pens_cmd(season="2026-27")
    out = capsys.readouterr().out
    assert "the report is empty" in out
    assert "no live season on disk" in out
    assert json.loads(path.read_text())["season_totals"]["note"] == \
        "the good one"


def test_a_first_run_on_a_cold_clone_writes_its_empty_report(clone,
                                                             monkeypatch):
    """The half that makes the refusal safe. With nothing banked there is
    nothing to protect, and refusing would mean the file is never created."""
    _report(monkeypatch, {"season": "2026-27", "gws": [], "season_totals": {},
                          "notes": ["no finished gameweek in the live season "
                                    "yet"]})
    cli.track_pens_cmd(season="2026-27")
    assert (clone / "reports" / "pen_tracker.json").exists()


def test_a_first_run_whose_every_week_is_broken_also_writes(clone,
                                                            monkeypatch):
    """Same rule, other shape. Nothing banked, so the degraded report is the
    best available answer and hiding it would leave no artifact at all."""
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad"}]})
    cli.track_pens_cmd(season="2026-27")
    assert (clone / "reports" / "pen_tracker.json").exists()


def test_an_unreadable_banked_report_does_not_block_the_write(clone,
                                                              monkeypatch):
    """A corrupt file is not something worth protecting, and a refusal here
    would wedge the command with no way out but deleting the file by hand —
    which is exactly the state the refusal is meant to spare the user."""
    (clone / "reports" / "pen_tracker.json").write_text("{not json")
    _report(monkeypatch, {"season": "2026-27", "notes": [],
                          "season_totals": {},
                          "gws": [{"gw": 1, "error": "bad"}]})
    cli.track_pens_cmd(season="2026-27")
    assert json.loads(
        (clone / "reports" / "pen_tracker.json").read_text())["gws"]
```

- [ ] **Implement.** `cli.py`'s `track_pens_cmd`:

```python
@app.command("track-pens")
def track_pens_cmd(season: str = typer.Option(
        "", help="Season to track (default: fpl.current_season).")):
    """Predicted penalty EP against the penalties actually taken (v7c F3)."""
    import json

    from gaffer.pen_tracker import (format_tracker, save_tracker,
                                    tracker_path, track_pens)

    report = track_pens(season or None)
    # v12 W1 §2.5 (specs/2026-09-01-gaffer-v12-program-design.md), mirroring
    # calibrate_noise's refusal above. track_pens never raises — a standing
    # report that dies on one bad file is a report nobody runs — so a failure
    # arrives as a *shape*, and writing that shape over a good artifact loses
    # a season of tracking to one unreadable parquet.
    #
    # Two shapes, two messages. And the refusal only fires when there is
    # something to protect: a first run on a cold clone must write its empty
    # report or the file never comes into existence. An unreadable banked file
    # is not something to protect either — refusing there would wedge the
    # command with no remedy but deleting the file by hand.
    blocks = report.get("gws") or []
    degraded = [b for b in blocks if "error" in b]
    banked = False
    try:
        banked = bool(json.loads(tracker_path().read_text()))
    except Exception:  # noqa: BLE001 — absent or corrupt: nothing to protect
        banked = False
    if banked:
        path = tracker_path()
        if blocks and len(degraded) == len(blocks):
            typer.echo(f"track_pens: refused to overwrite {path}: all "
                       f"{len(blocks)} rows degraded")
            raise typer.Exit(1)
        if not blocks:
            note = (report.get("notes") or ["no gameweeks"])[0]
            typer.echo(f"track_pens: refused to overwrite {path}: the report "
                       f"is empty ({note})")
            raise typer.Exit(1)
    path = save_tracker(report)
    typer.echo(format_tracker(report))
    typer.echo(f"Wrote {path}")
```

The refusal is in the CLI and not in `save_tracker` for two reasons, both worth keeping
in the comment: `calibrate_noise`'s refusal is there and §2.5 says to mirror it, and
`save_tracker` is a dumb writer that a caller may legitimately want to hand a
deliberately empty report.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_track_pens_refusal.py \
  tests/test_pen_tracker.py
.venv/bin/pytest -q
```

- [ ] **Commit** (`feat: a degraded pen-tracker run does not overwrite a good one`,
staging `src/gaffer/cli.py tests/test_v12_track_pens_refusal.py`, with the standing
trailers).

---

## Task 9 — **STOP** — the solver's pool sizes become a number a human can see

**Files:**
- Modify `src/gaffer/config.py`
- Modify `config.example.toml`
- Modify `src/gaffer/optimize/milp.py` — **PROTECTED**
- Modify `src/gaffer/web/routers/meta.py`, `src/gaffer/web/schemas.py`
- Modify `frontend/src/hubs/model/HealthTab.tsx`, `frontend/src/types.ts`
- Create `tests/test_v12_top_n.py`

> ### STOP
>
> **Do not start the `milp.py` edit.** Report to the orchestrator that Task 9 is ready,
> paste the enumeration below, and wait. Everything else in this task — the config field,
> the example, the Health line, the tests — is unprotected and can be built first; it
> just has no effect until the one line-group lands.
>
> If authorization does not arrive, `DEFAULT_TOP_N` stays the only source, the config
> key is not added (an unread key is worse than no key), `len(fields(Config))` is 52
> rather than 53, and Task 15's numbers change accordingly. Say so before Task 15 runs.

**Read A7 before starting**, especially the mechanical half. The orchestrator ruled
(2026-09-02) that there is **no `[solver]` section**: the key goes in the existing
`[optimizer]`, which `load_config` **splats**. So the dataclass field is named `top_n`,
after its TOML key, and needs no key-by-key read — while the *forgiving* read that
decides an actual solve stays in a module-level reader, because the splat validates
nothing.

### The enumeration — `src/gaffer/optimize/milp.py:728-737`, one line-group

**Before:**

```python
def build_pool(players: pd.DataFrame, ep_by_code_gw: dict,
               my_picks: pd.DataFrame, gws: list[int],
               top_n: dict | None = None) -> pd.DataFrame:
    """Candidate pool: owned players + top-N per position by horizon EP.

    Keeps the MILP small (fast) without losing realistic candidates.
    """
    if top_n is None:
        top_n = DEFAULT_TOP_N
```

**After:**

```python
def build_pool(players: pd.DataFrame, ep_by_code_gw: dict,
               my_picks: pd.DataFrame, gws: list[int],
               top_n: dict | None = None) -> pd.DataFrame:
    """Candidate pool: owned players + top-N per position by horizon EP.

    Keeps the MILP small (fast) without losing realistic candidates.
    """
    if top_n is None:
        # v12 W1 §2.6 (specs/2026-09-01-gaffer-v12-program-design.md). These
        # four numbers decide which players the solver is allowed to consider
        # at all, and until now they existed only here — so a plan that never
        # mentioned an owned player could not be distinguished from a plan
        # that had considered and rejected him. `[optimizer] top_n` in config
        # is the same four numbers where a user can see them, and
        # `optimizer_top_n()` falls back to DEFAULT_TOP_N on anything
        # unreadable: a typo in a TOML file must not silently shrink the pool.
        from gaffer.config import optimizer_top_n

        top_n = optimizer_top_n()
```

`DEFAULT_TOP_N` at L132 is **not** deleted. It stays as the fallback and as the value
`scripts/v10_dnp.py`'s measurement was taken at (the docstring at L69-74 cites it by
name), and `optimizer_top_n()` returns it whenever the config cannot be read — which is
every test in the suite that does not write a `config.toml`.

The import is inside the function, matching this module's own habit and avoiding an
import cycle (`config` is imported by nearly everything).

- [ ] **Write the failing test.** Create `tests/test_v12_top_n.py`:

```python
"""The four numbers that decide who the solver may consider.

`DEFAULT_TOP_N` has picked the candidate pool since the first MILP and has never
appeared anywhere a user could see. That matters for a reason that is not about
tuning: a plan that never mentions an owned player is indistinguishable from a
plan that considered him and rejected him, unless you can find out whether he was
in the pool at all.

The reader is deliberately forgiving. A missing section, a missing key, a typo, a
string where a number should be — every one of them falls back to the shipped
value, because a config error that silently shrinks the solver's pool is a config
error that changes the advice without saying so.

The key lives in `[optimizer]` beside horizon, decay and bench_curve — orchestrator
ruling, 2026-09-02 — and that section is *splatted* into Config, which is why the
field is named `top_n` after its key and why the forgiveness lives in the reader
rather than in `load_config`. The two are pinned against each other below: the
dataclass carries what the file says, the reader carries what the solver gets.
"""

from __future__ import annotations

import dataclasses

import pytest

from gaffer.config import Config, load_config, optimizer_top_n
from gaffer.optimize.milp import DEFAULT_TOP_N


def _cfg(tmp_path, body=""):
    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n" + body)
    return path


def test_the_shipped_default_is_what_it_always_was():
    assert DEFAULT_TOP_N == {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14}


def test_no_config_at_all_gives_the_shipped_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert optimizer_top_n() == DEFAULT_TOP_N


def test_a_config_without_the_section_gives_the_default(tmp_path):
    assert optimizer_top_n(_cfg(tmp_path)) == DEFAULT_TOP_N


def test_the_section_is_read(tmp_path):
    body = "[optimizer]\ntop_n = {GKP = 4, DEF = 10, MID = 12, FWD = 6}\n"
    assert optimizer_top_n(_cfg(tmp_path, body)) == {"GKP": 4, "DEF": 10,
                                                  "MID": 12, "FWD": 6}


def test_a_missing_position_keeps_its_shipped_value(tmp_path):
    """Merged over the default rather than replacing it: a user tuning one
    position should not have to restate the other three, and a solver with no
    goalkeepers in its pool is infeasible rather than fast."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    assert optimizer_top_n(_cfg(tmp_path, body)) == {
        "GKP": 8, "DEF": 30, "MID": 26, "FWD": 14}


def test_an_unknown_position_is_dropped_rather_than_added(tmp_path):
    """`build_pool` iterates the dict and filters `players["position"]`, so an
    unknown key contributes an empty frame — harmless, and a typo that reads
    as harmless is a typo nobody finds. Dropped, so the pool is exactly the
    four positions that exist."""
    body = '[optimizer]\ntop_n = {GKP = 4, MIDD = 99}\n'
    assert set(optimizer_top_n(_cfg(tmp_path, body))) == {"GKP", "DEF", "MID",
                                                       "FWD"}


def test_a_non_numeric_value_falls_back_for_that_position(tmp_path):
    body = '[optimizer]\ntop_n = {GKP = "lots"}\n'
    assert optimizer_top_n(_cfg(tmp_path, body))["GKP"] == 8


def test_a_zero_or_negative_falls_back(tmp_path):
    """A pool of zero at any position makes the squad constraints infeasible,
    which surfaces as "no plan" — a long way from the config line that caused
    it."""
    body = "[optimizer]\ntop_n = {GKP = 0, DEF = -3}\n"
    out = optimizer_top_n(_cfg(tmp_path, body))
    assert (out["GKP"], out["DEF"]) == (8, 22)


def test_a_corrupt_toml_gives_the_default(tmp_path):
    """The serve-time reader convention (`config.lineup_providers`): a broken
    config degrades to the shipped behaviour rather than taking the solver
    down."""
    path = tmp_path / "config.toml"
    path.write_text("[optimizer\n")
    assert optimizer_top_n(path) == DEFAULT_TOP_N


def test_the_key_is_on_the_dataclass_too(tmp_path):
    """Read twice, deliberately, and they are not the same read.

    `optimizer_top_n` is the serve-time reader `build_pool` calls without a
    Config in hand; it merges over the shipped default and forgives anything
    unreadable. `Config.top_n` comes through `[optimizer]`'s splat, which
    forgives nothing and carries exactly what the file said — and it is what
    W5 §6.2's Settings tab will edit. The next test pins the gap between them
    so it cannot rot into a disagreement nobody notices."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    assert load_config(_cfg(tmp_path, body)).top_n["DEF"] == 30


def test_the_splat_carries_a_partial_table_and_the_reader_completes_it(
        tmp_path):
    """The one consequence of putting this key in a splatted section, made
    visible. `[optimizer]` maps TOML keys straight onto dataclass fields, so a
    table naming one position reaches Config naming one position — while the
    solver, which must have four, gets four. Neither is wrong; they answer
    different questions, and a reviewer who "fixes" one to match the other
    breaks whichever they did not read."""
    body = "[optimizer]\ntop_n = {DEF = 30}\n"
    path = _cfg(tmp_path, body)
    assert load_config(path).top_n == {"DEF": 30}
    assert optimizer_top_n(path) == {"GKP": 8, "DEF": 30, "MID": 26,
                                     "FWD": 14}


def test_a_config_with_no_top_n_key_still_loads(tmp_path):
    """The splat's other edge: the field needs a default_factory or every
    existing config.toml in the world stops loading."""
    assert load_config(_cfg(tmp_path)).top_n == DEFAULT_TOP_N


def test_the_build_pool_default_now_comes_from_the_config(tmp_path,
                                                          monkeypatch):
    """The one protected line-group, asserted through behaviour rather than
    through source."""
    import pandas as pd

    from gaffer.optimize.milp import build_pool

    monkeypatch.chdir(tmp_path)
    _cfg(tmp_path, "[optimizer]\n"
                   "top_n = {GKP = 1, DEF = 1, MID = 1, FWD = 1}\n")
    players = pd.DataFrame({
        "code": [1, 2, 3, 4, 5, 6, 7, 8],
        "position": ["GKP", "GKP", "DEF", "DEF", "MID", "MID", "FWD", "FWD"],
    })
    ep = {(c, 1): float(c) for c in range(1, 9)}
    pool = build_pool(players, ep, pd.DataFrame({"code": []}), [1])
    assert len(pool) == 4


def test_the_config_field_count_moved_deliberately():
    """Named here as well as in the degradation file: this key is one of the
    five that move the pin from 48 to 53, and each one should be findable from
    its own test."""
    assert any(f.name == "top_n" for f in dataclasses.fields(Config))
```

- [ ] **Implement the config reader.** In `src/gaffer/config.py`, a module-level reader
beside `lineup_providers` — the same shape, for the same reason (`build_pool` has no
`Config` in hand and cannot be given one without an `optimize/**` signature change):

```python
def optimizer_top_n(path: Path | str = "config.toml") -> dict[str, int]:
    """``[optimizer] top_n`` merged over the shipped default.

    v12 W1 §2.6. Never raises: a missing file, a missing section, a corrupt
    TOML, a typo'd position and a non-numeric value all degrade to the shipped
    value for that position. A config error that silently shrank the solver's
    candidate pool would change the advice without saying so, and the symptom
    — a plan that never mentions a player — looks nothing like its cause.

    Merged rather than replaced so a user tuning one position does not have to
    restate the other three, and unknown keys are dropped so a typo cannot
    contribute an empty position to a pool that then reads as intentional.

    Separate from ``Config.top_n``, which comes through ``[optimizer]``'s
    splat and carries exactly what the file said. That one is what the
    Settings tab edits; this one is what the solver gets. ``build_pool`` has
    no ``Config`` in hand and cannot be given one without an ``optimize/**``
    signature change, which is the other half of why this reader exists.
    """
    from gaffer.optimize.milp import DEFAULT_TOP_N

    out = dict(DEFAULT_TOP_N)
    try:
        raw = tomllib.loads(Path(path).read_text())
        table = raw.get("optimizer", {}).get("top_n", {})
    except Exception:  # noqa: BLE001 — serve-time readers never raise
        return out
    if not isinstance(table, dict):
        return out
    for pos in out:
        value = table.get(pos)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        if value > 0:
            out[pos] = int(value)
    return out
```

`isinstance(value, bool)` is checked first because `True` is an `int` in Python and
`top_n = {GKP = true}` would otherwise set the goalkeeper pool to 1.

And the dataclass field. **`[optimizer]` is splatted** (A7), so this needs **no** line
in `load_config`'s `Config(...)` call at all — the key arrives as a keyword argument on
its own, which is exactly why the field is named `top_n` after the TOML key rather than
`solver_top_n` after its subject. It goes beside `bench_curve`, the section's other
non-scalar field:

```python
    top_n: dict[str, int] = field(
        default_factory=lambda: {"GKP": 8, "DEF": 22, "MID": 26, "FWD": 14})
```

The `default_factory` is load-bearing rather than tidy: without it every existing
`config.toml` in the world — none of which has this key — stops loading.

- [ ] **`config.example.toml`** gains the key **inside the existing `[optimizer]`
section**, after `hit_cost`. No new section:

```toml
# v12: how many players per position the MILP may consider, on top of the ones
# you already own. These four numbers have decided the candidate pool since the
# first solve and lived only in the source until now; they are here so that "he
# was never in the pool" and "he was considered and rejected" are
# distinguishable. Smaller is faster and blinder. A missing position keeps the
# value below and anything unreadable falls back to it too — a typo must not
# quietly shrink the pool.
top_n = { GKP = 8, DEF = 22, MID = 26, FWD = 14 }
```

- [ ] **The Health line.** `Health` gains `solver_top_n: dict[str, int] | None = None`
— named for what it *is* on the wire, a solver pool, since a schema field carries no
TOML section with it — `meta.health()` fills it from `optimizer_top_n()` inside a
`try`, and `HealthTab.tsx`
renders one row per position in the existing Data-freshness card's neighbourhood, under
a "Solver pool" heading, with the sentence *"players per position the solver may
consider, on top of the ones you own"*.

**Not** a bare four numbers: the caption is the whole point of surfacing them.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_top_n.py tests/test_milp.py \
  tests/test_config.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
```

`tests/test_milp.py:109-113` passes `top_n=` explicitly and must be untouched — the
protected edit changes only the `None` branch.

- [ ] **Commit** (`feat: the solver's candidate pool is a number you can read`, staging
`src/gaffer/config.py config.example.toml src/gaffer/optimize/milp.py
src/gaffer/web/routers/meta.py src/gaffer/web/schemas.py frontend/src/types.ts
frontend/src/hubs/model/HealthTab.tsx tests/test_v12_top_n.py`, with the standing
trailers).

---

## Task 10 — `gaffer backup`

**Files:**
- Create `src/gaffer/backup.py`
- Modify `src/gaffer/config.py`, `config.example.toml`
- Modify `src/gaffer/cli.py`
- Create `scripts/com.gaffer.backup.plist`
- Modify `scripts/install_automation.sh`
- Modify `src/gaffer/web/routers/meta.py`, `src/gaffer/web/schemas.py`
- Modify `frontend/src/hubs/model/HealthTab.tsx`, `frontend/src/types.ts`
- Create `tests/test_v12_backup.py`

**Read A9 before starting.** The spec's archive set is missing `data/raw/field/`, which
is the one directory in this tree whose contents cannot be fetched again from anywhere.

- [ ] **Write the failing test.** Create `tests/test_v12_backup.py`. The **restore**
test is named in the W1 gate, so it is the first one written and the one that decides
the design:

```python
"""An archive that restores, and a prune that only ever deletes locally.

The gate for this item is not "an archive appears". It is "extract it into an
empty tree and diff": a backup nobody has restored is a hypothesis.

Two things are deliberate and neither is obvious:

* **`data/raw/field/` is in the set and the spec did not put it there.** The spec
  says field EO samples are covered because they live in
  data/live/field_eo_log.parquet. The *log* does; the sampled *squads* do not —
  `save_field_sample` writes data/raw/field/<season>/gw<N>.json, and a past
  gameweek's top-10k picks cannot be fetched again from anywhere. Everything else
  in this archive is replaceable by a command; those are not.
* **the prune deletes only in the local directory.** `--rsync` copies to a remote
  path, and a retention rule that reached across it would be this tool deleting
  files on a machine it does not own, over a protocol with no undo.
"""

from __future__ import annotations

import tarfile

import pytest

from gaffer import backup


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    """A miniature of the real layout, with one file in every archived root."""
    monkeypatch.chdir(tmp_path)
    for rel, text in (
            ("data/live/player_gw.parquet", "live"),
            ("data/live/field_eo_log.parquet", "eo"),
            ("data/raw/field/2026-27/gw2.json", "squads"),
            ("data/raw/tier_eo/2026-27.json", "tier"),
            ("reports/decision_ledger.json", "ledger"),
            ("models/minutes.joblib", "model"),
            # Not in the set: big, and re-fetchable.
            ("data/history/player_gw.parquet", "history"),
            ("data/raw/news/page.html", "news"),
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return tmp_path


def test_the_archive_extracts_to_a_tree_that_matches(tree, tmp_path):
    """The gate, as a test."""
    archive = backup.run_backup(to=tree / "backups")
    out = tmp_path / "restored"
    out.mkdir()
    with tarfile.open(archive) as tar:
        tar.extractall(out)
    for rel in ("data/live/player_gw.parquet", "data/raw/field/2026-27/gw2.json",
                "reports/decision_ledger.json", "models/minutes.joblib"):
        assert (out / rel).read_text() == (tree / rel).read_text()


def test_the_sampled_squads_are_in_it(tree):
    """The spec's omission, pinned. These are the only files in the tree that
    no command can rebuild."""
    archive = backup.run_backup(to=tree / "backups")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "data/raw/field/2026-27/gw2.json" in names
    assert "data/raw/tier_eo/2026-27.json" in names


def test_the_replaceable_bulk_is_not(tree):
    """67 MB of scraped pages and 3 MB of history that `gaffer build-history`
    rebuilds. Excluded on purpose, and the README says which command rebuilds
    which."""
    archive = backup.run_backup(to=tree / "backups")
    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert not [n for n in names if n.startswith("data/history")]
    assert not [n for n in names if n.startswith("data/raw/news")]


def test_the_name_carries_the_minute(tree):
    archive = backup.run_backup(to=tree / "backups")
    assert archive.name.startswith("gaffer-")
    assert archive.name.endswith(".tar.gz")
    stamp = archive.stem.removeprefix("gaffer-").removesuffix(".tar")
    assert len(stamp) == 13 and stamp[8] == "-"       # YYYYMMDD-HHMM


def test_a_missing_root_is_skipped_rather_than_fatal(tmp_path, monkeypatch):
    """A clone that has never trained has no models/. Backing up four of five
    roots beats backing up none."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "x.json").write_text("{}")
    archive = backup.run_backup(to=tmp_path / "backups")
    with tarfile.open(archive) as tar:
        assert tar.getnames() == ["reports/x.json"]


def test_a_tree_with_nothing_to_archive_says_so_and_writes_no_file(tmp_path,
                                                                   monkeypatch):
    """An empty tar is worse than none: it looks like a successful backup and
    restores to nothing."""
    monkeypatch.chdir(tmp_path)
    assert backup.run_backup(to=tmp_path / "backups") is None
    assert not list((tmp_path / "backups").glob("*.tar.gz"))


def test_the_prune_keeps_the_newest_n(tree):
    dest = tree / "backups"
    dest.mkdir()
    for i in range(6):
        (dest / f"gaffer-2026090{i}-1200.tar.gz").write_text("x")
    backup.prune(dest, keep=3)
    assert sorted(p.name for p in dest.glob("*.tar.gz")) == [
        "gaffer-20260903-1200.tar.gz", "gaffer-20260904-1200.tar.gz",
        "gaffer-20260905-1200.tar.gz"]


def test_the_prune_ignores_files_it_did_not_write(tree):
    """A user's own directory. Deleting by pattern and not by "everything in
    here" is the difference between a retention rule and a data loss."""
    dest = tree / "backups"
    dest.mkdir()
    (dest / "gaffer-20260901-1200.tar.gz").write_text("x")
    (dest / "gaffer-20260902-1200.tar.gz").write_text("x")
    (dest / "important-notes.txt").write_text("mine")
    (dest / "gaffer-notes.md").write_text("also mine")
    backup.prune(dest, keep=1)
    assert (dest / "important-notes.txt").exists()
    assert (dest / "gaffer-notes.md").exists()
    assert len(list(dest.glob("gaffer-*.tar.gz"))) == 1


def test_keep_zero_is_treated_as_keep_everything(tree):
    """A misread config key must not empty the backup directory. There is no
    legitimate reason to ask this command to keep nothing."""
    dest = tree / "backups"
    dest.mkdir()
    (dest / "gaffer-20260901-1200.tar.gz").write_text("x")
    backup.prune(dest, keep=0)
    assert len(list(dest.glob("gaffer-*.tar.gz"))) == 1


def test_the_rsync_target_is_copied_to_and_never_pruned(tree, monkeypatch):
    """The remote half. This tool does not delete on a machine it does not
    own, over a protocol with no undo."""
    calls = []
    monkeypatch.setattr(backup.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or
                        type("R", (), {"returncode": 0, "stderr": ""})())
    backup.run_backup(to=tree / "backups", rsync="host:/vol/gaffer")
    assert calls and calls[0][:2] == ["rsync", "-a"]
    assert calls[0][-1] == "host:/vol/gaffer"


def test_a_failing_rsync_does_not_lose_the_local_archive(tree, monkeypatch):
    """The copy is the optional half. A local archive that exists beats an
    exception that leaves the user believing nothing was backed up."""
    monkeypatch.setattr(backup.subprocess, "run",
                        lambda cmd, **kw:
                        type("R", (), {"returncode": 1,
                                       "stderr": "host unreachable"})())
    archive = backup.run_backup(to=tree / "backups", rsync="host:/vol")
    assert archive is not None and archive.exists()


def test_latest_backup_reads_the_newest_and_its_size(tree):
    dest = tree / "backups"
    backup.run_backup(to=dest)
    newest = backup.latest_backup(dest)
    assert newest is not None
    assert newest["bytes"] > 0
    assert newest["modified_at"].endswith("+00:00")


def test_latest_backup_of_an_absent_directory_is_None(tmp_path):
    """The Health line's empty state: "never", not a zero and not a crash."""
    assert backup.latest_backup(tmp_path / "nope") is None
```

- [ ] **Implement `src/gaffer/backup.py`:**

```python
"""``gaffer backup`` — one tar of the things no command can rebuild.

Spec §2.1 (specs/2026-09-01-gaffer-v12-program-design.md), with one correction
made deliberately and recorded here rather than in a commit nobody re-reads.

The spec's set is ``data/live/``, ``reports/`` and ``models/``, on the grounds
that the field EO samples live in ``data/live/field_eo_log.parquet``. The
*log* does. The sampled *squads* do not: ``data.field.save_field_sample``
writes ``data/raw/field/<season>/gw<N>.json``, and ``data/field.py:43`` says
why they sit under ``raw/`` — they are API payloads, not derived frames. A
past gameweek's top-10k picks cannot be fetched again from anywhere, which
makes them and ``data/raw/tier_eo/`` the only genuinely irreplaceable bytes in
the tree. They are in the archive.

What is deliberately **out**, and what rebuilds it:

* ``data/history/`` (3 MB) — ``gaffer build-history``
* ``data/raw/understat/`` (12 MB) — ``gaffer understat``, slowly
* ``data/raw/vaastav/`` (24 MB) — a download
* ``data/raw/news/`` (67 MB) — a scrape cache. The *derived* corpus that
  matters, ``data/live/availability_log.parquet`` and
  ``live/presser_log.parquet``, is inside the set.
* the timestamped API snapshots under ``data/raw/`` (~34 MB) — a record of
  calls made, not a record of anything the tool needs.

That is ~16 MB in and ~140 MB out, so ``keep = 14`` costs a few hundred
megabytes rather than two gigabytes.
"""

from __future__ import annotations

import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

ROOTS = ["data/live", "data/raw/field", "data/raw/tier_eo", "reports",
         "models"]
"""Archived, in this order. A root that does not exist is skipped."""

NAME_GLOB = "gaffer-*.tar.gz"
"""What :func:`prune` is allowed to consider. Never ``*``: the destination may
be a directory the user also keeps their own files in, and a retention rule
that deletes by "everything here" is a data loss with a schedule."""


def archive_name(now: datetime | None = None) -> str:
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M")
    return f"gaffer-{stamp}.tar.gz"


def run_backup(*, to: Path | str, rsync: str | None = None,
               keep: int = 14, now: datetime | None = None) -> Path | None:
    """Write one archive, optionally copy it, prune the local directory.

    ``None`` when there was nothing to archive at all — an empty tar looks
    exactly like a successful backup and restores to nothing, which is the
    worst of the available outcomes.
    """
    roots = [Path(r) for r in ROOTS if Path(r).exists()]
    if not roots:
        print("backup: nothing to archive — no data/, reports/ or models/")
        return None
    dest = Path(to)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / archive_name(now)
    # Written to its final name rather than through gaffer.io.atomic_write:
    # the archive is a new file every minute, so there is no previous version
    # for a torn write to destroy, and streaming a tarball through a temp
    # would double the peak disk for no gain.
    with tarfile.open(path, "w:gz") as tar:
        for root in roots:
            tar.add(root, arcname=str(root))
    if rsync:
        result = subprocess.run(["rsync", "-a", str(path), rsync],
                                capture_output=True, text=True)
        if result.returncode != 0:
            # Never fatal. The local archive exists and is the thing that
            # matters; raising here would tell the user nothing was backed up,
            # which would be false.
            print(f"backup: rsync to {rsync} failed "
                  f"({result.stderr.strip() or result.returncode}) — the "
                  f"local archive at {path} is written")
    prune(dest, keep=keep)
    return path


def prune(dest: Path | str, *, keep: int = 14) -> list[Path]:
    """Delete all but the newest ``keep`` archives **in the local directory**.

    Never across ``--rsync``: that is a path on a machine this tool does not
    own, reached over a protocol with no undo, and a retention rule that
    crossed it would be deleting somebody else's files on a timer.

    ``keep <= 0`` keeps everything. There is no legitimate reason to ask this
    command to keep nothing, and a misread config key should not empty a
    backup directory.
    """
    if keep <= 0:
        return []
    found = sorted(Path(dest).glob(NAME_GLOB), key=lambda p: p.name)
    doomed = found[:-keep] if len(found) > keep else []
    for path in doomed:
        path.unlink(missing_ok=True)
    return doomed


def latest_backup(dest: Path | str) -> dict | None:
    """``{"path", "modified_at", "bytes"}`` for the newest archive, or None.

    ``None`` is the Health line's "never". Never a zero-byte dict: a size of
    zero would render as a backup that happened and was empty.
    """
    found = sorted(Path(dest).glob(NAME_GLOB), key=lambda p: p.stat().st_mtime)
    if not found:
        return None
    newest = found[-1]
    stat = newest.stat()
    return {"path": str(newest),
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc).isoformat(),
            "bytes": int(stat.st_size)}


def backup_dir(configured: str = "") -> Path:
    """``[backup] dir``, or ``~/gaffer-backups``. Expanded, never relative to
    the project: a backup inside the tree it is backing up is not a backup."""
    return Path(configured).expanduser() if configured \
        else Path.home() / "gaffer-backups"
```

- [ ] **Config.** Three fields, read key-by-key (A7):

```python
    backup_dir: str = ""
    backup_rsync_target: str = ""
    backup_keep: int = 14
```

```python
    backup = raw.get("backup", {})
    # ... beside the existing `odds`/`scen`/`league`/`news`/`digest` reads at
    # config.py:134-140, and then three more keyword arguments in the Config(...)
    # call, after `digest_notify=` at config.py:190:
        backup_dir=str(backup.get("dir", "")),
        backup_rsync_target=str(backup.get("rsync_target", "")),
        backup_keep=int(backup.get("keep", 14)),
```

and `config.example.toml`:

```toml
[backup]
# `gaffer backup` tars data/live/, data/raw/field/, data/raw/tier_eo/,
# reports/ and models/ — roughly 16 MB, so `keep = 14` is a few hundred
# megabytes of archives rather than a few gigabytes. data/history/,
# data/raw/understat/, data/raw/vaastav/ and data/raw/news/ are left out
# because a command rebuilds each of them; the sampled top-10k squads under
# data/raw/field/ are in, because nothing can.
# dir = "~/gaffer-backups"        # the default
# rsync_target = "nas:/volume1/backups/gaffer"
keep = 14
```

- [ ] **The CLI:**

```python
@app.command()
def backup(to: Path = typer.Option(
               None, "--to",
               help="Where to write the archive. Defaults to [backup] dir, "
                    "then ~/gaffer-backups."),
           rsync: str = typer.Option(
               None, "--rsync",
               help="Also copy the archive here with `rsync -a`. Defaults to "
                    "[backup] rsync_target. Never pruned.")):
    """Tar the data no command can rebuild, and keep the last few."""
    from gaffer.backup import backup_dir, run_backup
    from gaffer.config import load_config

    try:
        cfg = load_config()
        configured, target, keep = (cfg.backup_dir, cfg.backup_rsync_target,
                                    cfg.backup_keep)
    except Exception:  # noqa: BLE001 — a clone with no config can still back up
        configured, target, keep = "", "", 14
    dest = Path(to) if to is not None else backup_dir(configured)
    path = run_backup(to=dest, rsync=rsync or target or None, keep=keep)
    if path is None:
        raise typer.Exit(1)
    typer.echo(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")
```

- [ ] **The plist**, `scripts/com.gaffer.backup.plist`, copying
`com.gaffer.prices.plist` exactly and changing three things — the label, the command,
and the time (23:45, thirty minutes after prices at 23:15, so the archive contains the
night's price reading rather than racing it):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.backup</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer backup &gt;&gt; logs/backup.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>23</integer><key>Minute</key><integer>45</integer></dict>
</dict></plist>
```

and `scripts/install_automation.sh`'s loop gains `backup`, its echo line gains
`+ nightly 23:45 backup`, and the README/GUIDE's "seven plists" becomes eight (Task 17).

- [ ] **The Health line.** `Health` gains `last_backup: BackupHealth | None = None`
where `BackupHealth` is `{path: str, modified_at: str, bytes: int}`; `meta.health()`
fills it from `latest_backup(backup_dir(cfg.backup_dir))` inside a `try`; `HealthTab`
renders `"last backup: <ts> (<size>)"` or, when it is `None`, **"never — run `gaffer
backup`"** rather than a blank cell.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_backup.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
plutil -lint scripts/com.gaffer.backup.plist
```

- [ ] **Commit** (`feat: gaffer backup, including the bytes no command can rebuild`,
staging `src/gaffer/backup.py src/gaffer/config.py config.example.toml
src/gaffer/cli.py scripts/com.gaffer.backup.plist scripts/install_automation.sh
src/gaffer/web/routers/meta.py src/gaffer/web/schemas.py frontend/src/types.ts
frontend/src/hubs/model/HealthTab.tsx tests/test_v12_backup.py`, with the standing
trailers).

---

## Task 11 — `gaffer tidy`

**Files:**
- Create `src/gaffer/tidy.py`
- Modify `src/gaffer/cli.py`
- Create `tests/test_v12_tidy.py`

**Read A10 before starting.** Measured on the real tree: this command reclaims **54 KB**
today. The 34 MB next door is out of §2.7's scope and stays out.

- [ ] **Write the failing test.** Create `tests/test_v12_tidy.py`:

```python
"""What is safe to delete, and the four things that are not.

Measured on the real tree before this was written: 33 backtest logs, 28 of them
paired with their report, five orphans totalling 54 KB. That is the whole prize,
and saying so here is the point — a delete command whose value is overstated is a
delete command that gets pointed at something bigger.

The four exclusions each exist because of a specific reader:

* `data/live/backtest_log.parquet` — no tag — is the shared log `run_backtest`
  writes and `/api/history` reads. The glob does not match it, which is luck
  rather than design, so it is asserted rather than assumed.
* only the `v7b_` prefix is swept. `scripts/s2_replay.py` writes
  `backtest_log_s2_<mode>.parquet` and writes **no companion report at all** —
  its evidence is an S2_ARM_DONE line in logs/. "No report ⇒ orphan" would delete
  every S2 arm the moment it was written.
* `logs/advise.log` is read by `/api/health` (LaunchdHealth.last_line). It is
  dated well outside the 30-day cutoff and would qualify within a week.
* the four named logs — availability, field EO, price, and any ledger — are never
  candidates, whatever their age.
"""

from __future__ import annotations

import pytest

from gaffer import tidy


@pytest.fixture()
def tree(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


def _log(tree, name, size=100):
    path = tree / "data" / "live" / name
    path.write_bytes(b"x" * size)
    return path


def test_a_backtest_log_with_no_report_is_a_candidate(tree):
    _log(tree, "backtest_log_v7b_orphan.parquet")
    found = tidy.candidates()
    assert [p.name for p in found["backtests"]] == \
        ["backtest_log_v7b_orphan.parquet"]


def test_a_backtest_log_with_its_report_is_not(tree):
    _log(tree, "backtest_log_v7b_kept.parquet")
    (tree / "reports" / "v7b_kept.json").write_text("{}")
    assert tidy.candidates()["backtests"] == []


def test_the_shared_log_is_never_a_candidate(tree):
    """`/api/history` reads it. The glob does not match it either, and both
    facts are asserted because only one of them was designed."""
    _log(tree, "backtest_log.parquet")
    assert tidy.candidates()["backtests"] == []


def test_an_s2_arm_log_is_never_a_candidate(tree):
    """s2_replay writes no companion report — its evidence is an S2_ARM_DONE
    line in logs/ — so "no report" says nothing about it."""
    _log(tree, "backtest_log_s2_est.parquet")
    assert tidy.candidates()["backtests"] == []


def test_the_named_logs_are_never_candidates(tree):
    for name in ("availability_log.parquet", "field_eo_log.parquet",
                 "price_log.parquet", "presser_log.parquet"):
        _log(tree, name)
    found = tidy.candidates()
    assert found["backtests"] == []
    assert found["logs"] == []


def test_an_old_log_file_is_a_candidate(tree):
    import os
    import time

    path = tree / "logs" / "v7b_q3-f03.log"
    path.write_text("x" * 50)
    old = time.time() - 60 * 86400
    os.utime(path, (old, old))
    assert [p.name for p in tidy.candidates()["logs"]] == ["v7b_q3-f03.log"]


def test_a_recent_log_file_is_not(tree):
    (tree / "logs" / "prices.log").write_text("x")
    assert tidy.candidates()["logs"] == []


def test_the_advise_log_is_never_a_candidate_however_old(tree):
    """It is what `/api/health` shows as the launchd last line, and it is
    already outside the default cutoff — so without this exclusion the first
    `tidy --apply` blanks the Health page."""
    import os
    import time

    path = tree / "logs" / "advise.log"
    path.write_text("x")
    old = time.time() - 400 * 86400
    os.utime(path, (old, old))
    assert tidy.candidates()["logs"] == []


def test_the_dry_run_deletes_nothing_and_reports_the_total(tree, capsys):
    path = _log(tree, "backtest_log_v7b_orphan.parquet", size=2048)
    tidy.run_tidy(apply=False)
    assert path.exists()
    out = capsys.readouterr().out
    assert "backtest_log_v7b_orphan.parquet" in out
    assert "2.0 KB" in out or "0.0 MB" in out
    assert "--apply" in out


def test_apply_deletes_exactly_the_candidates(tree):
    doomed = _log(tree, "backtest_log_v7b_orphan.parquet")
    kept = _log(tree, "backtest_log_v7b_kept.parquet")
    (tree / "reports" / "v7b_kept.json").write_text("{}")
    tidy.run_tidy(apply=True)
    assert not doomed.exists()
    assert kept.exists()


def test_nothing_to_do_says_so_rather_than_printing_an_empty_list(tree,
                                                                  capsys):
    tidy.run_tidy(apply=False)
    assert "nothing to tidy" in capsys.readouterr().out


def test_the_cutoff_is_configurable_and_applies_only_to_logs(tree):
    """An orphaned backtest log is orphaned whatever its age: the report it
    would have been paired with is never going to appear."""
    import os
    import time

    _log(tree, "backtest_log_v7b_orphan.parquet")
    path = tree / "logs" / "old.log"
    path.write_text("x")
    old = time.time() - 10 * 86400
    os.utime(path, (old, old))
    assert len(tidy.candidates(older_than=30)["backtests"]) == 1
    assert tidy.candidates(older_than=30)["logs"] == []
    assert len(tidy.candidates(older_than=5)["logs"]) == 1
```

- [ ] **Implement `src/gaffer/tidy.py`:**

```python
"""``gaffer tidy`` — the two kinds of file that pile up and are safe to lose.

Spec §2.7 (specs/2026-09-01-gaffer-v12-program-design.md).

Measured on the real tree the day this shipped: 33 files matching
``data/live/backtest_log_*.parquet``, 28 of them paired with a
``reports/v7b_<tag>.json``, five orphans totalling **54 KB**. That is the whole
prize, and it is written here so nobody mistakes this for a disk-space tool.
The 150 MB under ``data/raw/`` — 67 MB of scrape cache, 34 MB of timestamped
API snapshots nothing prunes — is out of §2.7's scope, deliberately, and is
recorded as a residual instead. Widening a delete command past its spec is the
most expensive kind of helpfulness available here.

Four exclusions, each with a named reader:

* ``data/live/backtest_log.parquet`` (no tag) is written by
  ``backtest.run_backtest`` and read by ``/api/history``;
* only ``backtest_log_v7b_*`` is swept, because ``scripts/v7b_replay.py`` is
  the only writer that pairs a log with a report. ``scripts/s2_replay.py``
  writes ``backtest_log_s2_<mode>.parquet`` and no report at all;
* ``logs/advise.log`` is ``/api/health``'s launchd line;
* the availability, field EO, price and presser logs are the corpus, not
  output.
"""

from __future__ import annotations

import time
from pathlib import Path

LIVE = Path("data/live")
REPORTS = Path("reports")
LOGS = Path("logs")

BACKTEST_GLOB = "backtest_log_v7b_*.parquet"
KEEP_LOGS = {"advise.log"}
"""Log files that are never candidates, whatever their age."""


def _report_for(path: Path) -> Path:
    tag = path.name.removeprefix("backtest_log_").removesuffix(".parquet")
    return REPORTS / f"{tag}.json"


def candidates(older_than: int = 30) -> dict[str, list[Path]]:
    """``{"backtests": [...], "logs": [...]}`` — what ``--apply`` would delete.

    ``older_than`` applies to ``logs/`` alone. An orphaned backtest log is
    orphaned whatever its age: the report it would have been paired with is
    never going to appear.
    """
    backtests = [p for p in sorted(LIVE.glob(BACKTEST_GLOB))
                 if not _report_for(p).exists()]
    cutoff = time.time() - older_than * 86400
    logs = [p for p in sorted(LOGS.glob("*.log"))
            if p.name not in KEEP_LOGS and p.stat().st_mtime < cutoff]
    return {"backtests": backtests, "logs": logs}


def _size(paths) -> int:
    return sum(p.stat().st_size for p in paths)


def run_tidy(*, apply: bool = False, older_than: int = 30) -> dict:
    """Print what would go; delete it only under ``apply``."""
    found = candidates(older_than)
    every = found["backtests"] + found["logs"]
    if not every:
        print("nothing to tidy")
        return found
    total = _size(every)
    for path in every:
        print(f"  {path}  ({path.stat().st_size / 1024:.1f} KB)")
    print(f"{len(every)} files, {total / 1024:.1f} KB "
          f"({total / 1e6:.1f} MB)")
    if not apply:
        print("dry run — pass --apply to delete")
        return found
    for path in every:
        path.unlink(missing_ok=True)
    print(f"deleted {len(every)} files")
    return found
```

- [ ] **The CLI:**

```python
@app.command()
def tidy(apply: bool = typer.Option(
             False, "--apply",
             help="Actually delete. Without it this only prints."),
         older_than: int = typer.Option(
             30, "--older-than",
             help="Age in days for logs/. Backtest logs are judged by whether "
                  "their report exists, not by age.")):
    """List (or delete) replay logs nothing references and stale run logs."""
    from gaffer.tidy import run_tidy

    run_tidy(apply=apply, older_than=older_than)
```

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_tidy.py
.venv/bin/pytest -q
# and on the real tree, dry-run only — this must print five files and 54 KB
.venv/bin/python -m gaffer.cli tidy
```

**Do not run `tidy --apply` on the real tree.** The plan measured which five files it
names; deleting them is the user's decision and not part of shipping the command.

- [ ] **Commit** (`feat: gaffer tidy, honest about how little it reclaims`, staging
`src/gaffer/tidy.py src/gaffer/cli.py tests/test_v12_tidy.py`, with the standing
trailers).

---

## Task 12 — LAN write protection

**Files:**
- Modify `src/gaffer/web/app.py` (L47-52)
- Modify `src/gaffer/config.py`, `config.example.toml`
- Modify `src/gaffer/cli.py` (`ui`, L584-635)
- Modify `frontend/src/api/client.ts`
- Create `tests/test_v12_lan_token.py`
- Create `frontend/src/api/token.test.ts`

**Read A11 before starting.** One middleware and one keyword-only argument, so that
`create_app()` keeps meaning what it means to every existing test.

- [ ] **Write the failing test.** Create `tests/test_v12_lan_token.py`:

```python
"""Reads are open; writes need the token, and only when you asked for LAN.

`gaffer ui --lan` binds 0.0.0.0 and the banner has always said, out loud, that
there is no auth. That was an honest description of a loopback tool served to a
home network, and it stops being adequate the moment the network has a guest on
it: every write route here mutates state a person's season depends on — pinned
p_play overrides, watchlist stars, saved drafts, queued jobs.

The shape is a middleware and a keyword-only argument, not a per-route
dependency. There are ten-odd non-GET routes across nine routers and one of them
lives in a protected module, so a `Depends` on each would be a wide diff and an
unauthorized one. `create_app()` with no token enforces nothing, which is every
existing caller and every existing test.

403 rather than 401: a 401 invites the browser's own credential prompt for a
scheme this app does not implement, and the user would have nowhere to type.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_without_a_token_nothing_changes(clone):
    """Loopback, which is the default and the overwhelmingly common case."""
    client = TestClient(create_app())
    assert client.get("/api/ping").status_code == 200
    # A write with no header: it may 404 or 422 on a cold clone, but it must
    # not be refused for a token that was never required.
    assert client.post("/api/watchlist", json={}).status_code != 403


def test_a_get_is_open_even_with_a_token(clone):
    client = TestClient(create_app(token="s3cret"))
    assert client.get("/api/ping").status_code == 200


def test_a_write_without_the_header_is_refused(clone):
    client = TestClient(create_app(token="s3cret"))
    response = client.post("/api/watchlist", json={})
    assert response.status_code == 403
    assert "X-Gaffer-Token" in response.json()["detail"]


def test_a_write_with_the_wrong_token_is_refused(clone):
    client = TestClient(create_app(token="s3cret"))
    assert client.post("/api/watchlist", json={},
                       headers={"X-Gaffer-Token": "nope"}).status_code == 403


def test_a_write_with_the_right_token_reaches_the_route(clone):
    """"Reaches" rather than "succeeds": on a cold clone the route itself may
    still refuse. What matters is that the refusal is the route's and not the
    middleware's."""
    client = TestClient(create_app(token="s3cret"))
    assert client.post("/api/watchlist", json={},
                       headers={"X-Gaffer-Token": "s3cret"}
                       ).status_code != 403


def test_every_write_method_is_covered(clone):
    """POST, PUT, PATCH and DELETE. A DELETE that slipped through would be the
    worst one to miss — /api/jobs/current cancels a running job."""
    client = TestClient(create_app(token="s3cret"))
    for call in (client.post, client.put, client.patch, client.delete):
        assert call("/api/watchlist").status_code == 403


def test_options_and_head_pass_with_get(clone):
    """A preflight that fails closed makes every write look like a network
    error rather than a refusal, and the page would say nothing useful."""
    client = TestClient(create_app(token="s3cret"))
    assert client.options("/api/ping").status_code != 403
    assert client.head("/api/ping").status_code != 403


def test_the_comparison_is_constant_time():
    """Not because a home network is a threat model, but because
    `secrets.compare_digest` costs one import and the alternative is a habit
    that travels to code where it matters."""
    import inspect

    from gaffer.web import app as app_mod

    assert "compare_digest" in inspect.getsource(app_mod)


def test_a_generated_token_is_not_predictable():
    from gaffer.web.app import generate_token

    assert len({generate_token() for _ in range(20)}) == 20
    assert len(generate_token()) >= 16


def test_the_config_key_is_read(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n"
                    '[web]\ntoken = "from-config"\n')
    assert load_config(path).web_token == "from-config"


def test_the_token_is_absent_by_default(tmp_path):
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n")
    assert load_config(path).web_token == ""
```

- [ ] **Implement `web/app.py`.** Signature and middleware:

```python
def generate_token() -> str:
    """A LAN token when the config has none. Printed once, stored nowhere.

    v12 W1 §2.8. Not written into config.toml: spec §8 forbids the app
    editing that file, and a token persisted by a tool the user did not ask to
    persist it is a surprise in a file that also holds an API key.
    """
    import secrets

    return secrets.token_urlsafe(16)


def create_app(*, token: str | None = None) -> FastAPI:
    app = FastAPI(title="gaffer", docs_url=None, redoc_url=None)
    # ... the body is unchanged: app.state, the two exception handlers, /api/ping,
    # the twenty-five include_router calls and the static mount, exactly as they
    # are at web/app.py:47-100. The middleware goes in immediately before the SPA
    # 404 handler, so it is registered after every router and runs before all of
    # them (Starlette middleware wraps the whole app, routing included).

    # v12 W1 §2.8 (specs/2026-09-01-gaffer-v12-program-design.md). `token`
    # is None for every loopback caller and every test, and the middleware is
    # not installed at all in that case — so the default app is byte-for-byte
    # the app that shipped.
    #
    # A middleware rather than a dependency on each write route: there are
    # ten-odd non-GET routes across nine routers, one of them in the protected
    # whatif module, so per-route would be a wide diff and an unauthorized one.
    #
    # 403 and not 401: a 401 invites the browser's own credential prompt for a
    # scheme this app does not implement, leaving the user a dialog with
    # nowhere to type the thing it is asking for.
    if token:
        @app.middleware("http")
        async def _require_token(request: Request, call_next):
            if request.method in ("GET", "HEAD", "OPTIONS"):
                return await call_next(request)
            import secrets

            sent = request.headers.get("X-Gaffer-Token", "")
            if not secrets.compare_digest(sent, token):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "this gaffer is served to the network; "
                                       "writes need the X-Gaffer-Token header "
                                       "printed when `gaffer ui --lan` "
                                       "started"})
            return await call_next(request)

    return app
```

- [ ] **Config:** `web_token: str = ""`, read from `raw.get("web", {}).get("token", "")`
key-by-key, plus `config.example.toml`:

```toml
[web]
# Only consulted by `gaffer ui --lan`. On loopback there is no token and no
# check — the interface is the security model. On the network, every non-GET
# request needs `X-Gaffer-Token: <this>`; leave it unset and one is generated
# and printed each time you start, which is fine for a phone you are about to
# scan a QR code with and awkward for a bookmark.
# token = "something long and private"
```

- [ ] **The CLI.** Inside `ui`, in the `if lan:` branch, before the banner's last line:

```python
    from gaffer.web.app import create_app, generate_token

    token = None
    if lan:
        try:
            token = load_config().web_token or None
        except Exception:  # noqa: BLE001 — a clone with no config still serves
            token = None
        generated = token is None
        token = token or generate_token()
        # ... the existing LAN banner is unchanged: lan_mod.lan_ip(), the
        # "On your network" line and lan_mod.qr_lines() at cli.py:604-614. The
        # token lines go after them, replacing the "no auth" sentence at :615.
        if generated:
            typer.echo(f"Write token (this run only): {token}")
            typer.echo(f"Open on your phone with ?token={token} — the page "
                       f"stores it. Set [web] token in config.toml to keep "
                       f"one across restarts.")
        else:
            typer.echo("Writes need the [web] token from config.toml; open "
                       "with ?token=<it> once per device.")
```

and the existing line *"Serving to the whole network with no auth — trusted home network
only"* is **replaced**, because after this task it is false:

```python
        typer.echo("Serving to the whole network. Reads are open; writes need "
                   "the token above.")
```

Finally `uvicorn.run(create_app(), ...)` becomes `uvicorn.run(create_app(token=token),
...)`. **The shape of that call is pinned** by `tests/test_v9d_degradation.py` (the app
*instance*, never an import string, so `workers=` is impossible); passing a keyword to
`create_app` does not change that shape, but re-read the pin before editing and stop if
it asserts more than this plan expects.

- [ ] **The front end.** `client.ts`'s `request()` is the one chokepoint:

```typescript
export const TOKEN_KEY = 'gaffer-token'

/**
 * The LAN write token, from `?token=` on first load or from storage after.
 *
 * `useTheme`'s idiom, try/catch included: a browser refusing site data must
 * degrade to "this tab works, the next one will not" rather than throwing on
 * every request. The parameter is consumed into storage and left in the URL —
 * stripping it would mean touching history from a module that has no business
 * doing so, and the URL is one the user typed off a QR code on their own phone.
 */
export function readToken(): string {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('token')
    if (fromUrl) {
      localStorage.setItem(TOKEN_KEY, fromUrl)
      return fromUrl
    }
    return localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    try {
      return new URLSearchParams(window.location.search).get('token') ?? ''
    } catch {
      return ''
    }
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = readToken()
  const headers = token
    ? { ...(init?.headers ?? {}), 'X-Gaffer-Token': token }
    : init?.headers
  const response = await fetch(path, { ...init, headers })
  // ... the rest of `request` is unchanged (client.ts:38-43): parse the body,
  // throw ApiError on a non-ok status, return the body.
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, body?.detail ?? body)
  }
  return body as T
}
```

The header is sent on **every** request including GETs. Simpler than branching on the
method, harmless on loopback (nothing reads it), and it means a future read route that
becomes protected needs no client change.

- [ ] **`frontend/src/api/token.test.ts`:** the parameter is stored on first load; a
later load with no parameter reads storage; a throwing `localStorage` still returns the
URL's token; no token means no header; a token means the header is on a GET as well as a
POST.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_lan_token.py tests/test_v9d_degradation.py
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run
```

The **whole** Python suite matters here: `create_app()` is called in dozens of tests and
a signature change that broke one of them would mean the keyword was not keyword-only.

- [ ] **Commit** (`feat: writes need a token when the UI is served to the network`,
staging `src/gaffer/web/app.py src/gaffer/config.py config.example.toml
src/gaffer/cli.py frontend/src/api/client.ts frontend/src/api/token.test.ts
tests/test_v12_lan_token.py`, with the standing trailers).

---

## Task 13 — the "as of" strip, mounted once

**Files:**
- Modify `src/gaffer/web/routers/meta.py` — the cycle's one new route
- Modify `src/gaffer/web/schemas.py` — `Freshness`, `FreshnessRow`
- Create `frontend/src/kit/FreshnessStrip.tsx`
- Create `frontend/src/kit/FreshnessStrip.test.tsx`
- Modify `frontend/src/kit/AppShell.tsx`, `frontend/src/kit/index.ts`
- Modify `frontend/src/kit/AppShell.test.tsx`
- Modify `frontend/src/types.ts`
- Create `tests/test_v12_freshness.py`

**Read A12 before starting.** One mount in `AppShell`, five mtimes, and three
consequences for existing tests.

**This task moves the route pin from 45 to 46.** It is the only route this cycle adds.
The pin itself lives in the protected `tests/test_v11_degradation.py` and moves in Task
15, so this task's own suite run will show that one file failing. **That is expected;
note it and carry on.** Any *other* degradation failure means stop.

- [ ] **Write the failing test.** Create `tests/test_v12_freshness.py`:

```python
"""When each of the five things last happened, in one place.

Every hub in this app can be read as if it were current. A page of ownership
figures from a scrape that has not run since Saturday looks exactly like a page
of ownership figures from an hour ago, and the only cure is a line at the top of
every page saying which it is.

All five rows are file mtimes, and that is a decision rather than a shortcut: each
of these artifacts is rewritten whole by the job that produces it, so the mtime is
the run stamp. A timestamp parsed out of a file's *contents* can be stale inside a
file that was just rewritten, which is a subtler lie than a stale mtime.

`age_hours` is computed here and not on the client, so the colouring rule is one
implementation rather than two — and `None` means "never", which the strip draws
in grey. Never 0.0: a zero age is "just now", which is the exact opposite.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.data import store
from gaffer.web.app import create_app


@pytest.fixture()
def clone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _get(path="/api/meta/freshness"):
    return TestClient(create_app()).get(path).json()


def test_a_cold_clone_is_five_rows_of_never(clone):
    """The honest empty state, and the main case on a fresh install. Five
    rows, not zero: a strip that renders nothing teaches the reader that its
    absence means everything is fine."""
    body = _get()
    assert [r["source"] for r in body["rows"]] == [
        "refresh", "odds", "field", "advise", "backup"]
    assert all(r["modified_at"] is None for r in body["rows"])
    assert all(r["age_hours"] is None for r in body["rows"])


def test_an_age_is_never_zero_for_a_missing_file(clone):
    """0.0 hours is "just now", which is the strongest possible claim and the
    opposite of the truth."""
    assert all(r["age_hours"] != 0.0 for r in _get()["rows"])


def test_a_refreshed_clone_reports_the_live_frame(clone):
    store.save(pd.DataFrame({"code": [1]}), "live/player_gw.parquet")
    row = next(r for r in _get()["rows"] if r["source"] == "refresh")
    assert row["modified_at"] is not None
    assert row["age_hours"] is not None and row["age_hours"] < 1


def test_the_odds_row_reads_the_newest_gameweek_file(clone):
    store.save(pd.DataFrame({"gw": [2]}), "live/odds/gw2.parquet")
    store.save(pd.DataFrame({"gw": [3]}), "live/odds/gw3.parquet")
    row = next(r for r in _get()["rows"] if r["source"] == "odds")
    assert row["path"].endswith("gw3.parquet")


def test_the_advise_row_reads_the_newest_advice_artifact(clone):
    (clone / "reports").mkdir()
    (clone / "reports" / "gw2-advice.json").write_text("{}")
    (clone / "reports" / "gw3-advice.json").write_text("{}")
    row = next(r for r in _get()["rows"] if r["source"] == "advise")
    assert row["path"].endswith("gw3-advice.json")


def test_the_backup_row_reads_the_configured_directory(clone, monkeypatch):
    (clone / "config.toml").write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n"
        f'[backup]\ndir = "{clone / "bk"}"\n')
    (clone / "bk").mkdir()
    (clone / "bk" / "gaffer-20260901-2345.tar.gz").write_text("x")
    row = next(r for r in _get()["rows"] if r["source"] == "backup")
    assert row["modified_at"] is not None


def test_a_broken_config_leaves_the_backup_row_at_never(clone):
    """The endpoint is on every page load. It degrades one row rather than
    500ing the strip, which would take the freshness line off every hub the
    moment a config key was mistyped."""
    (clone / "config.toml").write_text("[backup\n")
    row = next(r for r in _get()["rows"] if r["source"] == "backup")
    assert row["age_hours"] is None


def test_the_endpoint_never_errors(clone):
    """Same contract as /api/review. This is drawn on every page in the app,
    so a 500 here is a 500 everywhere."""
    assert TestClient(create_app()).get(
        "/api/meta/freshness").status_code == 200


def test_this_cycle_added_exactly_this_route(clone):
    paths = set(create_app().openapi()["paths"])
    assert "/api/meta/freshness" in paths
```

- [ ] **Implement the schemas:**

```python
class FreshnessRow(BaseModel):
    source: Literal["refresh", "odds", "field", "advise", "backup"]
    path: str | None = None
    """What was actually stat'd, so a surprising age is diagnosable."""
    modified_at: str | None = None
    age_hours: float | None = None
    """Hours since the file was written, or ``None`` for "never".

    Never 0.0 for an absent file. Zero is "just now", which is the strongest
    claim this row can make and the exact opposite of what an absent file
    means. The client colours on ``None`` first and on the number second.
    """


class Freshness(BaseModel):
    rows: list[FreshnessRow] = Field(default_factory=list)
```

- [ ] **Implement the route** in `routers/meta.py`, reusing the existing `_stat` helper
(L155-161) rather than writing a second one:

```python
@router.get("/meta/freshness", response_model=Freshness)
def freshness() -> Freshness:
    """When each of the five standing jobs last wrote something.

    v12 W1 §2.9 (specs/2026-09-01-gaffer-v12-program-design.md). Drawn at the
    top of every hub, so it must never error and never block: five stats and,
    at worst, one config read that is allowed to fail on its own.

    All five are mtimes. Each of these artifacts is rewritten whole by the job
    that writes it, so the mtime *is* the run stamp — where a timestamp parsed
    out of a file's contents can be stale inside a file that was just
    rewritten, which is the harder lie to notice.
    """
    def _row(source: str, path: Path | None) -> FreshnessRow:
        if path is None:
            return FreshnessRow(source=source)
        present, modified, age = _stat(path)
        return FreshnessRow(source=source,
                            path=str(path) if present else None,
                            modified_at=modified, age_hours=age)

    def _newest(directory: Path, pattern: str) -> Path | None:
        if not directory.is_dir():
            return None
        found = sorted(directory.glob(pattern),
                       key=lambda p: p.stat().st_mtime)
        return found[-1] if found else None

    backup_newest = None
    try:
        from gaffer.backup import NAME_GLOB, backup_dir

        backup_newest = _newest(backup_dir(load_config().backup_dir),
                                NAME_GLOB)
    except Exception:  # noqa: BLE001 — one grey row, never a broken strip
        backup_newest = None

    return Freshness(rows=[
        _row("refresh", store.DATA_DIR / "live" / "player_gw.parquet"),
        _row("odds", _newest(store.DATA_DIR / "live" / "odds", "gw*.parquet")),
        _row("field", store.DATA_DIR / "live" / "field_eo_log.parquet"),
        _row("advise", _newest(REPORTS, "gw*-advice.json")),
        _row("backup", backup_newest),
    ])
```

`_row(source, None)` and `_row(source, <a path that does not exist>)` both produce the
"never" row, so an absent *directory* and an absent *file* read identically — which they
should, because to the reader they are the same fact.

- [ ] **Implement `frontend/src/kit/FreshnessStrip.tsx`:**

```tsx
import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import type { Freshness, FreshnessRow } from '../types'

const LABELS: Record<string, string> = {
  refresh: 'data', odds: 'odds', field: 'field EO',
  advise: 'advice', backup: 'backup',
}

/**
 * Green under a day, amber under three, red beyond, grey for never.
 *
 * `null` is checked before the number and not folded into it: "never" and
 * "very old" are different states, and a `>= 72` branch would paint a cold
 * clone red as if something had gone wrong rather than not yet happened.
 */
export function tone(age: number | null): string {
  if (age === null) return 'text-text-faint'
  if (age < 24) return 'text-moss'
  if (age < 72) return 'text-amber'
  return 'text-rust'
}

export function ageText(age: number | null): string {
  if (age === null) return 'never'
  if (age < 1) return 'just now'
  if (age < 48) return `${Math.round(age)}h`
  return `${Math.round(age / 24)}d`
}

export default function FreshnessStrip() {
  const [rows, setRows] = useState<FreshnessRow[] | null>(null)

  useEffect(() => {
    // Fails soft and stays visible. A strip that disappeared when its own
    // fetch failed would teach the reader that no strip means nothing stale.
    apiGet<Freshness>('/api/meta/freshness')
      .then((data) => setRows(data.rows))
      .catch(() => setRows([]))
  }, [])

  if (rows === null) return null

  const known = new Map(rows.map((r) => [r.source, r]))
  return (
    <div
      data-testid="freshness-strip"
      className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs
                 text-text-muted"
    >
      <span className="text-text-faint">as of</span>
      {Object.entries(LABELS).map(([source, label]) => {
        const row = known.get(source)
        const age = row?.age_hours ?? null
        return (
          <span key={source} className="whitespace-nowrap">
            {`${label} `}
            <span
              className={tone(age)}
              title={row?.modified_at ?? 'never run'}
              data-testid={`freshness-${source}`}
            >
              {ageText(age)}
            </span>
          </span>
        )
      })}
    </div>
  )
}
```

`Object.entries(LABELS)` rather than `rows.map` so the strip shows all five sources even
when the server sent fewer — an older server, or a payload that lost a row, must produce
five greys rather than a shorter strip nobody notices is shorter.

**No anchors anywhere in this component** (A12): `AppShell.test.tsx:24` asserts the shell
holds exactly six links.

- [ ] **Mount it in `AppShell`,** in **both** branches, immediately inside `<main>`:

```tsx
      <main className="p-4"><FreshnessStrip />{children}</main>
```
```tsx
      <main className="max-w-[1180px] p-6"><FreshnessStrip />{children}</main>
```

Inside `<main>` rather than above the nav so it inherits the page's padding and sits
where a reader's eye already starts, and in both branches because a phone is exactly the
device on which "is this current?" is hardest to answer.

- [ ] **Fix `frontend/src/kit/AppShell.test.tsx`.** It does not mock `../api/client`, so
the strip would fire a real `fetch` into jsdom. Add, at the top, the same mock every
other suite uses:

```tsx
vi.mock('../api/client', () => ({
  ApiError: class extends Error { status = 0; detail: unknown = null },
  apiGet: vi.fn(() => new Promise(() => {})),
  apiPost: vi.fn(),
}))
```

A forever-pending promise, matching `App.test.tsx:7-13`'s own choice and its reason: the
strip then renders `null` and the existing six-link and children assertions are
untouched.

- [ ] **`FreshnessStrip.test.tsx`:** five labels render; a `null` age is "never" in grey;
`< 24` is green; `< 72` amber; older is red; a rejecting fetch still renders five rows
of "never"; a payload missing a source still renders five rows; the `title` carries the
timestamp; **and** `container.querySelectorAll('a')` is empty.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_freshness.py
.venv/bin/pytest -q
# expect exactly one failure, in tests/test_v11_degradation.py, on the route
# count. Anything else: stop and report.
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Then the 390px pass: the strip is `flex-wrap`, so it must wrap rather than scroll the
body sideways — v9b's standing convention.

- [ ] **Commit** (`feat: every hub says how old the numbers on it are`, staging
`src/gaffer/web/routers/meta.py src/gaffer/web/schemas.py frontend/src/types.ts
frontend/src/kit/FreshnessStrip.tsx frontend/src/kit/FreshnessStrip.test.tsx
frontend/src/kit/AppShell.tsx frontend/src/kit/AppShell.test.tsx
frontend/src/kit/index.ts tests/test_v12_freshness.py`, with the standing trailers).

---

## Task 14 — `gaffer mcp`

**Files:**
- Modify `pyproject.toml`, `uv.lock`
- Create `src/gaffer/mcp_server.py`
- Modify `src/gaffer/cli.py`
- Create `tests/test_v12_mcp.py`

**Read A13 before starting.** Five of the six tools wrap a router function; the sixth
cannot, and the dependency is heavier than "the `mcp` package" suggests.

- [ ] **Add the dependency first**, because everything else in this task imports it:

```bash
uv add mcp
git diff --stat pyproject.toml uv.lock
.venv/bin/python -c "import mcp, importlib.metadata as m; print(m.version('mcp'))"
# expect 2.1.1
```

**Resolved before this plan was written**, so the numbers are checkable rather than
hopeful: `mcp==2.1.1`, plus fifteen transitive packages not previously in the tree
(`mcp-types`, `httpx2`, `httpcore2`, `sse-starlette`, `python-multipart`, `jsonschema`,
`jsonschema-specifications`, `referencing`, `rpds-py`, `attrs`, `cryptography`, `cffi`,
`pyjwt`, `opentelemetry-api`, `truststore`), and **`pydantic` 2.13.4 → 2.13.5**.

If `uv add` resolves anything other than `mcp==2.1.1`, **stop and report the resolved
version** before writing a line of the server: the plan's assertions name it.

The pydantic bump is why this task's verification runs the whole suite. Every model in
`web/schemas.py` is a pydantic model and a patch release is still a release.

- [ ] **Write the failing test.** Create `tests/test_v12_mcp.py`:

```python
"""Six read tools over the payloads the web app already serves.

The point of this server is that Claude Code can read this tree without a browser
and without a second implementation of anything. So every tool is the router's own
function, and the test that matters is not "the tool returns something" — it is
"the tool returns the same thing the endpoint does".

The one tool that is not a router function is `whatif`, and that is the spec being
wrong about the code rather than a shortcut: POST /api/whatif is
`status_code=202, response_model=JobAccepted`. It queues a job and returns an id. A
tool returning a job id would be useless, and polling one from a stdio subprocess
would put the job runner's lifecycle inside it. The synchronous body —
`solve_whatif` — is exported, and whatif.py is protected but importable.

No write tools, in v12 or in this file: spec §8 names them as out of scope.
"""

from __future__ import annotations

import inspect

import pytest

from gaffer import mcp_server


def test_the_six_tools_are_exactly_these():
    assert sorted(mcp_server.TOOLS) == [
        "explain", "freshness", "health", "ledger", "projections", "whatif"]


def test_every_tool_is_read_only():
    """Spec §8: no write tools in v12. Asserted by name rather than by
    intention, because "read-only" is a property a later cycle can lose in one
    line."""
    for name in mcp_server.TOOLS:
        assert not any(word in name
                       for word in ("save", "set", "add", "delete", "run",
                                    "start", "post", "write"))


def test_every_tool_has_a_docstring_the_model_can_read():
    """An MCP tool's docstring is its description on the wire, so an
    undocumented tool is an unusable one."""
    for name, fn in mcp_server.TOOLS.items():
        assert (fn.__doc__ or "").strip(), name


def test_each_schema_round_trips():
    """§2.10's first test. A tool whose signature cannot be turned into a JSON
    schema fails at registration time, in a subprocess, with no output."""
    for name, fn in mcp_server.TOOLS.items():
        sig = inspect.signature(fn)
        for param in sig.parameters.values():
            assert param.annotation is not inspect.Parameter.empty, \
                f"{name}.{param.name}"


def test_projections_is_the_players_endpoints_own_payload(monkeypatch):
    """§2.10's second test: the tool returns the router's payload, not a
    re-derivation of it."""
    from gaffer.web.routers import players as players_router

    sentinel = [{"code": 1, "name": "A"}]
    monkeypatch.setattr(players_router, "players",
                        lambda **kw: sentinel)
    assert mcp_server.TOOLS["projections"]() == sentinel


def test_projections_forwards_its_filters(monkeypatch):
    from gaffer.web.routers import players as players_router

    seen = {}
    monkeypatch.setattr(players_router, "players",
                        lambda **kw: seen.update(kw) or [])
    mcp_server.TOOLS["projections"](position="MID", team=3, top=5)
    assert seen["position"] == "MID" and seen["team"] == 3


def test_top_truncates_and_is_not_passed_to_the_router(monkeypatch):
    """`players()` has no `top` parameter — it has position, team, search and
    sort. `top` is the tool's own, because a model reading 700 rows to answer
    "who are the best five midfielders" is the cost this server exists to
    avoid."""
    from gaffer.web.routers import players as players_router

    monkeypatch.setattr(players_router, "players",
                        lambda **kw: [{"code": c} for c in range(10)])
    assert len(mcp_server.TOOLS["projections"](top=3)) == 3


def test_whatif_calls_the_solver_body_and_not_the_job_route(monkeypatch):
    from gaffer.web.routers import whatif as whatif_router

    seen = {}

    def fake(req, gw):
        seen["req"], seen["gw"] = req, gw
        return {"diff": []}

    monkeypatch.setattr(whatif_router, "solve_whatif", fake)
    monkeypatch.setattr(mcp_server, "_latest_gw", lambda: 5)
    out = mcp_server.TOOLS["whatif"](transfers_in=[1], transfers_out=[2])
    assert out == {"diff": []}
    assert seen["gw"] == 5
    assert seen["req"].force_in == [1] and seen["req"].ban == [2]


def test_whatif_maps_the_chip_code(monkeypatch):
    from gaffer.web.routers import whatif as whatif_router

    seen = {}
    monkeypatch.setattr(whatif_router, "solve_whatif",
                        lambda req, gw: seen.update(chip=req.chip) or {})
    monkeypatch.setattr(mcp_server, "_latest_gw", lambda: 5)
    mcp_server.TOOLS["whatif"](transfers_in=[], transfers_out=[], chip="wc")
    assert seen["chip"] == "wc"


def test_a_tool_on_a_cold_clone_returns_a_sentence_rather_than_a_traceback(
        tmp_path, monkeypatch):
    """A stdio server's exception is a dead subprocess and a model with no
    idea why. Every tool answers `{"error": ...}` instead, carrying the domain
    message the CLI would have printed."""
    monkeypatch.chdir(tmp_path)
    out = mcp_server.TOOLS["projections"]()
    assert isinstance(out, dict) and "error" in out
    assert "gaffer advise" in out["error"]


def test_freshness_and_health_answer_on_a_cold_clone(tmp_path, monkeypatch):
    """These two are the ones a model reaches for *because* something is
    wrong, so neither may need a working tree."""
    monkeypatch.chdir(tmp_path)
    assert mcp_server.TOOLS["freshness"]()["rows"]
    assert "data" in mcp_server.TOOLS["health"]()


def test_the_server_builds_without_starting(tmp_path, monkeypatch):
    """Registration is where a bad signature fails, and it fails in a
    subprocess with no output — so it is done here, in-process, instead."""
    monkeypatch.chdir(tmp_path)
    server = mcp_server.build_server()
    assert server is not None


def test_the_dependency_is_pinned_in_the_project_metadata():
    import pathlib

    text = pathlib.Path("pyproject.toml").read_text()
    assert "mcp" in text
```

- [ ] **Implement `src/gaffer/mcp_server.py`:**

```python
"""``gaffer mcp`` — this tree, readable by Claude Code over stdio.

Spec §2.10 (specs/2026-09-01-gaffer-v12-program-design.md). Six tools, all
reads, each one the router function that already serves the same payload to the
web UI. No second implementation of anything: a tool that re-derived a number
would drift from the page showing it, and the drift would be invisible from
both sides.

**One correction to the spec.** It says each tool is a thin wrapper over the
existing router function. That is true of five. ``POST /api/whatif`` is
``status_code=202, response_model=JobAccepted``: it queues a job on the web
app's runner and returns an id. A tool returning a job id would be useless, and
polling one from a stdio subprocess would put the runner's lifecycle inside it.
So ``whatif`` wraps :func:`gaffer.web.routers.whatif.solve_whatif`, the
synchronous body the job runs — an import from a protected module, which is not
an edit to it.

**No write tools**, here or in v12 at all — spec §8 names them out of scope. The
tools are also named so that stays checkable: nothing here is a verb that
changes something.

Every tool returns ``{"error": "..."}`` rather than raising. An exception out of
a stdio server is a dead subprocess and a model with no idea why, where the
domain message ("run `gaffer advise` first") is exactly the thing that would
have told it what to do.
"""

from __future__ import annotations

from typing import Any, Callable


def _safe(fn: Callable[[], Any]) -> Any:
    """Run ``fn``; return ``{"error": <message>}`` instead of raising."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — see the module docstring
        return {"error": str(exc) or exc.__class__.__name__}


def _latest_gw() -> int:
    from gaffer.artifacts import latest_gw
    from gaffer.errors import GafferError

    gw = latest_gw()
    if gw is None:
        raise GafferError("nothing on disk yet — run `gaffer advise` first")
    return int(gw)


def projections(position: str | None = None, team: int | None = None,
                top: int | None = None) -> Any:
    """This week's expected points per player, as the Players page sees them.

    ``position`` is GKP/DEF/MID/FWD; ``team`` is an FPL team *code*; ``top``
    keeps only the first N rows after the endpoint's own sort (highest
    ``ep_next`` first).
    """
    def call():
        from gaffer.web.routers import players as router

        rows = router.players(position=position, team=team)
        # `top` is this tool's own, not the endpoint's: `players()` takes
        # position, team, search and sort and returns every candidate. A model
        # reading seven hundred rows to answer "the best five midfielders" is
        # the cost this server exists to avoid.
        return rows[:top] if top else rows
    return _safe(call)


def explain(code: int) -> Any:
    """Why one player's expected points are what they are — the same breakdown
    the Players page shows when you open a row. ``code`` is the FPL player
    code, which is stable across seasons (``element`` is not)."""
    def call():
        from gaffer.web.routers import players as router

        return router.explain(code)
    return _safe(call)


def whatif(transfers_in: list[int], transfers_out: list[int],
           chip: str = "none") -> Any:
    """Preview a set of transfers against the saved board. Solves nothing on
    the FPL site and starts no job — it re-solves locally and returns the
    baseline, the constrained plan and their difference.

    ``transfers_in`` become ``force_in`` (the solve must include them) and
    ``transfers_out`` become ``ban`` (it may not hold them). ``ban`` is
    stronger than "sell": it also forbids buying the player back, which is the
    closest the constraint vocabulary gets and is stated here rather than
    quietly approximated.
    """
    def call():
        from gaffer.web.routers import whatif as router
        from gaffer.web.schemas import WhatIfRequest

        req = WhatIfRequest(force_in=list(transfers_in),
                            ban=list(transfers_out), chip=chip)
        return router.solve_whatif(req, _latest_gw())
    return _safe(call)


def ledger(gw: int | None = None) -> Any:
    """The banked decision ledger: what was advised, what was done, and how
    each graded week turned out. ``gw`` narrows it to one gameweek."""
    def call():
        from gaffer.web.routers import review as router

        payload = router.review().model_dump()
        if gw is not None:
            payload["gws"] = [row for row in payload["gws"]
                              if int(row.get("gw", -1)) == int(gw)]
        return payload
    return _safe(call)


def freshness() -> Any:
    """How old each of the five standing data sources is — the same line the
    UI draws at the top of every page. Answers on a tree with no data."""
    def call():
        from gaffer.web.routers import meta as router

        return router.freshness().model_dump()
    return _safe(call)


def health() -> Any:
    """Data files, model ages, the launchd log, the season check and the last
    backup. Answers on a tree with no data."""
    def call():
        from gaffer.web.routers import meta as router

        return router.health().model_dump()
    return _safe(call)


TOOLS: dict[str, Callable[..., Any]] = {
    "projections": projections,
    "explain": explain,
    "whatif": whatif,
    "ledger": ledger,
    "freshness": freshness,
    "health": health,
}


def build_server():
    """Register the six tools. Built here rather than at import so a bad
    signature fails in a test rather than in a subprocess with no output."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("gaffer")
    for fn in TOOLS.values():
        server.add_tool(fn)
    return server


def run() -> None:
    """Serve over stdio until the client disconnects."""
    build_server().run()
```

**Before writing `build_server`, read the installed package's own API**:

```bash
.venv/bin/python -c "from mcp.server.fastmcp import FastMCP; help(FastMCP.add_tool)"
```

`mcp` 2.x is not the API any model remembers. If `FastMCP` is not at
`mcp.server.fastmcp`, or `add_tool` takes a different shape, **use what the installed
version exposes** and record the deviation in the commit message. The six functions and
their contracts do not change; only the registration call does.

- [ ] **The CLI:**

```python
@app.command()
def mcp():
    """Serve this tree to an MCP client (Claude Code) over stdio.

    Add it with:  claude mcp add gaffer -- gaffer mcp
    """
    from gaffer.mcp_server import run

    run()
```

No `typer.echo` anywhere in this command: stdout **is** the protocol channel, and a
banner would be a parse error at the other end.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_mcp.py
.venv/bin/pytest -q          # the WHOLE suite: pydantic moved 2.13.4 -> 2.13.5
```

A test failing anywhere in `web/` after the pydantic bump is a real regression, not
noise. **Stop and report it** rather than pinning the old version — the version is a
resolution, and hiding a break behind it defers the same break.

- [ ] **Commit** (`feat: gaffer mcp — six read tools over the payloads the UI already
serves`, staging `pyproject.toml uv.lock src/gaffer/mcp_server.py src/gaffer/cli.py
tests/test_v12_mcp.py`, with the standing trailers). The README section is Task 17.

---

## Task 15 — **STOP** — the pins move, and the config pin gets v11's treatment

**Files (eight, seven of them protected):**
- Modify `tests/test_v8f_degradation.py` — **PROTECTED**
- Modify `tests/test_v8g_degradation.py` — **PROTECTED**
- Modify `tests/test_v9c_degradation.py` — **PROTECTED**
- Modify `tests/test_v9d_degradation.py` — **PROTECTED**
- Modify `tests/test_v10_degradation.py` — **PROTECTED**
- Modify `tests/test_v10b_degradation.py` — **PROTECTED**
- Modify `tests/test_v11_degradation.py` — **PROTECTED**
- Modify `tests/test_v10_config_providers.py` — unprotected

> ### STOP
>
> **Do not start this task.** Report to the orchestrator that Task 15 is ready, paste the
> enumeration below, and wait for explicit authorization to edit seven protected files.
>
> **Do not start it before Tasks 9, 10, 12 and 13 have landed either**, authorized or
> not: this task writes the *measured* new values, and if Task 9's STOP was refused the
> config count is 52 rather than 53. Re-measure immediately before editing; do not copy
> the numbers out of this plan.
>
> If authorization does not arrive, W1 cannot ship at all — five config fields and one
> route exist and eight assertions say they do not. Say so plainly rather than
> shipping a red suite.

**Read A8 and A14 before starting.**

### Part 1 — the route pin, one file, one number

v11 finished the route-pin restructure, so there is exactly one absolute route
assertion in the suite and W1 moves it by one.

| File | Line | Today | After |
| --- | --- | --- | --- |
| `tests/test_v11_degradation.py` | 349 | `assert len(paths) == 45` | `assert len(paths) == 46` |

The docstring above it (L338-348) claims *"45 at the branch point (3404fc3) and 45 now:
every serve-side change this cycle made is an additive field"* — a sentence about v11
that is still true about v11 and is now the wrong sentence for this assertion to carry.
It gains a paragraph rather than losing the old one, because the v11 claim is worth
keeping and the v12 claim is a different one:

```python
    """45 at the branch point (3404fc3) and 45 at the end of v11: every
    serve-side change *that* cycle made was an additive field on a model that
    already existed.

    **This is the only absolute route pin in the suite**, which is what v11's
    restructure bought — and v12 W1 is the first cycle to spend it. 45 → 46,
    and the one is `GET /api/meta/freshness` (§2.9), the endpoint behind the
    "as of" strip that every hub draws. Pinned by name below as well as by
    count, because a count alone would let a route be added and another
    removed in one cycle.
    """
```

and the assertion gains the by-name half:

```python
    assert len(paths) == 46
    assert "/api/meta/freshness" in paths
    assert not [p for p in paths
                if p.startswith(("/api/board", "/api/season",
                                 "/api/compare"))]
```

The absence assert on L350-351 is **untouched** — it is v11's claim about v11 and
`/api/meta/freshness` collides with none of those three prefixes.

### Part 2 — the config pin, eight files, v11's method

`len(dataclasses.fields(Config)) == 48` is asserted eight times. W1 adds five fields, so
without a restructure this cycle moves eight numbers and buys seven authorizations —
and so does every future cycle that adds a key. `tests/test_v10_config_providers.py`'s
module docstring records what that already cost once: v10 **abandoned a designed config
field** because two protected files pinned the count.

Each historical file's absolute count becomes the by-name claim its own cycle is
entitled to make. In five of the eight, **that claim is already on the line above**.

| # | File | Line | Today | After | Protected? |
| --- | --- | --- | --- | --- | --- |
| 1 | `test_v8f_degradation.py` | 301 | `assert len(names) == 48` + the `digest_notify` claims at L296-300 | the claims only | **yes** |
| 2 | `test_v8g_degradation.py` | 283 | `assert len(names) == 48` + the no-`band`/`uncertainty` claim at L277-281 | the claim only | **yes** |
| 3 | `test_v9c_degradation.py` | 323 | the bare count | a by-name claim (below) | **yes** |
| 4 | `test_v9d_degradation.py` | 421 | the bare count | a by-name claim | **yes** |
| 5 | `test_v10_degradation.py` | 422 | the bare count + `lineup_providers()` at L423-424 | the `lineup_providers` half only, plus the absence claim | **yes** |
| 6 | `test_v10b_degradation.py` | 266 | the bare count | a by-name claim | **yes** |
| 7 | `test_v11_degradation.py` | 330 | the bare count | a by-name claim | **yes** |
| 8 | `test_v10_config_providers.py` | 86 | the count + the `news_lineup_providers` absence at L87-88 | the absence only | no |
| 9 | `tests/test_v12_w1_degradation.py` | — | — | **the sole `assert len(...) == 53`**, plus W1's five by name | new |

**The four by-name replacements**, each of which restates in code what that file's
docstring already says in prose:

`test_v9c_degradation.py:315-323` — *"no new config keys; ADVISE_TIMEOUT_S is a module
constant that finally acquired a reader, not a knob"*:

```python
def test_the_config_gained_no_field():
    """Spec §2: no new config keys. ``ADVISE_TIMEOUT_S`` is a module constant
    that finally acquired a reader, not a knob.

    v12 W1 §2.6/§2.8 (specs/2026-09-01-gaffer-v12-program-design.md): this
    asserted an absolute count of 48, in one of seven protected files that
    did. That shape had already cost one cycle a designed feature — see
    ``tests/test_v10_config_providers.py``'s docstring — so it becomes the
    claim this cycle is actually entitled to make, and the total lives in
    ``tests/test_v12_w1_degradation.py`` alone.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert not [n for n in names if "timeout" in n or "abandon" in n]
```

`test_v9d_degradation.py:413-421` — *"ABANDON_TIMEOUT_S is an engineering deadline on a
local single-lane runner, not something a user tunes"* — takes the same body, since it
is the same claim about the same constant one cycle later. Give the two different
function names if they collide in a shared run; they are in different modules, so they
do not.

`test_v10b_degradation.py:262-266` — *"the season the field log is read for comes from
the existing `current_season`; the scenario path is a module constant in chip_policy"*:

```python
    names = {f.name for f in dataclasses.fields(Config)}
    assert "current_season" in names
    assert not [n for n in names if "scenario_path" in n or "chip" in n]
```

`test_v11_degradation.py:324-330` — *"nothing in a UI cycle is a knob"*:

```python
    names = {f.name for f in dataclasses.fields(Config)}
    assert not [n for n in names
                if "bank" in n or "rank" in n or "wins" in n or "board" in n]
```

`test_v10_degradation.py:413-424` keeps its `lineup_providers()` assertion verbatim —
that is the whole substance of its claim — and its docstring's second half, which
explains that A6 wanted a 49th field and the tree refused it, gains one sentence saying
the refusal's cause was retired in v12 W1 and the design question is open again. That
sentence is the point of doing this restructure at all.

### Part 3 — where the totals now live

In `tests/test_v12_w1_degradation.py` (created in Task 16, so if Tasks 15 and 16 are
run out of order the file is created here and extended there):

```python
def test_the_config_gained_exactly_five_fields():
    """48 at 27f7933 and 53 now, and **this is the only absolute config-field
    pin in the suite.**

    Seven protected files used to assert 48. That is not a hypothetical cost:
    ``tests/test_v10_config_providers.py``'s docstring records v10 abandoning
    a designed dataclass field because two of them did, and settling for a
    module-level reader instead. v12 W1 replaced each with the by-name claim
    its own cycle is entitled to make — v11's route-pin restructure, applied
    to the other pin — and a future cycle that adds a key moves this number,
    here, and nowhere else.

    Pinned as a total *and* by name: a count alone would let a key be added
    and another removed in one cycle, and W1's claim is precisely which five.
    """
    import dataclasses

    from gaffer.config import Config

    names = {f.name for f in dataclasses.fields(Config)}
    assert len(names) == 53
    assert {"backup_dir", "backup_rsync_target", "backup_keep",
            "top_n", "web_token"} <= names


def test_only_one_file_pins_the_absolute_config_field_count():
    """A rail on the rails, exactly as v11 wrote for routes. Without it the
    eighth pin grows back the next time somebody adds a key and reaches for
    the nearest example."""
    import pathlib
    import re

    hits = [p.name for p in pathlib.Path("tests").glob("test_*.py")
            if re.search(r"len\((?:names|dataclasses\.fields\(Config\))\)"
                         r"\s*==\s*\d+", p.read_text())]
    assert hits == ["test_v12_w1_degradation.py"]
```

### Verification

```bash
# re-measure FIRST. Do not trust this plan's numbers.
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# expect: 46 12 53   (or 46 12 52 if Task 9's STOP was refused)

.venv/bin/pytest -q tests/ -k degradation
.venv/bin/pytest -q tests/test_v10_config_providers.py
.venv/bin/pytest -q

grep -rn "len(names) ==\|fields(Config)) ==" tests/
# expect exactly one hit, in tests/test_v12_w1_degradation.py
grep -rn "len(paths) ==" tests/
# expect exactly one hit, in tests/test_v11_degradation.py
```

Note the asymmetry and do not "fix" it: after this cycle the **route** total is pinned in
`test_v11_degradation.py` and the **config** total in `test_v12_w1_degradation.py`. Each
lives in exactly one file, which is the property that matters; moving the route pin into
the newer file as well would be a protected edit that buys nothing.

- [ ] **Commit** — one commit for all eight files, so the restructure reads as a single
change:

```bash
git add tests/test_v8f_degradation.py tests/test_v8g_degradation.py \
  tests/test_v9c_degradation.py tests/test_v9d_degradation.py \
  tests/test_v10_degradation.py tests/test_v10b_degradation.py \
  tests/test_v11_degradation.py tests/test_v10_config_providers.py \
  tests/test_v12_w1_degradation.py && git commit -m "$(cat <<'EOF'
test: one absolute config-field pin, and per-cycle claims everywhere else

Eight files pinned len(fields(Config)) == 48, seven of them protected. Every
cycle entitled to add a config key therefore had to buy seven authorizations
first — and one cycle did not: test_v10_config_providers.py's docstring records
v10 abandoning a designed dataclass field for a module-level reader because two
protected files pinned the count.

This is v11's route-pin restructure applied to the other pin. Each historical
count becomes the by-name claim its own cycle is entitled to make, and in five of
the eight files that claim was already asserted on the line above — v8f names
digest_notify, v8g names the absent band/uncertainty keys, v10 names
lineup_providers, v10_config_providers names the field it did not add. The total
moves to tests/test_v12_w1_degradation.py and reads 53.

Unlike v11's, this restructure could not be done against an unchanged number: W1
adds five keys and doing the shape change first would have meant a second
authorization round for a no-op. The mitigation is that the count moves in exactly
one file; the other seven lose a number rather than gaining a different one, and
each replacement is checkable against its own docstring.

The route pin moves too — 45 → 46, the freshness endpoint — in the one file v11
left it in.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 16 — the degradation rails (gate G1)

**Files:**
- Create/extend `tests/test_v12_w1_degradation.py`
- Modify `frontend/src/hubs/responsive.test.tsx`

Every rail here is a state a real machine reaches, and several of them are the state
*this* machine is in today.

- [ ] **Write `tests/test_v12_w1_degradation.py`.**

**Block 1 — the atomic write (§2.11, §1).**
- A failed write leaves the previous file byte-identical, once per family: text
  (`digest.save_digest`), parquet (`snapshot.append_snapshot`), bytes
  (`routers/assets._bank`). Three families, three tests, because they fail in three
  different places.
- **The census.** The exact set of modules still containing `os.replace`, asserted by
  name, tolerant of exactly the two documented exceptions:

```python
def test_the_rename_lives_in_one_place_and_the_exceptions_are_named():
    """A9 and A15. Twenty modules open-coded this idiom; nineteen now call the
    helper. journal.py keeps its own because it is import-only this cycle, and
    advise.py keeps its own if Task 4's authorization did not arrive — both
    are recorded residuals rather than tolerated drift, which is why this is
    an equality and not a `<=`. A twenty-first copy fails here."""
    import pathlib
    import re

    pattern = re.compile(r"(?<!dataclasses\.)(?<!\.)\bos\.replace\(")
    hits = sorted(p.relative_to("src").as_posix()
                  for p in pathlib.Path("src").rglob("*.py")
                  if pattern.search(p.read_text()))
    assert hits == ["gaffer/io.py", "gaffer/journal.py"]
```

  If Task 4 was **not** authorized, the expected list is
  `["gaffer/advise.py", "gaffer/io.py", "gaffer/journal.py"]` and the docstring says the
  authorization did not arrive — a rail that records the residual rather than one that
  quietly disappears.

**Block 2 — the EO constants (§2.2).** The three are in `(0, 1)`; no other module
assigns a numeric literal to a `*_EO` name; `captain_table` still reads a percent
column. (These live in `tests/test_v12_eo_constants.py`; the degradation file asserts
only the grep, because that is the one that decays silently.)

**Block 3 — the season guard (§2.3, §2.4).**
- Two seasons in the field log, overlapping element ids: the reader returns only the
  named season's, and a bare call is a `TypeError`.
- `GET /api/players` on a clone whose config names a season the log does not carry:
  every row's `field_eo`, `field_se` and `field_n` is `None` and **not 0.0** — v11's
  contract, still holding across §2.3's change.
- `/api/health` on a clone with no events: `season_ok is None`, and the banner's
  `=== false` therefore does not draw.
- `season_from_events` on an empty frame: `None`, never a guess.

**Block 4 — the refusals (§2.5, §2.7, §2.1).**
- `track-pens` with every gameweek degraded and a banked report: exit 1, file unchanged.
- `track-pens` with nothing banked: writes.
- `tidy` dry-run deletes nothing; `tidy --apply` never touches
  `data/live/backtest_log.parquet`, `backtest_log_s2_*.parquet`, the availability/field
  EO/price logs, or `logs/advise.log`.
- `backup` on a tree with nothing to archive writes no file and returns `None` — an
  empty tar restores to nothing and looks like a success.
- `prune(keep=0)` deletes nothing; `prune` ignores files not matching `gaffer-*.tar.gz`.

**Block 5 — the LAN token (§2.8).**
- `create_app()` with no token: a POST is not a 403.
- `create_app(token=...)`: GET/HEAD/OPTIONS pass, POST/PUT/PATCH/DELETE are 403 with a
  detail naming the header.

**Block 6 — the strip (§2.9).**
- `/api/meta/freshness` on a cold clone: five rows, every `age_hours` `None`, none 0.0.
- `/api/meta/freshness` with a broken `config.toml`: 200, and only the backup row is
  grey.
- It never 500s, on any tree. It is drawn on every page in the app.

**Block 7 — the MCP tools (§2.10).**
- Every tool returns `{"error": ...}` rather than raising on a cold clone.
- `freshness` and `health` answer *without* one — they are what a model reaches for when
  something is wrong.
- `TOOLS` has exactly six keys and none of them is a verb that writes.

**Block 8 — the counts.**

```python
def test_the_job_kinds_are_still_twelve():
    """W1 adds three CLI commands and no lane. A thirteenth kind would also
    need a row in ABANDON_TIMEOUT_S or SLOW_ABANDON_KINDS, pinned as jointly
    exhaustive in the protected test_v9d_degradation.py."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 12
```

plus the two pin tests written out in Task 15's Part 3, plus the rail asserting only one
file pins each total.

- [ ] **Update `frontend/src/hubs/responsive.test.tsx`.** The strip is new chrome on
every page: assert it wraps at 390px rather than scrolling the body sideways, and that
it does not push a hub's `PageHeader` off screen. If the strip is the only thing that
moved, one added case is enough — do not restructure the file.

- [ ] **Verify.**

```bash
.venv/bin/pytest -q tests/test_v12_w1_degradation.py
.venv/bin/pytest -q tests/ -k degradation
git diff main --stat -- 'tests/test_*_degradation.py'
# expect: test_v12_w1_degradation.py, plus v9c (T4), v8c/v10b (T6) and the
# seven of T15 — and nothing else. If a file appears that no STOP named,
# stop and report.
cd frontend && npx vitest run
```

- [ ] **Commit** (`test: v12 W1 degradation rails and the two pins`, staging
`tests/test_v12_w1_degradation.py frontend/src/hubs/responsive.test.tsx`, with the
standing trailers).

---

## Task 17 — the docs

**Files:**
- Modify `README.md`
- Modify `docs/GUIDE.md`

- [ ] **README — the automation table.** Seven plists become **eight**. Three places say
"seven" and all three move: the `install_automation.sh` description (L905-910), the
bullet list under it, and the `launchctl unload` line (L935), which is a brace expansion
and needs `backup` adding. The new bullet, in the voice of its neighbours:

> - **Nightly 23:45** — `gaffer backup`, half an hour after the price check, so the
>   archive contains the night's reading rather than racing it. Tars `data/live/`,
>   `data/raw/field/`, `data/raw/tier_eo/`, `reports/` and `models/` — about 16 MB — into
>   `~/gaffer-backups` and keeps the last fourteen. `data/history/`,
>   `data/raw/understat/`, `data/raw/vaastav/` and `data/raw/news/` are left out because
>   a command rebuilds each of them; the sampled top-10k squads under `data/raw/field/`
>   are in, because nothing can.

- [ ] **README — the new commands**, in the voice the file already uses:

  - `gaffer backup [--to DIR] [--rsync TARGET]` — the above, plus: `--rsync` copies with
    `rsync -a` and the remote copy is **never pruned**, because a retention rule reaching
    across it would be this tool deleting files on a machine it does not own.
  - `gaffer tidy [--apply] [--older-than DAYS]` — dry-run by default. What it targets
    (replay logs whose `reports/v7b_<tag>.json` never appeared, and `logs/*.log` past the
    cutoff) and, said plainly, **how little it reclaims**: 54 KB on this tree today.
    What it will never touch: the shared `backtest_log.parquet` that `/api/history`
    reads, the S2 arm logs whose evidence lives only in `logs/`, the availability, field
    EO and price logs, and `logs/advise.log`.
  - `gaffer mcp` — a stdio MCP server, six read tools, no writes. With the line the spec
    asks for:

    ```
    claude mcp add gaffer -- gaffer mcp
    ```

    and the two sentences that make it usable: the tools are `projections`, `explain`,
    `whatif`, `ledger`, `freshness` and `health`; `whatif` re-solves locally and starts
    no job, and a transfer out reaches the solver as "don't own him", which also rules
    out buying him back.

- [ ] **README — `gaffer ui --lan` is no longer unauthenticated.** The existing text
says so in at least two places and both are now false. Replace with: reads are open,
writes need `X-Gaffer-Token`, the token comes from `[web] token` or is generated and
printed once per run, and the phone picks it up from `?token=` and stores it.

- [ ] **README — the residuals**, recorded here rather than lost:

  1. `journal.py` keeps its own copy of the atomic-write idiom — it is import-only for
     this cycle, and Task 16's census names it so a twenty-first copy cannot appear
     quietly (and `advise.py` too, if Task 4 was not authorized).
  2. The spec asks for a `[solver]` section; there is none. `top_n` lives in the
     existing `[optimizer]` beside every other solver knob, by orchestrator ruling —
     which means **W2 §3.4's `price_timing` and W5 §6.2's whitelist read `[optimizer]`
     too**, and the spec's `[solver]` wording is stale wherever it appears.
  3. `gaffer tidy` reclaims 54 KB. The real accumulation is **~34 MB of timestamped API
     snapshots** under `data/raw/` (`bootstrap-*.json` at 1.7 MB apiece, `fixtures-*`,
     `odds-*`, `ags-*`, `entry-*`) that nothing prunes, plus 67 MB of `data/raw/news/`.
     Out of §2.7's scope and deliberately not swept: silently widening a delete command
     past its spec is the most expensive kind of helpfulness available in this cycle.
  4. The rollover guard's served half reads the **banked** events snapshot, not the API,
     because `/api/health` is disk-only by contract. So it answers "is the data on disk
     the data the config describes", which is the state that matters, and it says
     nothing about a season FPL has published and this machine has not yet fetched.
  5. The MCP server exposes no write tools (spec §8) and no resources or prompts —
     `whatif` is the one tool that computes, and it computes locally and banks nothing.

- [ ] **GUIDE.md.** The automation table at L254-265 gains the backup row; the "seven
launchd jobs" at L254 becomes eight; and the Health-tab description at L220 gains the
season banner, the solver pool and the last-backup line. The `--lan` paragraph, wherever
it appears, gains the token sentence.

- [ ] **Commit** (`docs: v12 W1 — backup, tidy, the MCP server, and a LAN that checks`,
staging exactly `README.md docs/GUIDE.md`, with the standing trailers).

---

## Task 18 — final verification, the gate checklist and the ROADMAP

**Files:**
- Modify `docs/superpowers/specs/2026-09-01-gaffer-v12-program-design.md` (§2's gate)
- Modify `docs/superpowers/ROADMAP.md`

CONVENTIONS §7: the implementer builds this and does not run G2. Fill in the **measured**
G1 numbers from your own final run; leave every G2 box unchecked.

- [ ] **G1 — suites, types, build, and the audits.**

```bash
.venv/bin/pytest -q
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Baselines to beat: the re-measured branch counts from this plan's header (3193 Python;
frontend re-measured at Task 0) plus this cycle's new tests, all green.

Then the protected diff — **and unlike v11, this one is not empty**, which is the whole
character of W1:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/**' src/gaffer/web/jobs.py \
  src/gaffer/web/routers/whatif.py \
  tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py \
  scripts/s2_replay.py
# EXPECTED, and only these:
#   src/gaffer/advise.py                  (T4 §2.11, T5 §2.2)
#   src/gaffer/optimize/differentials.py  (T5 §2.2)
#   src/gaffer/optimize/milp.py           (T9 §2.6)
# set_pieces.py, jobs.py, whatif.py, test_advise.py, test_odds.py,
# test_web_jobs.py and s2_replay.py must be ABSENT. whatif.py is imported by
# the MCP server and must show no diff.

git diff main --stat -- 'tests/test_*_degradation.py'
# EXPECTED: test_v12_w1_degradation.py (new), v9c (T4), v8c and v10b (T6),
# and v8f/v8g/v9c/v9d/v10/v10b/v11 (T15). Nothing else.

git diff main --stat -- 'data/**' 'reports/**' 'models/**' 'logs/**' \
  config.toml 'src/gaffer/web/static/**'
# must be EMPTY
```

And every provenance comment is present on every protected edit:

```bash
git diff main -- src/gaffer/advise.py src/gaffer/optimize/differentials.py \
  src/gaffer/optimize/milp.py | grep -c "v12 W1 §"
# at least one per authorized line-group: 4 (advise x2, differentials, milp)
```

And the pin audit:

```bash
.venv/bin/python -c "
import os, tempfile, dataclasses
os.chdir(tempfile.mkdtemp())
from gaffer.web.app import create_app
from gaffer.web.job_kinds import JOB_KINDS
from gaffer.config import Config
print(len(create_app().openapi()['paths']), len(JOB_KINDS),
      len(dataclasses.fields(Config)))"
# 46 12 53

grep -rn "len(paths) ==" tests/          # exactly one: test_v11_degradation.py
grep -rn "fields(Config)) ==\|len(names) ==" tests/
                                          # exactly one: test_v12_w1_degradation.py
```

**The gate's own two extra items (spec §2):**

```bash
# 1. an archive that restores
.venv/bin/pytest -q tests/test_v12_backup.py -k restore
# and by hand, because the gate says "extracts and diffs a fixture tree":
uv run gaffer backup --to /tmp/gaffer-gate
mkdir -p /tmp/gaffer-restore && tar -xzf /tmp/gaffer-gate/gaffer-*.tar.gz \
  -C /tmp/gaffer-restore
diff -r reports/ /tmp/gaffer-restore/reports/ && echo RESTORE_OK

# 2. refresh against the live API passes the rollover guard
uv run gaffer refresh
# expect the row count, not the refusal. A refusal here means either the guard
# is wrong or config.toml genuinely names the wrong season — check which
# before "fixing" anything.
```

Security ritual (CONVENTIONS §8): grep the whole branch diff for keys and tokens —
**including the generated LAN token, which must appear in no committed file** — confirm
no `data/`, `reports/`, `models/`, `logs/` or `config.toml` path appears in
`git diff main --stat`, and confirm `git show main:config.toml` fails.

**No commit at this step.** The numbers go into the checklist below.

- [ ] **Write the checklist into the spec's §2**, under the existing `**W1 gate:**`
line, G1 filled from the run above and every G2 box unchecked:

```markdown
### G1 — suites, rails, pins (measured by the implementer)

- [x] `.venv/bin/pytest -q` — <N> passed (branch baseline 3193 + <new> new)
- [x] `npx tsc --noEmit` — clean
- [x] `npx vitest run` — <N> passed (baseline <M> + <new> new)
- [x] `npm run build` — clean
- [x] Protected diff is exactly the five authorized STOPs and nothing else:
      `advise.py` (§2.11 write, §2.2 constants), `optimize/differentials.py`
      (§2.2), `optimize/milp.py` (§2.6), and the ten protected test files of
      §2.3 and the pin restructure. Every line-group carries its `# v12 W1 §`
      provenance comment. `set_pieces.py`, `web/jobs.py`,
      `routers/whatif.py`, `test_advise.py`, `test_odds.py`,
      `test_web_jobs.py` and `s2_replay.py` show zero diff — `whatif.py` is
      imported by the MCP server and not edited
- [x] Pins: job kinds still 12, **OpenAPI paths 45 → 46** (`/api/meta/freshness`,
      the cycle's only route), **config fields 48 → 53** (`backup_dir`,
      `backup_rsync_target`, `backup_keep`, `top_n`, `web_token`)
- [x] Exactly one file in the suite pins each absolute count: routes in
      `test_v11_degradation.py`, config fields in `test_v12_w1_degradation.py`
- [x] `os.replace` census: nineteen of twenty copies migrated; the survivors
      are `gaffer/io.py` and `gaffer/journal.py` (import-only), asserted by
      name so a twenty-first cannot appear quietly
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
      empty tree and diffed against `reports/`, clean
- [x] `gaffer refresh` against the live API passes the rollover guard

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
place to spend it is §2.6**: an `[optimizer] top_n` typo is the one change in W1 that
could move a plan, and the rail that a missing section reproduces
`DEFAULT_TOP_N` exactly is the cheaper version of the same check.

### Live spot-checks (orchestrator, on the dev server)

- [ ] Every hub draws the "as of" strip, once, with five sources; a source with
      no file reads "never" in grey rather than "0h".
- [ ] `gaffer ui --lan` prints a token; a phone opened with `?token=` can star a
      watchlist player, and the same phone without it gets the 403 sentence
      rather than a silent failure.
- [ ] Model → Health shows the solver pool sizes with their caption, the last
      backup with its size, and — on a machine whose `config.toml` names the
      right season — no red banner.
- [ ] `claude mcp add gaffer -- gaffer mcp`, then ask Claude Code for the top
      five midfielders and for `health` on a tree with no advice: the first
      answers, the second answers, and neither kills the subprocess.
- [ ] `gaffer tidy` names five files and 54 KB. `gaffer backup` writes ~16 MB.
```

- [ ] **Commit the checklist** (`docs: v12 W1 gate checklist with the measured G1
numbers, G2 unfilled`, staging only the spec, with the standing trailers).

- [ ] **The ROADMAP.** Add a v12 W1 entry in the file's own style — `### <name> —
<summary> (in progress, branch \`<branch>\`)`, a `Spec: … · Plan: …` line, `- [x]`
bullets, a `- Pins:` line, a `- Residuals:` line and a closing `- Suite:` line:

```markdown
### v12 W1 — hygiene (in progress, branch `feat/gaffer-v12`)
Spec: `specs/2026-09-01-gaffer-v12-program-design.md` (§1, §2 = the W1 gate) · Plan: `plans/2026-09-01-gaffer-v12-w1-hygiene.md`
- [ ] §2.11 one atomic write: the spec said six copies of the temp-then-rename idiom and there were **twenty**, in three families — so the helper serves text, parquet-through-`store` and raw bytes, and nineteen of the twenty migrated. Two latent bugs fixed by construction: `presser_log` had no pid in its temp name, `understat` and `chip_scenarios` had no `finally`
- [ ] §2.2 one set of EO constants: `differentials.py` held two of the three the spec said it exported and none of them in fractions; `TEMPLATE_EO` moved there rather than being found there, and this module's own two readers convert at the comparison because `league_eo` is a percent that gets served
- [ ] §2.3 season-guarded field EO: the keyword has existed since v10b and was optional, and `routers/players.py` forgot it — recorded as a residual twice, closed here, at the cost of two protected pins that asserted the bare call
- [ ] §2.4 rollover guard: `refresh` refuses on a mismatch and names both values and both keys; `/api/health` answers from the **banked** events snapshot, because that router is disk-only by contract, and `season_ok` is three-state so a cold clone is not an alarm
- [ ] §2.5 `track_pens` refusal, on both shapes of degraded run — all gameweeks broken, and no gameweeks at all — and never when there is nothing banked to protect
- [ ] §2.6 `top_n` in config — in the existing `[optimizer]`, not the spec's new `[solver]` (orchestrator ruling, so **W2 §3.4 and W5 §6.2 follow**), which makes it a *splatted* key: the field is named for the TOML key and the forgiving merge-over-default lives in the reader `build_pool` calls, because the splat validates nothing. Surfaced on Health with the caption that is the point of surfacing it
- [ ] §2.1 `gaffer backup` + the eighth plist: **`data/raw/field/` is in the archive and the spec did not put it there** — the EO *log* is under `data/live/`, the sampled top-10k *squads* are not, and they are the only bytes in this tree no command can rebuild
- [ ] §2.7 `gaffer tidy`, honest about reclaiming 54 KB; the ~34 MB of timestamped API snapshots next door is out of the spec's scope and stayed out
- [ ] §2.8 LAN write protection: one middleware and a keyword-only `create_app(token=)`, so every existing caller and test is untouched; 403 rather than 401
- [ ] §2.9 the "as of" strip, mounted **once** in `AppShell` rather than six times in six hubs — which also covers `/league/rival/:id`, the route with no hub
- [ ] §2.10 `gaffer mcp`: six read tools, five of them the router's own function. `whatif` is not — `POST /api/whatif` returns a job id — so it wraps `solve_whatif`, importing from a protected module without editing it. `mcp==2.1.1`, fifteen new transitive deps, pydantic 2.13.4 → 2.13.5
- [ ] Config-pin restructure: eight files pinned `len(fields(Config)) == 48`, seven protected — the same shape v10b hit with routes and v11 retired, and it had already cost v10 a designed config field. Each becomes the by-name claim its cycle is entitled to make; the total lives in `test_v12_w1_degradation.py` alone
- [ ] No replay — nothing on the training path moves, and the two decision-path edits are a config-backed default that falls back to the shipped value and a constant merge in a module whose own docstring says it annotates and never decides
- Pins: job kinds 12, config fields 48 → **53**, routes 45 → **46**
- Residuals: `journal.py` keeps its own `os.replace` (import-only this cycle, named in the census rail); the spec's `[solver]` section does not exist — `top_n` went in `[optimizer]` by ruling, and W2/W5 must read it there; ~34 MB of timestamped API snapshots under `data/raw/` accumulate unswept and are outside §2.7; the served rollover check reads disk rather than the API, so it cannot see a season FPL has published and this machine has not fetched
```

- [ ] **Commit** (`docs: open v12 W1 on the roadmap`, staging only
`docs/superpowers/ROADMAP.md`, with the standing trailers).

---

## Notes for the implementer

- **Task order has six constraints and is otherwise free.** T1 → T2 → T3 → T4 (each
  migrates onto the helper T1 creates, and T4's rail depends on T2 and T3 having
  landed). T9, T10, T12 → T15 (T15 writes the *measured* config-field count, so every
  field must exist first). T13 → T15 (same, for the route). T10 → T13 (the freshness
  strip's backup row reads `gaffer.backup`). T15 → T16 (the rails assert what T15
  pinned). Everything else — T5, T6, T7, T8, T11, T14 — is independent and can run in
  any order.
- **Five STOPs, and every one is real.** v11 had one and dissolved three candidates.
  W1 has five because §2.11 and §2.3 are *specified* to move things that protected files
  assert about, and because the config pin sits in seven protected files. No candidate
  dissolved. If a sixth appears, it STOPs — do not widen the diff and explain afterwards.
- **`npx vitest run`, never `npm test`.** `package.json` maps `test` to bare `vitest`,
  which is watch mode. An agent that runs it waits forever.
- **`.venv/bin/pytest`, and there is no bare `python`.** Use `.venv/bin/python` or
  `uv run`.
- **The most valuable thing in this cycle is a refusal.** Three of the eleven items are
  a program declining to do something: `refresh` declining to ingest, `track_pens`
  declining to overwrite, the LAN middleware declining to write. Every review instinct
  will be to soften one of them into a warning. Refuse: a warning printed into
  `logs/prices.log` at 23:45 is a warning nobody reads, and all three of these failures
  are silent by nature — that is why they need a stop rather than a note.
- **Three null conventions are in play and they are not interchangeable.**
  `field_eo`'s "never 0.0 for unknown" (`schemas.py:406-412`) now covers `age_hours`
  too; `season_ok`'s three states, where `None` is "cannot tell" and only `False` draws
  the banner; and the graded counter's "never measured is not never wrong"
  (`review.py:1109-1115`), untouched here but neighbouring the review ledger this cycle
  migrates. A review comment proposing any of them default to zero "for the type's sake"
  is proposing the bug the convention exists to prevent.
- **Do not run `gaffer tidy --apply` on the real tree.** The plan measured which five
  files it names. Deleting them is the user's call and is not part of shipping the
  command.
- **The spec is wrong in five places and the plan says which.** §2.11's count (six →
  twenty), §2.2's canonical exports (`TEMPLATE_EO` is not there), §2.1's archive set
  (`data/raw/field/` is not covered by the field EO log), §2.10's "thin wrapper over the
  router function" (`whatif` cannot be), and §2.4's served half (cannot call the API).
  Each is planned in its honest version with the deviation stated. If the orchestrator
  disagrees with any of them, that is a decision to take **before** the task runs, not
  a review comment afterwards.
