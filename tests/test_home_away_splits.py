"""C3's home/away splits, the code shipped off (holiday F-92).

ROADMAP candidate 5 (GUIDE §12.5 item 5), as F-81 shipped C2's step:
``models.train.HOME_AWAY_SPLITS`` is off, and off the training frame and the
attacking head's feature list are today's. On, the frame carries
``engineer.SPLIT_COLUMNS``, the head reads them, and the serve-time frame
rebuilds them from the history it is handed. The builder moved from
``scripts/c3_home_away.py`` into ``features/engineer.py`` and the script
imports it back, so there is one definition. The replay and its verdict are
the Mac's (v20 spec §4).
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from gaffer.features import engineer
from gaffer.features.engineer import (
    SPLIT_COLUMNS,
    add_venue_splits,
    build_prediction_frame,
    latest_venue_splits,
)
from gaffer.models import train as train_mod
from tests.test_train import _bps_fixtures, _bps_history, _stub_store

sys.path.insert(0, "scripts")

import c3_home_away  # noqa: E402 — scripts/ is not a package; the path insert must come first


def _training_frame(monkeypatch, on: bool) -> pd.DataFrame:
    monkeypatch.setattr(train_mod, "HOME_AWAY_SPLITS", on)
    history = _bps_history(year=2022, season_idx=0)
    history["xg"] = 0.1 * (history["gw"] + history["code"] - 100)
    _stub_store(monkeypatch, train_mod,
                history=history,
                fixtures=_bps_fixtures(year=2022, season_idx=0))
    df, _tg, _elo = train_mod.load_training_frame()
    return df


def _one_player(home: list[int], xg: list[float]) -> pd.DataFrame:
    n = len(home)
    return pd.DataFrame({
        "code": [1] * n, "season_idx": [0] * n, "gw": list(range(1, n + 1)),
        "home": home, "xg": xg, "xa": 0.0, "goals": 0, "assists": 0})


def test_the_switch_ships_off():
    assert train_mod.HOME_AWAY_SPLITS is False


def test_off_the_training_frame_and_the_head_read_todays_columns(monkeypatch):
    df = _training_frame(monkeypatch, on=False)
    assert set(SPLIT_COLUMNS) & set(df.columns) == set()
    assert set(SPLIT_COLUMNS) & set(train_mod.attacking_features()) == set()


def test_on_adds_the_eight_columns_and_moves_nothing_else(monkeypatch):
    off = _training_frame(monkeypatch, on=False)
    on = _training_frame(monkeypatch, on=True)
    assert len(SPLIT_COLUMNS) == 8
    assert sorted(c for c in on.columns if c not in off.columns) == sorted(
        SPLIT_COLUMNS)
    assert [c for c in on.columns if c in off.columns] == list(off.columns)
    pd.testing.assert_frame_equal(on[list(off.columns)], off)
    feats = train_mod.attacking_features()
    assert feats[-len(SPLIT_COLUMNS):] == SPLIT_COLUMNS


def test_a_rows_own_match_never_enters_its_columns():
    out = add_venue_splits(_one_player([1, 0, 1, 0, 1],
                                       [1.0, 10.0, 3.0, 20.0, 5.0]))
    home = out["xg_home_r5"].tolist()
    away = out["xg_away_r5"].tolist()
    assert home[1:] == [1.0, 1.0, 2.0, 2.0]
    assert away[2:] == [10.0, 10.0, 15.0]
    # The fifth row's own 5.0 would make the home mean 3.0.
    assert home[4] != 3.0


def test_a_player_with_no_earlier_row_at_a_venue_reads_nan():
    out = add_venue_splits(_one_player([1, 1, 0], [2.0, 4.0, 9.0]))
    assert out["xg_away_r5"].isna().all()
    assert np.isnan(out["xg_home_r5"].iloc[0])


def test_the_builder_reads_was_home_before_add_context_builds_home():
    raw = _one_player([1, 0, 1], [1.0, 10.0, 3.0]).rename(
        columns={"home": "was_home"})
    built = add_venue_splits(_one_player([1, 0, 1], [1.0, 10.0, 3.0]))
    pd.testing.assert_frame_equal(add_venue_splits(raw)[SPLIT_COLUMNS],
                                  built[SPLIT_COLUMNS])


def test_the_script_shares_the_builder():
    assert c3_home_away.add_venue_splits is engineer.add_venue_splits
    assert c3_home_away.SPLIT_COLUMNS is engineer.SPLIT_COLUMNS


def test_the_serve_time_value_is_what_training_puts_on_the_next_row():
    hist = _one_player([1, 0, 1, 0, 1, 1, 1, 1],
                       [1.0, 10.0, 3.0, 20.0, 5.0, 7.0, 9.0, 11.0])
    nxt = _one_player([1] * 9, [0.0] * 9).iloc[[-1]]
    trained = add_venue_splits(pd.concat([hist, nxt], ignore_index=True))
    served = latest_venue_splits(hist)
    for col in SPLIT_COLUMNS:
        want, got = trained[col].iloc[-1], served.loc[1, col]
        assert (np.isnan(want) and np.isnan(got)) or want == pytest.approx(got)


def _future(hist: pd.DataFrame) -> pd.DataFrame:
    last = hist[hist["gw"] == hist["gw"].max()]
    return last[["code", "season_idx", "position", "team_code",
                 "opp_code", "was_home"]].assign(
        gw=last["gw"] + 1, kickoff_time="2022-08-20T14:00:00Z")


@pytest.mark.parametrize("on", [False, True])
def test_the_prediction_frame_carries_the_splits_only_when_trained_on(
        monkeypatch, on):
    hist = _training_frame(monkeypatch, on=on)
    hist = hist.drop(columns=[c for c in engineer.feature_columns()
                              if c in hist.columns])
    frame = build_prediction_frame(hist, _future(hist), tenures=None)
    if not on:
        assert set(SPLIT_COLUMNS) & set(frame.columns) == set()
        return
    want = latest_venue_splits(hist).reindex(frame["code"])
    pd.testing.assert_frame_equal(frame[SPLIT_COLUMNS].reset_index(drop=True),
                                  want.reset_index(drop=True))
    # The home pair (codes 100, 101) played home in all three weeks.
    assert frame.set_index("code").loc[100, "xg_home_r5"] == pytest.approx(0.2)
