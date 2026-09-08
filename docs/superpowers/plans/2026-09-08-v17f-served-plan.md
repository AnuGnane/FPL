# v17f — the served plan, owned once: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One frozen `ServedPlan` value, built in advise, written whole into the advice JSON, read back by one loader that every router calls; the plan router becomes a shape adapter; the advice filename is spelled once.

**Architecture:** `src/gaffer/served.py` holds the pydantic models and the pure functions that price, charge, bank and trace a plan (`completed`), called by advise at write time and by `artifacts.served_plan` to backfill a file written before this cycle. `serve_rung` returns the typed value. The router maps it onto the unchanged `PlanTimeline`. Spec: `docs/superpowers/specs/2026-09-08-v17f-served-plan-design.md`.

**Tech Stack:** Python 3, pydantic v2 (core dependency already), FastAPI, pytest; the frontend's generated types via `cd frontend && npm run types`.

**Protected and orchestrator-only (CLAUDE.md, spec §7):** Tasks 0, 3, 4, 5, 7 and 9 are the orchestrator's. Implementers never touch `src/gaffer/advise.py`, `serve_rung` in `src/gaffer/ladder.py`, `tests/test_advise.py`, `tests/test_v16_restraint.py`, any pre-existing `tests/test_v*_degradation.py`, or `config.toml`. The odds key is `[odds] api_key`, by name only.

**The suites:** `.venv/bin/pytest -q` (about 4360 tests, five minutes) and `cd frontend && npx tsc --noEmit && npx vitest run` (read vitest's `Errors  N error` line as a failure). The golden gate, `.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py`, takes about eight minutes and is the orchestrator's (Task 9). Between tasks, run the named files, then the full Python suite before each commit.

**Amendments to the spec, made in Task 0's first commit:** (a) the advice JSON already has a top-level `alternatives` key (the captain-alternatives table), so the served alternatives keep the existing `alternative_plans` key and its `{gap, plan_by_gw}` shape; the weeks inside gain the same new keys as `plan_by_gw`'s, and nothing is duplicated or left for v17g. (b) The write is `model_dump(exclude_unset=True)`, so a move that advise never tagged does not gain a `tag: null` on disk; a rail pins it. (c) `tracking.py` reads the captain through `load_advice`, which knows no filename either; `served_plan` there would trace a whole plan for one integer. (d) A captain or vice that cannot name a player (not a dict, or no integer code) is `None`, not a validation failure; `test_a_captain_that_is_not_a_dict_is_ignored` therefore survives.

---

## File structure

| File | Responsibility |
|---|---|
| `src/gaffer/served.py` (new) | The models (`PlanMoveTrace`, `PlanWeekTrace`, `ServedMove`, `ServedWeek`, `ServedStep`, `ServedRestraint`, `ServedObjective`, `ServedAlternative`, `ServedPlan`); the pool readers moved from the router (`pool_prices`, `trace_inputs`, `thresholds`, `chip_by_gw`, `price_falls`); the pure passes (`decorated`, `with_alternatives`, `priced`, `charged`, `banked`, `traced`, `completed`). |
| `src/gaffer/web/schemas.py` | Re-exports the models; `WIRE_EXPORTS` names them for the generator. `PlanMoveTrace` and `PlanWeekTrace` are deleted here and imported. |
| `scripts/gen_types.py` | Emits a model named in `schemas.WIRE_EXPORTS` as if defined in `schemas.py`; two `OPTIONAL_ON_THE_WIRE` entries for `ServedMove.tag` and `.frequency`. |
| `src/gaffer/artifacts.py` | `advice_path`, `advice_gws`, `served_plan`; `load_advice` uses `advice_path`. |
| `src/gaffer/ladder.py` | `serve_rung` returns `ServedPlan` (orchestrator). |
| `src/gaffer/advise.py` | Builds the objective input once, decorates, completes, splats one dump into `Advice`; `Advice` gains `generated_at` and `bank` (orchestrator). |
| `src/gaffer/web/routers/plan.py` | Shape adapter. |
| `src/gaffer/web/routers/meta.py`, `src/gaffer/tracking.py`, `src/gaffer/report/render.py` | No filename. |
| `tests/golden_client.py`, `tests/test_golden_board.py`, `tests/data/golden_board/expected/plan.json` | The recorded route (orchestrator). |
| `tests/test_served_plan.py` (new) | The module's tests and the round trip. |
| `frontend/src/types.ts`, `frontend/src/hubs/this-week/MovesCard.tsx`, `frontend/scripts/shots.sh` | Generated served types replace the hand-typed `Restraint`/`Objective`; the v17f shots stage. |

---

### Task 0 (orchestrator): record the plan route on main's code; amend the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-09-08-v17f-served-plan-design.md` (§2.4, §2.5, §2.8, §4, §9 per the amendments above)
- Modify: `tests/golden_client.py` (after `run_golden`)
- Modify: `tests/test_golden_board.py` (after `test_the_golden_run_writes_nothing_through_the_symlinks`)
- Create: `tests/data/golden_board/expected/plan.json`

- [ ] **Step 1: Amend the spec** — in §2.4 replace the `alternatives` row with `every week of alternative_plans[*].plan_by_gw | price, hit_cost, chip, bank | as plan_by_gw's weeks; no trace`, and delete the sentence about `alternatives` beside `alternative_plans`; in §2.5 say the alternatives keep the `alternative_plans` key; in §2.8 say `update_health` reads the captain through `load_advice`; in §4 rename `ServedPlan.alternatives` to `alternative_plans: list[ServedAlternative]` with `ServedAlternative(gap=None, plan_by_gw=[])`, add `ServedStep`, and add the sentence "advise writes `model_dump(exclude_unset=True)`: a key the writer never set is not on disk, so a move advise never tagged carries no `tag`"; in §2.7 add "a captain or vice that cannot name a player is `None`"; in §6 remove `test_a_captain_that_is_not_a_dict_is_ignored` from the dying list; in §9 delete "retiring `alternative_plans` (v17g)".

- [ ] **Step 2: Add `plan_route` to `tests/golden_client.py`** after `run_golden`:

```python
def plan_route(root: Path, gw: int, client: FPLClient | None = None) -> dict:
    """``GET /api/plan/{gw}`` served over the scratch tree ``run_golden``
    filled, ``strip_volatile``d (v17f §1 part 2). The route reads only
    ``reports/`` under the cwd, so it runs inside ``golden_cwd`` exactly
    as the pipeline did; the recorded client keeps the sleep hush."""
    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    client = client if client is not None else RecordedClient()
    with golden_cwd(root, client) as root:
        resp = TestClient(create_app()).get(f"/api/plan/{gw}")
        assert resp.status_code == 200, resp.text
        return strip_volatile(resp.json(), str(root))
```

and in `write_expected`, after the `solve_state.json` write:

```python
    (expected / "plan.json").write_text(
        json.dumps(plan_route(root, int(advice["gw"]), RecordedClient(golden)),
                   indent=1, sort_keys=True) + "\n")
```

- [ ] **Step 3: Add the golden test** to `tests/test_golden_board.py`:

```python
@pytest.mark.golden
def test_the_golden_board_serves_the_recorded_plan_route(golden_run):
    """v17f §1 part 2: the board's plan route, byte for byte, over the run
    the module fixture already made. Recorded on main's code before the
    served plan moved; never re-recorded inside v17f."""
    expected = json.loads((gc.GOLDEN_DIR / gc.EXPECTED_DIR / "plan.json").read_text())
    served = gc.plan_route(Path(golden_run["cwd"]), int(golden_run["header"]["gw"]))
    assert served == expected
```

(`Path` is already imported there via `REPO = Path(...)`; check the import block.)

- [ ] **Step 4: Record the file** with a scratchpad script (not committed):

```python
# scratchpad/record_plan.py — run from the repo root with .venv/bin/python
import json, tempfile
from pathlib import Path
from tests import golden_client as gc
root = Path(tempfile.mkdtemp(prefix="golden-plan-"))
gc.build_scratch_tree(root, gc._repo_root())
advice, _ = gc.run_golden(root)
body = gc.plan_route(root, int(advice["gw"]))
out = gc.GOLDEN_DIR / gc.EXPECTED_DIR / "plan.json"
out.write_text(json.dumps(body, indent=1, sort_keys=True) + "\n")
print(out, len(body["weeks"]), body["bank"], body["objective"] is not None)
```

Expected: `6 weeks`, a numeric bank, `objective is not None` is `True` (the golden's restraint disagrees: `agrees: False`).

- [ ] **Step 5: Run the new golden test once** — `.venv/bin/pytest -q tests/test_golden_board.py -k recorded_plan_route` — Expected: 1 passed (about three minutes).

- [ ] **Step 6: Commit** `test(v17f): record GET /api/plan/4 over the golden board before the served plan moves; plan_route and the parity test; spec amendments` staging the spec, `tests/golden_client.py`, `tests/test_golden_board.py`, `tests/data/golden_board/expected/plan.json`.

---

### Task 1: the models, the moved pool readers, the wire exports

**Files:**
- Create: `src/gaffer/served.py`
- Modify: `src/gaffer/web/schemas.py:1393-1452` (delete `PlanMoveTrace`, `PlanWeekTrace`; import and `WIRE_EXPORTS`)
- Modify: `scripts/gen_types.py:99-107` (`OPTIONAL_ON_THE_WIRE`), `:232-243` (`_models`)
- Modify: `frontend/src/schemas.json`, `frontend/src/types.generated.ts` (regenerated)
- Create: `tests/test_served_plan.py`

- [ ] **Step 1: Write the failing tests** in `tests/test_served_plan.py`:

```python
"""v17f — the served plan, owned once
(specs/2026-09-08-v17f-served-plan-design.md)."""
from __future__ import annotations

import json
import math

import pandas as pd
import pytest

from gaffer.artifacts import POOL_COLS


def _pool(rows=((100, "In", "MID", 80, 78, 6.0), (200, "Out", "MID", 75, 74, 4.0))):
    out = [{"code": c, "name": n, "position": p, "team_code": 1, "cost": cost,
            "sell": sell, "owned": c == 200, "gw": g, "ep_raw": ep}
           for c, n, p, cost, sell, ep in rows for g in (5, 6, 7)]
    return pd.DataFrame(out, columns=POOL_COLS)


# --- the models ---------------------------------------------------------

def test_the_models_are_frozen_and_ignore_keys_they_do_not_know():
    from gaffer.served import ServedMove

    move = ServedMove.model_validate({"code": 1, "name": "A", "position": "MID",
                                      "ep": 5.0, "p_haul": 0.3})
    assert move.model_dump(exclude_unset=True) == {"code": 1, "name": "A",
                                                   "position": "MID", "ep": 5.0}
    with pytest.raises(Exception):
        move.price = 1.0          # frozen


def test_a_nameless_move_is_named_by_its_code():
    from gaffer.served import ServedMove

    assert ServedMove.model_validate({"code": 7}).name == "7"


def test_a_captain_that_cannot_name_a_player_is_none_and_the_plan_stands():
    from gaffer.served import ServedPlan

    plan = ServedPlan.model_validate({"gw": 5, "captain": {"name": "Salah"},
                                      "vice": "not a dict"})
    assert plan.captain is None and plan.vice is None and plan.gw == 5


def test_plan_by_gw_keyed_by_gameweek_loads_by_its_values():
    from gaffer.served import ServedPlan

    plan = ServedPlan.model_validate({"gw": 5, "plan_by_gw": {
        "5": {"gw": 5, "hits": 0}, "6": {"gw": 6, "hits": 1}}})
    assert [w.gw for w in plan.plan_by_gw] == [5, 6]


def test_a_gap_that_is_not_a_number_is_none_and_not_zero():
    from gaffer.served import ServedAlternative

    assert ServedAlternative.model_validate({"gap": "abc"}).gap is None
    assert ServedAlternative.model_validate({"gap": -0.4}).gap == -0.4


def test_a_restraint_default_invents_no_hit_price():
    """v17b §3.3: ``hit_cost`` is not invented; readers fall back to the
    config's default."""
    from gaffer.served import ServedRestraint

    assert ServedRestraint().hit_cost is None


def test_a_file_that_is_not_the_shape_advise_writes_fails_to_validate():
    from pydantic import ValidationError

    from gaffer.served import ServedPlan

    with pytest.raises(ValidationError):
        ServedPlan.model_validate({"gw": 5, "hits": "one"})
    with pytest.raises(ValidationError):
        ServedPlan.model_validate({"gw": 5, "plan_by_gw": ["not a week"]})


# --- the pool readers, moved from the router -----------------------------

def test_pool_prices_read_cost_and_sell_in_millions():
    from gaffer.served import pool_prices

    buy, sell = pool_prices(_pool())
    assert buy == {100: 8.0, 200: 7.5} and sell == {100: 7.8, 200: 7.4}


def test_a_pool_with_no_sell_column_prices_only_the_buys():
    from gaffer.served import pool_prices

    buy, sell = pool_prices(_pool().drop(columns=["sell"]))
    assert buy == {100: 8.0, 200: 7.5} and sell == {}


def test_a_nan_or_non_numeric_price_leaves_that_side_unpriced():
    from gaffer.served import pool_prices

    pool = _pool()
    pool["sell"] = pool["sell"].astype(float)
    pool.loc[pool["code"] == 200, "sell"] = float("nan")
    pool["cost"] = "cheap"
    buy, sell = pool_prices(pool)
    assert buy == {} and sell == {100: 7.8}


def test_a_pool_with_no_code_column_prices_nothing():
    from gaffer.served import pool_prices, trace_inputs

    assert pool_prices(_pool().drop(columns=["code"])) == ({}, {})
    assert trace_inputs(_pool().drop(columns=["code"])) == ({}, {}, {})


def test_trace_inputs_keep_a_nan_ep_out_rather_than_as_zero():
    from gaffer.served import trace_inputs

    pool = _pool()
    pool.loc[(pool["code"] == 100) & (pool["gw"] == 6), "ep_raw"] = float("nan")
    ep_by, positions, names = trace_inputs(pool)
    assert (100, 6) not in ep_by and ep_by[(100, 5)] == 6.0
    assert positions[100] == "MID" and names[200] == "Out"


def test_chip_and_theta_lookups_read_only_played_rows():
    from gaffer.served import chip_by_gw, thresholds

    table = [{"chip": "bboost", "gw": 6, "play_now": True, "threshold": 2.5},
             {"chip": "wildcard", "gw": None, "play_now": True, "threshold": 1.0},
             {"chip": "freehit", "gw": 7, "play_now": False, "threshold": 0.0},
             {"chip": "3xc", "gw": 8, "play_now": True, "threshold": "abc"}]
    assert chip_by_gw(table) == {6: "bboost", 8: "3xc"}
    assert thresholds(table) == {6: 2.5}
    assert chip_by_gw("nonsense") == {} and thresholds(None) == {}


# --- the wire exports ---------------------------------------------------

def test_schemas_re_exports_the_served_models_and_the_generator_emits_them():
    from gaffer import served
    from gaffer.web import schemas
    from scripts.gen_types import _models

    names = {m.__name__ for m in schemas.WIRE_EXPORTS}
    assert names == {"PlanMoveTrace", "PlanWeekTrace", "ServedMove", "ServedWeek",
                     "ServedStep", "ServedRestraint", "ServedObjective",
                     "ServedAlternative", "ServedPlan"}
    assert schemas.PlanWeekTrace is served.PlanWeekTrace
    emitted = {name for name, _ in _models()}
    assert names <= emitted
```

- [ ] **Step 2: Run them** — `.venv/bin/pytest -q tests/test_served_plan.py` — Expected: every test fails with `ModuleNotFoundError: gaffer.served` (or `ImportError`).

- [ ] **Step 3: Create `src/gaffer/served.py`**:

```python
"""The served plan, owned once (v17f §4,
specs/2026-09-08-v17f-served-plan-design.md).

One value answers "what does the user see for GW N": the moves, the weeks
with their prices, banks and traces, the restraint walk and the objective's
own week. ``advise`` builds it and writes it whole; ``artifacts.served_plan``
reads it back and, for a file written before v17f, fills the same fields
through the same functions. Everything here is a value in and a value out.

The four pool readers at the bottom moved from ``web/routers/plan.py`` with
their docstrings: the pool parquet is written by whatever run wrote the
advice and drifts with it, so they still degrade a column they cannot
read rather than raise.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _Frozen(BaseModel):
    """Frozen, and blind to keys it does not declare: the advice JSON
    carries more than the plan (chip table, threats, scenarios), and a
    key a future writer adds must not break this reader."""

    model_config = ConfigDict(frozen=True, extra="ignore")


class PlanMoveTrace(_Frozen):
    """One transfer, priced against the objective's own terms (v12 W5 §6.5).

    Not a counterfactual. ``ep_gain`` is the decayed expected-points
    difference of a position-matched swap over the rest of the horizon — the
    objective's own arithmetic at the plan the solver returned — and **not**
    "the plan is this much worse without this move", which would need a
    re-solve. ``None`` everywhere means unknown, never a measured zero.
    """

    buy_code: int | None = None
    buy_name: str = ""
    sell_code: int | None = None
    sell_name: str = ""
    ep_gain: float | None = None
    lambda_tilt: float | None = None
    note: str = ""


class PlanWeekTrace(_Frozen):
    """One planned week's charges. Four of them are week-level on purpose:
    a week with two transfers and one hit cannot attribute the hit to one of
    them, and splitting it would be arithmetic dressed as a finding.

    Three of the objective's terms are **not** here — the XI, captain and vice
    weightings and the bench seats (``milp.py:813-835``, including
    ``_decision_scales``' per-week autosub scales). They price the whole squad
    rather than a swap, so these numbers do not sum to ``expected_pts`` and
    are not meant to. The board's caption says so in the same words.
    """

    gw: int
    moves: list[PlanMoveTrace] = Field(default_factory=list)
    ep_gain: float | None = None
    hit_cost: float = 0.0
    ft_used: int = 0
    ft_after: int = 0
    ft_use_penalty: float = 0.0
    ft_shadow: float | None = None
    ft_basis: Literal["flat", "lambda"] = "flat"
    bank_value: float | None = None
    theta: float | None = None
    price_charge: float | None = None
    note: str = ""


def _codeable(value) -> bool:
    if not isinstance(value, dict) or value.get("code") is None:
        return False
    try:
        return int(value["code"]) >= 0
    except (TypeError, ValueError):
        return False


class ServedMove(_Frozen):
    """A player on a move or in the XI, in ``advise._named``'s shape plus
    the price the pool gives him (millions; ``None`` when it cannot) and
    the decorations advise adds to a served buy or sell."""

    code: int
    name: str = ""
    position: str = ""
    ep: float = 0.0
    price: float | None = None
    tag: str | None = None
    frequency: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _named_by_code(cls, data):
        if isinstance(data, dict) and data.get("name") is None and data.get("code") is not None:
            return {**data, "name": str(data["code"])}
        return data


class ServedWeek(_Frozen):
    gw: int
    hits: int = 0
    hit_cost: int = 0
    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    expected_pts: float = 0.0
    chip: str | None = None
    bank: float | None = None
    """What is left after this week's moves, in millions. ``None`` means
    unknown — some move in this week or an earlier one had no price — and
    never 0.0, which is "fully invested"."""
    trace: PlanWeekTrace | None = None


class ServedStep(_Frozen):
    """One step of the ladder's restraint walk (v16 §3), as the ladder
    writes it, with v17b's served sentence."""

    below: str
    above: str
    share: float
    taken: bool
    reason: str = ""
    reason_kind: str = ""
    line: str | None = None


class ServedRestraint(_Frozen):
    chosen: str | None = None
    label: str | None = None
    bar: float | None = None
    steps: list[ServedStep] = Field(default_factory=list)
    agrees: bool = True
    note: str | None = None
    hit_cost: int | None = None
    """Not invented (v17b §3.3): a reader of a block that carries none
    falls back to the config's default."""
    line: str | None = None


class ServedObjective(_Frozen):
    """The solver's own week one, kept beside the served plan (v16 §4),
    and the same week priced, banked and traced under ``week`` so the
    board's objective column is carried rather than rebuilt."""

    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    hits: int = 0
    expected_pts: float = 0.0
    line: str | None = None
    week: ServedWeek | None = None


def _number_or_none(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out


class ServedAlternative(_Frozen):
    """A plan the solver ranked behind the recommended one (v12 W3 §4.3),
    under the advice's own ``alternative_plans`` key and shape."""

    gap: float | None = None
    plan_by_gw: list[ServedWeek] = Field(default_factory=list)

    @field_validator("gap", mode="before")
    @classmethod
    def _signed_or_unknown(cls, value):
        # Never 0.0 for unreadable: zero is "exactly level with the
        # recommendation", a real and different claim.
        out = _number_or_none(value)
        return None if out is None else round(out, 2)

    @field_validator("plan_by_gw", mode="before")
    @classmethod
    def _weeks_however_written(cls, raw):
        return list(raw.values()) if isinstance(raw, dict) else raw


class ServedPlan(_Frozen):
    """Field names are the advice JSON's own keys: ``model_dump`` is the
    write and ``model_validate(advice_dict)`` is the read."""

    gw: int
    generated_at: str | None = None
    bank: float | None = None
    """The bank before the horizon's first move, in millions; ``None``
    when the solve state carried no usable figure, never 0.0."""
    buys: list[ServedMove] = Field(default_factory=list)
    sells: list[ServedMove] = Field(default_factory=list)
    hits: int = 0
    xi: list[ServedMove] = Field(default_factory=list)
    bench: list[ServedMove] = Field(default_factory=list)
    captain: ServedMove | None = None
    vice: ServedMove | None = None
    captain_note: str | None = None
    expected_pts: float = 0.0
    plan_by_gw: list[ServedWeek] = Field(default_factory=list)
    objective: ServedObjective | None = None
    restraint: ServedRestraint | None = None
    alternative_plans: list[ServedAlternative] = Field(default_factory=list)

    @field_validator("plan_by_gw", mode="before")
    @classmethod
    def _weeks_however_written(cls, raw):
        # An older writer keyed the horizon by gameweek.
        return list(raw.values()) if isinstance(raw, dict) else raw

    @field_validator("captain", "vice", mode="before")
    @classmethod
    def _armband_or_none(cls, raw):
        # A captain the artifact cannot name is a missing armband, not a
        # missing plan.
        return raw if _codeable(raw) else None


# --- the pool readers, moved whole from routers/plan.py (v17f §4) ---------

def _int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float(value, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if out != out else out          # NaN


def _price(value) -> float | None:
    """Tenths of a million as millions, or ``None`` if it is not a number."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else round(out / 10, 1)          # NaN


def pool_prices(pool) -> tuple[dict[int, float], dict[int, float]]:
    """``({code: buy price}, {code: sell value})`` in millions.

    A column the pool does not carry, and a value that is not a number, leave
    that side unpriced. The timeline renders a move with no price; it cannot
    render a 500.
    """
    if getattr(pool, "columns", None) is None or "code" not in pool.columns:
        return {}, {}
    one = pool.drop_duplicates("code")
    buy: dict[int, float] = {}
    sell: dict[int, float] = {}
    for row in one.itertuples():
        code = _int(getattr(row, "code", None), -1)
        if code < 0:
            continue
        for column, out in (("cost", buy), ("sell", sell)):
            price = _price(getattr(row, column, None))
            if price is not None:
                out[code] = price
    return buy, sell


def trace_inputs(pool) -> tuple[dict, dict, dict]:
    """``({(code, gw): ep}, {code: position}, {code: name})`` off the pool.

    A pool with no ``ep_raw`` column yields an empty EP table, which the
    trace reports as "not in the pool" per move rather than as a zero.
    """
    columns = getattr(pool, "columns", None)
    if columns is None or "code" not in columns:
        return {}, {}, {}
    ep_by: dict = {}
    positions: dict = {}
    player_names: dict = {}
    has_ep = "ep_raw" in columns
    for row in pool.itertuples():
        code = _int(getattr(row, "code", None), -1)
        if code < 0:
            continue
        positions.setdefault(code, str(getattr(row, "position", "")))
        player_names.setdefault(code, str(getattr(row, "name", code)))
        if has_ep:
            # A NaN is not a 0.0: leaving the key out is what makes the
            # trace say "not in the pool".
            ep = _float(getattr(row, "ep_raw", None), float("nan"))
            if ep == ep:
                ep_by[(code, _int(getattr(row, "gw", None), -1))] = ep
    return ep_by, positions, player_names


def chip_by_gw(chip_table) -> dict[int, str]:
    """``{gw: chip}`` for chips this run actually recommended playing."""
    out: dict[int, str] = {}
    if not isinstance(chip_table, list):
        return out
    for row in chip_table:
        # A chip the solver could not place writes the key with a null.
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None:
            continue
        out[_int(row["gw"], -1)] = str(row.get("chip"))
    out.pop(-1, None)
    return out


def thresholds(chip_table) -> dict[int, float]:
    """``{gw: θ}`` for the chips this run recommends playing.

    A threshold that is not a number is dropped rather than defaulted. 0.0 is
    a real θ — "play it in any week that is not actively worse" — so a string
    where a number belongs must not be served as the most permissive threshold
    the model can have.
    """
    out: dict[int, float] = {}
    if not isinstance(chip_table, list):
        return out
    for row in chip_table:
        if not (isinstance(row, dict) and row.get("play_now")):
            continue
        if row.get("gw") is None or row.get("threshold") is None:
            continue
        gw_key = _int(row["gw"], -1)
        theta = _float(row["threshold"], float("nan"))
        if gw_key < 0 or theta != theta:
            continue
        out[gw_key] = theta
    return out


def price_falls(state) -> tuple[bool, dict[int, float]]:
    """``(price_timing is on, {code: p_fall_tonight})`` for the owned squad.

    The same reader the objective's price-timing term uses (W2 §3.4), called
    the same way — so the charge the board prints is not a second estimate
    computed from the same log by slightly different arithmetic. Read at
    write time by advise (v17f §2.2), so a fresh file carries what the
    solve saw; read again only for a file written before v17f, where it
    is a present-tense read and the week note says so.

    ``price_timing`` off means the objective carried **no such term**, so
    the trace reports ``None`` and says so rather than printing a zero. A
    table that will not read is also ``None`` — an unknown, which is not a
    zero chance of a fall.
    """
    from gaffer.config import config_in_force
    from gaffer.price_timing import owned_price_falls

    try:
        if not config_in_force().price_timing:
            return False, {}
        owned = [int(c) for c in getattr(state, "owned_codes", []) or []]
        return True, {int(k): float(v)
                      for k, v in (owned_price_falls(owned) or {}).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"plan trace: price falls unreadable ({exc})")
        return True, {}
```

(The pure passes `decorated`, `with_alternatives`, `priced`, `charged`, `banked`, `traced`, `completed` are Task 2. Leave the module ending at `price_falls`.)

- [ ] **Step 4: Re-export from `schemas.py`.** Delete the `PlanMoveTrace` and `PlanWeekTrace` classes (lines 1393–1452) and, in the import block at the top, add:

```python
from gaffer.served import (PlanMoveTrace, PlanWeekTrace, ServedAlternative,  # noqa: F401
                           ServedMove, ServedObjective, ServedPlan,
                           ServedRestraint, ServedStep, ServedWeek)

WIRE_EXPORTS = (PlanMoveTrace, PlanWeekTrace, ServedMove, ServedWeek, ServedStep,
                ServedRestraint, ServedObjective, ServedAlternative, ServedPlan)
"""Models defined in :mod:`gaffer.served` and served on the wire (v17f §2.9):
``scripts/gen_types.py`` emits a model named here as if it were defined in
this file, so the served plan is typed once and the frontend takes the
generated names."""
```

Put `WIRE_EXPORTS` right after the imports, before the first model. Keep `PlanGw.trace: PlanWeekTrace | None` as is; it now refers to the import.

- [ ] **Step 5: Teach the generator.** In `scripts/gen_types.py`, `_models()` becomes:

```python
def _models():
    from pydantic import BaseModel

    from gaffer.web import schemas

    out = []
    exported = set(getattr(schemas, "WIRE_EXPORTS", ()))
    for name, obj in sorted(vars(schemas).items()):
        if (isinstance(obj, type) and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and (obj.__module__ == schemas.__name__ or obj in exported)):
            out.append((name, obj))
    return out
```

and add to `OPTIONAL_ON_THE_WIRE`:

```python
    ("ServedMove", "tag"):
        "Advise tags a served buy and nothing else; the write is "
        "model_dump(exclude_unset=True), so an XI or sell move carries no key.",
    ("ServedMove", "frequency"):
        "Present only on a served move the scenario sweep saw; absent with "
        "[scenarios] n = 0, and never on the XI.",
```

- [ ] **Step 6: Regenerate** — `cd frontend && npm run types && npm run types -- --check` — Expected: the check exits 0; `git diff --stat frontend/src/schemas.json frontend/src/types.generated.ts` shows both changed. Then `npx tsc --noEmit` — Expected: clean (the hand-written `Restraint`/`Objective` still exist and do not clash with `ServedRestraint`/`ServedObjective`).

- [ ] **Step 7: Run the tests** — `.venv/bin/pytest -q tests/test_served_plan.py tests/test_v12_w5_plan_trace.py tests/test_web_plan.py` — Expected: `test_served_plan.py` all pass; the other two files unchanged and green (the router still imports `PlanWeekTrace` from `schemas`). Then `cd frontend && npx vitest run` — Expected: green; `types.test.ts` passes (no hand-written name collides with a generated one).

- [ ] **Step 8: Full suite** — `.venv/bin/pytest -q` — Expected: green (skips on the golden marker are fine here; the golden gate is Task 9).

- [ ] **Step 9: Commit** `feat(v17f): gaffer.served — the frozen ServedPlan models, the pool readers moved from the plan router, WIRE_EXPORTS and the generator's re-export rule; types regenerated` staging `src/gaffer/served.py`, `src/gaffer/web/schemas.py`, `scripts/gen_types.py`, `frontend/src/schemas.json`, `frontend/src/types.generated.ts`, `tests/test_served_plan.py`.

---

### Task 2: the pure passes, and the loader

**Files:**
- Modify: `src/gaffer/served.py` (append)
- Modify: `src/gaffer/artifacts.py:413-420` (`load_advice`) and after it
- Modify: `tests/test_served_plan.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_served_plan.py`):

```python
# --- the passes ---------------------------------------------------------

P = {"code": 100, "name": "In", "position": "MID", "ep": 6.0}
S = {"code": 200, "name": "Out", "position": "MID", "ep": 4.0}


def _state(pool=None, bank=15, opt=None, **kw):
    from gaffer.artifacts import SolveState

    return SolveState(pool=_pool() if pool is None else pool, bank=bank,
                      opt={"hit_cost": 4, "decay": 0.5, "ft_value": 1.5,
                           "itb_value": 0.05, "decision_priors": False,
                           **(opt or {})},
                      generated_at="2026-09-01T09:00:00+00:00", deadline="",
                      owned_codes=[200], gws=[5, 6, 7], gw=5, mode="weekly",
                      free_transfers=1, lam=0.0, league_eo={}, cover=None,
                      avail_by_gw={}, **kw)


def _week(gw, buys=(), sells=(), hits=0):
    return {"gw": gw, "hits": hits, "buys": list(buys), "sells": list(sells),
            "expected_pts": 60.0}


def _plan(weeks, **kw):
    from gaffer.served import ServedPlan

    return ServedPlan.model_validate({"gw": 5, "plan_by_gw": weeks, **kw})


def test_priced_prices_buys_at_cost_and_sells_at_value_and_the_xi_at_cost():
    from gaffer.served import priced

    plan = _plan([_week(5, buys=[P], sells=[S])], buys=[P], sells=[S], xi=[P],
                 bench=[S], captain=P, vice=S)
    out = priced(plan, {100: 8.0, 200: 7.5}, {100: 7.8, 200: 7.4})
    week = out.plan_by_gw[0]
    assert (week.buys[0].price, week.sells[0].price) == (8.0, 7.4)
    assert (out.buys[0].price, out.sells[0].price) == (8.0, 7.4)
    assert (out.xi[0].price, out.bench[0].price) == (8.0, 7.5)
    assert (out.captain.price, out.vice.price) == (8.0, 7.5)
    assert plan.plan_by_gw[0].buys[0].price is None      # a value, not a mutation


def test_a_move_the_pool_cannot_price_is_none():
    from gaffer.served import priced

    out = priced(_plan([_week(5, buys=[{"code": 999, "name": "Ghost"}])]), {}, {})
    assert out.plan_by_gw[0].buys[0].price is None


def test_charged_prices_the_hits_and_lands_the_chip_on_its_week():
    from gaffer.served import charged

    out = charged(_plan([_week(5, hits=1), _week(6)]), hit_cost=4, chips={6: "bboost"})
    assert [w.hit_cost for w in out.plan_by_gw] == [4, 0]
    assert [w.chip for w in out.plan_by_gw] == [None, "bboost"]


def test_banked_runs_the_bank_forward_and_blanks_from_the_first_unpriced_move():
    from gaffer.served import banked, priced

    plan = priced(_plan([_week(5, sells=[S]), _week(6, buys=[P]),
                         _week(7, buys=[{"code": 999, "name": "Ghost"}]), _week(8)]),
                  {100: 8.0}, {200: 7.4})
    out = banked(plan, 1.5)
    assert out.bank == 1.5
    assert [w.bank for w in out.plan_by_gw] == [8.9, 0.9, None, None]


def test_banked_keeps_a_week_with_no_moves_and_a_none_start_is_never_zero():
    from gaffer.served import banked

    assert banked(_plan([_week(5)]), 1.5).plan_by_gw[0].bank == 1.5
    out = banked(_plan([_week(5)]), None)
    assert out.bank is None and out.plan_by_gw[0].bank is None


def test_banked_runs_the_objective_week_and_every_alternative_from_the_start():
    from gaffer.served import banked, priced

    plan = priced(_plan([_week(5, sells=[S])],
                        objective={"buys": [P], "sells": [], "hits": 1,
                                   "expected_pts": 60.0,
                                   "week": _week(5, buys=[P], hits=1)},
                        alternative_plans=[{"gap": 0.4, "plan_by_gw": [_week(5, buys=[P])]}]),
                  {100: 8.0}, {200: 7.4})
    out = banked(plan, 15.0)
    assert out.plan_by_gw[0].bank == 22.4
    assert out.objective.week.bank == 7.0
    assert out.alternative_plans[0].plan_by_gw[0].bank == 7.0


def test_traced_hangs_a_trace_on_the_served_weeks_and_the_objective_and_never_an_alternative():
    from gaffer.served import banked, priced, traced

    plan = banked(priced(_plan([_week(5, buys=[P], sells=[S], hits=1), _week(6)],
                               objective={"buys": [P], "sells": [S], "hits": 1,
                                          "expected_pts": 60.0,
                                          "week": _week(5, buys=[P], sells=[S], hits=1)},
                               alternative_plans=[{"gap": 0.4,
                                                   "plan_by_gw": [_week(6, buys=[P], sells=[S])]}]),
                         {100: 8.0}, {200: 7.4}), 15.0)
    out = traced(plan, state=_state(), thresholds={}, ft_lambda=None,
                 price_timing=False, price_fall={})
    assert out.plan_by_gw[0].trace is not None
    assert out.plan_by_gw[0].trace.moves[0].buy_code == 100
    assert out.plan_by_gw[0].trace.hit_cost == 4.0
    assert out.plan_by_gw[1].trace is not None          # a week that does nothing still has one
    assert out.objective.week.trace is not None
    assert out.alternative_plans[0].plan_by_gw[0].trace is None


def test_a_trace_that_throws_costs_the_trace_and_not_the_plan(monkeypatch, capsys):
    from gaffer.served import traced

    def boom(*a, **k):
        raise ValueError("nope")

    monkeypatch.setattr("gaffer.trace.trace_plan", boom)
    out = traced(_plan([_week(5, buys=[P], sells=[S])]), state=_state(),
                 thresholds={}, ft_lambda=None, price_timing=False, price_fall={})
    assert out.plan_by_gw[0].expected_pts == 60.0
    assert out.plan_by_gw[0].trace is None
    assert "trace" in out.plan_by_gw[0].model_fields_set     # written as None, not left unset
    assert "plan trace unavailable" in capsys.readouterr().out


def test_a_chip_week_is_charged_what_the_base_plan_paid_and_the_note_says_so():
    from gaffer.served import charged, traced

    plan = charged(_plan([_week(5, buys=[P], sells=[S], hits=1)]), hit_cost=4,
                   chips={5: "wildcard"})
    out = traced(plan, state=_state(), thresholds={5: 1.0}, ft_lambda=None,
                 price_timing=False, price_fall={})
    trace = out.plan_by_gw[0].trace
    assert trace.hit_cost == 4.0 and trace.theta == 1.0
    assert "a wildcard is recommended this week" in trace.note


def test_completed_is_the_one_pass_over_a_solve_state(monkeypatch):
    from gaffer.served import completed

    monkeypatch.setattr("gaffer.served.price_falls", lambda state: (True, {200: 0.8}))
    plan = _plan([_week(5, buys=[P], sells=[S], hits=1), _week(6, buys=[P], sells=[S])],
                 objective={"buys": [P], "sells": [S], "hits": 1, "expected_pts": 60.0,
                            "week": _week(5, buys=[P], sells=[S], hits=1)})
    out = completed(plan, state=_state(), chip_table=[
        {"chip": "bboost", "gw": 6, "play_now": True, "threshold": 2.0}])
    assert out.generated_at == "2026-09-01T09:00:00+00:00" and out.bank == 1.5
    week = out.plan_by_gw[0]
    assert (week.buys[0].price, week.sells[0].price, week.hit_cost) == (8.0, 7.4, 4)
    assert week.bank == 0.9 and week.trace is not None
    assert out.plan_by_gw[1].bank == 0.3
    assert out.plan_by_gw[1].chip == "bboost" and out.plan_by_gw[1].trace.theta == 2.0
    assert out.plan_by_gw[1].trace.price_charge == pytest.approx(0.8 * 0.1 * 0.05)
    assert out.objective.week.bank == 0.9 and out.objective.week.trace is not None


def test_decorated_tags_the_served_buys_and_carries_frequencies_only_where_seen():
    from gaffer.served import decorated

    plan = _plan([], buys=[P], sells=[S], xi=[P])
    out = decorated(plan, tags={100: "attack"}, frequencies={("buy", 100): 0.7})
    assert out.buys[0].tag == "attack" and out.buys[0].frequency == 0.7
    assert out.sells[0].frequency is None and "tag" not in out.sells[0].model_fields_set
    assert "tag" not in out.xi[0].model_fields_set
    dumped = out.model_dump(exclude_unset=True)
    assert "tag" not in dumped["xi"][0] and "tag" not in dumped["sells"][0]


def test_with_alternatives_types_the_rows_advise_built():
    from gaffer.served import with_alternatives

    out = with_alternatives(_plan([]), [{"gap": 0.4, "plan_by_gw": [_week(5, buys=[P])]},
                                        {"gap": None, "plan_by_gw": {"5": _week(5)}}])
    assert [a.gap for a in out.alternative_plans] == [0.4, None]
    assert out.alternative_plans[1].plan_by_gw[0].gw == 5
    assert with_alternatives(_plan([]), None).alternative_plans == []


# --- the loader ---------------------------------------------------------

def _write_state(bank=15):
    from gaffer.artifacts import save_solve_state

    save_solve_state(_state(bank=bank))


def test_the_loader_backfills_a_file_written_before_v17f_from_its_solve_state(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    _write_state()
    Path("reports/gw5-advice.json").write_text(json.dumps({
        "gw": 5, "deadline": "x", "buys": [P], "sells": [S], "hits": 1,
        "captain": P, "vice": S, "expected_pts": 60.0,
        "chip_table": [{"chip": "bboost", "gw": 6, "play_now": True}],
        "plan_by_gw": [_week(5, buys=[P], sells=[S], hits=1), _week(6)],
        "alternative_plans": [{"gap": 0.4, "plan_by_gw": [_week(6, buys=[P], sells=[S])]}]}))
    plan = served_plan(5)
    assert plan.generated_at == "2026-09-01T09:00:00+00:00" and plan.bank == 1.5
    assert plan.plan_by_gw[0].bank == 0.9 and plan.plan_by_gw[0].trace is not None
    assert plan.plan_by_gw[1].chip == "bboost"
    assert plan.alternative_plans[0].plan_by_gw[0].buys[0].price == 8.0
    assert plan.alternative_plans[0].plan_by_gw[0].trace is None
    assert plan.captain.price == 8.0


def test_the_loader_serves_a_v17f_file_as_written_without_the_solve_state(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()                        # no solve state on disk
    Path("reports/gw5-advice.json").write_text(json.dumps({
        "gw": 5, "generated_at": "2026-09-02T00:00:00+00:00", "bank": 2.5,
        "buys": [{**P, "price": 8.0}], "plan_by_gw": [
            {**_week(5, buys=[{**P, "price": 8.0}]), "hit_cost": 0, "chip": None,
             "bank": -5.5, "trace": None}]}))
    plan = served_plan(5)
    assert plan.bank == 2.5 and plan.plan_by_gw[0].bank == -5.5
    assert plan.plan_by_gw[0].trace is None


def test_a_missing_advice_is_the_same_sentence_load_advice_raises(tmp_path, monkeypatch):
    from gaffer.artifacts import served_plan
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError, match="gaffer advise"):
        served_plan(9)


def test_a_file_that_will_not_validate_is_a_gaffer_error_naming_the_field(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import served_plan
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    Path("reports/gw5-advice.json").write_text(json.dumps({"gw": 5, "hits": "one"}))
    with pytest.raises(GafferError, match="hits"):
        served_plan(5)


def test_advice_gws_enumerates_ascending_and_ignores_a_stem_that_is_not_a_number(tmp_path, monkeypatch):
    from pathlib import Path

    from gaffer.artifacts import advice_gws, advice_path

    monkeypatch.chdir(tmp_path)
    assert advice_gws() == []
    Path("reports").mkdir()
    for name in ("gw7-advice.json", "gw5-advice.json", "gwX-advice.json", "gw6.json"):
        Path("reports", name).write_text("{}")
    assert advice_gws() == [5, 7]
    assert advice_path(5) == Path("reports/gw5-advice.json")
```

- [ ] **Step 2: Run them** — `.venv/bin/pytest -q tests/test_served_plan.py -k "priced or charged or banked or traced or completed or decorated or with_alternatives or loader or advice_gws or validate or missing"` — Expected: fail with `ImportError` (`cannot import name 'priced'` …, `cannot import name 'served_plan'`).

- [ ] **Step 3: Append the passes to `src/gaffer/served.py`**:

```python
# --- the passes: a value in, a value out (v17f §4) -------------------------

def decorated(plan: ServedPlan, *, tags: dict[int, str],
              frequencies: dict[tuple[str, int], float]) -> ServedPlan:
    """The tags and sweep frequencies on the *served* moves (v16 §4): a tag
    for every buy ``tags`` names, a frequency for a buy or sell the sweep
    saw. A move with neither is left unset, so the write carries no null
    for it."""
    def one(kind: str, move: ServedMove) -> ServedMove:
        update: dict = {}
        if kind == "buy" and move.code in tags:
            update["tag"] = tags[move.code]
        if (kind, move.code) in frequencies:
            update["frequency"] = frequencies[(kind, move.code)]
        return move.model_copy(update=update) if update else move
    return plan.model_copy(update={
        "buys": [one("buy", m) for m in plan.buys],
        "sells": [one("sell", m) for m in plan.sells]})


def with_alternatives(plan: ServedPlan, rows) -> ServedPlan:
    """The alternatives typed from the rows advise built, or from the file's
    ``alternative_plans`` on a backfill. ``None`` and ``[]`` are the same
    empty strip."""
    return plan.model_copy(update={
        "alternative_plans": [ServedAlternative.model_validate(r) for r in (rows or [])]})


def _priced_moves(moves, prices: dict[int, float]) -> list[ServedMove]:
    return [m.model_copy(update={"price": prices.get(m.code)}) for m in moves]


def _priced_week(week: ServedWeek, buy, sell) -> ServedWeek:
    return week.model_copy(update={"buys": _priced_moves(week.buys, buy),
                                   "sells": _priced_moves(week.sells, sell)})


def _each_week(plan: ServedPlan, fn) -> ServedPlan:
    """``fn(weeks) -> weeks`` over the served weeks, the objective's week
    (as a one-week list) and every alternative's weeks."""
    update: dict = {"plan_by_gw": fn(plan.plan_by_gw),
                    "alternative_plans": [a.model_copy(update={"plan_by_gw": fn(a.plan_by_gw)})
                                          for a in plan.alternative_plans]}
    if plan.objective is not None and plan.objective.week is not None:
        update["objective"] = plan.objective.model_copy(
            update={"week": fn([plan.objective.week])[0]})
    return plan.model_copy(update=update)


def priced(plan: ServedPlan, buy: dict[int, float], sell: dict[int, float]) -> ServedPlan:
    """Every move priced from the pool's two columns: buy price for an in,
    sell value for an out; the XI, bench and armband at buy price, as the
    board's head week always showed them. A code the pool cannot price is
    ``None``."""
    def moves(name, prices):
        return _priced_moves(getattr(plan, name), prices)

    out = _each_week(plan, lambda weeks: [_priced_week(w, buy, sell) for w in weeks])
    return out.model_copy(update={
        "buys": moves("buys", buy), "sells": moves("sells", sell),
        "xi": moves("xi", buy), "bench": moves("bench", buy),
        "captain": None if plan.captain is None else _priced_moves([plan.captain], buy)[0],
        "vice": None if plan.vice is None else _priced_moves([plan.vice], buy)[0]})


def charged(plan: ServedPlan, *, hit_cost: int, chips: dict[int, str]) -> ServedPlan:
    """The hit charge and the chip table's recommendation on every week."""
    return _each_week(plan, lambda weeks: [
        w.model_copy(update={"hit_cost": w.hits * hit_cost, "chip": chips.get(w.gw)})
        for w in weeks])


def _banked_weeks(weeks: list[ServedWeek], start: float | None) -> list[ServedWeek]:
    # v11 §F1: an unpriced move breaks the total permanently. Skipping it
    # would report a bank wrong by exactly that player's price with nothing
    # on the page to say so, and there is no later week at which the sum
    # re-synchronises.
    running = start
    out = []
    for week in weeks:
        moves = [*week.buys, *week.sells]
        if running is not None and all(m.price is not None for m in moves):
            # round(..., 1): every price is one decimal, and float drift over
            # a six-week horizon puts 0.8999999999999995 on the page.
            running = round(running + sum(m.price for m in week.sells)
                            - sum(m.price for m in week.buys), 1)
        else:
            running = None
        out.append(week.model_copy(update={"bank": running}))
    return out


def banked(plan: ServedPlan, start: float | None) -> ServedPlan:
    """The bank run forward from ``start`` (millions) over the served weeks,
    the objective's week and each alternative — one implementation, because
    the board prints their banks side by side."""
    return _each_week(plan, lambda weeks: _banked_weeks(weeks, start)).model_copy(
        update={"bank": start})


def _traced_weeks(weeks: list[ServedWeek], *, state, ep_by, positions, names,
                  thresholds, ft_lambda, price_timing, price_fall) -> list[ServedWeek]:
    from gaffer.league_mode import cover_from_eo
    from gaffer.trace import trace_plan

    opt = state.opt if isinstance(state.opt, dict) else {}
    hit_cost = _int(opt.get("hit_cost", 4), 4)
    # The moves' own names under the pool's: a move can name a player who
    # is not on the solver's candidate list.
    move_names = {m.code: m.name for w in weeks for m in (*w.buys, *w.sells)}
    # ``chip: None``, deliberately: ``plan_by_gw`` is the base solve, which
    # charged this week's transfers and ran the free-transfer recurrence,
    # and telling the trace a wildcard was played would report a charge that
    # was made as zero. θ still comes from the chip table; the note says so.
    traced = trace_plan(
        [{"gw": w.gw, "hits": w.hits, "buys": [m.code for m in w.buys],
          "sells": [m.code for m in w.sells], "chip": None} for w in weeks],
        gws=[int(g) for g in getattr(state, "gws", [])],
        ep_by=ep_by, positions=positions, names={**move_names, **names},
        decay=_float(opt.get("decay", 1.0), 1.0), hit_cost=hit_cost,
        ft_value=_float(opt.get("ft_value", 0.0)),
        itb_value=_float(opt.get("itb_value", 0.0)),
        free_transfers=_int(getattr(state, "free_transfers", 0)),
        ft_lambda=ft_lambda,
        ft_use_penalty=_float(opt.get("ft_use_penalty", 0.0)),
        lam=_float(getattr(state, "lam", 0.0)),
        # ``is not None``, not ``or {}``: an empty cover tilts nothing, and
        # ``or {}`` would report 0.0 for a term the objective applied.
        cover=(state.cover if getattr(state, "cover", None) is not None
               else cover_from_eo(getattr(state, "league_eo", {}) or {})),
        thresholds=thresholds, banks={w.gw: w.bank for w in weeks},
        price_timing=price_timing, price_fall=price_fall)
    out = []
    for week, one in zip(weeks, traced):
        payload = asdict(one)
        if week.chip:
            said = (f"a {week.chip} is recommended this week; these terms are "
                    f"the base plan's, which the solver returned without it")
            payload["note"] = "; ".join(part for part in (payload["note"], said) if part)
        out.append(week.model_copy(update={"trace": PlanWeekTrace(**payload)}))
    return out


def traced(plan: ServedPlan, *, state, thresholds: dict[int, float], ft_lambda,
           price_timing: bool, price_fall: dict[int, float]) -> ServedPlan:
    """The objective's own terms on the served weeks and on the objective's
    week (v12 W5 §6.5, v16 §4) — never on an alternative, which was returned
    by a different solve. A trace that throws costs the trace and not the
    plan: every week is written with ``trace=None`` and one line is printed."""
    ep_by, positions, names = trace_inputs(getattr(state, "pool", None))
    kw = dict(state=state, ep_by=ep_by, positions=positions, names=names,
              thresholds=thresholds, ft_lambda=ft_lambda,
              price_timing=price_timing, price_fall=price_fall)
    try:
        update: dict = {"plan_by_gw": _traced_weeks(plan.plan_by_gw, **kw)}
        if plan.objective is not None and plan.objective.week is not None:
            update["objective"] = plan.objective.model_copy(
                update={"week": _traced_weeks([plan.objective.week], **kw)[0]})
        return plan.model_copy(update=update)
    except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
        print(f"plan trace unavailable for GW{plan.gw}: {exc}")
        untraced = lambda weeks: [w.model_copy(update={"trace": None}) for w in weeks]  # noqa: E731
        update = {"plan_by_gw": untraced(plan.plan_by_gw)}
        if plan.objective is not None and plan.objective.week is not None:
            update["objective"] = plan.objective.model_copy(
                update={"week": untraced([plan.objective.week])[0]})
        return plan.model_copy(update=update)


def completed(plan: ServedPlan, *, state, chip_table) -> ServedPlan:
    """Prices, charges, chips, banks and traces off one solve state — the
    one pass advise runs at write time and ``artifacts.served_plan`` runs
    for a file written before v17f (§2.3). ``generated_at`` is the state's,
    so the two files that describe one run carry one stamp."""
    buy, sell = pool_prices(getattr(state, "pool", None))
    opt = state.opt if isinstance(state.opt, dict) else {}
    ft_lambda = None
    if opt.get("decision_priors"):
        try:
            from gaffer.assets import load_decision_priors
            from gaffer.optimize.ft_value import lambda_from_priors
            ft_lambda = lambda_from_priors(load_decision_priors())
        except Exception as exc:  # noqa: BLE001 — a decoration, never a gate
            print(f"plan trace: no lambda table ({exc}); flat ft_value")
    price_timing, price_fall = price_falls(state)
    out = priced(plan, buy, sell)
    out = charged(out, hit_cost=_int(opt.get("hit_cost", 4), 4), chips=chip_by_gw(chip_table))
    out = banked(out, _price(getattr(state, "bank", None)))
    out = traced(out, state=state, thresholds=thresholds(chip_table), ft_lambda=ft_lambda,
                 price_timing=price_timing, price_fall=price_fall)
    return out.model_copy(update={"generated_at": getattr(state, "generated_at", None)})
```

Note on `traced`: `price_falls` is read in `completed`, outside the `try`, exactly as `_price_falls` was read inside the router's `attach_trace` try — the reader has its own `try` and returns `(True, {})` on failure, so nothing changes.

- [ ] **Step 4: The loader in `src/gaffer/artifacts.py`.** Replace `load_advice` (lines 413–420) with:

```python
def advice_path(gw: int) -> Path:
    """The one place the advice filename is spelled (v17f §1 part 4)."""
    return REPORTS / f"gw{gw}-advice.json"


def advice_gws() -> list[int]:
    """Every gameweek with an advice file, ascending."""
    gws = []
    for path in REPORTS.glob("gw*-advice.json"):
        stem = path.stem.removeprefix("gw").removesuffix("-advice")
        if stem.isdigit():
            gws.append(int(stem))
    return sorted(gws)


def load_advice(gw: int) -> dict:
    """The advice payload ``run_advise`` wrote for ``gw``."""
    path = advice_path(gw)
    if not path.exists():
        raise GafferError(
            f"no advice for GW{gw} — run `gaffer advise` first")
    return json.loads(path.read_text())


def served_plan(gw: int):
    """The served plan for ``gw`` as one value (v17f §2.3): a file advise
    wrote through ``ServedPlan`` is served as written; a file written
    before v17f is priced, banked and traced here from its solve state,
    through the functions advise runs at write time. A file that is not
    the shape any ``gaffer advise`` wrote is a ``GafferError`` naming the
    field, never a 500 and never a silently degraded number."""
    from pydantic import ValidationError

    from gaffer.served import ServedPlan, completed, with_alternatives

    raw = load_advice(gw)
    try:
        plan = ServedPlan.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first.get("loc", ())) or "payload"
        raise GafferError(f"advice for GW{gw} will not read at {where}: "
                          f"{first.get('msg')}") from exc
    if "bank" in raw and "generated_at" in raw:
        return plan
    return completed(with_alternatives(plan, raw.get("alternative_plans")),
                     state=load_solve_state(gw), chip_table=raw.get("chip_table"))
```

`artifacts` imports `served` lazily inside the function because `served` imports nothing from `artifacts` today, but `price_falls` reaches `gaffer.config`, whose callers import `artifacts` early (the existing note on `save_solve_state` explains the cycle).

- [ ] **Step 5: Run the file** — `.venv/bin/pytest -q tests/test_served_plan.py` — Expected: all pass. If `test_a_trace_that_throws…` fails on the `capsys` line, the print is missing; if on `model_fields_set`, the failure branch left `trace` unset.

- [ ] **Step 6: Full suite** — `.venv/bin/pytest -q` — Expected: green.

- [ ] **Step 7: Commit** `feat(v17f): the pure passes (decorated, with_alternatives, priced, charged, banked, traced, completed) and artifacts.served_plan with its backfill; advice_path and advice_gws` staging `src/gaffer/served.py`, `src/gaffer/artifacts.py`, `tests/test_served_plan.py`.

---

### Task 3 (orchestrator): `serve_rung` returns `ServedPlan`

**Files:**
- Modify: `src/gaffer/ladder.py:269-346` (`serve_rung`), the import block
- Modify: `tests/test_v16_ladder.py:160-168, 190-291`, `tests/test_v17b_prose.py:63-77`
- Modify: `tests/test_served_plan.py` (append)

- [ ] **Step 1: The failing test** (append to `tests/test_served_plan.py`):

```python
# --- serve_rung ---------------------------------------------------------

def test_serve_rung_returns_the_objectives_plan_typed_when_there_is_no_ladder():
    from gaffer.ladder import serve_rung
    from gaffer.served import ServedPlan

    objective = {"gw": 4, "buys": [P], "sells": [S], "hits": 1, "xi": [P], "bench": [S],
                 "captain": P, "vice": S, "expected_pts": 61.5,
                 "plan_by_gw": [_week(4, buys=[P], sells=[S], hits=1), _week(5)]}
    out = serve_rung(None, objective, hit_cost=4, captain_note=None)
    assert isinstance(out, ServedPlan)
    assert out.gw == 4 and out.hits == 1 and out.buys[0].code == 100
    assert out.restraint.chosen is None and out.restraint.hit_cost == 4
    assert out.restraint.line == "restraint: the ladder did not build; this is the objective's plan"
    assert out.objective.line == "the objective wanted: In in; Out out; 1 hit"
    assert out.objective.week.gw == 4 and out.objective.week.hits == 1
    dumped = out.model_dump(exclude_unset=True)
    assert set(dumped) == {"gw", "buys", "sells", "hits", "xi", "bench", "captain", "vice",
                           "expected_pts", "plan_by_gw", "captain_note", "objective",
                           "restraint"}
```

- [ ] **Step 2: Run** — Expected: fails (`out["buys"]`-style dict comes back; `isinstance` false).

- [ ] **Step 3: Rewrite `serve_rung`** in `src/gaffer/ladder.py`. Add `from gaffer.served import ServedObjective, ServedPlan, ServedRestraint, ServedWeek` to the imports. Body:

```python
def serve_rung(ladder: dict | None, objective: dict, *, hit_cost: int,
               captain_note: str | None) -> ServedPlan:
    """The served plan from the chosen rung (v16 §4), or the objective's
    own when there is no rung to serve — one typed value (v17f §4), with
    the moves unpriced and the weeks unbanked: ``served.completed`` fills
    those off the solve state.

    ``hit_cost`` is the solve's price per hit (v17b §3.2): the block prices
    the served hits, and a ladder that did not build carries no cost of its
    own.

    ``objective`` is ``{gw, buys, sells, hits, xi, bench, captain, vice,
    expected_pts, plan_by_gw}`` in ``advise._named``'s shape.

    The armband: the rung's own plan captains its own squad, and that is
    what is served — the objective's captain was chosen for the objective's
    squad, and a buy the rung makes (Palmer, GW4) was never on the captain
    table the objective read. The one exception is a captain a note
    explains: the league sweep's cover or attack override (``captain_note``
    set) is a decision about the field, not the squad, so it stands when he
    is in the rung's XI and is replaced with a note when he is not.
    """
    obj = ServedPlan.model_validate(objective)
    # v17b §3.2: the block carries its prose — the chosen rung's ``label``,
    # the one ``line`` the CLI and the moves card print — and the objective
    # block its own line, so no surface composes a sentence of its own.
    objective_block = ServedObjective(
        buys=obj.buys, sells=obj.sells, hits=obj.hits, expected_pts=obj.expected_pts,
        line=_objective_line(objective),
        week=ServedWeek(gw=obj.gw, hits=obj.hits, buys=obj.buys, sells=obj.sells,
                        expected_pts=obj.expected_pts))
    restraint = {"chosen": None, "label": None, "bar": None, "steps": [],
                 "agrees": True, "note": None, "hit_cost": int(hit_cost), "line": None}

    def served(**fields) -> ServedPlan:
        restraint["line"] = _restraint_line(restraint)
        return obj.model_copy(update={
            "captain_note": captain_note, "objective": objective_block,
            "restraint": ServedRestraint.model_validate(restraint), **fields})

    if ladder is None:
        restraint["note"] = "the ladder did not build; this is the objective's plan"
        return served()
    chosen = ladder.get("chosen")
    row = next((r for r in ladder.get("rungs") or [] if r.get("key") == chosen), None)
    if chosen is None or row is None or not row.get("plan_by_gw"):
        restraint.update(bar=ladder.get("bar"), steps=_lined(ladder.get("steps")),
                         note="no rung of the ladder could be served; "
                              "this is the objective's plan")
        return served()
    weeks = row["plan_by_gw"]
    first = weeks[0]
    xi_codes = {int(p["code"]) for p in first["xi"]}
    captain, note = first["captain"], captain_note
    if captain_note:
        captain = objective["captain"]
        if int(captain["code"]) not in xi_codes:
            captain = first["captain"]
            note = (f"captain from the restrained plan; the sweep's choice "
                    f"({objective['captain']['name']}) is not in it")
    vice = first["vice"]
    if int(vice["code"]) == int(captain["code"]):
        vice = first["captain"] if int(first["captain"]["code"]) != int(captain["code"]) \
            else next(p for p in first["xi"] if int(p["code"]) != int(captain["code"]))
    agrees = _moves(first) == _moves(objective)
    restraint.update(
        chosen=chosen, label=_rung_label(str(chosen)), bar=ladder.get("bar"),
        steps=_lined(ladder.get("steps")), agrees=agrees,
        note=None if agrees else
        f"the objective's plan was the {_rung_label(chosen)} rung's "
        f"neighbour; the walk stopped at {_rung_label(chosen)}")
    rung = ServedPlan.model_validate({
        "gw": obj.gw,
        "buys": list(first["buys"]), "sells": list(first["sells"]),
        "hits": int(first["hits"]), "xi": list(first["xi"]),
        "bench": list(first["bench"]), "captain": captain, "vice": vice,
        "expected_pts": _week_pts(first),
        "plan_by_gw": [{"gw": int(w["gw"]), "hits": int(w["hits"]),
                        "buys": list(w["buys"]), "sells": list(w["sells"]),
                        "expected_pts": _week_pts(w)} for w in weeks]})
    return served(captain_note=note, **{k: getattr(rung, k) for k in (
        "buys", "sells", "hits", "xi", "bench", "captain", "vice",
        "expected_pts", "plan_by_gw")})
```

- [ ] **Step 4: Rewire the two test files.** In `tests/test_v16_ladder.py` `_objective()` gains `"gw": 4` and every `out["key"]` becomes an attribute read: `out.buys`, `[b.code for b in out.buys]`, `out.captain.code`, `out.captain_note`, `out.restraint.agrees`, `out.restraint.hit_cost`, `r.label`, `r.line`, `len(out.plan_by_gw)`; `out["buys"] == _objective()["buys"]` becomes `[b.code for b in out.buys] == [20, 19]`. In `tests/test_v17b_prose.py` `_objective()` gains `"gw": 4` and `_case` writes `served.model_dump(exclude_unset=True)["buys"]`, `["sells"]`, `["restraint"]`, and returns `served.hits`, `served.model_dump(exclude_unset=True)["restraint"]`, `served.model_dump(exclude_unset=True)["objective"]` (the fixture file stays JSON). Re-run `.venv/bin/python -m tests.test_v17b_prose --write` only if the file's diff shows a wording change; it should not — the prose functions are untouched.

- [ ] **Step 5: Run** — `.venv/bin/pytest -q tests/test_served_plan.py tests/test_v16_ladder.py tests/test_v17b_prose.py tests/test_v16_restraint.py` — Expected: the first three green; `test_v16_restraint.py`'s three source pins still pass at this point (advise is unchanged). Then `cd frontend && npx vitest run src/hubs/this-week/restraint-prose.test.tsx` — Expected: green.

- [ ] **Step 6: Commit** `refactor(v17f): serve_rung returns ServedPlan — the objective typed once, the rung's fields copied in, the restraint validated; the ladder and prose tests read attributes` staging `src/gaffer/ladder.py`, `tests/test_v16_ladder.py`, `tests/test_v17b_prose.py`, `tests/test_served_plan.py` and the fixture JSON only if it changed.

---

### Task 4 (orchestrator): advise writes the plan whole

**Files:**
- Modify: `src/gaffer/advise.py:118-180` (`Advice`), `:1113-1244` (the served block and the write)
- Modify: `tests/test_advise.py` only if a pin moves (expected: none)

- [ ] **Step 1: `Advice` gains two defaulted fields** after `restraint`:

```python
    # v17f §2.4 (specs/2026-09-08-v17f-served-plan-design.md): the run's
    # stamp and the starting bank in millions, so a reader of the served plan
    # never opens the solve state for either. Defaulted, so every payload
    # written before this and every positional construction still loads.
    generated_at: str | None = None
    bank: float | None = None
```

- [ ] **Step 2: Hoist the solve state.** Replace `save_solve_state(SolveState(` … `pool=pool_rows(pool, players, owned_now, ep_by, gws)))` with `generated_at = datetime.now(timezone.utc).isoformat()` before it, `solve_state = SolveState(... generated_at=generated_at, ...)` and `save_solve_state(solve_state)`.

- [ ] **Step 3: The served block.** Replace from `served = serve_rung(ladder, dict(` through `strategy = None` (exclusive) with:

```python
    served = serve_rung(ladder, dict(
        gw=gw, buys=buys, sells=sells, hits=int(first.hits),
        xi=_named(first.xi, name_of, pos_of, ep_by, gw),
        bench=_named(first.bench, name_of, pos_of, ep_by, gw),
        captain=_named([first.captain], name_of, pos_of, ep_by, gw)[0],
        vice=_named([first.vice], name_of, pos_of, ep_by, gw)[0],
        expected_pts=round(raw_xi_pts(first, ep_by), 2),
        plan_by_gw=[{"gw": p.gw, "hits": p.hits,
                     "buys": _named(p.buys, name_of, pos_of, ep_by, p.gw),
                     "sells": _named(p.sells, name_of, pos_of, ep_by, p.gw),
                     "expected_pts": round(raw_xi_pts(p, ep_by), 2)}
                    for p in plan.gw_plans]),
        # v17b §3.2: the served block prices its hits off the solve's cost.
        hit_cost=int(cfg.hit_cost), captain_note=captain_note)
    # The tags and the sweep frequencies decorate the *served* moves (v16
    # §4). An empty EO map is "nobody's ownership is known", not "nobody
    # owns them" — at GW1 no rival picks are public yet, and tagging all 15
    # opening picks "attack" off a missing map would be pure noise.
    # Frequencies ride on the move dicts as well as on the standalone table:
    # the CLI and the UI both render per-move.
    served = decorated(
        served,
        tags={b.code: transfer_tag(league_eo.get(b.code),
                                   strat is not None and bool(league_eo))
              for b in served.buys},
        frequencies={(str(r["kind"]), int(r["code"])): float(r["frequency"])
                     for r in move_freqs})
    # v17f §2.2: prices, banks and the trace at write time, off the state
    # just saved — the same pass ``artifacts.served_plan`` runs for a file
    # written before this cycle, so the two cannot disagree.
    served = completed(with_alternatives(served, alt_rows),
                       state=solve_state, chip_table=chip_rows)
```

and the import `from gaffer.served import completed, decorated, with_alternatives`.

- [ ] **Step 4: The `Advice` construction** becomes:

```python
    advice = Advice(
        deadline=deadline,
        captain_options=cap_tab.to_dict("records"),
        chip_table=chip_rows,
        wildcard_now=wc_now,
        alternatives=alts.to_dict("records"),
        threats=threats.to_dict("records"),
        price_alerts=alerts.to_dict("records"),
        strategy=strategy,
        win_probs=win_probs,
        mode="weekly" if my is not None else "initial_squad",
        data_through_gw=through,
        data_warning=gap_warning,
        move_frequencies=move_freqs,
        raw_optimum_agrees=raw_agrees,
        scenarios=scenario_report,
        demoted_captain=demoted_captain,
        caps=(None if my is None
              else {"max_hits": int(cfg.max_hits),
                    "max_transfers": int(cfg.max_transfers)}),
        # v17f §2.1: the served plan, written whole. ``exclude_unset`` so a
        # move advise never tagged carries no ``tag`` key on disk.
        **served.model_dump(exclude_unset=True),
    )
```

(`gw`, `buys`, `sells`, `hits`, `xi`, `bench`, `captain`, `vice`, `captain_note`, `expected_pts`, `plan_by_gw`, `objective`, `restraint`, `alternative_plans`, `generated_at`, `bank` all come from the dump.) The write becomes `atomic_write(advice_path(gw), ...)` with `advice_path` imported from `gaffer.artifacts`; delete the local `advice_path = REPORTS / ...` line.

- [ ] **Step 5: Run** — `.venv/bin/pytest -q tests/test_advise.py tests/test_v16_restraint.py tests/test_v4c_degradation.py tests/test_served_plan.py -x` — Expected: `test_advise.py` green; `test_v16_restraint.py`'s two source-order pins fail (`served["hits"]` is no longer in the source) — that is the ruling Task 5 records; do not edit them here. If `test_advise.py` fails on a pin, stop and record the ruling in the spec's §7 before changing it.

- [ ] **Step 6: Commit** `feat(v17f): advise writes the served plan whole — one objective dict, decorated, completed off the hoisted solve state, one model_dump into Advice; Advice gains generated_at and bank` staging `src/gaffer/advise.py` (and `tests/test_advise.py` only with a ruling).

---

### Task 5 (orchestrator): the v16 pins move to a round trip (gate part 3)

**Files:**
- Modify: `tests/test_v16_restraint.py:1-46`
- Modify: `tests/test_served_plan.py` (append)

- [ ] **Step 1: The round trip** (append):

```python
# --- the round trip (v17f §1 part 3; replaces the v16 source-order pins) --

def test_the_served_plan_round_trips_through_the_advice_file(tmp_path, monkeypatch):
    """Build → write the way advise writes → load → equal. This is the pin
    the three source-order tests in test_v16_restraint.py became: the
    served fields reach the file through one dump and come back through
    one loader, so the order of the calls in run_advise is no longer a
    thing a test has to read the source to check."""
    from dataclasses import asdict
    from pathlib import Path

    from gaffer.advise import Advice
    from gaffer.artifacts import advice_path, served_plan
    from gaffer.io import atomic_write
    from gaffer.ladder import serve_rung
    from gaffer.served import completed, decorated, with_alternatives

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    objective = {"gw": 5, "buys": [P], "sells": [S], "hits": 1, "xi": [P], "bench": [S],
                 "captain": P, "vice": S, "expected_pts": 61.5,
                 "plan_by_gw": [_week(5, buys=[P], sells=[S], hits=1), _week(6)]}
    plan = serve_rung(None, objective, hit_cost=4, captain_note="covering Dave")
    plan = decorated(plan, tags={100: "attack"}, frequencies={("buy", 100): 0.7})
    plan = completed(with_alternatives(plan, [{"gap": 0.4, "plan_by_gw": [_week(6, buys=[P])]}]),
                     state=_state(), chip_table=[{"chip": "bboost", "gw": 6, "play_now": True}])
    advice = Advice(deadline="2026-09-18T17:30:00Z", captain_options=[], chip_table=[],
                    wildcard_now=None, alternatives=[], threats=[], price_alerts=[],
                    **plan.model_dump(exclude_unset=True))
    atomic_write(advice_path(5), json.dumps(asdict(advice), indent=1, default=str))
    assert served_plan(5) == plan
    raw = json.loads(advice_path(5).read_text())
    assert "tag" not in raw["xi"][0] and raw["buys"][0]["tag"] == "attack"
    assert raw["plan_by_gw"][0]["bank"] == 0.9 and raw["bank"] == 1.5
```

- [ ] **Step 2: Replace the three pins.** In `tests/test_v16_restraint.py` delete `test_advice_carries_the_two_blocks_with_safe_defaults`, `test_the_state_is_saved_then_the_ladder_then_the_served_plan` and `test_the_objective_dict_is_the_solvers_own_week_one`, and the now-unused `import inspect`; replace the module docstring with `"""v16 §4 — the advice is the chosen rung: the CLI lines. The source-order pins on run_advise moved to the round trip in tests/test_served_plan.py (v17f §1 part 3)."""`.

- [ ] **Step 3: Run** — `.venv/bin/pytest -q tests/test_served_plan.py tests/test_v16_restraint.py` — Expected: green. Then the full suite `.venv/bin/pytest -q` — Expected: red only in the plan-route test files that still patch `plan_router.load_advice` (Tasks 6 and 7 rewire them); note the count.

- [ ] **Step 4: Commit** `test(v17f): ruling — the v16 source-order pins on run_advise are replaced by the served plan's round trip (spec §1 part 3)` staging both files.

---

### Task 6: the plan router as a shape adapter; the route tests rewired

**Files:**
- Modify: `src/gaffer/web/routers/plan.py` (rewrite)
- Modify: `tests/test_web_plan.py`, `tests/test_v11_plan_bank.py`, `tests/test_v16_plan_objective.py`, `tests/test_v12_w3_plan_alternatives.py`, `tests/test_v12_w5_plan_trace.py`

- [ ] **Step 1: Rewrite `src/gaffer/web/routers/plan.py`**:

```python
"""GET /api/plan/{gw} — the served plan, shaped for the board.

A shape adapter and nothing else (v17f §2.6): every number here — the
prices, the running bank, the trace — was written by ``gaffer advise`` or
filled by ``artifacts.served_plan`` for a file written before v17f. No
MILP runs here, deliberately: the plan the timeline draws must be the plan
the report printed, not a fresh solve that could differ.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from gaffer.artifacts import served_plan
from gaffer.errors import GafferError
from gaffer.served import ServedMove, ServedWeek
from gaffer.web.schemas import (PlanAlternative, PlanGw, PlanMove,
                                PlanTimeline)

router = APIRouter(prefix="/api", tags=["plan"])

LABELS = ("Plan B", "Plan C", "Plan D", "Plan E")
"""Names for the alternatives, by position. Longer than ``ALT_PLAN_MAX``
needs, so an artifact written by a build with a larger set does not fall off
the end of the list and lose its last tab."""


def _move(move: ServedMove | None) -> PlanMove | None:
    if move is None:
        return None
    return PlanMove(code=move.code, name=move.name, position=move.position,
                    ep=round(move.ep, 2), price=move.price)


@router.get("/plan/{gw}", response_model=PlanTimeline)
def plan(gw: int) -> PlanTimeline:
    try:
        served = served_plan(gw)
    except GafferError as exc:
        # 404, not the app-wide 422: the timeline hides on a missing artifact
        # and must not be confused with a constraint failure.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    head = served.gw

    def week(w: ServedWeek, *, head_refs: bool) -> PlanGw:
        # The armband belongs to the plan that was recommended, on its head
        # week only; lending it to an alternative, or to the objective's
        # week, would be the most confident thing this payload could get
        # wrong.
        is_head = head_refs and w.gw == head
        return PlanGw(
            gw=w.gw, buys=[_move(m) for m in w.buys], sells=[_move(m) for m in w.sells],
            hits=w.hits, hit_cost=w.hit_cost, chip=w.chip,
            captain=_move(served.captain) if is_head else None,
            vice=_move(served.vice) if is_head else None,
            expected_pts=round(w.expected_pts, 2), bank=w.bank, trace=w.trace)

    weeks = [week(w, head_refs=True) for w in served.plan_by_gw]
    alternatives = [
        PlanAlternative(label=LABELS[i], gap=alt.gap,
                        weeks=[week(w, head_refs=False) for w in alt.plan_by_gw])
        for i, alt in enumerate(served.alternative_plans[:len(LABELS)])]
    # v16 §4: the objective's week one beside the served rung's only when
    # the two differ — an agreeing objective would say it twice.
    objective = None
    if (served.objective is not None and served.objective.week is not None
            and served.restraint is not None and served.restraint.agrees is False):
        objective = week(served.objective.week, head_refs=False)
    return PlanTimeline(gw=head, generated_at=served.generated_at or "", weeks=weeks,
                       bank=served.bank, alternatives=alternatives, objective=objective)
```

- [ ] **Step 2: Rewire the fixtures.** In every file, `monkeypatch.setattr(plan_router, "load_advice", …)` becomes `monkeypatch.setattr("gaffer.artifacts.load_advice", …)` and `…"load_solve_state"…` likewise; `tests/test_v16_plan_objective.py`'s `_with_objective` assigns `plan_router.load_advice = advice` directly — change it to `monkeypatch.setattr("gaffer.artifacts.load_advice", advice)` (add `monkeypatch` to its signature and callers). In `tests/test_v12_w5_plan_trace.py`: `plan_router._price_falls` patches become `"gaffer.served.price_falls"`; `plan_router.trace_plan` becomes `"gaffer.trace.trace_plan"`; `plan_router.load_solve_state(5)` in the last test becomes `gaffer.artifacts.load_solve_state(5)`.

- [ ] **Step 3: Delete the dying tests** (spec §6, amended): in `tests/test_web_plan.py` `test_a_non_numeric_hits_count_reads_as_none_taken`, `test_a_non_numeric_ep_on_a_move_reads_as_zero`, `test_a_move_with_no_code_is_dropped_not_fatal`, `test_a_plan_entry_that_is_not_a_dict_is_skipped`, `test_a_chip_row_with_a_null_gameweek_is_ignored` (its rule now lives in `test_chip_and_theta_lookups_read_only_played_rows`), `test_a_chip_table_that_is_not_a_list_costs_only_the_chips` (same), `test_a_non_numeric_hit_cost_falls_back_to_four`, `test_a_plan_entry_with_no_gameweek_is_skipped`; in `tests/test_v12_w3_plan_alternatives.py` `test_a_malformed_alternatives_key_costs_a_tab_and_not_the_board` and `test_an_alternative_that_is_not_a_dict_is_dropped_and_the_rest_stand`; in `tests/test_v12_w5_plan_trace.py` `test_the_payload_is_byte_identical_with_the_trace_off` and `test_a_trace_that_throws_costs_the_trace_and_not_the_plan` (moved to `test_served_plan.py` in Task 2). Add one test to `tests/test_web_plan.py` in their place:

```python
def test_a_file_that_is_not_the_shape_advise_writes_is_a_404_naming_the_field(
        tmp_path, monkeypatch):
    """v17f §2.7: the coercers are gone. A number that is not a number is a
    file no `gaffer advise` wrote, and the detail says where."""
    client = _with(tmp_path, monkeypatch, {**ADVICE, "hits": "one"})
    resp = client.get("/api/plan/5")
    assert resp.status_code == 404
    assert "hits" in resp.json()["detail"]
```

Update the "artifact drift" comment block above `_with` to say the loader validates and the pool readers still degrade.

- [ ] **Step 4: Run** — `.venv/bin/pytest -q tests/test_web_plan.py tests/test_v11_plan_bank.py tests/test_v16_plan_objective.py tests/test_v12_w3_plan_alternatives.py tests/test_v12_w5_plan_trace.py tests/test_served_plan.py` — Expected: green. The `test_v12_w5_plan_trace.py` note assertions (`"tonight's price log"`, `"price_timing\` is off now"`) still hold: the sentences are `trace_plan`'s.

- [ ] **Step 5: Full suite** — `.venv/bin/pytest -q` — Expected: red only in `tests/test_v11_degradation.py` and `tests/test_v12_w3_degradation.py` (protected; Task 7). Report the exact failing names to the orchestrator.

- [ ] **Step 6: Commit** `refactor(v17f): the plan router is a shape adapter over served_plan; the route tests patch the artifact loaders; the coercer tests retired by ruling (spec §2.7)` staging `src/gaffer/web/routers/plan.py` and the five test files.

---

### Task 7 (orchestrator): the protected rails

**Files:**
- Modify: `tests/test_v11_degradation.py:30-130`, `tests/test_v12_w3_degradation.py:208-250`

- [ ] **Step 1:** In `tests/test_v11_degradation.py` the `planned` fixture patches `"gaffer.artifacts.load_advice"` and `"gaffer.artifacts.load_solve_state"`; delete `test_a_move_too_broken_to_parse_blanks_the_bank_the_same_way` and `test_a_buys_key_that_is_not_a_list_blanks_it_too` with a comment naming the ruling (`v17f §2.7: a move too broken to parse is a file no advise wrote; the loader refuses it by name`). In `tests/test_v12_w3_degradation.py` `_wire` patches the artifact names; delete `test_a_malformed_alternative_costs_a_tab_and_not_the_board` with the same comment.

- [ ] **Step 2: Run** — `.venv/bin/pytest -q tests/test_v11_degradation.py tests/test_v12_w3_degradation.py tests/test_v12_w5_degradation.py tests/test_v12_w1_degradation.py` — Expected: green; the route total pin (51) untouched.

- [ ] **Step 3: Commit** `test(v17f): ruling — the v11 and v12 W3 plan rails patch the artifact loaders; three malformed-file tests retired (spec §2.7)`.

---

### Task 8: no filename outside artifacts; the frontend takes the generated types; the shots stage

**Files:**
- Modify: `src/gaffer/web/routers/meta.py:125-131, 229`, `src/gaffer/tracking.py:47-52`, `src/gaffer/report/render.py:1-6`
- Modify: `frontend/src/types.ts:101-135, 163-166`, `frontend/src/hubs/this-week/MovesCard.tsx:5`, `frontend/scripts/shots.sh` (after the v17e block)
- Modify: `tests/test_served_plan.py` (append)

- [ ] **Step 1: The failing tests** (append):

```python
# --- no filename outside artifacts (v17f §1 part 4) ----------------------

def test_the_advice_filename_is_spelled_only_in_artifacts():
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = subprocess.run(["grep", "-rln", "advice.json", "src/gaffer", "--include=*.py"],
                         cwd=root, capture_output=True, text=True).stdout.split()
    assert out == ["src/gaffer/artifacts.py"], out


def test_the_history_route_reads_the_gameweeks_through_artifacts(tmp_path, monkeypatch):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from gaffer.web.app import create_app

    monkeypatch.chdir(tmp_path)
    Path("reports").mkdir()
    for gw in (5, 4):
        Path(f"reports/gw{gw}-advice.json").write_text(json.dumps({
            "gw": gw, "deadline": "d", "captain": P, "buys": [P], "sells": [S],
            "hits": 0, "expected_pts": 60.0, "xi": [P]}))
    runs = TestClient(create_app()).get("/api/history").json()["runs"]
    assert [r["gw"] for r in runs] == [5, 4]


def test_update_health_reads_the_captain_through_artifacts(tmp_path, monkeypatch):
    import gaffer.tracking as tracking

    monkeypatch.chdir(tmp_path)
    seen = {}
    monkeypatch.setattr(tracking, "compute_health",
                        lambda preds, actuals, captain_code: seen.update(c=captain_code) or {})
    monkeypatch.setattr("gaffer.artifacts.load_advice", lambda gw: {"captain": {"code": 42}})
    monkeypatch.setattr(tracking.store, "exists", lambda rel: True)
    monkeypatch.setattr(tracking.store, "load",
                        lambda rel: pd.DataFrame({"code": [1], "gw": [4], "total_points": [2],
                                                  "minutes": [90]}))
    tracking.update_health(4)
    assert seen["c"] == 42
```

- [ ] **Step 2: Run** — Expected: the grep test fails listing four files; the history test fails or passes by accident (it globs the same directory), the tracking test fails on `seen`.

- [ ] **Step 3: `meta.py`.** Replace the glob loop with:

```python
    from gaffer.artifacts import advice_gws, advice_path
    ...
    for gw_seen in advice_gws():
        advice = load_advice(gw_seen)
```

(drop the `stem` lines) and the freshness row with `_row("advise", advice_path(advice_gws()[-1]) if advice_gws() else None)` — bind `gws = advice_gws()` once above the `Freshness(...)` return. `tracking.py`:

```python
    from gaffer.artifacts import load_advice
    from gaffer.errors import GafferError

    captain = 0
    try:
        captain = int((load_advice(finished_gw).get("captain") or {}).get("code", 0))
    except (GafferError, TypeError, ValueError):
        captain = 0
```

and drop the `Path`/`json` uses that only served the file (keep those the health file needs). `render.py`'s docstring: "so a payload round-tripped through the advice artifact renders identically".

- [ ] **Step 4: Frontend.** In `frontend/src/types.ts` delete `RestraintStep`, `Restraint`, `Objective`; `Advice.objective?: ServedObjective | null` and `restraint?: ServedRestraint | null` with `import type { ServedObjective, ServedRestraint } from './types.generated'` (match the file's existing import style for generated names). `MovesCard.tsx` imports `ServedObjective, ServedRestraint` from `'../../types.generated'` and its props use them; `restraint.hit_cost` is `number | null` in the generated type, so the hit line reads `hits * (restraint.hit_cost ?? 4)` only if tsc demands it — first check what the component already does with a null. Add to `shots.sh` after the v17e block:

```bash
# v17f gate (specs/2026-09-08-v17f-served-plan-design.md §1): the Planning
# board's timeline (banks, traces, the objective column) and This Week.
if [[ "$STAGE" == v17f* ]]; then
  HUBS=(
    "planning-board:/planning?tab=board"
    "this-week:/"
  )
fi
```

- [ ] **Step 5: Run** — `.venv/bin/pytest -q tests/test_served_plan.py tests/test_web_meta.py tests/test_tracking.py` (use the nearest existing file names; `ls tests | grep -i "meta\|tracking\|health"`), then `cd frontend && npx tsc --noEmit && npx vitest run` — Expected: all green, `Errors  0`.

- [ ] **Step 6: Full suite** — `.venv/bin/pytest -q` — Expected: green.

- [ ] **Step 7: Commit** `refactor(v17f): meta and tracking read gameweeks and the captain through artifacts; the render docstring; the frontend takes the generated served types; shots.sh v17f stage`.

---

### Task 9 (orchestrator): the gate

- [ ] **Step 1: The strip check (gate part 1).** Run the golden pipeline on the branch into a scratch tree and compare with the new keys stripped:

```python
# scratchpad/strip_check.py
import json, tempfile
from pathlib import Path
from tests import golden_client as gc
NEW_TOP = {"generated_at", "bank"}
NEW_WEEK = {"hit_cost", "chip", "bank", "trace"}
def move(m): return {k: v for k, v in m.items() if k != "price"}
def week(w): return {**{k: v for k, v in w.items() if k not in NEW_WEEK},
                     "buys": [move(m) for m in w.get("buys", [])],
                     "sells": [move(m) for m in w.get("sells", [])]}
def strip(a):
    a = {k: v for k, v in a.items() if k not in NEW_TOP}
    for key in ("buys", "sells", "xi", "bench"): a[key] = [move(m) for m in a[key]]
    for key in ("captain", "vice"): a[key] = move(a[key]) if a[key] else a[key]
    a["plan_by_gw"] = [week(w) for w in a["plan_by_gw"]]
    a["alternative_plans"] = [{**alt, "plan_by_gw": [week(w) for w in alt["plan_by_gw"]]}
                              for alt in a["alternative_plans"]]
    if a.get("objective"):
        a["objective"] = {k: v for k, v in a["objective"].items() if k != "week"}
        for key in ("buys", "sells"): a["objective"][key] = [move(m) for m in a["objective"][key]]
    return a
root = Path(tempfile.mkdtemp(prefix="golden-v17f-"))
gc.build_scratch_tree(root, gc._repo_root())
advice, state = gc.run_golden(root)
cwd = str(root.resolve())
advice, state = gc.strip_volatile(advice, cwd), gc.strip_volatile(state, cwd)
exp = gc.GOLDEN_DIR / gc.EXPECTED_DIR
old_advice = json.loads((exp / "advice.json").read_text())
old_state = json.loads((exp / "solve_state.json").read_text())
print("advice stripped equal:", strip(advice) == old_advice)
print("state equal:", state == old_state)
print("levers equal:", gc.lever_counts(advice) == json.loads((gc.GOLDEN_DIR / gc.HEADER_NAME).read_text())["levers"])
print("plan route equal:", gc.plan_route(root, int(advice["gw"])) == json.loads((exp / "plan.json").read_text()))
```

Expected: four `True`. On any `False`, diff and fix before re-recording; a value that differs fails the gate.

- [ ] **Step 2: Re-record** — `.venv/bin/python -m tests.golden_client --write`; then `git diff --stat -- tests/data/golden_board` must list `expected/advice.json` and `header.json` only (`plan.json` unchanged; `solve_state.json` unchanged). Commit `test(v17f): golden expected advice re-recorded — the served plan's new keys (price, hit_cost, chip, bank, trace, objective.week, generated_at, bank); every pre-existing value equal (spec §1 part 1)`.

- [ ] **Step 3: The golden gate** — `.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py` — Expected: 45 passed, none skipped.

- [ ] **Step 4: The suites** — `.venv/bin/pytest -q`; `cd frontend && npx tsc --noEmit && npx vitest run`. Record the counts.

- [ ] **Step 5: Part 4** — `grep -rn "advice.json" src/gaffer --include='*.py'` prints only `artifacts.py` lines.

- [ ] **Step 6: Screenshots** — `gaffer ui` on :8927 with the real `reports/`, `frontend/scripts/shots.sh v17f`, user approval.

- [ ] **Step 7: Spec §10, ff-merge, push, security ritual, ROADMAP, GUIDE §11, tracker, memory.**
