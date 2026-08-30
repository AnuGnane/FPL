"""The v6 penalty term measured forward: takers predicted vs pens taken."""

from __future__ import annotations

import pandas as pd

from gaffer.pen_tracker import (attach_npxg, finished_gws, predicted_ep,
                                realized_pens)


def _week() -> pd.DataFrame:
    """One finished gameweek of live rows: two clubs, two spot kicks.

    Code 10 is his club's first-choice taker and scored one (xg 1.05 against
    an open-play 0.20 — a 0.85 gap, one penalty's worth). Code 12 has no
    recorded order and missed one.
    """
    return pd.DataFrame({
        "gw": [1, 1, 1],
        "code": [10, 11, 12],
        "name": ["First Choice", "Second Name", "Other Club"],
        "position": ["MID", "FWD", "DEF"],
        "team_code": [3, 3, 7],
        "kickoff_time": ["2026-08-22T14:00:00Z"] * 3,
        "xg": [1.05, 0.20, 0.30],
        "pens_missed": [0, 0, 1],
        "penalties_order": [1.0, 2.0, None]})


def _understat() -> pd.DataFrame:
    return pd.DataFrame({
        "season": ["2026-27"] * 3,
        "season_idx": [4] * 3,
        "code": [10, 11, 12],
        "date": ["2026-08-22"] * 3,
        "us_npxg": [0.20, 0.20, 0.30]})


def _events() -> pd.DataFrame:
    return pd.DataFrame({"gw": [1, 2, 3], "finished": [True, False, False]})


def _with_understat(monkeypatch, tmp_path, us=None):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    store_mod.save(_understat() if us is None else us,
                   "history/understat_player.parquet")


def test_finished_gameweeks_are_the_ones_the_league_has_played():
    assert finished_gws(_events()) == [1]


def test_an_events_frame_without_the_column_yields_nothing():
    assert finished_gws(pd.DataFrame({"gw": [1]})) == []


def test_the_understat_join_lands_on_the_uk_match_date(tmp_path, monkeypatch):
    """Understat carries no gameweek number, so the key is the player and the
    date — unique even in a double gameweek."""
    _with_understat(monkeypatch, tmp_path)
    out = attach_npxg(_week(), "2026-27")
    assert list(out["us_npxg"]) == [0.20, 0.20, 0.30]
    assert len(out) == 3


def test_a_season_understat_has_never_seen_is_no_join(tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    assert attach_npxg(_week(), "2028-29") is None


def test_no_understat_parquet_at_all_is_no_join(tmp_path, monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    assert attach_npxg(_week(), "2026-27") is None


def test_the_xg_gap_instrument_counts_the_penalty_that_was_taken(
        tmp_path, monkeypatch):
    _with_understat(monkeypatch, tmp_path)
    events, instrument = realized_pens(_week(), "2026-27")
    assert instrument == "xg_gap"
    assert list(events) == [1.0, 0.0, 0.0]


def test_without_understat_it_degrades_to_pens_missed(tmp_path, monkeypatch):
    """A floor, not a count — every converted spot kick is invisible to the
    FPL feed alone — so the instrument is named and the two never mix."""
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    events, instrument = realized_pens(_week(), "2026-27")
    assert instrument == "pens_missed_only"
    assert list(events) == [0.0, 0.0, 1.0]


def test_a_frame_with_neither_signal_reports_no_penalties(tmp_path,
                                                          monkeypatch):
    from gaffer.data import store as store_mod

    monkeypatch.setattr(store_mod, "DATA_DIR", tmp_path)
    bare = _week().drop(columns=["xg", "pens_missed"])
    events, instrument = realized_pens(bare, "2026-27")
    assert instrument == "pens_missed_only"
    assert list(events) == [0.0, 0.0, 0.0]


def test_the_component_file_gives_the_pen_term_that_was_served(tmp_path,
                                                               monkeypatch):
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    pd.DataFrame({"code": [10, 11], "gw": [1, 1],
                  "ep_pen_taker": [0.42, 0.0]}).to_parquet(
                      tmp_path / "components_gw1.parquet", index=False)
    assert predicted_ep(1) == {"rows": 2, "ep_pen_taker": 0.42, "takers": 1}


def test_a_gameweek_with_no_component_file_predicted_nothing(tmp_path,
                                                             monkeypatch):
    """The tracker covers a whole season and the earliest weeks of one
    predate the artifact — that is a zero, not an error."""
    from gaffer import artifacts

    monkeypatch.setattr(artifacts, "REPORTS", tmp_path)
    assert predicted_ep(1) == {"rows": 0, "ep_pen_taker": 0.0, "takers": 0}
