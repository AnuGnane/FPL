import inspect
import math

import pandas as pd
from gaffer.advise import run_advise
from gaffer.backtest import run_backtest
from gaffer.models.assemble import (PEN_FACED_RATE, PEN_SAVE_RATE,
                                    apply_calibration, assemble_ep, ep_matrix,
                                    p_haul)
from gaffer.models.calibrate import CalibrationModel

SCORING = {
    "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "assists": {p: 3 for p in ["GKP", "DEF", "MID", "FWD"]},
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -0.5, "DEF": -0.5, "MID": 0, "FWD": 0},
    "saves": {p: 1 / 3 if p == "GKP" else 0 for p in ["GKP", "DEF", "MID", "FWD"]},
    "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
    "minutes_0_59": {p: 1 for p in ["GKP", "DEF", "MID", "FWD"]},
    "minutes_60_plus": {p: 2 for p in ["GKP", "DEF", "MID", "FWD"]},
}


def _components():
    return pd.DataFrame([{
        "code": 1, "season_idx": 4, "gw": 2, "position": "DEF",
        "p_play": 1.0, "p60": 1.0,
        "e_goals": 0.1, "e_assists": 0.1, "p_cs": 0.5, "e_gc": 0.6,
        "e_saves": 0.0, "p_defcon": 0.5, "e_bonus": 0.4, "e_cards": -0.1,
    }])


def test_assemble_ep_matches_hand_calc():
    ep = assemble_ep(_components(), SCORING)
    # appearance: 1*p_play + 1*p60 = 2.0 ; goals: .1*6=.6 ; assists: .1*3=.3
    # cs: p60*p_cs*4 = 2.0 ; gc: -0.5*e_gc*p60 = -0.3 ; defcon: .5*2=1.0
    # bonus .4 ; cards -.1  => total 5.9
    assert abs(ep.iloc[0]["ep"] - 5.9) < 1e-9


def test_p_haul_poisson():
    lam = 0.5
    expected = 1 - math.exp(-lam) * (1 + lam)
    assert abs(p_haul(0.3, 0.2) - expected) < 1e-9


def test_p_haul_treats_nan_as_zero():
    assert p_haul(float("nan"), 0.2) == p_haul(0.0, 0.2)
    assert p_haul(0.3, float("nan")) == p_haul(0.3, 0.0)
    assert p_haul(None, None) == 0.0


def test_assemble_ep_propagates_nan_without_crashing():
    comp = _components()
    comp.loc[0, "p_cs"] = float("nan")
    ep = assemble_ep(comp, SCORING)
    assert math.isnan(ep.iloc[0]["ep"])
    # p_haul is unaffected by the missing clean-sheet probability.
    assert abs(ep.iloc[0]["p_haul"] - p_haul(0.1, 0.1)) < 1e-9


def test_assemble_ep_scales_by_playing_probability():
    comp = _components()
    comp.loc[0, "p_play"] = 0.5
    comp.loc[0, "p60"] = 0.4
    ep = assemble_ep(comp, SCORING)
    expected = (
        0.5 * 1 + 0.4 * (2 - 1)
        + 0.5 * 0.1 * 6 + 0.5 * 0.1 * 3
        + 0.4 * 0.5 * 4 + 0.4 * 0.6 * -0.5
        + 0.5 * 0.5 * 2 + 0.5 * 0.4 + 0.5 * -0.1
    )
    assert abs(ep.iloc[0]["ep"] - expected) < 1e-9
    assert abs(ep.iloc[0]["p_haul"] - p_haul(0.05, 0.05)) < 1e-9


def test_ep_matrix_sums_double_gameweeks():
    a = _components()
    b = _components()
    b.loc[0, "e_goals"] = 0.2
    per_fixture = assemble_ep(pd.concat([a, b], ignore_index=True), SCORING)
    mat = ep_matrix(per_fixture)
    assert len(mat) == 1
    row = mat.iloc[0]
    assert row["code"] == 1 and row["gw"] == 2
    assert abs(row["ep"] - per_fixture["ep"].sum()) < 1e-9
    assert abs(row["p_haul"] - per_fixture["p_haul"].max()) < 1e-9
    assert list(mat.columns) == ["code", "gw", "ep", "p_haul"]


def test_ep_matrix_omits_blank_gameweeks():
    comp = _components()
    other = _components()
    other.loc[0, "gw"] = 4
    mat = ep_matrix(assemble_ep(pd.concat([comp, other], ignore_index=True), SCORING))
    assert sorted(mat["gw"]) == [2, 4]
    assert 3 not in set(mat["gw"])


def _plus_one_cal():
    """A CalibrationModel adding 1.0 to a nailed MID, other positions be."""
    cal = CalibrationModel()
    cal.by_pos["MID"] = 1.0
    return cal


def _assembled():
    """Two MID fixtures in one gameweek (a DGW pair) plus one FWD fixture."""
    return pd.DataFrame(
        [{"code": 1, "gw": 2, "position": "MID", "ep": 1.0, "p60": 1.0,
          "p_haul": 0.2},
         {"code": 1, "gw": 2, "position": "MID", "ep": 2.0, "p60": 1.0,
          "p_haul": 0.4},
         {"code": 2, "gw": 2, "position": "FWD", "ep": 3.0, "p60": 1.0,
          "p_haul": 0.5}],
        index=[5, 6, 7],   # non-default index: the write must not realign
    )


def test_apply_calibration_shifts_ep_by_position():
    assembled = _assembled()
    out = apply_calibration(assembled, _plus_one_cal())
    assert list(out["ep"]) == [2.0, 3.0, 3.0]
    # p_haul comes from the components, not from ep, so it is untouched.
    assert list(out["p_haul"]) == list(assembled["p_haul"])
    # the caller's frame is left alone
    assert list(assembled["ep"]) == [1.0, 2.0, 3.0]


def test_apply_calibration_gates_the_shift_on_p60():
    """A fixture the player is unlikely to start earns little of the
    starter correction, and a certain benching earns none."""
    assembled = _assembled()
    assembled["p60"] = [0.0, 0.5, 1.0]
    out = apply_calibration(assembled, _plus_one_cal())
    assert list(out["ep"]) == [1.0, 2.5, 3.0]


def test_apply_calibration_without_a_model_is_a_no_op():
    assembled = _assembled()
    out = apply_calibration(assembled, None)
    assert list(out["ep"]) == [1.0, 2.0, 3.0]
    assert list(out["p_haul"]) == list(assembled["p_haul"])


def test_apply_calibration_happens_before_the_double_gameweek_sums():
    assembled = _assembled()
    cal = ep_matrix(apply_calibration(assembled, _plus_one_cal()))
    plain = ep_matrix(assembled)
    # Each fixture is corrected, then summed: a DGW player is expected to
    # start twice, so he earns the starter correction twice -> 2 + 3 = 5.
    # Correcting after the sum would have given 4 and understated him.
    assert float(cal.loc[cal["code"] == 1, "ep"].iloc[0]) == 5.0
    assert float(cal.loc[cal["code"] == 2, "ep"].iloc[0]) == 3.0
    assert float(plain.loc[plain["code"] == 1, "ep"].iloc[0]) == 3.0
    # p_haul survives the calibration untouched
    assert list(cal["p_haul"]) == list(plain["p_haul"])


def _gkp_components():
    comp = _components()
    comp.loc[0, "position"] = "GKP"
    return comp


def test_gkp_ep_includes_the_penalty_save_term():
    scoring = dict(SCORING, penalties_saved={"GKP": 5, "DEF": 0, "MID": 0,
                                             "FWD": 0})
    with_pens = assemble_ep(_gkp_components(), scoring).iloc[0]["ep"]
    without = assemble_ep(_gkp_components(), SCORING).iloc[0]["ep"]
    # p_play(1) * PEN_FACED_RATE(0.06) * PEN_SAVE_RATE(0.30) * 5 = 0.09
    assert abs(with_pens - without - 0.09) < 1e-9
    assert abs(with_pens - (without + PEN_FACED_RATE * PEN_SAVE_RATE * 5)) < 1e-9


def test_penalty_save_term_scales_by_playing_probability():
    scoring = dict(SCORING, penalties_saved={"GKP": 5, "DEF": 0, "MID": 0,
                                             "FWD": 0})
    comp = _gkp_components()
    comp.loc[0, "p_play"] = 0.5
    base = assemble_ep(comp, SCORING).iloc[0]["ep"]
    assert abs(assemble_ep(comp, scoring).iloc[0]["ep"] - base - 0.045) < 1e-9


def test_outfielders_are_unaffected_by_the_penalty_save_term():
    scoring = dict(SCORING, penalties_saved={"GKP": 5, "DEF": 5, "MID": 5,
                                             "FWD": 5})
    comp = _components()
    comp.loc[0, "position"] = "MID"
    assert (assemble_ep(comp, scoring).iloc[0]["ep"]
            == assemble_ep(comp, SCORING).iloc[0]["ep"])


def test_bonus_uses_the_scoring_table_multiplier():
    scoring = dict(SCORING, bonus={"GKP": 1, "DEF": 1, "MID": 2, "FWD": 1})
    comp = _components()
    comp.loc[0, "position"] = "MID"
    doubled = assemble_ep(comp, scoring).iloc[0]["ep"]
    plain = assemble_ep(comp, SCORING).iloc[0]["ep"]
    # e_bonus 0.4 at p_play 1.0: the multiplier of 2 adds one more 0.4.
    assert abs(doubled - plain - 0.4) < 1e-9


def test_absent_penalties_saved_and_bonus_keys_keep_todays_behaviour():
    """Old fixture tables carry neither key; the multiplier defaults to 1 for
    bonus and the penalty-save term to 0."""
    assert "penalties_saved" not in SCORING and "bonus" not in SCORING
    assert abs(assemble_ep(_components(), SCORING).iloc[0]["ep"] - 5.9) < 1e-9
    gkp = assemble_ep(_gkp_components(), SCORING).iloc[0]["ep"]
    # GKP: appearance 2.0 + goals .1*10 + assists .3 + cs 1*.5*4=2.0
    # + gc .6*-0.5=-0.3 + saves 0 + defcon 0 + bonus .4 + cards -.1
    assert abs(gkp - (2.0 + 1.0 + 0.3 + 2.0 - 0.3 + 0.4 - 0.1)) < 1e-9


def test_advise_and_backtest_wire_calibration_into_the_ep_pipeline():
    """The application point is pinned by spec: inside ``ep_matrix(...)``,
    wrapping ``assemble_ep``. Neither entry point has a cheap end-to-end
    harness, so pin the seam at the source level."""
    for fn in (run_advise, run_backtest):
        src = inspect.getsource(fn)
        assert "ep_matrix(apply_calibration(assemble_ep(" in src, fn.__name__


def test_ep_breakdown_terms_sum_to_assembled_ep():
    """The breakdown is a second implementation of the same arithmetic, so
    the only guard against drift is that its terms re-add to ``ep``."""
    from gaffer.models.assemble import ep_breakdown

    comp = pd.concat([_components(), _gkp_components()], ignore_index=True)
    assembled = assemble_ep(comp, SCORING)
    broken = ep_breakdown(assembled, SCORING)
    terms = ["ep_minutes", "ep_goals", "ep_assists", "ep_cs", "ep_gc",
             "ep_saves", "ep_defcon", "ep_bonus", "ep_cards", "ep_pensave"]
    total = broken[terms].sum(axis=1)
    for got, want in zip(total, assembled["ep"]):
        assert abs(got - want) < 1e-9


def test_absent_defensive_contribution_key_drops_the_term():
    """Defensive contribution arrived in 2025/26, so a table restated to an
    earlier season's rules simply has no such key — the benchmark evaluation
    hands one in. The term drops out rather than raising."""
    older = {k: v for k, v in SCORING.items() if k != "defensive_contribution"}
    ep = assemble_ep(_components(), older).iloc[0]["ep"]
    assert abs(ep - (5.9 - 1.0)) < 1e-9        # the 0.5 * 2 defcon term
    from gaffer.models.assemble import ep_breakdown
    broken = ep_breakdown(assemble_ep(_components(), older), older)
    assert float(broken.iloc[0]["ep_defcon"]) == 0.0
