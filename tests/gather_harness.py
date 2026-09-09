"""Run ``gather_inputs`` with every heavy dependency replaced by a spy, and
report the order in which it called them (v17g §5).

The claims this replaces were source-order pins: ``refresh_live`` appears
before ``ingested_through`` in the text of ``run_advise``, and so on. Those
were written because ``run_advise`` could not be called — it wanted a
network, a models directory and a season of history. ``gather_inputs`` can,
once the things that want those are stubbed, and then the ordering claim is
about the order the calls *happened in* rather than the order they are
written in. That is a stronger statement and it is the one the docstrings
always meant.

The stubs return the smallest thing each caller will accept, so the run
reaches the end. Nothing here asserts; the tests do.
"""
from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import gaffer.advise as advise
from gaffer.config import Config
from gaffer.data.entry import MyTeam

GW = 7
"""The gameweek the fake bootstrap is next on. Two ahead of ``THROUGH`` so
the data-gap warning has something to say."""

THROUGH = 5


def _players() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 100 + i, "element": i, "name": f"P{i}", "position": "MID",
         "team_code": i % 4, "now_cost": 50, "price_change_percent": 0.0,
         "status": "a", "chance_of_playing": 100} for i in range(4)])


def _comp() -> pd.DataFrame:
    return pd.DataFrame([{"code": 100 + i, "gw": g, "p_play": 0.9,
                          "p60": 0.8, "ep": 4.0, "position": "MID"}
                         for i in range(4) for g in (GW, GW + 1)])


class _Client:
    """Answers the four endpoints ``gather_inputs`` reaches for."""

    def get_bootstrap(self):
        return {"events": [], "elements": [], "teams": []}

    def get_fixtures(self):
        return []

    def get_entry(self, entry_id):
        return {"summary_overall_points": 100}


def gather(monkeypatch, *, cfg: Config | None = None, my: bool = True,
           predictions=None, **overrides) -> tuple[object, list[str]]:
    """``(inputs, call_order)``.

    ``overrides`` replaces a stub by name, which is how a test says what it
    is about: ``gather(monkeypatch, news_availability=boom)`` asks what
    happens when the news layer raises.
    """
    order: list[str] = []
    players, comp = _players(), _comp()
    ep = pd.DataFrame([{"code": c, "gw": g, "ep": v}
                       for c, g, v in ((100, GW, 6.0), (101, GW, 5.0),
                                       (102, GW, 4.0), (103, GW, 3.0))])

    def spy(name, value):
        def stub(*args, **kw):
            order.append(name)
            return value(*args, **kw) if callable(value) else value
        return stub

    frame = pd.DataFrame({"code": [100], "gw": [GW]})
    stubs = {
        "build_players": players, "build_teams": pd.DataFrame({"code": [0]}),
        "build_events": pd.DataFrame({"gw": [GW],
                                      "deadline_time": ["2026-10-01T17:30Z"]}),
        "next_gw": GW,
        "refresh_live": None,
        "ingested_through": THROUGH,
        "data_warning": "two gameweeks behind",
        "fixture_frame": frame, "save_live_fixtures": None,
        "save_snapshots": None,
        "load_training_frame": (frame, frame, {}),
        "future_fixture_frame": frame,
        "feature_columns": [],
        "build_prediction_frame": frame,
        "_rate_elo": frame,
        "build_team_future": frame,
        "pen_priors": None,
        "news_availability": pd.DataFrame({"code": [100], "status": ["a"],
                                           "chance_of_playing": [100]}),
        "write_shadow": None,
        "blend_attacking_odds": comp,
        "rescale_pen_after_blend": comp,
        "components_frame": comp,
        "scoring_table": {},
        "assemble_ep": ep, "apply_calibration": ep, "ep_matrix": ep,
        "save_components": None, "save_availability": None,
        "load_advice": {"gw": GW},
        "load_decision_priors": None, "load_chip_scenarios": {},
        "price_falls": (False, {}),
    }
    stubs.update(overrides)
    for name, value in stubs.items():
        monkeypatch.setattr(advise, name, spy(name, value), raising=False)
    # Two of gather's reads are imported inside the function body — the
    # health update because ``tracking`` imports back, the ticker's
    # difficulty because it lives under ``web``. Patching ``advise`` would
    # miss both, so they are patched where they are looked up.
    monkeypatch.setattr("gaffer.tracking.update_health",
                        spy("update_health", None))
    monkeypatch.setattr("gaffer.web.identity._difficulty_by_team",
                        spy("_difficulty_by_team", {}))

    # The predictions seam, spied like the rest: this is the model load.
    class _Predictions:
        def missing(self):
            order.append("Predictions.missing")
            return []

        def components(self, **kw):
            order.append("Predictions.components")
            return comp

        def calibration(self):
            order.append("Predictions.calibration")
            return None

    squad = pd.DataFrame([{"code": 100 + i, "sell": 50} for i in range(4)])
    team = MyTeam(entry_id=1, bank=0, free_transfers=1, current_gw=GW,
                  picks=squad, chips_used=[], chips_by_gw={})

    def fetch_my_team(*a, **kw):
        order.append("fetch_my_team")
        if not my:
            from gaffer.errors import GafferError
            raise GafferError("GW1: no squad yet")
        return team

    monkeypatch.setattr(advise, "fetch_my_team", fetch_my_team)
    monkeypatch.setattr(advise, "store", SimpleNamespace(
        save=lambda *a, **kw: order.append("store.save")))

    inputs = advise.gather_inputs(
        cfg or Config(entry_id=1, league_id=0), _Client(),
        predictions=predictions if predictions is not None else _Predictions())
    return inputs, order
