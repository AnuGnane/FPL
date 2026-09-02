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
