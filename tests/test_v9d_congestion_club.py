"""Cup-tie congestion, counted for the club he was actually at.

``_recent_load`` counts league matches per *player* and cup ties per *club* —
the cup files carry no player rows, and a midweek tie is a squad-level event
either way. The club it counted for was the stamped ``team_code``, so a
transferred player's August rows were credited with his new club's August cup
run: a Thursday tie he did not travel to, inflating the congestion feature in
the direction of "rested less than he was".

The second of the two consumers ``bps.as_of_club_code`` left for v9d.
"""

from __future__ import annotations

import pandas as pd

from gaffer.features.engineer import CONGESTION_FEATURES, add_congestion


def _cups() -> pd.DataFrame:
    """Only Arsenal (3) played midweek. Man Utd (1) did not."""
    return pd.DataFrame({"team_code": [3],
                         "date": ["2024-08-14T19:45:00Z"]})


def _players() -> pd.DataFrame:
    """Stamped Arsenal today; played the 17th for Man Utd."""
    return pd.DataFrame({
        "code": [7],
        "season_idx": [3],
        "gw": [1],
        "kickoff_time": ["2024-08-17T14:00:00Z"],
        "team_code": [3],
        "club_code": [1],
    })


def test_the_cup_tie_counts_for_the_club_he_was_actually_at():
    """The finding. Arsenal's midweek tie is not his midweek tie."""
    out = add_congestion(_players(), _cups())
    assert out["matches_last_14d"].iloc[0] == 0.0


def test_a_player_who_never_moved_still_gets_his_clubs_tie():
    """The switch must be a no-op for the overwhelming majority of rows."""
    stayed = _players().assign(club_code=[3])
    out = add_congestion(stayed, _cups())
    assert out["matches_last_14d"].iloc[0] == 1.0


def test_a_frame_with_no_club_code_produces_exactly_what_main_produced():
    out = add_congestion(_players().drop(columns=["club_code"]), _cups())
    assert out["matches_last_14d"].iloc[0] == 1.0


def test_a_frame_with_no_team_code_still_returns_the_league_count(monkeypatch):
    """Plan A3: the guard at the top of the cup block stays as written even
    though the line below it no longer reads ``team_code`` directly.
    ``as_of_club`` *falls back* to that column and raises KeyError without
    it, so deleting the guard as "now unused" would turn a clean early
    return into a crash on every simple-component frame."""
    thin = _players().drop(columns=["team_code", "club_code"])
    out = add_congestion(thin, _cups())
    assert out["matches_last_14d"].iloc[0] == 0.0


def test_every_congestion_column_is_still_produced():
    out = add_congestion(_players(), _cups())
    for col in CONGESTION_FEATURES:
        assert col in out.columns


def test_no_cups_frame_is_unaffected():
    out = add_congestion(_players(), None)
    assert out["matches_last_14d"].iloc[0] == 0.0
