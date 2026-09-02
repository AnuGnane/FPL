"""v12 W4 §5.2's two feature builders, and the coverage they really have."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from gaffer.features.engineer import (ROLE_FEATURES, WB_BOX_TOUCHES,
                                      WB_CROSSES, add_role_wb_share)


def _pms(rows: list[dict]) -> pd.DataFrame:
    base = {"season": "2025-26", "season_idx": 3, "gw": 1, "code": 1,
            "minutes_played": 90.0, "start_min": 0.0, "finish_min": 90.0,
            "accurate_crosses": 0.0, "touches_opposition_box": 0.0}
    return pd.DataFrame([{**base, **r} for r in rows])


def _players(rows: list[dict]) -> pd.DataFrame:
    base = {"season_idx": 3, "gw": 6, "code": 1, "position": "DEF"}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_the_feature_names_are_two_and_stable():
    assert ROLE_FEATURES == ["role_wb_share", "role_wb_missing"]


def test_a_defender_who_crosses_every_week_reads_one():
    stats = _pms([{"gw": g, "accurate_crosses": 2.0} for g in range(1, 6)])
    out = add_role_wb_share(_players([{}]), stats)
    assert out["role_wb_share"].iloc[0] == 1.0
    assert out["role_wb_missing"].iloc[0] == 0.0


def test_a_centre_back_who_never_crosses_reads_zero():
    stats = _pms([{"gw": g} for g in range(1, 6)])
    out = add_role_wb_share(_players([{}]), stats)
    assert out["role_wb_share"].iloc[0] == 0.0
    assert out["role_wb_missing"].iloc[0] == 0.0


def test_box_touches_alone_classify_a_start_as_wing_back():
    stats = _pms([{"gw": g, "touches_opposition_box": float(WB_BOX_TOUCHES)}
                  for g in range(1, 6)])
    assert add_role_wb_share(_players([{}]), stats)["role_wb_share"].iloc[0] \
        == 1.0


def test_the_thresholds_are_the_stated_ones():
    assert (WB_CROSSES, WB_BOX_TOUCHES) == (1, 3)


def test_three_of_five_starts_read_zero_point_six():
    stats = _pms([{"gw": 1, "accurate_crosses": 1.0},
                  {"gw": 2, "accurate_crosses": 1.0},
                  {"gw": 3, "accurate_crosses": 1.0},
                  {"gw": 4}, {"gw": 5}])
    assert add_role_wb_share(_players([{}]),
                             stats)["role_wb_share"].iloc[0] == 0.6


def test_only_the_last_five_starts_count():
    stats = _pms([{"gw": g, "accurate_crosses": 5.0} for g in range(1, 4)]
                 + [{"gw": g} for g in range(4, 9)])
    assert add_role_wb_share(_players([{"gw": 9}]),
                             stats)["role_wb_share"].iloc[0] == 0.0


def test_a_substitute_appearance_is_not_a_start():
    stats = _pms([{"gw": g, "minutes_played": 20.0, "start_min": 70.0,
                   "accurate_crosses": 3.0} for g in range(1, 9)])
    out = add_role_wb_share(_players([{}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_fewer_than_five_starts_is_missing_not_a_partial_mean():
    stats = _pms([{"gw": g, "accurate_crosses": 1.0} for g in range(1, 4)])
    out = add_role_wb_share(_players([{}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_a_non_defender_is_missing_by_definition():
    stats = _pms([{"gw": g, "accurate_crosses": 4.0} for g in range(1, 6)])
    out = add_role_wb_share(_players([{"position": "MID"}]), stats)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_the_feature_never_looks_forward():
    """A start in the gameweek being predicted must not feed its own
    feature — that is leakage, and it is the whole reason this reads
    ``< gw`` rather than ``<= gw``."""
    stats = _pms([{"gw": g} for g in range(1, 6)]
                 + [{"gw": 6, "accurate_crosses": 9.0}])
    assert add_role_wb_share(_players([{"gw": 6}]),
                             stats)["role_wb_share"].iloc[0] == 0.0


def test_another_seasons_starts_never_leak_across_the_boundary():
    stats = pd.concat([
        _pms([{"gw": g, "accurate_crosses": 4.0} for g in range(1, 9)])
        .assign(season="2024-25", season_idx=2),
        _pms([{"gw": g} for g in range(1, 6)])])
    out = add_role_wb_share(_players([{"gw": 6}]), stats)
    assert out["role_wb_share"].iloc[0] == 0.0


def test_an_empty_stats_frame_is_all_missing_and_not_a_crash():
    out = add_role_wb_share(_players([{}]),
                            pd.DataFrame(columns=["season_idx", "gw", "code"]))
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0


def test_the_builder_adds_exactly_two_columns_and_reorders_nothing():
    players = _players([{"code": 1}, {"code": 2}, {"code": 3}])
    out = add_role_wb_share(players, _pms([{"gw": 1}]))
    assert list(out.columns) == list(players.columns) + ROLE_FEATURES
    assert list(out["code"]) == [1, 2, 3]


# --- Task 8: density_pub_7d ---------------------------------------------

from gaffer.data import store  # noqa: E402
from gaffer.data.core_insights import ci_path  # noqa: E402
from gaffer.features.engineer import (DENSITY_FEATURES,  # noqa: E402
                                      DENSITY_WINDOW_DAYS, add_density_pub,
                                      core_insights_frames)


def _fx(rows: list[dict]) -> pd.DataFrame:
    # Each fixture gets its own match_id unless the case overrides it. The
    # builder counts *distinct matches*, so one shared default would collapse
    # two real ties into one and let a test pass for the wrong reason —
    # test_a_duplicated_fixture_row_counts_once is where the sharing is the
    # point, and it says so by naming the id itself.
    base = {"season": "2026-27", "season_idx": 4, "gw": 6,
            "tournament": "prem", "team_code": 8,
            "opponent_code": 91, "is_home": True, "finished": False}
    out = pd.DataFrame([{**base, "match_id": f"m{i}", **r}
                        for i, r in enumerate(rows)])
    out["kickoff"] = pd.to_datetime(out["kickoff"], utc=True)
    return out


def _rows(rows: list[dict]) -> pd.DataFrame:
    base = {"season_idx": 4, "gw": 6, "code": 1, "team_code": 8,
            "kickoff_time": "2026-10-10T14:00:00Z"}
    out = pd.DataFrame([{**base, **r} for r in rows])
    out["kickoff_time"] = pd.to_datetime(out["kickoff_time"], utc=True)
    return out


def test_the_density_feature_names_are_two_and_stable():
    assert DENSITY_FEATURES == ["density_pub_7d", "density_pub_missing"]
    assert DENSITY_WINDOW_DAYS == 7


def test_a_club_with_a_midweek_tie_reads_one():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z",
                     "tournament": "efl-cup"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    out = add_density_pub(_rows([{}]), fixtures)
    assert out["density_pub_7d"].iloc[0] == 1.0
    assert out["density_pub_missing"].iloc[0] == 0.0


def test_the_fixture_being_predicted_is_not_counted_against_itself():
    fixtures = _fx([{"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_a_match_eight_days_earlier_is_outside_the_window():
    fixtures = _fx([{"kickoff": "2026-10-02T14:00:00Z"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_european_and_league_ties_both_count():
    fixtures = _fx([{"kickoff": "2026-10-06T19:00:00Z",
                     "tournament": "champions-league"},
                    {"kickoff": "2026-10-08T19:00:00Z",
                     "tournament": "prem"},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 2.0


def test_an_unplayed_future_tie_counts_which_is_the_whole_point():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "finished": False,
                     "tournament": "efl-cup"},
                    {"kickoff": "2026-10-10T14:00:00Z", "finished": False}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 1.0


def test_another_clubs_ties_never_count():
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "team_code": 3},
                    {"kickoff": "2026-10-10T14:00:00Z"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_another_seasons_ties_never_count():
    fixtures = pd.concat([
        _fx([{"kickoff": "2026-10-07T19:00:00Z"}]).assign(season_idx=3),
        _fx([{"kickoff": "2026-10-10T14:00:00Z"}])])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 0.0


def test_a_duplicated_fixture_row_counts_once():
    """The table emits one row per club per match, and a club can appear in
    both a By Gameweek file and a re-collection; the count is over matches."""
    fixtures = _fx([{"kickoff": "2026-10-07T19:00:00Z", "match_id": "cup1"},
                    {"kickoff": "2026-10-07T19:00:00Z", "match_id": "cup1"},
                    {"kickoff": "2026-10-10T14:00:00Z", "match_id": "lg"}])
    assert add_density_pub(_rows([{}]), fixtures)["density_pub_7d"].iloc[0] \
        == 1.0


def test_no_collection_is_missing_everywhere_not_zero_everywhere():
    out = add_density_pub(_rows([{}]), None)
    assert np.isnan(out["density_pub_7d"].iloc[0])
    assert out["density_pub_missing"].iloc[0] == 1.0


def test_a_row_with_no_kickoff_time_is_missing_not_zero():
    out = add_density_pub(_rows([{"kickoff_time": None}]),
                          _fx([{"kickoff": "2026-10-07T19:00:00Z"}]))
    assert np.isnan(out["density_pub_7d"].iloc[0])


def test_the_density_builder_adds_two_columns_and_reorders_nothing():
    rows = _rows([{"code": 1}, {"code": 2}])
    out = add_density_pub(rows, _fx([{"kickoff": "2026-10-07T19:00:00Z"}]))
    assert list(out.columns) == list(rows.columns) + DENSITY_FEATURES
    assert list(out["code"]) == [1, 2]


def test_nothing_collected_is_two_nones_and_not_two_empty_frames():
    """The distinction both builders are written around: ``None`` is "this
    machine has never run the collector", an empty frame would be "the club
    played nothing"."""
    assert core_insights_frames() == (None, None)


def test_the_frames_are_enumerated_from_disk_and_not_from_a_season_list(
        monkeypatch, tmp_path):
    """Zero-arg by ruling: the seasons in play are whatever was collected.

    ``load_training_frame`` has no season list in scope and
    ``build_prediction_frame``'s frame has no ``season`` column, so a
    signature taking one would have been populated at training time and empty
    at serve time — v12 W2 §3.5's shape exactly.
    """
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    store.save(_pms([{"gw": 1}]).assign(player_id=1, match_id="m"),
               ci_path("2025-26", "players"))
    store.save(_fx([{"kickoff": "2026-10-07T19:00:00Z"}]),
               ci_path("2026-27", "fixtures"))
    stats, fixtures = core_insights_frames()
    assert stats is not None and list(stats["season"]) == ["2025-26"]
    assert fixtures is not None and list(fixtures["season"]) == ["2026-27"]


# --- Task 9: wiring ------------------------------------------------------

from gaffer.data.core_insights import (CI_FIXTURE_COLS,  # noqa: E402
                                       CI_PLAYER_COLS)
from gaffer.features.engineer import (build_prediction_frame,  # noqa: E402
                                      feature_columns)
from gaffer.models import train as tr  # noqa: E402


def test_the_new_columns_are_canonical_inputs():
    cols = feature_columns()
    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name in cols


def test_neither_arm_ships_inside_the_minutes_model():
    """CONVENTIONS §2: the gate is pre-registered and the arm is off until it
    passes. A feature that arrives already in the model is a feature nobody
    measured."""
    for name in ROLE_FEATURES + DENSITY_FEATURES:
        assert name not in tr.MINUTES_FEATURES


def test_the_builders_are_wired_into_the_training_frame():
    import inspect
    src = inspect.getsource(tr.load_training_frame)
    assert "add_role_wb_share" in src and "add_density_pub" in src


def test_the_builders_are_wired_into_the_prediction_frame():
    import inspect
    src = inspect.getsource(build_prediction_frame)
    assert "add_role_wb_share" in src and "add_density_pub" in src


# The two seams, measured rather than grepped. v12 W2 §3.5 shipped a builder
# wired into training and not into serving; a source-text assertion cannot
# tell the difference between "called" and "called with something it can use",
# and the serving frame is exactly where the season list ran out.

def _archive(tmp_path, monkeypatch, *, season="2025-26", season_idx=3,
             team=8, code=100, first_gw=1, starts=6):
    """Bank one season of core-insights parquets under a throwaway DATA_DIR.

    Six starts, every one of them a wing-back's (two crosses), and a midweek
    cup tie three days before each league kickoff. A correctly wired frame
    therefore reads ``role_wb_share == 1.0`` and ``density_pub_7d == 2.0`` —
    the previous week's league match, exactly seven days back and inside the
    closed lower bound, plus the cup tie three days back, which is the pair
    that shows both tournaments count — and an unwired one reads NaN.
    """
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    kick = lambda gw: (pd.Timestamp("2025-08-09", tz="UTC")   # noqa: E731
                       + pd.Timedelta(days=7 * (gw - 1)))
    players = pd.DataFrame([
        {"season": season, "season_idx": season_idx, "gw": gw, "code": code,
         "player_id": 1, "match_id": f"lg{gw}", "minutes_played": 90.0,
         "accurate_crosses": 2.0, "touches_opposition_box": 4.0,
         "final_third_passes": 5.0, "tackles_won": 1.0, "interceptions": 1.0,
         "blocks": 0.0, "clearances": 2.0, "recoveries": 3.0,
         "start_min": 0.0, "finish_min": 90.0,
         "defensive_contributions": float("nan")}
        for gw in range(first_gw, first_gw + starts)])[CI_PLAYER_COLS]
    fixtures = pd.concat([
        pd.DataFrame([
            {"season": season, "season_idx": season_idx, "gw": gw,
             "tournament": "prem", "match_id": f"lg{gw}",
             "kickoff": kick(gw), "team_code": team, "opponent_code": 2,
             "is_home": True, "finished": True}
            for gw in range(first_gw, first_gw + starts + 4)]),
        pd.DataFrame([
            {"season": season, "season_idx": season_idx, "gw": gw,
             "tournament": "efl-cup", "match_id": f"cup{gw}",
             "kickoff": kick(gw) - pd.Timedelta(days=3), "team_code": team,
             "opponent_code": 9, "is_home": False, "finished": True}
            for gw in range(first_gw, first_gw + starts + 4)])],
        ignore_index=True)[CI_FIXTURE_COLS]
    store.save(players, ci_path(season, "players"))
    store.save(fixtures, ci_path(season, "fixtures"))
    return kick


def test_the_prediction_frame_populates_both_arms_from_the_archive(
        monkeypatch, tmp_path):
    """The serving seam, which is the one W2 §3.5 lost.

    ``build_prediction_frame``'s rows carry ``season_idx`` and no ``season``
    column at all, so a ``core_insights_frames(seasons)`` keyed on the latter
    would leave both columns null here while training stayed populated — a
    train/serve skew no assertion on the training frame can see.
    """
    kick = _archive(tmp_path, monkeypatch)
    hist = pd.DataFrame([
        {"code": 100, "team_code": 8, "season_idx": 3, "gw": gw,
         "kickoff_time": kick(gw).isoformat(), "starts": 1.0, "minutes": 90.0}
        for gw in range(1, 7)])
    future = pd.DataFrame([
        {"code": 100, "season_idx": 3, "gw": 7, "team_code": 8, "opp_code": 2,
         "was_home": True, "position": "DEF",
         "kickoff_time": kick(7).isoformat()}])
    out = build_prediction_frame(hist, future)
    assert out["role_wb_share"].iloc[0] == 1.0
    assert out["role_wb_missing"].iloc[0] == 0.0
    assert out["density_pub_7d"].iloc[0] == 2.0
    assert out["density_pub_missing"].iloc[0] == 0.0


def test_the_prediction_frame_degrades_to_missing_with_no_collection(
        monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    future = pd.DataFrame([
        {"code": 100, "season_idx": 3, "gw": 7, "team_code": 8, "opp_code": 2,
         "was_home": True, "position": "DEF",
         "kickoff_time": "2025-09-20T14:00:00Z"}])
    out = build_prediction_frame(pd.DataFrame(columns=list(future.columns)),
                                 future)
    assert np.isnan(out["role_wb_share"].iloc[0])
    assert out["role_wb_missing"].iloc[0] == 1.0
    assert np.isnan(out["density_pub_7d"].iloc[0])
    assert out["density_pub_missing"].iloc[0] == 1.0


def test_the_training_frame_populates_both_arms_from_the_archive(
        monkeypatch, tmp_path):
    """The training seam, measured on the real ``load_training_frame``."""
    kick = _archive(tmp_path, monkeypatch)
    hist = pd.DataFrame([
        {"code": 100, "season_idx": 3, "gw": gw, "team_code": 8,
         "opp_code": 2, "position": "DEF", "was_home": True,
         "kickoff_time": kick(gw).isoformat(), "starts": 1.0, "minutes": 90.0,
         "total_points": 5.0, "value": 50, "bps": 20.0, "bonus": 0.0}
        for gw in range(1, 9)])
    fixtures = pd.DataFrame([
        {"season_idx": 3, "gw": gw, "kickoff_time": kick(gw).isoformat(),
         "home_code": 8, "away_code": 2, "home_goals": 1, "away_goals": 0}
        for gw in range(1, 9)])
    store.save(hist, "history/player_gw.parquet")
    store.save(fixtures, "history/fixtures.parquet")
    df, _tg, _elo = tr.load_training_frame()
    late = df[df["gw"] == 8]
    assert float(late["role_wb_share"].iloc[0]) == 1.0
    assert float(late["density_pub_7d"].iloc[0]) == 2.0


# --- Task 10: the arm driver's pure parts --------------------------------

import importlib.util as _ilu  # noqa: E402
from pathlib import Path as _P  # noqa: E402


def _driver():
    spec = _ilu.spec_from_file_location("v12_w4_arms",
                                        _P("scripts/v12_w4_arms.py"))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_window_is_the_shifted_one_and_is_stated():
    d = _driver()
    assert (d.TRAIN_MAX_IDX, d.TEST_IDX) == (2, 3)


def test_the_bar_is_v10s_verbatim():
    d = _driver()
    assert d.LOGLOSS_MIN_RELATIVE_GAIN == 0.01
    assert d.GUARD_TOLERANCE == 0.005


def test_there_are_two_arms_and_one_control():
    d = _driver()
    assert set(d.ARMS) == {"baseline", "role", "density"}
    assert d.ARMS["baseline"] == []


def test_the_verdict_keeps_only_on_both_halves():
    d = _driver()
    base = {"p_start_ll_starters": 0.5, "zeros": 1.0}
    assert d.verdict(base, {"p_start_ll_starters": 0.49,
                            "zeros": 1.002})["decision"] == "keep"
    # gain big enough, zeros cost too big
    assert d.verdict(base, {"p_start_ll_starters": 0.40,
                            "zeros": 1.010})["decision"] == "withdraw"
    # zeros fine, gain too small
    assert d.verdict(base, {"p_start_ll_starters": 0.4975,
                            "zeros": 1.000})["decision"] == "withdraw"


def test_the_verdict_says_it_is_only_half_the_rule():
    """The pre-registered rule has two halves and this driver measures one.
    A ``decision`` of ``keep`` here with no autosub-week number beside it is
    an arm shipped on half a gate, so the half is named in the payload the
    gate reads and not only in a docstring nobody diffs."""
    d = _driver()
    out = d.verdict({"p_start_ll_starters": 0.5, "zeros": 1.0},
                    {"p_start_ll_starters": 0.49, "zeros": 1.002})
    assert out["half"] == "a"
    assert "v12_w4_autosub_cf" in out["keep_also_requires"]


def test_coverage_refuses_a_window_with_no_training_rows():
    """The archive's real shape: populated in the test season and nowhere
    else, which is a season indicator and not a feature."""
    d = _driver()
    frame = pd.DataFrame({"season_idx": [3, 3],
                          "role_wb_share": [0.5, 0.25],
                          "role_wb_missing": [0.0, 0.0],
                          "density_pub_7d": [1.0, 2.0],
                          "density_pub_missing": [0.0, 0.0]})
    report = d.coverage(frame, ["role_wb_share", "density_pub_7d"])
    assert report["train_covered"] == 0
    with pytest.raises(SystemExit):
        d.check_coverage(report)


def test_coverage_accepts_a_window_with_training_rows():
    d = _driver()
    frame = pd.DataFrame({"season_idx": [2, 2, 3],
                          "role_wb_share": [0.5, float("nan"), 0.25],
                          "role_wb_missing": [0.0, 1.0, 0.0],
                          "density_pub_7d": [1.0, 2.0, 1.0],
                          "density_pub_missing": [0.0, 0.0, 0.0]})
    report = d.coverage(frame, ["role_wb_share", "density_pub_7d"])
    assert report["train_covered"] > 0
    d.check_coverage(report)   # does not raise


def test_coverage_refuses_a_window_with_no_test_rows():
    d = _driver()
    frame = pd.DataFrame({"season_idx": [2, 2],
                          "role_wb_share": [0.5, 0.25],
                          "density_pub_7d": [1.0, 2.0]})
    report = d.coverage(frame, ["role_wb_share", "density_pub_7d"])
    assert report["test_covered"] == 0
    with pytest.raises(SystemExit):
        d.check_coverage(report)


def test_coverage_survives_a_column_the_frame_never_grew():
    """A missing column is zero coverage, not an AttributeError: the guard
    has to be able to *report* the state it exists to refuse."""
    d = _driver()
    report = d.coverage(pd.DataFrame({"season_idx": [2, 3]}),
                        ["role_wb_share", "density_pub_7d"])
    assert report["train_covered"] == 0
    assert report["per_season"]["2"]["role_wb_share"] == 0.0


def test_the_lever_guard_refuses_an_arm_equal_to_the_control(monkeypatch):
    d = _driver()
    monkeypatch.setitem(d.ARMS, "role", [])
    with pytest.raises(SystemExit):
        d.check_lever(pd.DataFrame({"density_pub_7d": [0.0, 1.0]}))


def test_the_lever_guard_refuses_a_constant_column():
    d = _driver()
    frame = pd.DataFrame({"role_wb_share": [0.5, 0.5],
                          "role_wb_missing": [0.0, 0.0],
                          "density_pub_7d": [0.0, 1.0],
                          "density_pub_missing": [0.0, 0.0]})
    with pytest.raises(SystemExit):
        d.check_lever(frame)


def test_the_arm_composes_from_the_shipped_list_and_not_from_its_predecessor():
    """The loop's own lever guard. ``arm_features`` reads the module global,
    so a driver that assigns ``MINUTES_FEATURES`` twice — shipped, then
    composed — leaves arm n+1 composing on top of arm n and reports the union
    of two arms under the second one's name."""
    d = _driver()
    import inspect
    src = inspect.getsource(d.main)
    assert "tr.MINUTES_FEATURES = list(shipped) + list(ARMS[name])" in src
    assert "tr.MINUTES_FEATURES = shipped\n" not in src.split("finally:")[0]


# --- Task 11: the autosub counterfactual driver --------------------------


def _cf_driver():
    spec = _ilu.spec_from_file_location("v12_w4_autosub_cf",
                                        _P("scripts/v12_w4_autosub_cf.py"))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_counterfactual_shares_the_arms_and_the_window_it_does_not_copy():
    """Two files disagreeing about which columns an arm is, is how a cycle
    reports one arm's numbers under another arm's name."""
    cf = _cf_driver()
    assert sorted(cf.arms_mod.ARMS) == ["baseline", "density", "role"]
    assert (cf.arms_mod.TRAIN_MAX_IDX, cf.arms_mod.TEST_IDX) == (2, 3)


def test_the_solve_every_arm_shares_carries_a_bench_curve():
    """Without a curve there are no bench-slot indicators and a better p_play
    has nothing to move — the gate would measure a lever that is not there."""
    cf = _cf_driver()
    assert sorted(cf.OPT_KW) == ["bench_curve", "bench_weight", "decay",
                                 "ft_use_penalty", "ft_value", "hit_cost",
                                 "itb_value", "vice_weight"]
    assert cf.OPT_KW["bench_curve"]


def test_both_drivers_state_both_halves_of_the_arm_rule():
    """Neither half ships an arm on its own, so neither file is allowed to
    read as though it were the whole gate."""
    d, cf = _driver(), _cf_driver()
    for text in (d.__doc__, cf.__doc__, d.ARM_RULE):
        assert "autosub" in text
        assert "log-loss" in text or "log_loss" in text
    assert "not measurable" in d.ARM_RULE.lower()


def test_each_arm_fits_from_the_shipped_list_and_not_from_its_predecessor():
    import inspect
    src = inspect.getsource(_cf_driver()._fit)
    assert ("tr.MINUTES_FEATURES = list(shipped) "
            "+ list(arms_mod.ARMS[arm])") in src
