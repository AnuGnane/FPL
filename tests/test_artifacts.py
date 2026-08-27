import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from gaffer.artifacts import (COMPONENT_COLS, SolveState, components_frame,
                              data_warning, ingested_through, latest_gw,
                              load_components, load_solve_state, milp_pool,
                              pool_rows, raw_ep_by, save_components,
                              save_solve_state)

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


# --- how much of the current season the model has actually seen -------------


def _player_gw(rows):
    return pd.DataFrame(rows, columns=["season", "season_idx", "gw", "code",
                                       "total_points"])


def _save_player_gw(root, rows):
    (root / "data" / "live").mkdir(parents=True, exist_ok=True)
    _player_gw(rows).to_parquet(root / "data" / "live" / "player_gw.parquet",
                                index=False)


def test_ingested_through_is_none_without_a_parquet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert ingested_through() is None


def test_ingested_through_is_none_when_the_parquet_is_empty(tmp_path,
                                                            monkeypatch):
    """The real state after a pre-`data_checked` refresh: the file exists and
    holds nothing, because every unchecked gameweek was dropped."""
    monkeypatch.chdir(tmp_path)
    _save_player_gw(tmp_path, [])
    assert ingested_through() is None


def test_ingested_through_is_the_newest_gw_on_disk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_player_gw(tmp_path, [
        {"season": "2026-27", "season_idx": 4, "gw": 1, "code": 100,
         "total_points": 5},
        {"season": "2026-27", "season_idx": 4, "gw": 2, "code": 100,
         "total_points": 7}])
    assert ingested_through() == 2


def test_ingested_through_can_be_asked_about_one_season(tmp_path,
                                                        monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_player_gw(tmp_path, [
        {"season": "2025-26", "season_idx": 3, "gw": 38, "code": 100,
         "total_points": 2},
        {"season": "2026-27", "season_idx": 4, "gw": 1, "code": 100,
         "total_points": 5}])
    assert ingested_through(4) == 1
    assert ingested_through(3) == 38
    assert ingested_through(9) is None
    assert ingested_through() == 1      # newest season by default


def test_no_warning_when_the_data_reaches_last_gameweek():
    assert data_warning(5, 4) is None
    assert data_warning(1, None) is None       # nothing has been played yet
    assert data_warning(None, None) is None    # season over


def test_missing_gw1_warning_names_the_gameweek_and_the_fix():
    msg = data_warning(2, None)
    assert msg is not None
    assert "GW1" in msg and "gaffer advise" in msg
    assert "morning after the last match" in msg


def test_warning_spans_every_missing_gameweek():
    assert "GW3-GW6" in data_warning(7, 2)
    assert data_warning(7, 5).startswith("model has no data for GW6 ")


def test_save_and_load_params_round_trip(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 0.62})
    assert persistence.params_exist("blend")
    assert persistence.load_params("blend")["odds_blend_weight"] == 0.62


def test_params_exist_is_false_before_anything_is_saved(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    assert persistence.params_exist("blend") is False


def test_load_params_on_a_missing_file_returns_an_empty_dict(tmp_path,
                                                             monkeypatch):
    """A fresh clone has no artifacts; every reader falls back to its own
    default rather than crashing on the way to a first train."""
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    assert persistence.load_params("blend") == {}


def test_save_params_stamps_the_save_time(tmp_path, monkeypatch):
    import gaffer.models.persistence as persistence

    monkeypatch.setattr(persistence, "MODELS_DIR", tmp_path)
    persistence.save_params("blend", {"odds_blend_weight": 0.5})
    assert "saved_at" in persistence.load_params("blend")


# --- v6: the availability snapshot -----------------------------------------

def _avail() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 1, "status": "d", "chance_of_playing": 75,
         "injury_type": "hamstring", "expected_return_gw": 6,
         "p_start_hint": 0.0, "source": "premierinjuries|lineups",
         "fetched_at": "2026-09-04T09:00:00Z"},
        {"code": 2, "status": "a", "chance_of_playing": None,
         "injury_type": None, "expected_return_gw": None,
         "p_start_hint": None, "source": None, "fetched_at": None},
    ])


def test_save_availability_round_trips_through_parquet(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    path = art.save_availability(_avail(), 5)
    assert path == art.availability_path(5)
    back = art.load_availability(5)
    assert list(back.columns) == art.AVAILABILITY_COLS
    assert back.loc[back["code"] == 1, "injury_type"].iloc[0] == "hamstring"
    assert float(back.loc[back["code"] == 1, "expected_return_gw"].iloc[0]) == 6


def test_save_availability_fills_columns_a_flags_only_frame_lacks(
        tmp_path, monkeypatch):
    """With news off, ``news_availability`` returns the bare official slice.
    The snapshot still has to be readable by the news endpoint."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    official = pd.DataFrame([{"code": 1, "status": "a",
                              "chance_of_playing": None}])
    art.save_availability(official, 5)
    back = art.load_availability(5)
    assert list(back.columns) == art.AVAILABILITY_COLS
    assert back["injury_type"].isna().all()


def test_save_availability_never_raises(tmp_path, monkeypatch):
    """It is a snapshot for a UI panel. An advise run must not die of it."""
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    assert art.save_availability(None, 5) is None
    assert art.save_availability(pd.DataFrame(), 5) is None
    assert art.save_availability(pd.DataFrame({"nope": [1]}), 5) is None


def test_load_availability_is_none_when_nothing_was_written(tmp_path,
                                                            monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    assert art.load_availability(5) is None


# --- v6: the advice history log --------------------------------------------

def _advice(gw=5, captain=("Salah", 100), buys=(), sells=(), pts=61.5,
            chip=None) -> dict:
    return {
        "gw": gw, "deadline": "2026-09-05T10:00:00Z",
        "captain": {"code": captain[1], "name": captain[0]},
        "buys": [{"code": c, "name": n} for n, c in buys],
        "sells": [{"code": c, "name": n} for n, c in sells],
        "expected_pts": pts,
        "chip_table": ([] if chip is None
                       else [{"chip": chip, "gw": gw, "gain": 9.0,
                              "threshold": 8.0, "play_now": True}]),
    }


def test_append_advice_history_writes_one_file_per_run(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    first = art.append_advice_history(_advice(), 5,
                                      now=datetime(2026, 9, 4, 9, 0,
                                                   tzinfo=timezone.utc))
    second = art.append_advice_history(_advice(pts=63.0), 5,
                                       now=datetime(2026, 9, 4, 10, 0,
                                                    tzinfo=timezone.utc))
    assert first != second
    assert first.parent == art.ADVICE_HISTORY
    assert len(art.advice_history_files(5)) == 2
    assert json.loads(second.read_text())["expected_pts"] == 63.0


def test_advice_history_is_pruned_to_the_newest_twenty(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    for minute in range(25):
        art.append_advice_history(
            _advice(pts=float(minute)), 5,
            now=datetime(2026, 9, 4, 9, minute, tzinfo=timezone.utc))
    files = art.advice_history_files()
    assert len(files) == art.ADVICE_HISTORY_KEEP
    newest = json.loads(files[-1].read_text())
    assert newest["expected_pts"] == 24.0


def test_advice_history_files_filter_by_gameweek(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    art.append_advice_history(_advice(gw=5), 5,
                              now=datetime(2026, 9, 4, 9, 0,
                                           tzinfo=timezone.utc))
    art.append_advice_history(_advice(gw=6), 6,
                              now=datetime(2026, 9, 11, 9, 0,
                                           tzinfo=timezone.utc))
    assert len(art.advice_history_files(5)) == 1
    assert len(art.advice_history_files(6)) == 1
    assert len(art.advice_history_files()) == 2


def test_append_advice_history_never_raises(tmp_path, monkeypatch):
    import gaffer.artifacts as art

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(art, "ADVICE_HISTORY",
                        tmp_path / "nope" / "\0" / "bad")
    assert art.append_advice_history(_advice(), 5) is None


# --- v6: the run-to-run diff ------------------------------------------------

def test_diff_advice_reports_what_changed_between_two_runs():
    from gaffer.artifacts import diff_advice

    previous = _advice(captain=("Salah", 100), buys=[("Isak", 200)],
                       sells=[("Watkins", 300)], pts=61.5)
    current = _advice(captain=("Haaland", 101), buys=[("Wirtz", 201)],
                      sells=[("Watkins", 300)], pts=64.0, chip="bboost")
    out = diff_advice(previous, current)
    assert out["captain_from"]["name"] == "Salah"
    assert out["captain_to"]["name"] == "Haaland"
    assert [b["name"] for b in out["buys_added"]] == ["Wirtz"]
    assert [b["name"] for b in out["buys_dropped"]] == ["Isak"]
    assert out["sells_added"] == [] and out["sells_dropped"] == []
    assert out["expected_pts_delta"] == 2.5
    assert out["chip_from"] is None and out["chip_to"] == "bboost"


def test_diff_advice_of_two_identical_runs_is_empty_but_present():
    from gaffer.artifacts import diff_advice

    out = diff_advice(_advice(), _advice())
    assert out["buys_added"] == [] and out["buys_dropped"] == []
    assert out["captain_from"] is None and out["captain_to"] is None
    assert out["expected_pts_delta"] == 0.0
    assert out["changed"] is False


def test_diff_advice_tolerates_a_payload_missing_every_optional_key():
    """History written by an older build is still worth diffing."""
    from gaffer.artifacts import diff_advice

    out = diff_advice({}, {"expected_pts": 3.0})
    assert out["expected_pts_delta"] == 3.0
    assert out["changed"] is True
