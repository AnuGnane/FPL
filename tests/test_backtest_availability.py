"""The replay's availability mode, shipped off (holiday F-122).

ROADMAP candidate 1's replay half, step one (v20 spec §4): the replay applies
no availability layer (``run_backtest``'s docstring), so C1's ablation could
not run on it. ``REPLAY_AVAILABILITY`` swaps in the shadow log's banked
``p_play_<mode>`` for the gameweek being played; these pin the swap on a
synthetic ``comp`` frame and a stub shadow frame.
"""

from __future__ import annotations

import pandas as pd
import pytest

import gaffer.backtest as bt
from gaffer.news_shadow import SHADOW_COLS


def _comp() -> pd.DataFrame:
    """Three players at gameweek 5, then the same three at gameweek 6."""
    return pd.DataFrame({
        "code": [101, 102, 103, 101, 102, 103],
        "season_idx": 0,
        "gw": [5, 5, 5, 6, 6, 6],
        "p_play": [0.9, 0.8, 0.7, 0.9, 0.8, 0.7],
        "e_min": [80.0, 70.0, 60.0, 80.0, 70.0, 60.0]})


def _shadow(rows: list[tuple]) -> pd.DataFrame:
    """``(season, gw, code, p_play_news, p_play_flags, run_at)`` rows."""
    out = pd.DataFrame(rows, columns=["season", "gw", "code", "p_play_news",
                                      "p_play_flags", "run_at"])
    for col in SHADOW_COLS:
        if col not in out.columns:
            out[col] = float("nan")
    return out[SHADOW_COLS]


SHADOW = _shadow([
    ("2025-26", 5, 101, 0.10, 0.25, "2025-09-26T10:00:00+00:00"),
    ("2025-26", 5, 102, 0.50, 0.75, "2025-09-26T10:00:00+00:00"),
    ("2025-26", 6, 101, 0.00, 0.00, "2025-10-03T10:00:00+00:00"),
])


def test_the_switch_ships_off():
    assert bt.REPLAY_AVAILABILITY is None


def test_none_leaves_the_frame_untouched_and_prints_no_line():
    comp = _comp()
    out, line = bt.apply_replay_availability(comp, SHADOW, None, "2025-26", 5)
    assert out is comp
    assert line is None


def test_flags_replaces_the_matched_rows_and_only_them():
    out, _ = bt.apply_replay_availability(_comp(), SHADOW, "flags",
                                          "2025-26", 5)
    assert out.loc[out["gw"] == 5, "p_play"].tolist() == [0.25, 0.75, 0.7]
    assert out["e_min"].tolist() == _comp()["e_min"].tolist()


def test_news_reads_its_own_column():
    out, _ = bt.apply_replay_availability(_comp(), SHADOW, "news",
                                          "2025-26", 5)
    assert out.loc[out["gw"] == 5, "p_play"].tolist() == [0.10, 0.50, 0.7]


def test_a_later_horizon_week_keeps_its_number():
    out, _ = bt.apply_replay_availability(_comp(), SHADOW, "flags",
                                          "2025-26", 5)
    # The shadow has a gameweek-6 row for 101, but at gameweek 5's deadline
    # that row did not exist yet: the horizon week keeps the model's number.
    assert out.loc[out["gw"] == 6, "p_play"].tolist() == [0.9, 0.8, 0.7]


def test_a_season_mismatch_replaces_nothing():
    out, line = bt.apply_replay_availability(_comp(), SHADOW, "flags",
                                             "2024-25", 5)
    assert out["p_play"].tolist() == _comp()["p_play"].tolist()
    assert "replaced=0 of 3" in line


def test_the_latest_run_of_the_week_wins():
    shadow = pd.concat([SHADOW, _shadow([
        ("2025-26", 5, 101, 0.40, 0.60, "2025-09-27T09:00:00+00:00")])],
        ignore_index=True)
    out, _ = bt.apply_replay_availability(_comp(), shadow, "flags",
                                          "2025-26", 5)
    assert out.loc[(out["gw"] == 5) & (out["code"] == 101),
                   "p_play"].item() == 0.60


def test_the_lever_line_counts_the_replaced_rows():
    _, line = bt.apply_replay_availability(_comp(), SHADOW, "flags",
                                           "2025-26", 5)
    assert line == ("REPLAY_AVAILABILITY flags gw=5 replaced=2 of 3 "
                    "mean_before=0.8000 mean_after=0.5667")


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="REPLAY_AVAILABILITY"):
        bt.apply_replay_availability(_comp(), SHADOW, "presser", "2025-26", 5)


def test_the_replay_loads_the_shadow_only_when_the_switch_is_on(monkeypatch):
    calls = []
    monkeypatch.setattr(bt, "load_shadow",
                        lambda: calls.append(1) or SHADOW)
    monkeypatch.setattr(bt, "REPLAY_AVAILABILITY", None)
    assert bt.replay_shadow("2025-26") is None
    assert calls == []
    monkeypatch.setattr(bt, "REPLAY_AVAILABILITY", "flags")
    cut = bt.replay_shadow("2025-26")
    assert calls == [1]
    assert set(cut["season"]) == {"2025-26"}
