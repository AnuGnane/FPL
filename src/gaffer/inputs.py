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
from dataclasses import asdict, dataclass
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
        price_timing=bool(scalars["price_timing"]), **frames,
        **{name: _int_keys(scalars[name]) for name in INT_KEYED})
