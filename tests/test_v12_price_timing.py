"""Spec §3.4: a deferred sale of a falling player is charged the fall.

Two levels, because the term is smaller than the solver's own tolerance on a
real problem (plan A6). The coefficient test is exact and gap-free; the
behavioural test sets itb_value high enough in its own fixture that the charge
is half a point, and says so, because a test that depended on HiGHS resolving
0.008 would be testing the solver's mood.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer import price_timing
from gaffer.optimize import milp


def test_a_falling_owned_player_gets_his_predictor_reading_as_a_probability():
    log = pd.DataFrame({
        "snap_date": ["2026-09-01"] * 3,
        "code": [1, 2, 3],
        "now_cost": [80, 75, 60],
        "price_change_percent": [-95.0, -40.0, 88.0],
        "direction": ["drop", "drop", "rise"],
        "calibrating": [False, False, False]})
    out = price_timing.price_falls(log, [1, 2, 3])
    assert out[1] == 0.95
    assert out[2] == 0.4
    assert 3 not in out          # a rise is never charged (spec §8)


def test_a_calibrating_reading_is_not_a_probability():
    """``calibrating`` exists to say the log is not yet trustworthy, and a
    charge levied off an untrustworthy reading is worse than none —
    ``routers/prices.py``'s own rule for the movers panel."""
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [1],
                        "now_cost": [80], "price_change_percent": [-95.0],
                        "direction": ["drop"], "calibrating": [True]})
    assert price_timing.price_falls(log, [1]) == {}


def test_only_the_newest_day_is_read():
    log = pd.DataFrame({
        "snap_date": ["2026-08-31", "2026-09-01"],
        "code": [1, 1], "now_cost": [80, 80],
        "price_change_percent": [-95.0, -10.0],
        "direction": ["drop", "drop"], "calibrating": [False, False]})
    assert price_timing.price_falls(log, [1]) == {1: 0.1}


def test_a_reading_past_the_threshold_is_clamped_to_one():
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [1],
                        "now_cost": [80], "price_change_percent": [-129.9],
                        "direction": ["drop"], "calibrating": [False]})
    assert price_timing.price_falls(log, [1]) == {1: 1.0}


def test_an_unowned_player_is_not_in_the_table():
    log = pd.DataFrame({"snap_date": ["2026-09-01"], "code": [9],
                        "now_cost": [80], "price_change_percent": [-95.0],
                        "direction": ["drop"], "calibrating": [False]})
    assert price_timing.price_falls(log, [1, 2]) == {}


def test_the_switch_is_off_by_default_and_lives_under_optimizer(tmp_path):
    """Off, against spec §3.4's `true`: CONVENTIONS §6, and the flip rule is
    in the gate. Under [optimizer] and not [solver]: program ruling."""
    from gaffer.config import price_timing as read_flag

    on = tmp_path / "on.toml"
    on.write_text("[optimizer]\nprice_timing = true\n")
    off = tmp_path / "off.toml"
    off.write_text("[optimizer]\nhorizon = 3\n")
    assert read_flag(on) is True
    assert read_flag(off) is False
    assert read_flag(tmp_path / "nothing.toml") is False
    stale = tmp_path / "stale.toml"
    stale.write_text("[solver]\nprice_timing = true\n")
    # A key in a section this project does not have is not a switch.
    assert read_flag(stale) is False


def test_the_flag_does_not_reach_the_config_constructor(tmp_path):
    """The grenade the [optimizer] ruling armed: that section is splatted
    wholesale, so an unpopped knob is a TypeError out of Config.__init__ on
    the next advise run — for anyone who copies config.example.toml."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n\n"
                    "[optimizer]\nhorizon = 3\nprice_timing = true\n")
    cfg = load_config(path)
    assert cfg.horizon == 3
    assert not hasattr(cfg, "price_timing")


def test_w1s_top_n_still_travels_through_the_splat(tmp_path):
    """The other half of the pop list, and the expensive mistake it prevents.

    W1 §2.6 ships ``top_n`` as a real Config field read through
    ``optimizer_top_n()``. Popping it beside ``price_timing`` would strip a
    configured pool size out of the constructor and hand every user the
    dataclass default — silently, because a smaller pool is a valid solve.
    A key belongs in NON_FIELD_OPTIMIZER_KEYS only when Config has no field
    of that name.
    """
    import dataclasses

    from gaffer.config import NON_FIELD_OPTIMIZER_KEYS, Config, load_config

    names = {f.name for f in dataclasses.fields(Config)}
    assert not (set(NON_FIELD_OPTIMIZER_KEYS) & names)

    path = tmp_path / "config.toml"
    path.write_text(
        "[fpl]\nentry_id = 1\nleague_id = 2\n\n[optimizer]\n"
        "top_n = {GKP = 4, DEF = 5, MID = 6, FWD = 7}\nprice_timing = true\n")
    cfg = load_config(path)
    assert cfg.top_n["MID"] == 6


def test_a_typo_under_optimizer_still_raises_loudly(tmp_path):
    """Why the pop is a named list and not a fields(Config) filter: a silently
    ignored `horizen = 6` is a season of quietly wrong advice."""
    from gaffer.config import load_config

    path = tmp_path / "config.toml"
    path.write_text("[fpl]\nentry_id = 1\nleague_id = 2\n\n"
                    "[optimizer]\nhorizen = 6\n")
    with pytest.raises(TypeError):
        load_config(path)


def test_the_switch_off_is_an_empty_table(monkeypatch):
    monkeypatch.setattr(price_timing, "price_timing_enabled", lambda: False)
    monkeypatch.setattr(price_timing, "load_price_log",
                        lambda: pd.DataFrame({
                            "snap_date": ["2026-09-01"], "code": [1],
                            "now_cost": [80], "price_change_percent": [-95.0],
                            "direction": ["drop"], "calibrating": [False]}))
    assert price_timing.owned_price_falls([1]) == {}


def test_a_missing_price_log_costs_the_term_and_not_the_solve(monkeypatch):
    def boom():
        raise OSError("no price log on this machine")

    monkeypatch.setattr(price_timing, "price_timing_enabled", lambda: True)
    monkeypatch.setattr(price_timing, "load_price_log", boom)
    assert price_timing.owned_price_falls([1]) == {}


# --- the objective ------------------------------------------------------

def _pool():
    """Fifteen buildable players plus two alternatives.

    Everyone is EP-equal at 1.0 except code 1, and everyone costs 40 except
    code 1 — and both exceptions exist so that the *timing* of one sale is the
    only free choice left in the problem (see the behavioural test below).
    Code 1 is dear (45) and better in the first week only (1.2), so selling him
    frees half a million either way and costs 0.2 points only if it happens in
    the first week. Code 17 is the keeper who replaces him.
    """
    rows = []
    positions = ["GKP"] * 2 + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 4
    for i, pos in enumerate(positions):
        rows.append({"code": i + 1, "position": pos, "team_code": i % 6,
                     "cost": 40.0, "sell": 40.0,
                     "ep": {5: 1.0, 6: 1.0}})
    rows[0].update(cost=45.0, sell=45.0, ep={5: 1.2, 6: 1.0})
    rows.append({"code": 17, "position": "GKP", "team_code": 0,
                 "cost": 40.0, "sell": 40.0, "ep": {5: 1.0, 6: 1.0}})
    return pd.DataFrame(rows)


def _state(pool):
    return milp.SolveInput(owned_codes=list(pool["code"])[:15], bank=0,
                           free_transfers=2, gws=[5, 6])


def test_the_charge_lands_on_the_objective_with_the_specified_coefficient(
        monkeypatch):
    """The exact assertion. The built problem carries one term per (owned,
    later gameweek) at p x 0.1 x itb_value, and none in the first week."""
    captured = {}

    def spy(prob):
        captured["obj"] = str(prob.objective)
        raise RuntimeError("stop here — the built problem is the assertion")

    pool = _pool()
    monkeypatch.setattr(milp, "_solve", spy)
    with pytest.raises(RuntimeError):
        milp._solve_once(pool, _state(pool), decay=1.0, bench_weight=0.1,
                         vice_weight=0.1, ft_value=1.5, itb_value=0.08,
                         hit_cost=4, price_fall={1: 1.0})
    # 1.0 x 0.1 x 0.08 = 0.008, on out_1_6 and on nothing in week 5.
    assert "0.008*out_1_6" in captured["obj"].replace(" ", "")
    assert "out_1_5" not in captured["obj"].replace(" ", "").replace(
        "0.008*out_1_6", "")


def test_with_the_charge_large_enough_to_beat_the_gap_the_sale_moves_forward(
        monkeypatch):
    """Spec §3.4's own test, at a knob setting where the solver must respect
    it: itb_value = 5.0 makes the charge 0.5 points. At the shipped 0.08 the
    charge is 0.008 and HiGHS's default relative gap on a real horizon is
    larger than that — which is a fact about the term's size, recorded in the
    plan (A6), not a fact this test can paper over.

    ``_solve_once`` rather than ``solve_plan``: the enumerated change builds
    the lookup *inside* ``solve_plan`` from the config and the price log, so
    that wrapper takes no ``price_fall`` and a test that handed it one would
    be testing a keyword the tree does not have. The term lives in
    ``_solve_once`` rather than ``solve_plan``: the enumerated change builds
    the lookup *inside* ``solve_plan`` from the config and the price log, so
    that wrapper takes no ``price_fall`` and a test that handed it one would
    be testing a keyword the tree does not have. The term lives in
    ``_solve_once`` and pass two inherits it through ``**kw``.

    The control is half the test and not a courtesy: without the charge this
    exact problem defers the sale to the second week, because holding code 1
    through the first week is worth 0.2 points and the half million his sale
    frees is worth the same whenever it is banked. The assertion below is only
    a statement about the term because the line above says the solver would
    otherwise have done the opposite."""
    pool = _pool()
    state = _state(pool)
    kw = dict(decay=1.0, bench_weight=0.1, vice_weight=0.1, ft_value=0.0,
              itb_value=5.0, hit_cost=4)
    control = milp._solve_once(pool, state, **kw, price_fall=None)
    assert 1 in control.gw_plans[1].sells

    plan = milp._solve_once(pool, state, **kw, price_fall={1: 1.0})
    assert 1 not in plan.gw_plans[1].squad or 1 in plan.gw_plans[0].sells


def test_no_price_fall_leaves_the_problem_byte_identical(monkeypatch):
    """The degradation direction: an empty table must reproduce today's
    objective exactly, so a machine with no price log solves what it always
    did."""
    captured = []

    def spy(prob):
        captured.append(str(prob.objective))
        raise RuntimeError("stop")

    pool = _pool()
    monkeypatch.setattr(milp, "_solve", spy)
    for fall in (None, {}):
        with pytest.raises(RuntimeError):
            milp._solve_once(pool, _state(pool), decay=1.0, bench_weight=0.1,
                             vice_weight=0.1, ft_value=1.5, itb_value=0.08,
                             hit_cost=4, price_fall=fall)
    assert captured[0] == captured[1]
