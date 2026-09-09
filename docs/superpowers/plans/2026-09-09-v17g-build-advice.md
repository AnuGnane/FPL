# v17g — `build_advice` as a pure module: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> superpowers:subagent-driven-development to implement this plan task by
> task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** split `run_advise` into `gather_inputs(cfg, client) -> Inputs` and a
pure `build_advice(inputs, cfg) -> Outputs`, so the weekly pipeline is tested
through an interface instead of by string-matching its source.

**Architecture:** one new module `src/gaffer/inputs.py` holds two frozen
values (`Inputs`, `Outputs`), two protocols (`Predictions`, `Solver`), their
live adapters and the fixture serializer. `advise.py` keeps every line of its
body — the same calls in the same order — but the body now lives in two
functions with `run_advise` composing them and doing the writes. `ladder.py`
gains a pure `ladder_payload` so the ladder can be solved off a `SolveState`
in memory.

**Spec:** `docs/superpowers/specs/2026-09-09-v17g-build-advice-design.md`.
Read §1 (the gate) and §2 (the decisions) before starting any task.

**Tech stack:** unchanged. Python 3, pandas, pytest.

---

## Ground rules for every task

- **Never** edit a file listed as protected in the spec's §6 unless the task
  says "orchestrator". Implementers: if a task seems to need one, stop and
  report `BLOCKED` with the file and the reason.
- **Never** open `config.toml`. The bookmaker odds key lives there under
  `[odds] api_key`; refer to it by name, never by value, in code, comments,
  commit messages or reports.
- Run `.venv/bin/pytest -q <the files your task touches>` from the repo root
  before committing. Do **not** run `tests/test_golden_board.py` — it takes
  eight minutes and it is the orchestrator's gate (CONVENTIONS §7).
- Comments and docstrings cite the cycle and section (`v17g §2.2`) and say
  **why**, not what. Test names are sentences.
- Commit with explicit paths. Never `git add -A`.
- Commit trailers:
  ```
  Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Nc7ELpPwL6u3VNDi5mm4op
  ```

**Task order matters.** T3 must land before T4: it redirects eighteen pins
while the text they read is still `run_advise`'s, so the redirect commit is
provably a no-op and the split that follows cannot be blamed for it.

| Task | Owner | What |
|---|---|---|
| T1 | implementer | `src/gaffer/inputs.py` and its tests |
| T2 | implementer | the pure cores: `ladder_payload` and the trace context |
| T3 | **orchestrator** | `tests/advise_source.py`, eighteen pins redirected |
| T4 | **orchestrator** | the split in `advise.py` |
| T5 | implementer | the test fixture: `ScriptedSolver`, a tiny `Inputs` |
| T6 | implementer | the golden's `inputs/` recording and its four tests |
| T7 | **orchestrator** | `tests/test_advise.py`: thirty-five pins rewritten |

---

## Task 1: `src/gaffer/inputs.py` — the seam

**Owner:** implementer.

**Files:**
- Create: `src/gaffer/inputs.py`
- Create: `tests/test_inputs.py`
- Modify: none. **Do not touch `src/gaffer/advise.py`** — it is protected and
  T4 wires it up.

**Scene.** `run_advise` in `src/gaffer/advise.py` is one 659-line function.
T4 will cut it in two: a gather half that fetches, loads models and predicts,
and a build half that solves. This task builds the value that passes between
them and the two protocols that hide the models and the solver. Nothing
imports it yet; that is fine and expected.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_inputs.py`:

```python
"""v17g §2.7, §2.8 — the frozen seam between gather and build, and the
recording that gives it a second adapter."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from gaffer.inputs import (Inputs, LiveModels, MilpSolver, Outputs,
                           Predictions, RecordedComponents, Solver,
                           load_inputs, save_inputs)


def _inputs(**over) -> Inputs:
    """A small, complete Inputs. Two players, one gameweek, no league."""
    players = pd.DataFrame([
        {"code": 100, "name": "In", "position": "MID", "team_code": 1,
         "now_cost": 80, "price_change_percent": 0.0},
        {"code": 200, "name": "Out", "position": "MID", "team_code": 2,
         "now_cost": 75, "price_change_percent": 0.0}])
    comp = pd.DataFrame([{"code": 100, "gw": 7, "p_play": 0.9, "ep": 6.0},
                         {"code": 200, "gw": 7, "p_play": 0.8, "ep": 4.0}])
    fields = dict(
        gw=7, gws=[7, 8], deadline="2026-10-01T17:30:00Z", through=6,
        gap_warning=None, players=players, comp=comp, components=comp.copy(),
        ep_named=pd.DataFrame([{"code": 100, "gw": 7, "ep": 6.0,
                                "name": "In", "position": "MID"}]),
        ep_by={(100, 7): 6.0, (200, 7): 4.0}, my=None, league_eo={},
        cover={}, cap_cover={}, rival_captains={}, rival_names={},
        strategy=None, win_probs=[], priors=None, dgw_probs={},
        prior_advice=None, price_timing=True, price_fall={})
    fields.update(over)
    return Inputs(**fields)


def test_inputs_is_frozen_so_a_pass_cannot_edit_the_board():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _inputs().gw = 8


def test_outputs_is_frozen_and_carries_the_three_things_run_advise_banks():
    assert [f.name for f in dataclasses.fields(Outputs)] == [
        "advice", "state", "ladder"]


def test_the_round_trip_returns_every_field_unchanged(tmp_path):
    """v17g §2.8: the recording is the second adapter of the Inputs seam, so
    it has to be exact, not close."""
    original = _inputs()
    save_inputs(original, tmp_path)
    back = load_inputs(tmp_path)
    for f in dataclasses.fields(Inputs):
        a, b = getattr(original, f.name), getattr(back, f.name)
        if isinstance(a, pd.DataFrame):
            pd.testing.assert_frame_equal(a, b)
        else:
            assert a == b, f.name


def test_the_integer_keys_survive_json(tmp_path):
    """JSON has no integer keys. A silently stringified code moves the pool
    and nothing would say so."""
    original = _inputs(league_eo={100: 12.5}, cover={100: 0.4},
                       cap_cover={200: 0.1}, rival_captains={9: 100},
                       rival_names={9: "Rivals"}, dgw_probs={12: 0.8},
                       price_fall={100: 0.7})
    save_inputs(original, tmp_path)
    back = load_inputs(tmp_path)
    assert back.league_eo == {100: 12.5}
    assert back.cover == {100: 0.4}
    assert back.cap_cover == {200: 0.1}
    assert back.rival_captains == {9: 100}
    assert back.rival_names == {9: "Rivals"}
    assert back.dgw_probs == {12: 0.8}
    assert back.price_fall == {100: 0.7}


def test_a_squad_and_a_strategy_round_trip(tmp_path):
    from gaffer.data.entry import MyTeam
    from gaffer.league_mode import Strategy

    my = MyTeam(entry_id=5, bank=12, free_transfers=1, current_gw=7,
                picks=pd.DataFrame([{"code": 100, "sell": 80}]),
                chips_used=["wildcard"], chips_by_gw={3: "wildcard"})
    strat = Strategy(lam=0.4, gap=12, weeks_left=30, stance="chase",
                     rival_name="Rivals", cover_weights={9: 1.0})
    save_inputs(_inputs(my=my, strategy=strat), tmp_path)
    back = load_inputs(tmp_path)
    assert back.my.bank == 12 and back.my.chips_by_gw == {3: "wildcard"}
    pd.testing.assert_frame_equal(back.my.picks, my.picks)
    assert back.strategy == strat
    assert back.strategy.cover_weights == {9: 1.0}


def test_every_protocol_has_two_adapters():
    """The review's test for a real seam: one adapter is a hypothetical one."""
    assert isinstance(LiveModels(), Predictions)
    assert isinstance(RecordedComponents("."), Predictions)
    assert isinstance(MilpSolver(), Solver)


def test_the_milp_solver_passes_its_arguments_straight_through(monkeypatch):
    """v17g §2.5: the adapter is a pass-through, so no solve changes."""
    seen = {}
    monkeypatch.setattr("gaffer.inputs.solve_plan",
                        lambda pool, state, **kw: seen.update(
                            pool=pool, state=state, kw=kw) or "plan")
    assert MilpSolver().solve("POOL", "STATE", decay=0.85) == "plan"
    assert seen == {"pool": "POOL", "state": "STATE", "kw": {"decay": 0.85}}


def test_recorded_components_serves_the_fixture_and_claims_no_models(tmp_path):
    comp = pd.DataFrame([{"code": 100, "gw": 7, "ep": 6.0}])
    save_inputs(_inputs(comp=comp), tmp_path)
    rec = RecordedComponents(tmp_path)
    assert rec.missing() == []
    pd.testing.assert_frame_equal(
        rec.components(pred_frame=None, tg_future=None, players=None,
                       avail=None, pens=None), comp)
    assert rec.calibration() is None
```

- [ ] **Step 2: Run them and watch them fail**

```
.venv/bin/pytest -q tests/test_inputs.py
```

Expected: collection error, `ModuleNotFoundError: No module named 'gaffer.inputs'`.

- [ ] **Step 3: Write `src/gaffer/inputs.py`**

```python
"""The seam ``run_advise`` is composed from (v17g §3).

``gather_inputs`` fills an :class:`Inputs` — every fetch, every model load
and every prediction — and ``build_advice`` reads one and returns an
:class:`Outputs`. Everything impure is on the gather side, which is what
makes the build a pure function of one frozen value: testable with no
models, no network and no ``reports/``.

Two protocols hide what the two halves still depend on. :class:`Predictions`
is the three places gather touches ``models/``; :class:`Solver` is the four
calls that produce a :class:`~gaffer.optimize.milp.Plan`. Each has two
adapters, which is the review's test for a seam that is real rather than
hypothetical.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import pandas as pd

from gaffer.data.entry import MyTeam
from gaffer.league_mode import Strategy
from gaffer.optimize.milp import alternative_plans, solve_plan
from gaffer.optimize.policy import coherent_plan
from gaffer.optimize.scenarios import run_scenarios

if TYPE_CHECKING:  # the annotations are strings, and advise imports this
    from gaffer.advise import Advice
    from gaffer.artifacts import SolveState


@dataclass(frozen=True)
class Inputs:
    """Everything ``build_advice`` reads, and nothing it does not (v17g §2.7).

    The rule is enforced by a rail rather than by care: a field that
    ``build_advice`` never names is a field the golden has to record and keep
    correct for no reader.
    """

    gw: int
    gws: list[int]
    deadline: str
    through: int | None
    gap_warning: str | None
    players: pd.DataFrame
    comp: pd.DataFrame
    components: pd.DataFrame
    ep_named: pd.DataFrame
    ep_by: dict[tuple[int, int], float]
    my: MyTeam | None
    league_eo: dict[int, float]
    cover: dict[int, float]
    cap_cover: dict[int, float]
    rival_captains: dict[int, int]
    rival_names: dict[int, str]
    strategy: Strategy | None
    win_probs: list[dict]
    priors: dict | None
    dgw_probs: dict[int, float]
    prior_advice: dict | None
    # v17g §2.3b: the served plan's trace reads the price-timing switch and
    # the banked fall table. Both are reads, so both are gathered.
    price_timing: bool
    price_fall: dict[int, float]


@dataclass(frozen=True)
class Outputs:
    """What a build produced: the payload, the board it solved on, and the
    ladder. ``run_advise`` banks all three; nothing here has been written yet.
    """

    advice: "Advice"
    state: "SolveState"
    ladder: dict | None


@runtime_checkable
class Predictions(Protocol):
    """The three places the weekly run touches ``models/`` (v17g §2.5)."""

    def missing(self) -> list[str]: ...

    def components(self, *, pred_frame, tg_future, players, avail,
                   pens) -> pd.DataFrame: ...

    def calibration(self): ...


@runtime_checkable
class Solver(Protocol):
    """The four calls that produce a plan. Chip pricing is deliberately not
    here: it answers what a chip is worth against a baseline, not what to do
    this week, and a protocol for it would be a third seam nobody needs.
    """

    def solve(self, pool, state, **kw): ...

    def coherent(self, pool, state, decision, **kw): ...

    def scenarios(self, pool, state, xmins, **kw): ...

    def alternatives(self, pool, state, plan, **kw): ...


class LiveModels:
    """The real ``models/`` directory."""

    def missing(self) -> list[str]:
        from gaffer.advise import MODEL_NAMES
        from gaffer.models.persistence import model_exists
        return [n for n in MODEL_NAMES if not model_exists(n)]

    def components(self, *, pred_frame, tg_future, players, avail, pens):
        # Imported in the body because ``advise`` imports this module: the
        # seam has to be declarable without the pipeline that fills it.
        from gaffer.advise import predict_components
        return predict_components(pred_frame, tg_future, players, avail, pens)

    def calibration(self):
        from gaffer.models.persistence import load_model, model_exists
        # An optional artifact: directories trained before calibration
        # existed have no such file, and None is the identity map.
        return load_model("calibration") if model_exists("calibration") else None


class RecordedComponents:
    """A recorded ``inputs/`` directory, so ``gather_inputs`` can run with no
    ``models/`` at all.

    ``calibration`` is ``None``: a fitted model is not a thing this fixture
    records, so a gather under this adapter produces *uncalibrated* expected
    points. That is why the golden's build test loads :class:`Inputs`
    directly (spec §1 part 2) instead of re-gathering.
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)

    def missing(self) -> list[str]:
        return []

    def components(self, *, pred_frame, tg_future, players, avail, pens):
        return pd.read_parquet(self.directory / "comp.parquet")

    def calibration(self):
        return None


class MilpSolver:
    """The shipped solver. Every method is a pass-through, so ``optimize/``
    is untouched and no solve changes (v17g §2.5)."""

    def solve(self, pool, state, **kw):
        return solve_plan(pool, state, **kw)

    def coherent(self, pool, state, decision, **kw):
        return coherent_plan(pool, state, decision, **kw)

    def scenarios(self, pool, state, xmins, **kw):
        return run_scenarios(pool, state, xmins, **kw)

    def alternatives(self, pool, state, plan, **kw):
        return alternative_plans(pool, state, plan, **kw)


# --- the recording (v17g §2.8) ------------------------------------------

FRAMES = ("players", "comp", "components", "ep_named")
"""Fields stored one parquet each. ``ep_by`` and ``my.picks`` have their own."""

INT_KEYED = ("league_eo", "cover", "cap_cover", "rival_captains",
             "rival_names", "dgw_probs", "price_fall")
"""Dicts whose keys are player codes, entry ids or gameweeks. JSON has no
integer keys, so each is restored explicitly on load; a string key here
would silently move the pool."""


def save_inputs(inputs: Inputs, directory: Path | str) -> None:
    """Write ``inputs`` as parquet plus one JSON, under ``directory``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in FRAMES:
        getattr(inputs, name).to_parquet(directory / f"{name}.parquet")
    pd.DataFrame([{"code": c, "gw": g, "ep": v}
                  for (c, g), v in inputs.ep_by.items()]).to_parquet(
        directory / "ep_by.parquet")
    my = None
    if inputs.my is not None:
        inputs.my.picks.to_parquet(directory / "my_picks.parquet")
        my = {k: v for k, v in asdict(inputs.my).items() if k != "picks"}
    scalars = {
        "gw": inputs.gw, "gws": inputs.gws, "deadline": inputs.deadline,
        "through": inputs.through, "gap_warning": inputs.gap_warning,
        "my": my,
        "strategy": None if inputs.strategy is None else asdict(inputs.strategy),
        "win_probs": inputs.win_probs, "priors": inputs.priors,
        "prior_advice": inputs.prior_advice,
        "price_timing": bool(inputs.price_timing),
        **{name: getattr(inputs, name) for name in INT_KEYED},
    }
    (directory / "scalars.json").write_text(
        json.dumps(scalars, indent=1, default=str))


def _int_keys(d: dict | None) -> dict:
    return {int(k): v for k, v in (d or {}).items()}


def load_inputs(directory: Path | str) -> Inputs:
    """Read back what :func:`save_inputs` wrote."""
    directory = Path(directory)
    scalars = json.loads((directory / "scalars.json").read_text())
    frames = {name: pd.read_parquet(directory / f"{name}.parquet")
              for name in FRAMES}
    ep = pd.read_parquet(directory / "ep_by.parquet")
    ep_by = {(int(r.code), int(r.gw)): float(r.ep) for r in ep.itertuples()}

    my = None
    if scalars["my"] is not None:
        my = MyTeam(picks=pd.read_parquet(directory / "my_picks.parquet"),
                    **{**scalars["my"],
                       "chips_by_gw": _int_keys(scalars["my"]["chips_by_gw"])})
    strategy = None
    if scalars["strategy"] is not None:
        strategy = Strategy(**{**scalars["strategy"],
                               "cover_weights": _int_keys(
                                   scalars["strategy"]["cover_weights"])})
    return Inputs(
        gw=int(scalars["gw"]), gws=[int(g) for g in scalars["gws"]],
        deadline=scalars["deadline"], through=scalars["through"],
        gap_warning=scalars["gap_warning"], ep_by=ep_by, my=my,
        strategy=strategy, win_probs=scalars["win_probs"],
        priors=scalars["priors"], prior_advice=scalars["prior_advice"],
        price_timing=bool(scalars["price_timing"]), **frames, **{name: _int_keys(scalars[name]) for name in INT_KEYED})
```

- [ ] **Step 4: Run the tests until they pass**

```
.venv/bin/pytest -q tests/test_inputs.py
```

Expected: all pass. Two failures are likely on the way and both have one
right fix:

- `rival_captains` and `dgw_probs` hold non-`float` values, so `_int_keys`
  must not coerce the value, only the key. It does not — keep it that way.
- `_int_keys` is applied to `rival_names` too, whose values are strings.
  That is correct: the *key* is the entry id.

- [ ] **Step 5: Check nothing else moved**

```
.venv/bin/pytest -q tests/test_inputs.py tests/test_ladder.py tests/test_served_plan.py
```

Expected: all pass. `gaffer.inputs` has no importers yet, so nothing else can
have changed.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/inputs.py tests/test_inputs.py
git commit -m "feat(v17g): the seam — frozen Inputs and Outputs, the Predictions and Solver protocols, and the recording

..."
```

---

## Task 2: the pure cores — `ladder_payload` and the trace context

**Owner:** implementer.

**Files:**
- Modify: `src/gaffer/ladder.py` (`build_ladder`, `sigma_table`; add
  `ladder_payload` and `sigmas_from_components`)
- Modify: `src/gaffer/served.py` (`completed`; add `trace_context`)
- Modify: `src/gaffer/artifacts.py` (`served_plan`'s call to `completed`)
- Test: `tests/test_ladder.py`, `tests/test_served_plan.py`

Two modules, one job: take the file reads out of the two helpers
`build_advice` calls, without changing what either produces.

**Scene.** `build_ladder(gw)` loads the solve state off disk, loads the
components parquet for its σ table, loads the previous advice to mark the
recommended rung, and saves the payload. T4 needs to build a ladder from a
`SolveState` that is still in memory and has not been written yet, so the
solving has to be separable from the loading and the saving. Every existing
caller of `build_ladder(gw)` — the `ladder` job kind and the web router —
must keep working with no change at the call site.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ladder.py`:

```python
def test_ladder_payload_solves_off_a_state_it_was_handed(tmp_path, monkeypatch):
    """v17g §2.2: the pure core takes the board, the bar, the seed, the sigmas
    and the prior advice, so build_advice can call it before anything is
    written."""
    from gaffer.ladder import ladder_payload

    state = _saved_state(tmp_path, monkeypatch)   # the file's existing helper
    payload = ladder_payload(state, gw=state.gw, gws=state.gws, hit_bar=0.6,
                             seed=11, sigmas={}, sigma_source="outcome_only",
                             prior_advice=None, n_draws=64)
    assert payload["gw"] == state.gw
    assert payload["bar"] == 0.6
    assert payload["seed"] == 11
    assert payload["sigma_source"] == "outcome_only"
    assert payload["rungs"]


def test_ladder_payload_writes_nothing(tmp_path, monkeypatch):
    """The whole point of the core: no file, so build_advice stays pure."""
    from gaffer.ladder import ladder_payload

    state = _saved_state(tmp_path, monkeypatch)
    written: list = []
    monkeypatch.setattr("gaffer.ladder.save_ladder",
                        lambda payload, gw: written.append(gw))
    ladder_payload(state, gw=state.gw, gws=state.gws, hit_bar=0.6, seed=11,
                   sigmas={}, sigma_source="outcome_only", prior_advice=None,
                   n_draws=32)
    assert written == []


def test_build_ladder_still_loads_delegates_and_saves(tmp_path, monkeypatch):
    """Its callers — the job kind and the router — pass a gameweek and expect
    a banked payload, and that is unchanged."""
    from gaffer import ladder as ladder_mod

    state = _saved_state(tmp_path, monkeypatch)
    seen, saved = {}, []
    monkeypatch.setattr(ladder_mod, "ladder_payload",
                        lambda st, **kw: seen.update(state=st, **kw) or {"gw": kw["gw"]})
    monkeypatch.setattr(ladder_mod, "save_ladder",
                        lambda payload, gw: saved.append((payload, gw)))
    out = ladder_mod.build_ladder(state.gw)
    assert out == {"gw": state.gw}
    assert saved == [({"gw": state.gw}, state.gw)]
    assert seen["hit_bar"] and seen["seed"] and "sigmas" in seen


def test_sigmas_come_from_a_frame_not_a_file():
    """v17g §2.2: build_advice already holds the components frame the ladder
    used to re-read from parquet."""
    import pandas as pd

    from gaffer.ladder import sigmas_from_components

    sigmas, source = sigmas_from_components(pd.DataFrame())
    assert (sigmas, source) == ({}, "outcome_only")
```

Use the file's existing state-building helper. If `tests/test_ladder.py` has
no helper that saves a `SolveState` and returns it, write `_saved_state` from
the pattern the file's other tests already use, and keep it module-private.

- [ ] **Step 2: Run them and watch them fail**

```
.venv/bin/pytest -q tests/test_ladder.py -k "payload or sigmas or delegates"
```

Expected: `ImportError: cannot import name 'ladder_payload'`.

- [ ] **Step 3: Split `build_ladder`**

In `src/gaffer/ladder.py`:

1. Add, next to `sigma_table`:

```python
def sigmas_from_components(comp) -> tuple[dict[tuple[int, int], float], str]:
    """``{(code, gw): σ}`` off a components frame already in hand, and where
    it came from. v17g §2.2: ``build_advice`` holds the frame this run
    predicted on, so the ladder no longer round-trips it through parquet."""
    bands = bands_by_player_gw(comp)
    if not bands:
        return {}, "outcome_only"
    return {key: float(band.sigma) for key, band in bands.items()}, "bands"
```

and re-express `sigma_table(gw)` as the loading wrapper, unchanged in
behaviour including its printed line:

```python
def sigma_table(gw: int) -> tuple[dict[tuple[int, int], float], str]:
    """``sigmas_from_components`` off the banked frame. ``{}`` with
    ``"outcome_only"`` when no frame is banked, and :func:`draw_points` then
    falls back cell by cell."""
    try:
        comp = load_components(gw)
    except Exception as exc:  # noqa: BLE001 — a ladder is not worth a crash
        print(f"ladder: no component breakdown ({exc})")
        return {}, "outcome_only"
    return sigmas_from_components(comp)
```

2. Rename the body of `build_ladder` to `ladder_payload` with this signature,
   and take out of it the four impure lines — `latest_gw()`,
   `load_solve_state`, `sigma_table`, `load_advice`, `save_ladder`:

```python
def ladder_payload(state, *, gw: int, gws: list[int], hit_bar: float,
                   seed: int, sigmas: dict, sigma_source: str,
                   prior_advice: dict | None,
                   n_draws: int = LADDER_DRAWS) -> dict:
    """Solve every rung off ``state``, score them on shared draws, return the
    payload. v17g §2.2: pure, so ``build_advice`` can call it before anything
    has been written and ``build_ladder`` can call it after loading.
    """
```

Inside, replace:

- `sigmas, sigma_source = sigma_table(gw)` — delete; both are parameters now.
- `recommended, recommended_note = recommended_rung(load_advice(gw), rows)`
  becomes `recommended_rung(prior_advice, rows)`. Keep the `try/except` and
  its printed line: `recommended_rung` can still raise on a malformed
  payload, and a ladder is not worth a crash.
- `hit_bar = _hit_bar()` — delete; it is a parameter.
- the seed default block — delete; it is a parameter.
- `save_ladder(payload, gw)` — delete; the caller saves.
- `horizon`/`gws` derivation — delete; `gws` is a parameter.

3. `build_ladder(gw)` becomes the loading, defaulting and saving wrapper.
   Its defaults are exactly what it computed before, so its callers see no
   change:

```python
def build_ladder(gw: int | None = None, *, n_draws: int = LADDER_DRAWS,
                 seed: int | None = None) -> dict:
    """Load the saved board, solve the ladder off it, bank the payload. The
    job body, and ``advise``'s path before v17g §2.2 moved the solving into
    :func:`ladder_payload`.

    Raises :class:`GafferError` when there is no saved state — the job
    runner's cue to say "run `gaffer advise` first" rather than 500.
    """
    gw = latest_gw() if gw is None else int(gw)
    if gw is None:
        raise GafferError("no saved solve state — run `gaffer advise` first")
    state = load_solve_state(gw)
    horizon = state.opt.get("horizon") or len(state.gws)
    gws = state.gws[:max(1, int(horizon))]
    if seed is None:
        from gaffer.config import config_in_force
        seed = int(config_in_force().scenarios_seed) + SEED_OFFSET + int(gw)
    sigmas, sigma_source = sigma_table(gw)
    try:
        prior_advice = load_advice(gw)
    except Exception as exc:  # noqa: BLE001 — no advice is no mark, not a crash
        print(f"ladder: no served advice to mark ({exc})")
        prior_advice = None
    payload = ladder_payload(state, gw=gw, gws=gws, hit_bar=_hit_bar(),
                             seed=int(seed), sigmas=sigmas,
                             sigma_source=sigma_source,
                             prior_advice=prior_advice, n_draws=n_draws)
    save_ladder(payload, gw)
    return payload
```

**Behaviour to preserve exactly.** `load_advice(gw)` used to raise *inside*
`ladder_payload`'s `try`, which printed `ladder: no served advice to mark
(...)` and set `recommended = None, recommended_note = f"no served advice for
GW{gw}"`. Moving the load out means the note is now produced by
`recommended_rung(None, rows)`. Check what `recommended_rung` returns for
`None` before you finish: if it does not already produce that note, keep the
`None` case inside `ladder_payload` producing the identical string. The
golden compares the served `restraint` block, so a changed note fails the
gate.

- [ ] **Step 3b: `served.completed` stops reading files**

`completed` makes three derivations of its own, and two of them open files:
`config_in_force().price_timing` and the banked price log inside
`price_falls(state)`, and `load_decision_priors()` when the state says the
priors were on (spec §2.3b). `build_advice` already holds all three. Move
them into a helper the loader keeps using, and make `completed` take them:

```python
def trace_context(state) -> tuple[object, bool, dict[int, float]]:
    """``(ft_lambda, price_timing, price_fall)`` for a state read back off
    disk. v17g §2.3b: the three derivations ``completed`` used to make for
    itself, kept for the one caller that has nothing but a state — the
    loader. ``build_advice`` passes its own, because it has them."""
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
    return ft_lambda, price_timing, price_fall


def completed(plan: ServedPlan, *, state, chip_table, ft_lambda,
              price_timing: bool, price_fall: dict[int, float]) -> ServedPlan:
```

Delete the three derivations from `completed`'s body and use the keywords.
Keep every other line of it, including the `generated_at` copy at the end.

In `src/gaffer/artifacts.py`, `served_plan` becomes:

```python
    state = load_solve_state(gw)
    return completed(with_objective_week(plan), state=state,
                     chip_table=raw.get("chip_table"),
                     *(), **dict(zip(("ft_lambda", "price_timing",
                                      "price_fall"), trace_context(state))))
```

— or, more plainly, unpack into three locals first and pass them by name.
Prefer the plain form; this is a loader, not a puzzle.

- [ ] **Step 3c: Test the split**

Add to `tests/test_served_plan.py`:

```python
def test_trace_context_makes_the_three_a_state_alone_can_give():
    """v17g §2.3b: the loader has nothing but a state, so the derivations
    live on for it — and only for it."""
    from gaffer.served import trace_context

    ft_lambda, price_timing, price_fall = trace_context(_state())
    assert price_timing in (True, False)
    assert isinstance(price_fall, dict)


def test_completed_takes_its_trace_context_rather_than_reading_for_it(monkeypatch):
    """The whole point: build_advice calls this and must open nothing."""
    import gaffer.served as served_mod

    monkeypatch.setattr(served_mod, "price_falls", _never_called)
    out = served_mod.completed(_plan(), state=_state(), chip_table=[],
                               ft_lambda=None, price_timing=False,
                               price_fall={})
    assert out.generated_at is not None
```

Update the two existing `completed(...)` calls in that file (lines 304 and
515 on `main`) to pass the three keywords. Their assertions do not change.

- [ ] **Step 4: Run the tests**

```
.venv/bin/pytest -q tests/test_ladder.py
```

Expected: all pass, including every pre-existing test in the file.

- [ ] **Step 5: Run everything that touches the ladder**

```
.venv/bin/pytest -q tests/test_ladder.py tests/test_v16_restraint.py \
  tests/test_served_plan.py tests/test_web_jobs.py tests/test_artifacts.py \
  tests/test_web_plan.py
```

Expected: all pass. If `tests/test_v16_restraint.py` or `tests/test_web_jobs.py`
fails, stop and report — both are protected and the fix is the orchestrator's.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/ladder.py src/gaffer/served.py src/gaffer/artifacts.py \
  tests/test_ladder.py tests/test_served_plan.py
git commit -m "refactor(v17g): the pure cores — ladder_payload solves off a state it is handed, completed takes its trace context

..."
```

---

## Task 3: `advise_source()` and the eighteen redirected pins

**Owner:** **orchestrator.** Fourteen of these pins are in protected rails
(`tests/test_odds.py` and seven `tests/test_v*_degradation.py`); the ruling is
recorded in spec §2.4 and §6.

**Files:**
- Create: `tests/advise_source.py`, `tests/test_advise_source.py`
- Modify (protected, orchestrator's diff): `tests/test_odds.py` (5 pins),
  `tests/test_v4d_degradation.py` (2), `tests/test_v5_degradation.py`,
  `tests/test_v6_degradation.py`, `tests/test_v7_model_degradation.py`,
  `tests/test_v8a_degradation.py`, `tests/test_v8c_degradation.py`,
  `tests/test_v8f_degradation.py`, `tests/test_v12_w3_degradation.py`
- Modify: `tests/test_v12_w3_alt_plans.py` (2), `tests/test_v12_w3_chip_pairs.py`,
  `tests/test_v12_w3_dgw_captain.py`

**Why now, before the split:** at this point `advise_source()` returns exactly
`inspect.getsource(run_advise)`, so every redirected pin reads the same
characters it read before and the whole suite stays green. The commit is
provably a no-op, and when T4 extends the helper the only thing that can
break is T4.

- [ ] **Step 1: Write the helper and its rail**

```python
# tests/advise_source.py
"""The weekly pipeline's source, in pipeline order (v17g §2.4).

Older cycles pinned orderings and wirings by string-matching
``run_advise``'s body, because there was no interface to assert them
through. v17g cut that body into ``gather_inputs`` and ``build_advice`` with
``run_advise`` composing them; the rails still ask the same question of the
same text, so they ask it here. Concatenating in pipeline order is what keeps
an ordering assertion that straddles the split true.

New rails do not belong here. ``build_advice`` is callable now: assert what
the code *did*, the way ``tests/test_advise.py`` does since v17g §5.
"""
from __future__ import annotations

import inspect


def advise_source() -> str:
    from gaffer.advise import run_advise
    return inspect.getsource(run_advise)
```

The helper's own rail goes in `tests/test_advise_source.py`, because
`advise_source.py` does not match `test_*.py` and pytest would never collect
a rail written inside it:

```python
"""v17g §2.4 — the helper the older ordering rails read through."""
from tests.advise_source import advise_source


def test_the_helper_reads_the_whole_weekly_pipeline():
    """Three functions, in pipeline order: an ordering assertion that
    straddles the split is true only if they are concatenated that way."""
    src = advise_source()
    assert "def run_advise(" in src
```

After T4 lands, extend that rail to name all three functions and to assert
the order: `src.index("def gather_inputs(") < src.index("def build_advice(")
< src.index("def run_advise(")`.

- [ ] **Step 2: Redirect all eighteen pins**

In each of the twelve files, replace
`src = inspect.getsource(run_advise)` with `src = advise_source()` and add
`from tests.advise_source import advise_source` to the imports. Two are
shaped differently and keep their shape:

- `tests/test_v12_w3_alt_plans.py:218` — `ast.parse(textwrap.dedent(
  inspect.getsource(run_advise)))` becomes
  `ast.parse(textwrap.dedent(advise_source()))`.
- `tests/test_v8f_degradation.py:319` — `inspect.getsource(advise.run_advise)`
  becomes `advise_source()`.

Leave the assertions themselves untouched, every one. Where the import of
`run_advise` is then unused in a file, remove it; where it is still used by
another test in the same file, leave it.

- [ ] **Step 3: The whole suite, green**

```
.venv/bin/pytest -q
```

Expected: the same pass count as `main` (4,369), no failures. This commit
changes no claim, so any failure is a mistake in the redirect.

- [ ] **Step 4: Verify the redirect is complete**

```
grep -rn "getsource(run_advise)\|getsource(advise.run_advise)" tests/
```

Expected: matches only in `tests/test_advise.py` (T7 removes those) and
`tests/advise_source.py`.

- [ ] **Step 5: Commit — the ruling commit**

```bash
git add tests/advise_source.py tests/test_advise_source.py \
  tests/test_odds.py tests/test_v4d_degradation.py \
  tests/test_v5_degradation.py tests/test_v6_degradation.py \
  tests/test_v7_model_degradation.py tests/test_v8a_degradation.py \
  tests/test_v8c_degradation.py tests/test_v8f_degradation.py \
  tests/test_v12_w3_degradation.py tests/test_v12_w3_alt_plans.py \
  tests/test_v12_w3_chip_pairs.py tests/test_v12_w3_dgw_captain.py
git commit -m "test(v17g): the eighteen source pins outside test_advise read advise_source()

..."
```

The subject must say this is the protected-rail ruling of spec §2.4, and the
body must say that no claim changed and that the helper still returns
``run_advise``'s source alone until the split lands.

---

## Task 4: the split in `src/gaffer/advise.py`

**Owner:** **orchestrator.** `advise.py` is protected; every line of this
diff is the orchestrator's (spec §6).

**Files:**
- Modify: `src/gaffer/advise.py`
- Modify: `tests/advise_source.py` (extend the helper to three functions)

**The rule that makes this reviewable:** the body moves, it does not change.
`build_advice` unpacks `Inputs` into the local names the code uses today, so
every line between the unpacking and the return reads exactly as it does now
(spec §2.4). A diff that renames a local, reorders two calls or "tidies" a
comment is a diff that cannot be gated.

- [ ] **Step 1: `gather_inputs`**

Cut `run_advise` at `pool_ep = tilt_ep(...)`. Everything above becomes:

```python
def gather_inputs(cfg: Config, client: FPLClient | None = None, *,
                  predictions: Predictions | None = None) -> Inputs:
    """Every fetch, every model load and every prediction (v17g §3).

    The impure half of the weekly run, and the reason ``build_advice`` can be
    pure: what crosses the seam is a frozen value, not a client.
    """
```

with these changes and no others:

1. `missing = [n for n in MODEL_NAMES if not model_exists(n)]` becomes
   `missing = predictions.missing()`, after
   `predictions = predictions or LiveModels()`.
2. `comp = predict_components(pred_frame, tg_future, players, avail, pens)`
   becomes `comp = predictions.components(pred_frame=pred_frame,
   tg_future=tg_future, players=players, avail=avail, pens=pens)`.
3. `cal = load_model("calibration") if model_exists("calibration") else None`
   becomes `cal = predictions.calibration()`.
4. Move `components = components_frame(comp, scoring, cal, players, teams)`
   up to sit directly after `rescale_pen_after_blend` (spec §2.6), keeping
   its whole comment and adding one sentence: v17g §2.6 moved it here because
   it takes the calibration model, and the frame is identical because `comp`
   has not moved since the rescale.
5. Add, after the league block:

```python
    # v17g §2.2: the ladder marks the rung this gameweek's *previous* advice
    # recommended. Read here, before anything is written, because the pure
    # build cannot open a file — and because the value is the same either
    # way: nothing writes that file between this line and the ladder.
    try:
        prior_advice = load_advice(gw)
    except Exception as exc:  # noqa: BLE001 — no advice is no mark, not a crash
        print(f"ladder: no served advice to mark ({exc})")
        prior_advice = None
    priors = load_decision_priors() if cfg.decision_priors else None
    dgw_probs = load_chip_scenarios()
```

   moving `priors` and `dgw_probs` up from the build half with their comments
   intact. `ft_lambda = lambda_from_priors(priors)` and
   `chip_thresholds = chip_thresholds_from_asset(priors, dgw_probs)` stay in
   the build half: they are pure derivations, not reads.

   Add beside them the price-timing pair (spec §2.3b). It reads the config
   switch and the banked fall log, and the served plan's trace needs both:

```python
    # v17g §2.3b: the switch and the banked table the served trace charges
    # from. Read here because both are reads; the build is handed the pair.
    price_timing, price_fall = price_falls(
        SimpleNamespace(owned_codes=[] if my is None
                        else my.picks["code"].tolist()))
```

   `price_falls` takes anything with `owned_codes`, and the list is the same
   one `SolveState.owned_codes` gets in the build half — so the value is
   identical to today's, which read it off the state a few lines later.
   `SimpleNamespace` needs `from types import SimpleNamespace` at the top of
   `advise.py`, and `price_falls` an import from `gaffer.served` beside
   `completed`'s.
6. Add `REPORTS.mkdir(exist_ok=True)`, `save_components(components, gw)` and
   `save_availability(avail, gw)` at the end, with the §2.6 rule as their
   comment: gather banks what gather made.
7. Return the `Inputs(...)`, naming all twenty-three fields.

- [ ] **Step 2: `build_advice`**

Everything from `pool_ep = tilt_ep(...)` becomes:

```python
def build_advice(inputs: Inputs, cfg: Config, *,
                 solver: Solver | None = None) -> Outputs:
    """Every solve, the alternatives, the ladder, the served plan, the state
    and the payload — from one frozen value, with no file and no socket
    (v17g §3).

    The locals below are unpacked rather than read through ``inputs.`` at
    each use so that the body is the body that was here before: the ordering
    rails older cycles wrote read this text through
    ``tests/advise_source.py`` (v17g §2.4).
    """
    solver = solver or MilpSolver()
    gw, gws, deadline = inputs.gw, inputs.gws, inputs.deadline
    through, gap_warning = inputs.through, inputs.gap_warning
    players, comp, components = inputs.players, inputs.comp, inputs.components
    ep_named, ep_by, my = inputs.ep_named, inputs.ep_by, inputs.my
    league_eo, cover, cap_cover = inputs.league_eo, inputs.cover, inputs.cap_cover
    rival_captains, rival_names = inputs.rival_captains, inputs.rival_names
    strat, win_probs = inputs.strategy, inputs.win_probs
    priors, dgw_probs = inputs.priors, inputs.dgw_probs
```

with these changes and no others:

1. `build_pool` is told its pool size instead of reading for it (spec
   §2.3b). **Both** calls — the candidate pool and `chip_pool` — become
   `build_pool(..., top_n=cfg.solver_top_n())`. `build_pool` already has the
   parameter, so `optimize/milp.py` does not change. Note that this shifts a
   pinned literal: `"build_pool(players, pool_ep,"` still matches, because
   the addition is at the end of the call.
2. `completed` is given its trace context rather than reading for it:

```python
    served = completed(with_alternatives(served, alt_rows),
                       state=solve_state, chip_table=chip_rows,
                       # v17g §2.3b: completed's own rule, spelled at the
                       # call site. lambda_from_priors(None) is an empty
                       # lookup, not None, so the guard is not optional.
                       ft_lambda=ft_lambda if cfg.decision_priors else None,
                       price_timing=inputs.price_timing,
                       price_fall=inputs.price_fall)
```

3. The four solver calls route through `solver`:
   `solve_plan(pool, state, **solve_kw)` → `solver.solve(pool, state, **solve_kw)`;
   `run_scenarios(...)` → `solver.scenarios(...)`;
   `coherent_plan(pool, state, decision, **solve_kw, p_play=p_play_by_code)` →
   `solver.coherent(...)`;
   `alternative_plans(pool, state, plan, max_gap=..., **solve_kw, **weighted)` →
   `solver.alternatives(...)`. The chip calls do **not** change.
4. `save_solve_state(solve_state)` is deleted — `run_advise` saves it.
5. The ladder block becomes:

```python
    # v13 §3.2 / v16 §4: the transfer ladder, off the state built above.
    # v17g §2.2: off it *in memory* — the state has not been written yet, and
    # the σ table comes from the components frame this run predicted on
    # rather than from the parquet of it. Never the run's failure: a ladder
    # that could not be built is one printed line, the objective's plan
    # served, and a card with a rebuild button.
    ladder = None
    try:
        sigmas, sigma_source = sigmas_from_components(components)
        ladder = ladder_payload(
            solve_state, gw=gw, gws=gws, hit_bar=float(cfg.hit_bar),
            seed=int(cfg.scenarios_seed) + LADDER_SEED_OFFSET + int(gw),
            sigmas=sigmas, sigma_source=sigma_source,
            prior_advice=inputs.prior_advice)
    except Exception as exc:  # noqa: BLE001
        print(f"ladder: not built for GW{gw} ({exc})")
```

   `LADDER_SEED_OFFSET` is `ladder.SEED_OFFSET`, imported under that name so
   the arithmetic is visibly the same as `build_ladder`'s.

   Note the ladder's own `gws` slice: `build_ladder` computes
   `state.gws[:max(1, int(horizon))]`. Pass exactly that, not `gws` — the
   horizon comes from `state.opt["horizon"]` and the two are equal on this
   path, but "equal today" is not the same as "the same expression".
6. `atomic_write(...)`, `save_availability`, `append_advice_history`,
   `save_components` and `REPORTS.mkdir` are deleted — they belong to
   `run_advise` and `gather_inputs`.
7. `return Outputs(advice=advice, state=solve_state, ladder=ladder)`.

- [ ] **Step 3: `run_advise`, the composition**

```python
def run_advise(cfg: Config, client: FPLClient | None = None) -> Advice:
    """The whole weekly pipeline, from live refresh to ``reports/``.

    v17g §3: gather, build, bank. The signature is unchanged, so the CLI, the
    ``train_and_advise`` job, ``pipeline.weekly_run``, the what-if router and
    the golden board all call it exactly as before.
    """
    inputs = gather_inputs(cfg, client)
    out = build_advice(inputs, cfg)
    save_solve_state(out.state)
    if out.ladder is not None:
        save_ladder(out.ladder, inputs.gw)
    # v9c orchestrator-authorized protected edit (review I1): atomic advice
    # artifact write. [keep the whole existing comment, verbatim]
    atomic_write(advice_path(inputs.gw),
                 json.dumps(asdict(out.advice), indent=1, default=str))
    append_advice_history(asdict(out.advice), inputs.gw)
    return out.advice
```

`save_ladder` is imported from `gaffer.ladder`. The v9c rail reads
`inspect.getsource(advise_mod)` — the whole module — and anchors on
`advice_path(gw)`; check it still passes and do **not** adjust it to suit the
code.

- [ ] **Step 4: Extend the helper**

```python
def advise_source() -> str:
    from gaffer.advise import build_advice, gather_inputs, run_advise
    return "\n".join(inspect.getsource(f)
                     for f in (gather_inputs, build_advice, run_advise))
```

- [ ] **Step 5: The suite, then the golden**

```
.venv/bin/pytest -q -x --ignore=tests/test_golden_board.py
.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py
git diff --stat tests/data/golden_board/
```

Expected: the first green apart from `tests/test_advise.py`'s thirty-five
pins, which T7 replaces and which are expected to fail here — record which
ones and why. The second: 45 passed, no skips. The third: **nothing**.

If the golden moves, do not re-record. Find the difference: the likeliest
causes are the ladder's `gws` slice, the σ table's parquet round trip, the
`recommended_rung(None)` note, and the moved `components_frame`.

- [ ] **Step 6: Commit**

```bash
git add src/gaffer/advise.py tests/advise_source.py
git commit -m "refactor(v17g): run_advise is gather then build — the body moved, not one call changed

..."
```

---

## Task 5: the test fixture — `ScriptedSolver` and a tiny board

**Owner:** implementer. Depends on T4.

**Files:**
- Create: `tests/advice_fixture.py`
- Create: `tests/test_advice_fixture.py`

**Scene.** T7 rewrites thirty-five source pins in `tests/test_advise.py` as
assertions about what `build_advice` did. Each one needs an `Inputs` small
enough to read and a solver that answers instantly, because thirty-five real
MILP solves would be a visible tax on every suite run. This task builds both.
Nothing in `src/` changes.

- [ ] **Step 1: Write `tests/advice_fixture.py`**

```python
"""A board small enough to read, and a solver that does not solve (v17g §5).

``tests/test_advise.py`` asserts what ``build_advice`` did with its inputs.
Those claims are about wiring — which pool was built, which plan was served,
which value reached the state — so the plan itself can be scripted, and the
golden board is what proves the real solver is wired the same way.
"""
from __future__ import annotations

import pandas as pd

from gaffer.config import Config
from gaffer.inputs import Inputs
from gaffer.optimize.milp import GwPlan, Plan

GW = 7
GWS = [7, 8]

SQUAD = [("GKP", 2, 45), ("DEF", 6, 50), ("MID", 7, 65), ("FWD", 5, 70)]
"""Position, count, price. Fifteen and a bench, so a real solve is feasible
if a test wants one; the counts are the FPL squad rules, not a guess."""


def tiny_players() -> pd.DataFrame:
    """One row per player, with every column the build half reads: the pool
    (code, position, team_code, now_cost), the alerts
    (price_change_percent, status, chance_of_playing) and the name maps."""
    rows, code = [], 101
    for pos, n, cost in SQUAD:
        for i in range(n + 2):        # two spares per position to buy from
            rows.append({"code": code, "element": code - 100,
                         "name": f"{pos}{i}", "position": pos,
                         "team_code": code % 12, "now_cost": cost + i,
                         "price_change_percent": 0.0, "status": "a",
                         "chance_of_playing": 100})
            code += 1
    return pd.DataFrame(rows)


def tiny_ep(players: pd.DataFrame) -> dict[tuple[int, int], float]:
    """Descending EP by code, so the best fifteen are predictable."""
    return {(int(r.code), g): 8.0 - 0.1 * i
            for i, r in enumerate(players.itertuples()) for g in GWS}


def tiny_comp(players: pd.DataFrame) -> pd.DataFrame:
    """The component frame: what p_play, xmins and the σ bands are read from."""
    return pd.DataFrame([{"code": int(r.code), "gw": g, "p_play": 0.9,
                          "xmins": 80.0, "ep": 5.0, "position": r.position}
                         for r in players.itertuples() for g in GWS])


def tiny_inputs(**over) -> Inputs:
    """A complete Inputs over the tiny board. ``**over`` replaces any field,
    which is how a test says what it is actually about."""
    players = tiny_players()
    ep_by = tiny_ep(players)
    comp = tiny_comp(players)
    ep_named = pd.DataFrame([{"code": c, "gw": g, "ep": v,
                              "name": f"p{c}", "position": "MID"}
                             for (c, g), v in ep_by.items()])
    fields = dict(
        gw=GW, gws=list(GWS), deadline="2026-10-01T17:30:00Z", through=GW - 1,
        gap_warning=None, players=players, comp=comp, components=comp.copy(),
        ep_named=ep_named, ep_by=ep_by, my=None, league_eo={}, cover={},
        cap_cover={}, rival_captains={}, rival_names={}, strategy=None,
        win_probs=[], priors=None, dgw_probs={}, prior_advice=None,
        price_timing=False, price_fall={})
    fields.update(over)
    return Inputs(**fields)


def tiny_cfg(**over) -> Config:
    """The knobs the build reads. The sweep and the alternatives are off by
    default: a test that wants either says so, and pays for it."""
    fields = dict(entry_id=1, league_id=0, horizon=len(GWS), scenarios_n=0,
                  alt_plan_max_gap=0.0, decision_priors=False,
                  price_timing=False)
    fields.update(over)
    return Config(**fields)


def a_plan(*, buys=(), sells=(), hits=0, squad=None, xi=None, bench=None,
           captain=None, vice=None, objective=60.0) -> Plan:
    """A scripted Plan over the tiny board: fifteen owned, eleven starting."""
    players = tiny_players()
    codes = [int(c) for c in players["code"]][:15]
    squad = list(squad or codes)
    xi = list(xi or squad[:11])
    bench = list(bench or squad[11:])
    weeks = [GwPlan(gw=g, buys=list(buys) if g == GW else [],
                    sells=list(sells) if g == GW else [],
                    hits=hits if g == GW else 0, squad=squad, xi=xi,
                    bench=bench, captain=captain or xi[0],
                    vice=vice or xi[1],
                    # The solver's own objective, in tilted units. Nothing on
                    # the build path reads it — ``advise.raw_xi_pts`` re-sums
                    # the untilted ep_by over ``xi`` — and ``xi_rows`` has no
                    # reader outside optimize/milp.py at all.
                    xi_rows=[], expected_pts=objective) for g in GWS]
    return Plan(gw_plans=weeks, objective=objective)


class ScriptedSolver:
    """Answers every call from a script and records what it was asked.

    The recording is the point: a claim like "the chips are priced on an
    untilted pool" is a claim about the pool a call *received*, and this is
    where a test can see it.
    """

    def __init__(self, *, plan=None, coherent=None, scenarios=None,
                 alternatives=()):
        self._plan = plan
        self._coherent = coherent
        self._scenarios = scenarios
        self._alternatives = list(alternatives)
        self.calls: list[tuple[str, dict]] = []

    @property
    def names(self) -> list[str]:
        """The call order, which is what an ordering pin used to assert by
        reading the source."""
        return [name for name, _ in self.calls]

    def _record(self, name, **kw):
        self.calls.append((name, kw))

    def solve(self, pool, state, **kw):
        self._record("solve", pool=pool, state=state, **kw)
        return self._plan or a_plan()

    def coherent(self, pool, state, decision, **kw):
        self._record("coherent", pool=pool, state=state, decision=decision, **kw)
        return self._coherent or self._plan or a_plan()

    def scenarios(self, pool, state, xmins, **kw):
        self._record("scenarios", pool=pool, state=state, xmins=xmins, **kw)
        return self._scenarios

    def alternatives(self, pool, state, plan, **kw):
        self._record("alternatives", pool=pool, state=state, plan=plan, **kw)
        return self._alternatives
```

`GwPlan` and `Plan` are in `src/gaffer/optimize/milp.py:182` and `:207`.
`GwPlan` has eleven required fields and one defaulted (`bank`); `Plan` takes
`objective` and `gw_plans` with `gap` defaulted. Read both field lists and
match them: if a field has been appended since this plan was written, add it
with the module's default and say nothing else about it.

`ScriptedSolver.scenarios` returning `None` is deliberate: a build with
`scenarios_n = 0` never calls it, and a test that wants a sweep passes a
`ScenarioRun`.

- [ ] **Step 2: Write `tests/test_advice_fixture.py`**

```python
"""If the fixture cannot build, every test that uses it is testing the
fixture rather than the code (v17g §5)."""
from __future__ import annotations

import pytest

from gaffer.advise import build_advice
from tests.advice_fixture import (GW, ScriptedSolver, a_plan, tiny_cfg,
                                  tiny_inputs)


def test_the_tiny_board_builds_an_advice_end_to_end():
    out = build_advice(tiny_inputs(), tiny_cfg(), solver=ScriptedSolver())
    assert out.advice.gw == GW
    assert out.state.gw == GW
    assert len(out.advice.xi) == 11
    assert out.advice.captain["code"]


def test_the_scripted_solver_records_the_pool_and_the_state_it_was_handed():
    solver = ScriptedSolver()
    build_advice(tiny_inputs(), tiny_cfg(), solver=solver)
    assert solver.names[0] == "solve"
    name, kw = solver.calls[0]
    assert list(kw["pool"].columns) == ["code", "position", "team_code",
                                        "cost", "sell", "ep"]
    assert kw["state"].gws == [7, 8]


def test_a_scripted_captain_reaches_the_served_plan():
    plan = a_plan(captain=104, vice=105)
    out = build_advice(tiny_inputs(), tiny_cfg(),
                       solver=ScriptedSolver(plan=plan))
    assert out.advice.captain["code"] == 104
    assert out.advice.vice["code"] == 105


@pytest.mark.slow
def test_the_tiny_board_also_solves_for_real():
    """One real MILP over the fixture, so the shape is known to be solvable
    and a test that wants the real solver can have it."""
    from gaffer.inputs import MilpSolver

    out = build_advice(tiny_inputs(), tiny_cfg(), solver=MilpSolver())
    assert len(out.advice.xi) == 11
    assert out.advice.expected_pts > 0
```

If `slow` is not already a registered marker in `pyproject.toml` or
`pytest.ini`, drop the decorator rather than registering a new one — a
warning about an unknown mark is noise, and this file is four tests.

- [ ] **Step 2b: Close the `Solver` protocol's second adapter**

`tests/test_inputs.py`'s `test_every_protocol_has_two_adapters` (T1) can name
only `MilpSolver`, because the second adapter is the one you have just
written. Spec §5 asks for two per protocol, so add to
`tests/test_advice_fixture.py`:

```python
def test_the_scripted_solver_is_the_protocol_s_second_adapter():
    """The review's test for a seam that is real rather than hypothetical:
    one adapter is a hypothetical seam, two make it a real one."""
    from gaffer.inputs import Solver

    assert isinstance(ScriptedSolver(), Solver)
```

- [ ] **Step 3: Run**

```
.venv/bin/pytest -q tests/test_advice_fixture.py --durations=5
```

Expected: all pass, the whole file under **ten seconds**. If the real solve
is slower, cut `GWS` to one gameweek and say why in the docstring; do not
silence it with a skip.

- [ ] **Step 4: Commit**

```bash
git add tests/advice_fixture.py tests/test_advice_fixture.py
git commit -m "test(v17g): a tiny board and a scripted solver, so the wiring can be asserted in milliseconds

..."
```

---

## Task 6: the golden board's recorded `Inputs`

**Owner:** implementer writes the harness and the tests; **the orchestrator
records the fixture and runs the gate** (CONVENTIONS §7).

**Files:**
- Modify: `tests/golden_client.py`
- Modify: `tests/test_golden_board.py`
- Create (orchestrator, by running the recorder):
  `tests/data/golden_board/inputs/`

- [ ] **Step 1: Record `Inputs` from `write_expected`**

In `tests/golden_client.py`, add beside `EXPECTED_DIR`:

```python
INPUTS_DIR = "inputs"
"""The recorded Inputs (v17g §2.8). Written by ``--write`` beside
``expected/``, so one command still re-records everything after a retrain."""
```

and a sibling of `run_golden` that gathers rather than runs:

```python
def gather_golden(root: Path, client: FPLClient | None = None):
    """``gather_inputs(golden_config(), client)`` inside ``golden_cwd``.

    The recorded half of the split: what ``build_advice`` is given, so the
    golden can build the same board on a machine with no ``models/``.
    """
    from gaffer.advise import gather_inputs

    client = client if client is not None else RecordedClient()
    with golden_cwd(root, client):
        return gather_inputs(golden_config(), client)
```

In `write_expected`, after the expected files are written, add — using
`root`, which is what that function calls its scratch tree, and
`RecordedClient(golden)`, which is the client it already passes to
`run_golden` for the same reason (the golden's own bundle, not
`GOLDEN_DIR`'s):

```python
    save_inputs(gather_golden(root, RecordedClient(golden)),
                golden / INPUTS_DIR)
```

Recording now gathers once and runs once; say so in `write_expected`'s
docstring.

**And add a third mode to `main`,** because `--write` rewrites `expected/`
and stamps a fresh `written_at`, `commit` and `runtime_s` into the header —
churn this cycle must not create, since its whole claim is that the board
did not move:

```python
    mode.add_argument("--inputs", action="store_true",
                      help="record only the Inputs (v17g §2.8); the expected "
                           "files and the header are left alone")
```

with the branch:

```python
    if args.inputs:
        root = Path(tempfile.mkdtemp(prefix="golden-inputs-"))
        print(f"scratch: {root}", file=sys.stderr)
        build_scratch_tree(root, _repo_root(), GOLDEN_DIR)
        save_inputs(gather_golden(root, RecordedClient()),
                    GOLDEN_DIR / INPUTS_DIR)
        print(f"inputs: {GOLDEN_DIR / INPUTS_DIR}")
        return 0
```

placed before the `record()`/`write_expected()` line, since it returns its
own exit code and has no header to report levers from. Update the parser's
`description` to name all three modes.

- [ ] **Step 2: The five new tests**

Append to `tests/test_golden_board.py`:

```python
def _built_from_inputs():
    """``build_advice`` over the recorded Inputs, serialized the way
    ``run_advise`` serializes it, so the comparison is like for like."""
    from dataclasses import asdict

    from gaffer.advise import build_advice
    from gaffer.inputs import load_inputs

    inputs = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
    out = build_advice(inputs, gc.golden_config())
    advice = json.loads(json.dumps(asdict(out.advice), default=str))
    return out, advice


@pytest.mark.golden
def test_the_recorded_inputs_build_the_same_advice_with_no_models(tmp_path):
    """Spec §1 part 2. No hash guard and no module fixture: the point of this
    test is that it runs where the others cannot."""
    if not (gc.GOLDEN_DIR / gc.INPUTS_DIR).exists():
        pytest.skip("inputs not recorded yet (python -m tests.golden_client --write)")
    _, advice = _built_from_inputs()
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())
    cwd = str(Path.cwd())
    assert gc.strip_volatile(advice, cwd) == gc.strip_volatile(expected, cwd)


@pytest.mark.golden
def test_the_recorded_inputs_build_the_same_solve_state(tmp_path, monkeypatch):
    """The state is compared through its own writer, because that writer is
    what made the expected file: the pool goes to parquet and the scalars to
    JSON, and re-deriving that here would be a second opinion."""
    if not (gc.GOLDEN_DIR / gc.INPUTS_DIR).exists():
        pytest.skip("inputs not recorded yet")
    from gaffer.artifacts import save_solve_state

    out, _ = _built_from_inputs()
    monkeypatch.chdir(tmp_path)
    save_solve_state(out.state)
    written = json.loads(
        (tmp_path / "reports" / f"solve_state_gw{out.state.gw}.json").read_text())
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "solve_state.json").read_text())
    cwd = str(tmp_path)
    assert gc.strip_volatile(written, cwd) == gc.strip_volatile(expected, cwd)


@pytest.mark.golden
def test_build_advice_opens_no_file(monkeypatch):
    """Spec §1 part 4, the run-time half. A hidden read cannot hide behind a
    swallowed exception — ``ladder._hit_bar`` falls back silently — so this
    asserts the numbers, not the absence of a traceback."""
    if not (gc.GOLDEN_DIR / gc.INPUTS_DIR).exists():
        pytest.skip("inputs not recorded yet")
    # Every module build_advice reaches, imported before open() is taken
    # away: an import that is not yet in sys.modules opens a file.
    import gaffer.advise, gaffer.config, gaffer.ladder, gaffer.served  # noqa: F401
    from gaffer.inputs import load_inputs

    inputs = load_inputs(gc.GOLDEN_DIR / gc.INPUTS_DIR)
    expected = json.loads(
        (gc.GOLDEN_DIR / gc.EXPECTED_DIR / "advice.json").read_text())

    real_open = open

    def refuse(*a, **kw):
        raise AssertionError(f"build_advice opened {a[:1]}")

    monkeypatch.setattr("builtins.open", refuse)
    try:
        from dataclasses import asdict

        from gaffer.advise import build_advice
        out = build_advice(inputs, gc.golden_config())
    finally:
        monkeypatch.setattr("builtins.open", real_open)
    advice = json.loads(json.dumps(asdict(out.advice), default=str))
    cwd = str(Path.cwd())
    assert gc.strip_volatile(advice, cwd) == gc.strip_volatile(expected, cwd)


def test_build_advice_names_no_reader_in_its_source():
    """Spec §1 part 4, the static half."""
    import inspect

    from gaffer.advise import build_advice

    src = inspect.getsource(build_advice)
    for token in ("open(", "Path(", "client.", "load_", "save_", "store.",
                  "atomic_write"):
        assert token not in src, token


def test_every_inputs_field_is_read_by_build_advice():
    """Spec §2.7: a field nothing reads is a field the golden has to record
    and keep correct for no reader."""
    import dataclasses
    import inspect

    from gaffer.advise import build_advice
    from gaffer.inputs import Inputs

    src = inspect.getsource(build_advice)
    for f in dataclasses.fields(Inputs):
        assert f.name in src, f.name
```

Two warnings about the purity test. `monkeypatch.setattr("builtins.open",
...)` breaks pytest's own machinery on failure, which is why the real `open`
goes back in a `finally` before any assertion runs. And `pd.read_parquet`
opens files, so `load_inputs` is called *before* the patch, not inside it.

- [ ] **Step 3: Run what you can**

```
.venv/bin/pytest -q tests/test_golden_board.py -m "not golden"
```

Expected: pass, including the two new unmarked rails. The `golden`-marked
tests need the fixture the orchestrator records next; report
`DONE_WITH_CONCERNS` naming them rather than hand-skipping them.

- [ ] **Step 4 (orchestrator): record and gate**

```
PYTHONPATH=. .venv/bin/python -m tests.golden_client --inputs
git status --short tests/data/golden_board/
.venv/bin/pytest -q tests/test_golden_board.py tests/test_pipeline.py
mv models models.off && .venv/bin/pytest -q tests/test_golden_board.py -k inputs; mv models.off models
du -sk tests/data/golden_board
```

Expected: `inputs/` appears as the only untracked path and **nothing under
`expected/` or `header.json` is modified** — that is what `--inputs` is for.
The models-absent run passes and does not skip. The directory stays under
5,120 KB.

The `--write` path is still the one to use after a retrain, and it now
records the Inputs too. It is not used here, because it would restamp the
header and rewrite the expected files this cycle claims are unmoved.

- [ ] **Step 5: Commit**

```bash
git add tests/golden_client.py tests/test_golden_board.py tests/data/golden_board/inputs
git commit -m "test(v17g): the golden's recorded Inputs — the same board, built with no models on disk

..."
```

---

## Task 7: `tests/test_advise.py` — the thirty-five pins

**Owner:** **orchestrator.** The file is protected (spec §6).

**Files:**
- Modify: `tests/test_advise.py`

Every pin becomes a test of the same claim, with the same sentence for a
name and its docstring's provenance kept. The table below is the whole task;
each row is one commit-sized unit and the file must be green after each.

| Pins | Claim | Becomes |
|---|---|---|
| 82, 104, 590, 1002-style | the league is read before the tilt, and the tilt before the pool | build with a `ScriptedSolver`, assert the pool it was handed carries tilted EP and the advice reports raw EP |
| 168 | GW1 falls back to the initial squad | `tiny_inputs(my=None)`, assert `mode == "initial_squad"` and fifteen buys |
| 189 | buys are tagged only when league ownership is known | build with `league_eo={}` and with a map; assert the tags |
| 228 | chips are scored on an untilted pool | `ScriptedSolver` plus a stubbed `evaluate_chips`; assert the pool it saw |
| 244 | raw XI points, not the tilted objective | assert `expected_pts` against `raw_xi_pts` |
| 275 | the components file and the solve state are persisted | assert `gather_inputs` wrote the components and `run_advise` wrote the state |
| 303 | a position map beside the name map | assert every served move carries `position` |
| 331 | the data gap is recorded after the refresh | assert `Inputs.through` and the advice's two fields |
| 345, 358, 371, 510, 521, 533, 544, 555 | the scenario block: gated on config, after the deterministic solve, never on `pool_ep`, the seed moves with the gameweek, an empty xmins warns, a dead sweep says so, the captain frequency belongs to the captain | `ScriptedSolver` recording the sweep's kwargs and returning a scripted run |
| 384, 455 | the protected ordering, whole | one test asserting the call order the `ScriptedSolver` recorded |
| 417 | `SolveState.opt` stays JSON-serializable | `json.dumps(out.state.opt)` |
| 432, 445, 474, 488 | the priors: resolved before solving, switchable off, the craft knobs, recorded as on | assert `opt` and the solver's kwargs |
| 572 | the cover table is built inside the league block | now a `gather_inputs` test with a fake client |
| 606 | the captain is re-picked after the plan is fixed | build with `lam` and a cover map; assert `captain` and `demoted_captain` |
| 663 | the shadow log is written before EP is assembled | a `gather_inputs` test with a recording stub |
| 744 | the penalty priors are built before predicting | a `gather_inputs` test asserting `pens` reached `Predictions.components` |
| 768 | availability and history are persisted | assert both files after `run_advise` on the tiny board |
| 788 | the caps reach the weekly `SolveInput` | assert the state the `ScriptedSolver` was handed |
| 821 | the ladder is built after the state and never fails the run | assert `Outputs.ladder`, then a raising `ladder_payload` leaves the advice served |
| 258, 647, 729 | `predict_components`: the pre-blend team output, the flags-only shadow columns, penalties priced after availability | call `predict_components` with small frames and a stubbed `load_model` |

- [ ] **Step 1** Rewrite the file, row by row, running
  `.venv/bin/pytest -q tests/test_advise.py` after each.
- [ ] **Step 2** `grep -c "inspect.getsource" tests/test_advise.py` prints `0`.
- [ ] **Step 3** `.venv/bin/pytest -q --ignore=tests/test_golden_board.py`
  is green.
- [ ] **Step 4** Commit, with the ruling in the body: the pins are replaced,
  not deleted, and the claim each one made is named.

---

## After the tasks

The orchestrator runs the four-part gate of spec §1 in full, writes the
verdict into the spec's §9 Outcome with the numbers, and then:
ff-merge to `main`, push, the security ritual from `CLAUDE.md` (both greps
and the `git show`), the ROADMAP block, `docs/GUIDE.md` §11 and §10 (the
golden now runs without models), the tracker's ledger row, its eleven boxes
and the v17g hand-off note, and the memory line. Screenshots are n/a: this
cycle changes no pixel.
