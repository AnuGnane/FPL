"""The seam ``run_advise`` is composed from (v17g §3).

``gather_inputs`` fills an :class:`Inputs` — every fetch, every model load
and every prediction — and ``build_advice`` reads one and returns an
:class:`Outputs`. Everything impure is on the gather side, which is what
makes the build a pure function of one frozen value: testable with no
models, no network and no ``reports/``.

Two protocols hide what the two halves still depend on. :class:`Predictions`
is the three places gather touches ``models/``; :class:`Solver` is the four
calls that produce a :class:`~gaffer.optimize.milp.Plan`. Two adapters is the
review's test for a seam that is real rather than hypothetical:
:class:`Predictions` has both of its own here, and the second :class:`Solver`
— the tests' scripted one — arrives with the fixture that needs it.
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
    from gaffer.optimize.milp import Plan
    from gaffer.optimize.scenarios import ScenarioRun


@dataclass(frozen=True)
class Inputs:
    """Everything ``build_advice`` reads, and nothing it does not (v17g §2.7).

    Enforced by a rail rather than by care, because a field
    ``build_advice`` never names is a field the golden has to record and keep
    correct for no reader: ``tests/test_golden_board.py``'s
    ``test_every_inputs_field_is_read_by_build_advice`` lands with the
    recording that would have to carry it.
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
    # v17g §2.3b: the ladder's step reasons rate a fixture through the
    # ticker, which reads the snapshots. Gathered here so a replay from a
    # recorded board cannot pick up the machine's own week instead.
    difficulty: dict[tuple[int, int], float]


@dataclass(frozen=True)
class Outputs:
    """What a build produced: the payload, the board it solved on, and the
    ladder. ``run_advise`` banks all three; nothing here has been written yet.
    """

    advice: Advice
    state: SolveState
    ladder: dict | None


@runtime_checkable
class Predictions(Protocol):
    """The three places the weekly run touches ``models/`` (v17g §2.5)."""

    def missing(self) -> list[str]: ...

    def components(self, *, pred_frame, tg_future, players, avail,
                   pens) -> pd.DataFrame: ...

    def calibration(self) -> object | None: ...


@runtime_checkable
class Solver(Protocol):
    """The four calls that produce a plan. Chip pricing is deliberately not
    here: it answers what a chip is worth against a baseline, not what to do
    this week, and a protocol for it would be a third seam nobody needs.

    The parameter names are ``optimize/``'s own, ``incumbent`` included, so a
    reader can follow a call through the adapter without a translation step.
    """

    def solve(self, pool, state, **kw) -> Plan: ...

    def coherent(self, pool, state, decision, **kw) -> Plan: ...

    def scenarios(self, pool, state, xmins, **kw) -> ScenarioRun: ...

    def alternatives(self, pool, state, incumbent, **kw) -> list[Plan]: ...


class LiveModels:
    """The real ``models/`` directory."""

    def missing(self) -> list[str]:
        from gaffer.advise import MODEL_NAMES
        from gaffer.models.persistence import model_exists
        return [n for n in MODEL_NAMES if not model_exists(n)]

    def components(self, *, pred_frame, tg_future, players, avail,
                   pens) -> pd.DataFrame:
        # Imported in the body because ``advise`` imports this module: the
        # seam has to be declarable without the pipeline that fills it.
        from gaffer.advise import predict_components
        return predict_components(pred_frame, tg_future, players, avail, pens)

    def calibration(self) -> object | None:
        from gaffer.models.persistence import load_model, model_exists
        # An optional artifact: directories trained before calibration
        # existed have no such file, and None is the identity map.
        return load_model("calibration") if model_exists("calibration") else None


class RecordedComponents:
    """A recorded ``inputs/`` directory, so ``gather_inputs`` can run with no
    ``models/`` at all.

    ``filename`` holds the frame as :func:`~gaffer.advise.predict_components`
    returned it, which is *not* ``Inputs.comp``: the blend and
    :func:`~gaffer.set_pieces.rescale_pen_after_blend` run between the two,
    and the rescale keys off ``BLEND_MARKER``, a column the blend writes and
    the recording therefore carries. Serving ``comp`` here would send an
    already-rescaled frame back through the rescale, quietly taking
    ``ep_pen_taker`` down by the blend weight a second time.

    ``calibration`` is ``None``: a fitted model is not a thing this fixture
    records, so a gather under this adapter produces *uncalibrated* expected
    points. That is why the golden's build test loads :class:`Inputs`
    directly (spec §1 part 2) instead of re-gathering.
    """

    def __init__(self, directory: Path | str, *,
                 filename: str = "predicted.parquet") -> None:
        self.directory = Path(directory)
        self.filename = filename

    def missing(self) -> list[str]:
        return []

    def components(self, *, pred_frame, tg_future, players, avail,
                   pens) -> pd.DataFrame:
        return pd.read_parquet(self.directory / self.filename)

    def calibration(self) -> object | None:
        return None


class MilpSolver:
    """The shipped solver. Every method is a pass-through, so ``optimize/``
    is untouched and no solve changes (v17g §2.5)."""

    def solve(self, pool, state, **kw) -> Plan:
        return solve_plan(pool, state, **kw)

    def coherent(self, pool, state, decision, **kw) -> Plan:
        return coherent_plan(pool, state, decision, **kw)

    def scenarios(self, pool, state, xmins, **kw) -> ScenarioRun:
        return run_scenarios(pool, state, xmins, **kw)

    def alternatives(self, pool, state, incumbent, **kw) -> list[Plan]:
        return alternative_plans(pool, state, incumbent, **kw)


# --- the recording (v17g §2.8) ------------------------------------------

FRAMES = ("players", "comp", "components", "ep_named")
"""Fields stored one parquet each. ``my.picks`` has its own beside them."""

EP_BY = "ep_by"
DIFFICULTY = "difficulty"

PAIR_KEYED = {EP_BY: ("code", "gw", "ep"),
              DIFFICULTY: ("team_code", "gw", "difficulty")}
"""Dicts keyed on a pair, each its own parquet of one row per key: JSON has
no tuple keys, and a frame of three columns is the one shape that keeps
``(code, gw) -> ep`` exact. The value under each name is the three column
headings, in order. A map with no rows is a real recording — the ticker
answers with an empty one for a week it cannot rate — and reads back as the
empty dict it was."""

INT_KEYED = ("league_eo", "cover", "cap_cover", "rival_captains",
             "rival_names", "dgw_probs", "price_fall")
"""Dicts whose keys are player codes, entry ids or gameweeks. JSON has no
integer keys, so each is written and restored through :func:`_int_keys`; a
string key here would silently move the pool."""

SCALARS = ("gw", "gws", "deadline", "through", "gap_warning", "my",
           "strategy", "win_probs", "priors", "prior_advice", "price_timing")
"""The rest of ``scalars.json``. Named rather than only written, so a rail can
add the four groups up and see whether a new field would be dropped on save
and silently defaulted on load."""


def _jsonable(o):
    """A numpy scalar keeps its number; anything else is a bug, loudly.

    v17g §2.8: ``default=str`` would record ``np.int64(100)`` as ``"100"``,
    and a code that is a string matches no row in the pool. Native ints are
    what pandas 3 hands this module today, so this is insurance against the
    pandas the fixture is read back under rather than a bug being fixed.
    """
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"{type(o).__name__} is not recordable: {o!r}")


def _int_keys(d: dict | None) -> dict:
    """Keys to ``int``, values untouched — ``rival_captains`` holds codes and
    ``rival_names`` holds strings, and neither is a float."""
    return {int(k): v for k, v in (d or {}).items()}


def _int_or_none(v) -> int | None:
    """``through`` gets the same coercion as ``gw``, and ``None`` survives it:
    nothing ingested yet is not gameweek zero."""
    return None if v is None else int(v)


def save_inputs(inputs: Inputs, directory: Path | str) -> None:
    """Record ``inputs`` so a later run can build from it with no models.

    Parquet per frame plus one JSON rather than a pickle (v17g §2.8): the
    fixture has to stay readable, diffable and loadable under the pandas
    versions it is meant to outlive.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in FRAMES:
        getattr(inputs, name).to_parquet(directory / f"{name}.parquet")
    for name, (left, right, value) in PAIR_KEYED.items():
        pd.DataFrame([{left: a, right: b, value: v}
                      for (a, b), v in getattr(inputs, name).items()]
                     ).to_parquet(directory / f"{name}.parquet")
    my = None
    if inputs.my is not None:
        inputs.my.picks.to_parquet(directory / "my_picks.parquet")
        # From ``fields`` rather than ``asdict``, which would deep-copy the
        # picks frame only for the next expression to drop it.
        my = {f.name: getattr(inputs.my, f.name)
              for f in fields(inputs.my) if f.name != "picks"}
    scalars = {
        # The three below are named in ``SCALARS`` and overwritten here,
        # because JSON holds neither a dataclass nor whatever flavour of
        # ``bool`` the config layer handed over.
        **{name: getattr(inputs, name) for name in SCALARS},
        "my": my,
        "strategy": None if inputs.strategy is None else asdict(inputs.strategy),
        "price_timing": bool(inputs.price_timing),
        **{name: _int_keys(getattr(inputs, name)) for name in INT_KEYED},
    }
    (directory / "scalars.json").write_text(
        json.dumps(scalars, indent=1, default=_jsonable))


def load_inputs(directory: Path | str) -> Inputs:
    """Rebuild the :class:`Inputs` :func:`save_inputs` wrote.

    Every integer key and scalar is restored as an ``int`` on the way out,
    because JSON has neither (v17g §2.8) and a string where the pool expects
    a code fails as a missing row rather than as an error.
    """
    directory = Path(directory)
    scalars = json.loads((directory / "scalars.json").read_text())
    frames = {name: pd.read_parquet(directory / f"{name}.parquet")
              for name in FRAMES}
    pairs = {}
    for name, (left, right, value) in PAIR_KEYED.items():
        frame = pd.read_parquet(directory / f"{name}.parquet")
        # ``itertuples`` and not ``iterrows``: the row-as-Series would put
        # three columns through one dtype, and a code is not a float.
        pairs[name] = {(int(getattr(r, left)), int(getattr(r, right))):
                       float(getattr(r, value)) for r in frame.itertuples()}

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
        deadline=scalars["deadline"], through=_int_or_none(scalars["through"]),
        gap_warning=scalars["gap_warning"], **pairs, my=my,
        strategy=strategy, win_probs=scalars["win_probs"],
        priors=scalars["priors"], prior_advice=scalars["prior_advice"],
        price_timing=bool(scalars["price_timing"]), **frames,
        **{name: _int_keys(scalars[name]) for name in INT_KEYED})
