import pandas as pd
import pytest

from gaffer.artifacts import (COMPONENT_COLS, SolveState, components_frame,
                              latest_gw, load_components, load_solve_state,
                              milp_pool, pool_rows, raw_ep_by,
                              save_components, save_solve_state)

SCORING = {
    "goals_scored": {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4},
    "assists": {"GKP": 3, "DEF": 3, "MID": 3, "FWD": 3},
    "clean_sheets": {"GKP": 4, "DEF": 4, "MID": 1, "FWD": 0},
    "goals_conceded": {"GKP": -0.5, "DEF": -0.5, "MID": 0, "FWD": 0},
    "saves": {"GKP": 1 / 3, "DEF": 0, "MID": 0, "FWD": 0},
    "defensive_contribution": {"GKP": 0, "DEF": 2, "MID": 2, "FWD": 2},
    "minutes_0_59": {"GKP": 1, "DEF": 1, "MID": 1, "FWD": 1},
    "minutes_60_plus": {"GKP": 2, "DEF": 2, "MID": 2, "FWD": 2},
}


def _comp():
    return pd.DataFrame([
        {"code": 100, "season_idx": 4, "gw": 3, "opp_code": 200,
         "position": "MID", "team_code": 300, "was_home": True,
         "kickoff_time": "2026-09-12T14:00:00Z", "e_cards": -0.1,
         "p_play": 0.9, "p60": 0.8, "e_goals": 0.3, "e_assists": 0.2,
         "p_defcon": 0.15, "e_saves": 0.0, "e_bonus": 0.4,
         "p_cs": 0.31, "e_gc": 1.2, "p_cs_model": 0.25, "e_gc_model": 1.4,
         "odds_e_goals_against": 1.17, "odds_weight": 0.7,
         "pen_taker": 1.0, "setpiece_taker": 0.5},
    ])


def _players():
    return pd.DataFrame([{"code": 100, "element": 7, "name": "Salah"}])


def _teams():
    return pd.DataFrame([{"code": 300, "name": "Liverpool"},
                         {"code": 200, "name": "Arsenal"}])


def test_components_frame_carries_every_declared_column():
    out = components_frame(_comp(), SCORING, None, _players(), _teams())
    assert list(out.columns) == COMPONENT_COLS
    row = out.iloc[0]
    assert row["name"] == "Salah" and row["opp_name"] == "Arsenal"
    assert row["team_name"] == "Liverpool"
    assert row["cal_delta"] == 0.0            # no calibration model
    assert abs(row["ep"] - row["ep_uncalibrated"]) < 1e-12
    assert row["odds_weight"] == 0.7


def test_components_round_trip_through_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    frame = components_frame(_comp(), SCORING, None, _players(), _teams())
    save_components(frame, 3)
    back = load_components(3)
    assert len(back) == 1 and back.iloc[0]["code"] == 100


def test_load_components_missing_gw_raises_a_readable_error(tmp_path,
                                                            monkeypatch):
    from gaffer.errors import GafferError

    monkeypatch.chdir(tmp_path)
    with pytest.raises(GafferError) as exc:
        load_components(9)
    assert "gaffer advise" in str(exc.value)


def _state():
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 130, "sell": 128}]),
        _players(), owned_codes=[100],
        ep_by={(100, 3): 6.4, (100, 4): 5.1}, gws=[3, 4])
    return SolveState(
        gw=3, gws=[3, 4], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly",
        bank=12, free_transfers=2, owned_codes=[100], lam=0.25,
        league_eo={100: 62.5}, avail_by_gw={3: ["wildcard"], 4: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": 2},
        pool=pool)


def test_solve_state_round_trips_with_int_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    save_solve_state(_state())
    back = load_solve_state(3)
    assert back.gws == [3, 4] and back.bank == 12 and back.lam == 0.25
    assert back.league_eo == {100: 62.5}          # int keys, not "100"
    assert back.avail_by_gw == {3: ["wildcard"], 4: []}
    assert back.opt["hit_cost"] == 4
    assert raw_ep_by(back) == {(100, 3): 6.4, (100, 4): 5.1}


def test_milp_pool_is_the_shape_solve_plan_expects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = _state()
    pool = milp_pool(state, raw_ep_by(state), [3, 4])
    assert list(pool.columns) == ["code", "position", "team_code", "cost",
                                  "sell", "ep"]
    assert pool.iloc[0]["ep"] == {3: 6.4, 4: 5.1}


def test_latest_gw_picks_the_newest_saved_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert latest_gw() is None
    from dataclasses import replace
    save_solve_state(_state())
    save_solve_state(replace(_state(), gw=11))
    assert latest_gw() == 11
