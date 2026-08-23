import math

import pandas as pd

from gaffer.models.assemble import assemble_ep, ep_matrix, p_haul

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
        "p_play": 1.0, "p60": 1.0, "e_min": 90.0,
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
