# Gaffer v7d Cockpit Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the five deferred cockpit items — a fast advise that skips the scenario sweep, the penalty tracker on the Model hub, the snapshot button, the compare-card name treatment, and a light theme — without moving a single line of model behaviour.

**Architecture:** Five independent additions on existing seams. F1 rides `Config.scenarios_n` (`src/gaffer/advise.py:734` already guards the sweep on `> 0`): a typer `--fast` flag and a new job kind, both threading `dataclasses.replace(cfg, scenarios_n=0)` through the *existing* `run_train_and_advise` body, which grows one defaulted keyword. F2 follows the quality.py pattern — the CLI/job writes `reports/pen_tracker.json`, a new `GET /api/pens` on the quality router reads it, a `PensSection` renders it. F3 is two lines of frontend wiring for a job kind the backend already has. F4 adds a `heading` slot to `Card` so the one `PlayerName` component reaches the compare cards and the explorer. F5 is a CSS-variable override block plus a three-state preference hook — every colour in the app is already var-backed, so no component changes for it.

**Tech Stack:** Python 3.12, uv, typer, FastAPI, pydantic, pytest; React 18, TypeScript, Tailwind v4, Radix, Recharts, vitest + jsdom.

**Prerequisite:** work on branch `feat/gaffer-v7d` cut from `main`. Authoritative spec: `docs/superpowers/specs/2026-08-30-gaffer-v7d-cockpit-polish-design.md`.

**Protected — must show zero diffs at the end (Task 19 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every `tests/test_*_degradation.py`, `scripts/s2_replay.py`.
`JobRunner` and the jobs routes are unchanged: new kinds only, never a new route or a new start signature.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/`, `config.toml` (all gitignored). The single exception is Task 18, which stages the whole build-artifact directory `src/gaffer/web/static` — that directory ships in the wheel and is regenerated wholesale by `npm run build`.

**Count bookkeeping (green after every task):** the backend kind-count assertion in `tests/test_web_job_kinds.py` is edited **twice** — 5→6 in Task 2 (with `advise-fast`) and 6→7 in Task 4 (with `track-pens`) — so the assertion always matches the table that exists at that moment. The frontend union is edited **once**: Task 5 adds all three new kinds (`advise-fast`, `track-pens`, `snapshot`) to `types.ts` and moves `types.test.ts` from 4 to 7 in one step, even though the `advise-fast` button lands in Task 6, the `track-pens`/`snapshot` buttons in Task 8. A kind in the union with no button yet is inert — nothing else in the frontend asserts over `JOB_KINDS`.

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/cli.py` | Modify (`advise`, lines 17-30) | F1: `--fast` flag replacing `scenarios_n` with 0. |
| `tests/test_cli.py` | Modify (append) | F1: the flag threads 0; its absence keeps the configured n. |
| `config.example.toml` | Modify (`[scenarios]`, line 16-18) | One comment line: `n = 0` disables the sweep, `--fast` does it per-run. |
| `src/gaffer/web/routers/advice.py` | Modify (`run_train_and_advise`, lines 27-39) | F1: optional `cfg` keyword, defaulted so every existing caller is untouched. |
| `src/gaffer/web/job_kinds.py` | Modify (docstring, new wrappers, `JOB_KINDS` line 61) | F1/F2: `run_train_and_advise_fast`, `run_track_pens`. |
| `tests/test_web_job_kinds.py` | Modify (lines 24-26 only, twice) | The allow-list assertion: 5→6 (Task 2), 6→7 (Task 4). |
| `tests/test_web_job_kinds_v7c.py` | Modify (docstring + append) | The new kinds' own tests, kept out of the protected `tests/test_web_jobs.py`. |
| `src/gaffer/web/schemas.py` | Modify (append after `Journal`) | F2: `PenTrackerGw`, `PenTrackerTotals`, `PenTracker`. |
| `src/gaffer/web/routers/quality.py` | Modify (imports + append) | F2: `GET /api/pens`, reading `tracker_path()` off disk. |
| `tests/test_web_pens.py` | Create | F2 endpoint suite: served payload, error blocks, missing file → 422. |
| `frontend/src/types.ts` | Modify (`JOB_KINDS` line 570; append pen types) | F1/F2/F3: three new kinds + labels; the pen tracker's row types. |
| `frontend/src/types.test.ts` | Modify (lines 5-8) | The union grows 4 → 7, once. |
| `frontend/src/hubs/ThisWeek.tsx` | Modify (header `action`, line 117) | F1: the Fast advise button beside Run advise. |
| `frontend/src/hubs/ThisWeek.test.tsx` | Modify (append) | F1: the header offers both runs. |
| `frontend/src/hubs/model/QualityTab.tsx` | Modify (imports, new `PensSection`, render) | F2: the penalty card. |
| `frontend/src/hubs/model/QualityTab.test.tsx` | Modify (append) | F2: totals, floor badge, unreadable row, notes, empty state. |
| `frontend/src/hubs/Model.tsx` | Modify (header `action`, lines 29-36) | F2/F3: `track-pens` and `snapshot` buttons. |
| `frontend/src/hubs/Model.test.tsx` | Modify (append) | F2/F3: both buttons and what each one reloads. |
| `frontend/src/kit/Card.tsx` | Modify (props + header) | F4: `heading?: ReactNode`. |
| `frontend/src/kit/Card.test.tsx` | Modify (append) | F4: heading wins visually, the `h3` stays. |
| `frontend/src/kit/PlayerName.test.tsx` | Create | F4: the kit's one untested component. |
| `frontend/src/hubs/players/ComparePanel.tsx` | Modify (line 94) | F4: the card heading becomes the click-to-explain name. |
| `frontend/src/hubs/players/ComparePanel.test.tsx` | Modify (append) | F4: the heading carries the control. |
| `frontend/src/hubs/Players.tsx` | Modify (name column, line ~64) | F4: explorer names become `PlayerName`. |
| `frontend/src/hubs/Players.test.tsx` | Modify (append) | F4: the explorer name is the control. |
| `frontend/src/styles/theme.css` | Modify (after `@theme`) | F5: the light palette and its `prefers-color-scheme` mirror. |
| `frontend/src/styles/theme.test.ts` | Modify (append) | F5: every token once per block, contrast ≥ 4.5:1, boot script present. |
| `frontend/src/kit/useTheme.ts` | Create | F5: three-state preference, localStorage behind try/catch. |
| `frontend/src/kit/useTheme.test.ts` | Create | F5: default, stored, hostile-storage, attribute application. |
| `frontend/src/kit/ThemeToggle.tsx` | Create | F5: three-way segmented control; compact single-button form. |
| `frontend/src/kit/ThemeToggle.test.tsx` | Create | F5: both forms. |
| `frontend/src/kit/index.ts` | Modify (append exports) | F5: `ThemeToggle`, `useTheme`. |
| `frontend/src/kit/index.test.ts` | Modify (append) | F5: the barrel exports it. |
| `frontend/src/kit/AppShell.tsx` | Modify (both branches) | F5: sidebar footer + mobile 7th slot. |
| `frontend/src/kit/AppShell.test.tsx` | Modify (append) | F5: placement in both layouts. |
| `frontend/index.html` | Modify (`<head>`) | F5: the inline boot script. |
| `src/gaffer/web/static/**` | Regenerate (Task 18) | The shipped bundle. |

---

## Task 1 — F1: `gaffer advise --fast`

**Files:**
- Modify `src/gaffer/cli.py` (lines 17-30, the `advise` command signature and its `cfg = load_config()`)
- Modify `tests/test_cli.py` (append at end of file)
- Modify `config.example.toml` (the `[scenarios]` block, lines 16-18)

- [ ] **Write the failing test.** Append to `tests/test_cli.py`:

```python
def _fast_run(tmp_path, monkeypatch, seen, argv):
    """`gaffer advise` over a config that asks for a 40-scenario sweep.

    `run_advise` is replaced by a recorder: what this pins is the config the
    CLI hands it, which is the whole of the --fast contract.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 0\n\n[scenarios]\nn = 40\n')

    def _run(cfg):
        seen["scenarios_n"] = cfg.scenarios_n
        return _stub_advice()

    monkeypatch.setattr("gaffer.advise.run_advise", _run)
    monkeypatch.setattr("gaffer.report.render.render_report",
                        lambda a, model_health=None: "reports/gw2.md")
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)
    return runner.invoke(app, argv)


def test_advise_fast_turns_the_scenario_sweep_off(tmp_path, monkeypatch):
    """--fast is the whole of the fast path: n = 0 is the pre-v4c rail that
    solves once, deterministically (advise.py:734 guards the sweep on n > 0)."""
    seen = {}
    result = _fast_run(tmp_path, monkeypatch, seen, ["advise", "--fast"])
    assert result.exit_code == 0
    assert seen["scenarios_n"] == 0


def test_advise_without_fast_keeps_the_configured_sweep(tmp_path, monkeypatch):
    """The flag is opt-in per run and must not touch config.toml's answer."""
    seen = {}
    result = _fast_run(tmp_path, monkeypatch, seen, ["advise"])
    assert result.exit_code == 0
    assert seen["scenarios_n"] == 40


def test_advise_help_names_the_fast_flag():
    out = runner.invoke(app, ["advise", "--help"]).output
    assert "--fast" in out
```

- [ ] **Run it, expecting failure.** `uv run pytest -q -p no:randomly tests/test_cli.py -k fast`
  Expected: failure — `advise` takes no `--fast` option, so typer exits 2 with "No such option: --fast" and `seen` is empty (`KeyError: 'scenarios_n'` / exit_code 2).

- [ ] **Write the minimal implementation.** In `src/gaffer/cli.py`, replace the `advise` signature and its config load (lines 17-25) with:

```python
@app.command()
def advise(fast: bool = typer.Option(
        False, "--fast",
        help="Skip the scenario sweep (~5 min); serves the raw optimum.")):
    """Full weekly run: refresh -> predict -> optimize -> report."""
    import dataclasses

    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.errors import GafferError
    from gaffer.report.render import render_report

    cfg = load_config()
    # n = 0 is the byte-pinned pre-v4c rail: solve once, deterministically.
    # Every consumer of a scenario field already degrades on its absence
    # (the `_pct` helper below is the CLI's own half of that), so the flag
    # needs no second switch anywhere downstream.
    if fast:
        cfg = dataclasses.replace(cfg, scenarios_n=0)
    if not cfg.entry_id:
```

  (Everything from `if not cfg.entry_id:` onward is unchanged.)

- [ ] **Document the seam.** In `config.example.toml`, replace the `[scenarios]` block's first two lines with:

```toml
[scenarios]
# n = 0 disables the sweep and solves once, deterministically. `gaffer advise
# --fast` and the UI's Fast advise button do that per-run without editing this.
n = 40               # gate D1: gated replay 1818 vs raw 1743 (+75), fewer transfers and hits
```

- [ ] **Run to pass.** `uv run pytest -q -p no:randomly tests/test_cli.py`

- [ ] **Commit.**

```bash
git add src/gaffer/cli.py tests/test_cli.py config.example.toml && git commit -m "$(cat <<'EOF'
feat: gaffer advise --fast skips the scenario sweep

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — F1: the `advise-fast` job kind

**Files:**
- Modify `src/gaffer/web/routers/advice.py` (lines 27-39, `run_train_and_advise`)
- Modify `src/gaffer/web/job_kinds.py` (docstring line 1, new wrapper, `JOB_KINDS` line 61)
- Modify `tests/test_web_job_kinds.py` (lines 24-26 only)
- Modify `tests/test_web_job_kinds_v7c.py` (docstring line 1, append)

- [ ] **Write the failing test.** Replace lines 24-26 of `tests/test_web_job_kinds.py` with:

```python
def test_exactly_the_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "advise-fast", "evaluate",
                                 "news-shadow", "refresh-data", "snapshot"]
```

  Replace line 1 of `tests/test_web_job_kinds_v7c.py` with:

```python
"""The job kinds added after the original five: v7c's snapshot, v7d's
advise-fast and track-pens."""
```

  And append to `tests/test_web_job_kinds_v7c.py`:

```python
def test_the_fast_advise_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["advise-fast"] \
        is job_kinds.run_train_and_advise_fast


def test_the_advise_body_still_defaults_to_the_config_on_disk():
    """The refactor must be invisible to every existing caller: the kind
    table stores the function itself, and the runner calls it with no args."""
    import inspect

    from gaffer.web.routers.advice import run_train_and_advise

    assert inspect.signature(run_train_and_advise).parameters["cfg"].default \
        is None


def test_the_advise_body_uses_the_config_it_is_handed(monkeypatch):
    from gaffer.config import Config
    from gaffer.web.routers.advice import run_train_and_advise

    seen = {}

    class _Advice:
        gw = 5
        expected_pts = 61.0

    def _run(cfg):
        seen["scenarios_n"] = cfg.scenarios_n
        return _Advice()

    monkeypatch.setattr("gaffer.models.train.load_training_frame",
                        lambda: (None, None, None))
    monkeypatch.setattr("gaffer.models.train.train_all",
                        lambda frame, team_frame, save=True: None)
    monkeypatch.setattr("gaffer.advise.run_advise", _run)
    monkeypatch.setattr("gaffer.report.render.render_report",
                        lambda advice, model_health=None: "reports/gw5.html")
    monkeypatch.setattr("gaffer.tracking.latest_health", lambda: None)

    out = run_train_and_advise(
        Config(entry_id=1, league_id=2, scenarios_n=7))
    assert seen["scenarios_n"] == 7
    assert out == {"gw": 5, "expected_pts": 61.0}


def test_fast_advise_replaces_the_sweep_count_with_zero(monkeypatch):
    """The kind is the --fast flag, served: same body, n = 0.

    ``job_kinds`` binds ``run_train_and_advise`` by reference at import, so
    the substitute goes on ``job_kinds`` itself — patching the router module
    would leave the table pointing at the original.
    """
    from gaffer.config import Config

    seen = {}

    def _body(cfg=None):
        seen["cfg"] = cfg
        return {"gw": 5, "expected_pts": 61.0}

    monkeypatch.setattr(
        "gaffer.config.load_config",
        lambda path="config.toml": Config(entry_id=1, league_id=2,
                                          scenarios_n=40))
    monkeypatch.setattr(job_kinds, "run_train_and_advise", _body)

    out = job_kinds.run_train_and_advise_fast()
    assert seen["cfg"].scenarios_n == 0
    assert seen["cfg"].entry_id == 1
    assert out == {"gw": 5, "expected_pts": 61.0}
```

- [ ] **Run it, expecting failure.** `uv run pytest -q -p no:randomly tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py`
  Expected: failures — `AttributeError: module 'gaffer.web.job_kinds' has no attribute 'run_train_and_advise_fast'`, `KeyError: 'advise-fast'`, and the allow-list assertion failing on the missing sixth kind.

- [ ] **Write the minimal implementation.** In `src/gaffer/web/routers/advice.py`, replace lines 27-39 with:

```python
def run_train_and_advise(cfg: "Config | None" = None) -> dict:
    """The job body: exactly what the launchd Thursday run does.

    ``cfg`` defaults to ``None`` — that is, to ``load_config()`` — so the
    zero-argument callers (``JOB_KINDS['advise']``, which the runner calls
    with no arguments) are untouched. The keyword exists for the one caller
    that wants the same run under a modified config: ``advise-fast``, which
    hands it ``scenarios_n=0``.
    """
    from gaffer.advise import run_advise
    from gaffer.config import load_config
    from gaffer.models.train import load_training_frame, train_all
    from gaffer.report.render import render_report
    from gaffer.tracking import latest_health

    frame, team_frame, _ = load_training_frame()
    train_all(frame, team_frame, save=True)
    advice = run_advise(cfg if cfg is not None else load_config())
    render_report(advice, model_health=latest_health())
    return {"gw": advice.gw, "expected_pts": advice.expected_pts}
```

  And add the type-checking import beside the existing imports in that file (after `import json`, before `import pandas as pd`):

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the runtime import stays lazy inside the function body
    from gaffer.config import Config
```

  In `src/gaffer/web/job_kinds.py`, replace line 1 of the docstring:

```python
"""The job kinds the browser may start (spec §5, v7c F1, v7d F1/F2).
```

  Add the wrapper after `run_snapshot_job` (line 58) and extend the table:

```python
def run_train_and_advise_fast() -> dict:
    """``gaffer advise --fast`` — the same run with the scenario sweep off.

    Not a second implementation: it is the advise kind's own body under a
    config with ``scenarios_n=0``, which is the byte-pinned pre-v4c rail
    (``tests/test_v4c_degradation.py``). Roughly five minutes cheaper on a
    Thursday when the sweep's answer is not what is being asked for.
    """
    import dataclasses

    from gaffer.config import load_config

    return run_train_and_advise(
        dataclasses.replace(load_config(), scenarios_n=0))


JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "advise-fast": run_train_and_advise_fast,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
    "snapshot": run_snapshot_job,
}
```

- [ ] **Run to pass.** `uv run pytest -q -p no:randomly tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py tests/test_web_advice.py tests/test_web_jobs.py`

- [ ] **Commit.**

```bash
git add src/gaffer/web/routers/advice.py src/gaffer/web/job_kinds.py tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py && git commit -m "$(cat <<'EOF'
feat: advise-fast job kind runs the advise body with the sweep off

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F2: `GET /api/pens`

**Files:**
- Modify `src/gaffer/web/schemas.py` (append after the `Journal` model, end of file)
- Modify `src/gaffer/web/routers/quality.py` (imports lines 8-15, append route)
- Create `tests/test_web_pens.py`

- [ ] **Write the failing test.** Create `tests/test_web_pens.py`:

```python
"""GET /api/pens: the browser renders the tracker the CLI writes.

Disk-only, exactly like /api/quality: `gaffer track-pens` reads two parquets
and joins Understat, which is not something a page load may start.
"""

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

REPORT = {
    "season": "2026-27",
    "gws": [
        {"gw": 1, "instrument": "xg_gap", "rows": 520, "covered_rows": 498,
         "team_games": 10, "component_rows": 520,
         "predicted_ep_pen_taker": 3.2, "predicted_takers": 12,
         "pens_taken": 2.0, "pens_by_first_choice": 2.0,
         "taker_hit_rate": 1.0, "pens_per_team_game": 0.2,
         "realized_pen_points": 6.4},
        {"gw": 2, "instrument": "pens_missed_only", "rows": 515,
         "covered_rows": 0, "team_games": 10, "component_rows": 515,
         "predicted_ep_pen_taker": 2.9, "predicted_takers": 12,
         "pens_taken": 1.0, "pens_by_first_choice": 0.0,
         "taker_hit_rate": 0.0, "pens_per_team_game": 0.1,
         "realized_pen_points": 3.2},
        {"gw": 3, "error": "the week would not read"},
    ],
    "season_totals": {
        "gws": 2, "instruments": ["pens_missed_only", "xg_gap"],
        "team_games": 20, "predicted_ep_pen_taker": 6.1, "pens_taken": 3.0,
        "pens_by_first_choice": 2.0, "taker_hit_rate": 0.667,
        "pens_per_team_game": 0.15, "league_pens_pg_served": 0.13,
        "realized_pen_points": 9.6},
    "notes": ["penalties counted from pens_missed only"],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # artifacts.REPORTS is the relative Path("reports"), so chdir is the whole
    # of the redirection — the same fixture tests/test_web_quality.py uses.
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_pens_without_a_report_tells_you_to_run_track_pens(client):
    response = client.get("/api/pens")
    assert response.status_code == 422
    assert "gaffer track-pens" in response.json()["detail"]


def test_pens_serves_the_season_and_every_gameweek(client, tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(REPORT))
    body = client.get("/api/pens").json()
    assert body["season"] == "2026-27"
    assert [g["gw"] for g in body["gws"]] == [1, 2, 3]
    assert body["gws"][1]["instrument"] == "pens_missed_only"
    assert body["season_totals"]["taker_hit_rate"] == 0.667
    assert body["season_totals"]["league_pens_pg_served"] == 0.13
    assert body["notes"] == ["penalties counted from pens_missed only"]


def test_an_unreadable_gameweek_is_served_as_its_error(client, tmp_path):
    """safe_gw_block writes {"gw": N, "error": ...} for one bad week; the
    endpoint must carry it rather than 500 on the missing fields."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(REPORT))
    broken = client.get("/api/pens").json()["gws"][2]
    assert broken["error"] == "the week would not read"
    assert broken["instrument"] is None
    assert broken["pens_taken"] is None


def test_a_degraded_report_with_no_gameweeks_still_serves(client, tmp_path):
    """track_pens never raises: a season with nothing on disk is an empty
    report carrying a note, and that is a 200, not an error."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(
        {"season": "", "gws": [], "season_totals": {},
         "notes": ["no live season on disk — run `gaffer refresh` first"]}))
    body = client.get("/api/pens").json()
    assert body["gws"] == []
    assert body["season_totals"]["pens_taken"] is None
    assert "gaffer refresh" in body["notes"][0]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q -p no:randomly tests/test_web_pens.py`
  Expected: every test fails with 404 — `/api/pens` is not a route yet (`assert 404 == 422`, and `.json()["detail"]` is FastAPI's "Not Found").

- [ ] **Write the minimal implementation.** Append to `src/gaffer/web/schemas.py`:

```python
class PenTrackerGw(BaseModel):
    """One finished gameweek of the penalty tracker.

    Every field but ``gw`` is optional because ``pen_tracker.safe_gw_block``
    writes one of two shapes: the full block, or ``{"gw": N, "error": ...}``
    when that week would not read. One optional-field model rather than a
    union — a union would make the client discriminate before it can render
    a row that is a row either way.
    """

    gw: int
    instrument: str | None = None
    rows: int | None = None
    covered_rows: int | None = None
    team_games: int | None = None
    component_rows: int | None = None
    predicted_ep_pen_taker: float | None = None
    predicted_takers: int | None = None
    pens_taken: float | None = None
    pens_by_first_choice: float | None = None
    taker_hit_rate: float | None = None
    pens_per_team_game: float | None = None
    realized_pen_points: float | None = None
    error: str | None = None


class PenTrackerTotals(BaseModel):
    """The season line. All optional: a report that degraded before it
    reached a single finished gameweek writes ``{}`` here."""

    gws: int | None = None
    instruments: list[str] = Field(default_factory=list)
    team_games: int | None = None
    predicted_ep_pen_taker: float | None = None
    pens_taken: float | None = None
    pens_by_first_choice: float | None = None
    taker_hit_rate: float | None = None
    pens_per_team_game: float | None = None
    league_pens_pg_served: float | None = None
    realized_pen_points: float | None = None


class PenTracker(BaseModel):
    """``reports/pen_tracker.json``, as written by ``gaffer track-pens``."""

    season: str = ""
    gws: list[PenTrackerGw] = Field(default_factory=list)
    season_totals: PenTrackerTotals = Field(default_factory=PenTrackerTotals)
    notes: list[str] = Field(default_factory=list)
```

  Replace lines 8-15 of `src/gaffer/web/routers/quality.py` with:

```python
from __future__ import annotations

import json

from fastapi import APIRouter

from gaffer.errors import GafferError
from gaffer.evaluation import load_evaluation
from gaffer.pen_tracker import tracker_path
from gaffer.web.schemas import PenTracker, Quality

router = APIRouter(prefix="/api", tags=["quality"])
```

  And append to `src/gaffer/web/routers/quality.py`:

```python
@router.get("/pens", response_model=PenTracker)
def pens() -> PenTracker:
    """The penalty tracker artifact, read off disk.

    ``json.loads(read_text())`` rather than pandas: the file is one small
    hand-written dict and going through a frame would only lose the nulls
    that ``taker_hit_rate`` deliberately carries.
    """
    path = tracker_path()
    if not path.exists():
        # The app-wide GafferError handler turns this into the 422 whose
        # sentence the empty state prints verbatim.
        raise GafferError("no pen tracker report — run gaffer track-pens")
    return PenTracker(**json.loads(path.read_text()))
```

- [ ] **Run to pass.** `uv run pytest -q -p no:randomly tests/test_web_pens.py tests/test_web_quality.py tests/test_web_app.py`

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/quality.py tests/test_web_pens.py && git commit -m "$(cat <<'EOF'
feat: serve the penalty tracker at GET /api/pens

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — F2: the `track-pens` job kind

**Files:**
- Modify `src/gaffer/web/job_kinds.py` (new wrapper after `run_train_and_advise_fast`, `JOB_KINDS`)
- Modify `tests/test_web_job_kinds.py` (the allow-list assertion, 6 → 7)
- Modify `tests/test_web_job_kinds_v7c.py` (append)

- [ ] **Write the failing test.** Replace the allow-list assertion in `tests/test_web_job_kinds.py` with:

```python
def test_exactly_the_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "advise-fast", "evaluate",
                                 "news-shadow", "refresh-data", "snapshot",
                                 "track-pens"]
```

  And append to `tests/test_web_job_kinds_v7c.py`:

```python
def test_the_track_pens_kind_is_on_the_allow_list():
    assert job_kinds.JOB_KINDS["track-pens"] is job_kinds.run_track_pens


def test_track_pens_saves_the_report_and_counts_its_gameweeks(monkeypatch,
                                                              capsys):
    """The runner captures this thread's stdout, so the printed table is what
    the browser shows as the job's progress."""
    report = {"season": "2026-27",
              "gws": [{"gw": 1, "error": "x"}, {"gw": 2, "error": "y"}],
              "season_totals": {}, "notes": []}
    saved = {}

    def _save(payload):
        saved["report"] = payload
        return "reports/pen_tracker.json"

    monkeypatch.setattr("gaffer.pen_tracker.track_pens",
                        lambda season=None: report)
    monkeypatch.setattr("gaffer.pen_tracker.save_tracker", _save)
    assert job_kinds.run_track_pens() == {"gws": 2}
    assert saved["report"] is report
    out = capsys.readouterr().out
    assert "Penalty tracker" in out
    assert "reports/pen_tracker.json" in out


def test_a_degraded_pen_report_is_still_a_finished_job(monkeypatch):
    """track_pens never raises — a season with nothing on disk is an empty
    report with a note, and the job must bank it as zero gameweeks."""
    monkeypatch.setattr(
        "gaffer.pen_tracker.track_pens",
        lambda season=None: {"season": "", "gws": [], "season_totals": {},
                             "notes": ["no live season on disk"]})
    monkeypatch.setattr("gaffer.pen_tracker.save_tracker",
                        lambda payload: "reports/pen_tracker.json")
    assert job_kinds.run_track_pens() == {"gws": 0}


def test_the_track_pens_wrapper_imports_lazily():
    import inspect

    source = inspect.getsource(job_kinds)
    assert "from gaffer.pen_tracker import" not in source.split("def ")[0]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q -p no:randomly tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py`
  Expected: `AttributeError: module 'gaffer.web.job_kinds' has no attribute 'run_track_pens'` and the allow-list assertion failing on the missing seventh kind.

- [ ] **Write the minimal implementation.** In `src/gaffer/web/job_kinds.py`, add after `run_train_and_advise_fast` and extend the table:

```python
def run_track_pens() -> dict:
    """``gaffer track-pens`` — the standing penalty-term report (v7d F2).

    ``track_pens`` never raises: a missing live season comes back as an empty
    report carrying a note, which is a finished job with zero gameweeks, not
    a failed one. The printed table is ``format_tracker``'s, character for
    character the same thing the CLI prints.
    """
    from gaffer.pen_tracker import (format_tracker, save_tracker,
                                    track_pens)

    report = track_pens()
    path = save_tracker(report)
    print(format_tracker(report))
    print(f"Wrote {path}")
    return {"gws": len(report.get("gws", []))}


JOB_KINDS: dict[str, Callable[[], Any]] = {
    "advise": run_train_and_advise,
    "advise-fast": run_train_and_advise_fast,
    "evaluate": run_evaluate,
    "refresh-data": run_data_refresh,
    "news-shadow": run_news_shadow,
    "snapshot": run_snapshot_job,
    "track-pens": run_track_pens,
}
```

- [ ] **Run to pass.** `uv run pytest -q -p no:randomly tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py tests/test_web_jobs_api.py`

- [ ] **Commit.**

```bash
git add src/gaffer/web/job_kinds.py tests/test_web_job_kinds.py tests/test_web_job_kinds_v7c.py && git commit -m "$(cat <<'EOF'
feat: track-pens job kind so the browser can rebuild the tracker

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — F1/F2/F3: the frontend job union and the pen types

**Files:**
- Modify `frontend/src/types.ts` (lines 570-580, `JOB_KINDS` and `JOB_KIND_LABEL`; append the pen types at end of file)
- Modify `frontend/src/types.test.ts` (lines 5-8)

All three new kinds land here at once, so `types.test.ts` moves 4 → 7 in one edit and never has to move again this cycle. The buttons follow in Tasks 6 and 8; a kind in the union with no button is inert.

- [ ] **Write the failing test.** Replace lines 5-8 of `frontend/src/types.test.ts` with:

```ts
  it('lists exactly the seven kinds the backend allows', () => {
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens'])
  })

  it('labels every kind for a button', () => {
    for (const kind of JOB_KINDS) {
      expect(JOB_KIND_LABEL[kind].length).toBeGreaterThan(0)
    }
  })
```

  And replace line 2 of that file with:

```ts
import {
  JOB_KINDS, JOB_KIND_LABEL, type JobKind, type JobRunView,
} from './types'
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/types.test.ts`
  Expected: failure — the array is still `['advise', 'evaluate', 'refresh-data', 'news-shadow']`, so `toEqual` reports the three missing kinds.

- [ ] **Write the minimal implementation.** Replace lines 570-580 of `frontend/src/types.ts` with:

```ts
export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens'] as const

export type JobKind = typeof JOB_KINDS[number]

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
}
```

  And append to `frontend/src/types.ts`:

```ts
/**
 * One gameweek of `reports/pen_tracker.json`. Everything but `gw` is optional
 * because a week that would not read is written as `{gw, error}` — the same
 * one-model-two-shapes contract the server's `PenTrackerGw` carries.
 */
export interface PenTrackerGw {
  gw: number
  instrument?: string | null
  rows?: number | null
  covered_rows?: number | null
  team_games?: number | null
  component_rows?: number | null
  predicted_ep_pen_taker?: number | null
  predicted_takers?: number | null
  pens_taken?: number | null
  pens_by_first_choice?: number | null
  taker_hit_rate?: number | null
  pens_per_team_game?: number | null
  realized_pen_points?: number | null
  error?: string | null
}

export interface PenTrackerTotals {
  gws?: number | null
  instruments?: string[]
  team_games?: number | null
  predicted_ep_pen_taker?: number | null
  pens_taken?: number | null
  pens_by_first_choice?: number | null
  taker_hit_rate?: number | null
  pens_per_team_game?: number | null
  league_pens_pg_served?: number | null
  realized_pen_points?: number | null
}

export interface PenTrackerData {
  season: string
  gws: PenTrackerGw[]
  season_totals: PenTrackerTotals
  notes: string[]
}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/types.test.ts`

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/types.test.ts && git commit -m "$(cat <<'EOF'
feat: three new job kinds and the pen tracker types

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — F1: the Fast advise button in the This Week header

**Files:**
- Modify `frontend/src/hubs/ThisWeek.tsx` (line 117, the `PageHeader` `action`)
- Modify `frontend/src/hubs/ThisWeek.test.tsx` (append inside the existing top-level `describe`, before its closing `})`)

- [ ] **Write the failing test.** Append to the `describe` block in `frontend/src/hubs/ThisWeek.test.tsx`:

```tsx
  it('offers the fast run beside the full one', async () => {
    render(<MemoryRouter><ThisWeek /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Run advise' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fast advise' }))
      .toBeInTheDocument()
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx`
  Expected: failure — `Unable to find an accessible element with the role "button" and name "Fast advise"`.

- [ ] **Write the minimal implementation.** In `frontend/src/hubs/ThisWeek.tsx`, replace line 117 with:

```tsx
        action={(
          // Two runs, one lane: the full solve and the same solve with the
          // scenario sweep off (~5 min cheaper). Both reload this page.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="advise" onDone={load} />
            <JobButton kind="advise-fast" onDone={load} />
          </div>
        )}
```

  The empty-state branch (line 68) keeps its single `advise` button unchanged: nothing has been solved there, so a fast re-solve is not the offer to make.

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/ThisWeek.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/hubs/ThisWeek.tsx frontend/src/hubs/ThisWeek.test.tsx && git commit -m "$(cat <<'EOF'
feat: Fast advise button in the This Week header

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — F2: the penalty card in the Quality tab

**Files:**
- Modify `frontend/src/hubs/model/QualityTab.tsx` (imports lines 6-11, new `PensSection` before the default export, render at line 356-365)
- Modify `frontend/src/hubs/model/QualityTab.test.tsx` (append a new `describe` at end of file)

- [ ] **Write the failing test.** Append to `frontend/src/hubs/model/QualityTab.test.tsx`:

```tsx
// Gameweeks 11-13, deliberately clear of the news-shadow fixture's GW3/GW4:
// both sections render "GW{n}" cells into the same document.
const pens = {
  season: '2026-27',
  gws: [
    { gw: 11, instrument: 'xg_gap', rows: 520, covered_rows: 498,
      team_games: 10, component_rows: 520, predicted_ep_pen_taker: 3.2,
      predicted_takers: 12, pens_taken: 2, pens_by_first_choice: 2,
      taker_hit_rate: 1, pens_per_team_game: 0.2, realized_pen_points: 6.4 },
    { gw: 12, instrument: 'pens_missed_only', rows: 515, covered_rows: 0,
      team_games: 10, component_rows: 515, predicted_ep_pen_taker: 2.9,
      predicted_takers: 12, pens_taken: 1, pens_by_first_choice: 0,
      taker_hit_rate: 0, pens_per_team_game: 0.1, realized_pen_points: 3.2 },
    { gw: 13, error: 'the week would not read' },
  ],
  season_totals: {
    gws: 2, instruments: ['pens_missed_only', 'xg_gap'], team_games: 20,
    predicted_ep_pen_taker: 6.1, pens_taken: 3, pens_by_first_choice: 2,
    taker_hit_rate: 0.667, pens_per_team_game: 0.15,
    league_pens_pg_served: 0.13, realized_pen_points: 9.6,
  },
  notes: ['penalties counted from pens_missed only'],
}

function routed(penResponse: unknown, reject = false) {
  return (path: string) => {
    if (path !== '/api/pens') return Promise.resolve(payload)
    return reject ? Promise.reject(penResponse) : Promise.resolve(penResponse)
  }
}

describe('QualityTab penalty card', () => {
  it('states the season line', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByRole('heading',
                                   { name: /penalty term — 2026-27/i }))
      .toBeInTheDocument()
    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('0.150 vs 0.13 served')).toBeInTheDocument()
    expect(screen.getByText('6.1 / 9.6')).toBeInTheDocument()
  })

  it('flags a missed-only week as a floor', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText('floor')).toBeInTheDocument()
    expect(screen.getByText('xg_gap')).toBeInTheDocument()
  })

  it('renders a broken week as an unreadable row', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    const cell = await screen.findByTitle('the week would not read')
    expect(cell).toHaveTextContent('unreadable')
    expect(screen.getByText('GW13')).toBeInTheDocument()
  })

  it('prints the report notes as a footer', async () => {
    apiGet.mockImplementation(routed(pens))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/counted from pens_missed only/))
      .toBeInTheDocument()
  })

  it('names the command when no tracker has been written', async () => {
    apiGet.mockImplementation(routed(
      new FakeApiError(422, 'no pen tracker report — run gaffer track-pens'),
      true))
    render(<MemoryRouter><QualityTab /></MemoryRouter>)
    expect(await screen.findByText(/no pen tracker report/))
      .toBeInTheDocument()
    expect(screen.getByText('gaffer track-pens')).toBeInTheDocument()
  })
})
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/model/QualityTab.test.tsx`
  Expected: the five new tests fail — no heading matching `/penalty term/i`, no `floor` text, no `gaffer track-pens` empty state. The eight existing tests still pass (their blanket `mockResolvedValue(payload)` reaches `/api/pens` too, and `PensSection` renders nothing for a payload with no `gws` array).

- [ ] **Write the minimal implementation.** In `frontend/src/hubs/model/QualityTab.tsx`, replace the import block (lines 6-11) with:

```tsx
import { ApiError, apiGet } from '../../api/client'
import {
  type Column, Badge, Card, DataTable, EmptyState, Loading, Stat, fmtNum,
  fmtPct,
} from '../../kit'
import type {
  BenchmarkEvaluation, CurrentEvaluation, DecompositionData, HeadMetrics,
  NewsShadowData, PenTrackerData, PenTrackerGw, QualityData, StratifiedTable,
} from '../../types'
```

  Add before `export default function QualityTab()` (line 324):

```tsx
// The instrument is the first thing to read on a pen row: an xg-gap week
// counts penalties, a pens_missed_only week can only see the ones that were
// missed, so every number beside it is a floor rather than a count.
function InstrumentCell({ row }: { row: PenTrackerGw }) {
  if (row.error) {
    return (
      <span className="text-text-muted" title={row.error}>unreadable</span>
    )
  }
  if (row.instrument === 'pens_missed_only') {
    return (
      <Badge variant="negative"
             title="counted from missed penalties only — converted spot kicks
                    are invisible, so every count on this row is a floor">
        floor
      </Badge>
    )
  }
  return <Badge variant="info">{row.instrument ?? '—'}</Badge>
}

const PEN_COLUMNS: Column<PenTrackerGw>[] = [
  { key: 'gw', header: 'GW', primary: true, value: (r) => r.gw,
    render: (r) => (
      <span className={r.error ? 'num text-text-muted' : 'num text-text'}>
        GW{r.gw}
      </span>
    ) },
  { key: 'instrument', header: 'Instrument', primary: true,
    value: (r) => (r.error ? 'unreadable' : r.instrument ?? '—'),
    render: (r) => <InstrumentCell row={r} /> },
  { key: 'covered_rows', header: 'Covered', numeric: true,
    value: (r) => r.covered_rows ?? null,
    render: (r) => fmtNum(r.covered_rows, 0) },
  { key: 'pens_taken', header: 'Pens', primary: true, numeric: true,
    value: (r) => r.pens_taken ?? null,
    render: (r) => fmtNum(r.pens_taken) },
  { key: 'taker_hit_rate', header: 'Hit rate', numeric: true,
    value: (r) => r.taker_hit_rate ?? null,
    render: (r) => fmtPct(r.taker_hit_rate) },
]

/**
 * The v6 penalty term, measured forward. Its own fetch, like every other
 * section here: the tracker is a separate artifact with its own "not written
 * yet" state, and folding it into /api/quality would make one missing file
 * blank the other's page.
 */
function PensSection() {
  const [data, setData] = useState<PenTrackerData | null>(null)
  const [empty, setEmpty] = useState<string | null>(null)

  useEffect(() => {
    apiGet<PenTrackerData>('/api/pens').then(setData).catch((e: Error) => {
      // 422 is the ordinary "nobody has run it yet"; anything else is a
      // server that cannot answer, and this card is not the place to shout
      // about it — the page above still has its numbers.
      if (e instanceof ApiError && e.status === 422) setEmpty(e.message)
    })
  }, [])

  if (empty) {
    return (
      <EmptyState
        title="No penalty tracker yet"
        detail={empty}
        action="gaffer track-pens"
      />
    )
  }
  // A payload without a gws array is not a tracker: render nothing rather
  // than crash the tab on an artifact half-written by an older version.
  if (!data || !Array.isArray(data.gws)) return null

  const totals = data.season_totals ?? {}
  return (
    <Card title={`Penalty term — ${data.season || 'season unknown'}`}
          className="mt-4">
      <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Pens taken" value={fmtNum(totals.pens_taken)} />
        <Stat label="Taker hit rate" value={fmtPct(totals.taker_hit_rate)} />
        <Stat
          label="Pens / team-game"
          value={`${fmtNum(totals.pens_per_team_game, 3)} vs `
            + `${fmtNum(totals.league_pens_pg_served, 2)} served`}
        />
        <Stat
          label="Predicted EP / realized"
          value={`${fmtNum(totals.predicted_ep_pen_taker)} / `
            + `${fmtNum(totals.realized_pen_points)}`}
        />
      </div>
      <DataTable
        columns={PEN_COLUMNS}
        rows={data.gws}
        rowKey={(r) => r.gw}
        rowLabel={(r) => `GW${r.gw}`}
        initialSort="gw"
        empty={<p className="text-text-muted">No finished gameweek yet.</p>}
      />
      {(data.notes ?? []).map((note) => (
        <p key={note} className="mt-2 text-text-faint">{note}</p>
      ))}
    </Card>
  )
}
```

  And replace the `news_shadow` line of the default export's return (lines 362-363) with:

```tsx
      {data.news_shadow && data.news_shadow.rows > 0
        && <NewsShadowSection shadow={data.news_shadow} />}
      <PensSection />
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/model/QualityTab.test.tsx src/hubs/Model.test.tsx src/hubs/responsive.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/hubs/model/QualityTab.tsx frontend/src/hubs/model/QualityTab.test.tsx && git commit -m "$(cat <<'EOF'
feat: penalty tracker card in the Model quality tab

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — F2/F3: the Track pens and Snapshot buttons in the Model header

**Files:**
- Modify `frontend/src/hubs/Model.tsx` (lines 29-36, the `PageHeader` `action`)
- Modify `frontend/src/hubs/Model.test.tsx` (append inside the existing `describe`, before its closing `})`)

- [ ] **Write the failing test.** Append to the `describe('Model hub')` block in `frontend/src/hubs/Model.test.tsx`:

```tsx
  it('offers the track-pens and snapshot jobs too', () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'Track pens' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Snapshot news' }))
      .toBeInTheDocument()
  })

  it('refetches the quality tab after a track-pens run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await screen.findByText('quality panel')
    const before = mounts.quality
    await act(async () => { jobs['track-pens']?.() })
    expect(mounts.quality).toBeGreaterThan(before)
  })

  it('refetches the health tab after a snapshot run', async () => {
    render(<MemoryRouter><Model /></MemoryRouter>)
    await userEvent.click(screen.getByRole('tab', { name: 'Health' }))
    await screen.findByText('health panel')
    const before = mounts.health
    await act(async () => { jobs.snapshot?.() })
    expect(mounts.health).toBeGreaterThan(before)
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/Model.test.tsx`
  Expected: failure — no button named "Track pens", and `jobs['track-pens']` / `jobs.snapshot` are `undefined` so neither mount count moves.

- [ ] **Write the minimal implementation.** In `frontend/src/hubs/Model.tsx`, replace lines 29-36 with:

```tsx
        action={(
          // The header is the hub's one control lane: every job that rewrites
          // something a tab under it renders lives here, and each says which
          // tab it invalidates. Track pens rewrites the quality artifact's
          // neighbour; snapshot moves what Health grades.
          <div className="flex flex-wrap gap-2">
            <JobButton kind="evaluate" label="Evaluate"
                       onDone={reloadQuality} />
            <JobButton kind="track-pens" label="Track pens"
                       onDone={reloadQuality} />
            <JobButton kind="refresh-data" label="Refresh data"
                       onDone={reloadHealth} />
            <JobButton kind="snapshot" label="Snapshot news"
                       onDone={reloadHealth} />
          </div>
        )}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/Model.test.tsx src/hubs/responsive.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/hubs/Model.tsx frontend/src/hubs/Model.test.tsx && git commit -m "$(cat <<'EOF'
feat: Track pens and Snapshot buttons in the Model header

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — F4: `Card` gains a heading slot

**Files:**
- Modify `frontend/src/kit/Card.tsx` (props lines 14-20, body lines 27-40)
- Modify `frontend/src/kit/Card.test.tsx` (append inside the existing `describe`)

- [ ] **Write the failing test.** Append to the `describe('Card')` block in `frontend/src/kit/Card.test.tsx`:

```tsx
  it('renders rich heading content in place of the title string', () => {
    render(
      <Card title="Saka" heading={<button type="button">Saka</button>}>
        <p>inside</p>
      </Card>,
    )
    const heading = screen.getByRole('heading', { level: 3 })
    expect(within(heading).getByRole('button', { name: 'Saka' }))
      .toBeInTheDocument()
  })

  it('keeps the h3 and its size class for a heading', () => {
    render(
      <Card heading={<span>Saka</span>} titleSize="lg"><p>inside</p></Card>,
    )
    const heading = screen.getByRole('heading', { level: 3, name: 'Saka' })
    expect(heading).toHaveClass('text-lg')
    expect(heading).not.toHaveClass('label')
  })

  it('opens the header row for a heading with no title', () => {
    render(<Card heading={<span>Saka</span>}><p>inside</p></Card>)
    expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument()
  })
```

  And replace line 1 of that file with:

```tsx
import { render, screen, within } from '@testing-library/react'
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/kit/Card.test.tsx`
  Expected: failure — `Card` has no `heading` prop, so TypeScript-in-vitest passes the unknown prop through and the `h3` renders "Saka" as plain text; `within(heading).getByRole('button')` finds nothing, and the heading-with-no-title case renders no header at all.

- [ ] **Write the minimal implementation.** Replace `frontend/src/kit/Card.tsx` lines 14-44 with:

```tsx
export interface CardProps {
  title?: string
  /**
   * Rich heading content. When given it is what the `h3` renders, so a card
   * *about* something can carry that thing's own control — ComparePanel's
   * click-to-explain player name — rather than a copy of its name as text.
   * `title` stays the string form of the same thing and may be passed with
   * it; `heading` wins visually, and the `h3` (and its `titleSize` class) is
   * the same element either way.
   */
  heading?: ReactNode
  titleSize?: 'sm' | 'lg'
  action?: ReactNode
  children: ReactNode
  className?: string
}

const TITLE_CLASS = {
  sm: 'label',
  lg: 'text-lg font-medium text-text',
} as const

export default function Card({
  title, heading, titleSize = 'sm', action, children, className,
}: CardProps) {
  const shown = heading ?? title
  return (
    <section
      className={`rounded-card border border-border bg-card ${className ?? ''}`}
    >
      {(shown || action) && (
        <header className="flex items-center justify-between gap-3 border-b
                           border-divider px-4 py-3">
          {shown && <h3 className={TITLE_CLASS[titleSize]}>{shown}</h3>}
          {action}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/kit/Card.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/kit/Card.tsx frontend/src/kit/Card.test.tsx && git commit -m "$(cat <<'EOF'
feat: Card takes a rich heading slot

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — F4: the missing `PlayerName` test

**Files:**
- Create `frontend/src/kit/PlayerName.test.tsx`

`PlayerName` renders `ExplainModal` on click, and that modal fetches `/api/players/{code}/explain` through `api/client`. The mock returns a promise that never settles, so the modal stays in its own loading state — which is all this test needs: that the dialog opened and that it asked for the right player.

- [ ] **Write the failing test.** Create `frontend/src/kit/PlayerName.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import PlayerName from './PlayerName'

// vi.mock's factory is hoisted above the file body, so the spy is hoisted
// with it (the ExplainModal.test.tsx pattern).
const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))
vi.mock('../api/client', () => ({
  ApiError: class extends Error {},
  apiGet: (path: string) => apiGet(path),
  apiPost: vi.fn(),
}))

beforeEach(() => {
  apiGet.mockReset()
  // Never settles: the modal's loading state is enough to prove it opened,
  // and ExplainModal's own suite covers what it does with a payload.
  apiGet.mockReturnValue(new Promise(() => {}))
})

describe('PlayerName', () => {
  it('renders the name as the control', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.getByRole('button', { name: 'Salah' })).toBeInTheDocument()
  })

  it('carries the position dot when the row has one', () => {
    render(<PlayerName code={9} name="Salah" pos="MID" />)
    expect(screen.getByTestId('pos-dot-MID')).toBeInTheDocument()
  })

  it('leaves the dot out when the row carries no position', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.queryByTestId('pos-dot-MID')).toBeNull()
  })

  it('stays closed until it is clicked', () => {
    render(<PlayerName code={9} name="Salah" />)
    expect(screen.queryByTestId('modal-backdrop')).toBeNull()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('opens the explain modal for its own player', async () => {
    render(<PlayerName code={9} name="Salah" />)
    await userEvent.click(screen.getByRole('button', { name: 'Salah' }))
    expect(await screen.findByRole('dialog',
                                   { name: 'Expected points explained' }))
      .toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/api/players/9/explain')
  })

  it("closes again on the modal's own control", async () => {
    render(<PlayerName code={9} name="Salah" />)
    await userEvent.click(screen.getByRole('button', { name: 'Salah' }))
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByTestId('modal-backdrop')).toBeNull()
  })
})
```

- [ ] **Run it.** `cd frontend && npx vitest run src/kit/PlayerName.test.tsx`
  Expected: **6 passed**. This task is the one deliberate exception to red-first in the plan — it is a coverage backfill over a component that already behaves correctly, so the failing state it guards against is a future regression, not a present one. Before this file existed the whole suite passed with `PlayerName` untested, which is precisely the hole being closed. If any test fails now, that is a real defect in `PlayerName` and it is fixed here.

- [ ] **Write the minimal implementation.** None: `frontend/src/kit/PlayerName.tsx` is unchanged. The `pos !== undefined` guard at line 24 and the `open && <ExplainModal .../>` at line 33 are exactly what the tests describe.

- [ ] **Run to pass.** `cd frontend && npx vitest run src/kit/PlayerName.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/kit/PlayerName.test.tsx && git commit -m "$(cat <<'EOF'
test: cover PlayerName, the kit's last untested component

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — F4: player names as controls in Compare and the explorer

**Files:**
- Modify `frontend/src/hubs/players/ComparePanel.tsx` (imports line 7, card line 94)
- Modify `frontend/src/hubs/players/ComparePanel.test.tsx` (append inside the existing `describe`)
- Modify `frontend/src/hubs/Players.tsx` (imports lines 5-8, name column line ~64)
- Modify `frontend/src/hubs/Players.test.tsx` (append inside the existing `describe`)

- [ ] **Write the failing test.** Append to the `describe('ComparePanel')` block in `frontend/src/hubs/players/ComparePanel.test.tsx`:

```tsx
  it('makes the card heading the click-to-explain name', async () => {
    render(<ComparePanel gw={5} players={PLAYERS} />)
    const card = await screen.findByTestId(`compare-${PLAYERS[0].code}`)
    const heading = within(card).getByRole('heading',
                                           { name: PLAYERS[0].name })
    expect(within(heading).getByRole('button', { name: PLAYERS[0].name }))
      .toBeInTheDocument()
  })
```

  Append to the `describe('Players hub')` block in `frontend/src/hubs/Players.test.tsx`:

```tsx
  it('makes every explorer name the click-to-explain control', async () => {
    render(<MemoryRouter><Players /></MemoryRouter>)
    expect(await screen.findByRole('button', { name: 'Salah' }))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saka' })).toBeInTheDocument()
  })
```

  (`within` is already imported in both test files.)

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/players/ComparePanel.test.tsx src/hubs/Players.test.tsx`
  Expected: both new tests fail — the compare heading is a plain string and the explorer's name cell is plain text, so no `button` with either name exists.

- [ ] **Write the minimal implementation.** In `frontend/src/hubs/players/ComparePanel.tsx`, replace line 7 with:

```tsx
import {
  Badge, Card, EmptyState, PlayerName, PosBadge, Sparkline, fmtNum,
} from '../../kit'
```

  and replace lines 94-95 with:

```tsx
              {/* The name is the control, not a label of one: the same
                  click-to-explain affordance every other page gives it.
                  PosBadge stays in the action slot, so no dot here. */}
              <Card
                heading={<PlayerName code={player.code} name={player.name} />}
                titleSize="lg"
                action={<PosBadge pos={player.position} />}
              >
```

  In `frontend/src/hubs/Players.tsx`, replace the import block (lines 5-8) with:

```tsx
import {
  type Column, Card, DataTable, EmptyState, Loading, PageHeader, PlayerName,
  PosBadge, Sparkline, fmtNum, posColor,
} from '../kit'
```

  and replace the name column with:

```tsx
    { key: 'name', header: 'Player', primary: true, value: (r) => r.name,
      // No pos dot: the explorer has its own position column, and two
      // statements of the same fact in one row is one too many.
      render: (r) => <PlayerName code={r.code} name={r.name} /> },
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/players/ComparePanel.test.tsx src/hubs/Players.test.tsx src/hubs/responsive.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/hubs/players/ComparePanel.tsx frontend/src/hubs/players/ComparePanel.test.tsx frontend/src/hubs/Players.tsx frontend/src/hubs/Players.test.tsx && git commit -m "$(cat <<'EOF'
feat: player names are the explain control in Compare and the explorer

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — F5: the light palette

**Files:**
- Modify `frontend/src/styles/theme.css` (append after the `@theme` block, before `html, body, #root`)
- Modify `frontend/src/styles/theme.test.ts` (append a new `describe`)

Dark declarations keep their exact spelling — the existing assertions are containment checks over the whole file, and the light values live in their own blocks.

- [ ] **Write the failing test.** Append to `frontend/src/styles/theme.test.ts`:

```ts
const TOKENS = [
  '--color-base', '--color-card', '--color-border', '--color-divider',
  '--color-text', '--color-text-secondary', '--color-text-muted',
  '--color-text-faint', '--color-sage', '--color-rust', '--color-info',
  '--color-pos-gkp', '--color-pos-def', '--color-pos-mid', '--color-pos-fwd',
]

/** The declarations between `opener` and the first `}` that follows it. */
function block(opener: string): string {
  const start = css.indexOf(opener)
  expect(start, `${opener} missing`).toBeGreaterThan(-1)
  const from = start + opener.length
  return css.slice(from, css.indexOf('}', from))
}

function valueOf(source: string, token: string): string {
  const found = new RegExp(`${token}:\\s*(#[0-9a-f]{6});`).exec(source)
  expect(found, `${token} has no hex value`).not.toBeNull()
  return found![1]
}

// WCAG 2.1 relative luminance and contrast, implemented here rather than
// pulled in: it is nine lines, and a theme test that needs a dependency to
// say whether the text is readable is a test nobody will keep running.
function channel(value: number): number {
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16)
  return 0.2126 * channel(((n >> 16) & 255) / 255)
    + 0.7152 * channel(((n >> 8) & 255) / 255)
    + 0.0722 * channel((n & 255) / 255)
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('light theme', () => {
  it('overrides every token exactly once for an explicit light choice', () => {
    const light = block('[data-theme="light"] {')
    for (const token of TOKENS) {
      expect(light.split(`${token}:`).length - 1,
             `${token} in [data-theme="light"]`).toBe(1)
    }
  })

  it('mirrors the same tokens under a light system preference', () => {
    expect(css).toContain('@media (prefers-color-scheme: light)')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(mirror.split(`${token}:`).length - 1,
             `${token} in the system mirror`).toBe(1)
    }
  })

  it('lets an explicit dark choice out of the system mirror', () => {
    // Without the :not() guard a user who chose dark on a light-set laptop
    // would get the light palette back the moment the media query matched.
    expect(css).toContain(':root:not([data-theme="dark"])')
  })

  it('agrees with itself: the mirror is the light block', () => {
    const light = block('[data-theme="light"] {')
    const mirror = block(':root:not([data-theme="dark"]) {')
    for (const token of TOKENS) {
      expect(valueOf(mirror, token), token).toBe(valueOf(light, token))
    }
  })

  it('holds 4.5:1 for every text token on a light card', () => {
    const light = block('[data-theme="light"] {')
    const card = valueOf(light, '--color-card')
    for (const token of ['--color-text', '--color-text-secondary',
      '--color-text-muted']) {
      expect(contrast(valueOf(light, token), card),
             `${token} on card`).toBeGreaterThanOrEqual(4.5)
    }
  })
})
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/styles/theme.test.ts`
  Expected: the five new tests fail at `expect(start, '[data-theme="light"] { missing').toBeGreaterThan(-1)` — the block does not exist. The four existing dark assertions still pass.

- [ ] **Write the minimal implementation.** In `frontend/src/styles/theme.css`, replace the comment above `@theme` and insert the two blocks after the `@theme` block's closing brace (line 30), before `html, body, #root`:

```css
/* The locked design language (spec §2). The @theme block is the dark
   palette and the source of every token name; light is an override of the
   same names, so no component knows which one is on. */
```

```css
/* An explicit light choice: `data-theme="light"` on <html>, set by
   kit/useTheme.ts and by the boot script in index.html. Position hues are
   darkened rather than re-hued — a MID is violet in both themes, because
   the hue is identity and identity does not change with the lights. */
[data-theme="light"] {
  --color-base: #f4f5f7;
  --color-card: #ffffff;
  --color-border: #d9dce2;
  --color-divider: #e7e9ee;
  --color-text: #191c22;
  --color-text-secondary: #3d434e;
  --color-text-muted: #6b7280;
  --color-text-faint: #9aa1ab;
  --color-sage: #3f7a44;
  --color-rust: #b0532f;
  --color-info: #2f6b96;
  --color-pos-gkp: #96731f;
  --color-pos-def: #2867a5;
  --color-pos-mid: #6f51b8;
  --color-pos-fwd: #b04f78;
}

/* "System" is the absence of the attribute, so the OS preference speaks
   here. The :not() guard is what keeps an explicit dark choice dark on a
   light-set machine. */
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --color-base: #f4f5f7;
    --color-card: #ffffff;
    --color-border: #d9dce2;
    --color-divider: #e7e9ee;
    --color-text: #191c22;
    --color-text-secondary: #3d434e;
    --color-text-muted: #6b7280;
    --color-text-faint: #9aa1ab;
    --color-sage: #3f7a44;
    --color-rust: #b0532f;
    --color-info: #2f6b96;
    --color-pos-gkp: #96731f;
    --color-pos-def: #2867a5;
    --color-pos-mid: #6f51b8;
    --color-pos-fwd: #b04f78;
  }
}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/styles/theme.test.ts`

- [ ] **Commit.**

```bash
git add frontend/src/styles/theme.css frontend/src/styles/theme.test.ts && git commit -m "$(cat <<'EOF'
feat: light palette as a token override block

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 13 — F5: the theme preference hook

**Files:**
- Create `frontend/src/kit/useTheme.ts`
- Create `frontend/src/kit/useTheme.test.ts`

- [ ] **Write the failing test.** Create `frontend/src/kit/useTheme.test.ts`:

```ts
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { THEMES, THEME_KEY, applyTheme, readTheme, useTheme } from './useTheme'

function hostileStorage() {
  vi.stubGlobal('localStorage', {
    getItem() { throw new Error('storage denied') },
    setItem() { throw new Error('storage denied') },
  })
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

afterEach(() => { vi.unstubAllGlobals() })

describe('useTheme', () => {
  it('offers the three states in a stable order', () => {
    expect(THEMES).toEqual(['system', 'dark', 'light'])
  })

  it('defaults to following the system', () => {
    expect(readTheme()).toBe('system')
  })

  it('reads a stored choice', () => {
    localStorage.setItem(THEME_KEY, 'light')
    expect(readTheme()).toBe('light')
  })

  it('ignores a stored value that is not a theme', () => {
    localStorage.setItem(THEME_KEY, 'neon')
    expect(readTheme()).toBe('system')
  })

  // Safari's private mode throws on both ends of localStorage. A theme
  // preference is not worth a white screen.
  it('follows the system when storage refuses to be read', () => {
    hostileStorage()
    expect(readTheme()).toBe('system')
  })

  it('stamps an explicit choice on the document element', () => {
    applyTheme('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('removes the attribute for system, which is its whole meaning', () => {
    applyTheme('dark')
    applyTheme('system')
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('persists and applies what the hook is given', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current[0]).toBe('system')
    act(() => { result.current[1]('dark') })
    expect(result.current[0]).toBe('dark')
    expect(localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('still switches when storage refuses the write', () => {
    hostileStorage()
    const { result } = renderHook(() => useTheme())
    act(() => { result.current[1]('light') })
    expect(result.current[0]).toBe('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })
})
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/kit/useTheme.test.ts`
  Expected: collection error — `Failed to resolve import "./useTheme"`.

- [ ] **Write the minimal implementation.** Create `frontend/src/kit/useTheme.ts`:

```ts
import { useCallback, useEffect, useState } from 'react'

/**
 * Three states, not two. "system" is the absence of a choice — no attribute
 * on <html>, so theme.css's `prefers-color-scheme` mirror decides — and it
 * is what a fresh install gets. The other two are the user overruling their
 * machine, which is the whole reason a toggle exists.
 */
export type Theme = 'system' | 'dark' | 'light'

export const THEMES: Theme[] = ['system', 'dark', 'light']

export const THEME_KEY = 'gaffer-theme'
/** Shared verbatim with the boot script in index.html. */

/** The stored choice, or "system" — including when storage itself throws. */
export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    return stored === 'dark' || stored === 'light' ? stored : 'system'
  } catch {
    // Private mode, or a browser configured to refuse site data. Following
    // the system is a perfectly good answer to that.
    return 'system'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

/** The current theme and a setter that persists it. */
export function useTheme(): [Theme, (next: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(readTheme)

  useEffect(() => { applyTheme(theme) }, [theme])

  const choose = useCallback((next: Theme) => {
    setTheme(next)
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      // The choice still applies to this tab; it just will not outlive it.
    }
  }, [])

  return [theme, choose]
}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/kit/useTheme.test.ts`

- [ ] **Commit.**

```bash
git add frontend/src/kit/useTheme.ts frontend/src/kit/useTheme.test.ts && git commit -m "$(cat <<'EOF'
feat: three-state theme preference behind try/catch storage

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 14 — F5: the theme toggle

**Files:**
- Create `frontend/src/kit/ThemeToggle.tsx`
- Create `frontend/src/kit/ThemeToggle.test.tsx`
- Modify `frontend/src/kit/index.ts` (append exports)
- Modify `frontend/src/kit/index.test.ts` (append)

- [ ] **Write the failing test.** Create `frontend/src/kit/ThemeToggle.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import ThemeToggle from './ThemeToggle'
import { THEME_KEY } from './useTheme'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeToggle', () => {
  it('offers all three states as one labelled group', () => {
    render(<ThemeToggle />)
    const group = screen.getByRole('group', { name: 'Theme' })
    expect(group).toBeInTheDocument()
    for (const name of ['System', 'Dark', 'Light']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument()
    }
  })

  it('marks the current state as pressed', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'System' }))
      .toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Dark' }))
      .toHaveAttribute('aria-pressed', 'false')
  })

  it('applies and persists the state it is clicked into', async () => {
    render(<ThemeToggle />)
    await userEvent.click(screen.getByRole('button', { name: 'Light' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    expect(localStorage.getItem(THEME_KEY)).toBe('light')
    expect(screen.getByRole('button', { name: 'Light' }))
      .toHaveAttribute('aria-pressed', 'true')
  })

  it('goes back to system, which clears the attribute', async () => {
    render(<ThemeToggle />)
    await userEvent.click(screen.getByRole('button', { name: 'Dark' }))
    await userEvent.click(screen.getByRole('button', { name: 'System' }))
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })

  it('is one icon-only cycling control when compact', () => {
    render(<ThemeToggle compact />)
    expect(screen.getByRole('button', { name: 'Theme: system' }))
      .toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Light' })).toBeNull()
  })

  it('cycles system to dark to light and round again', async () => {
    render(<ThemeToggle compact />)
    await userEvent.click(screen.getByRole('button', { name: 'Theme: system' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    await userEvent.click(screen.getByRole('button', { name: 'Theme: dark' }))
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
    await userEvent.click(screen.getByRole('button', { name: 'Theme: light' }))
    expect(document.documentElement.getAttribute('data-theme')).toBeNull()
  })
})
```

  And append to `frontend/src/kit/index.test.ts`, inside the existing `describe`:

```ts
  it('exports the theme controls', () => {
    expect(typeof kit.ThemeToggle).toBe('function')
    expect(typeof kit.useTheme).toBe('function')
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/kit/ThemeToggle.test.tsx src/kit/index.test.ts`
  Expected: collection error — `Failed to resolve import "./ThemeToggle"` — and `kit.ThemeToggle` is `undefined`.

- [ ] **Write the minimal implementation.** Create `frontend/src/kit/ThemeToggle.tsx`:

```tsx
import { THEMES, type Theme, useTheme } from './useTheme'

const ICON: Record<Theme, string> = {
  system: '◐',
  dark: '☾',
  light: '☀',
}

const LABEL: Record<Theme, string> = {
  system: 'System',
  dark: 'Dark',
  light: 'Light',
}

export interface ThemeToggleProps {
  /** The tab-bar form: one icon-only button that cycles the three states. */
  compact?: boolean
}

/**
 * The theme control, in the two shapes the shell has room for.
 *
 * Segmented on desktop, where the sidebar footer can hold three labelled
 * options and showing which one is live is worth the width. Compact on
 * mobile, where the bottom bar has six hubs already and a seventh slot is
 * all there is: one button, cycling, its state carried by the aria-label
 * rather than by three of anything.
 */
export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const [theme, choose] = useTheme()

  if (compact) {
    const next = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length]
    return (
      <button
        type="button"
        aria-label={`Theme: ${theme}`}
        onClick={() => choose(next)}
        className="flex flex-col items-center gap-0.5 rounded-card px-3 py-2
                   text-[11px] text-text-muted hover:text-text"
      >
        <span aria-hidden>{ICON[theme]}</span>
      </button>
    )
  }

  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex gap-1 rounded-card border border-border p-1"
    >
      {THEMES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={theme === option}
          onClick={() => choose(option)}
          className={`flex flex-1 items-center justify-center gap-1
                      rounded-card px-1.5 py-1 text-[11px] ${theme === option
                        ? 'bg-card text-text' : 'text-text-muted hover:text-text'}`}
        >
          <span aria-hidden>{ICON[option]}</span>
          {LABEL[option]}
        </button>
      ))}
    </div>
  )
}
```

  Append to `frontend/src/kit/index.ts`:

```ts
export { default as ThemeToggle } from './ThemeToggle'
export type { ThemeToggleProps } from './ThemeToggle'
export { THEMES, THEME_KEY, applyTheme, readTheme, useTheme } from './useTheme'
export type { Theme } from './useTheme'
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/kit/ThemeToggle.test.tsx src/kit/index.test.ts src/kit/useTheme.test.ts`

- [ ] **Commit.**

```bash
git add frontend/src/kit/ThemeToggle.tsx frontend/src/kit/ThemeToggle.test.tsx frontend/src/kit/index.ts frontend/src/kit/index.test.ts && git commit -m "$(cat <<'EOF'
feat: three-way theme toggle, segmented and compact

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 15 — F5: the toggle's place in the shell

**Files:**
- Modify `frontend/src/kit/AppShell.tsx` (import line 3, mobile branch lines 34-48, desktop branch lines 50-62)
- Modify `frontend/src/kit/AppShell.test.tsx` (import line 1, append inside the existing `describe`)

`frontend/src/hubs/responsive.test.tsx` needs no change: it renders hubs, never `AppShell`, and its `matchMedia` stub is already total.

- [ ] **Write the failing test.** Replace line 1 of `frontend/src/kit/AppShell.test.tsx` with:

```tsx
import { render, screen, within } from '@testing-library/react'
```

  And append inside the `describe('AppShell')` block:

```tsx
  it('puts the theme control in the sidebar footer on desktop', () => {
    stubMatchMedia(false)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    const nav = screen.getByTestId('nav')
    expect(within(nav).getByRole('group', { name: 'Theme' }))
      .toBeInTheDocument()
  })

  it('gives the tab bar a seventh, icon-only slot on mobile', () => {
    stubMatchMedia(true)
    render(<MemoryRouter><AppShell><p>page</p></AppShell></MemoryRouter>)
    const nav = screen.getByTestId('nav')
    expect(within(nav).getByRole('button', { name: /^Theme: / }))
      .toBeInTheDocument()
    // Still six hubs: the toggle is a button, never a seventh destination.
    expect(within(nav).getAllByRole('link')).toHaveLength(6)
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/kit/AppShell.test.tsx`
  Expected: both new tests fail — `Unable to find an accessible element with the role "group" and name "Theme"`, and no button whose label starts `Theme: `.

- [ ] **Write the minimal implementation.** In `frontend/src/kit/AppShell.tsx`, replace line 3 with:

```tsx
import ThemeToggle from './ThemeToggle'
import { useIsMobile } from './useMediaQuery'
```

  Replace the mobile `<nav>` (lines 38-45) with:

```tsx
        <nav
          data-testid="nav"
          data-mode="tabbar"
          className="fixed inset-x-0 bottom-0 flex justify-around border-t
                     border-border bg-card py-1"
        >
          {links}
          {/* The seventh slot. Six hubs already fill this row, so the theme
              control gets an icon and carries its state in the label. */}
          <ThemeToggle compact />
        </nav>
```

  And replace the desktop `<nav>` (lines 52-59) with:

```tsx
      <nav
        data-testid="nav"
        data-mode="sidebar"
        className="flex flex-col gap-1 border-r border-border p-3"
      >
        <p className="mb-3 px-3 text-lg font-semibold text-text">gaffer</p>
        {links}
        {/* Footer, under the nav: chrome about the app rather than a place
            in it, so it sits below every destination and off the tab order
            of the six. */}
        <div className="mt-auto pt-3">
          <ThemeToggle />
        </div>
      </nav>
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/kit/AppShell.test.tsx src/hubs/responsive.test.tsx`

- [ ] **Commit.**

```bash
git add frontend/src/kit/AppShell.tsx frontend/src/kit/AppShell.test.tsx && git commit -m "$(cat <<'EOF'
feat: theme control in the sidebar footer and the mobile tab bar

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 16 — F5: no flash of the wrong theme

**Files:**
- Modify `frontend/index.html` (inside `<head>`, after the `<title>`)
- Modify `frontend/src/styles/theme.test.ts` (append to the `light theme` describe)

- [ ] **Write the failing test.** Append inside the `describe('light theme')` block of `frontend/src/styles/theme.test.ts`:

```ts
  // The attribute has to be on <html> before the first paint, or a user who
  // chose light sees the dark base flash while the bundle loads.
  it('is applied by a boot script before the bundle runs', () => {
    const html = readFileSync(new URL('../../index.html', import.meta.url),
                              'utf8')
    expect(html).toContain("localStorage.getItem('gaffer-theme')")
    expect(html).toContain("setAttribute('data-theme'")
    expect(html).toContain('try {')
    expect(html).toContain('catch')
    // Before the module script, or it is not a boot script.
    expect(html.indexOf("localStorage.getItem('gaffer-theme')"))
      .toBeLessThan(html.indexOf('/src/main.tsx'))
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/styles/theme.test.ts`
  Expected: failure — `index.html` has no boot script, so the first `toContain` fails.

- [ ] **Write the minimal implementation.** Replace `frontend/index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>gaffer</title>
    <script>
      // Before the first paint: the bundle applies the same attribute from
      // kit/useTheme.ts, but it does so a network round trip later, which is
      // long enough to flash the dark base at someone who chose light.
      // "system" stores nothing and needs no attribute, so a throw here — a
      // private window, site data refused — lands on exactly that.
      try {
        var stored = localStorage.getItem('gaffer-theme')
        if (stored === 'dark' || stored === 'light') {
          document.documentElement.setAttribute('data-theme', stored)
        }
      } catch (e) { /* system theme it is */ }
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/styles/theme.test.ts`

- [ ] **Commit.**

```bash
git add frontend/index.html frontend/src/styles/theme.test.ts && git commit -m "$(cat <<'EOF'
feat: boot script applies the stored theme before first paint

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 17 — The whole frontend suite and the type check

**Files:** none modified unless a failure demands it.

- [ ] **Run the suite.** `cd frontend && npm test -- --run`
  Expected: every file green, including the pre-existing hub suites, `coldclone.test.tsx` and `responsive.test.tsx`.

- [ ] **Run the type check.** `cd frontend && npx tsc -b`
  Expected: no output (clean). The likely findings if it is not: `PenTrackerGw`'s optional fields reaching `fmtNum`, which takes `number | null | undefined` (fine), and `Column<PenTrackerGw>['value']` needing `?? null` rather than `?? undefined` (already written that way).

- [ ] **Fix only what these two commands report.** No new behaviour here; if a fix is needed, it belongs to the task that introduced the code and gets the same commit trailers.

- [ ] **Commit only if something changed.** Run `git status --short` and name every changed path explicitly in the `git add` — the staging rule holds here too:

```bash
git add <the exact files git status listed> && git commit -m "$(cat <<'EOF'
fix: type and suite fallout from the v7d frontend work

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

  If `git status --short` shows nothing, skip the commit — a clean run is the deliverable.

---

## Task 18 — Rebuild the shipped bundle

**Files:**
- Regenerate `src/gaffer/web/static/**` (build artifact; `frontend/vite.config.ts` points `build.outDir` there)

- [ ] **Build.** `cd frontend && npm run build`
  Expected: `tsc -b` clean, then vite writing `../src/gaffer/web/static` (`emptyOutDir: true`, so the directory is replaced wholesale).

- [ ] **Check what that staged-to-be.** `git status --short src/gaffer/web/static`
  Expected: modified/added/deleted files under `src/gaffer/web/static/` only — `index.html` and hashed `assets/*`.

- [ ] **Stage the directory and verify nothing else came with it.**

```bash
git add src/gaffer/web/static && git status --short
```

  Every staged path must begin `src/gaffer/web/static/`. This is the one broad `git add` in the plan: the directory is a build output that ships in the wheel, and naming its hashed filenames by hand is not possible.

- [ ] **Run the packaging test.** `uv run pytest -q -p no:randomly tests/test_web_packaging.py tests/test_web_smoke.py`

- [ ] **Commit.**

```bash
git commit -m "$(cat <<'EOF'
chore: rebuild the shipped UI bundle for v7d

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 19 — Full suite and the protected audit

**Files:** none modified.

- [ ] **Run the whole Python suite.** `uv run pytest -q -p no:randomly`
  Expected: green. The kind count is 7 backend and 7 frontend, and both were moved in lockstep with the tables they describe.

- [ ] **Audit the protected list.** Run:

```bash
git diff main --stat -- src/gaffer/advise.py src/gaffer/set_pieces.py 'src/gaffer/optimize/**' tests/test_advise.py tests/test_odds.py tests/test_web_jobs.py 'tests/test_*_degradation.py' scripts/s2_replay.py
```

  Expected: **empty output**. Any line here is a defect to revert, not to explain.

- [ ] **Confirm the runner and its routes never moved.**

```bash
git diff main --stat -- src/gaffer/web/jobs.py src/gaffer/web/routers/jobs.py
```

  Expected: empty output — v7d adds kinds to the allow-list only.

- [ ] **Confirm the working tree is clean.** `git status --short`
  Expected: nothing but ignored paths. No commit for this task.

---

## Deferred to the orchestrator

Live smokes are out of the plan by instruction: `uv run gaffer advise --fast` (G1), `GET /api/pens` against a running server (G2), and the restarted-UI check that the Snapshot button and the light theme render (G4) are run after this plan completes.
