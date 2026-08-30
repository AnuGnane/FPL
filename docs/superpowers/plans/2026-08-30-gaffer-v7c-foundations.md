# Gaffer v7c Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three v7c foundation pieces — a daily availability snapshot that banks corrector training data, multi-seed replay gates as the house standard, and a read-only season tracker for the v6 penalty term — without touching a single line of model behaviour.

**Architecture:** Three independent additions bolted onto existing seams: `src/gaffer/snapshot.py` mirrors `news_shadow.py`'s never-raises append-by-rewrite log and is driven by a new CLI subcommand, a launchd plist and a web job kind; `scripts/v7b_replay.py` grows a `--seed-bases` loop around its existing single-arm body, with `scripts/seed_stats.py` reproducing the same aggregate from banked reports; `src/gaffer/pen_tracker.py` reads `reports/components_gw{N}.parquet` and `data/live/player_gw.parquet` and writes one atomic JSON. Every protected module is imported from and never modified.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, typer, FastAPI, pytest.

**Prerequisite:** work on branch `feat/gaffer-v7c` cut from `main`. Authoritative spec: `docs/superpowers/specs/2026-08-30-gaffer-v7c-foundations-design.md`.

**Protected — must show zero diffs at the end (Task 14 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every `tests/test_*_degradation.py`, `scripts/s2_replay.py`.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml` (all are gitignored, and `reports/` doubly so).

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/snapshot.py` | Create | F1: the daily availability log — column contract, day stamp, next-unfinished-GW, idempotent append-by-rewrite, never-raising `run_snapshot`, loader. |
| `tests/test_snapshot.py` | Create | F1 unit suite: row shape, flags-only degradation, same-day idempotency, never-raises, plist + installer wiring. |
| `src/gaffer/cli.py` | Modify (after `prices`, ~line 204; after `evaluate`, ~line 415) | Two new lazy-import subcommands: `snapshot` and `track-pens`. |
| `tests/test_cli.py` | Modify (append) | Registration tests for both new subcommands. |
| `src/gaffer/web/job_kinds.py` | Modify (docstring line 1; new wrapper; `JOB_KINDS` ~line 47) | Adds the `snapshot` job kind so the command centre can trigger it. |
| `tests/test_web_job_kinds.py` | Modify (lines 24-26 only) | The allow-list assertion grows from four kinds to five. |
| `tests/test_web_job_kinds_v7c.py` | Create | The new kind's own tests (kept out of the protected `tests/test_web_jobs.py`). |
| `scripts/com.gaffer.snapshot.plist` | Create | launchd job: daily 17:00, `uv run gaffer snapshot >> logs/snapshot.log 2>&1`. |
| `scripts/install_automation.sh` | Modify (lines 5, 12) | Installs the third plist and says so. |
| `README.md` | Modify (Automation section, ~line 254) | One line naming the third job. |
| `scripts/v7b_replay.py` | Modify (docstring, `_parser`, `arm_config`, `main`) | F2: `--seed-bases` loop, per-base arms, `MULTISEED_DONE` aggregate line. |
| `tests/test_v7b_driver.py` | Modify (append) | `--seed-bases` parsing, the loop, the aggregate math, the conventions doc guard. |
| `scripts/seed_stats.py` | Create | Standalone aggregator over banked report JSONs; same payload keys as `MULTISEED_DONE`. |
| `tests/test_seed_stats.py` | Create | Aggregator suite, including parity with the driver's own arithmetic. |
| `docs/superpowers/CONVENTIONS.md` | Create | The eight measurement conventions from spec §2. |
| `docs/superpowers/ROADMAP.md` | Modify (header area, after line 5) | One line linking the conventions doc. |
| `src/gaffer/pen_tracker.py` | Create | F3: read-only pen-term tracker — Understat join, realized-pen instrument with degradation, per-GW blocks, season totals, atomic JSON, printed table. |
| `tests/test_pen_tracker.py` | Create | F3 unit suite, including the degraded-instrument path. |

---

## Task 1 — F1: the snapshot log's column contract and row builder

**Files:**
- Create `src/gaffer/snapshot.py`
- Create `tests/test_snapshot.py`

- [ ] **Write the failing test.** Create `tests/test_snapshot.py`:

```python
"""The daily availability log: what the news said, stamped with the day."""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.errors import GafferError
from gaffer.snapshot import (SNAPSHOT_COLS, load_snapshot_log,
                             next_unfinished_gw, snap_date, snapshot_rows)


def _avail() -> pd.DataFrame:
    """A news-sharpened availability frame, in availability_frame's shape."""
    return pd.DataFrame({
        "code": [1, 2],
        "status": ["d", "a"],
        "chance_of_playing": [50.0, None],
        "injury_type": ["hamstring", None],
        "expected_return_gw": [4.0, None],
        "p_start_hint": [0.4, None],
        "source": ["ffs", None],
        "fetched_at": ["2026-08-30T09:00:00+00:00", None]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def test_the_log_columns_are_the_availability_columns_stamped():
    """The log reuses artifacts' column contract rather than restating it, so
    a column added to the availability frame lands here for free."""
    assert SNAPSHOT_COLS == ["season", "gw", "snap_date"] + AVAILABILITY_COLS


def test_the_snapshot_gameweek_is_the_first_unfinished_one():
    """``is_next`` goes false in the hours a gameweek is being played, and a
    snapshot taken then still belongs to that week's news cycle."""
    assert next_unfinished_gw(_events()) == 2


def test_a_finished_season_has_no_gameweek_to_snapshot():
    with pytest.raises(GafferError):
        next_unfinished_gw(pd.DataFrame({"gw": [1], "finished": [True]}))


def test_the_rows_carry_the_season_the_gameweek_and_the_day():
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert set(rows["season"]) == {"2026-27"}
    assert set(rows["gw"]) == {2}
    assert set(rows["snap_date"]) == {"2026-08-30"}
    assert sorted(rows["code"]) == [1, 2]
    assert rows.set_index("code").loc[1, "injury_type"] == "hamstring"


def test_a_flags_only_frame_still_writes_the_full_schema():
    """News off, or every source down: the log keeps one shape all season, so
    the corrector reads one table rather than a union of weekly shapes."""
    flags = pd.DataFrame({"code": [1], "status": ["a"],
                          "chance_of_playing": [None]})
    rows = snapshot_rows(flags, gw=2, season="2026-27", day="2026-08-30")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert rows["source"].isna().all()
    assert rows["p_start_hint"].isna().all()


def test_the_day_is_utc_and_dashed():
    day = snap_date()
    assert len(day) == 10 and day[4] == "-" and day[7] == "-"


def test_an_absent_log_reads_as_an_empty_frame(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    out = load_snapshot_log()
    assert out.empty
    assert list(out.columns) == SNAPSHOT_COLS
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_snapshot.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.snapshot'`.

- [ ] **Write the minimal implementation.** Create `src/gaffer/snapshot.py`:

```python
"""The daily availability snapshot: what the news said, stamped with the day.

``reports/availability_gw{N}.parquet`` is one file per gameweek, overwritten by
every advise run (``artifacts.py:390``), and the raw news cache is bucketed by
fetch time only. So the shape of a week's injury news is visible only at the
moment a run happened, and every day nobody runs one is corrector training data
lost for ever. This log is the fix: one row per player per day, kept.

Nothing here may raise. The caller is a launchd job at 17:00 with nowhere to
report a traceback, and a missed day is a far cheaper failure than a job that
dies loudly every afternoon.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from gaffer.artifacts import AVAILABILITY_COLS
from gaffer.data import store
from gaffer.errors import GafferError

SNAPSHOT_PATH = "live/availability_log.parquet"

SNAPSHOT_COLS = ["season", "gw", "snap_date"] + AVAILABILITY_COLS
"""The availability contract, prefixed with the three keys that date it.

Reused from :mod:`gaffer.artifacts` rather than restated: the news endpoint,
the per-gameweek snapshot and this log all read one column list, so a source
that starts carrying a new field lands in all three at once.
"""


def snap_date(now: datetime | None = None) -> str:
    """Today in UTC, ``YYYY-MM-DD``. The log's idempotency key.

    UTC rather than local time so a machine that travels, or one running the
    job either side of a clock change, cannot bank two "days" for one.
    """
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def next_unfinished_gw(events: pd.DataFrame) -> int:
    """The gameweek this snapshot is about: the first one not yet finished.

    Not ``is_next``, which goes false for the hours a gameweek is actually
    being played — a snapshot taken on a Saturday evening still belongs to
    that gameweek's news cycle, and stamping it with the following one would
    file Saturday's team news against next week's deadline.
    """
    pending = events[~events["finished"].astype(bool)]
    if pending.empty:
        raise GafferError(
            "no unfinished gameweek in the bootstrap — the season is over")
    return int(pending["gw"].min())


def snapshot_rows(avail: pd.DataFrame, gw: int, season: str = "",
                  day: str | None = None) -> pd.DataFrame:
    """The availability frame -> dated log rows, one per player.

    Columns a flags-only week never produced are filled with nulls and settled
    dtypes, the same trade :func:`gaffer.artifacts.save_availability` makes:
    parquet wants one dtype per column, and an all-``None`` object column has
    none, so a quiet week and a news-heavy one would otherwise write two
    incompatible schemas into one growing file.
    """
    out = avail.copy()
    for col in AVAILABILITY_COLS:
        if col not in out.columns:
            out[col] = None
    out = out[AVAILABILITY_COLS].copy()
    for col in ("status", "injury_type", "source", "fetched_at"):
        out[col] = out[col].astype("object").where(
            out[col].notna(), None).astype("string")
    for col in ("chance_of_playing", "expected_return_gw", "p_start_hint"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["code"] = pd.to_numeric(out["code"], errors="coerce").astype("int64")
    out.insert(0, "snap_date", str(day or snap_date()))
    out.insert(0, "gw", int(gw))
    out.insert(0, "season", str(season or ""))
    return out[SNAPSHOT_COLS]


def load_snapshot_log() -> pd.DataFrame:
    """Every banked day, or an empty frame with the right columns."""
    if not store.exists(SNAPSHOT_PATH):
        return pd.DataFrame(columns=SNAPSHOT_COLS)
    return store.load(SNAPSHOT_PATH)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_snapshot.py`

- [ ] **Commit.**

```bash
git add src/gaffer/snapshot.py tests/test_snapshot.py && git commit -m "$(cat <<'EOF'
feat: the daily availability log's column contract and row builder

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — F1: idempotent append-by-rewrite

**Files:**
- Modify `src/gaffer/snapshot.py` (append `append_snapshot` after `snapshot_rows`, before `load_snapshot_log`)
- Modify `tests/test_snapshot.py` (import line 9-11; append tests)

- [ ] **Write the failing test.** In `tests/test_snapshot.py`, replace the import:

```python
from gaffer.snapshot import (SNAPSHOT_COLS, load_snapshot_log,
                             next_unfinished_gw, snap_date, snapshot_rows)
```

with:

```python
from gaffer.snapshot import (SNAPSHOT_COLS, SNAPSHOT_PATH, append_snapshot,
                             load_snapshot_log, next_unfinished_gw, snap_date,
                             snapshot_rows)
```

and append:

```python
def test_the_first_write_creates_the_log(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    rows = snapshot_rows(_avail(), gw=2, season="2026-27", day="2026-08-30")
    assert append_snapshot(rows) == 2
    assert (tmp_path / SNAPSHOT_PATH).exists()
    assert len(load_snapshot_log()) == 2


def test_a_second_run_the_same_day_replaces_that_days_rows(tmp_path,
                                                           monkeypatch):
    """The job can be re-run by hand, and a duplicated afternoon would weight
    that day twice in whatever trains on this log. The later run wins: it is
    the news that stood at the end of the day."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    later = _avail()
    later.loc[0, "status"] = "i"
    append_snapshot(snapshot_rows(later, gw=2, season="2026-27",
                                  day="2026-08-30"))
    out = load_snapshot_log()
    assert len(out) == 2
    assert set(out["snap_date"]) == {"2026-08-30"}
    assert out.set_index("code").loc[1, "status"] == "i"


def test_a_later_day_appends_rather_than_replaces(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-30"))
    append_snapshot(snapshot_rows(_avail(), gw=2, season="2026-27",
                                  day="2026-08-31"))
    out = load_snapshot_log()
    assert len(out) == 4
    assert sorted(set(out["snap_date"])) == ["2026-08-30", "2026-08-31"]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_snapshot.py`
  Expected: collection error — `ImportError: cannot import name 'append_snapshot' from 'gaffer.snapshot'`.

- [ ] **Write the minimal implementation.** In `src/gaffer/snapshot.py`, insert between `snapshot_rows` and `load_snapshot_log`:

```python
def append_snapshot(rows: pd.DataFrame) -> int:
    """Rewrite the log with ``rows`` replacing anything from the same day.

    Append-by-rewrite, like :func:`gaffer.news_shadow.write_shadow`: parquet
    has no append, and at a few hundred rows a day the whole file is cheap to
    re-emit. Replacement rather than accumulation, keyed on ``snap_date``, is
    what makes a hand re-run free.

    Returns the number of rows banked for the day.
    """
    existing = (store.load(SNAPSHOT_PATH) if store.exists(SNAPSHOT_PATH)
                else pd.DataFrame(columns=SNAPSHOT_COLS))
    for col in SNAPSHOT_COLS:
        if col not in existing.columns:
            existing[col] = None
    days = set(rows["snap_date"].astype(str))
    kept = existing[~existing["snap_date"].astype(str).isin(days)]
    frames = [f[SNAPSHOT_COLS] for f in (kept, rows) if not f.empty]
    merged = (pd.concat(frames, ignore_index=True) if frames
              else rows[SNAPSHOT_COLS])
    store.save(merged, SNAPSHOT_PATH)
    return int(len(rows))
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_snapshot.py`

- [ ] **Commit.**

```bash
git add src/gaffer/snapshot.py tests/test_snapshot.py && git commit -m "$(cat <<'EOF'
feat: same-day-idempotent append for the availability log

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F1: `run_snapshot`, which never raises

**Files:**
- Modify `src/gaffer/snapshot.py` (append `run_snapshot` at end of file)
- Modify `tests/test_snapshot.py` (import line; append tests)

- [ ] **Write the failing test.** In `tests/test_snapshot.py`, extend the `gaffer.snapshot` import to add `run_snapshot`:

```python
from gaffer.snapshot import (SNAPSHOT_COLS, SNAPSHOT_PATH, append_snapshot,
                             load_snapshot_log, next_unfinished_gw,
                             run_snapshot, snap_date, snapshot_rows)
```

and append:

```python
def _cfg():
    from gaffer.config import Config

    return Config(entry_id=1, league_id=2, current_season="2026-27")


def _wire(monkeypatch, tmp_path, avail=None, boom=False):
    """Point the run at fakes: no network, no bootstrap, no news fetchers."""
    from gaffer.data import store as store_mod

    class _Client:
        def get_bootstrap(self):
            if boom:
                raise RuntimeError("the FPL API is down")
            return {"events": []}

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr("gaffer.api.client.FPLClient", lambda *a, **k: _Client())
    monkeypatch.setattr("gaffer.data.bootstrap.build_players",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_teams",
                        lambda raw: pd.DataFrame())
    monkeypatch.setattr("gaffer.data.bootstrap.build_events",
                        lambda raw: _events())
    monkeypatch.setattr("gaffer.advise.news_availability",
                        lambda *a, **kw: _avail() if avail is None else avail)
    monkeypatch.setattr("gaffer.snapshot.snap_date", lambda *a: "2026-08-30")


def test_a_run_banks_todays_rows_and_says_so(tmp_path, monkeypatch, capsys):
    _wire(monkeypatch, tmp_path)
    assert run_snapshot(cfg=_cfg()) == 2
    assert "Snapshot: 2 availability rows for gw2 at 2026-08-30." \
        in capsys.readouterr().out
    out = load_snapshot_log()
    assert list(out.columns) == SNAPSHOT_COLS
    assert set(out["season"]) == {"2026-27"}


def test_two_runs_in_one_day_leave_one_days_rows(tmp_path, monkeypatch):
    """Gate G1(b): the daily job is safe to trigger by hand."""
    _wire(monkeypatch, tmp_path)
    run_snapshot(cfg=_cfg())
    run_snapshot(cfg=_cfg())
    assert len(load_snapshot_log()) == 2


def test_a_dead_fetch_prints_one_line_and_banks_nothing(tmp_path, monkeypatch,
                                                        capsys):
    """Gate G1(c). A launchd job has nowhere to report a traceback, and a
    scheduled job that dies loudly every afternoon gets uninstalled."""
    _wire(monkeypatch, tmp_path, boom=True)
    assert run_snapshot(cfg=_cfg()) is None
    printed = capsys.readouterr().out.strip().splitlines()
    assert len(printed) == 1
    assert printed[0].startswith("availability snapshot not written:")
    assert not (tmp_path / SNAPSHOT_PATH).exists()


def test_an_empty_availability_frame_banks_nothing(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, avail=pd.DataFrame())
    assert run_snapshot(cfg=_cfg()) is None
    assert not (tmp_path / SNAPSHOT_PATH).exists()
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_snapshot.py`
  Expected: collection error — `ImportError: cannot import name 'run_snapshot' from 'gaffer.snapshot'`.

- [ ] **Write the minimal implementation.** Append to `src/gaffer/snapshot.py`:

```python
def run_snapshot(cfg=None) -> int | None:
    """Bank today's availability state. Rows written, or ``None``.

    Imports are local: the news layer pulls in half the advise pipeline, and a
    module the CLI touches to print ``--help`` must not pay for that. The
    config is an argument so a caller that already has one does not read
    ``config.toml`` twice.

    Prints its own one-line result, success or degradation, so the launchd
    log, the CLI and the web job all say the same sentence without three
    copies of it. Every failure lands in the one ``except``: this is
    instrumentation, and instrumentation never blocks.
    """
    try:
        from gaffer.advise import news_availability
        from gaffer.api.client import FPLClient
        from gaffer.config import load_config
        from gaffer.data.bootstrap import (build_events, build_players,
                                           build_teams)

        cfg = cfg or load_config()
        raw = FPLClient().get_bootstrap()
        events = build_events(raw)
        gw = next_unfinished_gw(events)
        avail = news_availability(cfg, build_players(raw), build_teams(raw),
                                  events, gw)
        if avail is None or len(avail) == 0:
            print("availability snapshot not written: the news layer returned "
                  "no rows")
            return None
        day = snap_date()
        rows = snapshot_rows(avail, gw, season=str(cfg.current_season or ""),
                             day=day)
        n = append_snapshot(rows)
        print(f"Snapshot: {n} availability rows for gw{gw} at {day}.")
        return n
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"availability snapshot not written: {exc}")
        return None
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_snapshot.py`

- [ ] **Commit.**

```bash
git add src/gaffer/snapshot.py tests/test_snapshot.py && git commit -m "$(cat <<'EOF'
feat: run_snapshot banks the day's availability and never raises

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — F1: the `gaffer snapshot` subcommand

**Files:**
- Modify `src/gaffer/cli.py` (insert after the `prices` command body, which ends at line 204, before `@app.command()` / `def league()` at line 206)
- Modify `tests/test_cli.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_cli.py`:

```python
def test_snapshot_is_registered_and_reports_what_it_banked(monkeypatch):
    """The daily job's front door: it must exist, and it must be quiet about
    its own failures the way the scheduled run needs it to be."""
    from typer.testing import CliRunner

    from gaffer import snapshot as snapshot_mod
    from gaffer.cli import app

    def fake_run(cfg=None):
        print("Snapshot: 3 availability rows for gw2 at 2026-08-30.")
        return 3

    monkeypatch.setattr(snapshot_mod, "run_snapshot", fake_run)
    result = CliRunner().invoke(app, ["snapshot"])
    assert result.exit_code == 0
    assert "3 availability rows" in result.output
    assert "snapshot" in CliRunner().invoke(app, ["--help"]).output


def test_snapshot_exits_zero_when_the_day_could_not_be_banked(monkeypatch):
    from typer.testing import CliRunner

    from gaffer import snapshot as snapshot_mod
    from gaffer.cli import app

    monkeypatch.setattr(snapshot_mod, "run_snapshot", lambda cfg=None: None)
    result = CliRunner().invoke(app, ["snapshot"])
    assert result.exit_code == 0
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_cli.py -k snapshot`
  Expected: both tests fail — `assert result.exit_code == 0` fails with exit code 2, because typer reports `No such command 'snapshot'`.

- [ ] **Write the minimal implementation.** In `src/gaffer/cli.py`, insert between the end of `prices` (line 204) and the `@app.command()` above `def league()` (line 206):

```python
@app.command()
def snapshot():
    """Bank today's availability state into the daily log (v7c F1).

    The launchd job's body. It prints its own line and never fails: a
    scheduled command that exits non-zero on a bad afternoon is a command
    that gets uninstalled.
    """
    from gaffer.snapshot import run_snapshot

    run_snapshot()
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_cli.py`

- [ ] **Commit.**

```bash
git add src/gaffer/cli.py tests/test_cli.py && git commit -m "$(cat <<'EOF'
feat: gaffer snapshot subcommand

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — F1: the `snapshot` web job kind

**Files:**
- Modify `src/gaffer/web/job_kinds.py` (docstring line 1; new wrapper after `run_news_shadow`, ~line 45; `JOB_KINDS` dict ~line 47)
- Modify `tests/test_web_job_kinds.py` (lines 24-26 only)
- Create `tests/test_web_job_kinds_v7c.py`

`tests/test_web_jobs.py` is protected and is not touched. `frontend/` is unchanged: the UI button is deferred (spec §1, §7), so `frontend/src/types.ts`'s `JOB_KINDS` stays at four and its vitest assertion still holds.

- [ ] **Write the failing test.** Create `tests/test_web_job_kinds_v7c.py`:

```python
"""The v7c job kind: the browser may trigger the daily availability snapshot."""

from gaffer.web import job_kinds


def test_the_snapshot_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["snapshot"] is job_kinds.run_snapshot_job


def test_the_snapshot_job_reports_the_rows_it_banked(monkeypatch, capsys):
    """The runner captures this thread's stdout, so the wrapper's print is
    what the browser shows as the job's progress line."""
    monkeypatch.setattr("gaffer.snapshot.run_snapshot", lambda: 42)
    assert job_kinds.run_snapshot_job() == {"rows": 42}
    assert "42 availability rows" in capsys.readouterr().out


def test_a_degraded_snapshot_is_still_a_finished_job(monkeypatch):
    """``run_snapshot`` answers ``None`` on any bad afternoon; the job must
    report zero rows rather than fail the run."""
    monkeypatch.setattr("gaffer.snapshot.run_snapshot", lambda: None)
    assert job_kinds.run_snapshot_job() == {"rows": 0}


def test_the_snapshot_wrapper_imports_lazily():
    import inspect

    source = inspect.getsource(job_kinds)
    assert "from gaffer.snapshot import" not in source.split("def ")[0]
```

Then, in `tests/test_web_job_kinds.py`, replace lines 24-26:

```python
def test_exactly_the_four_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "evaluate", "news-shadow",
                                 "refresh-data"]
```

with:

```python
def test_exactly_the_five_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "evaluate", "news-shadow",
                                 "refresh-data", "snapshot"]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_job_kinds_v7c.py tests/test_web_job_kinds.py`
  Expected: the new file's first three tests fail with `AttributeError: module 'gaffer.web.job_kinds' has no attribute 'run_snapshot_job'` / `KeyError: 'snapshot'`, and `test_exactly_the_five_kinds_the_spec_allows` fails on the missing `"snapshot"` entry.

- [ ] **Write the minimal implementation.** In `src/gaffer/web/job_kinds.py`:

Replace the docstring's first line:

```python
"""The four job kinds the browser may start (spec §5).
```

with:

```python
"""The five job kinds the browser may start (spec §5, v7c F1).
```

Insert after `run_news_shadow` (before the `JOB_KINDS` assignment):

```python
def run_snapshot_job() -> dict:
    """``gaffer snapshot`` — the daily availability log (v7c F1).

    ``run_snapshot`` prints its own result line and answers ``None`` on any
    failure, so the only work here is turning that into the row count the
    job record carries.
    """
    from gaffer.snapshot import SNAPSHOT_PATH, run_snapshot

    rows = int(run_snapshot() or 0)
    print(f"Wrote {rows} availability rows to {SNAPSHOT_PATH}.")
    return {"rows": rows}
```

Replace the `JOB_KINDS` mapping:

```python
JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
}
```

with:

```python
JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
    "snapshot": run_snapshot_job,
}
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_job_kinds_v7c.py tests/test_web_job_kinds.py tests/test_web_jobs_api.py tests/test_web_app.py`

- [ ] **Commit.**

```bash
git add src/gaffer/web/job_kinds.py tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py && git commit -m "$(cat <<'EOF'
feat: snapshot job kind so the command centre can bank a day

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — F1: the launchd job

**Files:**
- Create `scripts/com.gaffer.snapshot.plist`
- Modify `scripts/install_automation.sh` (lines 5 and 12)
- Modify `README.md` (Automation section, the paragraph beginning "Substitutes the project path", ~line 254)
- Modify `tests/test_snapshot.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_snapshot.py`:

```python
def test_the_snapshot_plist_runs_the_command_daily_at_five(tmp_path):
    """F1 is a scheduling change as much as a code one: a log nobody writes
    to banks nothing, and the whole value is one row per day."""
    import plistlib
    from pathlib import Path

    raw = Path("scripts/com.gaffer.snapshot.plist").read_text(encoding="utf-8")
    assert "__PROJECT_DIR__" in raw
    plist = plistlib.loads(
        raw.replace("__PROJECT_DIR__", str(tmp_path)).encode("utf-8"))
    assert plist["Label"] == "com.gaffer.snapshot"
    assert plist["StartCalendarInterval"] == {"Hour": 17, "Minute": 0}
    command = plist["ProgramArguments"][-1]
    assert "uv run gaffer snapshot" in command
    assert "logs/snapshot.log" in command
    assert str(tmp_path) in command


def test_the_installer_installs_the_snapshot_job():
    from pathlib import Path

    body = Path("scripts/install_automation.sh").read_text(encoding="utf-8")
    names = body.split("for name in")[1].split(";")[0]
    assert "snapshot" in names
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_snapshot.py -k "plist or installer"`
  Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'scripts/com.gaffer.snapshot.plist'` for the first, and `AssertionError` on the installer's `for name in advise prices` list for the second.

- [ ] **Write the minimal implementation.** Create `scripts/com.gaffer.snapshot.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.snapshot</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer snapshot &gt;&gt; logs/snapshot.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
</dict></plist>
```

In `scripts/install_automation.sh`, replace line 5:

```sh
for name in advise prices; do
```

with:

```sh
for name in advise prices snapshot; do
```

and replace line 12:

```sh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check."
```

with:

```sh
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot."
```

In `README.md`, replace the Automation paragraph:

```
Substitutes the project path into the two plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00)
and `com.gaffer.prices` (nightly 23:15). Re-run it after moving the project.
```

with:

```
Substitutes the project path into the three plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00),
`com.gaffer.prices` (nightly 23:15) and `com.gaffer.snapshot` (daily 17:00, banks
the availability log the news corrector will train on). Re-run it after moving
the project.
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_snapshot.py`

- [ ] **Commit.**

```bash
git add scripts/com.gaffer.snapshot.plist scripts/install_automation.sh README.md tests/test_snapshot.py && git commit -m "$(cat <<'EOF'
feat: daily 17:00 launchd job for the availability snapshot

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — F2: `--seed-bases` parsing

**Files:**
- Modify `scripts/v7b_replay.py` (`_parser` lines 119-136; `arm_config` lines 139-148)
- Modify `tests/test_v7b_driver.py` (append)

`arm_config` keeps its exact current contract — the existing rail tests at lines 57-67 and 144-156 must keep passing untouched.

- [ ] **Write the failing test.** Append to `tests/test_v7b_driver.py`:

```python
def test_seed_bases_derive_one_arm_per_base():
    """Each base owns its log and its report: two bases sharing either would
    read each other's hits and transfers and the trio would be one draw."""
    configs, bases, tag = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-bases", "1,2,3"])
    assert bases == [1, 2, 3]
    assert tag == "q"
    assert [c.tag for c in configs] == ["q-s1", "q-s2", "q-s3"]
    assert [c.seed_base for c in configs] == [1, 2, 3]
    assert [c.log_path for c in configs] == [
        "live/backtest_log_v7b_q-s1.parquet",
        "live/backtest_log_v7b_q-s2.parquet",
        "live/backtest_log_v7b_q-s3.parquet"]
    assert [c.report_path for c in configs] == [
        "reports/v7b_q-s1.json", "reports/v7b_q-s2.json",
        "reports/v7b_q-s3.json"]


def test_seed_bases_tolerate_spaces_in_the_list():
    configs, bases, _ = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-bases", "1, 2 ,3"])
    assert bases == [1, 2, 3]
    assert [c.tag for c in configs] == ["q-s1", "q-s2", "q-s3"]


def test_a_single_seed_base_still_derives_one_unsuffixed_arm():
    """The single-seed path must be byte-identical to today's: same tag, same
    log, same report, no aggregate."""
    configs, bases, tag = v7b_replay.arm_configs(
        ["--arm", "raw", "--tag", "q", "--seed-base", "20260825"])
    assert bases is None
    assert tag == "q"
    assert [c.tag for c in configs] == ["q"]
    assert configs[0].seed_base == 20260825
    assert configs[0].log_path == "live/backtest_log_v7b_q.parquet"
    assert configs[0].report_path == "reports/v7b_q.json"


def test_the_two_seed_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-base", "1", "--seed-bases", "1,2"])


def test_a_one_element_seed_bases_list_is_refused():
    """K >= 2 or use --seed-base: a "multi-seed" run of one is the single-draw
    verdict convention 1 exists to stop."""
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-bases", "20260825"])


def test_a_non_numeric_seed_base_is_refused():
    with pytest.raises(SystemExit):
        v7b_replay.arm_configs(["--arm", "raw", "--tag", "q",
                                "--seed-bases", "20260825,tuesday"])
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_v7b_driver.py -k seed`
  Expected: the new tests fail with `AttributeError: module 'v7b_replay' has no attribute 'arm_configs'` (the pre-existing `test_the_seed_is_the_base_plus_the_gameweek` still passes).

- [ ] **Write the minimal implementation.** In `scripts/v7b_replay.py`, replace `_parser` and `arm_config` (lines 119-148) with:

```python
def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--arm", required=True,
                   choices=["raw", "heur", "estimation", "composite"])
    p.add_argument("--tag", required=True,
                   help="per-arm output suffix; two arms may not share one")
    seeds = p.add_mutually_exclusive_group()
    seeds.add_argument("--seed-base", type=int, default=20260827)
    seeds.add_argument("--seed-bases", default=None,
                       help="comma-separated bases, e.g. 20260825,20260826,"
                            "20260827; runs one arm per base and prints the "
                            "aggregate MULTISEED_DONE line")
    p.add_argument("--n", type=int, default=40)
    p.add_argument("--chips", action=argparse.BooleanOptionalAction,
                   default=True)
    p.add_argument("--priors", choices=["current", "off"], default="current")
    p.add_argument("--minutes", choices=["current", "legacy"],
                   default="current")
    p.add_argument("--frame", choices=["current", "v4c"], default="current")
    p.add_argument("--noise-asset", default=None,
                   help="required for --arm estimation/composite, refused "
                        "otherwise")
    return p


def _parsed(argv: list[str]) -> argparse.Namespace:
    """Parse and validate, leaving the bases on ``.bases`` (``None`` if one).

    Split out of :func:`arm_config` so the single-arm and multi-seed entry
    points share one parser and one set of refusals.
    """
    p = _parser()
    a = p.parse_args(argv)
    if a.arm in TABLE_ARMS and not a.noise_asset:
        p.error(f"--arm {a.arm} needs a --noise-asset")
    if a.arm not in TABLE_ARMS and a.noise_asset:
        p.error(f"--arm {a.arm} serves no table; --noise-asset is refused")
    if a.seed_bases is None:
        a.bases = None
        return a
    a.bases = []
    try:
        a.bases = [int(b.strip()) for b in a.seed_bases.split(",") if b.strip()]
    except ValueError:
        p.error("--seed-bases takes a comma-separated list of integers")
    if len(a.bases) < 2:
        p.error("--seed-bases takes two or more bases; a single draw is what "
                "--seed-base is for")
    return a


def _configs(a: argparse.Namespace) -> list[ArmConfig]:
    def one(tag: str, base: int) -> ArmConfig:
        return ArmConfig(arm=a.arm, tag=tag, seed_base=base, n=a.n,
                         chips=a.chips, priors=a.priors, minutes=a.minutes,
                         frame=a.frame, noise_asset=a.noise_asset)

    if a.bases is None:
        return [one(a.tag, a.seed_base)]
    return [one(f"{a.tag}-s{b}", b) for b in a.bases]


def arm_config(argv: list[str]) -> ArmConfig:
    """The single arm ``argv`` asks for — the first, under ``--seed-bases``."""
    return _configs(_parsed(argv))[0]


def arm_configs(argv: list[str]) -> tuple[list[ArmConfig], list[int] | None,
                                          str]:
    """Every arm ``argv`` asks for, its bases, and the undecorated tag.

    ``bases`` is ``None`` for a single-seed run, which is what tells
    :func:`main` not to print an aggregate line: one draw has no spread, and a
    ``MULTISEED_DONE`` over one number would read as a measurement.
    """
    a = _parsed(argv)
    return _configs(a), a.bases, a.tag
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v7b_driver.py`

- [ ] **Commit.**

```bash
git add scripts/v7b_replay.py tests/test_v7b_driver.py && git commit -m "$(cat <<'EOF'
feat: v7b replay accepts --seed-bases and derives one arm per base

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — F2: the multi-seed loop and the `MULTISEED_DONE` line

**Files:**
- Modify `scripts/v7b_replay.py` (module docstring usage block lines 40-45; replace `main` at lines 249-287 with `run_one`, `multiseed_summary` and a new `main`)
- Modify `tests/test_v7b_driver.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_v7b_driver.py`:

```python
import json  # noqa: E402
from pathlib import Path  # noqa: E402


def _fake_backtest(monkeypatch, totals):
    """Drive ``main`` over a stubbed replay: one canned total per call."""
    seen = []
    pending = list(totals)

    def run_backtest(season, start_gw, horizon, chips):
        seen.append((season, start_gw, horizon, chips))
        return {"total": pending.pop(0), "chips_played": {}}

    def load(rel):
        return pd.DataFrame({"chip": ["", "bboost"], "points": [40, 60],
                             "hits": [0, 4], "transfers": [1, 2]})

    monkeypatch.setattr(v7b_replay.bt, "run_backtest", run_backtest)
    monkeypatch.setattr(v7b_replay.bt_store, "load", load)
    return seen


def test_the_multi_seed_run_replays_every_base_and_reports_each(
        tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    seen = _fake_backtest(monkeypatch, [1800, 1900, 1850])
    out = v7b_replay.main(["--arm", "raw", "--tag", "t",
                           "--seed-bases", "1,2,3"])
    assert len(seen) == 3
    printed = capsys.readouterr().out.splitlines()
    arm_lines = [ln for ln in printed if ln.startswith("V7B_ARM_DONE")]
    assert [ln.split()[1] for ln in arm_lines] == ["t-s1", "t-s2", "t-s3"]
    assert [json.loads(ln.split(" ", 2)[2])["total"] for ln in arm_lines] == \
        [1800, 1900, 1850]
    for tag in ("t-s1", "t-s2", "t-s3"):
        banked = json.loads(Path(f"reports/v7b_{tag}.json").read_text())
        assert banked["hits"] == 4 and banked["transfers"] == 3
        assert banked["config"]["tag"] == tag
    done = [ln for ln in printed if ln.startswith("MULTISEED_DONE")]
    assert len(done) == 1
    assert done[0].split()[1] == "t"
    assert json.loads(done[0].split(" ", 2)[2]) == out
    assert out == {"totals": [1800, 1900, 1850], "mean": 1850.0,
                   "spread": 100, "range": [1800, 1900],
                   "seed_bases": [1, 2, 3]}


def test_a_single_seed_run_prints_one_line_and_no_aggregate(
        tmp_path, monkeypatch, capsys):
    """The pre-v7c behaviour, unchanged: one arm, one report, one line."""
    monkeypatch.chdir(tmp_path)
    _fake_backtest(monkeypatch, [1876])
    out = v7b_replay.main(["--arm", "raw", "--tag", "t",
                           "--seed-base", "20260901"])
    printed = capsys.readouterr().out.splitlines()
    assert [ln.split()[:2] for ln in printed if ln.startswith("V7B_")] == \
        [["V7B_ARM_DONE", "t"]]
    assert not [ln for ln in printed if ln.startswith("MULTISEED_DONE")]
    assert out["total"] == 1876
    assert out["config"]["seed_base"] == 20260901
    assert Path("reports/v7b_t.json").exists()


def test_the_multi_seed_loop_leaves_the_backtest_module_as_it_found_it(
        tmp_path, monkeypatch):
    """Three bases in one process: a gate stacked on a gate, or an arm store
    left pointing at the previous base's log, would corrupt every run after
    the first."""
    monkeypatch.chdir(tmp_path)
    _fake_backtest(monkeypatch, [1800, 1900, 1850])
    before = (v7b_replay.bt.store, v7b_replay.bt.solve_plan,
              v7b_replay.bt.predict_components_simple)
    v7b_replay.main(["--arm", "raw", "--tag", "t", "--seed-bases", "1,2,3"])
    assert (v7b_replay.bt.store, v7b_replay.bt.solve_plan,
            v7b_replay.bt.predict_components_simple) == before


def test_the_aggregate_is_the_mean_spread_and_range_of_the_totals():
    """Convention 1's arithmetic: verdicts read mean +/- spread, and the v7b
    trio's own spread (115 pts) dwarfs every arm gap ever gated on."""
    outs = [{"total": 1876}, {"total": 1901}, {"total": 1786}]
    assert v7b_replay.multiseed_summary(
        outs, [20260901, 20260915, 20260825]) == {
            "totals": [1876, 1901, 1786], "mean": 1854.3, "spread": 115,
            "range": [1786, 1901],
            "seed_bases": [20260901, 20260915, 20260825]}
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_v7b_driver.py -k "multi_seed or aggregate or single_seed_run"`
  Expected: `AttributeError: module 'v7b_replay' has no attribute 'multiseed_summary'`, and the loop tests fail because `main` runs a single arm with no `MULTISEED_DONE` line.

- [ ] **Write the minimal implementation.** In `scripts/v7b_replay.py`, first replace the usage block in the module docstring (lines 40-45):

```
Usage (orchestrator only — Group 1 builds this and does not run it)::

    caffeinate -i nohup .venv/bin/python scripts/v7b_replay.py \\
        --arm heur --tag q1b-heur --seed-base 20260901 \\
        > logs/v7b_q1b-heur.log 2>&1 &
    grep V7B_ARM_DONE logs/v7b_*.log
"""
```

with:

```
Usage (orchestrator only — Group 1 builds this and does not run it)::

    caffeinate -i nohup .venv/bin/python scripts/v7b_replay.py \\
        --arm heur --tag q1b-heur --seed-base 20260901 \\
        > logs/v7b_q1b-heur.log 2>&1 &
    grep V7B_ARM_DONE logs/v7b_*.log

``--seed-bases 20260825,20260826,20260827`` runs the same arm once per base —
tags ``<tag>-s<base>``, one log and one report each — and finishes with a single
``MULTISEED_DONE <tag> {...}`` line carrying the totals, their mean and their
spread. That is the house standard (``docs/superpowers/CONVENTIONS.md`` §1): the
seed spread on this harness is larger than every arm gap ever gated on, so a
one-draw verdict measures the seed. ``scripts/seed_stats.py`` computes the same
aggregate from reports already on disk.
"""
```

Then replace `main` (lines 249-287) with:

```python
def run_one(cfg: ArmConfig, payload: dict | None) -> dict:
    """One seed base end to end: replay, report file, ``V7B_ARM_DONE`` line.

    The arm store is re-pointed *here* rather than in :func:`apply_patches`
    because it is the one patch that is not seed-independent — each base owns
    its own backtest log, and two bases sharing one would read each other's
    hits and transfers. ``apply_patches`` recorded the real module before the
    loop, so its undo still restores it.

    The component and solve hooks are restored before returning for the same
    reason: a second base must not run with the first base's gate stacked on
    top of its own.
    """
    bt.store = _ArmStore(cfg.log_path)
    real_pcs = bt.predict_components_simple
    real_solve = bt.solve_plan
    stash: dict = {}
    gate = None
    if gate_wanted(cfg):

        def pcs(models, rows):
            comp = real_pcs(models, rows)
            stash["xmins"] = xmins_by_player_gw(comp)
            return comp

        bt.predict_components_simple = pcs
        gate = make_gate(cfg, stash, real_solve)
        bt.solve_plan = gate
    try:
        r = bt.run_backtest(season="2025-26", start_gw=5, horizon=3,
                            chips=cfg.chips)
        d = bt_store.load(cfg.log_path)
        chip_pts = d[d["chip"] != ""].groupby("chip")["points"].sum().to_dict()
        out = {
            "total": r["total"],
            "hits": int(d["hits"].sum()),
            "transfers": int(d["transfers"].sum()),
            "gated_weeks": gate.gated_weeks if gate else 0,
            "held_weeks": gate.held_weeks if gate else 0,
            "chips_played": r["chips_played"],
            "chip_points": {str(k): int(v) for k, v in chip_pts.items()},
            "composite_floor": (payload or {}).get("composite_floor"),
            "config": cfg.echo(),
        }
    finally:
        bt.predict_components_simple = real_pcs
        bt.solve_plan = real_solve
    report = Path(cfg.report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("V7B_ARM_DONE", cfg.tag, json.dumps(out), flush=True)
    return out


def multiseed_summary(outs: list[dict], bases: list[int]) -> dict:
    """The aggregate line's payload: the spread a verdict is read against.

    ``scripts/seed_stats.py`` builds the identical dict from banked reports;
    ``tests/test_seed_stats.py`` pins the two together.
    """
    totals = [int(o["total"]) for o in outs]
    return {"totals": totals,
            "mean": round(sum(totals) / len(totals), 1),
            "spread": max(totals) - min(totals),
            "range": [min(totals), max(totals)],
            "seed_bases": [int(b) for b in bases]}


def main(argv: list[str]) -> dict:
    """Every base this invocation asks for, in sequence.

    Patches are installed once around the whole loop: the minutes head, the
    training frame, the priors and the noise table are all seed-independent,
    and re-installing them per base would only add ways for the third run to
    differ from the first.
    """
    configs, bases, tag = arm_configs(argv)
    undo = apply_patches(configs[0])
    payload = getattr(undo, "payload", None)
    try:
        outs = [run_one(cfg, payload) for cfg in configs]
    finally:
        undo()
    if bases is None:
        return outs[0]
    summary = multiseed_summary(outs, bases)
    print("MULTISEED_DONE", tag, json.dumps(summary), flush=True)
    return summary
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v7b_driver.py`

- [ ] **Commit.**

```bash
git add scripts/v7b_replay.py tests/test_v7b_driver.py && git commit -m "$(cat <<'EOF'
feat: multi-seed replay loop and the MULTISEED_DONE aggregate line

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — F2: `scripts/seed_stats.py`

**Files:**
- Create `scripts/seed_stats.py`
- Create `tests/test_seed_stats.py`

- [ ] **Write the failing test.** Create `tests/test_seed_stats.py`:

```python
"""The standalone seed aggregator: banked reports -> one multi-seed reading."""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, "scripts")

import seed_stats  # noqa: E402
import v7b_replay  # noqa: E402


def _report(path, total, base):
    payload = {"total": total, "config": {"seed_base": base}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_a_report_gives_up_its_total_and_its_seed_base(tmp_path):
    path = _report(tmp_path / "a.json", 1876, 20260901)
    assert seed_stats.read_report(path) == (1876, 20260901)


def test_a_report_with_no_recorded_base_still_reads(tmp_path):
    """Reports predating --seed-base carry no config block; the total is what
    the aggregate needs."""
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"total": 1799}), encoding="utf-8")
    assert seed_stats.read_report(path) == (1799, None)


def test_the_aggregate_is_the_mean_spread_and_range(tmp_path, capsys):
    """The v7b heuristic trio, read back off disk: one number per run, and a
    spread of 115 points that no arm gap in the cycle came close to."""
    paths = [_report(tmp_path / "a.json", 1876, 20260901),
             _report(tmp_path / "b.json", 1901, 20260915),
             _report(tmp_path / "c.json", 1786, 20260825)]
    out = seed_stats.main(paths)
    assert out == {"totals": [1876, 1901, 1786], "mean": 1854.3,
                   "spread": 115, "range": [1786, 1901],
                   "seed_bases": [20260901, 20260915, 20260825]}
    printed = capsys.readouterr().out.strip().splitlines()
    assert "total=1876" in printed[0]
    assert json.loads(printed[-1]) == out


def test_the_aggregator_and_the_driver_agree_key_for_key():
    """Six lines of arithmetic exist in two places so the aggregator stays
    importable without lightgbm. This is what stops the copy drifting."""
    outs = [{"total": 1876}, {"total": 1901}, {"total": 1786}]
    bases = [20260901, 20260915, 20260825]
    assert seed_stats.aggregate([o["total"] for o in outs], bases) == \
        v7b_replay.multiseed_summary(outs, bases)


def test_no_arguments_is_a_usage_error():
    with pytest.raises(SystemExit):
        seed_stats.main([])
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_seed_stats.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'seed_stats'`.

- [ ] **Write the minimal implementation.** Create `scripts/seed_stats.py`:

```python
"""Aggregate banked replay reports into one multi-seed reading.

``scripts/v7b_replay.py --seed-bases`` prints this line for a trio it drove
itself. This reads the same numbers back off reports already on disk, so three
single-seed runs banked weeks apart — every v7b report is one — can still be
read as one measurement without spending another replay.

Usage::

    uv run python scripts/seed_stats.py reports/v7b_q1b-heur.json \\
        reports/v7b_q1c-heur.json reports/v7b_q2-ctrl-heur.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def read_report(path: str | Path) -> tuple[int, int | None]:
    """``(total, seed_base)`` from one replay report.

    The base is ``None`` for a report written before ``--seed-base`` was
    recorded; the total is the number the aggregate is about either way.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    base = payload.get("config", {}).get("seed_base")
    return int(payload["total"]), (int(base) if base is not None else None)


def aggregate(totals: list[int], seed_bases: list[int | None]) -> dict:
    """The ``MULTISEED_DONE`` payload — identical keys, identical arithmetic.

    Deliberately a copy of ``v7b_replay.multiseed_summary`` rather than an
    import of it: importing that module pulls in ``gaffer.backtest`` and
    lightgbm to average three integers, and this script exists to be cheap.
    ``tests/test_seed_stats.py`` asserts the two agree.
    """
    values = [int(t) for t in totals]
    return {"totals": values,
            "mean": round(sum(values) / len(values), 1),
            "spread": max(values) - min(values),
            "range": [min(values), max(values)],
            "seed_bases": [int(b) if b is not None else None
                           for b in seed_bases]}


def main(argv: list[str]) -> dict:
    """Print one line per report, then the aggregate JSON."""
    if not argv:
        raise SystemExit("usage: seed_stats.py <report.json> [report.json ...]")
    totals: list[int] = []
    bases: list[int | None] = []
    for path in argv:
        total, base = read_report(path)
        totals.append(total)
        bases.append(base)
        print(f"{path}: total={total} seed_base={base}")
    out = aggregate(totals, bases)
    print(json.dumps(out))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_seed_stats.py`

- [ ] **Commit.**

```bash
git add scripts/seed_stats.py tests/test_seed_stats.py && git commit -m "$(cat <<'EOF'
feat: seed_stats aggregates banked replay reports into one reading

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — F2: the conventions doc

**Files:**
- Create `docs/superpowers/CONVENTIONS.md`
- Modify `docs/superpowers/ROADMAP.md` (one line inserted after line 5, the end of the header paragraph)
- Modify `tests/test_v7b_driver.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_v7b_driver.py`:

```python
def test_the_conventions_doc_is_committed_and_linked_from_the_roadmap():
    """A measurement standard that is not findable is not a standard. Eight
    numbered conventions, and the roadmap header points at them."""
    doc = Path("docs/superpowers/CONVENTIONS.md")
    body = doc.read_text(encoding="utf-8")
    for n in range(1, 9):
        assert f"## {n}." in body, f"convention {n} is missing"
    roadmap = Path("docs/superpowers/ROADMAP.md").read_text(encoding="utf-8")
    assert "CONVENTIONS.md" in roadmap
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_v7b_driver.py -k conventions`
  Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'docs/superpowers/CONVENTIONS.md'`.

- [ ] **Write the minimal implementation.** Create `docs/superpowers/CONVENTIONS.md`:

```markdown
# Gaffer measurement conventions

The discipline learned the hard way between v4c and v7b. These are house rules
for every cycle that gates a model change on a number, and a plan that breaks
one is wrong even if its code is right.

## 1. Every replay gate runs K >= 3 seed bases

Verdicts read mean +/- spread, never one draw. v7b measured a seed spread of
116 points on the heuristic arm — larger than every arm gap the project has
ever gated on. One draw measures the seed.

`scripts/v7b_replay.py --seed-bases a,b,c` runs the trio and prints the
aggregate; `scripts/seed_stats.py` reads the same aggregate off reports already
banked.

## 2. Gates are pre-registered

The spec states the gate and its mechanical verdict rule before any arm runs.
A rule written after the numbers are in is a rationalisation of the numbers.

## 3. Every comparison carries its control arm

Raw / no-op, run in the same batch on the same code. v7-model's S2 lesson: an
arm that beat nothing is an arm that was never compared.

## 4. The evidence appendix is transcribed into the spec

`logs/` is gitignored, so every `*_ARM_DONE` line the cycle produced is copied
into the spec verbatim. A verdict whose evidence lives only on one laptop is a
verdict nobody can re-read.

## 5. Single-seed causal claims are residuals, not conclusions

If only one draw exists, the finding is named a residual and stays open. It may
motivate the next cycle; it may not close one.

## 6. A failing gate ships OFF behind its flag

With the negative result recorded in the spec. Deleting a failed arm loses the
measurement that cost the hours.

## 7. The orchestrator runs the gates

Implementers build the driver and do not run it. Self-certification is how an
arm ends up measured against its own author's expectation.

## 8. Security ritual after any merge or push

Grep the diff for keys, and confirm `git show main:config.toml` fails. Every
time, not only when the cycle touched config.
```

Then in `docs/superpowers/ROADMAP.md`, replace lines 3-5:

```
One place to see what's shipped and what's left. Grouping comes from
`research/2026-08-25-improvement-research.md`. Update this file as cycles
progress: flip `[ ]` → `[x]`, link the spec/plan when they exist.
```

with:

```
One place to see what's shipped and what's left. Grouping comes from
`research/2026-08-25-improvement-research.md`. Update this file as cycles
progress: flip `[ ]` → `[x]`, link the spec/plan when they exist.
Measurement rules every cycle follows: `CONVENTIONS.md`.
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v7b_driver.py`

- [ ] **Commit.**

```bash
git add docs/superpowers/CONVENTIONS.md docs/superpowers/ROADMAP.md tests/test_v7b_driver.py && git commit -m "$(cat <<'EOF'
docs: the eight measurement conventions, linked from the roadmap

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — F3: the pen tracker's readers

**Files:**
- Create `src/gaffer/pen_tracker.py`
- Create `tests/test_pen_tracker.py`

`data/live/player_gw.parquet` carries no `us_npxg` (verified: its columns end at the three set-piece orders), and `pen_estimate` needs one. Understat lives in `data/history/understat_player.parquet`, which **does** carry the current season (verified: seasons 2022-23 … 2026-27). So the tracker joins it itself, on `(code, UK match date)` — exactly the key `models.train.attach_understat` (`src/gaffer/models/train.py:134`) uses — inside a guarded read, and degrades when that season is absent.

- [ ] **Write the failing test.** Create `tests/test_pen_tracker.py`:

```python
"""The v6 penalty term measured forward: takers predicted vs pens taken."""

from __future__ import annotations

import pandas as pd

from gaffer.pen_tracker import (attach_npxg, finished_gws, predicted_ep,
                                realized_pens)


def _week() -> pd.DataFrame:
    """One finished gameweek of live rows: two clubs, two spot kicks.

    Code 10 is his club's first-choice taker and scored one (xg 1.05 against
    an open-play 0.20 — a 0.85 gap, one penalty's worth). Code 12 has no
    recorded order and missed one.
    """
    return pd.DataFrame({
        "gw": [1, 1, 1],
        "code": [10, 11, 12],
        "name": ["First Choice", "Second Name", "Other Club"],
        "position": ["MID", "FWD", "DEF"],
        "team_code": [3, 3, 7],
        "kickoff_time": ["2026-08-22T14:00:00Z"] * 3,
        "xg": [1.05, 0.20, 0.30],
        "pens_missed": [0, 0, 1],
        "penalties_order": [1.0, 2.0, None]})


def _understat() -> pd.DataFrame:
    return pd.DataFrame({
        "season": ["2026-27"] * 3,
        "season_idx": [4] * 3,
        "code": [10, 11, 12],
        "date": ["2026-08-22"] * 3,
        "us_npxg": [0.20, 0.20, 0.30]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def _with_understat(monkeypatch, tmp_path, us=None):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    store_mod.save(_understat() if us is None else us,
                   "history/understat_player.parquet")


def test_finished_gameweeks_are_the_ones_the_league_has_played():
    assert finished_gws(_events()) == [1]


def test_an_events_frame_without_the_column_yields_nothing():
    assert finished_gws(pd.DataFrame({"gw": [1]})) == []


def test_the_understat_join_lands_on_the_uk_match_date(tmp_path, monkeypatch):
    """Understat carries no gameweek number, so the key is the player and the
    date — unique even in a double gameweek."""
    _with_understat(monkeypatch, tmp_path)
    out = attach_npxg(_week(), "2026-27")
    assert list(out["us_npxg"]) == [0.20, 0.20, 0.30]
    assert len(out) == 3


def test_a_season_understat_has_never_seen_is_no_join(tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    assert attach_npxg(_week(), "2028-29") is None


def test_no_understat_parquet_at_all_is_no_join(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert attach_npxg(_week(), "2026-27") is None


def test_the_xg_gap_instrument_counts_the_penalty_that_was_taken(
        tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    events, instrument = realized_pens(_week(), "2026-27")
    assert instrument == "xg_gap"
    assert list(events) == [1.0, 0.0, 0.0]


def test_without_understat_it_degrades_to_pens_missed(tmp_path, monkeypatch):
    """A floor, not a count — every converted spot kick is invisible to the
    FPL feed alone — so the instrument is named and the two never mix."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    events, instrument = realized_pens(_week(), "2026-27")
    assert instrument == "pens_missed_only"
    assert list(events) == [0.0, 0.0, 1.0]


def test_a_frame_with_neither_signal_reports_no_penalties(tmp_path,
                                                          monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    bare = _week().drop(columns=["xg", "pens_missed"])
    events, instrument = realized_pens(bare, "2026-27")
    assert instrument == "pens_missed_only"
    assert list(events) == [0.0, 0.0, 0.0]


def test_the_component_file_gives_the_pen_term_that_was_served(tmp_path,
                                                               monkeypatch):
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    pd.DataFrame({"code": [10, 11], "gw": [1, 1],
                  "ep_pen_taker": [0.42, 0.0]}).to_parquet(
                      tmp_path / "components_gw1.parquet", index=False)
    assert predicted_ep(1) == {"rows": 2, "ep_pen_taker": 0.42, "takers": 1}


def test_a_gameweek_with_no_component_file_predicted_nothing(tmp_path,
                                                             monkeypatch):
    """The tracker covers a whole season and the earliest weeks of one
    predate the artifact — that is a zero, not an error."""
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    assert predicted_ep(1) == {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_pen_tracker.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.pen_tracker'`.

- [ ] **Write the minimal implementation.** Create `src/gaffer/pen_tracker.py`:

```python
"""The v6 penalty term, measured forward: takers predicted vs pens taken.

Read-only over what has already been banked — ``reports/components_gw{N}.parquet``
for what was served, ``data/live/player_gw.parquet`` for the week that happened.
Nothing here trains, fetches, or writes a model input, and nothing here touches
``set_pieces``: it imports the pure functions and constants and leaves the
module alone.

The v6 validation was deferred to season end. This turns that one May
comparison into a standing report that accrues weekly, which is the only
version of it anybody will actually read.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.data import store
from gaffer.set_pieces import (GOAL_POINTS, LEAGUE_PENS_PG, PEN_CONVERSION,
                               pen_estimate, share_now)

PLAYER_GW_PATH = "live/player_gw.parquet"
EVENTS_PATH = "live/events.parquet"
UNDERSTAT_PATH = "history/understat_player.parquet"


def tracker_path() -> Path:
    """``reports/pen_tracker.json``, resolved through ``artifacts.REPORTS``.

    Read at call time rather than bound at import, so a test that redirects
    the reports directory redirects the component files and this output
    together.
    """
    return artifacts.REPORTS / "pen_tracker.json"


def finished_gws(events: pd.DataFrame) -> list[int]:
    """Gameweeks the league has actually played, in order.

    Only finished weeks: a gameweek in progress has half its penalties still
    to come, and a tracker that counted it would report a hit rate that moves
    on Sunday for reasons that are not evidence.
    """
    if events is None or "finished" not in events.columns:
        return []
    done = events[events["finished"].astype(bool)]
    return sorted(int(g) for g in done["gw"].unique())


def attach_npxg(rows: pd.DataFrame, season: str) -> pd.DataFrame | None:
    """``rows`` with Understat's ``us_npxg`` joined on (code, UK match date).

    The live parquet has no ``us_npxg`` — Understat is joined in the training
    frame, not the serving one — so the tracker does the join itself, on the
    same key ``models.train.attach_understat`` uses: Understat carries no
    gameweek number, and a player plus a date is unique even in a double
    gameweek.

    ``None`` — not a frame of NaN — when the parquet is missing or has nothing
    for this season, so the caller can tell "no coverage" from "no penalties"
    and name the instrument it fell back to.
    """
    if not store.exists(UNDERSTAT_PATH):
        return None
    us = store.load(UNDERSTAT_PATH)
    if us.empty or "us_npxg" not in us.columns:
        return None
    us = us[us["season"].astype(str) == str(season)]
    if us.empty:
        return None
    keyed = us[["code", "date", "us_npxg"]].copy()
    keyed["date"] = pd.to_datetime(keyed["date"], errors="coerce").dt.date
    keyed = keyed.drop_duplicates(subset=["code", "date"])
    out = rows.copy()
    out["_date"] = pd.to_datetime(out["kickoff_time"], errors="coerce",
                                  utc=True).dt.tz_convert(
                                      "Europe/London").dt.date
    out = out.merge(keyed.rename(columns={"date": "_date"}),
                    on=["code", "_date"], how="left", validate="many_to_one")
    return out.drop(columns=["_date"])


def realized_pens(rows: pd.DataFrame, season: str) -> tuple[pd.Series, str]:
    """Penalties taken per player-match, and the instrument that saw them.

    The xG-gap estimator when Understat covers the season, and otherwise the
    only penalties the FPL feed alone can see: the ones that were *missed*.
    That is a floor rather than a count — every converted spot kick is
    invisible to it — so the fallback is named ``pens_missed_only`` in the
    report and the two are never added together.

    ``rows`` is assumed to carry a fresh range index; the caller resets it.
    """
    joined = attach_npxg(rows, season)
    if joined is not None:
        events = pen_estimate(joined)
        if events is not None:
            return (pd.Series(events.to_numpy(), index=rows.index,
                              dtype="float64"), "xg_gap")
    if "pens_missed" not in rows.columns:
        return pd.Series(0.0, index=rows.index, dtype="float64"), \
            "pens_missed_only"
    missed = pd.to_numeric(rows["pens_missed"], errors="coerce").fillna(0.0)
    return missed.astype("float64"), "pens_missed_only"


def predicted_ep(gw: int) -> dict:
    """The pen term this gameweek's advise run actually served.

    Read off ``ep_pen_taker``, which ``run_advise`` already rescaled by the
    odds blend — so this is the increment that was *delivered*, not the one
    the model proposed. An absent component file is zeros: the tracker covers
    a whole season and the earliest weeks of one predate the artifact.
    """
    path = artifacts.components_path(gw)
    if not path.exists():
        return {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}
    comp = pd.read_parquet(path)
    if "ep_pen_taker" not in comp.columns:
        return {"rows": int(len(comp)), "ep_pen_taker": 0.0, "takers": 0}
    ep = pd.to_numeric(comp["ep_pen_taker"], errors="coerce").fillna(0.0)
    return {"rows": int(len(comp)),
            "ep_pen_taker": round(float(ep.sum()), 3),
            "takers": int((ep.abs() > 0).sum())}
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_pen_tracker.py`

- [ ] **Commit.**

```bash
git add src/gaffer/pen_tracker.py tests/test_pen_tracker.py && git commit -m "$(cat <<'EOF'
feat: pen tracker readers — Understat join, realized-pen instrument

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — F3: the report itself

**Files:**
- Modify `src/gaffer/pen_tracker.py` (append `gw_block`, `season_totals`, `_current_season`, `track_pens`, `save_tracker`, `format_tracker`)
- Modify `tests/test_pen_tracker.py` (import line; append tests)

- [ ] **Write the failing test.** In `tests/test_pen_tracker.py`, replace the import:

```python
from gaffer.pen_tracker import (attach_npxg, finished_gws, predicted_ep,
                                realized_pens)
```

with:

```python
from gaffer.pen_tracker import (attach_npxg, finished_gws, format_tracker,
                                gw_block, predicted_ep, realized_pens,
                                save_tracker, season_totals, track_pens,
                                tracker_path)
```

and append:

```python
def _live(monkeypatch, tmp_path, understat=True):
    """A whole finished gameweek on disk: live rows, events, components."""
    from gaffer import artifacts
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "REPORTS", tmp_path / "reports")
    (tmp_path / "reports").mkdir(exist_ok=True)
    store_mod.save(_week(), "live/player_gw.parquet")
    store_mod.save(_events(), "live/events.parquet")
    if understat:
        store_mod.save(_understat(), "history/understat_player.parquet")
    pd.DataFrame({"code": [10], "gw": [1], "ep_pen_taker": [0.42]}).to_parquet(
        tmp_path / "reports" / "components_gw1.parquet", index=False)


def test_a_gameweek_block_pairs_the_prediction_with_what_happened(
        tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path)
    block = gw_block(_week(), 1, "2026-27")
    assert block["gw"] == 1
    assert block["instrument"] == "xg_gap"
    assert block["predicted_ep_pen_taker"] == 0.42
    assert block["predicted_takers"] == 1
    assert block["pens_taken"] == 1.0
    assert block["pens_by_first_choice"] == 1.0
    assert block["taker_hit_rate"] == 1.0
    assert block["team_games"] == 2
    assert block["pens_per_team_game"] == 0.5
    # one penalty, MID, 0.78 converted x 5 points a goal
    assert block["realized_pen_points"] == 3.9


def test_a_week_with_no_penalties_has_no_hit_rate(tmp_path, monkeypatch):
    """Zero over zero is not zero — it is "nothing to say yet", and a 0.0 hit
    rate would read as the taker model being wrong every time."""
    _live(monkeypatch, tmp_path)
    quiet = _week().assign(xg=[0.2, 0.2, 0.3], pens_missed=[0, 0, 0])
    block = gw_block(quiet, 1, "2026-27")
    assert block["pens_taken"] == 0.0
    assert block["taker_hit_rate"] is None
    assert block["pens_per_team_game"] == 0.0


def test_the_season_totals_add_the_blocks_up(tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path)
    totals = season_totals([gw_block(_week(), 1, "2026-27")])
    assert totals["gws"] == 1
    assert totals["instruments"] == ["xg_gap"]
    assert totals["pens_taken"] == 1.0
    assert totals["taker_hit_rate"] == 1.0
    assert totals["league_pens_pg_served"] == 0.13
    assert totals["realized_pen_points"] == 3.9


def test_the_tracker_covers_every_finished_gameweek(tmp_path, monkeypatch):
    """Gate G3: GW1 is finished, GW2 and GW3 are not, and only the played
    week may appear."""
    _live(monkeypatch, tmp_path)
    report = track_pens(season="2026-27")
    assert report["season"] == "2026-27"
    assert [b["gw"] for b in report["gws"]] == [1]
    assert report["season_totals"]["pens_taken"] == 1.0
    assert report["notes"] == []


def test_a_degraded_instrument_is_named_in_the_report(tmp_path, monkeypatch):
    _live(monkeypatch, tmp_path, understat=False)
    report = track_pens(season="2026-27")
    assert report["gws"][0]["instrument"] == "pens_missed_only"
    assert any("pens_missed" in note for note in report["notes"])


def test_no_live_season_on_disk_is_an_empty_report(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    report = track_pens(season="2026-27")
    assert report["gws"] == []
    assert report["season_totals"] == {}
    assert report["notes"]


def test_a_broken_artifact_degrades_instead_of_raising(tmp_path, monkeypatch):
    """A season tracker that dies on one bad file is a tracker nobody runs."""
    from gaffer import pen_tracker
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    store_mod.save(_week(), "live/player_gw.parquet")
    store_mod.save(_events(), "live/events.parquet")

    def boom(events):
        raise RuntimeError("events parquet is truncated")

    monkeypatch.setattr(pen_tracker, "finished_gws", boom)
    report = pen_tracker.track_pens(season="2026-27")
    assert report["gws"] == []
    assert any("truncated" in note for note in report["notes"])


def test_the_report_is_written_atomically(tmp_path, monkeypatch):
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path / "reports")
    path = save_tracker({"season": "2026-27", "gws": [], "season_totals": {},
                         "notes": []})
    assert path == tracker_path()
    assert json.loads(path.read_text())["season"] == "2026-27"
    assert not list(path.parent.glob("*.tmp"))


def test_the_printed_table_names_the_instrument_and_the_season(tmp_path,
                                                               monkeypatch):
    _live(monkeypatch, tmp_path)
    text = format_tracker(track_pens(season="2026-27"))
    assert "2026-27" in text
    assert "xg_gap" in text
    assert "season:" in text
```

Add `import json` to the test module's imports (after `from __future__ import annotations`, before `import pandas as pd`).

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_pen_tracker.py`
  Expected: collection error — `ImportError: cannot import name 'format_tracker' from 'gaffer.pen_tracker'`.

- [ ] **Write the minimal implementation.** Append to `src/gaffer/pen_tracker.py`:

```python
def gw_block(week: pd.DataFrame, gw: int, season: str) -> dict:
    """One finished gameweek: what was predicted against what happened.

    ``team_games`` counts distinct (club, kickoff) pairs rather than clubs, so
    a double gameweek contributes two team-games and the observed pens-per-game
    stays comparable with the served :data:`LEAGUE_PENS_PG`.

    A week with no penalties reports ``None`` for the hit rate, not zero: zero
    over zero would read as the taker model having been wrong every time.
    """
    week = week.reset_index(drop=True)
    events, instrument = realized_pens(week, season)
    order = (week["penalties_order"] if "penalties_order" in week.columns
             else pd.Series(pd.NA, index=week.index))
    share = share_now(order)
    positions = (week["position"].astype(str) if "position" in week.columns
                 else pd.Series("MID", index=week.index))
    goal_points = positions.map(GOAL_POINTS).astype("float64").fillna(0.0)
    taken = float(events.sum())
    by_first = float(events[share >= 1.0].sum())
    team_games = 0
    if {"team_code", "kickoff_time"} <= set(week.columns):
        team_games = int(len(week[["team_code", "kickoff_time"]]
                             .drop_duplicates()))
    pred = predicted_ep(gw)
    return {
        "gw": int(gw),
        "instrument": instrument,
        "rows": int(len(week)),
        "team_games": team_games,
        "component_rows": pred["rows"],
        "predicted_ep_pen_taker": pred["ep_pen_taker"],
        "predicted_takers": pred["takers"],
        "pens_taken": round(taken, 3),
        "pens_by_first_choice": round(by_first, 3),
        "taker_hit_rate": round(by_first / taken, 3) if taken else None,
        "pens_per_team_game": (round(taken / team_games, 4) if team_games
                               else None),
        "realized_pen_points": round(
            float((events * PEN_CONVERSION * goal_points).sum()), 3),
    }


def season_totals(blocks: list[dict]) -> dict:
    """The season line: the cumulative comparison the v6 validation wanted.

    ``instruments`` is a list because a season can straddle an Understat
    backfill, and totals mixing a counted week with a missed-only week are not
    one measurement.
    """
    taken = sum(b["pens_taken"] for b in blocks)
    first = sum(b["pens_by_first_choice"] for b in blocks)
    games = sum(b["team_games"] for b in blocks)
    return {
        "gws": len(blocks),
        "instruments": sorted({b["instrument"] for b in blocks}),
        "team_games": games,
        "predicted_ep_pen_taker": round(
            sum(b["predicted_ep_pen_taker"] for b in blocks), 3),
        "pens_taken": round(taken, 3),
        "pens_by_first_choice": round(first, 3),
        "taker_hit_rate": round(first / taken, 3) if taken else None,
        "pens_per_team_game": round(taken / games, 4) if games else None,
        "league_pens_pg_served": LEAGUE_PENS_PG,
        "realized_pen_points": round(
            sum(b["realized_pen_points"] for b in blocks), 3),
    }


def _current_season() -> str:
    """``cfg.current_season``, or ``""`` when there is no readable config."""
    try:
        from gaffer.config import load_config

        return str(load_config().current_season or "")
    except Exception:  # noqa: BLE001 — a report never blocks on config
        return ""


def track_pens(season: str | None = None) -> dict:
    """The season so far, gameweek by gameweek. Never raises.

    Every failure — no live season, a truncated parquet, an Understat file
    that will not read — comes back as an empty report carrying a note. A
    standing report that dies on one bad file is a report nobody runs.
    """
    report: dict = {"season": "", "gws": [], "season_totals": {}, "notes": []}
    try:
        report["season"] = str(
            season if season is not None else _current_season())
        if not store.exists(PLAYER_GW_PATH) or not store.exists(EVENTS_PATH):
            report["notes"].append(
                "no live season on disk — run `gaffer refresh` first")
            return report
        rows = store.load(PLAYER_GW_PATH)
        have = {int(g) for g in rows["gw"].unique()}
        done = [g for g in finished_gws(store.load(EVENTS_PATH)) if g in have]
        if not done:
            report["notes"].append("no finished gameweek in the live season yet")
            return report
        report["gws"] = [gw_block(rows[rows["gw"] == g], g, report["season"])
                         for g in done]
        report["season_totals"] = season_totals(report["gws"])
        if any(b["instrument"] == "pens_missed_only" for b in report["gws"]):
            report["notes"].append(
                "penalties counted from pens_missed only — Understat npxg is "
                "not on disk for this season, so converted spot kicks are "
                "invisible and every count here is a floor")
        return report
    except Exception as exc:  # noqa: BLE001 — a standing report never blocks
        report["notes"].append(f"pen tracker degraded: {exc}")
        return report


def save_tracker(report: dict) -> Path:
    """``reports/pen_tracker.json``, through a temp file and ``os.replace``.

    The same atomic write as :func:`gaffer.evaluation.save_evaluation`, and for
    the same reason: a reader either sees the whole previous report or the
    whole new one, never the half-written middle.
    """
    text = json.dumps(report, indent=1, allow_nan=False)
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = tracker_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def format_tracker(report: dict) -> str:
    """The printed table: one line per gameweek, then the season line."""
    lines = [f"Penalty tracker — season {report.get('season') or 'unknown'}",
             f"{'GW':>3}  {'pred EP':>8}  {'pens':>5}  {'1st':>5}  "
             f"{'hit':>5}  {'per game':>9}  instrument"]
    for b in report.get("gws", []):
        hit = ("    —" if b["taker_hit_rate"] is None
               else f"{b['taker_hit_rate']:>5.2f}")
        per = ("        —" if b["pens_per_team_game"] is None
               else f"{b['pens_per_team_game']:>9.3f}")
        lines.append(
            f"{b['gw']:>3}  {b['predicted_ep_pen_taker']:>8.2f}  "
            f"{b['pens_taken']:>5.1f}  {b['pens_by_first_choice']:>5.1f}  "
            f"{hit}  {per}  {b['instrument']}")
    totals = report.get("season_totals") or {}
    if totals:
        lines.append(
            f"season: predicted EP {totals['predicted_ep_pen_taker']:.2f} vs "
            f"realized pen points {totals['realized_pen_points']:.2f} over "
            f"{totals['gws']} gw — {totals['pens_taken']:.1f} pens in "
            f"{totals['team_games']} team-games against a served "
            f"{totals['league_pens_pg_served']}/game")
    for note in report.get("notes", []):
        lines.append(f"note: {note}")
    return "\n".join(lines)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_pen_tracker.py`

- [ ] **Commit.**

```bash
git add src/gaffer/pen_tracker.py tests/test_pen_tracker.py && git commit -m "$(cat <<'EOF'
feat: the pen tracker's per-gameweek blocks, season totals and report

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — F3: the `gaffer track-pens` subcommand

**Files:**
- Modify `src/gaffer/cli.py` (insert after the `evaluate` command body, which ends at line 415, before `@app.command()` / `def ui(...)` at line 417)
- Modify `tests/test_cli.py` (append)

- [ ] **Write the failing test.** Append to `tests/test_cli.py`:

```python
def test_track_pens_is_registered_and_writes_its_report(monkeypatch, tmp_path):
    """Gate G3's front door. Not wired into `evaluate`: evaluation.json's
    schema stays stable and the Model hub is untouched this cycle."""
    from typer.testing import CliRunner

    from gaffer import pen_tracker
    from gaffer.cli import app

    seen = {}

    def fake(season):
        seen["season"] = season
        return {"season": "2026-27", "gws": [], "season_totals": {},
                "notes": []}

    monkeypatch.setattr(pen_tracker, "track_pens", fake)
    monkeypatch.setattr(pen_tracker, "save_tracker",
                        lambda report: tmp_path / "pen_tracker.json")
    result = CliRunner().invoke(app, ["track-pens"])
    assert result.exit_code == 0
    assert seen["season"] is None
    assert "Penalty tracker" in result.output
    assert "pen_tracker.json" in result.output


def test_track_pens_passes_the_season_through(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from gaffer import pen_tracker
    from gaffer.cli import app

    seen = {}

    def fake(season):
        seen["season"] = season
        return {"season": season, "gws": [], "season_totals": {}, "notes": []}

    monkeypatch.setattr(pen_tracker, "track_pens", fake)
    monkeypatch.setattr(pen_tracker, "save_tracker",
                        lambda report: tmp_path / "pen_tracker.json")
    result = CliRunner().invoke(app, ["track-pens", "--season", "2025-26"])
    assert result.exit_code == 0
    assert seen["season"] == "2025-26"
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_cli.py -k track_pens`
  Expected: both fail on `assert result.exit_code == 0` with exit code 2 — typer reports `No such command 'track-pens'`.

- [ ] **Write the minimal implementation.** In `src/gaffer/cli.py`, insert between the end of `evaluate` (line 415) and the `@app.command()` above `def ui(...)` (line 417):

```python
@app.command("track-pens")
def track_pens_cmd(season: str = typer.Option(
        "", help="Season to track (default: fpl.current_season).")):
    """Predicted penalty EP against the penalties actually taken (v7c F3)."""
    from gaffer.pen_tracker import format_tracker, save_tracker, track_pens

    report = track_pens(season or None)
    path = save_tracker(report)
    typer.echo(format_tracker(report))
    typer.echo(f"Wrote {path}")
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_cli.py`

- [ ] **Commit.**

```bash
git add src/gaffer/cli.py tests/test_cli.py && git commit -m "$(cat <<'EOF'
feat: gaffer track-pens subcommand

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — Gate G4: full suite and the protected-file audit

**Files:** none modified. No frontend change was made this cycle, so `npx tsc --noEmit` is not run.

- [ ] **Run the whole suite.**

```bash
uv run pytest -q
```

Expected: green, with no skips introduced by this cycle.

- [ ] **Audit the protected files — this must print nothing at all.**

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py 'src/gaffer/optimize/*' tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py 'tests/test_*_degradation.py' scripts/s2_replay.py
```

If any line appears, the cycle has failed spec §4: revert that file to `main`'s content and re-run the suite.

- [ ] **Audit what the cycle actually touched** — the list must be exactly the eighteen files in the File structure table, plus this plan document and the spec (both committed by the orchestrator), and must contain nothing under `data/`, `reports/`, `models/`, `logs/`, `.claude/`, or `config.toml`.

```bash
git diff main --stat
```

- [ ] **Smoke the three new entry points** (each is safe on live data and none writes a model input):

```bash
uv run gaffer snapshot
uv run gaffer snapshot
uv run python -c "import pandas as pd; d = pd.read_parquet('data/live/availability_log.parquet'); print(len(d), d['snap_date'].nunique(), 'days')"
uv run gaffer track-pens
uv run python scripts/seed_stats.py reports/v7b_q1b-heur.json reports/v7b_q1c-heur.json reports/v7b_q2-ctrl-heur.json
```

Expected: two `Snapshot: N availability rows …` lines with the row count unchanged after the second run and exactly one distinct `snap_date` (gate G1a/G1b); a penalty table covering GW1 plus `Wrote reports/pen_tracker.json` (gate G3); and a `{"totals": [1876, 1901, 1786], "mean": 1854.3, "spread": 115, …}` aggregate for the banked heuristic trio (gate G2). Record all of it in the spec's §8 evidence block — convention 4.

- [ ] **No commit.** This task changes no files; the orchestrator reviews the branch and runs the gates.
