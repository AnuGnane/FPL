# Gaffer v8b Decision Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** close the loop the whole app exists for. After a gameweek's results are final, grade every decision the user actually made against the model's *deadline-guarded* counterfactual — in points and in title odds — and bank the verdict in a season-long ledger of where EV leaks.

**Architecture:** Three seams, all new. `src/gaffer/data/my_entry.py` persists what nothing persists today — my picks per gameweek (the exact `fetch_rival_picks_history` file layout, so my entry caches like any other in the league), my entry history and my transfers. `src/gaffer/review.py` is the grading engine and is a pure *reader*: it imports `journal.latest_run_per_gw` for "what the model said in time", `backtest.score_gw` for "what that squad really scored with autosubs", and `league_sim.build_inputs`/`simulate_league` for "what that decision did to my title odds", and it modifies none of them. `reports/decision_ledger.json` is the bank — written once per gameweek at review time, because `ADVICE_HISTORY_KEEP = 20` is global and GW1's advice will be pruned within weeks. `GET /api/review` serves the ledger, a `review` job kind and a Tuesday launchd plist run it, and a fifth Model-hub tab renders it.

Nothing feeds back into advice. The ledger is measurement; using it to steer the tilt is a later cycle (spec §6).

**Tech Stack:** Python 3.12, uv, pandas/pyarrow/numpy, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest + Radix tabs.

**Prerequisite:** work on branch `feat/gaffer-v8b`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8b-decision-loop-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 12 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every pre-v8b `tests/test_*_degradation.py`, `scripts/s2_replay.py`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`.

**Import-only (spec §5):** `src/gaffer/journal.py` and `src/gaffer/backtest.py`. Both are read by `review.py` and neither is edited. `journal.py`'s row shape is pinned by `tests/test_web_journal.py`; `backtest.score_gw` is the autosub-aware scorer and moving it would break the replay. If a helper needs sharing, re-export it from `review.py` — never move it. `frontend/src/hubs/model/JournalTab.tsx` is likewise untouched: the Review tab is a fifth tab beside it, not a replacement for it.

If a task appears to need an edit inside a protected or import-only file, the plan is wrong — stop and report rather than editing.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8b commits no data asset — the ledger and the banked entry files are runtime artifacts.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 12 is the checklist, unfilled.

**Suite baselines:** 1966 python tests, 328 frontend tests + 1 skipped. Every task's final `pytest` run must leave the pre-existing suites green.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

## The reconciliation arithmetic, settled

Spec D7 makes reconciliation a hard gate, and the gate's formula depends on a fact about the FPL API that the spec left open: is `entry/{id}/history/`'s `current[].points` gross or net of the transfer hit?

**It is gross.** Verified against the live API on 2026-08-31, entry 43863:

```
GW1: points 62, event_transfers_cost 0, total_points 62
GW2: points 101, event_transfers_cost 4, total_points 159
```

62 + 101 = 163, but the cumulative `total_points` is 159. The four points are deducted once, from the cumulative, and are still present in `points`. So:

```
official_net(gw) = current[gw].points - current[gw].event_transfers_cost
```

and that is what `score_gw(..., hits=cost // 4)` — which subtracts `4 * hits` itself — must equal. Every fixture in this plan is built to that shape: a GW row carrying `points` **gross** beside a non-zero `event_transfers_cost`. A fixture that pre-deducted the hit would make the reconciliation test pass against a false API.

(The league standings endpoint's `event_total` is gross too — 101 for that entry — which is why it is not used here.)

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/data/my_entry.py` | Create | F1: bank my picks / history / transfers. Never raises. |
| `tests/test_my_entry.py` | Create | F1 suite: layout, idempotence, replace-on-write, degradation. |
| `src/gaffer/review.py` | Create (grown across Tasks 2-6) | F2: actuals, the two decision readers, the four lanes, hindsight, Δwin%, the ledger, the season summary. |
| `tests/test_review_inputs.py` | Create | `actuals_for_gw`, `reviewable_gws`, `model_decisions`, `my_decisions`. |
| `tests/test_review_grades.py` | Create | The four lanes, the labels, misses, accuracy, reconciliation. |
| `tests/test_review_hindsight.py` | Create | `hindsight_xi` over a hand-scored fifteen. |
| `tests/test_review_pwin.py` | Create | Δwin% pricing, and its absent-with-notice degradation. |
| `tests/test_review_ledger.py` | Create | `run_review`, the ledger, `season_summary`. |
| `src/gaffer/cli.py` | Modify (new `review` command after `field_scrape`, ~L256) | `gaffer review [--gw N]`. |
| `src/gaffer/web/job_kinds.py` | Modify (`run_review_job`; `JOB_KINDS` L111-120) | The ninth job kind. |
| `tests/test_web_job_kinds_v8b.py` | Create | Allow-list, row count, degradation, lazy import. |
| `scripts/com.gaffer.review.plist` | Create | Tuesday 09:00 local. |
| `scripts/install_automation.sh` | Modify (loop L5 + echo L12) | Installs it. |
| `src/gaffer/web/schemas.py` | Modify (append the v8b models) | `ReviewLane`, `ReviewMiss`, `ReviewHindsight`, `ReviewGw`, `ReviewSummary`, `Review`. |
| `src/gaffer/web/routers/review.py` | Create | `GET /api/review`. |
| `src/gaffer/web/app.py` | Modify (import L26-28; `include_router` ~L75) | Registers it. |
| `tests/test_web_review.py` | Create | The endpoint, the empty state, the corrupt-ledger rail. |
| `frontend/src/types.ts` | Modify (`JOB_KINDS` L574; `JOB_KIND_LABEL` L579; new interfaces) | Lockstep with the router. |
| `frontend/src/types.test.ts` | Modify (the count pin, L8-12) | Nine kinds. |
| `frontend/src/hubs/model/ReviewTab.tsx` | Create | The fifth tab. |
| `frontend/src/hubs/model/ReviewTab.test.tsx` | Create | Its suite. |
| `frontend/src/hubs/Model.tsx` | Modify (button row ~L41; tabs L48-61) | The Review button and tab. |
| `tests/test_v8b_degradation.py` | Create | G2 rails. |
| `README.md` | Modify (Where things live ~L313; Automation ~L340) | The ledger, the banked entry files, the Tuesday job. |

---

## Task 1 — F1: banking my own entry

**Files:**
- Create `src/gaffer/data/my_entry.py`
- Create `tests/test_my_entry.py`

- [ ] **Write the failing test.** Create `tests/test_my_entry.py`:

```python
"""Banking my own entry: the one thing gaffer has never kept about itself.

``fetch_my_team`` fetches my squad every Thursday and throws it away the
moment the solver has read it, so by December there is no record of what I
actually played in September. The review cannot grade a decision nobody wrote
down, so this module writes it down — in the *same* file layout
``fetch_rival_picks_history`` already uses for everybody else in the league,
because my entry is one of the fifty and there is no reason for it to have a
private format.

Everything here is called from a launchd job, so nothing here raises.
"""

from __future__ import annotations

import json

import pytest

from gaffer.data.my_entry import (bank_my_entry, bank_my_gw, bank_my_history,
                                  bank_my_transfers, chip_for_gw,
                                  gw_history_row, load_my_gw, load_my_history,
                                  load_my_transfers, my_history_path,
                                  my_picks_path, my_transfers_for_gw,
                                  my_transfers_path)

PICKS = [{"element": 7, "position": 1, "multiplier": 2, "is_captain": True,
          "is_vice_captain": False},
         {"element": 8, "position": 12, "multiplier": 0, "is_captain": False,
          "is_vice_captain": True}]

HISTORY = {
    "current": [
        {"event": 1, "points": 62, "total_points": 62, "rank": 1436685,
         "overall_rank": 1436683, "event_transfers": 0,
         "event_transfers_cost": 0, "points_on_bench": 8},
        # points is GROSS of the hit; total_points is cumulative NET.
        # 62 + 101 - 4 == 159, which is the arithmetic the reconciliation
        # gate is built on.
        {"event": 2, "points": 101, "total_points": 159, "rank": 355490,
         "overall_rank": 378985, "event_transfers": 2,
         "event_transfers_cost": 4, "points_on_bench": 0},
    ],
    "chips": [{"name": "bboost", "event": 2,
               "time": "2026-08-28T07:52:00Z"}],
}

TRANSFERS = [
    {"element_in": 9, "element_out": 8, "event": 2, "entry": 42},
    {"element_in": 11, "element_out": 10, "event": 2, "entry": 42},
    {"element_in": 3, "element_out": 4, "event": 3, "entry": 42},
]


class FakeClient:
    def __init__(self, *, dead=False):
        self.dead = dead
        self.picks_calls = []

    def get_entry_picks(self, entry_id, gw):
        self.picks_calls.append((entry_id, gw))
        if self.dead:
            raise RuntimeError("FPL is down")
        return {"picks": PICKS, "active_chip": None,
                "entry_history": HISTORY["current"][1]}

    def get_entry_history(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return HISTORY

    def get_entry_transfers(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return TRANSFERS


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    return tmp_path


def test_my_picks_land_where_every_other_entry_in_the_league_lands(here):
    """The layout claim, asserted rather than asserted-in-prose: my entry is
    one of the fifty, and ``fetch_rival_picks_history`` must find my file
    already cached rather than fetch it again."""
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert my_picks_path("2026-27", 42, 2) \
        == here / "data/raw/league/2026-27/42-2.json"
    assert my_picks_path("2026-27", 42, 2).is_file()


def test_the_banked_picks_are_the_bare_list_the_rival_cache_holds(here):
    """Not ``{"picks": [...]}``. ``fetch_rival_picks_history`` writes
    ``payload["picks"]`` and reads the file straight back as a list, so a
    dict here would break the very reader this layout exists to share."""
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert json.loads(my_picks_path("2026-27", 42, 2).read_text()) == PICKS


def test_a_banked_gameweek_is_never_fetched_twice(here):
    client = FakeClient()
    bank_my_gw(client, 42, "2026-27", 2)
    bank_my_gw(client, 42, "2026-27", 2)
    assert client.picks_calls == [(42, 2)]


def test_the_picks_read_back_as_they_went_in(here):
    bank_my_gw(FakeClient(), 42, "2026-27", 2)
    assert load_my_gw("2026-27", 42, 2) == PICKS


def test_an_unbanked_gameweek_is_none_not_an_empty_list(here):
    """``None`` is "never banked"; ``[]`` would be "banked and I fielded
    nobody". ``run_review`` reads the difference and skips rather than
    grading a squad of no players."""
    assert load_my_gw("2026-27", 42, 2) is None


def test_a_dead_api_banks_nothing_and_prints_one_line(here, capsys):
    assert bank_my_gw(FakeClient(dead=True), 42, "2026-27", 2) is None
    assert not my_picks_path("2026-27", 42, 2).exists()
    assert "picks for GW2 not banked" in capsys.readouterr().out


def test_the_history_is_replaced_on_write_rather_than_cached(here):
    """The picks of a finished gameweek are a fact; the *history* is
    cumulative and grows a row every week, so caching it permanently would
    freeze the season at whatever week it was first written."""
    bank_my_history(FakeClient(), 42, "2026-27")
    my_history_path("2026-27", 42).write_text(json.dumps({"current": []}))
    bank_my_history(FakeClient(), 42, "2026-27")
    assert len(load_my_history("2026-27", 42)["current"]) == 2


def test_the_history_rewrite_leaves_no_temp_file_behind(here):
    bank_my_history(FakeClient(), 42, "2026-27")
    assert not list(my_history_path("2026-27", 42).parent.glob("*.tmp"))


def test_an_absent_history_reads_as_none(here):
    assert load_my_history("2026-27", 42) is None


def test_a_corrupt_history_reads_as_none_rather_than_raising(here):
    path = my_history_path("2026-27", 42)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert load_my_history("2026-27", 42) is None


def test_a_dead_api_leaves_the_history_alone(here, capsys):
    bank_my_history(FakeClient(), 42, "2026-27")
    assert bank_my_history(FakeClient(dead=True), 42, "2026-27") is None
    assert len(load_my_history("2026-27", 42)["current"]) == 2
    assert "entry history not banked" in capsys.readouterr().out


def test_the_gameweek_row_is_the_one_the_reconciliation_reads(here):
    row = gw_history_row(HISTORY, 2)
    assert row["points"] == 101
    assert row["event_transfers_cost"] == 4
    assert row["points_on_bench"] == 0


def test_a_gameweek_the_history_has_no_row_for_is_none(here):
    assert gw_history_row(HISTORY, 9) is None
    assert gw_history_row(None, 2) is None


def test_the_chip_is_read_off_the_history_not_off_the_picks(here):
    """The picks payload carries ``active_chip`` too, but the history's
    ``chips`` list is the one that survives being banked once and read all
    season — and it is the only source for a gameweek whose picks the API
    will no longer serve."""
    assert chip_for_gw(HISTORY, 2) == "bboost"
    assert chip_for_gw(HISTORY, 1) is None
    assert chip_for_gw(None, 2) is None


def test_the_transfers_bank_and_read_back(here):
    bank_my_transfers(FakeClient(), 42, "2026-27")
    assert my_transfers_path("2026-27", 42).is_file()
    assert load_my_transfers("2026-27", 42) == TRANSFERS


def test_the_transfers_are_replaced_on_write_like_the_history(here):
    bank_my_transfers(FakeClient(), 42, "2026-27")
    my_transfers_path("2026-27", 42).write_text("[]")
    bank_my_transfers(FakeClient(), 42, "2026-27")
    assert len(load_my_transfers("2026-27", 42)) == 3


def test_one_gameweeks_transfers_are_the_ones_stamped_with_its_event(here):
    out = my_transfers_for_gw(TRANSFERS, 2)
    assert [(t["element_out"], t["element_in"]) for t in out] \
        == [(8, 9), (10, 11)]


def test_a_gameweek_with_no_transfers_is_an_empty_list(here):
    assert my_transfers_for_gw(TRANSFERS, 1) == []
    assert my_transfers_for_gw(None, 1) == []


def test_banking_the_lot_returns_all_three_pieces(here):
    out = bank_my_entry(FakeClient(), 42, "2026-27", 2)
    assert out["picks"] == PICKS
    assert out["chip"] == "bboost"
    assert out["hits"] == 1
    assert out["history_row"]["points"] == 101
    assert [t["element_in"] for t in out["transfers"]] == [9, 11]


def test_banking_the_lot_with_a_dead_api_is_a_dict_of_nothings(here, capsys):
    """A launchd Tuesday with no network must not take the review down; the
    gameweeks already banked are still gradeable, and this one is not."""
    out = bank_my_entry(FakeClient(dead=True), 42, "2026-27", 2)
    assert out["picks"] is None
    assert out["chip"] is None
    assert out["hits"] == 0
    assert out["history_row"] is None
    assert out["transfers"] == []
    assert "FPL is down" in capsys.readouterr().out
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_my_entry.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.data.my_entry'`.

- [ ] **Write the implementation.** Create `src/gaffer/data/my_entry.py`:

```python
"""What I actually did, kept.

Everything gaffer knows about its own manager today is transient.
``fetch_my_team`` pulls my fifteen every Thursday so the MILP has a starting
squad, and the moment the solve finishes there is no record that the fetch
ever happened. That is fine for advising and useless for reviewing: a grade
for GW3 asked in December needs the squad I fielded in September, and the FPL
API will still serve it — right up until it does not, and in any case one
HTTP call per gameweek per page view is not a way to read a season.

So three stores, keyed by season and entry, deliberately different in kind:

``data/raw/league/{season}/{entry}-{gw}.json``
    my picks for one finished gameweek. **The same path, and the same bare
    list, that** :func:`gaffer.data.league.fetch_rival_picks_history` **writes
    for every other entry in my mini-league.** My entry is one of the fifty;
    giving it a private format would mean two readers of one fact. Permanent
    and idempotent: a played gameweek's picks never change again.

``data/raw/league/{season}/{entry}-history.json``
    the entry-history payload: per-gameweek points, rank, bench points,
    transfer cost, and the chips list. Replace-on-write, because it is
    cumulative — a permanent cache would freeze the season at the week it was
    first taken.

``data/raw/league/{season}/{entry}-transfers.json``
    every transfer I have made this season, each stamped with the gameweek it
    was made for. Replace-on-write for the same reason.

A note on the points arithmetic, because the reconciliation gate turns on it:
``current[].points`` is **gross** of the transfer hit and ``total_points`` is
cumulative **net**. Verified on the live API, entry 43863 2026-27: GW1 62,
GW2 101 with a cost of 4, cumulative 159 — and 62 + 101 = 163. So the net
score of a gameweek is ``points - event_transfers_cost``, and
:func:`gw_history_row` hands both numbers to the caller rather than doing the
subtraction here, where a reader could not see it.

Nothing in this module raises. It is called from ``gaffer review``, which is
called from launchd, and :func:`gaffer.snapshot.run_snapshot`'s contract
applies: one printed line whatever happens.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from gaffer.data.league import RAW_LEAGUE

__all__ = ["RAW_LEAGUE", "bank_my_entry", "bank_my_gw", "bank_my_history",
           "bank_my_transfers", "chip_for_gw", "gw_history_row", "load_my_gw",
           "load_my_history", "load_my_transfers", "my_history_path",
           "my_picks_path", "my_transfers_for_gw", "my_transfers_path"]


def my_picks_path(season: str, entry_id: int, gw: int,
                  raw_dir: Path | str | None = None) -> Path:
    """``{raw_dir}/{season}/{entry}-{gw}.json`` — the shared league layout."""
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-{int(gw)}.json"


def my_history_path(season: str, entry_id: int,
                    raw_dir: Path | str | None = None) -> Path:
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-history.json"


def my_transfers_path(season: str, entry_id: int,
                      raw_dir: Path | str | None = None) -> Path:
    base = Path(raw_dir) if raw_dir is not None else RAW_LEAGUE
    return base / str(season) / f"{int(entry_id)}-transfers.json"


def _write_atomic(path: Path, payload) -> Path:
    """Write JSON through a sibling temp file and rename.

    ``os.replace`` is atomic within a directory, so a reader sees the whole
    old file or the whole new one — never the half-written middle it would
    throw away as corrupt. The same trade ``artifacts.append_advice_history``
    and ``league_sim.append_sim_history`` make.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _read_json(path: Path):
    """The parsed file, or ``None`` for absent *and* for corrupt.

    A half-written bank and no bank at all mean the same thing to every
    caller here — "this is not available, do not grade it" — and collapsing
    them is what stops one bad file from crashing a scheduled job.
    """
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def load_my_gw(season: str, entry_id: int, gw: int,
               raw_dir: Path | str | None = None) -> list[dict] | None:
    """My banked picks for ``gw``, or ``None`` if that week was never banked."""
    out = _read_json(my_picks_path(season, entry_id, gw, raw_dir))
    return list(out) if isinstance(out, list) else None


def bank_my_gw(client, entry_id: int, season: str, gw: int,
               raw_dir: Path | str | None = None) -> list[dict] | None:
    """Bank my picks for one gameweek. Idempotent; never raises.

    Returns the picks — banked or already-banked — or ``None`` when the API
    would not answer. A gameweek that is not banked is a gameweek the review
    skips, which is the documented degradation (spec §4, G2): the alternative
    is grading a squad we invented.
    """
    banked = load_my_gw(season, entry_id, gw, raw_dir)
    if banked is not None:
        return banked
    try:
        picks = list(client.get_entry_picks(int(entry_id), int(gw))["picks"])
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my picks for GW{gw} not banked: {exc}")
        return None
    _write_atomic(my_picks_path(season, entry_id, gw, raw_dir), picks)
    return picks


def load_my_history(season: str, entry_id: int,
                    raw_dir: Path | str | None = None) -> dict | None:
    out = _read_json(my_history_path(season, entry_id, raw_dir))
    return out if isinstance(out, dict) else None


def bank_my_history(client, entry_id: int, season: str,
                    raw_dir: Path | str | None = None) -> dict | None:
    """Refresh the banked entry history. Replace-on-write; never raises.

    A failed fetch leaves the previous bank exactly where it was rather than
    truncating it: last week's history is a strictly better answer than no
    history, and every reader here is asking about weeks that have already
    finished.
    """
    try:
        payload = client.get_entry_history(int(entry_id))
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my entry history not banked: {exc}")
        return None
    _write_atomic(my_history_path(season, entry_id, raw_dir), payload)
    return payload


def load_my_transfers(season: str, entry_id: int,
                      raw_dir: Path | str | None = None) -> list[dict] | None:
    out = _read_json(my_transfers_path(season, entry_id, raw_dir))
    return list(out) if isinstance(out, list) else None


def bank_my_transfers(client, entry_id: int, season: str,
                      raw_dir: Path | str | None = None
                      ) -> list[dict] | None:
    """Refresh the banked transfer list. Replace-on-write; never raises."""
    try:
        payload = list(client.get_entry_transfers(int(entry_id)))
    except Exception as exc:  # noqa: BLE001 — network / 404 / schema
        print(f"my transfers not banked: {exc}")
        return None
    _write_atomic(my_transfers_path(season, entry_id, raw_dir), payload)
    return payload


def gw_history_row(history: dict | None, gw: int) -> dict | None:
    """One gameweek's row out of ``current``, or ``None``.

    The row carries ``points`` (gross) *and* ``event_transfers_cost``
    separately; the subtraction is the reconciliation's, not this function's,
    so a reader of the ledger can see which number came from where.
    """
    for row in ((history or {}).get("current") or []):
        try:
            if int(row.get("event")) == int(gw):
                return dict(row)
        except (TypeError, ValueError):
            continue
    return None


def chip_for_gw(history: dict | None, gw: int) -> str | None:
    """The chip I played in ``gw``, or ``None``.

    Read off the history's ``chips`` list rather than the picks payload's
    ``active_chip``: the history is banked once and answers for every week of
    the season at once, including weeks whose picks endpoint has stopped
    answering.
    """
    for chip in ((history or {}).get("chips") or []):
        try:
            if int(chip.get("event")) == int(gw):
                return str(chip.get("name") or "") or None
        except (TypeError, ValueError):
            continue
    return None


def my_transfers_for_gw(transfers: list[dict] | None,
                        gw: int) -> list[dict]:
    """The transfers I made *for* ``gw``, in the order the API listed them.

    Takes the banked list rather than a client, unlike the sketch in spec §1:
    ``run_review`` banks the whole season's transfers once and then grades
    several gameweeks off it, and a function that could also take a client
    would be a second fetch path for one fact.
    """
    out = []
    for row in (transfers or []):
        try:
            if int(row.get("event")) == int(gw):
                out.append(dict(row))
        except (TypeError, ValueError):
            continue
    return out


def bank_my_entry(client, entry_id: int, season: str, gw: int,
                  raw_dir: Path | str | None = None) -> dict:
    """Bank all three stores and return one gameweek's view of them.

    ``hits`` is the *count* of hits, not their cost: ``score_gw`` takes a
    count and multiplies by four itself, and handing it a cost would charge
    the user sixteen points for a single hit.

    Every field degrades independently. A dead API on a Tuesday morning gives
    back a dict of nothings and a printed line, and ``run_review`` skips that
    gameweek while still grading the ones already banked.
    """
    picks = bank_my_gw(client, entry_id, season, gw, raw_dir)
    history = (bank_my_history(client, entry_id, season, raw_dir)
               or load_my_history(season, entry_id, raw_dir))
    transfers = (bank_my_transfers(client, entry_id, season, raw_dir)
                 or load_my_transfers(season, entry_id, raw_dir))
    row = gw_history_row(history, gw)
    cost = int((row or {}).get("event_transfers_cost", 0) or 0)
    return {"picks": picks, "history": history, "history_row": row,
            "chip": chip_for_gw(history, gw), "hits": cost // 4,
            "transfers": my_transfers_for_gw(transfers, gw)}
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_my_entry.py`
  Expected: `20 passed`.

- [ ] **Commit.**

```bash
git add src/gaffer/data/my_entry.py tests/test_my_entry.py && git commit -m "$(cat <<'EOF'
feat: bank my own picks, history and transfers per gameweek

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — F2: the actuals frame and the two decision readers

**Files:**
- Create `src/gaffer/review.py`
- Create `tests/test_review_inputs.py`

- [ ] **Write the failing test.** Create `tests/test_review_inputs.py`:

```python
"""What the review reads before it grades anything.

Three readers and no arithmetic: the realized points frame shaped the way
``backtest.score_gw`` wants it, what the model said before the deadline, and
what I actually did. Each answers ``None`` rather than a guess when its source
is not there, because a lane graded against a fabricated counterfactual is
worse than a lane not graded at all.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY
from gaffer.data import store
from gaffer.data.my_entry import my_picks_path
from gaffer.review import (actuals_for_gw, code_of_element, model_decisions,
                           my_decisions, reviewable_gws)

# code 100 plays twice in GW2 (a double gameweek): the frame must come back
# with one row per code, points and minutes summed.
PLAYER_GW = pd.DataFrame([
    {"season_idx": 4, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 9, "minutes": 90},
    {"season_idx": 4, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 4, "minutes": 62},
    {"season_idx": 4, "gw": 2, "code": 101, "element": 8, "position": "DEF",
     "total_points": 2, "minutes": 90},
    {"season_idx": 4, "gw": 1, "code": 100, "element": 7, "position": "MID",
     "total_points": 6, "minutes": 90},
    {"season_idx": 3, "gw": 2, "code": 100, "element": 7, "position": "MID",
     "total_points": 99, "minutes": 90},
])

PLAYERS = pd.DataFrame([{"code": 100, "element": 7},
                        {"code": 101, "element": 8}])

ADVICE = {
    "gw": 2,
    "deadline": "2026-08-21T17:30:00Z",
    "xi": [{"code": 100, "name": "Salah", "position": "MID"}],
    "bench": [{"code": 101, "name": "Dud", "position": "DEF"}],
    "captain": {"code": 100, "name": "Salah", "position": "MID"},
    "vice": {"code": 101, "name": "Dud", "position": "DEF"},
    "buys": [{"code": 100, "name": "Salah", "position": "MID"}],
    "sells": [{"code": 101, "name": "Dud", "position": "DEF"}],
    "hits": 1,
    "chip_table": [{"chip": "bboost", "gw": 2, "play_now": True},
                   {"chip": "3xc", "gw": 4, "play_now": False}],
}

MY_PICKS = [
    {"element": 7, "position": 1, "multiplier": 2, "is_captain": True,
     "is_vice_captain": False},
    {"element": 8, "position": 12, "multiplier": 0, "is_captain": False,
     "is_vice_captain": True},
]

HISTORY = {"current": [{"event": 2, "points": 20, "total_points": 20,
                        "event_transfers": 1, "event_transfers_cost": 4,
                        "points_on_bench": 3}],
           "chips": [{"name": "3xc", "event": 2}]}


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    return tmp_path


def _results():
    store.save(PLAYER_GW, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")


def _advice(payload=None, stamp="2026-08-21T09:00:00"):
    payload = ADVICE if payload is None else payload
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / f"gw{payload['gw']}-{stamp}.json").write_text(
        json.dumps(payload))


def _mine(season="2026-27", entry=42, gw=2, picks=None, history=None):
    path = my_picks_path(season, entry, gw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(MY_PICKS if picks is None else picks))
    (path.parent / f"{entry}-history.json").write_text(
        json.dumps(HISTORY if history is None else history))


def test_the_actuals_carry_exactly_the_columns_score_gw_reads(here):
    _results()
    out = actuals_for_gw(2)
    assert list(out.columns) == ["code", "total_points", "minutes", "position"]


def test_a_double_gameweek_is_one_row_per_code_with_the_totals_added(here):
    """``score_gw`` looks a code up in a dict built off this frame, so two
    rows for one code would silently drop one of the two matches — which is
    exactly the join ``backtest`` documents having learned the hard way."""
    _results()
    out = actuals_for_gw(2).set_index("code")
    assert out.loc[100, "total_points"] == 13
    assert out.loc[100, "minutes"] == 152
    assert out.loc[100, "position"] == "MID"


def test_only_the_newest_season_is_read(here):
    """The training frame holds several seasons and a code plays in more than
    one of them. GW2 of 2022-23 is not GW2 of this season."""
    _results()
    assert int(actuals_for_gw(2).set_index("code").loc[100,
                                                       "total_points"]) == 13


def test_a_gameweek_with_no_results_is_an_empty_frame_with_the_columns(here):
    _results()
    out = actuals_for_gw(9)
    assert out.empty
    assert list(out.columns) == ["code", "total_points", "minutes", "position"]


def test_no_results_file_at_all_is_an_empty_frame(here):
    out = actuals_for_gw(2)
    assert out.empty


def test_the_reviewable_gameweeks_are_the_ones_with_final_results(here):
    """``refresh_live`` drops every gameweek FPL has not marked
    ``data_checked``, so the presence of a gameweek in this file *is* the
    data_checked gate (artifacts.ingested_through's reasoning)."""
    _results()
    assert reviewable_gws() == [1, 2]


def test_a_clone_with_no_results_reviews_nothing(here):
    assert reviewable_gws() == []


def test_the_element_to_code_map_comes_from_the_players_table(here):
    _results()
    assert code_of_element() == {7: 100, 8: 101}


def test_the_model_side_is_the_last_run_that_beat_the_deadline(here):
    _results()
    _advice()
    out = model_decisions(2)
    assert out["xi"] == [100]
    assert out["bench"] == [101]
    assert out["captain"] == 100
    assert out["vice"] == 101
    assert out["buys"] == [100]
    assert out["sells"] == [101]
    assert out["hits"] == 1
    assert out["post_deadline"] is False


def test_the_model_chip_is_the_one_the_table_says_to_play_now(here):
    _results()
    _advice()
    assert model_decisions(2)["chip"] == "bboost"


def test_a_chip_table_with_nothing_to_play_now_is_no_chip(here):
    _results()
    payload = {**ADVICE, "chip_table": [{"chip": "bboost", "gw": 5,
                                         "play_now": False}]}
    _advice(payload)
    assert model_decisions(2)["chip"] is None


def test_a_run_banked_after_the_deadline_carries_the_late_flag(here):
    """``latest_run_per_gw`` verbatim (spec D3): a run written after kickoff
    saw the team news and must not pass itself off as foresight."""
    _results()
    _advice(stamp="2026-08-22T09:00:00")
    assert model_decisions(2)["post_deadline"] is True


def test_a_gameweek_with_no_banked_advice_is_none(here):
    """``ADVICE_HISTORY_KEEP`` is 20 and global, so this is not an edge case
    — it is what GW1 looks like by October (spec D2)."""
    _results()
    assert model_decisions(2) is None


def test_the_model_names_come_along_for_the_grade_cards(here):
    _results()
    _advice()
    assert model_decisions(2)["names"][100] == "Salah"


def test_my_side_is_read_off_the_bank_not_off_the_api(here):
    _results()
    _mine()
    out = my_decisions(2, season="2026-27", entry_id=42)
    assert out["xi"] == [100]
    assert out["bench"] == [101]
    assert out["captain"] == 100
    assert out["vice"] == 101
    assert out["chip"] == "3xc"
    assert out["hits"] == 1
    assert out["points_on_bench"] == 3
    assert out["official_gross"] == 20
    assert out["official_cost"] == 4


def test_my_bench_keeps_the_order_the_api_listed_it_in(here):
    """Bench order is a graded lane, so 12-13-14-15 is data, not a set."""
    _results()
    picks = [{"element": 7, "position": 1, "multiplier": 1,
              "is_captain": True, "is_vice_captain": False},
             {"element": 8, "position": 14, "multiplier": 0,
              "is_captain": False, "is_vice_captain": False},
             {"element": 7, "position": 12, "multiplier": 0,
              "is_captain": False, "is_vice_captain": True}]
    _mine(picks=picks)
    assert my_decisions(2, season="2026-27", entry_id=42)["bench"] \
        == [100, 101]


def test_an_unbanked_gameweek_of_mine_is_none(here):
    _results()
    assert my_decisions(2, season="2026-27", entry_id=42) is None


def test_a_pick_whose_element_the_players_table_does_not_know_is_dropped(here):
    """A player who left the game between the gameweek and the review has no
    code to score. Dropping him costs his points; inventing a code would cost
    somebody else's."""
    _results()
    _mine(picks=[{"element": 7, "position": 1, "multiplier": 2,
                  "is_captain": True, "is_vice_captain": False},
                 {"element": 999, "position": 2, "multiplier": 1,
                  "is_captain": False, "is_vice_captain": False}])
    out = my_decisions(2, season="2026-27", entry_id=42)
    assert out["xi"] == [100]
    assert "1 pick could not be resolved to a player" in out["notices"][0]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_review_inputs.py`
  Expected: collection error — `ModuleNotFoundError: No module named 'gaffer.review'`.

- [ ] **Write the implementation.** Create `src/gaffer/review.py`:

```python
"""The decision loop: grading what I did against what the model said in time.

The journal already draws one line — the model's XI against mine, captain
doubled, no autosubs. This module asks the harder question the whole app
exists for: *which decision* cost me, in points and in title odds, and how
much has that decision type cost me all season.

Four things make it more than a bigger journal:

* **The counterfactual is deadline-guarded.** ``journal.latest_run_per_gw`` is
  imported verbatim (spec D3): among a gameweek's banked runs the newest one
  written *before* the deadline wins, and a gameweek where every run was late
  is graded with a flag rather than passed off as foresight.
* **Every squad is scored with real autosubs.** ``backtest.score_gw`` — the
  replay's scorer, with the vice fallback, the bench-boost arithmetic and the
  hit cost already in it. Imported, never modified; its simplified-autosub
  caveats (``backtest.py:36-38``) are exactly what the reconciliation gate
  below is built to catch.
* **Two currencies.** Points, and the change in P(win the mini-league) from
  v8c's Monte Carlo. A captaincy that cost two points and a place in the race
  is a different decision from one that cost two points and nothing.
* **Grades are banked, never re-derived.** ``ADVICE_HISTORY_KEEP`` is 20 and
  global, so GW1's advice is pruned within weeks (spec D2). The review runs
  once a gameweek's results are final and appends to
  ``reports/decision_ledger.json``; every reader afterwards reads the ledger.

Nothing here writes to ``advise``. The ledger is measurement.
"""

from __future__ import annotations

import pandas as pd

from gaffer.artifacts import load_components  # noqa: F401 — Task 5's import
from gaffer.backtest import score_gw
from gaffer.data import store
from gaffer.data.my_entry import (bank_my_entry, chip_for_gw, gw_history_row,
                                  load_my_gw, load_my_history,
                                  load_my_transfers, my_transfers_for_gw)
from gaffer.journal import _code_of_element, latest_run_per_gw

__all__ = ["ACTUAL_COLS", "actuals_for_gw", "code_of_element",
           "model_decisions", "my_decisions", "reviewable_gws", "score_gw"]

ACTUAL_COLS = ["code", "total_points", "minutes", "position"]
"""Exactly the columns :func:`gaffer.backtest.score_gw` reads, in its order."""

PLAYER_GW = "live/player_gw.parquet"

XI_SIZE = 11
"""Picks at a higher ``position`` than this are the bench, in that order."""


def code_of_element() -> dict[int, int]:
    """``element -> code`` off the live players table.

    A re-export of ``journal._code_of_element`` rather than a copy of it:
    ``journal.py`` is import-only this cycle (spec §5) and its row shape is
    pinned by existing tests, so the sharing goes this way round.
    """
    return _code_of_element()


def actuals_for_gw(gw: int) -> pd.DataFrame:
    """One row per code for ``gw``, shaped for :func:`score_gw`.

    Double gameweeks are aggregated here rather than left to the caller,
    which is the join ``backtest``'s docstring records having learned the
    hard way: ``score_gw`` builds a dict off this frame, so a second row for
    a code silently drops one of his two matches.

    Only the newest season is read. The live frame carries several, and GW2
    of 2022-23 is not GW2 of this one.

    An empty frame with the right columns for every failure — no file, no
    such gameweek, an unreadable parquet. ``run_review`` reads emptiness as
    "not reviewable" and says so.
    """
    empty = pd.DataFrame(columns=ACTUAL_COLS)
    if not store.exists(PLAYER_GW):
        return empty
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001 — an unreadable frame is a missing one
        return empty
    if frame.empty:
        return empty
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    frame = frame[pd.to_numeric(frame["gw"], errors="coerce") == int(gw)]
    if frame.empty:
        return empty
    grouped = frame.groupby("code", as_index=False).agg(
        total_points=("total_points", "sum"), minutes=("minutes", "sum"),
        position=("position", "first"))
    grouped["code"] = grouped["code"].astype("int64")
    grouped["total_points"] = pd.to_numeric(
        grouped["total_points"], errors="coerce").fillna(0).astype("int64")
    grouped["minutes"] = pd.to_numeric(
        grouped["minutes"], errors="coerce").fillna(0).astype("int64")
    grouped["position"] = grouped["position"].astype(str)
    return grouped[ACTUAL_COLS]


def reviewable_gws() -> list[int]:
    """Every gameweek whose results are final, ascending.

    Presence in ``player_gw.parquet`` *is* the ``data_checked`` gate:
    ``refresh_live`` drops every gameweek FPL has not marked so, which is the
    same reasoning ``artifacts.ingested_through`` documents. Reviewing a week
    FPL is still adjusting would bank a grade against numbers that then move.
    """
    if not store.exists(PLAYER_GW):
        return []
    try:
        frame = store.load(PLAYER_GW)
    except Exception:  # noqa: BLE001
        return []
    if frame.empty:
        return []
    if "season_idx" in frame.columns:
        frame = frame[frame["season_idx"] == frame["season_idx"].max()]
    gws = pd.to_numeric(frame["gw"], errors="coerce").dropna()
    return sorted({int(g) for g in gws})


def _codes(entries) -> list[int]:
    return [int(e["code"]) for e in (entries or [])
            if isinstance(e, dict) and e.get("code") is not None]


def model_decisions(gw: int) -> dict | None:
    """What the model said before ``gw``'s deadline, or ``None``.

    ``None`` is not an edge case. ``ADVICE_HISTORY_KEEP`` is 20 runs across
    all gameweeks, so by October GW1's advice is gone and its ledger row is
    marked ``no_advice`` with every lane null — null, not zero, because "the
    model had no opinion" and "the model agreed with me" are different facts
    and only one of them is a grade (spec G2).
    """
    payload = latest_run_per_gw().get(int(gw))
    if payload is None:
        return None
    captain = (payload.get("captain") or {}).get("code")
    vice = (payload.get("vice") or {}).get("code")
    chip = next((str(row.get("chip")) for row in payload.get("chip_table") or []
                 if isinstance(row, dict) and row.get("play_now")), None)
    names = {int(p["code"]): str(p.get("name", p["code"]))
             for key in ("xi", "bench", "buys", "sells")
             for p in payload.get(key) or []
             if isinstance(p, dict) and p.get("code") is not None}
    positions = {int(p["code"]): str(p.get("position", ""))
                 for key in ("xi", "bench", "buys", "sells")
                 for p in payload.get(key) or []
                 if isinstance(p, dict) and p.get("code") is not None}
    return {
        "xi": _codes(payload.get("xi")),
        "bench": _codes(payload.get("bench")),
        "captain": None if captain is None else int(captain),
        "vice": None if vice is None else int(vice),
        "buys": _codes(payload.get("buys")),
        "sells": _codes(payload.get("sells")),
        "hits": int(payload.get("hits") or 0),
        "chip": chip,
        "names": names,
        "positions": positions,
        "post_deadline": bool(payload.get("post_deadline")),
    }


def my_decisions(gw: int, *, season: str, entry_id: int,
                 raw_dir=None) -> dict | None:
    """What I actually did in ``gw``, off the bank, or ``None``.

    Off the bank and never off the API: ``run_review`` banks first and grades
    second, so this function is a pure read and a gameweek nobody banked is a
    gameweek nobody grades (spec G2).

    ``xi`` is ``position`` 1-11 in that order and ``bench`` is 12-15 in that
    order, because bench order is one of the four graded lanes and a set
    would throw the lane away. The armband comes from ``is_captain`` rather
    than from the multiplier, which is 3 under a triple captain and 1 under a
    bench boost.
    """
    picks = load_my_gw(season, entry_id, gw, raw_dir)
    if picks is None:
        return None
    history = load_my_history(season, entry_id, raw_dir)
    row = gw_history_row(history, gw) or {}
    code_of = code_of_element()

    ordered, unresolved = [], 0
    for pick in picks:
        try:
            slot = int(pick["position"])
            element = int(pick["element"])
        except (KeyError, TypeError, ValueError):
            unresolved += 1
            continue
        code = code_of.get(element)
        if code is None:
            unresolved += 1
            continue
        ordered.append((slot, int(code), bool(pick.get("is_captain")),
                        bool(pick.get("is_vice_captain"))))
    ordered.sort(key=lambda r: r[0])

    notices = []
    if unresolved:
        notices.append(
            f"{unresolved} pick could not be resolved to a player and was "
            f"dropped from the grade" if unresolved == 1 else
            f"{unresolved} picks could not be resolved to players and were "
            f"dropped from the grade")
    cost = int(row.get("event_transfers_cost", 0) or 0)
    return {
        "xi": [code for slot, code, _, _ in ordered if slot <= XI_SIZE],
        "bench": [code for slot, code, _, _ in ordered if slot > XI_SIZE],
        "captain": next((c for _, c, cap, _ in ordered if cap), None),
        "vice": next((c for _, c, _, vc in ordered if vc), None),
        "chip": chip_for_gw(history, gw),
        "hits": cost // 4,
        "official_gross": (int(row["points"]) if row.get("points") is not None
                           else None),
        "official_cost": cost,
        "points_on_bench": (int(row["points_on_bench"])
                            if row.get("points_on_bench") is not None
                            else None),
        "transfers": my_transfers_for_gw(
            load_my_transfers(season, entry_id, raw_dir), gw),
        "notices": notices,
    }
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_review_inputs.py tests/test_web_journal.py`
  Expected: `18 passed` in the new file, and the journal router suite green and unmodified.

- [ ] **Commit.**

```bash
git add src/gaffer/review.py tests/test_review_inputs.py && git commit -m "$(cat <<'EOF'
feat: the review's actuals frame and its two decision readers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — F2: the four lanes, the labels and the reconciliation gate

**Files:**
- Modify `src/gaffer/review.py` (append the scoring helpers, the lane builders, `label_for`, `grade_gw`; extend `__all__`)
- Create `tests/test_review_grades.py`

The pre-registered taxonomy (spec D5), stated once here so every later task
means the same thing by it:

| lane | what varies | what is held at mine |
| --- | --- | --- |
| `transfers` | my transfer set → the model's | armband, bench order, chip |
| `captaincy` | my armband → the model's | squad, bench order, chip |
| `bench` | my bench order → the model's | squad, armband, chip |
| `chip` | my chip → the model's `play_now` | squad, armband, bench order |

One thing varies per lane. A lane that cannot be built — the model's captain
is not in my eleven, the model sold a player I never owned, either side played
a wildcard — is `null` with a note, never zero.

- [ ] **Write the failing test.** Create `tests/test_review_grades.py`:

```python
"""The four lanes, the five labels, and the gate that says the arithmetic is
FPL's arithmetic.

Every squad in here is small and hand-scored, so a failure names a rule rather
than a number. The actuals frame is the contract ``backtest.score_gw`` reads:
code, total points, minutes, position.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.review import (grade_gw_from, hindsight_gap, label_for,
                           lane_bench, lane_captaincy, lane_chip,
                           lane_transfers, pair_by_position, score_squad,
                           swap_slots)

# A legal fifteen: 2 GKP, 5 DEF, 5 MID, 3 FWD, codes 1..15. Two extras nobody
# starts with: 16 is the defender the model wanted and I never bought, 17 is
# the one I sold to fund my own move.
POS = {1: "GKP", 2: "GKP",
       3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
       8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
       13: "FWD", 14: "FWD", 15: "FWD",
       16: "DEF", 17: "DEF"}

PTS = {1: 6, 2: 1, 3: 2, 4: 5, 5: 1, 6: 0, 7: 9, 8: 12, 9: 3, 10: 2,
       11: 4, 12: 1, 13: 8, 14: 0, 15: 2, 16: 15, 17: 0}

MINS = {code: 90 for code in POS}
MINS[6] = 0          # a blank starter, so autosubs have something to do
MINS[14] = 0         # and a blank bench player, so they cannot use him
MINS[17] = 0


def actuals(points=None, minutes=None) -> pd.DataFrame:
    points = PTS if points is None else points
    minutes = MINS if minutes is None else minutes
    return pd.DataFrame([{"code": code, "total_points": points.get(code, 0),
                          "minutes": minutes.get(code, 0),
                          "position": POS[code]}
                         for code in sorted(POS)])


MY_XI = [1, 3, 4, 5, 6, 8, 9, 10, 11, 13, 15]
MY_BENCH = [2, 7, 12, 14]


def squad(**over) -> dict:
    base = {"xi": list(MY_XI), "bench": list(MY_BENCH), "captain": 8,
            "vice": 13, "hits": 0, "chip": None}
    base.update(over)
    return base


MODEL = {"xi": [1, 3, 4, 5, 16, 8, 9, 10, 11, 13, 15],
         "bench": [2, 12, 7, 14], "captain": 13, "vice": 8,
         "buys": [16], "sells": [6], "hits": 1, "chip": None,
         "names": {6: "Blank", 7: "Sub", 8: "Salah", 13: "Haaland",
                   16: "Guehi", 17: "Sold"},
         "positions": {6: "DEF", 7: "DEF", 8: "MID", 13: "FWD", 16: "DEF",
                       17: "DEF"},
         "post_deadline": False}

MY_SCORE = 66
"""My squad's real score, by hand: 6 blanks, so the first *legal* bench player
comes on — 2 is a keeper and would leave two in the eleven, 7 is a defender
and fits. That gives 1+3+4+5+7+8+9+10+11+13+15 =
6+2+5+1+9+12+3+2+4+8+2 = 54, plus 12 again for the armband on 8."""


def test_a_squad_scores_the_way_the_replay_scores_it():
    """``score_squad`` is a chip-aware wrapper over ``backtest.score_gw`` and
    adds no arithmetic of its own."""
    assert score_squad(actuals(), **squad()) == MY_SCORE


def test_the_triple_captain_triples_and_the_bench_boost_scores_fifteen():
    plain = score_squad(actuals(), **squad())
    assert score_squad(actuals(), **squad(chip="3xc")) == plain + PTS[8]
    # Under a bench boost there are no autosubs: 6 stays on and 7 is a
    # scorer in his own right, so the swap is undone and the bench added.
    boosted = score_squad(actuals(), **squad(chip="bboost"))
    assert boosted == plain - PTS[7] + PTS[6] + PTS[2] + PTS[7] + PTS[12] \
        + PTS[14]


def test_a_hit_costs_four_points_off_the_top():
    assert score_squad(actuals(), **squad(hits=2)) \
        == score_squad(actuals(), **squad()) - 8


def test_a_squad_with_no_armband_at_all_still_scores():
    """A snapshot with no captain flag is rare and must not be a crash."""
    assert score_squad(actuals(), **squad(captain=None, vice=None)) \
        == score_squad(actuals(), **squad()) - PTS[8]


def test_swapping_a_slot_keeps_the_player_where_he_sat():
    xi, bench = swap_slots(MY_XI, MY_BENCH, [(6, 16), (14, 17)])
    assert xi[4] == 16          # 6 sat fifth in the eleven; 16 sits there now
    assert bench == [2, 7, 12, 17]


def test_swapping_a_player_who_is_not_in_the_squad_is_none():
    """The signal the transfers lane needs: the model sold somebody I never
    owned, so there is no counterfactual to build and the lane is null."""
    assert swap_slots(MY_XI, MY_BENCH, [(99, 16)]) is None


def test_buys_and_sells_pair_up_by_position():
    assert pair_by_position([6], [16], MODEL["positions"]) == [(6, 16)]


def test_a_move_that_changes_the_shape_of_the_squad_does_not_pair():
    """Two out, two in, but a defender for a forward: FPL cannot do it and
    neither can the counterfactual."""
    assert pair_by_position([6, 8], [16, 13],
                            {6: "DEF", 8: "MID", 16: "DEF", 13: "FWD"}) is None


def test_the_transfers_lane_prices_my_move_against_the_models():
    """I made no transfer; the model would have paid four points to bring 16
    in for 6. My 66 comes from the autosub that partly covered the blank; the
    model's fifteen is 6+2+5+1+15+12+3+2+4+8+2 = 60, +12 for the armband,
    less the four-point hit = 68. So the model's week was two better."""
    lane = lane_transfers(squad(), MODEL, actuals(), my_transfers=[],
                          positions=MODEL["positions"])
    assert lane["delta_pts"] == -2
    assert lane["note"] is None


def test_the_transfers_lane_undoes_my_move_before_applying_the_models():
    """I sold 17 and bought 7 this week, for a hit. The counterfactual starts
    from the fifteen I owned *at the deadline* — with 17 back on the bench —
    and then applies the model's move to that, not to the squad I ended up
    with. My 66 becomes 62 once my own hit is charged; the model's is still
    68, so the lane is six against me."""
    lane = lane_transfers(
        squad(hits=1), MODEL, actuals(),
        my_transfers=[{"element_in": 7, "element_out": 17, "event": 2}],
        positions=MODEL["positions"], code_of={7: 7, 17: 17})
    assert lane["note"] is None
    assert lane["delta_pts"] == -6


def test_a_model_sale_i_never_owned_is_a_null_lane_not_a_zero_one():
    """"The model had no opinion I could have acted on" and "the model
    agreed with me" are different facts (spec G2)."""
    model = {**MODEL, "sells": [99], "buys": [16],
             "positions": {**MODEL["positions"], 99: "DEF"}}
    lane = lane_transfers(squad(), model, actuals(), my_transfers=[],
                          positions=model["positions"])
    assert lane["delta_pts"] is None
    assert "was not in your squad" in lane["note"]


def test_the_captaincy_lane_is_my_armband_against_the_models():
    """I captained 8 (12 pts); the model said 13 (8 pts). I am four up."""
    lane = lane_captaincy(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 4
    assert lane["mine"] == "Salah"
    assert lane["model"] == "Haaland"


def test_captaining_the_same_player_as_the_model_is_aligned():
    lane = lane_captaincy(squad(captain=13), MODEL, actuals())
    assert lane["delta_pts"] == 0
    assert lane["aligned"] is True


def test_a_model_captain_who_is_not_in_my_eleven_is_a_null_lane():
    """You cannot captain a player you do not own, so there is no squad to
    score — the honest answer is no grade."""
    lane = lane_captaincy(squad(), {**MODEL, "captain": 99}, actuals())
    assert lane["delta_pts"] is None
    assert "was not in your eleven" in lane["note"]


def test_the_bench_lane_prices_the_order_the_autosubs_walked():
    """My bench is [2, 7, 12, 14] and 6 blanks, so 7 comes on for nine. The
    model's order puts 12 ahead of 7, and 12 is a midfielder who also fits —
    so the model's ordering brings on a one-pointer instead."""
    lane = lane_bench(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 8


def test_a_bench_order_that_changes_nothing_is_a_zero_lane_not_a_null_one():
    """Nobody blanked, so no autosub fired. Zero is a real grade here: the
    ordering was tested and cost nothing."""
    lane = lane_bench(squad(), MODEL, actuals(minutes={c: 90 for c in POS}))
    assert lane["delta_pts"] == 0
    assert lane["note"] is None


def test_the_chip_lane_prices_holding_against_playing():
    """The model said bench boost; I held. The boost is worth the bench,
    less the autosub it cancels."""
    lane = lane_chip(squad(), {**MODEL, "chip": "bboost"}, actuals())
    assert lane["delta_pts"] == score_squad(actuals(), **squad()) \
        - score_squad(actuals(), **squad(chip="bboost"))


def test_holding_when_the_model_held_is_aligned():
    lane = lane_chip(squad(), MODEL, actuals())
    assert lane["delta_pts"] == 0
    assert lane["aligned"] is True


def test_a_wildcard_on_either_side_is_a_null_chip_lane():
    """A wildcard changes the fifteen, not the way the fifteen scores, so
    there is no same-squad comparison to make."""
    lane = lane_chip(squad(chip="wildcard"), MODEL, actuals())
    assert lane["delta_pts"] is None
    assert "changes the squad" in lane["note"]


def test_the_labels_are_the_pre_registered_bands():
    assert label_for(6.0, 0.4, aligned=False) == "Brilliant"
    assert label_for(6.0, -0.4, aligned=False) == "Good"
    assert label_for(6.0, None, aligned=False) == "Good"
    assert label_for(2.0, None, aligned=False) == "Good"
    assert label_for(0.5, None, aligned=False) == "Aligned"
    assert label_for(-0.5, None, aligned=False) == "Aligned"
    assert label_for(-2.0, None, aligned=False) == "Inaccuracy"
    assert label_for(-9.0, None, aligned=False) == "Blunder"
    assert label_for(None, None, aligned=False) is None


def test_following_the_model_is_aligned_however_it_turned_out():
    """A lane where I made the model's own choice cannot be a blunder. The
    delta is zero by construction; the flag says *why* it is zero."""
    assert label_for(0.0, None, aligned=True) == "Aligned"


def test_the_hindsight_gap_is_the_selection_ev_left_on_the_table():
    assert hindsight_gap(74, 61) == 13


def test_the_grade_reconciles_against_the_official_score():
    """Spec D7: ``score_gw`` on my real squad must equal FPL's own
    ``points - event_transfers_cost``. ``points`` is gross of the hit."""
    mine = {**squad(hits=1),
            "official_gross": score_squad(actuals(), **squad(hits=0)),
            "official_cost": 4, "points_on_bench": 0, "transfers": [],
            "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["my_points"] == mine["official_gross"] - 4
    assert row["official_points"] == mine["official_gross"] - 4
    assert row["reconciled"] is True


def test_a_mismatch_is_flagged_with_both_numbers_and_never_swallowed():
    """The known simplified-autosub caveats (backtest.py:36-38) are the
    expected source; the flag is how their real frequency gets measured."""
    mine = {**squad(), "official_gross": 999, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["reconciled"] is False
    assert row["official_points"] == 999
    assert row["my_points"] != 999


def test_an_absent_official_score_is_unreconciled_rather_than_wrong():
    mine = {**squad(), "official_gross": None, "official_cost": 0,
            "points_on_bench": None, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["reconciled"] is None
    assert "no official score" in " ".join(row["notices"])


def test_the_grade_carries_all_four_lanes_in_the_registered_order():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert [lane["lane"] for lane in row["lanes"]] \
        == ["transfers", "captaincy", "bench", "chip"]


def test_accuracy_is_capped_at_a_hundred_when_i_beat_the_model():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, {**MODEL, "captain": 6, "buys": [],
                                  "sells": [], "hits": 0,
                                  "bench": list(MY_BENCH)}, actuals())
    assert row["accuracy"] == 100


def test_accuracy_is_null_when_there_was_no_advice_to_measure_against():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, None, actuals())
    assert row["no_advice"] is True
    assert row["accuracy"] is None
    assert row["model_points"] is None
    assert all(lane["delta_pts"] is None for lane in row["lanes"])


def test_a_model_move_i_skipped_that_hauled_is_a_miss_row():
    """Spec D5's Miss: the model flagged 16, I kept 6, and 16 beat him by
    fifteen — over the six-point bar."""
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["misses"] == [{"code": 16, "name": "Guehi", "over": "Blank",
                              "gain": 15}]


def test_a_model_move_i_actually_made_is_never_a_miss():
    mine = {**squad(xi=[1, 3, 4, 5, 16, 8, 9, 10, 11, 13, 15]),
            "official_gross": 0, "official_cost": 0, "points_on_bench": 0,
            "transfers": [], "notices": []}
    assert grade_gw_from(2, mine, MODEL, actuals())["misses"] == []


def test_a_model_move_that_returned_little_is_not_a_miss():
    small = {**PTS, 16: 4}
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    assert grade_gw_from(2, mine, MODEL, actuals(points=small))["misses"] == []


def test_the_late_advice_caveat_rides_on_the_row():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, {**MODEL, "post_deadline": True}, actuals())
    assert row["post_deadline"] is True


def test_the_bench_points_we_compute_sit_beside_the_official_ones():
    """Spec D5's EV ledger reconciles our bench arithmetic against FPL's own
    rather than trusting either alone."""
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 11, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["points_on_bench"] == 11
    assert row["our_bench_points"] == PTS[2] + PTS[7] + PTS[12] + PTS[14]


def test_the_hindsight_row_names_the_best_eleven_i_owned():
    mine = {**squad(), "official_gross": 0, "official_cost": 0,
            "points_on_bench": 0, "transfers": [], "notices": []}
    row = grade_gw_from(2, mine, MODEL, actuals())
    assert row["hindsight"]["points"] >= row["my_points"]
    assert row["hindsight"]["gap"] == row["hindsight"]["points"] \
        - row["my_points"]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_review_grades.py`
  Expected: collection error — `ImportError: cannot import name 'score_squad' from 'gaffer.review'`.

- [ ] **Write the implementation, part 1: the scoring helpers.** Append to `src/gaffer/review.py`:

```python
CHIP_SCORING = {"bboost": (2, True), "3xc": (3, False)}
"""``chip -> (captain multiplier, bench boost)`` for the two chips that change
how a *fixed* fifteen scores. Everything else scores the ordinary way."""

SQUAD_CHIPS = ("wildcard", "freehit")
"""Chips that change *which* fifteen you own rather than how it scores. There
is no same-squad counterfactual for one of these, so the chip lane declines to
grade a week either side played one (see :func:`lane_chip`)."""

NO_PLAYER = -1
"""``score_gw`` looks the armband up in a points dict, so an absent captain
has to be a code that cannot match. A squad with no captain flag at all is
rare and must not be a crash."""

MISS_BAR = 6
"""Points a move I skipped must have returned *over its replacement* before
the review calls it a Miss (spec D5). Six is a goal and change: below it the
model was right by less than one bounce of the ball."""

LANES = ("transfers", "captaincy", "bench", "chip")
"""The pre-registered order. Stable, because a season ledger whose columns
move is a ledger nobody can read across weeks (CONVENTIONS.md §2)."""


def score_squad(actuals: pd.DataFrame, *, xi, bench, captain, vice, hits,
                chip=None) -> int:
    """One squad's real points: :func:`score_gw` with the chip decoded.

    Adds no arithmetic. The autosubs, the vice fallback and the four points a
    hit costs are all ``backtest``'s, which is the point — the review grades
    against the same scorer the season replay is measured with, so a lane
    delta and a replay delta are the same kind of number.
    """
    mult, boost = CHIP_SCORING.get(str(chip or ""), (2, False))
    return int(score_gw(
        actuals, list(xi), list(bench),
        NO_PLAYER if captain is None else int(captain),
        NO_PLAYER if vice is None else int(vice),
        int(hits), captain_mult=mult, bench_boost=boost))


def swap_slots(xi, bench, pairs) -> tuple[list[int], list[int]] | None:
    """Replace each ``out`` with its ``in`` *where the out was sitting*.

    Slot-preserving on purpose. A counterfactual that rebuilt the eleven from
    scratch would be answering a selection question inside a transfer lane,
    and the incoming player would quietly inherit the best slot available
    rather than the one his predecessor held.

    ``None`` when an ``out`` is in neither list: that is the model naming a
    player I never owned, and there is no squad to score.
    """
    xi, bench = list(xi), list(bench)
    for out_code, in_code in pairs:
        if out_code in xi:
            xi[xi.index(out_code)] = in_code
        elif out_code in bench:
            bench[bench.index(out_code)] = in_code
        else:
            return None
    return xi, bench


def pair_by_position(outs, ins, positions) -> list[tuple[int, int]] | None:
    """Match sells to buys by position, in the order each was listed.

    FPL's own constraint: a transfer swaps like for like, so a two-move week
    is two independent position-preserving swaps and the pairing is
    determined. ``None`` when the two sides do not have the same positional
    shape — a squad that is 4 defenders after the move and 5 before it is not
    a squad, and grading against one would be grading against a fiction.
    """
    outs, ins = list(outs), list(ins)
    if len(outs) != len(ins):
        return None
    pool: dict[str, list[int]] = {}
    for code in ins:
        pool.setdefault(str(positions.get(int(code), "")), []).append(int(code))
    pairs: list[tuple[int, int]] = []
    for code in outs:
        bucket = pool.get(str(positions.get(int(code), "")))
        if not bucket:
            return None
        pairs.append((int(code), bucket.pop(0)))
    return pairs


def hindsight_gap(best: int, actual: int) -> int:
    """Selection EV left on the table: the best legal eleven, less mine."""
    return int(best) - int(actual)


def label_for(delta_pts, delta_pwin, *, aligned: bool) -> str | None:
    """The pre-registered band for one lane (spec D5).

    ``None`` for an ungraded lane, which is not a band and must never be
    rendered as one. ``aligned`` short-circuits everything: a lane where I
    made the model's own choice is Aligned however the week turned out, and
    calling it a Blunder because the model's own pick blanked would be
    grading the outcome instead of the decision.

    Brilliant needs *both* currencies. A move that gained four points and cost
    title odds is a Good week for the points column and a bad week for the
    thing being played for, so with no Δwin% available the band tops out at
    Good — the honest answer when half the evidence is missing.
    """
    if delta_pts is None:
        return None
    if aligned:
        return "Aligned"
    value = float(delta_pts)
    if value >= 4 and (delta_pwin or 0.0) > 0:
        return "Brilliant"
    if value >= 1:
        return "Good"
    if value <= -4:
        return "Blunder"
    if value <= -1:
        return "Inaccuracy"
    return "Aligned"
```

- [ ] **Write the implementation, part 2: the four lane builders.** Append to
  `src/gaffer/review.py`:

```python
def _lane(name: str, cf: dict | None, mine: dict, actuals: pd.DataFrame, *,
          note: str | None, aligned: bool, mine_label: str,
          model_label: str) -> dict:
    """One graded lane. ``cf`` is my squad with exactly one thing changed.

    Both sides are scored with :func:`score_squad`, so the delta is "my
    choice minus the model's, both on what really happened". ``None`` for
    ``cf`` means the lane could not be built and the delta is null with the
    note saying why — spec G2's "null, not zero".
    """
    if cf is None:
        return {"lane": name, "delta_pts": None, "delta_pwin": None,
                "label": None, "aligned": False, "mine": mine_label,
                "model": model_label, "note": note}
    delta = score_squad(actuals, **mine) - score_squad(actuals, **cf)
    return {"lane": name, "delta_pts": int(delta), "delta_pwin": None,
            "label": label_for(delta, None, aligned=aligned),
            "aligned": bool(aligned), "mine": mine_label,
            "model": model_label, "note": note, "cf": cf}


def _name(names: dict, code) -> str:
    if code is None:
        return "none"
    return str((names or {}).get(int(code), code))


def lane_transfers(mine: dict, model: dict, actuals: pd.DataFrame, *,
                   my_transfers: list[dict], positions: dict,
                   code_of: dict | None = None) -> dict:
    """My transfer set against the model's, hits included.

    Two swaps, in order. First my own week is *undone* — each player I
    brought in goes back to the one I sold, in his slot — because the
    counterfactual starts from the fifteen I owned at the deadline and not
    from the one I ended the week with. Then the model's moves are applied to
    that pre-transfer squad.

    The armband follows the squad: if the model's counterfactual sells the
    player I captained, the armband goes to the model's captain when he is in
    the resulting eleven and to my vice otherwise, which is FPL's own
    fallback rather than a rule invented here.
    """
    code_of = code_of or {}
    names, note = model.get("names") or {}, None
    label_mine = ", ".join(_name(names, c) for c in model.get("sells") or []) \
        or "no move"
    undo = []
    for row in my_transfers or []:
        try:
            got = int(code_of.get(int(row["element_in"]), row["element_in"]))
            gone = int(code_of.get(int(row["element_out"]), row["element_out"]))
        except (KeyError, TypeError, ValueError):
            continue
        undo.append((got, gone))
    pre = swap_slots(mine["xi"], mine["bench"], undo)
    label_model = " / ".join(
        f"{_name(names, out)}->{_name(names, got)}"
        for out, got in zip(model.get("sells") or [], model.get("buys") or [])
    ) or "no move"
    mine_label = " / ".join(
        f"{_name(names, out)}->{_name(names, got)}" for got, out in undo
    ) or "no move"
    if pre is None:
        return _lane("transfers", None, mine, actuals,
                     note="a player you transferred in is not in your banked "
                          "squad, so the pre-deadline fifteen could not be "
                          "rebuilt",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    pairs = pair_by_position(model.get("sells") or [],
                             model.get("buys") or [], positions)
    if pairs is None:
        return _lane("transfers", None, mine, actuals,
                     note="the model's moves do not pair up by position, so "
                          "there is no legal counterfactual squad",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    swapped = swap_slots(pre[0], pre[1], pairs)
    if swapped is None:
        return _lane("transfers", None, mine, actuals,
                     note=f"the model sold {label_mine}, who was not in your "
                          f"squad — there is no counterfactual to score",
                     aligned=False, mine_label=mine_label,
                     model_label=label_model)
    xi, bench = swapped
    captain = mine["captain"] if mine["captain"] in xi + bench else None
    if captain is None:
        captain = model.get("captain") if model.get("captain") in xi \
            else mine["vice"]
    cf = {"xi": xi, "bench": bench, "captain": captain,
          "vice": mine["vice"] if mine["vice"] in xi + bench else captain,
          "hits": int(model.get("hits") or 0), "chip": mine["chip"]}
    aligned = (sorted(xi + bench) == sorted(mine["xi"] + mine["bench"])
               and int(model.get("hits") or 0) == int(mine["hits"]))
    return _lane("transfers", cf, mine, actuals, note=None, aligned=aligned,
                 mine_label=mine_label, model_label=label_model)


def lane_captaincy(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My armband against the model's, on my own eleven.

    Only comparable when the model's captain is in my eleven. You cannot
    captain a player you did not field, so a model captain I never owned is
    not a decision I declined to take — it is a decision that was never
    available, and grading it would charge me for a squad I could not have
    had. (That cost belongs to the transfers lane, where it already is.)
    """
    names = model.get("names") or {}
    mine_label, model_label = (_name(names, mine["captain"]),
                               _name(names, model.get("captain")))
    if model.get("captain") is None or int(model["captain"]) not in mine["xi"]:
        return _lane("captaincy", None, mine, actuals,
                     note="the model's captain was not in your eleven",
                     aligned=False, mine_label=mine_label,
                     model_label=model_label)
    vice = model.get("vice")
    cf = {**mine, "captain": int(model["captain"]),
          "vice": int(vice) if vice in mine["xi"] else mine["vice"]}
    aligned = mine["captain"] == int(model["captain"])
    return _lane("captaincy", cf, mine, actuals, note=None, aligned=aligned,
                 mine_label=mine_label, model_label=model_label)


def lane_bench(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My bench order against the model's, on my own fifteen.

    The model benched its own players, so its ordering is applied as a
    *ranking* over mine: my bench players it named, in its order, then the
    rest in mine. A week where nobody blanked scores zero on both sides —
    which is a real grade and not a missing one, because the ordering was
    tested by the week and cost nothing.
    """
    ranked = [c for c in (model.get("bench") or []) if c in mine["bench"]]
    order = ranked + [c for c in mine["bench"] if c not in ranked]
    names = model.get("names") or {}
    cf = {**mine, "bench": order}
    return _lane("bench", cf, mine, actuals, note=None,
                 aligned=order == list(mine["bench"]),
                 mine_label=", ".join(_name(names, c) for c in mine["bench"]),
                 model_label=", ".join(_name(names, c) for c in order))


def lane_chip(mine: dict, model: dict, actuals: pd.DataFrame) -> dict:
    """My chip decision against the model's ``play_now``.

    Bench boost and triple captain change how a fixed fifteen scores, so both
    sides are the same squad under two rulebooks and the delta is exact. A
    wildcard or a free hit changes *which* fifteen you own; there is no
    same-squad comparison, and inventing the squad a wildcard would have
    bought is a whole solve with a different budget — out of scope this cycle
    (spec §6) and null here rather than guessed.
    """
    mine_chip, model_chip = mine["chip"], model.get("chip")
    labels = (str(mine_chip or "none"), str(model_chip or "none"))
    if str(mine_chip or "") in SQUAD_CHIPS or str(model_chip or "") \
            in SQUAD_CHIPS:
        return _lane("chip", None, mine, actuals,
                     note="a wildcard or free hit changes the squad, not the "
                          "way it scores — there is no same-squad "
                          "counterfactual",
                     aligned=False, mine_label=labels[0],
                     model_label=labels[1])
    cf = {**mine, "chip": model_chip}
    return _lane("chip", cf, mine, actuals, note=None,
                 aligned=str(mine_chip or "") == str(model_chip or ""),
                 mine_label=labels[0], model_label=labels[1])
```

- [ ] **Write the implementation, part 3: `grade_gw_from`.** Append to
  `src/gaffer/review.py`:

```python
def _misses(mine: dict, model: dict, actuals: pd.DataFrame) -> list[dict]:
    """Moves the model flagged, I did not make, and that hauled anyway.

    Not a fifth lane: the transfers lane already prices the whole set against
    the whole set, and this is the human-readable line item inside it — "you
    were told about Guehi and he returned nine over the man you kept". Paired
    by position against the model's own sell, so the number is a *difference*
    and not a scoreline; an unpaired buy is skipped rather than compared
    against nothing.
    """
    owned = set(mine["xi"]) | set(mine["bench"])
    pairs = pair_by_position(model.get("sells") or [],
                             model.get("buys") or [],
                             model.get("positions") or {}) or []
    points = dict(zip(actuals["code"], actuals["total_points"]))
    names = model.get("names") or {}
    out = []
    for sold, bought in pairs:
        if bought in owned or sold not in owned:
            continue
        gain = int(points.get(bought, 0) or 0) - int(points.get(sold, 0) or 0)
        if gain >= MISS_BAR:
            out.append({"code": int(bought), "name": _name(names, bought),
                        "over": _name(names, sold), "gain": int(gain)})
    return out


def hindsight_xi(squad15, actuals: pd.DataFrame):
    """The best legal eleven and armband out of a fifteen, by actual points.

    Exhaustive: fifteen choose eleven is 1365 combinations and the formation
    check is a Counter, so the honest answer is cheaper than any clever one.
    Bench-boost and hit arithmetic are deliberately excluded — this measures
    *selection*, and folding a chip into it would price two decisions as one.

    Returns ``(xi, captain, points)``; ``([], None, 0)`` for a squad too small
    to field a legal eleven, which is what a partially-resolved bank looks
    like.
    """
    from itertools import combinations

    from gaffer.backtest import _formation_legal

    codes = [int(c) for c in squad15]
    points = dict(zip(actuals["code"], actuals["total_points"]))
    pos = dict(zip(actuals["code"], actuals["position"]))
    best: tuple[list[int], int | None, int] = ([], None, 0)
    for combo in combinations(codes, 11):
        if not _formation_legal([str(pos.get(c, "MID")) for c in combo]):
            continue
        armband = max(combo, key=lambda c: int(points.get(c, 0) or 0))
        total = sum(int(points.get(c, 0) or 0) for c in combo) \
            + int(points.get(armband, 0) or 0)
        if total > best[2]:
            best = (list(combo), int(armband), int(total))
    return best


def grade_gw_from(gw: int, mine: dict, model: dict | None,
                  actuals: pd.DataFrame) -> dict:
    """One ledger row from decisions already read. Pure; no I/O, no network.

    Split out from :func:`grade_gw` so the taxonomy can be tested against
    hand-scored squads rather than against a filesystem, and so the Δwin%
    pricing in Task 5 has exactly one place to attach.

    ``model is None`` — the advice for this gameweek has been pruned (spec
    D2) — gives a ``no_advice`` row: every lane null, no accuracy, and the
    reconciliation and hindsight still computed, because those do not need
    the model at all and are the half of the row that stays true forever.
    """
    my_points = score_squad(actuals, **{k: mine[k] for k in
                                        ("xi", "bench", "captain", "vice",
                                         "hits", "chip")})
    my_squad = {k: mine[k] for k in ("xi", "bench", "captain", "vice", "hits",
                                     "chip")}
    notices = list(mine.get("notices") or [])

    gross, cost = mine.get("official_gross"), int(mine.get("official_cost", 0))
    if gross is None:
        official, reconciled = None, None
        notices.append("no official score for this gameweek — the entry "
                       "history was not banked, so nothing reconciled")
    else:
        official = int(gross) - cost
        reconciled = official == my_points

    bench_points = sum(
        int(p) for c, p in zip(actuals["code"], actuals["total_points"])
        if int(c) in set(mine["bench"]))
    best_xi, best_captain, best_points = hindsight_xi(
        list(mine["xi"]) + list(mine["bench"]), actuals)

    row = {
        "gw": int(gw),
        "no_advice": model is None,
        "post_deadline": bool((model or {}).get("post_deadline")),
        "my_points": int(my_points),
        "official_points": official,
        "official_gross": None if gross is None else int(gross),
        "hits": int(mine["hits"]),
        "reconciled": reconciled,
        "chip": mine["chip"],
        "model_chip": (model or {}).get("chip"),
        "points_on_bench": mine.get("points_on_bench"),
        "our_bench_points": int(bench_points),
        "hindsight": {"points": int(best_points), "xi": best_xi,
                      "captain": best_captain,
                      "gap": hindsight_gap(best_points, my_points)},
        "misses": [],
        "notices": notices,
    }

    if model is None:
        row["lanes"] = [{"lane": name, "delta_pts": None, "delta_pwin": None,
                         "label": None, "aligned": False, "mine": None,
                         "model": None,
                         "note": "no banked advice survives for this "
                                 "gameweek"} for name in LANES]
        row["model_points"] = None
        row["accuracy"] = None
        return row

    positions = model.get("positions") or {}
    lanes = [
        lane_transfers(my_squad, model, actuals,
                       my_transfers=mine.get("transfers") or [],
                       positions=positions,
                       code_of=mine.get("code_of") or {}),
        lane_captaincy(my_squad, model, actuals),
        lane_bench(my_squad, model, actuals),
        lane_chip(my_squad, model, actuals),
    ]

    # The composite: my squad with every *comparable* lane taken from the
    # model at once. Applied in the registered order because the lanes
    # compose — a transfer can move the player the armband is on — and an
    # incomparable lane leaves its part of the squad at mine rather than
    # dropping out of the denominator, so accuracy always compares two whole
    # squads.
    composite = dict(my_squad)
    for lane in lanes:
        cf = lane.get("cf")
        if cf is None:
            continue
        if lane["lane"] == "transfers":
            composite = {**composite, "xi": cf["xi"], "bench": cf["bench"],
                         "captain": cf["captain"], "vice": cf["vice"],
                         "hits": cf["hits"]}
        elif lane["lane"] == "captaincy" and cf["captain"] in composite["xi"]:
            composite = {**composite, "captain": cf["captain"],
                         "vice": cf["vice"]}
        elif lane["lane"] == "bench":
            ranked = [c for c in (model.get("bench") or [])
                      if c in composite["bench"]]
            composite = {**composite, "bench": ranked + [
                c for c in composite["bench"] if c not in ranked]}
        elif lane["lane"] == "chip":
            composite = {**composite, "chip": cf["chip"]}
    model_points = score_squad(actuals, **composite)

    row["lanes"] = [{k: v for k, v in lane.items() if k != "cf"}
                    for lane in lanes]
    row["model_points"] = int(model_points)
    # Floored at 1 so a gameweek where the model's own squad scored nothing
    # cannot divide by zero, and capped at 100 so beating the model reads as
    # a perfect week — the surplus is the Brilliant lane's story, not the
    # dial's (spec D5).
    row["accuracy"] = int(min(100, round(100 * my_points
                                         / max(model_points, 1))))
    row["misses"] = _misses(my_squad, model, actuals)
    return row
```

- [ ] **Extend `__all__`.** Replace the `__all__` list at the top of
  `src/gaffer/review.py` with:

```python
__all__ = ["ACTUAL_COLS", "CHIP_SCORING", "LANES", "MISS_BAR", "SQUAD_CHIPS",
           "actuals_for_gw", "code_of_element", "grade_gw_from",
           "hindsight_gap", "hindsight_xi", "label_for", "lane_bench",
           "lane_captaincy", "lane_chip", "lane_transfers", "model_decisions",
           "my_decisions", "pair_by_position", "reviewable_gws", "score_gw",
           "score_squad", "swap_slots"]
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_review_grades.py tests/test_review_inputs.py tests/test_backtest.py`
  Expected: `34 passed` in the grades file, `18 passed` in the inputs file, and the backtest suite green and unmodified. If `tests/test_backtest.py` fails, something reached into `backtest.py` — revert it; that file is import-only (spec §5).

- [ ] **Commit.**

```bash
git add src/gaffer/review.py tests/test_review_grades.py && git commit -m "$(cat <<'EOF'
feat: the four decision lanes, their labels and the reconciliation gate

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — F2: the hindsight eleven, on its own

**Files:**
- Create `tests/test_review_hindsight.py`

`hindsight_xi` landed in Task 3 because `grade_gw_from` calls it — the code
argued against the suggested ordering and won. What it never got was a suite
of its own, and it is the one function in the module whose answer nobody can
check by eye against a ledger row. This task supplies it. No implementation
step: if a test here fails, the bug is in Task 3's `hindsight_xi` and that is
where it gets fixed.

- [ ] **Write the test.** Create `tests/test_review_hindsight.py`:

```python
"""The best eleven I could have fielded, chosen with hindsight.

The gap between this and what I actually scored is "selection EV left on the
table" (spec D5) — the one number in the ledger that owes nothing to the
model and is therefore true whatever happened to the advice history.

Fifteen choose eleven is 1365, so the search is exhaustive and the tests can
ask for the *exact* best rather than for a plausible one.
"""

from __future__ import annotations

import pandas as pd

from gaffer.review import hindsight_xi

POS = {1: "GKP", 2: "GKP",
       3: "DEF", 4: "DEF", 5: "DEF", 6: "DEF", 7: "DEF",
       8: "MID", 9: "MID", 10: "MID", 11: "MID", 12: "MID",
       13: "FWD", 14: "FWD", 15: "FWD"}

SQUAD = list(POS)


def frame(points: dict, minutes: dict | None = None) -> pd.DataFrame:
    minutes = minutes or {code: 90 for code in POS}
    return pd.DataFrame([{"code": code, "total_points": points.get(code, 0),
                          "minutes": minutes.get(code, 0),
                          "position": POS[code]}
                         for code in SQUAD])


def test_the_best_eleven_is_legal_by_formation():
    """Not simply the eleven highest scorers: FPL needs one keeper, three
    defenders and a forward, and an unconstrained pick would field five
    midfielders and no goalkeeper the moment midfielders had a good week."""
    points = {code: 10 for code in (8, 9, 10, 11, 12)}
    xi, _, _ = hindsight_xi(SQUAD, frame(points))
    kinds = [POS[c] for c in xi]
    assert kinds.count("GKP") == 1
    assert 3 <= kinds.count("DEF") <= 5
    assert 2 <= kinds.count("MID") <= 5
    assert 1 <= kinds.count("FWD") <= 3
    assert len(xi) == 11


def test_the_armband_goes_to_the_best_scorer_in_the_chosen_eleven():
    points = {1: 2, 3: 3, 4: 3, 5: 3, 8: 4, 9: 4, 13: 20}
    xi, captain, _ = hindsight_xi(SQUAD, frame(points))
    assert captain == 13
    assert 13 in xi


def test_the_total_counts_the_captain_twice():
    """One goalkeeper at 5 and everyone else at 1: the best legal eleven is
    5 + ten ones, and the armband on the keeper adds his five again."""
    points = {code: 1 for code in SQUAD}
    points[1] = 5
    _, captain, total = hindsight_xi(SQUAD, frame(points))
    assert captain == 1
    assert total == 5 + 10 + 5


def test_a_player_the_actuals_frame_has_never_heard_of_scores_nothing():
    """A player who did not feature at all is worth zero, which is exactly
    what he scored — the same rule ``score_gw`` applies."""
    xi, _, total = hindsight_xi(SQUAD + [999], frame({13: 9}))
    assert total == 9 + 9
    assert 999 not in xi


def test_minutes_do_not_constrain_the_hindsight_pick():
    """No autosubs here, deliberately. Autosubs are a *consequence* of a
    bench order; this measures the selection I could have made at the
    deadline, when a blank was still avoidable by picking somebody else."""
    points = {code: 1 for code in SQUAD}
    points[13] = 20
    _, captain, _ = hindsight_xi(SQUAD, frame(points, minutes={13: 0}))
    assert captain == 13


def test_a_squad_too_small_to_field_a_legal_eleven_is_an_empty_answer():
    """A partially-resolved bank — half its picks were players who have since
    left the game — must give back "no answer", not a nine-man eleven."""
    assert hindsight_xi([1, 3, 4, 8], frame({})) == ([], None, 0)


def test_the_hindsight_pick_never_scores_below_the_eleven_i_played():
    """The definitional property, and the one that makes the gap readable as
    a loss rather than as noise."""
    from gaffer.review import score_squad

    points = {1: 2, 2: 1, 3: 6, 4: 1, 5: 0, 6: 9, 7: 2, 8: 11, 9: 1, 10: 3,
              11: 0, 12: 7, 13: 4, 14: 8, 15: 1}
    actuals = frame(points)
    played = score_squad(actuals, xi=[1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15],
                         bench=[2, 6, 7, 12], captain=8, vice=13, hits=0)
    _, _, best = hindsight_xi(SQUAD, actuals)
    assert best >= played
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_review_hindsight.py`
  Expected: `7 passed`. A failure here is a bug in Task 3's `hindsight_xi`; fix
  the function, never the test.

- [ ] **Commit.**

```bash
git add tests/test_review_hindsight.py && git commit -m "$(cat <<'EOF'
test: pin the hindsight eleven's formation, armband and floor

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — F2: pricing the lanes in title odds

**Files:**
- Modify `src/gaffer/review.py` (append `PWIN_LANES`, `picks_from_squad`, `price_lanes`, `grade_gw`; two lines inside `grade_gw_from`; extend `__all__`)
- Create `tests/test_review_pwin.py`

The second currency (spec D4). v8c's engine already rebuilds a past gameweek's
inputs from banked component parquets and already supports swapping one
entry's squad for a counterfactual — that is exactly what the what-if router
does (`web/routers/league_sim.py:289-293`), same seed, same `n`, paired.

Three facts to hold on to before writing any of it:

1. **Which gameweek's inputs.** `build_inputs(cfg, client, gw=N)` reads
   `reports/components_gw{N}.parquet` and takes every entry's squad from
   `max(1, N-1)`. Pricing GW N's decision therefore asks GW N's own question —
   "with the season's remaining weeks priced as they were at that deadline,
   what did this choice do to my odds". **GW1 has no `components_gw1.parquet`
   and never will**, so GW1's Δwin% is absent with a notice. That is not a bug
   to route around; it is the degradation the gate checks for.
2. **What Δwin% can see.** `league_sim.effective_picks` normalises a squad to
   *starters and one armband* — the bench scores nothing and chips are
   deliberately stripped, because a stored week's multipliers read as a rate
   would hand a bench-booster four extra players for the rest of the season.
   So the bench and chip lanes cannot move title odds *by construction*, and
   burning two Monte Carlo runs to rediscover that every week would be
   theatre. They are set to `0.0` with a note, and a test pins the reason.
3. **Isolation.** Every engine call sits inside one `try`. A dead client, an
   absent parquet, a league id nobody set — all degrade to points-only
   grading with a notice on the row.

- [ ] **Write the failing test.** Create `tests/test_review_pwin.py`:

```python
"""The second currency: what a decision did to my title odds.

A captaincy that cost two points and no ground is a different week from one
that cost two points and the league. Everything here is about the *pairing* —
same seed, same n, same drift, one squad swapped — and about what happens
when the engine cannot answer.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.config import Config
from gaffer.review import PWIN_LANES, picks_from_squad, price_lanes

CFG = Config(entry_id=1, league_id=5, current_season="2026-27", sim_n=200)

MINE = {"xi": [100, 101], "bench": [102], "captain": 100, "vice": 101,
        "hits": 0, "chip": None}


class FakeSim:
    """A stand-in for ``LeagueSim`` carrying only what the pricing reads."""

    def __init__(self, p_win):
        self.p_win = p_win


def test_the_pick_dicts_carry_the_position_effective_picks_needs():
    """``league_sim.effective_picks`` rebuilds the multipliers from
    ``position`` — 1-11 started, 12-15 benched — because a stored week's own
    multipliers are chip arithmetic. A counterfactual squad without positions
    would fall through to the capped-multiplier branch and score its bench."""
    picks = picks_from_squad(MINE, {100: 7, 101: 8, 102: 9})
    assert [p["position"] for p in picks] == [1, 2, 12]
    assert [p["element"] for p in picks] == [7, 8, 9]
    assert picks[0]["is_captain"] is True
    assert picks[1]["is_vice_captain"] is True
    assert [p["multiplier"] for p in picks] == [2, 1, 0]


def test_a_player_with_no_element_is_dropped_rather_than_faked():
    """The sim keys on elements; a code with no element this season is a
    player who left the game, and inventing an id for him would price
    somebody else's squad."""
    picks = picks_from_squad(MINE, {100: 7, 101: 8})
    assert [p["element"] for p in picks] == [7, 8]


def test_only_the_two_lanes_the_engine_can_see_are_priced():
    """``effective_picks`` strips the bench and the chip, so those two lanes
    cannot move a win probability however they are simulated. Pricing them
    would be two Monte Carlo runs to rediscover a zero."""
    assert PWIN_LANES == ("transfers", "captaincy")


def test_each_priced_lane_is_my_odds_less_the_models():
    """The sign convention, matching ``delta_pts``: mine minus the model's,
    so a negative number is a decision that cost me. The baseline is the
    first run; every counterfactual follows it."""
    answers = iter([0.30, 0.25])

    def _sim(inputs, **kw):
        return FakeSim(next(answers))

    out, notice = price_lanes(
        CFG, _fake_inputs(), MINE,
        {"transfers": {"xi": [101], "bench": [], "captain": 101,
                       "vice": 101, "hits": 0, "chip": None}},
        {100: 7, 101: 8, 102: 9}, simulate=_sim)
    assert notice is None
    assert out["transfers"] == pytest.approx(5.0)


def test_every_run_uses_the_same_seed_and_the_same_n():
    """A paired comparison. Two draws of one seed differ by the seed, and a
    difference of seeds is not a difference of decisions (CONVENTIONS.md
    §1)."""
    seen = []

    def _sim(inputs, **kw):
        seen.append((kw["seed"], kw["n"], kw["rival_drift"]))
        return FakeSim(0.3)

    price_lanes(CFG, _fake_inputs(), MINE,
                {"captaincy": dict(MINE, captain=101)},
                {100: 7, 101: 8, 102: 9}, simulate=_sim)
    assert len(set(seen)) == 1
    assert seen[0][1] == 200


def test_an_unpriceable_lane_is_absent_rather_than_zero():
    out, _ = price_lanes(CFG, _fake_inputs(), MINE, {"transfers": None},
                         {100: 7}, simulate=lambda i, **k: FakeSim(0.3))
    assert "transfers" not in out


def test_a_league_with_no_me_in_it_prices_nothing_and_says_so():
    """``build_inputs`` flags my entry by id. If nothing in the standings is
    mine there is no squad to swap and the whole pricing is meaningless."""
    inputs = _fake_inputs(mine=False)
    out, notice = price_lanes(CFG, inputs, MINE, {"captaincy": MINE},
                              {100: 7}, simulate=lambda i, **k: FakeSim(0.3))
    assert out == {}
    assert "your entry is not in the simulated league" in notice


def test_an_engine_that_raises_degrades_to_points_only_with_a_notice():
    """Spec F2: the engine calls are isolated so a dead client or an absent
    parquet costs the second currency and nothing else."""
    def _boom(inputs, **kw):
        raise RuntimeError("no component frame for GW1")

    out, notice = price_lanes(CFG, _fake_inputs(), MINE, {"captaincy": MINE},
                              {100: 7}, simulate=_boom)
    assert out == {}
    assert "no component frame for GW1" in notice


def _fake_inputs(mine=True):
    """A ``SimInputs`` with two entries, one of them me."""
    from gaffer.league_sim import Entry, SimInputs

    return SimInputs(
        entries=[Entry(entry=1, name="You FC", total=100, picks=[],
                       is_me=mine),
                 Entry(entry=2, name="Rival", total=110, picks=[])],
        ep_by_element={7: 6.0, 8: 3.0, 9: 4.0},
        sigma_by_element={7: 5.0, 8: 4.0, 9: 4.0}, weeks_left=36)
```

Then append the integration test — the one that exercises the real engine
through `grade_gw` — to the same file:

```python
def test_the_gameweek_grade_prices_its_lanes_when_the_components_exist(
        tmp_path, monkeypatch):
    """The whole path, over the ``test_web_league_sim`` fixture: banked
    components, a fake standings endpoint, and a real Monte Carlo."""
    from tests.test_web_league_sim import FakeClient, _artifacts

    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    from gaffer.data import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    store.save(pd.DataFrame([
        {"season_idx": 4, "gw": 3, "code": 100, "element": 7,
         "position": "MID", "total_points": 9, "minutes": 90},
        {"season_idx": 4, "gw": 3, "code": 101, "element": 8,
         "position": "DEF", "total_points": 2, "minutes": 90},
    ]), "live/player_gw.parquet")

    from gaffer.league_sim import build_inputs
    inputs = build_inputs(CFG, FakeClient(), gw=3)
    out, notice = price_lanes(
        CFG, inputs, {"xi": [100], "bench": [101], "captain": 100,
                      "vice": 100, "hits": 0, "chip": None},
        {"captaincy": {"xi": [101], "bench": [100], "captain": 101,
                       "vice": 101, "hits": 0, "chip": None}},
        {100: 7, 101: 8})
    assert notice is None
    assert isinstance(out["captaincy"], float)


def test_a_gameweek_with_no_banked_components_is_absent_with_a_notice(
        tmp_path, monkeypatch):
    """GW1's case, and the one G1 checks for: ``reports/components_gw1.parquet``
    does not exist and never will, so GW1 is graded in points alone."""
    from tests.test_web_league_sim import FakeClient

    from gaffer.review import price_lanes_for_gw

    monkeypatch.chdir(tmp_path)

    out, notice = price_lanes_for_gw(CFG, FakeClient(), 1, MINE, {}, {})
    assert out == {}
    assert "GW1" in notice
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_review_pwin.py`
  Expected: `ImportError: cannot import name 'PWIN_LANES' from 'gaffer.review'`.

- [ ] **Write the implementation.** Append to `src/gaffer/review.py`:

```python
PWIN_LANES = ("transfers", "captaincy")
"""The lanes a win probability can see.

``league_sim.effective_picks`` normalises any squad to its eleven starters and
one armband — the bench scores nothing and a chip's multipliers are stripped,
because a bench-boost week read as a *rate* would hand that manager four extra
players for the whole rest of the season. So a bench reordering and a chip
decision are invisible to the engine by construction, and simulating them
would spend two Monte Carlo runs to rediscover a zero. They carry ``0.0`` and
a note instead, which is the true answer plus the reason.
"""

PWIN_DP = 1
"""Decimal places on a Δ in percentage points. At ``n = 2000`` the counting
granularity is 0.05pp, so one decimal place is already finer than the
instrument; the row carries ``pwin_granularity_pp`` so nobody has to guess."""


def picks_from_squad(squad: dict, element_of: dict[int, int]) -> list[dict]:
    """A counterfactual squad as the pick dicts ``effective_picks`` reads.

    ``position`` is the load-bearing field: 1-11 for the eleven, 12-15 for the
    bench, in order. Without it ``effective_picks`` falls through to its
    stored-multiplier branch and the counterfactual would score its own bench
    — see ``league_sim.py:251-291``. A code with no element this season is
    dropped rather than given an invented id, which would price a different
    player's squad.
    """
    out, slot = [], 0
    for code in list(squad["xi"]) + list(squad["bench"]):
        element = element_of.get(int(code))
        if element is None:
            continue
        slot += 1
        out.append({"element": int(element), "position": slot,
                    "multiplier": (0 if slot > XI_SIZE
                                   else 2 if code == squad.get("captain")
                                   else 1),
                    "is_captain": code == squad.get("captain"),
                    "is_vice_captain": code == squad.get("vice")})
    return out


def price_lanes(cfg, inputs, mine: dict, counterfactuals: dict,
                element_of: dict[int, int], *, simulate=None
                ) -> tuple[dict[str, float], str | None]:
    """``{lane: Δ win% in percentage points}`` for the priceable lanes.

    One baseline run with my real squad, then one run per counterfactual with
    my ``Entry.picks`` swapped and *everything else identical* — same seed,
    same ``n``, same drift. That pairing is the whole method: two Monte Carlo
    runs differing in their seed differ by the seed, and the difference of
    seeds is not the difference of decisions (CONVENTIONS.md §1).

    The sign matches ``delta_pts``: mine minus the model's, so a negative
    number is a decision that cost me ground.

    Never raises. Every failure comes back as ``({}, notice)`` and the row is
    graded in points alone (spec F2).
    """
    import dataclasses

    from gaffer.league_sim import SIM_SEED, simulate_league

    simulate = simulate or simulate_league
    wanted = {lane: cf for lane, cf in counterfactuals.items()
              if lane in PWIN_LANES and cf is not None}
    if not wanted:
        return {}, None
    if not any(entry.is_me for entry in inputs.entries):
        return {}, ("your entry is not in the simulated league, so no "
                    "decision could be priced in title odds")
    kwargs = {"n": int(getattr(cfg, "sim_n", 2000)), "seed": SIM_SEED,
              "rival_drift": float(getattr(cfg, "rival_drift", 0.5))}

    def _with(picks):
        return dataclasses.replace(
            inputs, entries=[dataclasses.replace(e, picks=picks) if e.is_me
                             else e for e in inputs.entries])

    try:
        base = simulate(_with(picks_from_squad(mine, element_of)), **kwargs)
        out = {}
        for lane, cf in wanted.items():
            run = simulate(_with(picks_from_squad(cf, element_of)), **kwargs)
            out[lane] = round((base.p_win - run.p_win) * 100.0, PWIN_DP)
        return out, None
    except Exception as exc:  # noqa: BLE001 — the second currency is optional
        return {}, f"title odds not priced: {exc}"


def price_lanes_for_gw(cfg, client, gw: int, mine: dict,
                       counterfactuals: dict, element_of: dict[int, int]
                       ) -> tuple[dict[str, float], str | None]:
    """:func:`price_lanes` with the gameweek's inputs rebuilt first.

    ``build_inputs(cfg, client, gw=N)`` reads ``components_gw{N}.parquet`` and
    takes every entry's squad from the gameweek before, so this prices GW N's
    decision under the expectations that stood at GW N's own deadline.

    A gameweek whose component parquet has been deleted — and **GW1, which
    never had one**, because the first solve of a season is GW2's — comes back
    absent with a notice. Spec D4 requires exactly that rather than a silent
    zero.
    """
    try:
        from gaffer.league_sim import build_inputs

        inputs = build_inputs(cfg, client, gw=int(gw))
    except Exception as exc:  # noqa: BLE001 — no parquet, no league, no net
        return {}, (f"title odds not priced for GW{int(gw)}: {exc}")
    return price_lanes(cfg, inputs, mine, counterfactuals, element_of)
```

- [ ] **Attach the pricing to the grade.** In `src/gaffer/review.py`, extend
  `grade_gw_from`'s signature and the two places a lane's `delta_pwin` is
  filled. Replace its `def` line and docstring opening:

```python
def grade_gw_from(gw: int, mine: dict, model: dict | None,
                  actuals: pd.DataFrame, pwin: dict | None = None,
                  pwin_meta: dict | None = None) -> dict:
    """One ledger row from decisions already read. Pure; no I/O, no network.
```

and, immediately before `row["lanes"] = [...]` near the end of the function,
insert:

```python
    pwin = pwin or {}
    for lane in lanes:
        if lane["lane"] in PWIN_LANES:
            lane["delta_pwin"] = pwin.get(lane["lane"])
        else:
            lane["delta_pwin"] = 0.0
            lane["note"] = lane["note"] or (
                "title odds price the starting eleven and the armband; a "
                "bench order and a chip do not move them")
        lane["label"] = label_for(lane["delta_pts"], lane["delta_pwin"],
                                  aligned=lane["aligned"])
```

and add the metadata to the row *before* the no-advice early return, so a
gameweek with no surviving advice still records the instrument's granularity.
Immediately after the `row = {...}` literal and before `if model is None:`:

```python
    row.update(pwin_meta or {})
```

- [ ] **Write `grade_gw`, the I/O wrapper.** Append to `src/gaffer/review.py`:

```python
def grade_gw(gw: int, *, cfg, client=None) -> dict | None:
    """One gameweek's full grade, read off disk and priced. ``None`` when my
    picks for that week were never banked.

    The order matters: everything that can be answered without a network is
    answered first, so an FPL outage costs the Δwin% column and nothing else.
    """
    from gaffer.league_sim import SIM_SEED

    season = str(getattr(cfg, "current_season", "") or "")
    entry_id = int(getattr(cfg, "entry_id", 0) or 0)
    mine = my_decisions(gw, season=season, entry_id=entry_id)
    if mine is None:
        return None
    frame = actuals_for_gw(gw)
    model = model_decisions(gw)
    mine = {**mine, "code_of": {e: c for e, c in code_of_element().items()}}

    n = int(getattr(cfg, "sim_n", 2000) or 2000)
    meta = {"pwin_n": n, "pwin_seed": SIM_SEED,
            "pwin_granularity_pp": round(100.0 / max(n, 1), 3)}
    if model is None or client is None:
        row = grade_gw_from(gw, mine, model, frame, pwin_meta=meta)
        if model is not None:
            row["notices"] = list(row["notices"]) + [
                "no FPL client available, so nothing was priced in title "
                "odds"]
        return row

    my_squad = {k: mine[k] for k in ("xi", "bench", "captain", "vice", "hits",
                                     "chip")}
    counterfactuals = {lane: _cf_squad(lane, my_squad, model)
                       for lane in PWIN_LANES}
    element_of = {c: e for e, c in code_of_element().items()}
    priced, notice = price_lanes_for_gw(cfg, client, gw, my_squad,
                                        counterfactuals, element_of)
    row = grade_gw_from(gw, mine, model, frame, pwin=priced, pwin_meta=meta)
    if notice:
        row["notices"] = list(row["notices"]) + [notice]
    return row


def _cf_squad(lane: str, mine: dict, model: dict) -> dict | None:
    """Rebuild one lane's counterfactual squad for the pricing pass.

    The lane builders drop their ``cf`` before the row is banked — the ledger
    holds grades, not squads — so the two priceable lanes are rebuilt here
    from the same two functions rather than from a second implementation.
    """
    import pandas as pd

    blank = pd.DataFrame(columns=ACTUAL_COLS)
    if lane == "transfers":
        built = lane_transfers(mine, model, blank, my_transfers=[],
                               positions=model.get("positions") or {})
    else:
        built = lane_captaincy(mine, model, blank)
    return built.get("cf")
```

- [ ] **Extend `__all__`** with `"PWIN_LANES"`, `"grade_gw"`,
  `"picks_from_squad"`, `"price_lanes"`, `"price_lanes_for_gw"` (keep the list
  alphabetical).

- [ ] **Run to pass.** `uv run pytest -q tests/test_review_pwin.py tests/test_review_grades.py tests/test_league_sim.py tests/test_web_league_sim.py`
  Expected: `10 passed` in the pricing file, `34 passed` in the grades file, and both v8c sim suites green and unmodified.

- [ ] **Commit.**

```bash
git add src/gaffer/review.py tests/test_review_pwin.py && git commit -m "$(cat <<'EOF'
feat: price the transfer and captaincy lanes in title odds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 6 — F2: the ledger, `run_review` and the season summary

**Files:**
- Modify `src/gaffer/review.py` (append `LEDGER`, `ledger_path`, `load_ledger`, `append_ledger`, `season_summary`, `run_review`, `format_review`; extend `__all__`)
- Modify `src/gaffer/cli.py` (new `review` command after `field_scrape`, ~L256)
- Create `tests/test_review_ledger.py`

- [ ] **Write the failing test.** Create `tests/test_review_ledger.py`:

```python
"""``gaffer review``: what it banks, what it refuses to bank twice, and the
season sums it adds up.

Grades are banked at review time and never re-derived (spec D2), because
``ADVICE_HISTORY_KEEP`` is 20 runs *globally* — GW1's advice is gone by
October and a May season review that recomputed from history would find
nothing to recompute from.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import ADVICE_HISTORY, REPORTS
from gaffer.config import Config
from gaffer.data import store
from gaffer.review import (append_ledger, format_review, ledger_path,
                           load_ledger, run_review, season_summary)

CFG = Config(entry_id=42, league_id=5, current_season="2026-27", sim_n=50)

PLAYER_GW = pd.DataFrame(
    [{"season_idx": 4, "gw": gw, "code": 100 + i, "element": 7 + i,
      "position": pos, "total_points": pts, "minutes": 90}
     for gw in (1, 2)
     for i, (pos, pts) in enumerate(
         [("GKP", 3), ("GKP", 1), ("DEF", 6), ("DEF", 2), ("DEF", 1),
          ("DEF", 0), ("DEF", 4), ("MID", 9), ("MID", 2), ("MID", 1),
          ("MID", 5), ("MID", 0), ("FWD", 7), ("FWD", 1), ("FWD", 2)])])

PLAYERS = pd.DataFrame([{"code": 100 + i, "element": 7 + i}
                        for i in range(15)])

# The eleven I fielded, as indices into the fifteen above: one keeper, four
# defenders, four midfielders, two forwards — a legal 4-4-2. Codes are
# 100 + index. The armband is on index 7 (a midfielder, nine points).
XI_INDEX = [0, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13]
BENCH_INDEX = [1, 5, 11, 14]

MY_PICKS = (
    [{"element": 7 + idx, "position": 1 + slot,
      "multiplier": 2 if idx == 7 else 1,
      "is_captain": idx == 7, "is_vice_captain": idx == 12}
     for slot, idx in enumerate(XI_INDEX)]
    + [{"element": 7 + idx, "position": 12 + slot, "multiplier": 0,
        "is_captain": False, "is_vice_captain": False}
       for slot, idx in enumerate(BENCH_INDEX)])

# My eleven scores 3+6+2+1+4+9+2+1+5+7+1 = 41, plus 9 again for the armband
# = 50. ``points`` is gross of the hit and there is no hit, so the official
# net is 50 and the reconciliation is exact. The bench is 1+0+0+2 = 3.
HISTORY = {"current": [
    {"event": 1, "points": 50, "total_points": 50, "event_transfers": 0,
     "event_transfers_cost": 0, "points_on_bench": 3},
    {"event": 2, "points": 50, "total_points": 100, "event_transfers": 0,
     "event_transfers_cost": 0, "points_on_bench": 3}], "chips": []}

ADVICE = {"gw": 2, "deadline": "2026-08-21T17:30:00Z",
          "xi": [{"code": 100 + i, "name": f"P{i}",
                  "position": PLAYER_GW.iloc[i]["position"]}
                 for i in range(11)],
          "bench": [{"code": 111, "name": "P11", "position": "MID"},
                    {"code": 112, "name": "P12", "position": "FWD"},
                    {"code": 113, "name": "P13", "position": "FWD"},
                    {"code": 101, "name": "P1", "position": "GKP"}],
          "captain": {"code": 112, "name": "P12"},
          "vice": {"code": 107, "name": "P7"},
          "buys": [], "sells": [], "hits": 0, "chip_table": []}


class FakeClient:
    def get_entry_picks(self, entry_id, gw):
        return {"picks": MY_PICKS}

    def get_entry_history(self, entry_id):
        return HISTORY

    def get_entry_transfers(self, entry_id):
        return []

    def get_league_standings(self, league_id, page=1):
        raise RuntimeError("no league in this fixture")


@pytest.fixture()
def here(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    store.save(PLAYER_GW, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw2-2026-08-21T09:00:00.json").write_text(
        json.dumps(ADVICE))
    return tmp_path


def test_the_ledger_starts_empty_rather_than_missing(here):
    assert load_ledger() == []


def test_a_row_lands_under_reports_and_reads_back(here):
    append_ledger({"gw": 3, "my_points": 50})
    assert ledger_path() == REPORTS / "decision_ledger.json"
    assert load_ledger() == [{"gw": 3, "my_points": 50}]


def test_a_second_row_for_one_gameweek_replaces_the_first(here):
    """``append_sim_history``'s rule: a gameweek is reviewed once, and a
    re-review supersedes rather than duplicates."""
    append_ledger({"gw": 3, "my_points": 50})
    append_ledger({"gw": 3, "my_points": 61})
    assert [r["my_points"] for r in load_ledger()] == [61]


def test_the_ledger_stays_sorted_by_gameweek(here):
    append_ledger({"gw": 5, "my_points": 1})
    append_ledger({"gw": 2, "my_points": 2})
    assert [r["gw"] for r in load_ledger()] == [2, 5]


def test_the_write_is_atomic_and_leaves_no_temp_file(here):
    append_ledger({"gw": 3, "my_points": 50})
    assert not list(REPORTS.glob("decision_ledger.json*.tmp"))


def test_a_corrupt_ledger_is_rebuilt_rather_than_crashing_anything(here):
    REPORTS.mkdir(exist_ok=True)
    ledger_path().write_text("{ this is not json")
    assert load_ledger() == []
    append_ledger({"gw": 3, "my_points": 50})
    assert [r["gw"] for r in load_ledger()] == [3]


def test_a_nan_never_reaches_the_ledger(here):
    """``allow_nan=False``: NaN is not JSON, and a file the browser cannot
    parse is a Model hub that shows nothing at all."""
    with pytest.raises(ValueError):
        append_ledger({"gw": 3, "my_points": float("nan")})


def test_the_review_grades_every_finished_gameweek(here, capsys):
    done = run_review(CFG, client=FakeClient())
    assert done == [1, 2]
    assert [r["gw"] for r in load_ledger()] == [1, 2]
    out = capsys.readouterr().out
    assert out.count("GW1") >= 1
    assert "GW2" in out


def test_the_review_banks_my_picks_before_it_grades_them(here):
    run_review(CFG, client=FakeClient())
    assert (here / "data/raw/league/2026-27/42-2.json").is_file()
    assert (here / "data/raw/league/2026-27/42-history.json").is_file()


def test_a_gameweek_with_no_surviving_advice_is_marked_rather_than_skipped(
        here):
    """GW1's advice was pruned weeks ago (spec D2). The row still carries the
    reconciliation and the hindsight eleven, which need no model at all."""
    run_review(CFG, client=FakeClient())
    row = next(r for r in load_ledger() if r["gw"] == 1)
    assert row["no_advice"] is True
    assert row["accuracy"] is None
    assert row["hindsight"]["points"] > 0


def test_a_second_run_reviews_nothing_and_says_so(here, capsys):
    run_review(CFG, client=FakeClient())
    capsys.readouterr()
    assert run_review(CFG, client=FakeClient()) == []
    assert "already reviewed" in capsys.readouterr().out


def test_naming_a_gameweek_re_reviews_it(here):
    run_review(CFG, client=FakeClient())
    assert run_review(CFG, gw=2, client=FakeClient()) == [2]


def test_a_gameweek_whose_results_are_not_final_is_never_reviewed(here,
                                                                  capsys):
    """Only ``data_checked`` weeks (spec §6). GW3 is not in the results
    frame, so there is nothing to grade and nothing to bank."""
    assert run_review(CFG, gw=3, client=FakeClient()) == []
    assert "no final results" in capsys.readouterr().out


def test_an_unbanked_and_unfetchable_gameweek_is_skipped_not_fabricated(
        here, capsys):
    class Dead(FakeClient):
        def get_entry_picks(self, entry_id, gw):
            raise RuntimeError("FPL is down")

    assert run_review(CFG, client=Dead()) == []
    assert load_ledger() == []
    assert "skipped" in capsys.readouterr().out


def test_the_review_never_raises_whatever_happens(here, capsys):
    class Exploding:
        def get_entry_picks(self, *a, **kw):
            raise RuntimeError("boom")

        def get_entry_history(self, *a, **kw):
            raise RuntimeError("boom")

        def get_entry_transfers(self, *a, **kw):
            raise RuntimeError("boom")

    assert run_review(CFG, client=Exploding()) == []


def test_the_summary_of_an_empty_ledger_is_none(here):
    assert season_summary([]) is None


def test_the_summary_sums_each_lane_in_both_currencies():
    ledger = [
        {"gw": 1, "my_points": 50, "accuracy": 90, "points_on_bench": 3,
         "our_bench_points": 3, "hindsight": {"gap": 8}, "reconciled": True,
         "lanes": [{"lane": "transfers", "delta_pts": -3, "delta_pwin": -0.4,
                    "label": "Inaccuracy"},
                   {"lane": "captaincy", "delta_pts": 5, "delta_pwin": 0.2,
                    "label": "Brilliant"},
                   {"lane": "bench", "delta_pts": 0, "delta_pwin": 0.0,
                    "label": "Aligned"},
                   {"lane": "chip", "delta_pts": None, "delta_pwin": None,
                    "label": None}]},
        {"gw": 2, "my_points": 61, "accuracy": 100, "points_on_bench": 5,
         "our_bench_points": 5, "hindsight": {"gap": 4}, "reconciled": False,
         "lanes": [{"lane": "transfers", "delta_pts": -6, "delta_pwin": -0.1,
                    "label": "Blunder"},
                   {"lane": "captaincy", "delta_pts": 1, "delta_pwin": None,
                    "label": "Good"},
                   {"lane": "bench", "delta_pts": -2, "delta_pwin": 0.0,
                    "label": "Inaccuracy"},
                   {"lane": "chip", "delta_pts": 0, "delta_pwin": 0.0,
                    "label": "Aligned"}]},
    ]
    out = season_summary(ledger)
    assert out["lanes"]["transfers"]["pts"] == -9
    assert out["lanes"]["transfers"]["pwin"] == pytest.approx(-0.5)
    assert out["lanes"]["captaincy"]["pts"] == 6
    assert out["lanes"]["chip"]["pts"] == 0


def test_an_ungraded_lane_adds_nothing_and_is_counted_separately():
    """A null lane is not a zero. Summing it as zero would report a season of
    perfect chip discipline to a manager whose chip weeks were never
    gradeable."""
    ledger = [{"gw": 1, "my_points": 1, "accuracy": None,
               "points_on_bench": 0, "our_bench_points": 0,
               "hindsight": {"gap": 0}, "reconciled": True,
               "lanes": [{"lane": "chip", "delta_pts": None,
                          "delta_pwin": None, "label": None}]}]
    out = season_summary(ledger)
    assert out["lanes"]["chip"]["pts"] == 0
    assert out["lanes"]["chip"]["graded"] == 0


def test_the_summary_names_the_best_and_the_worst_single_decision():
    ledger = [
        {"gw": 1, "my_points": 50, "accuracy": 90, "points_on_bench": 0,
         "our_bench_points": 0, "hindsight": {"gap": 0}, "reconciled": True,
         "lanes": [{"lane": "captaincy", "delta_pts": 12, "delta_pwin": 1.0,
                    "label": "Brilliant"}]},
        {"gw": 2, "my_points": 40, "accuracy": 70, "points_on_bench": 0,
         "our_bench_points": 0, "hindsight": {"gap": 0}, "reconciled": True,
         "lanes": [{"lane": "transfers", "delta_pts": -11, "delta_pwin": -2.0,
                    "label": "Blunder"}]},
    ]
    out = season_summary(ledger)
    assert (out["best"]["gw"], out["best"]["lane"]) == (1, "captaincy")
    assert (out["worst"]["gw"], out["worst"]["lane"]) == (2, "transfers")


def test_the_summary_carries_the_accuracy_series_and_the_totals():
    ledger = [{"gw": 1, "my_points": 50, "accuracy": 90,
               "points_on_bench": 3, "our_bench_points": 4,
               "hindsight": {"gap": 8}, "reconciled": True, "lanes": []},
              {"gw": 2, "my_points": 61, "accuracy": None,
               "points_on_bench": 5, "our_bench_points": 5,
               "hindsight": {"gap": 4}, "reconciled": False, "lanes": []}]
    out = season_summary(ledger)
    assert out["accuracy"] == [{"gw": 1, "accuracy": 90}]
    assert out["points_on_bench"] == 8
    assert out["hindsight_gap"] == 12
    assert out["reconciled_gws"] == 1
    assert out["unreconciled_gws"] == 1


def test_the_printed_line_names_the_gameweek_and_its_worst_lane(here):
    row = {"gw": 2, "my_points": 61, "model_points": 68, "accuracy": 89,
           "reconciled": True, "no_advice": False,
           "lanes": [{"lane": "transfers", "delta_pts": -7,
                      "label": "Blunder", "mine": "no move",
                      "model": "Blank->Guehi", "delta_pwin": -0.3}]}
    line = format_review(row)
    assert "GW2" in line
    assert "61" in line
    assert "transfers" in line


def test_the_printed_line_flags_a_row_that_did_not_reconcile():
    row = {"gw": 2, "my_points": 61, "model_points": 68, "accuracy": 89,
           "reconciled": False, "official_points": 63, "no_advice": False,
           "lanes": []}
    assert "did not reconcile" in format_review(row)
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_review_ledger.py`
  Expected: `ImportError: cannot import name 'append_ledger' from 'gaffer.review'`.

- [ ] **Write the implementation.** Append to `src/gaffer/review.py`:

```python
LEDGER = "decision_ledger.json"
"""Under ``artifacts.REPORTS``. Read at call time, never bound at import, so a
test that redirects the reports directory redirects the ledger with it."""


def ledger_path():
    from gaffer import artifacts

    return artifacts.REPORTS / LEDGER


def load_ledger() -> list[dict]:
    """Every banked grade, oldest gameweek first. ``[]`` on any failure.

    A corrupt ledger reads as an empty one and is rebuilt by the next review
    (spec G2) — the alternative is a Model hub that shows a stack trace
    because a laptop lost power during a write six weeks ago.
    """
    path = ledger_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt ledger is an empty one
        return []
    rows = payload.get("gws") if isinstance(payload, dict) else payload
    return sorted([r for r in (rows or []) if isinstance(r, dict)
                   and "gw" in r], key=lambda r: int(r["gw"]))


def append_ledger(row: dict):
    """Bank one gameweek's grade, replacing any earlier row for that week.

    ``league_sim.append_sim_history``'s idiom exactly: replace-by-gameweek,
    written to a sibling and renamed so a reader sees the whole old file or
    the whole new one, and ``allow_nan=False`` because NaN is not JSON and a
    file the browser cannot parse is a hub that shows nothing at all.
    """
    from gaffer import artifacts

    rows = [r for r in load_ledger() if int(r["gw"]) != int(row["gw"])]
    rows.append(dict(row))
    rows.sort(key=lambda r: int(r["gw"]))
    artifacts.REPORTS.mkdir(parents=True, exist_ok=True)
    path = ledger_path()
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps({"gws": rows}, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def season_summary(ledger: list[dict]) -> dict | None:
    """Per-lane season sums in both currencies, plus the season's two stories.

    ``None`` for an empty ledger: a season nobody has reviewed has no summary,
    and a summary of zeros would read as a season of flawless decisions.

    An ungraded lane contributes nothing to the sum *and* nothing to the
    count. The ``graded`` field is what stops "chip: 0 points" from being read
    as chip discipline when it really means the chip weeks were never
    comparable.
    """
    if not ledger:
        return None
    lanes = {name: {"pts": 0.0, "pwin": 0.0, "graded": 0} for name in LANES}
    accuracy, bench, gap = [], 0, 0
    reconciled = unreconciled = 0
    best = worst = None
    for row in ledger:
        for lane in row.get("lanes") or []:
            cell = lanes.get(str(lane.get("lane")))
            if cell is None or lane.get("delta_pts") is None:
                continue
            cell["pts"] += float(lane["delta_pts"])
            cell["pwin"] += float(lane.get("delta_pwin") or 0.0)
            cell["graded"] += 1
            marked = {**lane, "gw": int(row["gw"])}
            if best is None or lane["delta_pts"] > best["delta_pts"]:
                best = marked
            if worst is None or lane["delta_pts"] < worst["delta_pts"]:
                worst = marked
        if row.get("accuracy") is not None:
            accuracy.append({"gw": int(row["gw"]),
                             "accuracy": int(row["accuracy"])})
        bench += int(row.get("points_on_bench") or 0)
        gap += int((row.get("hindsight") or {}).get("gap") or 0)
        if row.get("reconciled") is True:
            reconciled += 1
        elif row.get("reconciled") is False:
            unreconciled += 1
    for cell in lanes.values():
        cell["pts"] = round(cell["pts"], 1)
        cell["pwin"] = round(cell["pwin"], 2)
    return {"gws": [int(r["gw"]) for r in ledger], "lanes": lanes,
            "accuracy": accuracy, "points_on_bench": int(bench),
            "hindsight_gap": int(gap), "reconciled_gws": reconciled,
            "unreconciled_gws": unreconciled, "best": best, "worst": worst}


def format_review(row: dict) -> str:
    """The one line ``gaffer review`` prints per gameweek.

    A scheduled job's log is the only place most of these rows will ever be
    read, so the line carries the verdict rather than a row count: the score,
    the model's, and the single worst lane by name.
    """
    parts = [f"GW{int(row['gw'])}: you {row.get('my_points')}"]
    if row.get("no_advice"):
        parts.append("no surviving advice — reconciliation and hindsight only")
    else:
        parts.append(f"model {row.get('model_points')} "
                     f"(accuracy {row.get('accuracy')})")
        graded = [lane for lane in (row.get("lanes") or [])
                  if lane.get("delta_pts") is not None]
        if graded:
            worst = min(graded, key=lambda lane: lane["delta_pts"])
            parts.append(f"worst lane {worst['lane']} "
                         f"{worst['delta_pts']:+d} ({worst.get('label')})")
    if row.get("reconciled") is False:
        parts.append(f"did not reconcile — FPL says "
                     f"{row.get('official_points')}")
    return " | ".join(str(p) for p in parts)


def run_review(cfg=None, gw: int | None = None, *, client=None) -> list[int]:
    """Review every finished gameweek not yet in the ledger. Never raises.

    The launchd body, held to ``run_snapshot``'s contract: one printed line
    per gameweek and no exception out of the function. A Tuesday morning with
    no network must cost the *new* week's grade and nothing else — every week
    already banked stays banked, because grades are banked and never
    re-derived (spec D2).

    Order of operations: bank first, grade second. Banking is the only step
    that needs the API, so a gameweek that banks is a gameweek that can be
    graded offline forever afterwards.
    """
    try:
        from gaffer.config import load_config

        cfg = cfg or load_config()
        season = str(getattr(cfg, "current_season", "") or "")
        entry_id = int(getattr(cfg, "entry_id", 0) or 0)
        if not entry_id:
            print("review skipped: set fpl.entry_id in config.toml first")
            return []
        if client is None:
            from gaffer.api.client import FPLClient

            client = FPLClient()

        final = reviewable_gws()
        if gw is not None:
            if int(gw) not in final:
                print(f"review skipped: GW{int(gw)} has no final results yet "
                      f"— FPL has not marked it data_checked")
                return []
            wanted = [int(gw)]
        else:
            done = {int(r["gw"]) for r in load_ledger()}
            wanted = [g for g in final if g not in done]
            if not wanted:
                print(f"review: all {len(final)} finished gameweeks are "
                      f"already reviewed — nothing to do.")
                return []

        reviewed = []
        for target in wanted:
            banked = bank_my_entry(client, entry_id, season, target)
            if banked["picks"] is None:
                print(f"GW{target} skipped: no banked picks and the API would "
                      f"not answer — nothing graded, nothing invented.")
                continue
            row = grade_gw(target, cfg=cfg, client=client)
            if row is None:
                print(f"GW{target} skipped: picks banked but not readable.")
                continue
            row["reviewed_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
            append_ledger(row)
            print(format_review(row))
            reviewed.append(target)
        return reviewed
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        print(f"review not written: {exc}")
        return []
```

- [ ] **Add the three imports the ledger needs.** At the top of
  `src/gaffer/review.py`, extend the stdlib block to:

```python
import json
import os
from datetime import datetime, timezone
```

- [ ] **Extend `__all__`** with `"LEDGER"`, `"append_ledger"`,
  `"format_review"`, `"ledger_path"`, `"load_ledger"`, `"run_review"`,
  `"season_summary"`.

- [ ] **Add the CLI command.** In `src/gaffer/cli.py`, immediately after the
  `field_scrape` command (~L256) and before `league_sim`, insert:

```python
@app.command()
def review(gw: int = typer.Option(0, help="Gameweek to review (default: "
                                          "every finished one not yet in "
                                          "the ledger).")):
    """Grade last week's decisions against the model's (v8b F2).

    The launchd job's body, and held to ``snapshot``'s contract: it prints one
    line per gameweek and never fails. A Tuesday with no network is a Tuesday
    with no new grade, not a Tuesday with a traceback.
    """
    try:
        from gaffer.review import run_review

        run_review(gw=gw or None)
    except Exception as exc:  # noqa: BLE001 — a scheduled job never blocks
        # run_review swallows its own failures; the import cannot, and an
        # ImportError here would be the one traceback the launchd job still
        # emits every Tuesday morning.
        typer.echo(f"review not written: {exc}")
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_review_ledger.py tests/test_cli.py`
  Expected: `22 passed` in the ledger file, and the CLI suite green.

- [ ] **Commit.**

```bash
git add src/gaffer/review.py src/gaffer/cli.py tests/test_review_ledger.py && git commit -m "$(cat <<'EOF'
feat: the decision ledger, the season summary and gaffer review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the ninth job kind, the Tuesday plist and the installer

**Files:**
- Modify `src/gaffer/web/job_kinds.py` (new `run_review_job`; `JOB_KINDS` L111-120)
- Create `scripts/com.gaffer.review.plist`
- Modify `scripts/install_automation.sh` (loop L5, echo L12)
- Create `tests/test_web_job_kinds_v8b.py`

- [ ] **Write the failing test.** Create `tests/test_web_job_kinds_v8b.py`:

```python
"""The ninth job kind, and the plist that runs it without a browser."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaffer.web import job_kinds


def test_the_allow_list_has_exactly_nine_kinds():
    """A kind not in the allow-list is a 404, never an exec of user input.
    The count is pinned on both sides — see frontend/src/types.test.ts."""
    assert len(job_kinds.JOB_KINDS) == 9
    assert "review" in job_kinds.JOB_KINDS


def test_every_kind_is_callable_without_arguments():
    for kind, fn in job_kinds.JOB_KINDS.items():
        assert callable(fn), kind


def test_the_review_job_reports_how_many_gameweeks_it_graded(monkeypatch,
                                                             capsys):
    monkeypatch.setattr("gaffer.review.run_review", lambda: [1, 2])
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 2}
    assert "2 gameweeks" in capsys.readouterr().out


def test_a_review_that_graded_nothing_is_a_finished_job_not_a_failed_one(
        monkeypatch, capsys):
    """Zero is what an already-reviewed season looks like, which is what the
    Tuesday job sees every week between gameweeks."""
    monkeypatch.setattr("gaffer.review.run_review", lambda: [])
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 0}


def test_the_review_import_is_lazy(monkeypatch):
    """``job_kinds`` is imported by ``app.py`` at start-up, so a heavyweight
    import at module level would cost every ``gaffer ui`` its parquet reads."""
    source = Path("src/gaffer/web/job_kinds.py").read_text()
    head = source.split("def run_review_job")[0]
    assert "from gaffer.review import" not in head


def test_the_plist_runs_the_command_on_a_tuesday_morning():
    text = Path("scripts/com.gaffer.review.plist").read_text()
    assert "gaffer review" in text
    assert "<key>Weekday</key><integer>2</integer>" in text
    assert "com.gaffer.review" in text
    assert "logs/review.log" in text


def test_the_installer_installs_it():
    text = Path("scripts/install_automation.sh").read_text()
    assert "advise prices snapshot field review" in text
    assert "review" in text.split("echo")[-1]
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_job_kinds_v8b.py`
  Expected: `AssertionError: assert 8 == 9`.

- [ ] **Write the job kind.** In `src/gaffer/web/job_kinds.py`, add after
  `run_field_scrape_job`:

```python
def run_review_job() -> dict:
    """``gaffer review`` — grade the finished gameweeks (v8b F2).

    ``run_review`` prints one line per gameweek and answers ``[]`` on every
    failure, so the only work here is turning that into the count the job
    record carries. Zero gameweeks is a success: it is what an already-
    reviewed season looks like, which is what the Tuesday job sees every week
    the previous run worked.
    """
    from gaffer.review import run_review

    gws = list(run_review() or [])
    print(f"Reviewed {len(gws)} gameweeks into reports/decision_ledger.json.")
    return {"gws": len(gws)}
```

and add the entry to `JOB_KINDS`, after `"field-scrape"`:

```python
    "review": run_review_job,
```

- [ ] **Write the plist.** Create `scripts/com.gaffer.review.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.gaffer.review</string>
  <key>ProgramArguments</key><array>
    <string>/bin/zsh</string><string>-lc</string>
    <string>cd __PROJECT_DIR__ &amp;&amp; uv run gaffer review &gt;&gt; logs/review.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>2</integer>
    <key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer>
  </dict>
</dict></plist>
```

Tuesday rather than Monday: FPL finalises a weekend gameweek's bonus and
`data_checked` flag on the Monday, sometimes late, and a review that ran
before the flag flipped would find nothing to grade and print so. A midweek
gameweek is picked up the following Tuesday or by the hub's button, which is
the documented lag (spec D6).

- [ ] **Wire the installer.** In `scripts/install_automation.sh`, change line 5:

```bash
for name in advise prices snapshot field review; do
```

and line 12:

```bash
echo "Installed: Thursday 18:00 advise run + nightly 23:15 price check + daily 17:00 availability snapshot + Sat/Sun 12:30 field scrape + Tuesday 09:00 decision review."
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_job_kinds_v8b.py tests/test_web_jobs.py`
  Expected: `7 passed` in the new file, and `tests/test_web_jobs.py` green **and
  unmodified** — it is on the protected list.

- [ ] **Commit.**

```bash
git add src/gaffer/web/job_kinds.py scripts/com.gaffer.review.plist scripts/install_automation.sh tests/test_web_job_kinds_v8b.py && git commit -m "$(cat <<'EOF'
feat: the review job kind and its Tuesday launchd agent

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — F3: `GET /api/review` and its schemas

**Files:**
- Modify `src/gaffer/web/schemas.py` (append the six v8b models after `PenTracker`)
- Create `src/gaffer/web/routers/review.py`
- Modify `src/gaffer/web/app.py` (import L26-28; `include_router` ~L75)
- Create `tests/test_web_review.py`

- [ ] **Write the failing test.** Create `tests/test_web_review.py`:

```python
"""``GET /api/review`` — the banked ledger and its season summary.

Never an error. An unreviewed season is not a failure state, it is the state
every season starts in, so the empty ledger is a 200 with an empty body and
the hub shows a "run review" button rather than a retry.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import REPORTS
from gaffer.web.app import create_app

ROW = {
    "gw": 2, "reviewed_at": "2026-09-01T09:00:00+00:00", "no_advice": False,
    "post_deadline": False, "my_points": 61, "official_points": 61,
    "official_gross": 65, "hits": 1, "reconciled": True, "chip": None,
    "model_chip": "bboost", "points_on_bench": 5, "our_bench_points": 5,
    "model_points": 68, "accuracy": 89,
    "pwin_n": 2000, "pwin_seed": 20260831, "pwin_granularity_pp": 0.05,
    "hindsight": {"points": 74, "xi": [1, 2, 3], "captain": 3, "gap": 13},
    "misses": [{"code": 16, "name": "Guehi", "over": "Blank", "gain": 15}],
    "notices": [],
    "lanes": [
        {"lane": "transfers", "delta_pts": -7, "delta_pwin": -0.3,
         "label": "Blunder", "aligned": False, "mine": "no move",
         "model": "Blank->Guehi", "note": None},
        {"lane": "captaincy", "delta_pts": 4, "delta_pwin": 0.2,
         "label": "Brilliant", "aligned": False, "mine": "Salah",
         "model": "Haaland", "note": None},
        {"lane": "bench", "delta_pts": 0, "delta_pwin": 0.0,
         "label": "Aligned", "aligned": True, "mine": "A, B", "model": "A, B",
         "note": None},
        {"lane": "chip", "delta_pts": None, "delta_pwin": None,
         "label": None, "aligned": False, "mine": "none", "model": "wildcard",
         "note": "a wildcard or free hit changes the squad"},
    ],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _ledger(rows):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text(json.dumps({"gws": rows}))


def test_an_unreviewed_season_is_an_empty_two_hundred(client):
    """Not a 422. The page shows an empty state with a Review button; a
    retry button would be telling the user to retry something that worked."""
    response = client.get("/api/review")
    assert response.status_code == 200
    assert response.json() == {"gws": [], "summary": None}


def test_the_ledger_comes_back_row_for_row(client):
    _ledger([ROW])
    body = client.get("/api/review").json()
    assert [r["gw"] for r in body["gws"]] == [2]
    assert body["gws"][0]["accuracy"] == 89
    assert [lane["lane"] for lane in body["gws"][0]["lanes"]] \
        == ["transfers", "captaincy", "bench", "chip"]


def test_a_null_lane_survives_serialisation_as_null(client):
    """The one thing the schema must not do is coerce an ungraded lane to
    zero on its way through pydantic (spec G2)."""
    _ledger([ROW])
    chip = client.get("/api/review").json()["gws"][0]["lanes"][3]
    assert chip["delta_pts"] is None
    assert chip["label"] is None


def test_the_summary_is_computed_from_the_banked_rows(client):
    _ledger([ROW])
    summary = client.get("/api/review").json()["summary"]
    assert summary["lanes"]["transfers"]["pts"] == -7
    assert summary["hindsight_gap"] == 13
    assert summary["reconciled_gws"] == 1


def test_the_misses_and_the_hindsight_eleven_ride_along(client):
    _ledger([ROW])
    row = client.get("/api/review").json()["gws"][0]
    assert row["misses"][0]["name"] == "Guehi"
    assert row["hindsight"]["gap"] == 13


def test_a_corrupt_ledger_is_an_empty_state_not_a_five_hundred(client):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ not json")
    response = client.get("/api/review")
    assert response.status_code == 200
    assert response.json()["gws"] == []


def test_a_row_missing_half_its_fields_still_renders(client):
    """Ledgers written by an older build must not take the page down: every
    field but the gameweek has a default."""
    _ledger([{"gw": 1}])
    body = client.get("/api/review").json()
    assert body["gws"][0]["gw"] == 1
    assert body["gws"][0]["lanes"] == []
    assert body["gws"][0]["accuracy"] is None
```

- [ ] **Run it, expecting failure.** `uv run pytest -q tests/test_web_review.py`
  Expected: every test fails with a 404 — the route does not exist.

- [ ] **Write the schemas.** Append to `src/gaffer/web/schemas.py`:

```python
class ReviewLane(BaseModel):
    """One graded decision lane (spec D5).

    ``delta_pts`` and ``label`` are ``None`` — never zero — for a lane that
    could not be built: the model's captain was not in my eleven, the model
    sold a player I never owned, either side played a wildcard. "The model had
    no opinion I could have acted on" and "the model agreed with me" are
    different facts and the UI colours them differently.
    """

    lane: Literal["transfers", "captaincy", "bench", "chip"]
    delta_pts: float | None = None
    delta_pwin: float | None = None
    """My choice minus the model's, in percentage points of P(win the
    league). ``0.0`` on the bench and chip lanes by construction — the
    simulation normalises every squad to its eleven and one armband."""
    label: Literal["Brilliant", "Good", "Aligned", "Inaccuracy",
                   "Blunder"] | None = None
    aligned: bool = False
    mine: str | None = None
    model: str | None = None
    note: str | None = None


class ReviewMiss(BaseModel):
    """A move the model flagged, I did not make, and that returned anyway."""

    code: int
    name: str
    over: str
    gain: int


class ReviewHindsight(BaseModel):
    points: int = 0
    xi: list[int] = Field(default_factory=list)
    captain: int | None = None
    gap: int = 0


class ReviewGw(BaseModel):
    """One gameweek's banked grade. Every field but ``gw`` has a default, so
    a ledger written by an older build still renders."""

    gw: int
    reviewed_at: str | None = None
    no_advice: bool = False
    post_deadline: bool = False
    my_points: int | None = None
    official_points: int | None = None
    official_gross: int | None = None
    hits: int = 0
    reconciled: bool | None = None
    chip: str | None = None
    model_chip: str | None = None
    points_on_bench: int | None = None
    our_bench_points: int | None = None
    model_points: int | None = None
    accuracy: int | None = None
    pwin_n: int | None = None
    pwin_seed: int | None = None
    pwin_granularity_pp: float | None = None
    lanes: list[ReviewLane] = Field(default_factory=list)
    misses: list[ReviewMiss] = Field(default_factory=list)
    hindsight: ReviewHindsight = Field(default_factory=ReviewHindsight)
    notices: list[str] = Field(default_factory=list)


class ReviewLaneTotal(BaseModel):
    pts: float = 0.0
    pwin: float = 0.0
    graded: int = 0
    """How many gameweeks this lane was gradeable in. ``pts`` of zero over
    ``graded`` of zero is "never measured", not "never wrong"."""


class ReviewAccuracyPoint(BaseModel):
    gw: int
    accuracy: int


class ReviewSummary(BaseModel):
    gws: list[int] = Field(default_factory=list)
    lanes: dict[str, ReviewLaneTotal] = Field(default_factory=dict)
    accuracy: list[ReviewAccuracyPoint] = Field(default_factory=list)
    points_on_bench: int = 0
    hindsight_gap: int = 0
    reconciled_gws: int = 0
    unreconciled_gws: int = 0
    best: dict[str, Any] | None = None
    worst: dict[str, Any] | None = None


class Review(BaseModel):
    gws: list[ReviewGw] = Field(default_factory=list)
    summary: ReviewSummary | None = None
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/review.py`:

```python
"""GET /api/review — the banked decision ledger (spec F3).

Never an error, and for a sharper reason than the journal's: an unreviewed
season is not a degraded state, it is the state every season begins in. So the
empty ledger is a 200 with an empty body and the hub shows a "Review" button,
where a 422 would show a retry button for something that did not fail.

All the arithmetic happened at review time (spec D2). This module reads a JSON
file and adds up a summary; it grades nothing, fetches nothing, and cannot be
slow.
"""

from __future__ import annotations

from fastapi import APIRouter

from gaffer.review import load_ledger, season_summary
from gaffer.web.schemas import Review

router = APIRouter(prefix="/api", tags=["review"])

EMPTY = Review()


@router.get("/review", response_model=Review)
def review() -> Review:
    try:
        ledger = load_ledger()
        if not ledger:
            return EMPTY
        return Review(gws=ledger, summary=season_summary(ledger))
    except Exception as exc:  # noqa: BLE001 — a corrupt bank is an empty one
        print(f"review ledger unavailable: {exc}")
        return EMPTY
```

- [ ] **Register it.** In `src/gaffer/web/app.py`, extend the router import to
  include `review`:

```python
from gaffer.web.routers import (advice, chips, components, fixtures, jobs,
                                journal, league, league_sim, live, meta, news,
                                plan, players, quality, review, whatif)
```

and add, immediately after `app.include_router(quality.router)`:

```python
    app.include_router(review.router)
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_web_review.py tests/test_web_journal.py`
  Expected: `7 passed` in the new file, and the journal router suite green and
  unmodified — the Review tab sits beside the Journal tab, it does not replace
  it.

- [ ] **Commit.**

```bash
git add src/gaffer/web/schemas.py src/gaffer/web/routers/review.py src/gaffer/web/app.py tests/test_web_review.py && git commit -m "$(cat <<'EOF'
feat: GET /api/review serves the banked decision ledger

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — F3: the Review tab and the types lockstep

**Files:**
- Modify `frontend/src/types.ts` (`JOB_KINDS` L574; `JOB_KIND_LABEL` L579; append the v8b interfaces)
- Modify `frontend/src/types.test.ts` (the count pin, L8-12)
- Create `frontend/src/hubs/model/ReviewTab.tsx`
- Create `frontend/src/hubs/model/ReviewTab.test.tsx`
- Modify `frontend/src/hubs/Model.tsx` (button row ~L41; tabs L48-61)

- [ ] **Update the job-kind pin first.** In `frontend/src/types.test.ts`,
  replace the first test:

```ts
  it('lists exactly the nine kinds the backend allows', () => {
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens', 'field-scrape', 'review'])
  })
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/types.test.ts`
  Expected: FAIL — the array has eight entries, not nine.

- [ ] **Add the kind and the types.** In `frontend/src/types.ts`, replace
  `JOB_KINDS` and `JOB_KIND_LABEL`:

```ts
export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape', 'review'] as const

export type JobKind = typeof JOB_KINDS[number]

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  advise: 'Run advise',
  'advise-fast': 'Fast advise',
  evaluate: 'Evaluate',
  'refresh-data': 'Refresh data',
  'news-shadow': 'Score news shadow',
  snapshot: 'Snapshot news',
  'track-pens': 'Track pens',
  'field-scrape': 'Field scrape',
  review: 'Review last week',
}
```

and append the v8b interfaces at the end of the file:

```ts
export type ReviewLaneName = 'transfers' | 'captaincy' | 'bench' | 'chip'

export type ReviewLabel =
  'Brilliant' | 'Good' | 'Aligned' | 'Inaccuracy' | 'Blunder'

export interface ReviewLane {
  lane: ReviewLaneName
  /** null — never 0 — for a lane that could not be built. */
  delta_pts: number | null
  /** Percentage points of P(win). 0 on bench and chip by construction. */
  delta_pwin: number | null
  label: ReviewLabel | null
  aligned: boolean
  mine: string | null
  model: string | null
  note: string | null
}

export interface ReviewMiss {
  code: number
  name: string
  over: string
  gain: number
}

export interface ReviewHindsight {
  points: number
  xi: number[]
  captain: number | null
  gap: number
}

export interface ReviewGw {
  gw: number
  reviewed_at: string | null
  no_advice: boolean
  post_deadline: boolean
  my_points: number | null
  official_points: number | null
  official_gross: number | null
  hits: number
  reconciled: boolean | null
  chip: string | null
  model_chip: string | null
  points_on_bench: number | null
  our_bench_points: number | null
  model_points: number | null
  accuracy: number | null
  pwin_n: number | null
  pwin_seed: number | null
  pwin_granularity_pp: number | null
  lanes: ReviewLane[]
  misses: ReviewMiss[]
  hindsight: ReviewHindsight
  notices: string[]
}

export interface ReviewLaneTotal {
  pts: number
  pwin: number
  graded: number
}

export interface ReviewSummary {
  gws: number[]
  lanes: Record<string, ReviewLaneTotal>
  accuracy: { gw: number, accuracy: number }[]
  points_on_bench: number
  hindsight_gap: number
  reconciled_gws: number
  unreconciled_gws: number
  best: (ReviewLane & { gw: number }) | null
  worst: (ReviewLane & { gw: number }) | null
}

export interface ReviewData {
  gws: ReviewGw[]
  summary: ReviewSummary | null
}
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/types.test.ts`
  Expected: PASS.

- [ ] **Write the failing tab test.** Create
  `frontend/src/hubs/model/ReviewTab.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReviewTab from './ReviewTab'
import type { ReviewData } from '../../types'

const LANES: ReviewData['gws'][number]['lanes'] = [
  { lane: 'transfers', delta_pts: -7, delta_pwin: -0.3, label: 'Blunder',
    aligned: false, mine: 'no move', model: 'Blank->Guehi', note: null },
  { lane: 'captaincy', delta_pts: 4, delta_pwin: 0.2, label: 'Brilliant',
    aligned: false, mine: 'Salah', model: 'Haaland', note: null },
  { lane: 'bench', delta_pts: 0, delta_pwin: 0, label: 'Aligned',
    aligned: true, mine: 'A, B', model: 'A, B', note: null },
  { lane: 'chip', delta_pts: null, delta_pwin: null, label: null,
    aligned: false, mine: 'none', model: 'wildcard',
    note: 'a wildcard changes the squad' },
]

const DATA: ReviewData = {
  gws: [{
    gw: 2, reviewed_at: '2026-09-01T09:00:00+00:00', no_advice: false,
    post_deadline: false, my_points: 61, official_points: 61,
    official_gross: 65, hits: 1, reconciled: true, chip: null,
    model_chip: 'bboost', points_on_bench: 5, our_bench_points: 5,
    model_points: 68, accuracy: 89, pwin_n: 2000, pwin_seed: 20260831,
    pwin_granularity_pp: 0.05, lanes: LANES,
    misses: [{ code: 16, name: 'Guehi', over: 'Blank', gain: 15 }],
    hindsight: { points: 74, xi: [1, 2, 3], captain: 3, gap: 13 },
    notices: [],
  }],
  summary: {
    gws: [2], lanes: {
      transfers: { pts: -7, pwin: -0.3, graded: 1 },
      captaincy: { pts: 4, pwin: 0.2, graded: 1 },
      bench: { pts: 0, pwin: 0, graded: 1 },
      chip: { pts: 0, pwin: 0, graded: 0 },
    },
    accuracy: [{ gw: 2, accuracy: 89 }], points_on_bench: 5,
    hindsight_gap: 13, reconciled_gws: 1, unreconciled_gws: 0,
    best: { ...LANES[1], gw: 2 }, worst: { ...LANES[0], gw: 2 },
  },
}

function mock(data: ReviewData | Error) {
  vi.stubGlobal('fetch', vi.fn(() => (data instanceof Error
    ? Promise.reject(data)
    : Promise.resolve({ ok: true, json: () => Promise.resolve(data) }))))
}

describe('ReviewTab', () => {
  beforeEach(() => vi.unstubAllGlobals())

  it('shows an empty state before anything has been reviewed', async () => {
    mock({ gws: [], summary: null })
    render(<ReviewTab />)
    expect(await screen.findByText(/Nothing reviewed yet/i)).toBeTruthy()
  })

  it('falls back to the empty state when the request fails', async () => {
    mock(new Error('offline'))
    render(<ReviewTab />)
    expect(await screen.findByText(/Nothing reviewed yet/i)).toBeTruthy()
  })

  it('renders a card per reviewed gameweek with its accuracy', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByText('GW2')).toBeTruthy()
    expect(screen.getByText('89')).toBeTruthy()
  })

  it('labels every graded lane', async () => {
    mock(DATA)
    render(<ReviewTab />)
    await waitFor(() => screen.getByText('Blunder'))
    expect(screen.getByText('Brilliant')).toBeTruthy()
    expect(screen.getByText('Aligned')).toBeTruthy()
  })

  it('renders an ungraded lane as an em dash, never as a nought', async () => {
    mock(DATA)
    render(<ReviewTab />)
    const chip = await screen.findByTestId('lane-chip')
    expect(chip.textContent).toContain('—')
    expect(chip.textContent).not.toContain('0.0')
  })

  it('shows the note explaining why a lane was not graded', async () => {
    mock(DATA)
    render(<ReviewTab />)
    const chip = await screen.findByTestId('lane-chip')
    expect(chip.getAttribute('title')).toContain('wildcard')
  })

  it('spells out the hindsight gap in plain words', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByTestId('hindsight-2')).toBeTruthy()
    expect(screen.getByTestId('hindsight-2').textContent)
      .toContain('74')
  })

  it('lists the moves flagged and skipped', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByText(/Guehi/)).toBeTruthy()
  })

  it('badges a gameweek that did not reconcile', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], reconciled: false, official_points: 63 }],
    })
    render(<ReviewTab />)
    expect(await screen.findByText(/did not reconcile/i)).toBeTruthy()
  })

  it('badges advice that was banked after the deadline', async () => {
    mock({ ...DATA, gws: [{ ...DATA.gws[0], post_deadline: true }] })
    render(<ReviewTab />)
    expect(await screen.findByText(/late run/i)).toBeTruthy()
  })

  it('says so when a gameweek has no surviving advice', async () => {
    mock({
      ...DATA,
      gws: [{ ...DATA.gws[0], no_advice: true, accuracy: null,
              model_points: null }],
    })
    render(<ReviewTab />)
    expect(await screen.findByText(/no surviving advice/i)).toBeTruthy()
  })

  it('sums each lane over the season', async () => {
    mock(DATA)
    render(<ReviewTab />)
    expect(await screen.findByTestId('season-transfers')).toBeTruthy()
    expect(screen.getByTestId('season-transfers').textContent).toContain('-7')
  })

  it('marks a lane that was never gradeable rather than scoring it 0',
     async () => {
       mock(DATA)
       render(<ReviewTab />)
       const cell = await screen.findByTestId('season-chip')
       expect(cell.textContent).toContain('never graded')
     })
})
```

- [ ] **Run it, expecting failure.** `cd frontend && npx vitest run src/hubs/model/ReviewTab.test.tsx`
  Expected: FAIL — `Failed to resolve import "./ReviewTab"`.

- [ ] **Write the tab.** Create `frontend/src/hubs/model/ReviewTab.tsx`:

```tsx
import { useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import {
  Badge, Card, EmptyState, Loading, Stat, TONE_CLASS, fmtDelta, fmtNum,
  toneOf,
} from '../../kit'
import type {
  ReviewData, ReviewGw, ReviewLabel, ReviewLane, ReviewLaneName,
} from '../../types'

const LANE_ORDER: ReviewLaneName[] = ['transfers', 'captaincy', 'bench', 'chip']

const LANE_TITLE: Record<ReviewLaneName, string> = {
  transfers: 'Transfers',
  captaincy: 'Captaincy',
  bench: 'Bench order',
  chip: 'Chip',
}

// The bands are the spec's, pre-registered before any gameweek was graded.
// Aligned is deliberately neutral rather than green: following the model is
// not a good week, it is a week with nothing to learn from.
const LABEL_VARIANT: Record<ReviewLabel, 'positive' | 'negative' | 'neutral'> = {
  Brilliant: 'positive',
  Good: 'positive',
  Aligned: 'neutral',
  Inaccuracy: 'negative',
  Blunder: 'negative',
}

const NO_ADVICE = 'no surviving advice — this gameweek is graded on '
  + 'reconciliation and hindsight alone'

const LATE_RUN = 'every banked run of this gameweek was written after the '
  + 'deadline, so the model saw team news you could not act on'

/** A whole number as a string, or an em dash. `Stat` would render a raw
 *  number through `fmtNum` and print "61.0" for a points total. */
function num(value: number | null): string {
  return value === null || value === undefined ? '—' : String(value)
}

function LaneRow({ lane }: { lane: ReviewLane }) {
  const graded = lane.delta_pts !== null
  return (
    <div data-testid={`lane-${lane.lane}`} title={lane.note ?? undefined}
         className="flex flex-wrap items-baseline gap-2 py-1.5">
      <span className="w-28 text-text-muted">{LANE_TITLE[lane.lane]}</span>
      {lane.label ? (
        <Badge variant={LABEL_VARIANT[lane.label]}>{lane.label}</Badge>
      ) : <Badge variant="neutral">not graded</Badge>}
      <span className={`num ${TONE_CLASS[toneOf(lane.delta_pts)]}`}>
        {graded ? `${fmtDelta(lane.delta_pts, 0)} pts` : '—'}
      </span>
      <span className={`num text-xs ${TONE_CLASS[toneOf(lane.delta_pwin)]}`}>
        {lane.delta_pwin === null ? '—' : `${fmtDelta(lane.delta_pwin)} pp`}
      </span>
      <span className="text-xs text-text-faint">
        you {lane.mine ?? '—'} · model {lane.model ?? '—'}
      </span>
    </div>
  )
}

function GwCard({ row }: { row: ReviewGw }) {
  const lanes = LANE_ORDER
    .map((name) => row.lanes.find((lane) => lane.lane === name))
    .filter((lane): lane is ReviewLane => lane !== undefined)
  return (
    <Card
      title={`GW${row.gw}`}
      heading={(
        // `Card.title` is a string; rich heading content goes in `heading`,
        // which is what the h3 renders. The badges belong in the heading
        // because they qualify the whole gameweek, not one lane of it.
        <span className="inline-flex flex-wrap items-center gap-2">
          {`GW${row.gw}`}
          {row.post_deadline
            ? <Badge variant="negative" title={LATE_RUN}>late run</Badge>
            : null}
          {row.reconciled === false ? (
            <Badge variant="negative">
              {`did not reconcile — FPL says ${row.official_points}`}
            </Badge>
          ) : null}
        </span>
      )}
      className="mb-4"
    >
      <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {/* Every value is pre-formatted as a string: `Stat` runs a raw
            number through fmtNum, which would print a points total as
            "61.0". These are counts, not measurements. */}
        <Stat label="You" value={num(row.my_points)} />
        <Stat label="Model" value={num(row.model_points)} />
        <Stat label="Accuracy" value={num(row.accuracy)} />
        <Stat label="Bench" value={num(row.points_on_bench)} />
      </div>
      {row.no_advice
        ? <p className="text-sm text-text-muted">{NO_ADVICE}</p>
        : <div className="divide-y divide-divider">
            {lanes.map((lane) => <LaneRow key={lane.lane} lane={lane} />)}
          </div>}
      <p data-testid={`hindsight-${row.gw}`}
         className="mt-3 text-sm text-text-muted">
        Best eleven you owned: {row.hindsight.points} — you scored{' '}
        {row.my_points ?? '—'}, so selection left {row.hindsight.gap} on the
        table.
      </p>
      {row.misses.length > 0 && (
        <p className="mt-1 text-sm text-text-muted">
          Flagged and skipped:{' '}
          {row.misses.map((m) => `${m.name} (+${m.gain} over ${m.over})`)
            .join(', ')}
        </p>
      )}
      {row.notices.map((notice) => (
        <p key={notice} className="mt-1 text-xs text-text-faint">{notice}</p>
      ))}
    </Card>
  )
}

export default function ReviewTab() {
  const [data, setData] = useState<ReviewData | null>(null)

  useEffect(() => {
    apiGet<ReviewData>('/api/review').then(setData)
      .catch(() => setData({ gws: [], summary: null }))
  }, [])

  if (!data) return <Loading />
  if (data.gws.length === 0) {
    return (
      <EmptyState
        title="Nothing reviewed yet"
        detail="The review grades the decisions you made against the ones the
                model made before the same deadline, so it needs a gameweek
                whose results FPL has finalised."
        action="Review last week"
      />
    )
  }

  return (
    <div>
      {data.summary && (
        <Card title="Season ledger" className="mb-4">
          <div className="mb-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {LANE_ORDER.map((name) => {
              const cell = data.summary!.lanes[name]
              return (
                <div key={name} data-testid={`season-${name}`}
                     className="rounded-card border border-border bg-card
                                px-4 py-3">
                  <p className="label">{LANE_TITLE[name]}</p>
                  <p className={`num mt-1 text-2xl
                                 ${TONE_CLASS[toneOf(cell?.pts ?? 0)]}`}>
                    {cell && cell.graded > 0 ? fmtDelta(cell.pts, 0) : '—'}
                  </p>
                  <p className="num mt-1 text-xs text-text-faint">
                    {cell && cell.graded > 0
                      ? `${fmtDelta(cell.pwin)} pp over ${cell.graded} GW`
                      : 'never graded'}
                  </p>
                </div>
              )
            })}
          </div>
          <p className="text-sm text-text-muted">
            Bench points this season: {data.summary.points_on_bench}. Selection
            left {data.summary.hindsight_gap} on the table.{' '}
            {data.summary.unreconciled_gws > 0
              ? `${data.summary.unreconciled_gws} gameweek(s) did not
                 reconcile against FPL's own score.`
              : 'Every reviewed gameweek reconciles against FPL’s own '
                + 'score.'}
          </p>
          {data.summary.worst && (
            <p className="mt-1 text-sm text-text-muted">
              Worst single decision: GW{data.summary.worst.gw}{' '}
              {LANE_TITLE[data.summary.worst.lane]}{' '}
              {fmtNum(data.summary.worst.delta_pts, 0)} pts.
            </p>
          )}
        </Card>
      )}
      {[...data.gws].reverse().map((row) => (
        <GwCard key={row.gw} row={row} />
      ))}
    </div>
  )
}
```

- [ ] **Wire it into the hub.** In `frontend/src/hubs/Model.tsx`: add the import

```tsx
import ReviewTab from './model/ReviewTab'
```

add a `reviewNonce` beside the two that exist:

```tsx
  const [reviewNonce, setReviewNonce] = useState(0)
  const reloadReview = useCallback(() => setReviewNonce((n) => n + 1), [])
```

add the button to the header row, after `Track pens`:

```tsx
            <JobButton kind="review" label="Review last week"
                       onDone={reloadReview} />
```

and add the tab between Journal and History:

```tsx
          <Tabs.Trigger value="review" className={TAB_CLASS}>Review</Tabs.Trigger>
```

```tsx
        <Tabs.Content value="review"><ReviewTab key={reviewNonce} /></Tabs.Content>
```

- [ ] **Run to pass.** `cd frontend && npx vitest run src/hubs/model/ReviewTab.test.tsx src/types.test.ts src/hubs/Model.test.tsx`
  Expected: `13 passed` in the tab file, the types pin green, and the existing
  Model hub suite green.

- [ ] **Typecheck and build.** `cd frontend && npx tsc --noEmit && npm run build`
  Expected: no errors.

- [ ] **Commit.**

```bash
git add frontend/src/types.ts frontend/src/types.test.ts frontend/src/hubs/model/ReviewTab.tsx frontend/src/hubs/model/ReviewTab.test.tsx frontend/src/hubs/Model.tsx && git commit -m "$(cat <<'EOF'
feat: the Review tab, the season ledger card and the ninth job button

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — G2: the rails

**Files:**
- Create `tests/test_v8b_degradation.py`

Gate G2 is pre-registered in spec §4 and every case below is a real Tuesday: a
fresh clone, an FPL outage, a pruned advice directory, a ledger a power cut
ate. The claim is that each degrades to something a user can read, and that
none of them fabricates a grade.

- [ ] **Write the test.** Create `tests/test_v8b_degradation.py`:

```python
"""v8b's rails: what the decision loop does when its inputs are not there.

Gate G2 (spec §4). The distinction every case here defends is the one the
whole cycle turns on: **null is not zero**. A lane the model had no opinion on
must not read as a lane the model agreed with me on, because the second is a
grade and the first is an absence of one, and a season summary that adds
absences up as zeros reports discipline the manager never showed.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import ADVICE_HISTORY, REPORTS
from gaffer.config import Config
from gaffer.data import store
from gaffer.review import (grade_gw, load_ledger, reviewable_gws, run_review,
                           season_summary)
from gaffer.web import job_kinds
from gaffer.web.app import create_app

CFG = Config(entry_id=42, league_id=5, current_season="2026-27", sim_n=50)

RESULTS = pd.DataFrame(
    [{"season_idx": 4, "gw": 1, "code": 100 + i, "element": 7 + i,
      "position": pos, "total_points": pts, "minutes": 90}
     for i, (pos, pts) in enumerate(
         [("GKP", 3), ("GKP", 1), ("DEF", 6), ("DEF", 2), ("DEF", 1),
          ("DEF", 0), ("DEF", 4), ("MID", 9), ("MID", 2), ("MID", 1),
          ("MID", 5), ("MID", 0), ("FWD", 7), ("FWD", 1), ("FWD", 2)])])

PLAYERS = pd.DataFrame([{"code": 100 + i, "element": 7 + i}
                        for i in range(15)])

# A legal 4-4-2 out of the fifteen, armband on index 7. See
# tests/test_review_ledger.py for the same fixture and its arithmetic: the
# eleven scores 41, the armband adds 9, and FPL's own gross is therefore 50
# with no hit — so the reconciliation is exact and `reconciled` is True.
XI_INDEX = [0, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13]
BENCH_INDEX = [1, 5, 11, 14]

PICKS = (
    [{"element": 7 + idx, "position": 1 + slot,
      "multiplier": 2 if idx == 7 else 1,
      "is_captain": idx == 7, "is_vice_captain": idx == 12}
     for slot, idx in enumerate(XI_INDEX)]
    + [{"element": 7 + idx, "position": 12 + slot, "multiplier": 0,
        "is_captain": False, "is_vice_captain": False}
       for slot, idx in enumerate(BENCH_INDEX)])

HISTORY = {"current": [{"event": 1, "points": 50, "total_points": 50,
                        "event_transfers": 0, "event_transfers_cost": 0,
                        "points_on_bench": 3}], "chips": []}


class Client:
    def __init__(self, dead=False):
        self.dead = dead

    def get_entry_picks(self, entry_id, gw):
        if self.dead:
            raise RuntimeError("FPL is down")
        return {"picks": PICKS}

    def get_entry_history(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return HISTORY

    def get_entry_transfers(self, entry_id):
        if self.dead:
            raise RuntimeError("FPL is down")
        return []

    def get_league_standings(self, league_id, page=1):
        raise RuntimeError("no league in this fixture")


@pytest.fixture()
def bare(tmp_path, monkeypatch):
    """A clone with results and players, and nothing else at all."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr("gaffer.data.my_entry.RAW_LEAGUE",
                        tmp_path / "data/raw/league")
    store.save(RESULTS, "live/player_gw.parquet")
    store.save(PLAYERS, "live/players.parquet")
    return tmp_path


def _bank(tmp_path, entry=42, season="2026-27", gw=1):
    base = tmp_path / "data/raw/league" / season
    base.mkdir(parents=True, exist_ok=True)
    (base / f"{entry}-{gw}.json").write_text(json.dumps(PICKS))
    (base / f"{entry}-history.json").write_text(json.dumps(HISTORY))


def test_no_banked_picks_and_no_api_reviews_nothing_and_says_so(bare, capsys):
    """The review never invents a squad. A gameweek it cannot read is a
    gameweek it does not grade."""
    assert run_review(CFG, client=Client(dead=True)) == []
    assert load_ledger() == []
    assert "skipped" in capsys.readouterr().out


def test_a_dead_api_still_grades_the_gameweeks_already_banked(bare, capsys):
    """Banking is the only step that needs the network. Once a week is
    banked it is gradeable forever, which is the whole reason for D1."""
    _bank(bare)
    assert run_review(CFG, client=Client(dead=True)) == [1]
    assert [r["gw"] for r in load_ledger()] == [1]


def test_a_gameweek_with_no_surviving_advice_is_null_not_zero(bare):
    """``ADVICE_HISTORY_KEEP`` is 20 and global (spec D2), so this is what
    every early gameweek looks like by October."""
    _bank(bare)
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["no_advice"] is True
    assert row["model_points"] is None
    assert row["accuracy"] is None
    assert [lane["delta_pts"] for lane in row["lanes"]] == [None] * 4
    assert [lane["label"] for lane in row["lanes"]] == [None] * 4


def test_a_null_lane_adds_nothing_to_the_season_sums(bare):
    _bank(bare)
    run_review(CFG, client=Client())
    summary = season_summary(load_ledger())
    assert summary["lanes"]["captaincy"]["graded"] == 0
    assert summary["lanes"]["captaincy"]["pts"] == 0


def test_the_reconciliation_and_the_hindsight_survive_a_pruned_history(bare):
    """The half of the row that owes nothing to the model stays true."""
    _bank(bare)
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["reconciled"] is True
    assert row["hindsight"]["points"] > 0


def test_a_gameweek_that_is_not_data_checked_is_never_reviewed(bare, capsys):
    """GW2 is not in the results frame, which is exactly how ``refresh_live``
    represents "FPL has not finalised it"."""
    _bank(bare, gw=2)
    assert run_review(CFG, gw=2, client=Client()) == []
    assert "no final results" in capsys.readouterr().out


def test_a_clone_that_has_never_refreshed_reviews_nothing(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    assert reviewable_gws() == []
    assert run_review(CFG, client=Client()) == []


def test_a_corrupt_ledger_is_rewritten_rather_than_crashing_the_review(bare):
    _bank(bare)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ half a file")
    assert run_review(CFG, client=Client()) == [1]
    assert [r["gw"] for r in load_ledger()] == [1]


def test_a_corrupt_ledger_is_an_empty_state_rather_than_a_router_crash(
        bare):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "decision_ledger.json").write_text("{ half a file")
    response = TestClient(create_app(),
                          raise_server_exceptions=False).get("/api/review")
    assert response.status_code == 200
    assert response.json() == {"gws": [], "summary": None}


def test_the_empty_review_endpoint_is_a_two_hundred(bare):
    response = TestClient(create_app(),
                          raise_server_exceptions=False).get("/api/review")
    assert response.status_code == 200


def test_the_title_odds_degrade_without_taking_the_grade_with_them(bare):
    """No league, no component parquet, a standings endpoint that raises —
    the row still carries every points number and says why it carries no
    percentage points (spec D4)."""
    _bank(bare)
    ADVICE_HISTORY.mkdir(parents=True, exist_ok=True)
    (ADVICE_HISTORY / "gw1-2026-08-14T09:00:00.json").write_text(json.dumps({
        "gw": 1, "deadline": "2026-08-14T17:30:00Z",
        "xi": [{"code": 100 + i, "name": f"P{i}"} for i in range(11)],
        "bench": [{"code": 111, "name": "P11"}], "captain": {"code": 112},
        "vice": {"code": 107}, "buys": [], "sells": [], "hits": 0,
        "chip_table": []}))
    row = grade_gw(1, cfg=CFG, client=Client())
    assert row["my_points"] is not None
    assert all(lane["delta_pwin"] in (None, 0.0) for lane in row["lanes"])
    assert any("title odds not priced" in n for n in row["notices"])


def test_the_review_job_kind_survives_a_review_that_grades_nothing(bare):
    assert job_kinds.JOB_KINDS["review"]() == {"gws": 0}


def test_the_job_kind_count_is_pinned_on_this_side_too():
    """The frontend pins nine in ``src/types.test.ts``; a kind added on one
    side and not the other is a button that 404s."""
    assert len(job_kinds.JOB_KINDS) == 9


def test_the_protected_ordering_rails_are_carried_forward():
    """Copied from v8a/v8c: the chip table is ordered by gameweek and the
    advice payload's XI is ordered by position, and the review reads both by
    index. A silent reorder upstream would regrade a season."""
    from gaffer.review import LANES, PWIN_LANES

    assert LANES == ("transfers", "captaincy", "bench", "chip")
    assert PWIN_LANES == ("transfers", "captaincy")
```

- [ ] **Run to pass.** `uv run pytest -q tests/test_v8b_degradation.py`
  Expected: `14 passed`.

- [ ] **Run the whole Python suite.** `uv run pytest -q`
  Expected: green, and the count is the 1966 baseline plus every test added by
  Tasks 1-10 (20 + 18 + 34 + 7 + 10 + 22 + 7 + 7 + 14 = 139), i.e. **2105
  passed**. A different number means a task's suite did not land or a
  pre-existing test broke — investigate before continuing.

- [ ] **Commit.**

```bash
git add tests/test_v8b_degradation.py && git commit -m "$(cat <<'EOF'
test: v8b's degradation rails — null is never zero

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — the documentation

**Files:**
- Modify `README.md` (Where things live ~L313; Automation ~L340)

- [ ] **Document the new stores.** In `README.md`, under **Where things live**,
  immediately after the `data/live/field_eo_log.parquet` bullet, add:

```markdown
- `data/raw/league/{season}/{entry}-{gw}.json` — one entry's squad for one
  finished gameweek. Your own entry is banked here too, in the same layout as
  every rival's, so the review can grade a September decision in December
  without asking the API again.
- `data/raw/league/{season}/{entry}-history.json` and `-transfers.json` — your
  per-gameweek points, rank, bench points and transfer cost, and every
  transfer you have made. Replaced on write, because both are cumulative.
```

and after the `reports/league_sim_history.json` bullet, add:

```markdown
- `reports/decision_ledger.json` — one banked grade per reviewed gameweek: the
  four decision lanes in points and in title odds, the reconciliation against
  FPL's own score, and the best eleven you could have fielded. Written once,
  when the gameweek's results are final, and never re-derived — the model's
  pre-deadline advice is pruned after twenty runs, so the grade has to outlive
  it.
```

- [ ] **Document the job.** In the **Automation** section, change "the four
  plists" to "the five plists" and extend the sentence listing them:

```markdown
Substitutes the project path into the five plists in `scripts/`, copies them to
`~/Library/LaunchAgents/`, and loads them: `com.gaffer.advise` (Thursday 18:00),
`com.gaffer.prices` (nightly 23:15), `com.gaffer.snapshot` (daily 17:00, banks
the availability log the news corrector will train on), `com.gaffer.field` and
`com.gaffer.review`.
Re-run it after moving the project.
```

and add a bullet after the Saturday/Sunday one:

```markdown
- **Tuesday 09:00** — `gaffer review`, grading every gameweek FPL has
  finalised since the last run. Tuesday rather than Monday because FPL
  finalises a weekend gameweek's bonus and its `data_checked` flag on the
  Monday, sometimes late; a midweek gameweek is picked up the following
  Tuesday or by the Model hub's **Review last week** button. Already-reviewed
  weeks are a no-op that prints one line.
```

and update the removal line:

```markdown
`launchctl unload ~/Library/LaunchAgents/com.gaffer.{advise,prices,snapshot,field,review}.plist`.
```

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: the decision ledger, the banked entry files and the Tuesday review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 12 — the audit, and the gate checklist (unfilled)

**Files:** none created. This task runs commands and reports.

- [ ] **Prove the protected files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/*' tests/test_advise.py tests/test_odds.py \
  tests/test_web_jobs.py scripts/s2_replay.py src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py
```

Expected: **no output at all.** Any line here is a plan failure — report it
rather than reverting quietly, because it means a task needed something the
plan said it would not.

- [ ] **Prove the import-only files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/journal.py src/gaffer/backtest.py \
  frontend/src/hubs/model/JournalTab.tsx
```

Expected: no output (spec §5).

- [ ] **Prove no runtime data was staged.**

```bash
git diff --name-only main...HEAD | grep -E '^(data|reports|models|logs)/|^config\.toml$' || echo "clean"
```

Expected: `clean`.

- [ ] **Security ritual (CONVENTIONS.md §8).**

```bash
git diff main...HEAD | grep -inE 'api[_-]?key|secret|token|password|bearer ' || echo "no keys"
git show main:config.toml && echo "LEAK" || echo "config.toml is not tracked"
```

Expected: `no keys`, then `config.toml is not tracked`.

- [ ] **Full suites.**

```bash
uv run pytest -q
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

Expected: `2105 passed` in Python; the frontend baseline of 328 + 1 skipped
plus this cycle's 13 tab tests, i.e. **341 passed, 1 skipped**; a clean
typecheck; a clean build.

- [ ] **Leave the gate checklist for the orchestrator.** Implementers build the
  driver and never run the gates (CONVENTIONS.md §7). Append this block to
  `docs/superpowers/specs/2026-08-31-gaffer-v8b-decision-loop-design.md` under
  §7, unfilled, and commit it:

```markdown
### Gate results (orchestrator-run)

**G1 — real review.** `uv run gaffer review` over the finished gameweeks.

- [ ] Ledger written to `reports/decision_ledger.json` with all four lanes per
      gameweek.
- [ ] **Reconciliation exact on at least one gameweek.** Every
      `reconciled: false` row investigated and explained here before merge,
      naming the cause (chip week / double gameweek / the simplified-autosub
      caveat at `backtest.py:36-38`). An unexplained mismatch blocks the merge.
- [ ] Idempotent: a second `gaffer review` reviews nothing and prints
      "already reviewed".
- [ ] Δwin% present for gameweeks with a banked `reports/components_gw{N}.parquet`
      (GW2 onward) and **absent with a notice for GW1**, which never had one.
- [ ] Transcribe the printed output verbatim (CONVENTIONS.md §4).

Output:

```
(paste `gaffer review` here)
```

**G2 — rails.** `uv run pytest -q tests/test_v8b_degradation.py`

- [ ] 14 passed.

**G3 — suites and audit.**

- [ ] `uv run pytest -q` — 2105 passed.
- [ ] `npx vitest run` — 341 passed, 1 skipped.
- [ ] `npx tsc --noEmit` — clean.
- [ ] `npm run build` — clean.
- [ ] Zero protected diffs; zero import-only diffs; no runtime data staged.
```

- [ ] **Commit the checklist.**

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v8b-decision-loop-design.md && git commit -m "$(cat <<'EOF'
docs: v8b gate checklist, unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

- [ ] **Report and stop.** Hand the orchestrator: the suite counts, the audit
  output, and the fact that G1-G3 are unrun by design. Do not run the gates.
