"""v7b: the flagged 2025-26 gated replay driver — the whole run matrix.

**Its defaults are exactly ``scripts/s2_replay.py``'s configuration.** With
``--arm heur|estimation``, ``--seed-base 20260827``, ``--chips``, ``--priors
current``, ``--minutes current``, ``--frame current`` and ``--n 40`` nothing is
monkeypatched beyond the two things s2 also patched (the per-arm log store and
the noise loader), the seed arithmetic is the same ``base + gw``, and the noise
resolution is the same shipping path. ``tests/test_v7b_driver.py`` pins that
rail: if any default drifts, the off-state test fails before a replay is spent.

``scripts/s2_replay.py`` itself is never edited — it is the S2 record. This
script is its body split into four testable pieces.

Which arm answers which question:

  ``--arm raw``          no gate at all — the ungated reference line.
  ``--arm heur``         Q1/Q2: the pre-v6 ``(92 - xmins) / 134`` heuristic,
                         loader pinned to ``None`` so the v4c noise runs
                         draw-for-draw.
  ``--arm estimation``   Q1: the fitted estimation σ table via ``--noise-asset``.
  ``--arm composite``    Q3: one floor's ``sqrt(σ_est² + floor²)`` table from
                         ``scripts/v7b_composite.py``. The payload must carry
                         ``composite_floor`` or the run is refused — an arm
                         tagged composite that is really the plain estimation
                         table is a silently wrong measurement.

``--minutes legacy`` and ``--frame v4c`` are the **Q2 ablations, run on current
code** rather than as historical checkouts (facts F1/F2). ``--minutes legacy``
patches ``gaffer.models.train.ThreeModeModel`` — the name ``train_all``
actually constructs, including through ``fit_calibration``'s recursive call —
with the verbatim pre-v5 head vendored in ``scripts/v7b_legacy_minutes.py``.
``--frame v4c`` neutralises the v5 training-frame additions (``cup_matches``
and ``add_shrunken_modes``). ``--no-chips`` and ``--priors off`` reproduce the
v4c D1 *harness*, which the current harness does not match (fact F3).

Every arm needs its own ``--tag``: it owns
``live/backtest_log_v7b_<tag>.parquet`` and ``reports/v7b_<tag>.json``. Two
arms sharing a tag is a corrupted measurement.

Usage (orchestrator only — Group 1 builds this and does not run it)::

    caffeinate -i nohup .venv/bin/python scripts/v7b_replay.py \\
        --arm heur --tag q1b-heur --seed-base 20260901 \\
        > logs/v7b_q1b-heur.log 2>&1 &
    grep V7B_ARM_DONE logs/v7b_*.log
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gaffer.backtest as bt
import gaffer.features.engineer as eng
import gaffer.models.train as tr
import gaffer.optimize.scenarios as sc
from gaffer.data import store as bt_store
from gaffer.optimize.policy import Thresholds, coherent_plan, decide
from gaffer.optimize.scenarios import (move_frequencies, run_scenarios,
                                       xmins_by_player_gw)

from v7b_legacy_minutes import LegacyMinutesModel

SHARED_LOG = "live/backtest_log.parquet"
TABLE_ARMS = ("estimation", "composite")


@dataclass
class ArmConfig:
    """One replay arm. Every default is the S2 configuration."""

    arm: str
    tag: str
    seed_base: int = 20260827
    n: int = 40
    chips: bool = True
    priors: str = "current"
    minutes: str = "current"
    frame: str = "current"
    noise_asset: str | None = None
    log_path: str = field(init=False)
    report_path: str = field(init=False)

    def __post_init__(self) -> None:
        self.log_path = f"live/backtest_log_v7b_{self.tag}.parquet"
        self.report_path = f"reports/v7b_{self.tag}.json"

    def echo(self) -> dict:
        return {"arm": self.arm, "tag": self.tag, "seed_base": self.seed_base,
                "n": self.n, "chips": self.chips, "priors": self.priors,
                "minutes": self.minutes, "frame": self.frame,
                "noise_asset": self.noise_asset}


class _ArmStore:
    """``backtest.store`` with the one racy write redirected per arm.

    ``run_backtest`` hard-codes ``live/backtest_log.parquet``; two concurrent
    arms would race on it and each driver would read the other's hits and
    transfers. Same proxy as ``scripts/s2_replay.py``, with the redirect target
    a constructor argument instead of a module global.
    """

    def __init__(self, arm_log: str):
        self._arm_log = arm_log

    def __getattr__(self, name):
        return getattr(bt_store, name)

    def save(self, df, rel):
        return bt_store.save(df, self._arm_log if rel == SHARED_LOG else rel)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--arm", required=True,
                   choices=["raw", "heur", "estimation", "composite"])
    p.add_argument("--tag", required=True,
                   help="per-arm output suffix; two arms may not share one")
    p.add_argument("--seed-base", type=int, default=20260827)
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


def arm_config(argv: list[str]) -> ArmConfig:
    p = _parser()
    a = p.parse_args(argv)
    if a.arm in TABLE_ARMS and not a.noise_asset:
        p.error(f"--arm {a.arm} needs a --noise-asset")
    if a.arm not in TABLE_ARMS and a.noise_asset:
        p.error(f"--arm {a.arm} serves no table; --noise-asset is refused")
    return ArmConfig(arm=a.arm, tag=a.tag, seed_base=a.seed_base, n=a.n,
                     chips=a.chips, priors=a.priors, minutes=a.minutes,
                     frame=a.frame, noise_asset=a.noise_asset)


def gate_wanted(cfg: ArmConfig) -> bool:
    return cfg.arm != "raw"


def apply_patches(cfg: ArmConfig):
    """Install every toggle this arm asks for; return a closure undoing all.

    Defaults install nothing but the per-arm store, which is why the off-state
    rail can assert byte-identity with ``s2_replay.py``.
    """
    undos: list = []

    def swap(module, name, value):
        original = getattr(module, name)
        undos.append(lambda: setattr(module, name, original))
        setattr(module, name, value)

    swap(bt, "store", _ArmStore(cfg.log_path))

    if cfg.minutes == "legacy":
        swap(tr, "ThreeModeModel", LegacyMinutesModel)

    if cfg.frame == "v4c":
        # train.attach_understat / load_training_frame resolve these by name at
        # call time; run_backtest calls cup_matches through its own import.
        swap(tr, "cup_matches", lambda: None)
        swap(bt, "cup_matches", lambda: None)
        swap(eng, "add_shrunken_modes", lambda df, *a, **kw: df)
        swap(tr, "add_shrunken_modes", lambda df, *a, **kw: df)

    if cfg.priors == "off":
        swap(bt, "load_decision_priors", lambda: None)

    payload = None
    if cfg.arm == "heur":
        swap(sc, "load_scenario_noise", lambda: None)
        sc.scenario_noise.cache_clear()
        assert sc.scenario_noise() is None, "heuristic arm must serve no table"
    elif cfg.arm in TABLE_ARMS:
        payload = json.loads(Path(cfg.noise_asset).read_text())
        if payload.get("source") != "estimation":
            raise SystemExit(
                f"--noise-asset is a {payload.get('source')!r} table, not an "
                "estimation one; scenario_noise() would refuse it and the arm "
                "would silently degrade to the heuristic")
        if cfg.arm == "composite" and "composite_floor" not in payload:
            raise SystemExit(
                "--arm composite needs a payload carrying composite_floor; "
                "this is the plain estimation table, which would make the arm "
                "a mislabelled duplicate of the estimation arm")
        swap(sc, "CALIBRATED_NOISE_DEFAULT", True)
        swap(sc, "load_scenario_noise", lambda: payload)
        sc.scenario_noise.cache_clear()
        assert sc.scenario_noise() is payload, "asset missing — arm invalid"

    def undo():
        for fn in reversed(undos):
            fn()
        sc.scenario_noise.cache_clear()

    undo.payload = payload  # type: ignore[attr-defined]
    return undo


def make_gate(cfg: ArmConfig, stash: dict, real_solve,
              run_scenarios=run_scenarios):
    """The s2 ``gated()`` closure, parameterised by ``cfg``.

    Chip valuation and execution solves (``wildcard_gw`` set, or
    ``free_transfers == 15`` for a Free Hit and the opening squad) stay raw,
    mirroring production. Week counts hang off the returned function so the
    caller can read them after the replay.
    """

    def gate(pool, state, **kw):
        plan = real_solve(pool, state, **kw)
        if (not state.owned_codes or state.wildcard_gw is not None
                or state.free_transfers >= 15):
            return plan
        xm = stash.get("xmins") or {}
        if not xm:
            return plan
        gw = int(state.gws[0])
        run = run_scenarios(pool, state, xm, n=cfg.n,
                            seed=cfg.seed_base + gw, **kw)
        if not run.completed:
            return plan
        gate.gated_weeks += 1
        decision = decide(move_frequencies(run.plans), plan, Thresholds())
        if decision.hold:
            gate.held_weeks += 1
        return coherent_plan(pool, state, decision, **kw)

    gate.gated_weeks = 0
    gate.held_weeks = 0
    return gate


def main(argv: list[str]) -> dict:
    cfg = arm_config(argv)
    undo = apply_patches(cfg)
    payload = getattr(undo, "payload", None)

    stash: dict = {}
    gate = None
    if gate_wanted(cfg):
        real_pcs = bt.predict_components_simple

        def pcs(models, rows):
            comp = real_pcs(models, rows)
            stash["xmins"] = xmins_by_player_gw(comp)
            return comp

        bt.predict_components_simple = pcs
        gate = make_gate(cfg, stash, bt.solve_plan)
        bt.solve_plan = gate

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
    report = Path(cfg.report_path)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print("V7B_ARM_DONE", cfg.tag, json.dumps(out), flush=True)
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
