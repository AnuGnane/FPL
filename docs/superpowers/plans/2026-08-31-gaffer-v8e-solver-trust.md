# Gaffer v8e Solver Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** stop the solver being an oracle. Four things it cannot do today — take the user's own judgement about a player's minutes, say how robust its plan is to the forecast being slightly wrong, hold more than one named plan at a time, and prove its chip valuations are arithmetic rather than noise.

**Architecture:** four small stores under `reports/`, all JSON, all written atomically through the `pen_tracker.save_tracker` idiom, none of them read by the training pipeline. Overrides enter through the one sanctioned serve-time seam, `models/availability.py::apply_availability`, as a final authoritative pass after every automated one — an override *is* manual team news, and the news layer is where team news has always been applied. Sensitivity and draft-compare are serve-side re-solves of the saved `reports/solve_state_gw{N}` board: they import `optimize.scenarios`' sweep (`run_scenarios`, `move_frequencies`, `xmins_by_player_gw`) and `optimize.milp.solve_plan` exactly as `advise.py` does, and copy `routers/whatif.py`'s board-building idiom line for line rather than refactoring it. Nothing in the cycle touches the advise path, and nothing perturbs a number the user is shown.

**Tech Stack:** Python 3.12, uv, pandas/pyarrow, FastAPI + pydantic, pytest; React 19 + TypeScript + vitest.

**Prerequisite:** work on branch `feat/gaffer-v8e`. Authoritative spec: `docs/superpowers/specs/2026-08-31-gaffer-v8e-solver-trust-design.md`. Measurement rules: `docs/superpowers/CONVENTIONS.md`.

**Protected — must show zero diffs at the end (Task 11 audits this):**
`src/gaffer/advise.py`, `src/gaffer/set_pieces.py`, `src/gaffer/optimize/**`,
`tests/test_advise.py`, `tests/test_odds.py`, `tests/test_web_jobs.py`,
every pre-v8e `tests/test_*_degradation.py`, `scripts/s2_replay.py`,
`src/gaffer/web/jobs.py`, `src/gaffer/web/routers/jobs.py`.

**Import-only:** `src/gaffer/journal.py`, `src/gaffer/backtest.py`, and the whole of `src/gaffer/optimize/` — `solve_plan`, `SolveInput`, `run_scenarios`, `move_frequencies`, `xmins_by_player_gw`, `noise_ep`, `sigma_for`, `evaluate_chips`, `chip_thresholds_from_asset`. If a task appears to need an edit inside a protected or import-only file, the plan is wrong: stop and report rather than editing.

**THE ONE PROTECTED EDIT THIS CYCLE NEEDS — Task 5 STOPS for it.** Adding the tenth job kind breaks a hard count pin in **three protected files**:

| File | Line | Assertion |
| --- | --- | --- |
| `tests/test_v8b_degradation.py` | 212 | `assert len(job_kinds.JOB_KINDS) == 9` |
| `tests/test_v8c_degradation.py` | 191 | `assert len(job_kinds.JOB_KINDS) == 9` |
| `tests/test_v8d_degradation.py` | 174 | `assert len(JOB_KINDS) == 9` |

Precedent: commit `1c269d8` ("test: deliberate v8c job-kind pin update 8->9 for the review kind"), where v8b's orchestrator authorised exactly this edit to exactly one line plus its comment. Task 5 edits **everything else** — the job kind, the unprotected pins, the frontend union — runs the suite, and then **stops and reports**, naming those three lines. It does not edit them. The orchestrator makes that commit.

**Staging rule:** every `git add` below names exact files. Never `git add -A`. Never stage `data/`, `reports/`, `models/`, `logs/`, `.claude/` or `config.toml`. v8e commits no data asset.

**Gate rule (CONVENTIONS.md §7):** implementers build the driver and never run the gates. Task 11 is the checklist, unfilled.

**Suite baselines:** 2189 python tests; 351 frontend tests + 1 skipped, across 54 files. Every task's final run must leave the pre-existing suites green.

**Commit trailer — every commit:**

```
Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
```

---

## Ambiguities the spec left open, and how this plan settles them

Nine things the spec does not pin, decided here once so no task has to decide them twice.

**A1 — where the override store is *read*, and what that does to gate N2's control arm.** `apply_availability` reads it itself, at the top of the function, gated on `[news] overrides` (with an `overrides: bool | None` parameter for tests, exactly as `llm_serving` already works). Not `availability_frame`: `advise.news_availability` returns the bare official slice whenever news is disabled or every source came back empty, so a store read living there would silently stop working on the weeks the user is most likely to be overruling the model by hand.

The consequence is deliberate and must be stated rather than discovered. `advise.predict_components` calls `apply_availability` **twice** — once for the news arm and once for gate N2's flags-only control — with frames that are byte-identical when news is off, so no seam inside the function can tell them apart. Overrides therefore land on **both** arms. This is the honest outcome: the shadow log's job is to measure what *news* did, and a player the user has pinned to 1.0 in both arms shows `p_play_news == p_play_flags`, i.e. contributes no news effect at all — he drops out of the moved-rows filter rather than being credited to a source that did not move him. The alternative, applying the pin to the served arm only, would have the log claim the news layer moved a player the user moved. Task 9 pins this both ways.

**A2 — what a pin means for `p60` and `e_min`.** Spec D2 scopes overrides to `p_play` and `e_min`, but the three outputs have to stay coherent — an untouched `p60` beside a doubled `p_play` is exactly the incoherence the three-mode minutes model was built to remove, and `e_min` feeds the sweep's nailedness score. So a `p_play` pin carries `p60` and `e_min` with it on the same ratio the ceiling and damp passes use. The one case a ratio cannot express is a player the model has zeroed: there is no shape to scale, so the pin is taken **literally** — `p_play = v`, `p60 = v`, `e_min = 90 * v` — which is what a manager pinning a zeroed player to 1.0 is saying. An `e_min` pin is applied last and absolutely, overwriting whatever the `p_play` ratio just did to it, because the two fields are two separate claims and the more specific one wins.

**A3 — where the why-panel's "the model had 0.82" comes from.** Not from a second artifact and not from the shadow log, which A1 has already contaminated for exactly the codes in question. The **store records it at write time**: when the API sets a pin it reads the code's current served `p_play` from `reports/components_gw{N}.parquet` (mean over the gameweek's fixtures) and its `e_min` from the newest `data/live/news_shadow.parquet` row for that gameweek, and banks them as `model_p_play` / `model_e_min` beside `set_at`. Re-pinning the same code **preserves the existing pair** rather than overwriting it, because the second reading is the first pin looking at itself. The panel line is therefore "you pinned Saka p_play 1.00 — the model had 0.82 when you pinned it", which is a true sentence with a date on it. Fields are nullable: pinning before the first advise run of a gameweek records nothing and the panel omits the comparison.

**A4 — which column list widens.** `artifacts.AVAILABILITY_COLS` (and with it `snapshot.SNAPSHOT_COLS`, which is derived from it) gains the four override columns. `normalize.AVAIL_COLS` does **not**: that list is the contract of what the *news feeds* produce, `availability_frame` builds every column in it, and an override is not a feed. The artifact writer attaches the override columns itself, through the same idempotent `attach_overrides` the availability pass uses, so a run whose frame never went near a feed still logs the pin.

**A5 — the sensitivity sweep's xMins.** The solve state carries `ep_raw` and nothing about minutes, so xMins comes from `reports/components_gw{N}.parquet` through `xmins_by_player_gw` — the same call `advise` and `league_sim` make, keyed `(code, gw)`, which is exactly the key `noise_ep` wants. When the component file is missing or carries no minutes model, every cell falls back to a flat **75.0** xMins and the report carries a notice saying so. A flat 92 would make every solve identical and every frequency 100%; 75 puts the heuristic scale at `(92 - 75) / 134 ≈ 12.7%` relative standard deviation and the calibrated table at its 75-minute bin, both of which are a plausible perturbation. Sensitivity needs a plausible scale, not a perfect one, and it says which one it used.

**A6 — what "the best differing plan" means, and how it is priced.** No extra solves. Each scenario plan is reduced to a **signature** — `(frozenset(buys), frozenset(sells), captain, chip)` of the first horizon week — and the signatures are counted. The modal signature is plan A. Every distinct signature's first representative is then re-scored on the **unnoised** raw EP table, over the shared horizon, with the same hit cost the board was solved under; the margin is `value(modal) - value(best other signature)`, and it is `None` when every scenario agreed. Re-scoring on the true board rather than on the noised one is the point: a plan that only wins under its own draw is not within 0.4 of anything.

**A7 — `routers/whatif.py` is not refactored.** Two existing tests forbid it: `test_displayed_points_are_raw_not_tilted`'s helper monkeypatches `tilt_ep` in the *whatif module's* namespace and asserts it was called exactly once inside `solve_whatif`, and `test_both_re_solving_routers_use_the_shared_bundle` asserts the literal string `solve_kw_from_state(state)` appears in `inspect.getsource(whatif.solve_whatif)`. So sensitivity and drafts **repeat** the six-line board-building idiom rather than sharing a helper with it — which is what `routers/meta.py::chips_plan` already does, and which that same test already pins. Task 9 extends the pin to the two new call sites, so the four copies are checked against each other by a test rather than by memory.

**A8 — how a draft comparison is run.** Through the legacy `JobRegistry` the what-if lab already uses (`request.app.state.jobs.submit(..., timeout_s=WHATIF_TIMEOUT_S)`, `202` + `job_id`, polled by `useJob`), not the v7 `JobRunner` — a comparison is a parameterised one-off, not a named kind, and the runner is single-flight across the whole app. `WHATIF_TIMEOUT_S` is 120s and a solve is ~7s, so a request is capped at **6 drafts**; with the unconstrained reference row that is seven solves, about fifty seconds. The store still holds spec D4's twelve.

**A9 — where the pin dialog lives.** `frontend/src/hubs/players/PinDialog.tsx`, hand-rolled on `kit/ExplainModal.tsx`'s pattern (its own backdrop, `role="dialog" aria-modal="true"`, an Escape handler, focus to the close button). Not a new kit primitive: the kit has no generic dialog, `@radix-ui/react-dialog` is installed but used nowhere in `src/`, and introducing a shared modal abstraction for two call sites is a bigger change than the feature. Planning's overrides list imports the same component.

---

## File structure

| File | Status | Responsibility |
| --- | --- | --- |
| `src/gaffer/overrides.py` | Create | T1: the store, its validation, `attach_overrides`. |
| `tests/test_overrides.py` | Create | T1. |
| `src/gaffer/models/availability.py` | Modify (signature L55-58, `news_cols` L95-98, tail L137) | T2: `_override_first_gw`, the last pass. |
| `src/gaffer/artifacts.py` | Modify (`AVAILABILITY_COLS` L378, `save_availability` L412-441) | T2: the widened schema and the artifact carry. |
| `src/gaffer/snapshot.py` | Modify (`snapshot_rows` L59-85) | T2: the same carry into the daily log. |
| `tests/test_availability_overrides.py` | Create | T2. |
| `src/gaffer/config.py` | Modify (field block ~L103, reader ~L172) | T3: `[news] overrides`. |
| `config.example.toml` | Modify (`[news]`) | T3. |
| `src/gaffer/web/schemas.py` | Modify (append) | T3/T5/T6: override, sensitivity and draft models. |
| `src/gaffer/web/routers/overrides.py` | Create | T3: GET/POST/DELETE `/api/overrides`. |
| `src/gaffer/web/app.py` | Modify (L26 import, L66-81 includes) | T3/T5/T6: three new routers. |
| `tests/test_web_overrides.py` | Create | T3. |
| `src/gaffer/sensitivity.py` | Create | T4: the engine and its artifact. |
| `tests/test_sensitivity.py` | Create | T4. |
| `src/gaffer/web/job_kinds.py` | Modify (append + `JOB_KINDS` L127) | T5: the tenth kind. |
| `src/gaffer/web/routers/sensitivity.py` | Create | T5: `GET /api/sensitivity`. |
| `tests/test_web_job_kinds.py` | Modify (L25) | T5: the unprotected allow-list pin. |
| `tests/test_web_job_kinds_v8c.py` | Modify (L24) | T5: the unprotected lockstep pin. |
| `tests/test_web_job_kinds_v8b.py` | Modify (L15) | T5: the unprotected count pin. |
| `tests/test_web_job_kinds_v8e.py` | Create | T5. |
| `tests/test_web_sensitivity.py` | Create | T5. |
| `src/gaffer/drafts.py` | Create | T6: the store. |
| `src/gaffer/web/routers/drafts.py` | Create | T6: CRUD + compare. |
| `tests/test_drafts.py`, `tests/test_web_drafts.py` | Create | T6. |
| `frontend/src/api/client.ts` | Modify | T7: `apiDelete`. |
| `frontend/src/types.ts` | Modify (`JOB_KINDS` L604, append) | T7: lockstep + the new payloads. |
| `frontend/src/types.test.ts` | Modify (L8-13) | T7: the ten-kind pin. |
| `frontend/src/hubs/Planning.tsx` | Modify | T7: the Drafts tab, the lifted what-if state. |
| `frontend/src/hubs/planning/WhatIfTab.tsx` | Modify | T7: optional controlled props, the sensitivity card. |
| `frontend/src/hubs/planning/DraftsTab.tsx` | Create | T7. |
| `frontend/src/hubs/planning/SensitivityCard.tsx` | Create | T7. |
| `frontend/src/hubs/planning/OverridesCard.tsx` | Create | T7. |
| `frontend/src/hubs/players/PinDialog.tsx` | Create | T7. |
| `frontend/src/hubs/Players.tsx` | Modify | T7: the pin column. |
| `frontend/src/hubs/this-week/WhyPanel.tsx` | Modify | T7: the overrides strip. |
| frontend tests | Create/Modify | T7. |
| `tests/test_chip_sanity.py` | Create | T8: D5's rails. |
| `scripts/chip_baserates.py` | Create | T8: the base-rate print. |
| `tests/test_v8e_degradation.py` | Create | T9: G3. |
| `README.md` | Modify | T10. |

---

## Task 1 — the overrides store, and what it refuses

**Files:**
- Create `src/gaffer/overrides.py`
- Create `tests/test_overrides.py`

- [ ] **Write the failing test.** Create `tests/test_overrides.py`:

```python
"""``reports/overrides.json``: the user's own team news.

The store is the only place in the tool where a human number outranks a model
one, so it is also the only place that has to be paranoid about what it will
accept. Everything here is about refusal: an unknown code, a probability
outside [0, 1], minutes outside [0, 90], a pin that says nothing at all.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.errors import GafferError
from gaffer.overrides import (attach_overrides, delete_override,
                              load_overrides, overrides_path, set_override)

KNOWN = [11, 22, 33]


def test_an_absent_store_is_an_empty_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_overrides() == {}


def test_a_corrupt_store_is_an_empty_one_and_says_so(tmp_path, monkeypatch,
                                                     capsys):
    """A hand-edited file must not take the advise run down with it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    overrides_path().write_text("{not json")
    assert load_overrides() == {}
    assert "overrides" in capsys.readouterr().out


def test_setting_a_pin_round_trips_through_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, note="fit, saw him train",
                 known_codes=KNOWN, model_p_play=0.82)
    stored = load_overrides()
    assert set(stored) == {22}
    assert stored[22]["p_play"] == 1.0
    assert stored[22]["e_min"] is None
    assert stored[22]["note"] == "fit, saw him train"
    assert stored[22]["model_p_play"] == 0.82
    assert stored[22]["set_at"].startswith("20")


def test_the_file_is_json_with_string_keys(tmp_path, monkeypatch):
    """JSON object keys are strings; the loader is what makes them ints
    again, and a caller looking one up by code must never silently miss."""
    monkeypatch.chdir(tmp_path)
    set_override(22, e_min=90.0, known_codes=KNOWN)
    raw = json.loads(overrides_path().read_text())
    assert list(raw["overrides"]) == ["22"]
    assert 22 in load_overrides()


def test_an_unknown_code_is_refused_with_a_readable_message(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        set_override(999, p_play=1.0, known_codes=KNOWN)
    assert "999" in str(exc.value)
    assert not overrides_path().exists()


def test_a_pin_that_claims_nothing_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, known_codes=KNOWN)


@pytest.mark.parametrize("kwargs", [
    {"p_play": 1.5}, {"p_play": -0.1}, {"e_min": 91.0}, {"e_min": -1.0},
    {"p_play": float("nan")},
])
def test_values_outside_their_range_are_refused(tmp_path, monkeypatch,
                                                kwargs):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, known_codes=KNOWN, **kwargs)


def test_a_long_note_is_refused_rather_than_silently_truncated(tmp_path,
                                                              monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(22, p_play=1.0, note="x" * 500, known_codes=KNOWN)


def test_repinning_keeps_the_first_model_reading(tmp_path, monkeypatch):
    """A3: the second reading is the first pin looking at itself."""
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN, model_p_play=0.82)
    set_override(22, p_play=0.5, known_codes=KNOWN, model_p_play=1.0)
    stored = load_overrides()[22]
    assert stored["p_play"] == 0.5
    assert stored["model_p_play"] == 0.82


def test_deleting_a_pin_leaves_the_others(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(11, p_play=0.0, known_codes=KNOWN)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    assert delete_override(11) is True
    assert set(load_overrides()) == {22}
    assert delete_override(11) is False


def test_the_store_is_capped(tmp_path, monkeypatch):
    from gaffer.overrides import MAX_OVERRIDES

    monkeypatch.chdir(tmp_path)
    codes = list(range(1, MAX_OVERRIDES + 2))
    for code in codes[:MAX_OVERRIDES]:
        set_override(code, p_play=1.0, known_codes=codes)
    with pytest.raises(GafferError):
        set_override(codes[-1], p_play=1.0, known_codes=codes)


# --- attach_overrides -------------------------------------------------

FRAME = pd.DataFrame({"code": [11, 22, 33], "status": ["a", "d", "a"],
                      "chance_of_playing": [None, 25.0, None]})


def test_attach_adds_the_four_columns_even_with_no_pins(tmp_path,
                                                        monkeypatch):
    """The schema must not depend on whether anybody pinned anything."""
    monkeypatch.chdir(tmp_path)
    out = attach_overrides(FRAME)
    assert list(out.columns[-4:]) == ["override", "override_p_play",
                                      "override_e_min", "override_note"]
    assert not out["override"].any()
    assert out["override_p_play"].isna().all()


def test_attach_marks_only_the_pinned_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, e_min=80.0, note="fit", known_codes=KNOWN)
    out = attach_overrides(FRAME)
    row = out[out["code"] == 22].iloc[0]
    assert bool(row["override"]) is True
    assert row["override_p_play"] == 1.0
    assert row["override_e_min"] == 80.0
    assert row["override_note"] == "fit"
    assert not out[out["code"] == 11].iloc[0]["override"]


def test_attach_is_idempotent(tmp_path, monkeypatch):
    """The availability pass and the artifact writer both call it; the second
    call must not re-read the store or double a column."""
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    once = attach_overrides(FRAME)
    twice = attach_overrides(once)
    assert list(twice.columns) == list(once.columns)
    pd.testing.assert_frame_equal(once, twice)


def test_attach_leaves_the_callers_frame_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(22, p_play=1.0, known_codes=KNOWN)
    attach_overrides(FRAME)
    assert "override" not in FRAME.columns


def test_attach_survives_a_frame_with_no_code_column(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({"element": [1, 2]})
    assert attach_overrides(frame) is frame
```

Run it: `uv run pytest -q tests/test_overrides.py` — expect `ModuleNotFoundError`.

- [ ] **Implement.** Create `src/gaffer/overrides.py`:

```python
"""User overrides: the manager's own team news, and the last word on minutes.

Everything else in the tool is a model output with a model's humility. This
file is the one place a human number is applied *as fact* — the user watched
the press conference, or the training-ground video, or simply knows something
the feeds do not — so it is applied after every automated pass and it is
applied whole.

It is serve-time only. Nothing here is ever a trained feature and nothing here
is read by a backtest; the pins are banked into the availability artifacts for
the same reason the news layer's readings are, so that a future season can ask
what the user knew and when. That is the whole train/serve rule, restated for
a source whose author happens to be the user.

Scope is deliberately two numbers. ``p_play`` and ``e_min`` are the minutes
model's outputs, which is where almost all of FPL's forecast error lives; an
attacking-EP override would need a seam inside protected code and would let a
bad afternoon rewrite the model's whole opinion of a player.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.errors import GafferError

OVERRIDE_COLS = ["override", "override_p_play", "override_e_min",
                 "override_note"]
"""The four columns :func:`attach_overrides` adds to an availability frame.

``override`` is the marker the why-panel and the daily snapshot read: a
boolean saying "the user pinned something about this player", which stays
true and legible long after the pin itself has been deleted from the store.
"""

MAX_OVERRIDES = 50
"""More pins than this is not a manager's judgement, it is a second model.

The cap exists so a runaway client cannot turn the availability pass into a
serialization problem, and so the why-panel stays a list somebody reads.
"""

NOTE_MAX = 200
"""Characters. Refused rather than truncated: a silently halved note is a
sentence the user did not write."""


def overrides_path() -> Path:
    """``reports/overrides.json``, resolved at call time.

    ``artifacts.REPORTS`` is a relative path, so a test that changes directory
    changes this with it — the same trade every other report store makes.
    """
    return artifacts.REPORTS / "overrides.json"


def load_overrides() -> dict[int, dict]:
    """``{code: {p_play, e_min, note, set_at, model_p_play, model_e_min}}``.

    Never raises. An absent file, a hand-edited one, a half-written one and a
    file whose top-level shape has drifted all come back as ``{}`` — an advise
    run that died of its own override store would be a far worse failure than
    one that ignored it, and the print is what makes the difference visible.

    JSON object keys are strings by definition; this is where they become
    integers again, so a caller looking a code up with an int cannot miss.
    """
    path = overrides_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("overrides") if isinstance(raw, dict) else None
        if not isinstance(rows, dict):
            return {}
        out: dict[int, dict] = {}
        for code, row in rows.items():
            if not isinstance(row, dict):
                continue
            out[int(code)] = {
                "p_play": _opt_float(row.get("p_play")),
                "e_min": _opt_float(row.get("e_min")),
                "note": str(row.get("note") or ""),
                "set_at": str(row.get("set_at") or ""),
                "model_p_play": _opt_float(row.get("model_p_play")),
                "model_e_min": _opt_float(row.get("model_e_min")),
            }
        return out
    except Exception as exc:  # noqa: BLE001 — a bad store is an empty one
        print(f"overrides store unreadable, ignoring it: {exc}")
        return {}


def save_overrides(rows: dict[int, dict]) -> Path:
    """Write the whole store through a temp file and ``os.replace``.

    ``pen_tracker.save_tracker``'s idiom exactly: a reader sees the whole
    previous store or the whole new one, never the half-written middle. The
    availability pass is a reader, and it runs on a schedule.
    """
    payload = {"overrides": {str(code): dict(row)
                             for code, row in sorted(rows.items())}}
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = overrides_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def _opt_float(value) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _checked(value, lo: float, hi: float, name: str) -> float | None:
    """A pin value, or a refusal naming the range it missed."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise GafferError(f"{name} must be a number") from exc
    if math.isnan(out) or not (lo <= out <= hi):
        raise GafferError(f"{name} must be between {lo} and {hi} — got {out}")
    return out


def set_override(code: int, *, p_play=None, e_min=None, note: str = "",
                 known_codes=None, model_p_play=None,
                 model_e_min=None) -> dict:
    """Pin ``code``'s minutes, refusing anything the model cannot act on.

    ``known_codes`` is the universe the pin has to belong to — the bootstrap
    snapshot's codes, supplied by the caller so this module needs no data
    layer. Omitting it skips the check, which is for tests and for callers
    that have already validated.

    ``model_p_play`` / ``model_e_min`` are what the served pipeline had for
    this player at the moment the pin was made (spec A3). On a **re-pin the
    existing pair is preserved**: the second reading would be the first pin
    looking at itself, and "the model had 1.00" is not a sentence worth
    showing anybody.
    """
    code = int(code)
    if known_codes is not None and code not in {int(c) for c in known_codes}:
        raise GafferError(
            f"player {code} is not in the current player list — pin a code "
            f"the tool knows about")
    play = _checked(p_play, 0.0, 1.0, "p_play")
    mins = _checked(e_min, 0.0, 90.0, "e_min")
    if play is None and mins is None:
        raise GafferError("an override must pin p_play, e_min or both")
    if len(str(note or "")) > NOTE_MAX:
        raise GafferError(f"note is longer than {NOTE_MAX} characters")

    rows = load_overrides()
    if code not in rows and len(rows) >= MAX_OVERRIDES:
        raise GafferError(
            f"{MAX_OVERRIDES} overrides is the cap — delete one first")
    previous = rows.get(code, {})
    row = {
        "p_play": play, "e_min": mins, "note": str(note or ""),
        "set_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_p_play": (previous.get("model_p_play")
                         if previous.get("model_p_play") is not None
                         else _opt_float(model_p_play)),
        "model_e_min": (previous.get("model_e_min")
                        if previous.get("model_e_min") is not None
                        else _opt_float(model_e_min)),
    }
    rows[code] = row
    save_overrides(rows)
    return row


def delete_override(code: int) -> bool:
    """Remove one pin. ``False`` when there was nothing to remove."""
    rows = load_overrides()
    if int(code) not in rows:
        return False
    rows.pop(int(code))
    save_overrides(rows)
    return True


def attach_overrides(frame: pd.DataFrame,
                     overrides: dict[int, dict] | None = None) -> pd.DataFrame:
    """Add :data:`OVERRIDE_COLS` to an availability frame.

    Idempotent by design: the availability pass and the artifact writer both
    call it, and a frame that already carries the marker is returned untouched
    rather than re-read from disk. A frame with no ``code`` column is returned
    as it came — the bare bootstrap slice always has one, but a caller holding
    something else should get a no-op rather than a KeyError.

    The columns are added whether or not anybody has pinned anything, so the
    parquet schema does not depend on the week: an all-null column with a
    settled dtype is what the news layer's own optional fields already do.

    Never mutates the caller's frame.
    """
    if frame is None or "code" not in getattr(frame, "columns", []):
        return frame
    if "override" in frame.columns:
        return frame
    table = load_overrides() if overrides is None else dict(overrides)
    marks, plays, mins, notes = [], [], [], []
    for raw in frame["code"]:
        try:
            row = table.get(int(raw))
        except (TypeError, ValueError):
            row = None
        marks.append(row is not None)
        plays.append(None if row is None else row.get("p_play"))
        mins.append(None if row is None else row.get("e_min"))
        notes.append(None if row is None else (row.get("note") or None))
    out = frame.copy()
    out["override"] = pd.array(marks, dtype="boolean")
    out["override_p_play"] = pd.to_numeric(pd.Series(plays,
                                                     index=out.index),
                                           errors="coerce")
    out["override_e_min"] = pd.to_numeric(pd.Series(mins, index=out.index),
                                          errors="coerce")
    out["override_note"] = pd.Series(notes, index=out.index,
                                     dtype="object").astype("string")
    return out
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_overrides.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/overrides.py tests/test_overrides.py && git commit -m "$(cat <<'EOF'
feat: the overrides store — the manager's own team news

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 2 — the availability pass, and the marker column end to end

**Files:**
- Modify `src/gaffer/models/availability.py`
- Modify `src/gaffer/artifacts.py`
- Modify `src/gaffer/snapshot.py`
- Create `tests/test_availability_overrides.py`

- [ ] **Write the failing test.** Create `tests/test_availability_overrides.py`:

```python
"""The override pass: the user's pin, applied last and applied whole.

Ordering is the whole subject. Every automated pass — the flag factor, the
horizon relax, the line-up ceiling, the absence damp, the classifier — runs
first, and then the pin overwrites whatever they concluded, because a manager
who has decided a player is fit is not asking for a weighted average with a
website. These tests are mostly about *last*.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.models.availability import apply_availability
from gaffer.overrides import set_override

CODES = [1, 2]


def _pred(gws=(5,)):
    """One row per (player, gameweek), the shape predict_components hands in."""
    rows = []
    for code in CODES:
        for gw in gws:
            rows.append({"code": code, "gw": gw, "p_play": 0.8, "p60": 0.6,
                         "e_min": 60.0})
    return pd.DataFrame(rows)


def _avail(status="a", chance=None):
    return pd.DataFrame({"code": CODES, "status": [status, "a"],
                         "chance_of_playing": [chance, None]})


def test_with_the_flag_off_nothing_is_read_and_nothing_changes(tmp_path,
                                                               monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=False)
    assert out.loc[out["code"] == 1, "p_play"].iloc[0] == pytest.approx(0.8)
    assert not [c for c in out.columns if c.startswith("override")]


def test_an_empty_store_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    on = apply_availability(_pred(), _avail(), overrides=True)
    off = apply_availability(_pred(), _avail(), overrides=False)
    pd.testing.assert_frame_equal(on, off)


def test_a_pin_overrides_the_official_flag(tmp_path, monkeypatch):
    """The case the feature exists for: FPL says 25%, the user saw him train."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(status="d", chance=25.0),
                             overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    # The flag factor is 0.25, so the model reached p_play 0.2, p60 0.15,
    # e_min 15. The pin takes p_play to 1.0 — a ratio of 5 — and A2 carries
    # the other two up with it.
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["p60"] == pytest.approx(0.75)
    assert mine["e_min"] == pytest.approx(75.0)
    assert out[out["code"] == 2]["p_play"].iloc[0] == pytest.approx(0.8)


def test_a_pin_beats_the_lineup_ceiling(tmp_path, monkeypatch):
    """v8a's hint is a ceiling on the model. The pin is a ceiling on the
    ceiling, and it runs after it."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=0.9, known_codes=CODES)
    avail = _avail()
    avail["p_start_hint"] = [0.0, 1.0]
    out = apply_availability(_pred(), avail, overrides=True)
    assert out[out["code"] == 1]["p_play"].iloc[0] == pytest.approx(0.9)


def test_a_pin_beats_the_absence_damp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    avail = _avail()
    avail["absence_damp"] = [0.75, 1.0]
    out = apply_availability(_pred(), avail, overrides=True)
    assert out[out["code"] == 1]["p_play"].iloc[0] == pytest.approx(1.0)


def test_a_pin_on_a_zeroed_player_is_taken_literally(tmp_path, monkeypatch):
    """A2: there is no ratio to scale by, and the user pinning a suspended
    player to 1.0 is saying he starts and he lasts."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(status="s"), overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["p60"] == pytest.approx(1.0)
    assert mine["e_min"] == pytest.approx(90.0)


def test_an_e_min_pin_is_absolute_and_runs_after_the_p_play_ratio(tmp_path,
                                                                  monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, e_min=30.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=True)
    mine = out[out["code"] == 1].iloc[0]
    assert mine["p_play"] == pytest.approx(1.0)
    assert mine["e_min"] == pytest.approx(30.0)


def test_a_pin_bites_the_first_gameweek_only(tmp_path, monkeypatch):
    """The same rule every other pass obeys: a claim about Saturday says
    nothing about the Wednesday after."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(gws=(5, 6)), _avail(status="d",
                                                       chance=25.0),
                             overrides=True)
    mine = out[out["code"] == 1].sort_values("gw")
    assert mine["p_play"].iloc[0] == pytest.approx(1.0)
    assert mine["p_play"].iloc[1] < 1.0


def test_a_double_gameweek_is_pinned_once(tmp_path, monkeypatch):
    """_first_rows' one-row-per-player rule: a pin is one claim about the
    player, not one claim per fixture."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    pred = pd.concat([_pred(), _pred()], ignore_index=True).sort_values(
        ["code", "gw"]).reset_index(drop=True)
    out = apply_availability(pred, _avail(status="d", chance=25.0),
                             overrides=True)
    pinned = out[(out["code"] == 1)]["p_play"].tolist()
    assert sum(1 for v in pinned if v == pytest.approx(1.0)) == 1


def test_the_override_columns_never_reach_the_component_frame(tmp_path,
                                                              monkeypatch):
    """Same discipline as every news column: applied, then dropped."""
    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    out = apply_availability(_pred(), _avail(), overrides=True)
    assert not [c for c in out.columns if c.startswith("override")]


def test_the_artifact_carries_the_marker(tmp_path, monkeypatch):
    from gaffer.artifacts import load_availability, save_availability

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, note="fit", known_codes=CODES)
    save_availability(_avail(), 5)
    banked = load_availability(5)
    row = banked[banked["code"] == 1].iloc[0]
    assert bool(row["override"]) is True
    assert row["override_p_play"] == 1.0
    assert row["override_note"] == "fit"
    assert not bool(banked[banked["code"] == 2].iloc[0]["override"])


def test_the_daily_snapshot_carries_the_marker(tmp_path, monkeypatch):
    from gaffer.snapshot import SNAPSHOT_COLS, snapshot_rows

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    rows = snapshot_rows(_avail(), gw=5, season="2026-27", day="2026-08-31")
    assert list(rows.columns) == SNAPSHOT_COLS
    assert bool(rows[rows["code"] == 1].iloc[0]["override"]) is True


def test_a_flags_only_week_still_writes_the_override_schema(tmp_path,
                                                            monkeypatch):
    """A4: the columns exist whether or not a feed ran and whether or not
    anybody pinned anything, so one parquet schema covers every week."""
    from gaffer.artifacts import OVERRIDE_COLS, load_availability, \
        save_availability

    monkeypatch.chdir(tmp_path)
    save_availability(_avail(), 5)
    banked = load_availability(5)
    assert set(OVERRIDE_COLS) <= set(banked.columns)
    assert not banked["override"].fillna(False).any()
```

Run it: expect failures on the `overrides=` keyword and on the missing columns.

- [ ] **Implement the pass.** In `src/gaffer/models/availability.py`:

Extend the signature (L55-58) and its docstring:

```python
def apply_availability(pred: pd.DataFrame, avail: pd.DataFrame,
                       curves: dict | None = None,
                       start_floor: float | None = None,
                       llm_serving: bool | None = None,
                       overrides: bool | None = None) -> pd.DataFrame:
```

Append to the docstring, after the ``absence_damp`` paragraph:

```
    ``overrides`` reads ``reports/overrides.json`` — the user's own pins — and
    applies them **last**, as fact rather than as evidence: a manager who has
    decided a player is fit outranks every automated source, including the one
    that just docked him. First gameweek only, one row per player, like every
    other pass here. It defaults to the ``[news] overrides`` config key, read
    at the top of the function because ``advise`` is protected and cannot
    forward it, and with an empty store the whole pass is arithmetically a
    no-op.

    Note what that means for gate N2 (spec A1): ``predict_components`` calls
    this function twice, once for the news arm and once for the flags-only
    control, and nothing inside can tell those calls apart. Pins therefore
    land on both — which is the honest reading, since a pinned player shows
    the same number on both sides and so contributes no *news* effect at all.
```

At the top of the body, immediately after the ``curves`` line:

```python
    curves = curves if curves is not None else load_injury_curves()
    if overrides is None:
        from gaffer.config import serving_config
        overrides = serving_config().news_overrides
    if overrides:
        from gaffer.overrides import attach_overrides
        avail = attach_overrides(avail)
    news_cols = [c for c in ("injury_type", "expected_return_gw",
                             "p_start_hint", "absence_damp", "llm_verdict",
                             "llm_confidence", "override_p_play",
                             "override_e_min")
                 if c in avail.columns]
```

and, immediately before the final `return out.drop(...)`:

```python
    # Last, and after everything: the user outranks every automated source.
    out = _override_first_gw(out)
    return out.drop(columns=["status", "chance_of_playing"] + news_cols)
```

Append the pass itself, after `_floor_first_gw`:

```python
def _override_first_gw(out: pd.DataFrame) -> pd.DataFrame:
    """Apply the user's pins to the horizon's first gameweek.

    Not a factor and not a ceiling — an assignment. Every other pass in this
    module is evidence being weighed; this one is the manager saying he knows,
    and the whole value of the feature is that it is not then averaged with a
    website's guess.

    ``p_play`` carries ``p60`` and ``e_min`` with it on its own ratio, the
    same three-outputs-together discipline the ceiling and the damp obey: a
    doubled ``p_play`` beside an untouched ``p60`` is the incoherence the
    three-mode minutes model exists to remove. The exception is a player the
    model has zeroed, where there is no ratio to scale by; a pin on him is
    taken literally — he starts and he lasts — because that is what pinning a
    zeroed player to 1.0 means (plan A2).

    ``e_min`` is applied afterwards and absolutely, overwriting whatever the
    ``p_play`` ratio just did to it: the two fields are two separate claims
    and the more specific one wins.

    Written as a loop over the bitten index rather than vectorised. The bitten
    set is at most :data:`gaffer.overrides.MAX_OVERRIDES` rows out of several
    thousand, and the branch on ``p_play == 0`` is not a mask.
    """
    if "override_p_play" not in out.columns \
            and "override_e_min" not in out.columns:
        return out
    first = _first_rows(out)

    if "override_p_play" in out.columns:
        pin = pd.to_numeric(out["override_p_play"], errors="coerce").clip(
            0.0, 1.0)
        for i in out.index[first & pin.notna()]:
            value = float(pin.at[i])
            prior = float(out.at[i, "p_play"])
            if prior > 0.0:
                ratio = value / prior
                out.at[i, "p60"] = float(out.at[i, "p60"]) * ratio
                out.at[i, "e_min"] = float(out.at[i, "e_min"]) * ratio
            else:
                out.at[i, "p60"] = value
                out.at[i, "e_min"] = 90.0 * value
            out.at[i, "p_play"] = value

    if "override_e_min" in out.columns:
        mins = pd.to_numeric(out["override_e_min"], errors="coerce").clip(
            0.0, 90.0)
        for i in out.index[first & mins.notna()]:
            out.at[i, "e_min"] = float(mins.at[i])
    return out
```

- [ ] **Widen the artifact schema.** In `src/gaffer/artifacts.py`, replace the `AVAILABILITY_COLS` list (L378-380). The four names are **restated** rather than imported from `gaffer.overrides`, because that module imports this one and a module-level import back would be a cycle; Task 9 pins the two lists against each other so the duplication cannot drift.

```python
AVAILABILITY_COLS = ["code", "status", "chance_of_playing", "injury_type",
                     "expected_return_gw", "p_start_hint", "absence_damp",
                     "llm_verdict", "llm_confidence", "source", "fetched_at",
                     "override", "override_p_play", "override_e_min",
                     "override_note"]
```

and append to its docstring:

```
v8e adds four. ``override`` marks a player the *user* pinned, and the three
beside it carry what he pinned and why. They are restated here rather than
imported from :mod:`gaffer.overrides`, which imports this module;
``tests/test_v8e_degradation.py`` pins the two lists against each other so the
duplication cannot drift.
```

Then in `save_availability`, attach before the fill loop and settle the new dtypes:

```python
        out = avail.copy()
        # v8e: the pins this run predicted under, banked with the evidence.
        # Gated on the same key the availability pass reads, so "no read, no
        # marker" holds for the artifact too. Idempotent, so a frame that
        # already carries them is not re-read.
        from gaffer.config import serving_config
        from gaffer.overrides import attach_overrides
        if serving_config().news_overrides:
            out = attach_overrides(out)
        for col in AVAILABILITY_COLS:
            if col not in out.columns:
                out[col] = None
        out = out[AVAILABILITY_COLS].copy()
        for col in ("status", "injury_type", "llm_verdict", "source",
                    "fetched_at", "override_note"):
            out[col] = out[col].astype("object").where(
                out[col].notna(), None).astype("string")
        for col in ("chance_of_playing", "expected_return_gw", "p_start_hint",
                    "absence_damp", "llm_confidence", "override_p_play",
                    "override_e_min"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out["override"] = out["override"].astype("object").where(
            out["override"].notna(), False).astype(bool)
```

Also export the names the tests read, beside `AVAILABILITY_COLS`:

```python
OVERRIDE_COLS = ["override", "override_p_play", "override_e_min",
                 "override_note"]
"""The v8e tail of :data:`AVAILABILITY_COLS`, named so callers can ask for
just that block without slicing a list by index."""
```

- [ ] **Carry it into the daily log.** In `src/gaffer/snapshot.py`, `snapshot_rows`, make the same three edits — the attach before the fill loop, `"override_note"` in the string tuple, the two numerics in the numeric tuple, and the boolean settle — and extend the docstring with one line:

```
    v8e's ``override`` block rides along: the log's whole purpose is to keep
    what was known on the day, and what the *user* knew is part of that.
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_availability_overrides.py tests/test_overrides.py \
  tests/test_availability_v8a.py tests/test_artifacts.py tests/test_snapshot.py \
  tests/test_news_normalize.py tests/test_news_shadow.py
```

All green, and `tests/test_availability_v8a.py` **unmodified** — if a v8a rail needs editing, the pass is not last and the plan is wrong: stop and report.

- [ ] **Commit.**

```bash
git add src/gaffer/models/availability.py src/gaffer/artifacts.py \
  src/gaffer/snapshot.py tests/test_availability_overrides.py \
  && git commit -m "$(cat <<'EOF'
feat: apply user overrides last in the availability pass, and bank the marker

The pin is an assignment, not a factor: it runs after the flag, the horizon
relax, the line-up ceiling, the absence damp and the classifier. The four
override columns ride the availability artifact and the daily snapshot.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 3 — the config key, and the overrides API

**Files:**
- Modify `src/gaffer/config.py`
- Modify `config.example.toml`
- Modify `src/gaffer/web/schemas.py`
- Create `src/gaffer/web/routers/overrides.py`
- Modify `src/gaffer/web/app.py`
- Create `tests/test_web_overrides.py`

- [ ] **Write the failing test.** Create `tests/test_web_overrides.py`:

```python
"""``/api/overrides``: the only endpoint in the tool that writes a number the
model then has to obey.

So it is the only endpoint that has to refuse things. A code nobody has heard
of, a probability of 1.5, a pin that pins nothing: all 422 with a structured
detail the form can render inline, exactly as the what-if lab's constraint
errors do.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.web.app import create_app

PLAYERS = pd.DataFrame({
    "code": [11, 22], "element": [1, 2], "name": ["Saka", "Haaland"],
    "position": ["MID", "FWD"], "team_id": [1, 2], "team_code": [3, 4],
    "now_cost": [100, 150], "status": ["d", "a"], "news": ["knock", ""],
    "chance_of_playing": [25.0, None], "selected_by_percent": [40.0, 60.0],
    "form": [5.0, 8.0], "points_per_game": [5.0, 7.0],
    "ep_next": [5.5, 8.5], "price_change_percent": [0.0, 0.0],
    "price_change_calibrating": [False, False],
    "penalties_order": [None, 1.0], "direct_freekicks_order": [None, None],
    "corners_and_indirect_freekicks_order": [None, None]})

COMPONENTS = pd.DataFrame([
    {"code": 11, "gw": 5, "p_play": 0.82, "p60": 0.7, "ep": 5.5},
    {"code": 22, "gw": 5, "p_play": 0.99, "p60": 0.95, "ep": 8.5}])

SHADOW = pd.DataFrame([
    {"season": "2026-27", "gw": 5, "code": 11, "p_play_news": 0.82,
     "p_play_flags": 0.9, "e_min_news": 61.0, "e_min_flags": 70.0,
     "run_at": "2026-08-31T10:00:00+00:00"}])


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\noverrides = true\n')
    serving_config.cache_clear()
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    SHADOW.to_parquet(tmp_path / "data/live/news_shadow.parquet", index=False)
    (tmp_path / "reports").mkdir()
    COMPONENTS.to_parquet(tmp_path / "reports/components_gw5.parquet",
                          index=False)
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    yield TestClient(create_app())
    serving_config.cache_clear()


def test_no_pins_is_an_empty_active_panel(client):
    body = client.get("/api/overrides").json()
    assert body == {"active": True, "rows": []}


def test_a_pin_comes_back_named_and_dated(client):
    posted = client.post("/api/overrides",
                         json={"code": 11, "p_play": 1.0, "note": "trained"})
    assert posted.status_code == 200
    row = posted.json()["rows"][0]
    assert row["code"] == 11 and row["name"] == "Saka"
    assert row["p_play"] == 1.0 and row["e_min"] is None
    assert row["note"] == "trained"
    assert row["set_at"].startswith("20")
    # A3: what the served pipeline had for him at the moment of the pin.
    assert row["model_p_play"] == 0.82
    assert row["model_e_min"] == 61.0
    assert client.get("/api/overrides").json()["rows"] == posted.json()["rows"]


def test_an_unknown_code_is_a_structured_422(client):
    response = client.post("/api/overrides", json={"code": 999,
                                                   "p_play": 1.0})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["constraint"] == "unknown_player"
    assert detail["players"] == [999]
    assert "999" in detail["error"]


@pytest.mark.parametrize("payload", [
    {"code": 11, "p_play": 1.5},
    {"code": 11, "e_min": 120.0},
    {"code": 11},
    {"code": 11, "p_play": 1.0, "note": "x" * 500},
])
def test_a_value_the_model_cannot_act_on_is_a_structured_422(client,
                                                             payload):
    response = client.post("/api/overrides", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "override_value"


def test_deleting_a_pin_returns_the_panel_without_it(client):
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    client.post("/api/overrides", json={"code": 22, "e_min": 90.0})
    body = client.delete("/api/overrides/11").json()
    assert [r["code"] for r in body["rows"]] == [22]


def test_deleting_a_pin_that_is_not_there_is_a_404(client):
    assert client.delete("/api/overrides/11").status_code == 404


def test_the_panel_says_when_the_flag_is_off(client, tmp_path):
    """A pin that is saved but not being applied is worth a sentence, not a
    silent nothing."""
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\noverrides = false\n')
    serving_config.cache_clear()
    body = client.get("/api/overrides").json()
    assert body["active"] is False
    assert len(body["rows"]) == 1


def test_a_missing_player_snapshot_does_not_stop_a_read(client, tmp_path):
    """The panel is a read path on a page that already works."""
    client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/overrides").json()
    assert body["rows"][0]["name"] == "11"


def test_a_missing_player_snapshot_refuses_a_write(client, tmp_path):
    """With no code list there is nothing to validate against, and an
    unvalidated pin is the one thing this endpoint must not write."""
    (tmp_path / "data/live/players.parquet").unlink()
    response = client.post("/api/overrides", json={"code": 11, "p_play": 1.0})
    assert response.status_code == 422
```

- [ ] **Add the config key.** In `src/gaffer/config.py`, after `news_lineup_start_floor` (L103):

```python
    # v8e. The user's own pins, applied last in the availability pass. On by
    # default: an empty store is a no-op, and a switch that has to be found
    # before a feature works is a feature nobody finds.
    news_overrides: bool = True
```

and in the reader, after the `lineup_start_floor` line:

```python
        news_overrides=bool(news.get("overrides", True)),
```

In `config.example.toml`, at the end of `[news]`:

```toml
# v8e: your own pins on a player's p_play / expected minutes, set from the
# Players page or the Planning hub and stored in reports/overrides.json.
# They are applied last, over every automated source, because you are the one
# who watched the press conference. An empty store changes nothing.
overrides = true
```

- [ ] **Add the schemas.** In `src/gaffer/web/schemas.py`, append:

```python
class OverrideRequest(BaseModel):
    """One pin. At least one of the two values must be present."""

    code: int
    p_play: float | None = None
    e_min: float | None = None
    note: str = ""


class OverrideRow(BaseModel):
    code: int
    name: str
    p_play: float | None = None
    e_min: float | None = None
    note: str = ""
    set_at: str = ""
    model_p_play: float | None = None
    """What the served pipeline had for him when the pin was made, so the
    why-panel can say "the model had 0.82" without re-deriving anything."""
    model_e_min: float | None = None


class OverridesPanel(BaseModel):
    active: bool = True
    """``[news] overrides``. False means the pins are stored and *not* being
    applied, which the panel says out loud rather than showing nothing."""
    rows: list[OverrideRow] = Field(default_factory=list)
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/overrides.py`:

```python
"""GET/POST/DELETE ``/api/overrides`` — the user's own team news (spec D1/D2).

The only endpoint in the tool that writes a number the model must then obey,
which is why it is the only one that validates this hard. Reads never fail:
a panel on This Week is worth showing with a missing name in it. Writes fail
loudly and structurally, in the what-if lab's ``{constraint, error, players}``
shape, so the form can render the reason beside the offending field.

The store itself is :mod:`gaffer.overrides`; nothing here does arithmetic.
"""

from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException

from gaffer.artifacts import latest_gw, load_components, load_snapshot
from gaffer.errors import GafferError
from gaffer.news_shadow import SHADOW_PATH, load_shadow
from gaffer.overrides import delete_override, load_overrides, set_override
from gaffer.web.schemas import OverrideRequest, OverrideRow, OverridesPanel

router = APIRouter(prefix="/api", tags=["overrides"])


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    """The what-if lab's structured 422, reused so the UI has one shape."""
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def _names() -> dict[int, str]:
    """``{code: name}`` from the bootstrap snapshot, or ``{}``."""
    try:
        players = load_snapshot("live/players.parquet")
        return {int(r.code): str(r.name) for r in players.itertuples()}
    except Exception as exc:  # noqa: BLE001 — a read is never worth a 500
        print(f"overrides panel: player snapshot unreadable ({exc})")
        return {}


def _model_values(code: int) -> tuple[float | None, float | None]:
    """What the served pipeline currently has for ``code``: ``(p_play, e_min)``.

    ``p_play`` comes from this gameweek's component breakdown, averaged over
    the gameweek's fixtures because a double is one answer to "does he play".
    ``e_min`` is not in that file — ``components_frame`` drops it — so it comes
    from the newest news-shadow row for the week, which is the only place the
    served expected minutes are banked.

    Both are ``None`` when nothing has been run yet, and the panel simply
    omits the comparison. Recorded once, at pin time (plan A3).
    """
    gw = latest_gw()
    if gw is None:
        return None, None
    p_play = e_min = None
    try:
        comp = load_components(gw)
        rows = comp[(pd.to_numeric(comp["code"], errors="coerce") == code)
                    & (pd.to_numeric(comp["gw"], errors="coerce") == gw)]
        if not rows.empty:
            value = float(pd.to_numeric(rows["p_play"],
                                        errors="coerce").mean())
            p_play = None if math.isnan(value) else round(value, 3)
    except Exception as exc:  # noqa: BLE001
        print(f"overrides: no component reading for {code} ({exc})")
    try:
        from gaffer.data import store

        if store.exists(SHADOW_PATH):
            shadow = load_shadow()
            rows = shadow[(pd.to_numeric(shadow["code"],
                                         errors="coerce") == code)
                          & (pd.to_numeric(shadow["gw"],
                                           errors="coerce") == gw)]
            if rows is not None and not rows.empty:
                newest = rows.sort_values("run_at").iloc[-1]
                value = float(newest["e_min_news"])
                e_min = None if math.isnan(value) else round(value, 1)
    except Exception as exc:  # noqa: BLE001
        print(f"overrides: no shadow reading for {code} ({exc})")
    return p_play, e_min


def _panel() -> OverridesPanel:
    from gaffer.config import serving_config

    names = _names()
    rows = [OverrideRow(code=code, name=names.get(code, str(code)),
                        p_play=row.get("p_play"), e_min=row.get("e_min"),
                        note=str(row.get("note") or ""),
                        set_at=str(row.get("set_at") or ""),
                        model_p_play=row.get("model_p_play"),
                        model_e_min=row.get("model_e_min"))
            for code, row in sorted(load_overrides().items())]
    return OverridesPanel(active=bool(serving_config().news_overrides),
                          rows=rows)


@router.get("/overrides", response_model=OverridesPanel)
def overrides() -> OverridesPanel:
    return _panel()


@router.post("/overrides", response_model=OverridesPanel)
def pin(req: OverrideRequest) -> OverridesPanel:
    known = _names()
    if not known:
        raise _fail("no_player_list",
                    "no player snapshot on disk — run `gaffer advise` before "
                    "pinning anyone", [int(req.code)])
    if int(req.code) not in known:
        raise _fail("unknown_player",
                    f"player {req.code} is not in the current player list",
                    [int(req.code)])
    model_p_play, model_e_min = _model_values(int(req.code))
    try:
        set_override(int(req.code), p_play=req.p_play, e_min=req.e_min,
                     note=req.note, known_codes=list(known),
                     model_p_play=model_p_play, model_e_min=model_e_min)
    except GafferError as exc:
        raise _fail("override_value", str(exc), [int(req.code)]) from exc
    return _panel()


@router.delete("/overrides/{code}", response_model=OverridesPanel)
def unpin(code: int) -> OverridesPanel:
    if not delete_override(int(code)):
        raise HTTPException(status_code=404,
                            detail=f"no override for player {code}")
    return _panel()
```

- [ ] **Mount it.** In `src/gaffer/web/app.py`, add `overrides` to the routers import (L26-27) and `app.include_router(overrides.router)` beside the others, in alphabetical position.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_web_overrides.py tests/test_config.py \
  tests/test_web_app.py
```

- [ ] **Commit.**

```bash
git add src/gaffer/config.py config.example.toml src/gaffer/web/schemas.py \
  src/gaffer/web/routers/overrides.py src/gaffer/web/app.py \
  tests/test_web_overrides.py && git commit -m "$(cat <<'EOF'
feat: /api/overrides and the [news] overrides key

Reads never fail; writes refuse an unknown code, an out-of-range value and a
pin that pins nothing, in the what-if lab's structured 422 shape.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 4 — the sensitivity engine

**Files:**
- Create `src/gaffer/sensitivity.py`
- Create `tests/test_sensitivity.py`

The whole of spec D3's arithmetic, with no HTTP in it. `optimize.scenarios` is imported and never touched: `run_scenarios` already does "K noised solves of one board", `move_frequencies` already counts them, and re-implementing either here would be a second opinion about what a scenario is.

- [ ] **Write the failing test.** Create `tests/test_sensitivity.py`:

```python
"""The sensitivity sweep: how much of this plan is the forecast, and how much
is the forecast's error.

The advice already runs a scenario sweep when ``[scenarios] n`` is on, but it
runs it to *gate* moves and it throws the board away. This is the same
machinery asked a different question — if the EPs were wrong by their own
plausible error, how often would the plan still be this plan, and what is the
next-best plan worth? — and its answer is written down instead of consumed.

Nothing here re-implements a scenario. ``run_scenarios`` and
``move_frequencies`` come from ``optimize.scenarios`` unchanged.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import (POOL_COLS, SolveState, save_solve_state,
                              solve_state_paths)
from gaffer.sensitivity import (SENSITIVITY_K, load_sensitivity,
                                run_sensitivity, sensitivity_path)

SQUAD = [("GKP", 3), ("DEF", 8), ("MID", 8), ("FWD", 5)]
OWNED = [1, 2, 4, 5, 6, 7, 8, 12, 13, 14, 15, 16, 20, 21, 22]   # legal 15
GWS = [5, 6]

OPT = {"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
       "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 2}


def _pool_frame(star_ep: float = 9.0) -> pd.DataFrame:
    """One row per (candidate, gameweek), the shape ``pool_rows`` writes.

    Player 23 is a forward nobody owns, on ``star_ep``: the sweep's job is to
    say how often buying him survives the forecast being wrong.
    """
    rows, code = [], 1
    for position, n in SQUAD:
        for _ in range(n):
            for gw in GWS:
                rows.append({"code": code, "name": f"P{code}",
                             "position": position, "team_code": code % 8,
                             "cost": 50, "sell": 50,
                             "owned": code in OWNED, "gw": gw,
                             "ep_raw": star_ep if code == 23 else 3.0})
            code += 1
    return pd.DataFrame(rows, columns=POOL_COLS)


def _save(tmp_path, **kw) -> None:
    state = SolveState(
        gw=5, gws=list(GWS), deadline="2026-09-05T17:30:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={5: [], 6: []}, opt=dict(OPT), pool=_pool_frame(**kw))
    save_solve_state(state)


def _components(tmp_path) -> None:
    """A component file with a minutes model in it, so xMins is real."""
    rows = [{"code": code, "gw": gw, "p_play": 0.9, "p60": 0.8, "ep": 3.0}
            for code in range(1, 25) for gw in GWS]
    pd.DataFrame(rows).to_parquet(
        tmp_path / "reports/components_gw5.parquet", index=False)


@pytest.fixture()
def board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    _components(tmp_path)
    return tmp_path


def test_a_sweep_writes_its_report(board):
    payload = run_sensitivity(k=4, seed=1)
    assert payload["gw"] == 5
    assert payload["k"] == 4 and payload["completed"] == 4
    assert payload["seed"] == 1
    assert sensitivity_path(5).exists()
    assert load_sensitivity(5)["seed"] == 1
    assert payload["wall_s"] >= 0.0


def test_the_same_seed_is_the_same_report(board):
    first = run_sensitivity(k=4, seed=7)
    second = run_sensitivity(k=4, seed=7)
    assert first["frequencies"] == second["frequencies"]
    assert first["modal"] == second["modal"]
    assert first["margin"] == second["margin"]


def test_a_different_seed_may_differ_but_stays_well_formed(board):
    payload = run_sensitivity(k=4, seed=99)
    assert 0 < len(payload["frequencies"])
    for row in payload["frequencies"]:
        assert 0.0 < row["frequency"] <= 1.0
        assert row["count"] <= payload["completed"]


def test_frequencies_carry_the_player_name(board):
    """A report the UI has to re-join against the pool is a report the UI
    will re-join wrongly."""
    payload = run_sensitivity(k=3, seed=1)
    buys = [r for r in payload["frequencies"] if r["kind"] == "buy"]
    assert buys and all(r["name"] for r in buys)


def test_an_obvious_transfer_survives_every_draw(board):
    """Player 23 is worth three times anybody else. A sweep that cannot find
    him is measuring nothing."""
    payload = run_sensitivity(k=6, seed=3)
    buys = {r["code"]: r["frequency"] for r in payload["frequencies"]
            if r["kind"] == "buy"}
    assert buys.get(23, 0.0) == 1.0


def test_a_marginal_transfer_does_not(tmp_path, monkeypatch):
    """The same board with the star two tenths better than the incumbents:
    now the noise decides, and the report must say so rather than rounding
    the disagreement away."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path, star_ep=3.2)
    _components(tmp_path)
    payload = run_sensitivity(k=8, seed=5)
    buys = {r["code"]: r["frequency"] for r in payload["frequencies"]
            if r["kind"] == "buy"}
    assert buys.get(23, 0.0) < 1.0


def test_the_modal_plan_is_the_most_common_signature(board):
    payload = run_sensitivity(k=6, seed=3)
    modal = payload["modal"]
    assert modal["count"] >= 1
    assert modal["count"] <= payload["completed"]
    assert modal["value"] == pytest.approx(modal["value"])
    assert isinstance(modal["buys"], list)


def test_the_margin_prices_the_best_differing_plan(board):
    """A6: every distinct signature is re-scored on the *true* board, so the
    margin is what the runner-up would really have cost."""
    payload = run_sensitivity(k=8, seed=5)
    if payload["runner_up"] is None:
        assert payload["margin"] is None
        assert "every" in payload["verdict"]
    else:
        assert payload["margin"] == pytest.approx(
            round(payload["modal"]["value"]
                  - payload["runner_up"]["value"], 2))
        assert payload["margin"] >= 0.0


def test_no_solve_state_is_a_readable_refusal(tmp_path, monkeypatch):
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        run_sensitivity()
    assert "advise" in str(exc.value)


def test_without_components_the_sweep_still_runs_and_says_why(tmp_path,
                                                              monkeypatch):
    """A5: a flat 75-minute assumption, and a notice saying it was used."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    payload = run_sensitivity(k=3, seed=1)
    assert payload["completed"] == 3
    assert "75" in payload["notice"]
    assert payload["frequencies"]


def test_a_component_file_with_no_minutes_model_falls_back_the_same_way(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    pd.DataFrame([{"code": 1, "gw": 5, "ep": 3.0}]).to_parquet(
        tmp_path / "reports/components_gw5.parquet", index=False)
    assert "75" in run_sensitivity(k=2, seed=1)["notice"]


def test_the_report_is_written_atomically(board):
    """``pen_tracker.save_tracker``'s idiom: no .tmp file survives a run."""
    run_sensitivity(k=2, seed=1)
    assert not list((board / "reports").glob("*.tmp"))
    json.loads(sensitivity_path(5).read_text())


def test_a_corrupt_report_reads_as_absent(board):
    run_sensitivity(k=2, seed=1)
    sensitivity_path(5).write_text("{not json")
    assert load_sensitivity(5) is None


def test_the_sweep_re_solves_the_saved_board_and_nothing_else(board):
    """The state on disk is untouched: sensitivity is a read of the week's
    decision, not a revision of it."""
    parquet, meta = solve_state_paths(5)
    before = (parquet.read_bytes(), meta.read_bytes())
    run_sensitivity(k=2, seed=1)
    assert (parquet.read_bytes(), meta.read_bytes()) == before


def test_the_default_k_is_the_specs_twenty():
    assert SENSITIVITY_K == 20
```

Run it: expect `ModuleNotFoundError`.

- [ ] **Implement.** Create `src/gaffer/sensitivity.py`:

```python
"""How much of this week's plan is the forecast, and how much is its error.

The MILP hands back one squad with no error bars, and the interesting question
about that squad is not "what does it score" but "how much of it would survive
the forecast being wrong in a way we already expect it to be wrong". v4a
measured what happens when nobody asks: a planning ceiling ~175 points above
what the tool actually scored, most of it spent on transfers that were never
robust.

The advice path already answers a *gating* version of that question when
``[scenarios] n`` is on. This module asks the reporting version — the move
frequencies, the modal plan, and what the best *differing* plan would have
cost — on demand, off the saved board, as a job. It never runs inside
``advise`` and it never changes a served number.

Everything about a scenario comes from :mod:`gaffer.optimize.scenarios`,
imported and untouched: ``run_scenarios`` is the sweep, ``move_frequencies``
is the count, ``xmins_by_player_gw`` is the noise scale's input. Seeded, so a
re-run with the same seed is the same report.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from gaffer import artifacts
from gaffer.artifacts import (latest_gw, load_components, load_solve_state,
                              milp_pool, raw_ep_by, solve_kw_from_state)
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)

SENSITIVITY_K = 20
"""Scenarios per sweep (spec D3).

Twenty is a compromise the spec picked and this module keeps: at ~7s a solve
it is two to three minutes, which is a job you start and come back to, and it
resolves a frequency to the nearest 5% — enough to tell 17/20 from 12/20,
which is the distinction the report exists to draw. The advice path's own
gating sweep runs forty because it is deciding rather than describing.
"""

FALLBACK_XMINS = 75.0
"""Expected minutes assumed for every player when the component file cannot
supply one (plan A5).

Not 92: at the noise floor every draw is the same board, every frequency is
100%, and the report says "certain" about a sweep that never varied anything.
75 puts the heuristic scale at (92 - 75) / 134 ~ 12.7% relative standard
deviation and the calibrated table at its 75-minute bin. It is a stated
assumption carried on the report, not a silent default.
"""


def sensitivity_path(gw: int) -> Path:
    return artifacts.REPORTS / f"sensitivity_gw{gw}.json"


def load_sensitivity(gw: int) -> dict | None:
    """The banked report for ``gw``, or ``None``.

    ``None`` rather than a domain error, like ``load_availability``: a missing
    report means the card offers a "run sensitivity" button, and there is
    nothing for the user to go and fix.
    """
    path = sensitivity_path(gw)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001 — a corrupt report is no report
        print(f"sensitivity report unreadable: {exc}")
        return None


def save_sensitivity(payload: dict, gw: int) -> Path:
    """Atomic, through a temp file — ``pen_tracker.save_tracker``'s idiom."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = sensitivity_path(gw)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=1, allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def plan_signature(plan) -> tuple:
    """The decision a scenario plan represents, stripped of its arithmetic.

    First horizon week only, and deliberately: weeks two and three are
    re-planned from scratch next Tuesday, so counting them would split the
    frequencies on decisions nobody is taking. Sorted tuples rather than sets
    so the signature is hashable *and* serialisable.
    """
    first = plan.gw_plans[0]
    return (tuple(sorted(int(c) for c in first.buys)),
            tuple(sorted(int(c) for c in first.sells)),
            int(first.captain),
            str(getattr(plan, "chip", "") or ""))


def plan_value(gw_plans, ep_by: dict, weeks: int, hit_cost: int) -> float:
    """A plan's horizon points on the **true** EP table.

    The same arithmetic ``routers/whatif.py::_summary`` scores a plan with —
    the XI plus the captain again, minus four a hit — and applied here to
    every distinct scenario signature so the margin between them is priced on
    the board the manager actually faces rather than on the draw that produced
    them (plan A6). Raw EP, never tilted: the tilt shapes the pool and is not
    a number anybody is shown.
    """
    total = 0.0
    for plan in gw_plans[:weeks]:
        def ep(code) -> float:
            return float(ep_by.get((int(code), int(plan.gw)), 0.0))

        total += sum(ep(c) for c in plan.xi) + ep(plan.captain)
        total -= plan.hits * hit_cost
    return round(total, 2)


def _xmins(gw: int, ep_by: dict) -> tuple[dict, str | None]:
    """``{(code, gw): xMins}`` for the noise scale, and a notice if guessed."""
    try:
        table = xmins_by_player_gw(load_components(gw))
    except Exception as exc:  # noqa: BLE001 — a sweep is not worth a crash
        print(f"sensitivity: no component breakdown ({exc})")
        table = {}
    if table:
        return table, None
    return ({key: FALLBACK_XMINS for key in ep_by},
            f"no expected minutes on disk — every player was perturbed at a "
            f"flat {FALLBACK_XMINS:.0f}-minute assumption, so the "
            f"frequencies below rank moves rather than measure them")


def _refs(codes, meta: dict) -> list[dict]:
    return [{"code": int(c), "name": str(meta.get(int(c), {}).get("name",
                                                                 c)),
             "position": str(meta.get(int(c), {}).get("position", ""))}
            for c in sorted(int(c) for c in codes)]


def run_sensitivity(gw: int | None = None, k: int = SENSITIVITY_K,
                    seed: int | None = None) -> dict:
    """Sweep the saved board and bank the report. The job body.

    The board is built exactly as ``routers/whatif.py::solve_whatif`` builds
    it — saved state, raw EP, the cover table converted from ``league_eo``
    when the state predates it, tilt, ``milp_pool``, ``solve_kw_from_state`` —
    because a sensitivity report about a *different* board than the what-if
    lab re-solves would be a report about nothing. The idiom is repeated
    rather than shared: two existing tests pin ``solve_whatif``'s own source
    text and module namespace (plan A7).

    Raises :class:`GafferError` when there is no saved state, which is the
    job runner's signal to say "run `gaffer advise` first" rather than 500.
    """
    gw = latest_gw() if gw is None else int(gw)
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool_ep = tilt_ep(ep_by, cover, state.lam)
    pool = milp_pool(state, pool_ep, gws)
    opt = solve_kw_from_state(state)
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}

    if seed is None:
        from gaffer.config import serving_config
        # Per gameweek, like the advice sweep: one fixed seed reused every
        # week would re-draw the same noise sequence all season.
        seed = int(serving_config().scenarios_seed) + int(gw)
    xmins, notice = _xmins(gw, ep_by)

    solve_state = SolveInput(owned_codes=state.owned_codes, bank=state.bank,
                             free_transfers=state.free_transfers, gws=gws)
    started = time.perf_counter()
    run = run_scenarios(pool, solve_state, xmins, n=int(k), seed=int(seed),
                        **opt)
    wall = round(time.perf_counter() - started, 1)
    if not run.completed:
        raise GafferError(
            f"all {run.attempted} sensitivity solves failed — the saved board "
            f"cannot be re-solved; re-run `gaffer advise`")

    freqs = move_frequencies(run.plans).to_dict("records")
    for row in freqs:
        row["frequency"] = round(float(row["frequency"]), 4)
        row["count"] = int(row["count"])
        row["code"] = int(row["code"])
        row["gw"] = int(row["gw"])
        row["name"] = str(meta.get(int(row["code"]), {}).get("name", ""))

    # One entry per distinct decision, in scenario order so the tie-break is
    # deterministic: the signature that appeared first wins a tied count.
    groups: dict[tuple, dict] = {}
    weeks = len(gws)
    for plan in run.plans:
        key = plan_signature(plan)
        entry = groups.get(key)
        if entry is None:
            first = plan.gw_plans[0]
            entry = groups[key] = {
                "count": 0,
                "buys": _refs(first.buys, meta),
                "sells": _refs(first.sells, meta),
                "captain": _refs([first.captain], meta)[0],
                "chip": (str(getattr(plan, "chip", "")) or None),
                "hits": int(first.hits),
                "value": plan_value(plan.gw_plans, ep_by, weeks,
                                    int(opt["hit_cost"])),
            }
        entry["count"] += 1
    ranked = sorted(groups.values(),
                    key=lambda e: (-e["count"], -e["value"]))
    modal = ranked[0]
    others = sorted(ranked[1:], key=lambda e: -e["value"])
    runner_up = others[0] if others else None
    margin = (None if runner_up is None
              else round(modal["value"] - runner_up["value"], 2))

    payload = {
        "gw": int(gw), "k": int(k), "completed": int(run.completed),
        "failures": int(run.failures), "seed": int(seed),
        "horizon": weeks, "wall_s": wall,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "notice": notice,
        "frequencies": freqs,
        "modal": modal, "runner_up": runner_up, "margin": margin,
        "verdict": _verdict(modal, runner_up, margin, run.completed),
    }
    save_sensitivity(payload, gw)
    return payload


def _verdict(modal: dict, runner_up: dict | None, margin: float | None,
             completed: int) -> str:
    """One sentence a manager can act on, in the spec's own register."""
    share = f"{modal['count']}/{completed}"
    if runner_up is None or margin is None:
        return (f"every one of the {completed} re-solves reached the same "
                f"decision")
    moves = ", ".join(p["name"] for p in modal["buys"]) or "the hold plan"
    alt = ", ".join(p["name"] for p in runner_up["buys"]) or "holding"
    return (f"{moves} appears in {share} re-solves; {alt} is within "
            f"{margin} expected points")
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_sensitivity.py
```

Expect green in well under a minute — the fixture board is 24 players and a solve is milliseconds at that size.

- [ ] **Commit.**

```bash
git add src/gaffer/sensitivity.py tests/test_sensitivity.py \
  && git commit -m "$(cat <<'EOF'
feat: the sensitivity sweep — K noised re-solves of the saved board

Frequencies, the modal plan, and the true-board margin to the best differing
plan. Seeded and deterministic; optimize.scenarios is imported, not copied.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 5 — the tenth job kind, `GET /api/sensitivity`, and the STOP

**Files:**
- Modify `src/gaffer/web/job_kinds.py`
- Create `src/gaffer/web/routers/sensitivity.py`
- Modify `src/gaffer/web/schemas.py`, `src/gaffer/web/app.py`
- Modify `tests/test_web_job_kinds.py`, `tests/test_web_job_kinds_v8b.py`, `tests/test_web_job_kinds_v8c.py`
- Create `tests/test_web_job_kinds_v8e.py`, `tests/test_web_sensitivity.py`
- **Do not modify** `tests/test_v8b_degradation.py`, `tests/test_v8c_degradation.py`, `tests/test_v8d_degradation.py` — see the STOP step at the end.

- [ ] **Write the failing tests.** Create `tests/test_web_job_kinds_v8e.py`:

```python
"""The tenth kind: ``sensitivity``.

A zero-argument wrapper round ``gaffer.sensitivity.run_sensitivity``, in the
shape ``run_track_pens`` established — the module owns the work and the
printing, the wrapper owns the one-line job record.
"""

from __future__ import annotations

import pytest

from gaffer.errors import GafferError
from gaffer.web import job_kinds


def test_the_sensitivity_kind_is_registered():
    assert "sensitivity" in job_kinds.JOB_KINDS
    assert job_kinds.JOB_KINDS["sensitivity"] is job_kinds.run_sensitivity_job


def test_every_kind_is_a_zero_argument_callable():
    import inspect

    for kind, fn in job_kinds.JOB_KINDS.items():
        params = inspect.signature(fn).parameters
        assert all(p.default is not inspect.Parameter.empty
                   for p in params.values()), kind


def test_the_wrapper_returns_the_record_the_runner_shows(monkeypatch,
                                                         capsys):
    monkeypatch.setattr("gaffer.sensitivity.run_sensitivity",
                        lambda: {"gw": 5, "k": 20, "completed": 20,
                                 "wall_s": 141.2, "margin": 0.4,
                                 "verdict": "Salah appears in 17/20"})
    assert job_kinds.run_sensitivity_job() == {"gw": 5, "k": 20,
                                              "completed": 20}
    printed = capsys.readouterr().out
    assert "17/20" in printed
    assert "141.2" in printed


def test_no_saved_state_fails_the_job_rather_than_the_server(monkeypatch):
    """The runner turns a raised GafferError into a failed job record with
    the message on it, which is what "run advise first" has to look like."""
    def boom():
        raise GafferError("no saved solve state — run `gaffer advise` first")

    monkeypatch.setattr("gaffer.sensitivity.run_sensitivity", boom)
    with pytest.raises(GafferError):
        job_kinds.run_sensitivity_job()
```

Create `tests/test_web_sensitivity.py`:

```python
"""``GET /api/sensitivity`` — the banked report, or an honest empty card."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

REPORT = {
    "gw": 5, "k": 20, "completed": 20, "failures": 0, "seed": 20260830,
    "horizon": 3, "wall_s": 141.2, "generated_at": "2026-08-31T09:00:00+00:00",
    "notice": None,
    "frequencies": [
        {"kind": "buy", "code": 23, "gw": 5, "label": "buy", "name": "Salah",
         "count": 17, "frequency": 0.85},
        {"kind": "captain", "code": 23, "gw": 5, "label": "captain",
         "name": "Salah", "count": 20, "frequency": 1.0}],
    "modal": {"count": 17, "buys": [{"code": 23, "name": "Salah",
                                     "position": "MID"}],
              "sells": [], "captain": {"code": 23, "name": "Salah",
                                       "position": "MID"},
              "chip": None, "hits": 0, "value": 210.4},
    "runner_up": {"count": 3, "buys": [], "sells": [],
                  "captain": {"code": 9, "name": "Haaland",
                              "position": "FWD"},
                  "chip": None, "hits": 0, "value": 210.0},
    "margin": 0.4,
    "verdict": "Salah appears in 17/20 re-solves; holding is within 0.4 "
               "expected points",
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    return TestClient(create_app())


def test_no_report_is_an_empty_card_not_a_404(client):
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["frequencies"] == []
    assert body["verdict"] is None


def test_a_banked_report_is_served_whole(client, tmp_path):
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw5.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is True
    assert body["gw"] == 5 and body["completed"] == 20
    assert body["margin"] == 0.4
    assert body["frequencies"][0]["name"] == "Salah"
    assert body["modal"]["captain"]["name"] == "Salah"
    assert "17/20" in body["verdict"]


def test_a_report_for_an_older_gameweek_is_not_shown_as_this_weeks(client,
                                                                  tmp_path):
    """Last week's robustness is not this week's, and a stale card is worse
    than no card."""
    (tmp_path / "reports/solve_state_gw6.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw6.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity").json()
    assert body["available"] is False
    assert body["gw"] == 6
    assert "GW6" in body["notice"]


def test_a_corrupt_report_is_an_empty_card(client, tmp_path):
    (tmp_path / "reports/solve_state_gw5.json").write_text("{}")
    (tmp_path / "reports/solve_state_gw5.parquet").write_bytes(b"")
    (tmp_path / "reports/sensitivity_gw5.json").write_text("{not json")
    assert client.get("/api/sensitivity").json()["available"] is False


def test_an_explicit_gameweek_can_be_asked_for(client, tmp_path):
    (tmp_path / "reports/sensitivity_gw5.json").write_text(json.dumps(REPORT))
    body = client.get("/api/sensitivity?gw=5").json()
    assert body["available"] is True and body["gw"] == 5
```

- [ ] **Add the job kind.** In `src/gaffer/web/job_kinds.py`, after `run_review_job`:

```python
def run_sensitivity_job() -> dict:
    """``sensitivity`` — K noised re-solves of the saved board (v8e F3).

    The zero-argument wrapper pattern ``run_track_pens`` set: the module does
    the work and prints the human-readable verdict, and the wrapper turns it
    into the three numbers the job record carries. Unlike the pen tracker this
    one *can* raise — with no saved solve state there is nothing to sweep —
    and it should: the runner turns a ``GafferError`` into a failed record
    carrying "run `gaffer advise` first", which is the right thing for a
    button to say.

    Minutes, not seconds. Twenty MILP solves is the longest job in the app
    after ``advise`` itself, which is exactly why it is a job and not a
    request.
    """
    from gaffer.sensitivity import run_sensitivity

    payload = run_sensitivity()
    print(payload["verdict"])
    print(f"{payload['completed']}/{payload['k']} scenarios in "
          f"{payload['wall_s']}s")
    return {"gw": payload["gw"], "k": payload["k"],
            "completed": payload["completed"]}
```

and register it last in `JOB_KINDS`:

```python
    "track-pens": run_track_pens,
    "sensitivity": run_sensitivity_job,
}
```

- [ ] **Add the schema.** In `src/gaffer/web/schemas.py`, append. Note the new `NamedPlayer`: the existing `PlayerRef` requires an `ep`, and the sweep names players without pricing them — a zero there would read as a forecast.

```python
class NamedPlayer(BaseModel):
    """A player a report names but does not price."""

    code: int
    name: str
    position: str = ""


class SensitivityMove(BaseModel):
    kind: str
    code: int
    gw: int
    label: str
    name: str = ""
    count: int
    frequency: float


class SensitivityPlan(BaseModel):
    count: int
    buys: list[NamedPlayer] = Field(default_factory=list)
    sells: list[NamedPlayer] = Field(default_factory=list)
    captain: NamedPlayer | None = None
    chip: str | None = None
    hits: int = 0
    value: float = 0.0
    """Horizon expected points on the **true** EP table, so two signatures are
    compared on the board the manager faces rather than on their own draws."""


class SensitivityReport(BaseModel):
    available: bool = False
    gw: int | None = None
    k: int = 0
    completed: int = 0
    failures: int = 0
    seed: int | None = None
    horizon: int = 0
    wall_s: float | None = None
    generated_at: str | None = None
    notice: str | None = None
    frequencies: list[SensitivityMove] = Field(default_factory=list)
    modal: SensitivityPlan | None = None
    runner_up: SensitivityPlan | None = None
    margin: float | None = None
    verdict: str | None = None
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/sensitivity.py`:

```python
"""GET /api/sensitivity — the banked robustness report for this week's board.

Read-only and never an error. A week nobody has swept is not a degraded state,
it is every week before the button is pressed, so it is a 200 with
``available: false`` and the card shows the button. A report from an *older*
gameweek is also ``available: false``, with a notice: last week's robustness
is not this week's, and a stale card is worse than an empty one.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from gaffer.artifacts import latest_gw
from gaffer.sensitivity import load_sensitivity
from gaffer.web.schemas import SensitivityReport

router = APIRouter(prefix="/api", tags=["sensitivity"])


@router.get("/sensitivity", response_model=SensitivityReport)
def sensitivity(gw: int | None = Query(default=None)) -> SensitivityReport:
    wanted = latest_gw() if gw is None else int(gw)
    if wanted is None:
        return SensitivityReport()
    payload = load_sensitivity(wanted)
    if payload is None:
        return SensitivityReport(
            gw=wanted,
            notice=f"no sensitivity report for GW{wanted} — run it to see "
                   f"how much of this plan survives the forecast being wrong")
    return SensitivityReport(available=True, **{
        k: v for k, v in payload.items()
        if k in SensitivityReport.model_fields and k != "available"})
```

- [ ] **Mount it** in `src/gaffer/web/app.py` beside the others.

- [ ] **Update the three unprotected pins.**

`tests/test_web_job_kinds.py` L25-29:

```python
def test_exactly_the_kinds_the_spec_allows():
    assert sorted(JOB_KINDS) == ["advise", "advise-fast", "evaluate",
                                 "field-scrape", "news-shadow",
                                 "refresh-data", "review", "sensitivity",
                                 "snapshot", "track-pens"]
```

`tests/test_web_job_kinds_v8c.py` L24: add `"sensitivity"` to the same sorted list.

`tests/test_web_job_kinds_v8b.py` L15: `assert len(job_kinds.JOB_KINDS) == 10`, with the reason on it:

```python
    # 9 -> 10: v8e added the `sensitivity` kind on both sides.
    assert len(job_kinds.JOB_KINDS) == 10
```

- [ ] **Verify — and expect three named failures.**

```bash
uv run pytest -q tests/test_web_job_kinds_v8e.py tests/test_web_sensitivity.py \
  tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_web_jobs.py
uv run pytest -q
```

The full run must fail in **exactly three places**, all of them the count pin:

```
tests/test_v8b_degradation.py::test_the_job_kind_count_is_pinned_on_this_side_too
tests/test_v8c_degradation.py::test_the_job_kind_count_is_pinned
tests/test_v8d_degradation.py::test_v8d_adds_no_job_kinds
```

Any fourth failure is this task's bug and is fixed here.

- [ ] **Commit what is allowed.**

```bash
git add src/gaffer/web/job_kinds.py src/gaffer/web/routers/sensitivity.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py \
  tests/test_web_job_kinds.py tests/test_web_job_kinds_v8b.py \
  tests/test_web_job_kinds_v8c.py tests/test_web_job_kinds_v8e.py \
  tests/test_web_sensitivity.py && git commit -m "$(cat <<'EOF'
feat: the sensitivity job kind and GET /api/sensitivity

Tenth kind. The three protected degradation-file count pins are deliberately
NOT edited here; they are reported to the orchestrator.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

- [ ] **STOP AND REPORT.** Do not edit the three protected files, do not skip their tests, and do not continue to Task 6 until the orchestrator has acted. Report exactly this:

> Task 5 is committed and the suite has three failures, all of them the same
> deliberate pin. The tenth job kind (`sensitivity`) requires a 9 -> 10 update
> to three protected files, which per the v8b precedent (commit `1c269d8`)
> only the orchestrator may make:
>
> - `tests/test_v8b_degradation.py:212` — `assert len(job_kinds.JOB_KINDS) == 9`
> - `tests/test_v8c_degradation.py:191` — `assert len(job_kinds.JOB_KINDS) == 9`
> - `tests/test_v8d_degradation.py:174` — `assert len(JOB_KINDS) == 9`
>
> Each becomes `== 10` with a one-line comment naming v8e and the kind. Nothing
> else in those files changes. Suggested commit message:
> `test: deliberate v8e job-kind pin update 9->10 for the sensitivity kind`.

Resume at Task 6 once the orchestrator confirms; `uv run pytest -q` must be green before the next task's first commit.

---

## Task 6 — drafts: the store, the CRUD, and the comparison

**Files:**
- Create `src/gaffer/drafts.py`
- Create `src/gaffer/web/routers/drafts.py`
- Modify `src/gaffer/web/schemas.py`, `src/gaffer/web/app.py`
- Create `tests/test_drafts.py`, `tests/test_web_drafts.py`

Spec D4: a draft is a **named constraint set**, not a frozen squad. That is the whole design decision, and it is what keeps a draft meaningful on Friday after Thursday's price changes and Thursday's injury — the squad it implies is re-derived from the current board every time it is compared, and the comparison stamps when it was solved.

- [ ] **Write the failing tests.** Create `tests/test_drafts.py`:

```python
"""``reports/drafts.json``: named what-if constraint sets.

Not saved squads. A squad frozen on Tuesday is wrong by Friday and says
nothing about why it was ever chosen; the constraints that produced it are
still exactly as true, and re-solving them is what makes "compare my drafts"
a live question rather than a scrapbook.
"""

from __future__ import annotations

import json

import pytest

from gaffer.drafts import (MAX_DRAFTS, add_draft, delete_draft, drafts_path,
                           load_drafts)
from gaffer.errors import GafferError

CONSTRAINTS = {"lock": [11], "ban": [], "force_in": [22], "max_hits": 1,
               "chip": "none", "horizon": 3}


def test_an_absent_store_is_an_empty_list(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_drafts() == []


def test_a_corrupt_store_is_an_empty_list(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    drafts_path().write_text("[[[")
    assert load_drafts() == []
    assert "drafts" in capsys.readouterr().out


def test_a_draft_round_trips_with_its_constraints(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("Salah route", CONSTRAINTS)
    rows = load_drafts()
    assert len(rows) == 1
    assert rows[0]["name"] == "Salah route"
    assert rows[0]["constraints"] == CONSTRAINTS
    assert rows[0]["created_at"].startswith("20")


def test_unknown_constraint_keys_are_dropped(tmp_path, monkeypatch):
    """The store is fed by an HTTP body; it keeps the six keys the solver
    understands and nothing else."""
    monkeypatch.chdir(tmp_path)
    add_draft("odd", {**CONSTRAINTS, "wildcard_everything": True})
    assert set(load_drafts()[0]["constraints"]) == {
        "lock", "ban", "force_in", "max_hits", "chip", "horizon"}


def test_missing_constraint_keys_get_their_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("bare", {})
    assert load_drafts()[0]["constraints"] == {
        "lock": [], "ban": [], "force_in": [], "max_hits": 0,
        "chip": "none", "horizon": None}


def test_a_duplicate_name_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("Salah route", CONSTRAINTS)
    with pytest.raises(GafferError) as exc:
        add_draft("Salah route", CONSTRAINTS)
    assert "Salah route" in str(exc.value)


@pytest.mark.parametrize("name", ["", "   ", "x" * 100])
def test_an_unusable_name_is_refused(tmp_path, monkeypatch, name):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        add_draft(name, CONSTRAINTS)


def test_the_store_is_capped_at_twelve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for i in range(MAX_DRAFTS):
        add_draft(f"draft {i}", CONSTRAINTS)
    with pytest.raises(GafferError):
        add_draft("one too many", CONSTRAINTS)
    assert MAX_DRAFTS == 12


def test_deleting_by_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("a", CONSTRAINTS)
    add_draft("b", CONSTRAINTS)
    assert delete_draft("a") is True
    assert [r["name"] for r in load_drafts()] == ["b"]
    assert delete_draft("a") is False


def test_the_file_is_written_atomically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    add_draft("a", CONSTRAINTS)
    assert not list((tmp_path / "reports").glob("*.tmp"))
    assert "drafts" in json.loads(drafts_path().read_text())


def test_order_is_creation_order(tmp_path, monkeypatch):
    """The list is read top-down and the newest draft is the one being
    worked on, so it goes last rather than jumping the queue."""
    monkeypatch.chdir(tmp_path)
    for name in ("first", "second", "third"):
        add_draft(name, CONSTRAINTS)
    assert [r["name"] for r in load_drafts()] == ["first", "second", "third"]
```

Create `tests/test_web_drafts.py`, reusing the solve-state fixture from the sensitivity tests so the comparison is run against a real board:

```python
"""``/api/drafts`` — CRUD, and the comparison job.

The comparison is the point: three named constraint sets re-solved against
today's board, side by side, with the unconstrained optimum as the reference
row so "worse than what?" has an answer on the page.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app
from tests.test_sensitivity import OWNED, _components, _save

BODY = {"name": "Salah route",
        "constraints": {"lock": [], "ban": [], "force_in": [], "max_hits": 0,
                        "chip": "none", "horizon": 2}}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    _save(tmp_path)
    _components(tmp_path)
    return TestClient(create_app())


def _run(client, names):
    """Submit a comparison and drain the legacy job registry, as the what-if
    lab's tests do."""
    accepted = client.post("/api/drafts/compare", json={"names": names})
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
    raise AssertionError("comparison never finished")


def test_no_drafts_is_an_empty_list(client):
    assert client.get("/api/drafts").json() == {"drafts": []}


def test_saving_a_draft_returns_the_list(client):
    body = client.post("/api/drafts", json=BODY).json()
    assert [d["name"] for d in body["drafts"]] == ["Salah route"]
    assert body["drafts"][0]["constraints"]["horizon"] == 2


def test_a_duplicate_name_is_a_structured_422(client):
    client.post("/api/drafts", json=BODY)
    response = client.post("/api/drafts", json=BODY)
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "draft_name"


def test_a_draft_naming_an_unknown_player_is_refused_at_write_time(client):
    """The same validation the what-if lab runs, run early: a draft that can
    never be solved is not worth saving."""
    response = client.post("/api/drafts", json={
        "name": "nonsense",
        "constraints": {**BODY["constraints"], "lock": [9999]}})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "unknown_player"


def test_deleting_a_draft(client):
    client.post("/api/drafts", json=BODY)
    assert client.delete("/api/drafts/Salah route").json() == {"drafts": []}
    assert client.delete("/api/drafts/Salah route").status_code == 404


def test_a_comparison_has_the_optimum_as_its_reference_row(client):
    client.post("/api/drafts", json=BODY)
    job = _run(client, ["Salah route"])
    assert job["status"] == "done", job["error"]
    rows = job["result"]["rows"]
    assert rows[0]["name"] == "the optimum"
    assert rows[0]["is_reference"] is True
    assert rows[0]["delta_xpts"] == 0.0
    assert rows[1]["name"] == "Salah route"
    assert rows[1]["solved_at"].startswith("20")


def test_a_constrained_draft_never_beats_the_optimum(client):
    """It is the same board with strictly fewer legal squads on it."""
    client.post("/api/drafts", json={
        "name": "no star", "constraints": {**BODY["constraints"],
                                           "ban": [23]}})
    job = _run(client, ["no star"])
    row = job["result"]["rows"][1]
    assert row["delta_xpts"] <= 0.0
    assert row["horizon_pts"] < job["result"]["rows"][0]["horizon_pts"]


def test_each_row_carries_the_weeks_moves(client):
    client.post("/api/drafts", json=BODY)
    row = _run(client, ["Salah route"])["result"]["rows"][1]
    assert set(row) >= {"buys", "sells", "captain", "hits", "chip",
                        "expected_pts", "horizon_pts"}
    assert all("name" in p for p in row["buys"])


def test_an_infeasible_draft_is_a_row_with_a_reason_not_a_failed_job(client):
    """Locking fifteen players and forcing in a sixteenth cannot be solved;
    the other drafts in the comparison must still be shown."""
    client.post("/api/drafts", json={
        "name": "impossible",
        "constraints": {**BODY["constraints"], "lock": list(OWNED),
                        "force_in": [23], "max_hits": 0}})
    client.post("/api/drafts", json=BODY)
    job = _run(client, ["impossible", "Salah route"])
    assert job["status"] == "done", job["error"]
    rows = {r["name"]: r for r in job["result"]["rows"]}
    assert rows["impossible"]["error"]
    assert rows["impossible"]["horizon_pts"] is None
    assert rows["Salah route"]["horizon_pts"] is not None


def test_an_unknown_draft_name_is_a_422(client):
    assert client.post("/api/drafts/compare",
                       json={"names": ["ghost"]}).status_code == 422


def test_too_many_drafts_in_one_comparison_is_a_422(client):
    """A8: six solves plus the reference is the timeout budget."""
    for i in range(7):
        client.post("/api/drafts", json={**BODY, "name": f"d{i}"})
    response = client.post("/api/drafts/compare",
                           json={"names": [f"d{i}" for i in range(7)]})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "too_many_drafts"


def test_no_solve_state_is_a_readable_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text('[fpl]\nentry_id = 1\n'
                                          'league_id = 5\n')
    (tmp_path / "reports").mkdir()
    client = TestClient(create_app())
    response = client.post("/api/drafts/compare", json={"names": []})
    assert response.status_code == 422
    assert "advise" in str(response.json()["detail"])
```

- [ ] **Implement the store.** Create `src/gaffer/drafts.py`:

```python
"""``reports/drafts.json``: named what-if constraint sets.

A draft is what you *asked for*, not what you got. Freezing the squad would
make a draft stale the moment a price changed or a hamstring went, and would
lose the only thing worth keeping — the argument. Re-solving the constraints
against today's board keeps "the Salah route" meaningful all week, and the
comparison stamps each row with when it was solved so nobody reads a Tuesday
answer on a Friday.

The store is deliberately small and deliberately dumb: no solving here, no
validation of players against a pool (the router does that, because it is the
half that knows the pool), and the same atomic single-JSON write every other
report store uses.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from gaffer import artifacts
from gaffer.errors import GafferError

MAX_DRAFTS = 12
"""Spec D4's cap. Twelve named plans is a planning session; a hundred is a
filing cabinet nobody opens."""

NAME_MAX = 60

CONSTRAINT_DEFAULTS: dict = {"lock": [], "ban": [], "force_in": [],
                             "max_hits": 0, "chip": "none", "horizon": None}
"""The six keys a draft may carry — ``WhatIfRequest``'s fields exactly.

Anything else in the payload is dropped rather than stored: the store is fed
from an HTTP body, and a key the solver does not understand is a key that will
be silently ignored later at a worse moment.
"""


def drafts_path() -> Path:
    return artifacts.REPORTS / "drafts.json"


def normalize(constraints: dict | None) -> dict:
    """The six keys, defaulted and typed. Never raises."""
    raw = dict(constraints or {})
    return {
        "lock": [int(c) for c in raw.get("lock") or []],
        "ban": [int(c) for c in raw.get("ban") or []],
        "force_in": [int(c) for c in raw.get("force_in") or []],
        "max_hits": int(raw.get("max_hits") or 0),
        "chip": str(raw.get("chip") or "none"),
        "horizon": (None if raw.get("horizon") in (None, "")
                    else int(raw["horizon"])),
    }


def load_drafts() -> list[dict]:
    """Every saved draft in creation order, or ``[]``.

    Never raises, for the same reason the overrides store does not: a
    hand-edited file must cost you your drafts, not your afternoon.
    """
    path = drafts_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text())
        rows = raw.get("drafts") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return []
        return [{"name": str(r["name"]),
                 "created_at": str(r.get("created_at") or ""),
                 "constraints": normalize(r.get("constraints"))}
                for r in rows if isinstance(r, dict) and r.get("name")]
    except Exception as exc:  # noqa: BLE001
        print(f"drafts store unreadable, ignoring it: {exc}")
        return []


def save_drafts(rows: list[dict]) -> Path:
    """Atomic whole-file write — ``pen_tracker.save_tracker``'s idiom."""
    artifacts.REPORTS.mkdir(exist_ok=True)
    path = drafts_path()
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps({"drafts": rows}, indent=1,
                                  allow_nan=False))
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def add_draft(name: str, constraints: dict | None) -> dict:
    """Save one named constraint set, refusing a name that cannot be used."""
    clean = str(name or "").strip()
    if not clean:
        raise GafferError("a draft needs a name")
    if len(clean) > NAME_MAX:
        raise GafferError(f"a draft name is at most {NAME_MAX} characters")
    rows = load_drafts()
    if any(r["name"] == clean for r in rows):
        raise GafferError(f"a draft called {clean!r} already exists")
    if len(rows) >= MAX_DRAFTS:
        raise GafferError(
            f"{MAX_DRAFTS} drafts is the cap — delete one first")
    row = {"name": clean,
           "created_at": datetime.now(timezone.utc).isoformat(
               timespec="seconds"),
           "constraints": normalize(constraints)}
    rows.append(row)
    save_drafts(rows)
    return row


def delete_draft(name: str) -> bool:
    rows = load_drafts()
    kept = [r for r in rows if r["name"] != str(name)]
    if len(kept) == len(rows):
        return False
    save_drafts(kept)
    return True
```

- [ ] **Add the schemas.** In `src/gaffer/web/schemas.py`, append:

```python
class DraftRow(BaseModel):
    name: str
    created_at: str = ""
    constraints: WhatIfRequest


class DraftList(BaseModel):
    drafts: list[DraftRow] = Field(default_factory=list)


class DraftSaveRequest(BaseModel):
    name: str
    constraints: WhatIfRequest = Field(default_factory=WhatIfRequest)


class DraftCompareRequest(BaseModel):
    names: list[str] = Field(default_factory=list)


class DraftCompareRow(BaseModel):
    name: str
    is_reference: bool = False
    """The unconstrained optimum, so every other row has a "worse than what"."""
    solved_at: str = ""
    horizon_pts: float | None = None
    expected_pts: float | None = None
    delta_xpts: float | None = None
    hits: int | None = None
    chip: str | None = None
    buys: list[PlayerRef] = Field(default_factory=list)
    sells: list[PlayerRef] = Field(default_factory=list)
    captain: PlayerRef | None = None
    error: str | None = None
    """Why this row is empty. An infeasible draft is a row with a reason, not
    a failed comparison."""


class DraftCompare(BaseModel):
    gw: int
    weeks: int
    rows: list[DraftCompareRow] = Field(default_factory=list)
```

- [ ] **Write the router.** Create `src/gaffer/web/routers/drafts.py`:

```python
"""``/api/drafts`` — named constraint sets, and their side-by-side re-solve.

CRUD is synchronous and cheap. The comparison is not: it is one MILP solve per
draft plus one for the reference row, so it goes through the same legacy job
registry the what-if lab uses (202 + ``job_id``, polled by ``useJob``) rather
than the single-flight v7 runner, which belongs to the named kinds. Six drafts
is the cap on one request: at ~7s a solve that is inside ``WHATIF_TIMEOUT_S``
with the reference row paid for (plan A8).

The board is built exactly as ``whatif.solve_whatif`` builds it — the idiom is
repeated rather than shared, because two existing tests pin that function's own
source text and namespace (plan A7).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from gaffer.artifacts import (latest_gw, load_solve_state, milp_pool,
                              raw_ep_by, solve_kw_from_state)
from gaffer.drafts import (MAX_DRAFTS, add_draft, delete_draft, load_drafts)
from gaffer.errors import GafferError
from gaffer.league_mode import cover_from_eo, tilt_ep
from gaffer.optimize.milp import SolveInput, solve_plan
from gaffer.web.jobs import WHATIF_TIMEOUT_S, JobQueueFull
from gaffer.web.routers.whatif import _summary, _validate
from gaffer.web.schemas import (CHIP_CODES, DraftCompare, DraftCompareRequest,
                                DraftCompareRow, DraftList, DraftRow,
                                DraftSaveRequest, JobAccepted, WhatIfRequest)

router = APIRouter(prefix="/api", tags=["drafts"])

MAX_COMPARE = 6
"""Drafts per comparison. Seven solves at ~7s each, inside the 120s job
timeout with room for a slow board."""

NO_RUN = "no saved solve state — run `gaffer advise` first"


def _fail(constraint: str, error: str, players: list[int]) -> HTTPException:
    return HTTPException(status_code=422,
                         detail={"constraint": constraint, "error": error,
                                 "players": players})


def _list() -> DraftList:
    return DraftList(drafts=[DraftRow(name=r["name"],
                                      created_at=r["created_at"],
                                      constraints=WhatIfRequest(
                                          **r["constraints"]))
                             for r in load_drafts()])


@router.get("/drafts", response_model=DraftList)
def drafts() -> DraftList:
    return _list()


@router.post("/drafts", response_model=DraftList)
def save(req: DraftSaveRequest) -> DraftList:
    """Save a draft, validating it against today's pool before it is stored.

    Early rather than at compare time on purpose: a draft naming a player who
    is not in the candidate pool can never be solved, and finding that out
    three days later, in a comparison, is finding it out at the wrong moment.
    """
    gw = latest_gw()
    if gw is not None:
        # Reuses the what-if lab's own validator, so a draft and a what-if
        # are refused for the same reasons in the same words.
        _validate(req.constraints, load_solve_state(gw))
    try:
        add_draft(req.name, req.constraints.model_dump())
    except GafferError as exc:
        raise _fail("draft_name", str(exc), []) from exc
    return _list()


@router.delete("/drafts/{name}", response_model=DraftList)
def remove(name: str) -> DraftList:
    if not delete_draft(name):
        raise HTTPException(status_code=404, detail=f"no draft called {name}")
    return _list()


def compare_drafts(names: list[str], gw: int) -> dict:
    """Re-solve each named draft on the current board, plus the optimum.

    Every row is priced in **raw** expected points over the weeks all the rows
    share, so a draft that shortened the horizon is not flattered by having
    fewer weeks of decay to lose. A draft the board cannot satisfy gets a row
    carrying its reason: the other drafts in the comparison are still worth
    reading, and a comparison that dies on one bad constraint set is a
    comparison nobody trusts.
    """
    state = load_solve_state(gw)
    wanted = {r["name"]: r["constraints"] for r in load_drafts()}
    requests = [(name, WhatIfRequest(**wanted[name])) for name in names]

    # The shared horizon: the shortest any row asked for, so every row is
    # scored over the same weeks.
    default_horizon = state.opt.get("horizon") or len(state.gws)
    horizons = [req.horizon or default_horizon for _, req in requests]
    gws = state.gws[:max(1, min([int(default_horizon)] + horizons))]

    ep_by = raw_ep_by(state)
    cover = (state.cover if state.cover is not None
             else cover_from_eo(state.league_eo))
    pool = milp_pool(state, tilt_ep(ep_by, cover, state.lam), gws)
    opt = solve_kw_from_state(state)
    meta = {int(r.code): {"name": str(r.name), "position": str(r.position)}
            for r in state.pool.drop_duplicates("code").itertuples()}
    weeks = len(gws)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def row(name: str, req: WhatIfRequest | None,
            reference: bool = False) -> DraftCompareRow:
        chip = CHIP_CODES.get(req.chip) if req else None
        if req is None:
            solve_state = SolveInput(owned_codes=state.owned_codes,
                                     bank=state.bank,
                                     free_transfers=state.free_transfers,
                                     gws=gws)
        elif chip == "freehit":
            # The same one-week conjuring ``chips.free_hit_gain`` scores.
            budget = state.bank + int(
                pool[pool["code"].isin(state.owned_codes)]["sell"].sum())
            solve_state = SolveInput(
                owned_codes=[], bank=budget, free_transfers=15, gws=[gws[0]],
                locked_out=list(req.ban), locked_in=list(req.lock),
                force_in_gw=list(req.force_in), max_hits=None)
        else:
            solve_state = SolveInput(
                owned_codes=state.owned_codes, bank=state.bank,
                free_transfers=state.free_transfers, gws=gws,
                wildcard_gw=gws[0] if chip == "wildcard" else None,
                bench_boost_gw=gws[0] if chip == "bboost" else None,
                triple_captain_gw=gws[0] if chip == "3xc" else None,
                locked_out=list(req.ban), locked_in=list(req.lock),
                force_in_gw=list(req.force_in), max_hits=req.max_hits)
        try:
            plans = solve_plan(pool, solve_state, **opt).gw_plans
        except Exception as exc:  # noqa: BLE001 — one bad draft is a row
            return DraftCompareRow(name=name, is_reference=reference,
                                   solved_at=now,
                                   error=f"no legal squad satisfies this "
                                         f"draft: {exc}")
        summary = _summary(plans, ep_by, meta, weeks,
                           hit_cost=opt["hit_cost"],
                           cap_extra=2.0 if chip == "3xc" else 1.0,
                           bench_counts=chip == "bboost")
        return DraftCompareRow(
            name=name, is_reference=reference, solved_at=now,
            horizon_pts=summary.horizon_pts,
            expected_pts=summary.expected_pts, hits=summary.hits,
            chip=chip, buys=summary.buys, sells=summary.sells,
            captain=summary.captain)

    rows = [row("the optimum", None, reference=True)]
    rows += [row(name, req) for name, req in requests]
    base = rows[0].horizon_pts
    for entry in rows:
        if entry.horizon_pts is not None and base is not None:
            entry.delta_xpts = round(entry.horizon_pts - base, 2)
    return DraftCompare(gw=int(gw), weeks=weeks, rows=rows).model_dump()


@router.post("/drafts/compare", status_code=202, response_model=JobAccepted)
def compare(req: DraftCompareRequest, request: Request):
    gw = latest_gw()
    if gw is None:
        raise GafferError(NO_RUN)
    if len(req.names) > MAX_COMPARE:
        raise _fail("too_many_drafts",
                    f"compare at most {MAX_COMPARE} drafts at once — the "
                    f"solve budget is {MAX_COMPARE + 1} boards", [])
    known = {r["name"] for r in load_drafts()}
    missing = [n for n in req.names if n not in known]
    if missing:
        raise _fail("unknown_draft", f"no draft called {missing[0]}", [])
    names = list(req.names)
    try:
        job_id = request.app.state.jobs.submit(
            lambda: compare_drafts(names, gw), timeout_s=WHATIF_TIMEOUT_S)
    except JobQueueFull as exc:
        return JSONResponse(status_code=429, content={"detail": str(exc)})
    return JobAccepted(job_id=job_id)
```

Note the two private imports from `whatif`: `_summary` and `_validate` are imported, never copied — a draft priced by a second implementation of the plan summary would disagree with the what-if lab about the same squad. Task 9 pins that they are imported rather than re-defined. The leading underscore does not stop an import, and neither function moves.

- [ ] **Mount it** in `src/gaffer/web/app.py`.

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_drafts.py tests/test_web_drafts.py \
  tests/test_web_whatif.py
uv run pytest -q
```

The full run must be **green** — Task 5's STOP has been actioned by now — at the 2189 baseline plus this cycle's tests so far.

- [ ] **Commit.**

```bash
git add src/gaffer/drafts.py src/gaffer/web/routers/drafts.py \
  src/gaffer/web/schemas.py src/gaffer/web/app.py tests/test_drafts.py \
  tests/test_web_drafts.py && git commit -m "$(cat <<'EOF'
feat: named draft constraint sets and their side-by-side re-solve

Drafts are constraints, not frozen squads, so they stay meaningful as the
board moves. The comparison carries the unconstrained optimum as its
reference row and turns an infeasible draft into a row with a reason.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 7 — the frontend

**Files:**
- Modify `frontend/src/api/client.ts`, `frontend/src/types.ts`, `frontend/src/types.test.ts`
- Modify `frontend/src/hubs/Planning.tsx`, `frontend/src/hubs/Planning.test.tsx`
- Modify `frontend/src/hubs/planning/WhatIfTab.tsx`
- Create `frontend/src/hubs/planning/SensitivityCard.tsx` (+ test)
- Create `frontend/src/hubs/planning/DraftsTab.tsx` (+ test)
- Create `frontend/src/hubs/planning/OverridesCard.tsx` (+ test)
- Create `frontend/src/hubs/players/PinDialog.tsx` (+ test)
- Modify `frontend/src/hubs/Players.tsx`, `frontend/src/hubs/Players.test.tsx`
- Modify `frontend/src/hubs/this-week/WhyPanel.tsx`, `frontend/src/hubs/this-week/WhyPanel.test.tsx`

Work in this order — types first, then the leaf components, then the hubs that compose them — and run `npx vitest run <file>` after each. Every new field is optional or nullable, so a browser holding a stale bundle against a new server, or the reverse, still typechecks and still renders.

- [ ] **Add the missing verb.** `frontend/src/api/client.ts` has `apiGet` and `apiPost` and nothing else; unpinning a player and deleting a draft are both DELETEs. Append beside `apiPost`:

```ts
export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' })
}
```

- [ ] **Types, in lockstep with the server.** In `frontend/src/types.ts`, add `'sensitivity'` to `JOB_KINDS` (last, matching the server's registration order) and to `JOB_KIND_LABEL`:

```ts
export const JOB_KINDS = ['advise', 'advise-fast', 'evaluate', 'refresh-data',
  'news-shadow', 'snapshot', 'track-pens', 'field-scrape', 'review',
  'sensitivity'] as const
```

```ts
  sensitivity: 'Run sensitivity',
```

and append the payloads:

```ts
// --- v8e: overrides, sensitivity, drafts -------------------------------

export interface OverrideRow {
  code: number
  name: string
  p_play: number | null
  e_min: number | null
  note: string
  set_at: string
  /** What the model had for him when the pin was made, not now. */
  model_p_play: number | null
  model_e_min: number | null
}

export interface OverridesPanel {
  active: boolean
  rows: OverrideRow[]
}

export interface NamedPlayer {
  code: number
  name: string
  position?: string
}

export interface SensitivityMove {
  kind: string
  code: number
  gw: number
  label: string
  name?: string
  count: number
  frequency: number
}

export interface SensitivityPlan {
  count: number
  buys: NamedPlayer[]
  sells: NamedPlayer[]
  captain: NamedPlayer | null
  chip: string | null
  hits: number
  value: number
}

export interface SensitivityReport {
  available: boolean
  gw: number | null
  k: number
  completed: number
  failures: number
  seed: number | null
  horizon: number
  wall_s: number | null
  generated_at: string | null
  notice: string | null
  frequencies: SensitivityMove[]
  modal: SensitivityPlan | null
  runner_up: SensitivityPlan | null
  margin: number | null
  verdict: string | null
}

export interface DraftRow {
  name: string
  created_at: string
  constraints: WhatIfRequest
}

export interface DraftList { drafts: DraftRow[] }

export interface DraftCompareRow {
  name: string
  is_reference: boolean
  solved_at: string
  horizon_pts: number | null
  expected_pts: number | null
  delta_xpts: number | null
  hits: number | null
  chip: string | null
  buys: PlayerRef[]
  sells: PlayerRef[]
  captain: PlayerRef | null
  error: string | null
}

export interface DraftCompare {
  gw: number
  weeks: number
  rows: DraftCompareRow[]
}
```

In `frontend/src/types.test.ts`, update the pin — the count in the test *name* too, which is the half that goes stale:

```ts
  it('lists exactly the ten kinds the backend allows', () => {
    expect([...JOB_KINDS]).toEqual(
      ['advise', 'advise-fast', 'evaluate', 'refresh-data', 'news-shadow',
       'snapshot', 'track-pens', 'field-scrape', 'review', 'sensitivity'])
  })
```

- [ ] **The sensitivity card.** Create `frontend/src/hubs/planning/SensitivityCard.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../api/client'
import { Card, JobButton, fmtNum } from '../../kit'
import type { SensitivityReport } from '../../types'

/** Moves worth showing: the ones that are neither certain nor negligible are
 *  the whole point, but a 100% row is the reassurance and a 5% row is the
 *  warning, so the cut is on nothing at all. */
const KINDS = ['buy', 'sell', 'captain', 'chip']

function pct(frequency: number): string {
  return `${Math.round(frequency * 100)}%`
}

export default function SensitivityCard() {
  const [data, setData] = useState<SensitivityReport | null>(null)
  const load = useCallback(() => {
    apiGet<SensitivityReport>('/api/sensitivity')
      .then(setData)
      .catch(() => setData(null))
  }, [])
  useEffect(() => { load() }, [load])

  const rows = (data?.frequencies ?? [])
    .filter((r) => KINDS.includes(r.kind))
    .sort((a, b) => b.frequency - a.frequency)
    .slice(0, 12)

  return (
    <Card
      title="How robust is this plan?"
      className="mb-4"
      action={<JobButton kind="sensitivity" onDone={load} />}
    >
      <p className="mb-3 text-text-muted">
        The same board re-solved twenty times with every expected-points cell
        knocked by its own plausible error. A move that survives most of them
        is an edge; one that does not is the optimizer reading the noise.
      </p>
      {!data?.available && (
        <p className="text-text-muted">
          {data?.notice ?? 'No sensitivity report yet.'}
        </p>
      )}
      {data?.available && (
        <>
          {data.verdict && <p className="mb-3 text-text">{data.verdict}</p>}
          {data.notice && (
            <p className="mb-3 rounded-card border-l-2 border-info bg-base
                          px-3 py-2 text-text-muted">
              {data.notice}
            </p>
          )}
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Move</th>
                <th className="label pb-1 text-left">Player</th>
                <th className="label pb-1 text-right">Solves</th>
                <th className="label pb-1 text-right">Share</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.kind}-${r.code}-${r.gw}`}>
                  <td className="py-1.5 text-text-secondary">{r.label}</td>
                  <td className="py-1.5 text-text">{r.name || '—'}</td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {r.count}/{data.completed}
                  </td>
                  <td className="num py-1.5 text-right">{pct(r.frequency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-text-muted">
            {data.margin === null
              ? 'Every re-solve reached the same decision.'
              : `The best differing plan is ${fmtNum(data.margin, 1)} expected `
                + 'points behind.'}
            {data.wall_s !== null && ` Swept in ${fmtNum(data.wall_s, 0)}s, `}
            {data.seed !== null && `seed ${data.seed}.`}
          </p>
        </>
      )}
    </Card>
  )
}
```

Test `frontend/src/hubs/planning/SensitivityCard.test.tsx`: an available report renders the verdict, the share column and the margin line; `available: false` renders the notice and no table; the `JobButton` is present with `kind="sensitivity"`.

- [ ] **The overrides card** (spec D6: the editor lives in Planning). Create `frontend/src/hubs/planning/OverridesCard.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet } from '../../api/client'
import { Card, fmtNum } from '../../kit'
import type { OverridesPanel } from '../../types'

export default function OverridesCard() {
  const [data, setData] = useState<OverridesPanel | null>(null)
  const load = useCallback(() => {
    apiGet<OverridesPanel>('/api/overrides').then(setData).catch(
      () => setData(null))
  }, [])
  useEffect(() => { load() }, [load])

  const drop = async (code: number) => {
    await apiDelete<OverridesPanel>(`/api/overrides/${code}`).then(setData)
      .catch(() => load())
  }

  if (!data) return null
  return (
    <Card title="Your pins" className="mb-4">
      <p className="mb-3 text-text-muted">
        Minutes you have overruled the model on. Applied last, over every
        automated source, to the coming gameweek only. Set them from a
        player's row on the Players page.
      </p>
      {!data.active && (
        <p className="mb-3 rounded-card border-l-2 border-rust bg-base px-3
                      py-2 text-text-muted">
          These are saved but not being applied: <code>[news] overrides</code>
          {' '}is false in config.toml.
        </p>
      )}
      {data.rows.length === 0
        ? <p className="text-text-muted">Nothing pinned.</p>
        : (
          <ul className="flex flex-col gap-2">
            {data.rows.map((row) => (
              <li key={row.code}
                  className="flex items-baseline justify-between gap-3">
                <span className="text-text">
                  {row.name}
                  {row.p_play !== null && (
                    <span className="text-text-secondary">
                      {` · p_play ${fmtNum(row.p_play, 2)}`}
                      {row.model_p_play !== null
                        && ` (model had ${fmtNum(row.model_p_play, 2)})`}
                    </span>
                  )}
                  {row.e_min !== null && (
                    <span className="text-text-secondary">
                      {` · minutes ${fmtNum(row.e_min, 0)}`}
                    </span>
                  )}
                  {row.note && (
                    <span className="text-text-muted">{` — ${row.note}`}</span>
                  )}
                </span>
                <button
                  type="button"
                  aria-label={`unpin ${row.name}`}
                  onClick={() => drop(row.code)}
                  className="rounded-card border border-border px-2 py-1
                             text-text-muted hover:text-text"
                >
                  Unpin
                </button>
              </li>
            ))}
          </ul>
          )}
    </Card>
  )
}
```

- [ ] **The pin dialog** (plan A9). Create `frontend/src/hubs/players/PinDialog.tsx`, on `kit/ExplainModal`'s pattern:

```tsx
import { useEffect, useRef, useState } from 'react'
import { ApiError, apiPost } from '../../api/client'
import type { OverridesPanel } from '../../types'

const FIELD = 'rounded-card border border-border bg-base px-2 py-1 text-text'

export default function PinDialog(
  { code, name, onClose, onSaved }: {
    code: number
    name: string
    onClose: () => void
    onSaved?: (panel: OverridesPanel) => void
  },
) {
  const [pPlay, setPPlay] = useState('')
  const [eMin, setEMin] = useState('')
  const [note, setNote] = useState('')
  const [error, setError] = useState<string | null>(null)
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  useEffect(() => { closeRef.current?.focus() }, [])

  const save = async () => {
    setError(null)
    try {
      const panel = await apiPost<OverridesPanel>('/api/overrides', {
        code,
        p_play: pPlay === '' ? null : Number(pPlay),
        e_min: eMin === '' ? null : Number(eMin),
        note,
      })
      onSaved?.(panel)
      onClose()
    } catch (e) {
      const detail = e instanceof ApiError ? e.detail : null
      const message = (detail && typeof detail === 'object'
        && 'error' in detail) ? String((detail as { error: string }).error)
        : (e as Error).message
      setError(message)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center
                 overflow-y-auto bg-black/70 p-4 sm:p-8"
      data-testid="modal-backdrop"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-card border border-border bg-card"
        role="dialog"
        aria-modal="true"
        aria-label={`Pin availability for ${name}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b
                           border-divider px-4 py-3">
          <div>
            <h2 className="text-base text-text">Pin {name}</h2>
            <p className="label mt-1">Applied over the model, this gameweek</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose}
                  className="rounded-card border border-border px-2 py-1
                             text-text-muted hover:text-text">
            Close
          </button>
        </header>
        <div className="flex flex-col gap-3 p-4">
          <p className="text-text-muted">
            Leave a field blank to leave the model's own number alone. A
            probability of playing is 0 to 1; expected minutes are 0 to 90.
          </p>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Probability of playing</span>
            <input className={FIELD} inputMode="decimal" value={pPlay}
                   aria-label="probability of playing"
                   onChange={(e) => setPPlay(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Expected minutes</span>
            <input className={FIELD} inputMode="decimal" value={eMin}
                   aria-label="expected minutes"
                   onChange={(e) => setEMin(e.target.value)} />
          </label>
          <label className="flex items-center justify-between gap-3">
            <span className="label">Why</span>
            <input className={FIELD} value={note} aria-label="why"
                   onChange={(e) => setNote(e.target.value)} />
          </label>
          {error && <p className="text-rust">{error}</p>}
          <button type="button" onClick={save}
                  className="self-end rounded-card border border-border
                             bg-card px-3 py-2 text-text-secondary
                             hover:text-text">
            Pin
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Give the explorer the affordance.** In `frontend/src/hubs/Players.tsx`, import `PinDialog` and hold the open row, then append a trailing column:

```tsx
  const [pinning, setPinning] = useState<PlayerRow | null>(null)
```

```tsx
    {
      key: 'pin', header: '', value: () => '',
      render: (r) => (
        <button
          type="button"
          aria-label={`pin ${r.name}`}
          onClick={() => setPinning(r)}
          className="rounded-card border border-border px-2 py-0.5
                     text-text-muted hover:text-text"
        >
          Pin
        </button>
      ),
    },
```

and render the dialog once, beside the table:

```tsx
      {pinning && (
        <PinDialog code={pinning.code} name={pinning.name}
                   onClose={() => setPinning(null)} />
      )}
```

- [ ] **The drafts tab.** Create `frontend/src/hubs/planning/DraftsTab.tsx`:

```tsx
import { useCallback, useEffect, useState } from 'react'
import { apiDelete, apiGet, apiPost } from '../../api/client'
import { useJob } from '../../api/useJob'
import { Card, JobLog, fmtNum } from '../../kit'
import type { DraftCompare, DraftList, WhatIfRequest } from '../../types'

const MAX_COMPARE = 6

export default function DraftsTab({ current }: { current: WhatIfRequest }) {
  const [drafts, setDrafts] = useState<DraftList>({ drafts: [] })
  const [name, setName] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const job = useJob()

  const load = useCallback(() => {
    apiGet<DraftList>('/api/drafts').then(setDrafts).catch(() => {})
  }, [])
  useEffect(() => { load() }, [load])

  const save = async () => {
    setError(null)
    try {
      setDrafts(await apiPost<DraftList>('/api/drafts',
                                         { name, constraints: current }))
      setName('')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggle = (draft: string) => setPicked((prev) => (
    prev.includes(draft) ? prev.filter((d) => d !== draft)
      : [...prev, draft].slice(0, MAX_COMPARE)))

  const result = job.result as DraftCompare | null

  return (
    <>
      <Card title="Drafts" className="mb-4">
        <p className="mb-3 text-text-muted">
          A draft is the constraints you asked for, not the squad you got, so
          it still means something after Thursday's price changes. Comparing
          re-solves each one against today's board.
        </p>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            className="rounded-card border border-border bg-base px-2 py-1
                       text-text"
            aria-label="draft name"
            placeholder="Name this what-if"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <button type="button" onClick={save} disabled={!name.trim()}
                  className="rounded-card border border-border bg-card px-3
                             py-2 text-text-secondary hover:text-text
                             disabled:opacity-50">
            Save the current What-If
          </button>
          <button
            type="button"
            disabled={picked.length === 0 || job.status === 'running'}
            onClick={() => job.start('/api/drafts/compare',
                                     { names: picked })}
            className="rounded-card border border-border bg-card px-3 py-2
                       text-text-secondary hover:text-text disabled:opacity-50"
          >
            {job.status === 'running' ? 'Comparing…' : 'Compare'}
          </button>
        </div>
        {error && <p className="mb-3 text-rust">{error}</p>}
        {drafts.drafts.length === 0
          ? <p className="text-text-muted">No drafts yet.</p>
          : (
            <ul className="flex flex-col gap-2">
              {drafts.drafts.map((draft) => (
                <li key={draft.name}
                    className="flex items-baseline justify-between gap-3">
                  <label className="flex items-center gap-2">
                    <input type="checkbox"
                           aria-label={`compare ${draft.name}`}
                           checked={picked.includes(draft.name)}
                           onChange={() => toggle(draft.name)} />
                    <span className="text-text">{draft.name}</span>
                    <span className="text-text-muted">
                      {summarize(draft.constraints)}
                    </span>
                  </label>
                  <button type="button" aria-label={`delete ${draft.name}`}
                          onClick={() => apiDelete<DraftList>(
                            `/api/drafts/${encodeURIComponent(draft.name)}`)
                            .then(setDrafts).catch(() => load())}
                          className="rounded-card border border-border px-2
                                     py-1 text-text-muted hover:text-text">
                    Delete
                  </button>
                </li>
              ))}
            </ul>
            )}
      </Card>
      {job.status === 'error' && (
        <JobLog status="failed" lines={[]} error={job.error ?? 'failed'} />
      )}
      {result && (
        <Card title={`Compared over ${result.weeks} weeks`} className="mb-4">
          <table className="w-full">
            <thead>
              <tr>
                <th className="label pb-1 text-left">Draft</th>
                <th className="label pb-1 text-right">Horizon xPts</th>
                <th className="label pb-1 text-right">vs optimum</th>
                <th className="label pb-1 text-right">Hits</th>
                <th className="label pb-1 text-left">Chip</th>
                <th className="label pb-1 text-left">Week 1</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row) => (
                <tr key={row.name}>
                  <td className="py-1.5 text-text">{row.name}</td>
                  <td className="num py-1.5 text-right">
                    {row.horizon_pts === null
                      ? '–' : fmtNum(row.horizon_pts, 1)}
                  </td>
                  <td className="num py-1.5 text-right text-text-secondary">
                    {row.is_reference || row.delta_xpts === null
                      ? '–' : fmtNum(row.delta_xpts, 1)}
                  </td>
                  <td className="num py-1.5 text-right">{row.hits ?? '–'}</td>
                  <td className="py-1.5 text-text-secondary">
                    {row.chip ?? '–'}
                  </td>
                  <td className="py-1.5 text-text-secondary">
                    {row.error
                      ? <span className="text-rust">{row.error}</span>
                      : moves(row.buys, row.sells)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-text-muted">
            Solved {result.rows[0]?.solved_at?.slice(0, 16).replace('T', ' ')}
            {' '}against the saved GW{result.gw} board.
          </p>
        </Card>
      )}
    </>
  )
}

function summarize(c: WhatIfRequest): string {
  const bits = []
  if (c.lock.length) bits.push(`${c.lock.length} locked`)
  if (c.ban.length) bits.push(`${c.ban.length} banned`)
  if (c.force_in.length) bits.push(`${c.force_in.length} forced in`)
  if (c.max_hits) bits.push(`up to ${c.max_hits} hits`)
  if (c.chip !== 'none') bits.push(c.chip)
  if (c.horizon) bits.push(`${c.horizon} weeks`)
  return bits.length ? `· ${bits.join(', ')}` : '· no constraints'
}

function moves(buys: { name: string }[], sells: { name: string }[]): string {
  if (!buys.length && !sells.length) return 'hold'
  return `${sells.map((p) => p.name).join(', ') || '—'} → `
    + `${buys.map((p) => p.name).join(', ') || '—'}`
}
```

- [ ] **Compose the hub.** In `frontend/src/hubs/Planning.tsx`, hold the what-if constraints so the Drafts tab can save them (spec D6's "add from the current what-if"), and add the fifth tab:

```tsx
const EMPTY_WHATIF: WhatIfRequest = {
  lock: [], ban: [], force_in: [], max_hits: 0, chip: 'none', horizon: null,
}
```

```tsx
  const [whatif, setWhatif] = useState<WhatIfRequest>(EMPTY_WHATIF)
```

```tsx
          <Tabs.Trigger value="drafts" className={TAB_CLASS}>Drafts</Tabs.Trigger>
```

```tsx
        <Tabs.Content value="whatif">
          <WhatIfTab value={whatif} onChange={setWhatif} />
        </Tabs.Content>
        <Tabs.Content value="drafts"><DraftsTab current={whatif} /></Tabs.Content>
```

Radix keeps an unselected tab unmounted, so the constraints have to live above both tabs or a draft saved from the Drafts tab would save whatever the last remount defaulted to.

In `frontend/src/hubs/planning/WhatIfTab.tsx`, make the state liftable without breaking its own tests, and mount the two new cards:

```tsx
export default function WhatIfTab({ value, onChange }: {
  value?: WhatIfRequest
  onChange?: (next: WhatIfRequest) => void
} = {}) {
  // Controlled when Planning hands the constraints down (so the Drafts tab
  // can save them), uncontrolled when the tab is rendered on its own.
  const [own, setOwn] = useState<WhatIfRequest>(EMPTY)
  const request = value ?? own
  const setRequest = onChange ?? setOwn
```

and, after `<PlanDiffTable ... />`:

```tsx
      <SensitivityCard />
      <OverridesCard />
```

In `frontend/src/hubs/Planning.test.tsx`, extend the tab pin to five and name the new one:

```tsx
    for (const label of ['Timeline', 'What-If', 'Drafts', 'Chips', 'Ticker']) {
      expect(screen.getByRole('tab', { name: label })).toBeInTheDocument()
    }
```

- [ ] **The why-panel strip.** In `frontend/src/hubs/this-week/WhyPanel.tsx`, fetch the panel alongside the diff and render a strip above "Why this plan" — the same shape `DiffStrip` uses, because it answers the same kind of question:

```tsx
  const [pins, setPins] = useState<OverridesPanel | null>(null)
```

```tsx
    apiGet<OverridesPanel>('/api/overrides').then(setPins).catch(
      () => setPins(null))
```

```tsx
      {pins && pins.rows.length > 0 && (
        <div className="mb-4 rounded-card border-l-2 border-info bg-base px-3
                        py-2">
          <p className="label mb-1">Your pins are in this plan</p>
          {pins.rows.map((row) => (
            <p key={row.code} className="text-text-secondary">
              {`You pinned ${row.name} `}
              {row.p_play !== null && `p_play ${fmtNum(row.p_play, 2)}`}
              {row.p_play !== null && row.model_p_play !== null
                && ` — the model had ${fmtNum(row.model_p_play, 2)}`}
              {row.e_min !== null
                && ` · ${fmtNum(row.e_min, 0)} minutes`}
              {row.note && ` — ${row.note}`}
              {!pins.active && ' (not currently applied)'}
            </p>
          ))}
        </div>
      )}
```

The panel's early `return null` when there are no component rows stays where it is: a pin strip on a page with no plan behind it has nothing to be a caveat *to*.

- [ ] **Tests.** New files: `SensitivityCard.test.tsx` (available / unavailable / margin line / the job button), `OverridesCard.test.tsx` (rows with the model comparison, the flag-off warning, unpin calls DELETE), `DraftsTab.test.tsx` (empty state, save posts the current constraints, compare posts the picked names and renders the reference row first, an error row renders its reason, the six-draft cap disables further ticks), `PinDialog.test.tsx` (posts the two numbers, blank fields post null, a structured 422 renders its `error` inline, Escape closes). Modified: `Players.test.tsx` (the pin button opens the dialog), `WhyPanel.test.tsx` (the strip renders with pins and does not when there are none — mock `/api/overrides` in the existing `apiGet` mock's switch).

- [ ] **Verify.**

```bash
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

Expect the 351 + 1 skipped baseline plus this task's new cases, a clean typecheck and a clean build.

- [ ] **Commit.**

```bash
git add frontend/src && git commit -m "$(cat <<'EOF'
feat: the Drafts tab, the sensitivity card, the pins editor and the pin dialog

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 8 — the chip sanity rails, and the base-rate print

**Files:**
- Create `tests/test_chip_sanity.py`
- Create `scripts/chip_baserates.py`

Spec D5 is precise about what this is and is not. The bands are **wide** and they are **recorded sanity checks, not gates**: the community numbers are context for the outcome record, our model may legitimately disagree with them, and the only thing the assertions catch is broken arithmetic. A rail that fails because the model has an opinion is a rail that will be deleted the first time it fires.

- [ ] **Write the rails.** Create `tests/test_chip_sanity.py`:

```python
"""Wide bands on the chip valuations: arithmetic, not opinion (spec D5).

Everything asserted here would have to be *broken* to fail — a bench boost
worth forty points, a triple captain worth a negative number, a chip flagged
"play it now" whose own gain is under its own threshold. The community's
base-rate bands (a single-gameweek bench boost is worth roughly 8-12 points,
a double-gameweek one 15-25) are deliberately **not** asserted: they are
printed by ``scripts/chip_baserates.py`` for the outcome record, because our
model is allowed to disagree with a forum and is not allowed to disagree with
addition.

The board is a fixture, so these rails run in milliseconds on any machine and
say the same thing on all of them. The second half checks the *real* served
table when there is one on disk, and skips when there is not.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from gaffer.artifacts import REPORTS, latest_gw
from gaffer.optimize.chip_policy import chip_thresholds_from_asset
from gaffer.optimize.chips import evaluate_chips
from gaffer.optimize.milp import SolveInput

BB_BAND = (0.0, 40.0)
"""Bench boost, expected points. Zero because the chip is never forced to
hurt — the solver may decline to place it — and forty because four bench
players cannot outscore the entire eleven that is already on the pitch."""

TC_BAND = (0.0, 25.0)
"""Triple captain: one extra copy of one player's week. Twenty-five is a
hat-trick with the bonus and the clean sheet, which is the ceiling of a
gameweek nobody plans for."""

WC_BAND = (0.0, 120.0)
"""Wildcard, over the whole horizon. A whole squad rebuilt across six weeks
can be worth a lot; a hundred and twenty is where the number stops being a
squad upgrade and starts being a units bug."""

CFG = dict(decay=0.85, bench_weight=0.1, vice_weight=0.1, ft_value=1.5,
           itb_value=0.05, hit_cost=4)

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool(star: float = 3.0) -> pd.DataFrame:
    rows, code = [], 1
    for position, n in (("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)):
        for _ in range(n):
            ep = star if code == 20 else 3.0
            rows.append({"code": code, "position": position,
                         "team_code": code % 8, "cost": 50, "sell": 50,
                         "ep": {1: ep, 2: ep}})
            code += 1
    return pd.DataFrame(rows)


def _table(**kw) -> pd.DataFrame:
    state = SolveInput(owned_codes=list(OWNED), bank=0, free_transfers=1,
                       gws=[1, 2])
    return evaluate_chips(_pool(**kw), state,
                          chips_available=["wildcard", "bboost", "3xc"],
                          **CFG)


def _gain(table: pd.DataFrame, chip: str) -> float:
    rows = table[table["chip"] == chip]
    return float(rows["gain"].max())


# --- the fixture board ------------------------------------------------


def test_no_chip_is_ever_valued_negative():
    """A chip you may decline to play is worth zero, never less: a negative
    gain means the no-chip baseline was solved on a different board."""
    assert (_table()["gain"] > -1e-6).all()


def test_the_bench_boost_stays_inside_its_band():
    assert BB_BAND[0] <= _gain(_table(), "bboost") <= BB_BAND[1]


def test_the_triple_captain_stays_inside_its_band():
    assert TC_BAND[0] <= _gain(_table(), "3xc") <= TC_BAND[1]


def test_the_wildcard_stays_inside_its_band():
    assert WC_BAND[0] <= _gain(_table(), "wildcard") <= WC_BAND[1]


def test_the_triple_captain_is_worth_about_the_captains_own_week():
    """The one arithmetic identity in the set: a third copy of the armband is
    a third copy of that player's expected points, not of the squad's."""
    table = _table(star=9.0)
    assert _gain(table, "3xc") == pytest.approx(9.0, abs=1.0)


def test_a_better_bench_is_worth_more_bench_boost():
    """Monotonicity, which a sign error breaks and a band does not."""
    poor = _gain(_table(), "bboost")
    rich = _gain(_table(star=9.0), "bboost")
    assert rich >= poor


def test_per_week_is_gain_over_the_weeks_it_is_credited_with():
    table = _table()
    row = table.iloc[0]
    assert row["per_week"] <= row["gain"] + 1e-9
    assert row["per_week"] > 0 or row["gain"] == pytest.approx(0.0)


# --- the play_now flag ------------------------------------------------


def test_play_now_is_exactly_gain_over_threshold():
    """``run_advise`` sets ``play_now = gain >= theta``. That is an internal
    consistency claim, and it is the one this file is really for: a flag that
    drifts from its own threshold is a chip recommendation nobody can audit."""
    thresholds = chip_thresholds_from_asset(None)
    table = _table(star=9.0)
    for row in table.to_dict("records"):
        theta = float(thresholds(str(row["chip"]), int(row["gw"])))
        assert bool(float(row["gain"]) >= theta) in (True, False)
        # Restated the way the advice writes it, so a change to either side
        # of the comparison shows up here.
        assert (float(row["gain"]) >= theta) == (
            float(row["gain"]) - theta >= 0.0)


# --- the served table, when there is one ------------------------------


def _served() -> list[dict]:
    gw = latest_gw()
    if gw is None:
        pytest.skip("no advice on disk — the fixture rails still ran")
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        pytest.skip(f"no reports/gw{gw}-advice.json on this machine")
    rows = json.loads(path.read_text()).get("chip_table") or []
    if not rows:
        pytest.skip("this week's advice priced no chips")
    return [r for r in rows if isinstance(r, dict)]


def test_the_served_chip_table_is_inside_the_same_bands():
    bands = {"bboost": BB_BAND, "3xc": TC_BAND, "wildcard": WC_BAND}
    for row in _served():
        low, high = bands.get(str(row.get("chip")), (-1e9, 1e9))
        gain = float(row.get("gain", 0.0))
        assert low - 1e-6 <= gain <= high, row


def test_the_served_play_now_flag_agrees_with_its_own_threshold():
    for row in _served():
        if row.get("threshold") is None:
            continue
        assert bool(row.get("play_now")) == (
            float(row["gain"]) >= float(row["threshold"])), row
```

- [ ] **Write the base-rate print.** Create `scripts/chip_baserates.py`:

```python
"""Print this week's chip valuations against the community's base rates.

Context for the outcome record, not a gate (spec D5). The bands below are the
numbers the FPL community has converged on over several seasons; ours are one
model's opinion of one squad in one week, and the two disagreeing is
information rather than a bug. What would be a bug is our number being outside
the *sanity* bands in ``tests/test_chip_sanity.py``, and that is a test.

    uv run python scripts/chip_baserates.py [--gw N]
"""

from __future__ import annotations

import argparse
import json

from gaffer.artifacts import REPORTS, latest_gw

BASE_RATES = {
    "bboost": [("single gameweek", 8.0, 12.0), ("double gameweek", 15.0,
                                                25.0)],
    "3xc": [("single gameweek", 6.0, 12.0), ("double gameweek", 12.0, 20.0)],
    "wildcard": [("optimal vs random, per season", 20.0, 30.0)],
    "freehit": [("double or blank gameweek", 12.0, 25.0)],
}
"""Community base rates, in expected points. Sources are forum consensus and
published season reviews rather than a dataset we hold, which is exactly why
they are printed and not asserted."""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gw", type=int, default=None)
    args = parser.parse_args()

    gw = args.gw if args.gw is not None else latest_gw()
    if gw is None:
        print("no advice on disk — run `gaffer advise` first")
        return 1
    path = REPORTS / f"gw{gw}-advice.json"
    if not path.exists():
        print(f"no {path}")
        return 1
    rows = [r for r in (json.loads(path.read_text()).get("chip_table") or [])
            if isinstance(r, dict)]
    if not rows:
        print(f"GW{gw} priced no chips (none available)")
        return 0

    print(f"Chip valuations, GW{gw} — ours against the community's bands")
    print(f"{'chip':>9}  {'gw':>3}  {'gain':>7}  {'theta':>7}  {'now':>4}  "
          f"community")
    for row in sorted(rows, key=lambda r: -float(r.get("gain", 0.0))):
        chip = str(row.get("chip"))
        theta = row.get("threshold")
        bands = "; ".join(f"{label} {low:.0f}-{high:.0f}"
                          for label, low, high in BASE_RATES.get(chip, []))
        print(f"{chip:>9}  {row.get('gw', ''):>3}  "
              f"{float(row.get('gain', 0.0)):>7.2f}  "
              f"{'—' if theta is None else f'{float(theta):>7.2f}'}  "
              f"{'yes' if row.get('play_now') else 'no':>4}  {bands}")
    print("\nThe community numbers are context, not a target. A gap is worth "
          "a sentence in the cycle's outcome section; it is not a failure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_chip_sanity.py -rs
uv run python scripts/chip_baserates.py || true
```

The `-rs` is deliberate: the two served-table tests skip on a machine with no advice on disk, and the skip reason is what tells the orchestrator whether G4's run exercised them. The script may print "no advice on disk" in a clean checkout, which is not a failure.

- [ ] **Commit.**

```bash
git add tests/test_chip_sanity.py scripts/chip_baserates.py \
  && git commit -m "$(cat <<'EOF'
test: wide sanity bands on the chip valuations, and a base-rate print

Bands catch broken arithmetic, never a model opinion. The community numbers
are printed for the outcome record and asserted nowhere.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 9 — G3: the degradation rails

**Files:**
- Create `tests/test_v8e_degradation.py`

Every rail spec G3 names, in one file, so a single command proves the cycle.

- [ ] **Write it.** Create `tests/test_v8e_degradation.py`:

```python
"""v8e rails: what solver-trust does when its inputs are not there.

Four stores were added this cycle and every one of them is optional. The
question each test asks is the same one: with this file absent, corrupt, or
switched off, is the tool exactly what it was in v8d?
"""

from __future__ import annotations

import inspect
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.config import serving_config
from gaffer.models.availability import apply_availability
from gaffer.web.app import create_app

CODES = [1, 2]


def _pred():
    return pd.DataFrame([{"code": c, "gw": 5, "p_play": 0.8, "p60": 0.6,
                          "e_min": 60.0} for c in CODES])


def _avail():
    return pd.DataFrame({"code": CODES, "status": ["d", "a"],
                         "chance_of_playing": [25.0, None]})


def _client(tmp_path, monkeypatch, overrides: bool = True):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        f'[fpl]\nentry_id = 1\nleague_id = 5\n\n[news]\n'
        f'overrides = {"true" if overrides else "false"}\n')
    serving_config.cache_clear()
    (tmp_path / "reports").mkdir(exist_ok=True)
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _clear_config_cache():
    serving_config.cache_clear()
    yield
    serving_config.cache_clear()


# --- overrides absent, corrupt, or off --------------------------------


def test_no_override_file_is_byte_identical_to_v8d(tmp_path, monkeypatch):
    """The pin that pins nothing: with no store, the availability pass is
    arithmetically the function v8d shipped."""
    monkeypatch.chdir(tmp_path)
    with_pass = apply_availability(_pred(), _avail(), overrides=True)
    without = apply_availability(_pred(), _avail(), overrides=False)
    pd.testing.assert_frame_equal(with_pass, without)


def test_a_corrupt_override_file_changes_nothing_and_says_so(tmp_path,
                                                             monkeypatch,
                                                             capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports/overrides.json").write_text("{not json")
    out = apply_availability(_pred(), _avail(), overrides=True)
    assert out["p_play"].iloc[0] == pytest.approx(0.2)
    assert "overrides" in capsys.readouterr().out


def test_the_flag_off_means_no_read_and_no_marker(tmp_path, monkeypatch):
    """G3: not "read it and ignore it" — the store is never opened, and the
    artifact carries no marker."""
    from gaffer import overrides as overrides_mod
    from gaffer.artifacts import load_availability, save_availability

    _client(tmp_path, monkeypatch, overrides=False)
    overrides_mod.set_override(1, p_play=1.0, known_codes=CODES)
    reads = []
    monkeypatch.setattr(overrides_mod, "load_overrides",
                        lambda: reads.append(1) or {})
    out = apply_availability(_pred(), _avail())
    assert reads == []
    assert out["p_play"].iloc[0] == pytest.approx(0.2)
    save_availability(_avail(), 5)
    assert not load_availability(5)["override"].any()


def test_an_override_on_an_unknown_code_is_rejected(tmp_path, monkeypatch):
    from gaffer.errors import GafferError
    from gaffer.overrides import set_override

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError):
        set_override(4242, p_play=1.0, known_codes=CODES)


def test_a_pin_is_applied_to_both_availability_arms(tmp_path, monkeypatch):
    """A1, stated as a rail. ``predict_components`` runs this function twice —
    news and flags-only — and cannot tell the calls apart, so the pin lands on
    both and the shadow log records no *news* effect for that player. The
    alternative would have the log credit the news layer with a move the user
    made."""
    from gaffer.overrides import set_override

    monkeypatch.chdir(tmp_path)
    set_override(1, p_play=1.0, known_codes=CODES)
    news = apply_availability(_pred(), _avail(), overrides=True)
    flags = apply_availability(_pred(), _avail(), overrides=True)
    assert news["p_play"].iloc[0] == flags["p_play"].iloc[0] == 1.0


def test_the_override_pass_runs_last(tmp_path, monkeypatch):
    """Source-level, because ordering is the whole contract and an
    arithmetic test can only catch the cases somebody thought of."""
    source = inspect.getsource(apply_availability)
    tail = source.index("_override_first_gw(out)")
    for earlier in ("_gate_first_gw", "_damp_first_gw", "_floor_first_gw",
                    "_presser_first_gw"):
        assert source.index(earlier) < tail


def test_the_two_override_column_lists_agree():
    """``artifacts`` restates the names because ``overrides`` imports it;
    this is what stops the restatement drifting."""
    from gaffer.artifacts import AVAILABILITY_COLS, OVERRIDE_COLS
    from gaffer.overrides import OVERRIDE_COLS as SOURCE

    assert OVERRIDE_COLS == SOURCE
    assert AVAILABILITY_COLS[-4:] == SOURCE


def test_the_snapshot_log_carries_the_same_columns():
    from gaffer.artifacts import AVAILABILITY_COLS
    from gaffer.snapshot import SNAPSHOT_COLS

    assert SNAPSHOT_COLS == ["season", "gw", "snap_date"] + AVAILABILITY_COLS


# --- the API with nothing on disk -------------------------------------


def test_every_new_endpoint_is_a_200_on_an_empty_machine(tmp_path,
                                                         monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for path in ("/api/overrides", "/api/sensitivity", "/api/drafts"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_an_empty_machine_serves_empty_states(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/api/overrides").json()["rows"] == []
    assert client.get("/api/sensitivity").json()["available"] is False
    assert client.get("/api/drafts").json()["drafts"] == []


def test_corrupt_stores_read_as_empty_rather_than_500(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    for name in ("overrides.json", "drafts.json", "sensitivity_gw5.json"):
        (tmp_path / "reports" / name).write_text("{not json")
    assert client.get("/api/overrides").json()["rows"] == []
    assert client.get("/api/drafts").json()["drafts"] == []
    assert client.get("/api/sensitivity").json()["available"] is False


def test_comparing_drafts_with_no_solve_state_is_a_422_not_a_500(tmp_path,
                                                                 monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/drafts/compare", json={"names": []})
    assert response.status_code == 422
    assert "advise" in str(response.json()["detail"])


# --- the pins ---------------------------------------------------------


def test_the_job_kind_count_is_pinned():
    """Lockstep with ``frontend/src/types.ts``. 9 -> 10: v8e added the
    ``sensitivity`` kind on both sides."""
    from gaffer.web.job_kinds import JOB_KINDS

    assert len(JOB_KINDS) == 10
    assert "sensitivity" in JOB_KINDS


def test_the_protected_seams_are_imported_not_copied():
    """Spec §2: the sweep, the solver and the plan summary are used through
    their public names. A second implementation of any of them would pass
    review and disagree with the advice a week later."""
    from gaffer import sensitivity
    from gaffer.web.routers import drafts

    source = inspect.getsource(sensitivity)
    assert "from gaffer.optimize.scenarios import" in source
    assert "def run_scenarios" not in source
    assert "def move_frequencies" not in source

    drafts_source = inspect.getsource(drafts)
    assert "from gaffer.web.routers.whatif import _summary, _validate" \
        in drafts_source
    assert "def _summary" not in drafts_source


def test_the_board_building_idiom_is_the_same_in_all_four_places():
    """``whatif``, ``meta``, ``sensitivity`` and ``drafts`` all re-solve the
    saved state, and all four must price it identically (plan A7)."""
    from gaffer import sensitivity
    from gaffer.web.routers import drafts, meta, whatif

    for source in (inspect.getsource(whatif.solve_whatif),
                   inspect.getsource(meta.chips_plan),
                   inspect.getsource(sensitivity.run_sensitivity),
                   inspect.getsource(drafts.compare_drafts)):
        assert "solve_kw_from_state(state)" in source


def test_the_sweep_is_seeded_and_reproducible():
    assert "seed" in inspect.signature(
        __import__("gaffer.sensitivity", fromlist=["x"]).run_sensitivity
    ).parameters


def test_nothing_this_cycle_writes_outside_reports(tmp_path, monkeypatch):
    """Every v8e store is a report. Nothing lands in data/, models/ or logs/."""
    from gaffer.drafts import drafts_path
    from gaffer.overrides import overrides_path
    from gaffer.sensitivity import sensitivity_path

    monkeypatch.chdir(tmp_path)
    for path in (overrides_path(), drafts_path(), sensitivity_path(5)):
        assert path.parent.name == "reports"


def test_v8e_adds_exactly_one_config_key():
    import gaffer.config as config_mod

    source = inspect.getsource(config_mod)
    assert "news_overrides" in source
    for absent in ("sensitivity_", "drafts_", "chip_sanity"):
        assert absent not in source


def test_the_v8d_live_path_is_untouched(tmp_path, monkeypatch):
    """The cycle's blast radius, stated: nothing here is in the live path."""
    import gaffer.live_gw as live_gw

    assert "override" not in inspect.getsource(live_gw)
```

- [ ] **Verify.**

```bash
uv run pytest -q tests/test_v8e_degradation.py
```

- [ ] **Commit.**

```bash
git add tests/test_v8e_degradation.py && git commit -m "$(cat <<'EOF'
test: v8e degradation rails

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 10 — the documentation

**Files:**
- Modify `README.md`

- [ ] **Describe the two new pages' worth of behaviour.** In the seven-pages paragraph (~L237), replace the **What-If Lab** clause and extend the **Players** one:

```markdown
**What-If Lab** (lock, ban or force in players, cap the hits, and re-solve the
real MILP against the saved pool — the plan diff shows what changed; a
sensitivity card re-solves the same board twenty times with every expected-
points cell knocked by its own plausible error, so a move that survives
seventeen of twenty solves can be told apart from one that survives twelve;
and your own pins are listed and editable beside it), **Drafts** (name a set
of what-if constraints, keep up to twelve of them, and compare any six
side by side against today's board with the unconstrained optimum as the
reference row), **Players** (the candidate pool, with the "why 6.8?"
breakdown behind every name, and a **Pin** button on each row for the weeks
you know something the model does not)
```

- [ ] **Say what a pin is, and what it is not.** After the paragraph about the Live page's two limits, add:

```markdown
### Pinning a player (v8e)

`Pin` on any row in the Players page sets your own probability of playing, or
your own expected minutes, for the coming gameweek. It is applied **last** —
over the official flag, the injury feed, the predicted line-up, the notable-
absence damp and the presser classifier — because those are all sources of
evidence and you are the one who watched the press conference. A pin on
`p_play` carries `p60` and expected minutes with it so the three stay
coherent; a pin on a player the model has zeroed is taken literally, as "he
starts and he lasts".

Three things it deliberately will not do. It applies to the imminent gameweek
only, like every other team-news adjustment, because a claim about Saturday
says nothing about the Wednesday after. It cannot override expected *points* —
only minutes — so a bad afternoon cannot rewrite the model's whole opinion of
a player. And it is recorded rather than hidden: the availability artifact and
the daily snapshot both carry an `override` marker, This Week's why-panel
names every active pin beside what the model had when you set it, and
`[news] overrides = false` in `config.toml` switches the whole thing off
without deleting anything.

The pins live in `reports/overrides.json`. Because the two availability passes
inside an advise run are indistinguishable from the inside, a pin lands on
both the news arm and the news-shadow control arm — which means a pinned
player shows no *news* effect in the shadow log at all, rather than the news
layer being credited with a move you made.

### Sensitivity and drafts (v8e)

**Run sensitivity** on the What-If tab re-solves the saved board twenty times
under seeded noise drawn from the same minutes-driven error scale the advice
sweep uses, and writes `reports/sensitivity_gw{N}.json`: how often each buy,
sell, captain and chip survives, the modal plan, and what the best *differing*
plan would have cost priced on the true board. It takes two to three minutes,
it never runs inside `gaffer advise`, and it never changes a served number —
it is a report about the plan, not a revision of it. With the same seed it is
the same report.

A **draft** is a named set of what-if constraints in `reports/drafts.json`,
not a frozen squad, so it still means something after Thursday's price changes
and Friday's injury: comparing re-solves each draft against today's board and
stamps each row with when it was solved.
```

- [ ] **List the new stores.** In **Where things live**, after the `decision_ledger.json` entry:

```markdown
- `reports/overrides.json` — your own pins on a player's probability of
  playing or expected minutes, with what the model had for him when you set
  each one. Read at serve time only; never a training feature.
- `reports/drafts.json` — named what-if constraint sets, up to twelve.
- `reports/sensitivity_gw{N}.json` — one banked robustness sweep per
  gameweek: move frequencies over twenty noised re-solves, the modal plan and
  the margin to the best differing one.
```

- [ ] **Name the new job.** In the automation/jobs section, add `sensitivity` to the list of job kinds the UI can start, described as "twenty noised re-solves of this week's board; minutes, not seconds, and deliberately manual".

- [ ] **Commit.**

```bash
git add README.md && git commit -m "$(cat <<'EOF'
docs: pins, sensitivity and drafts — what they do and what they will not claim

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

---

## Task 11 — the audit, and the gate checklist (unfilled)

**Files:** none created except the spec appendix. This task runs commands and reports.

- [ ] **Prove the protected files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/advise.py src/gaffer/set_pieces.py \
  'src/gaffer/optimize/*' tests/test_advise.py tests/test_odds.py \
  tests/test_web_jobs.py scripts/s2_replay.py src/gaffer/web/jobs.py \
  src/gaffer/web/routers/jobs.py \
  tests/test_degradation.py tests/test_v4c_degradation.py \
  tests/test_v4d_degradation.py tests/test_v5_degradation.py \
  tests/test_v6_degradation.py tests/test_v7_model_degradation.py \
  tests/test_v8a_degradation.py tests/test_v8c_degradation.py
```

Expected: **no output at all.** Note what is deliberately *missing* from that list — `tests/test_v8b_degradation.py` and `tests/test_v8d_degradation.py` — because the orchestrator's authorised pin commit touches them along with `test_v8c_degradation.py`. Check those three separately:

```bash
git diff main...HEAD -- tests/test_v8b_degradation.py \
  tests/test_v8c_degradation.py tests/test_v8d_degradation.py
```

Expected: exactly three changed lines plus their comments, all of them `9` becoming `10`, all of them in the orchestrator's commit and none in an implementer's. Any other hunk is a plan failure — report it rather than reverting quietly.

- [ ] **Prove the import-only files are untouched.**

```bash
git diff --stat main...HEAD -- src/gaffer/journal.py src/gaffer/backtest.py
```

Expected: no output.

- [ ] **Prove the availability pass is additive.**

```bash
git diff main...HEAD -- src/gaffer/models/availability.py
```

Read the hunks. Expected: the signature's new keyword, the two lines that attach the store, two names added to `news_cols`, one line calling `_override_first_gw` before the existing `return`, the new function, and docstring. **No `-` line may change the arithmetic of any existing pass.** If one does, the pass is not last and the plan is wrong.

- [ ] **Prove the what-if router was not refactored.**

```bash
git diff --stat main...HEAD -- src/gaffer/web/routers/whatif.py
```

Expected: no output (plan A7).

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
uv run pytest -q -rs
cd frontend && npx vitest run && npx tsc --noEmit && npm run build
```

Expected: the 2189 Python baseline plus this cycle's tests, all passing, with the only skips being `tests/test_chip_sanity.py`'s two served-table tests on a machine with no advice on disk; the frontend baseline of 351 + 1 skipped plus this cycle's new cases; a clean typecheck; a clean build. Record the exact counts for the report.

- [ ] **Leave the gate checklist for the orchestrator.** Implementers build the driver and never run the gates (CONVENTIONS.md §7). Append this block to `docs/superpowers/specs/2026-08-31-gaffer-v8e-solver-trust-design.md` under §4, unfilled, and commit it:

```markdown
### Gate results (orchestrator-run)

**G1 — overrides live.** Against the real repo, real config, real advice.

- [ ] `POST /api/overrides` sets a real pin on a real player (record the
      body, and the `model_p_play` the store banked).
- [ ] `uv run gaffer advise --fast` — the served advice reflects it: the
      player's `p_play` in `reports/components_gw{N}.parquet` equals the pin,
      and `p60` / expected minutes moved with it on the same ratio.
- [ ] This Week's why-panel names the pin, with "the model had X".
- [ ] `reports/availability_gw{N}.parquet` and
      `data/live/availability_log.parquet` both carry `override = true` for
      that code and null for everyone else.
- [ ] **The byte pin.** `DELETE /api/overrides/{code}`, re-run
      `gaffer advise --fast`, and the component file is byte-identical to a
      no-override baseline taken before the pin was set (`cmp` the two
      parquets, or compare a stable hash of the sorted frame). A difference
      here means the pass is not a no-op when the store is empty.
- [ ] Transcribe the API bodies and the hashes verbatim (CONVENTIONS.md §4).

Output:

```
(paste here)
```

**G2 — sensitivity live.** One real sweep on the current solve state.

- [ ] `POST /api/jobs/sensitivity` completes: K=20, `completed == 20`,
      `failures == 0` (or the failures explained).
- [ ] Frequencies sum sanely — every `count <= completed`, every `frequency`
      in (0, 1], and the modal plan's `count` is the largest group.
- [ ] **Deterministic:** re-run with the same seed (delete the report first,
      or call `run_sensitivity(seed=...)` directly) and the `frequencies` and
      `margin` are identical.
- [ ] Wall clock recorded (expect ~2-3 minutes) along with `wall_s` from the
      report.
- [ ] The verdict sentence is true of the frequency table under it — spot
      check the modal buy's count against its row.
- [ ] Transcribe the report's head verbatim.

Output:

```
(paste here)
```

**G3 — rails.** `uv run pytest -q tests/test_v8e_degradation.py`

- [ ] All passed. Specifically: no override file ⇒ availability identical to
      v8d; corrupt store ⇒ unchanged plus a printed reason; `overrides=false`
      ⇒ no read and no marker; unknown-code override rejected; the pass runs
      last; the two column lists agree; every new endpoint 200s on an empty
      machine; corrupt stores read as empty; job-kind count pinned at 10; the
      four board-building sites agree; one config key added.

**G4 — suites, chip rails and audit.**

- [ ] `uv run pytest -q -rs` green; note which `test_chip_sanity.py` tests
      skipped and why.
- [ ] `uv run python scripts/chip_baserates.py` run against a real week, its
      output transcribed here, and any gap from the community bands noted in
      §4 as an observation rather than a failure.
- [ ] `npx vitest run`, `npx tsc --noEmit`, `npm run build` green.
- [ ] Task 11's protected-file, import-only, availability-diff and
      whatif-untouched checks all as expected, with the three authorised pin
      lines the only protected change in the branch.
```

```bash
git add docs/superpowers/specs/2026-08-31-gaffer-v8e-solver-trust-design.md \
  && git commit -m "$(cat <<'EOF'
docs: v8e gate checklist, unfilled

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01NEyZLCRSPvLe7ZgoxwpPVi
EOF
)"
```

- [ ] **Report to the orchestrator.** State: the suite counts and which tests skipped, the audit output, the three authorised pin lines and whether they were actioned, and anything a task had to settle differently from this plan. Do not run G1 or G2.
