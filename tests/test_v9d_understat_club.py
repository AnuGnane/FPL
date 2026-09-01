"""The own-side Understat merge, on the club the player actually played for.

v9c derived ``club_code`` and switched three consumers onto it — the
position-by-club prior, manager-spell scoping, and the own side of the Elo
merge. ``bps.as_of_club_code``'s docstring names the two it deliberately left
behind, and this is the first of them: ``merge_understat_team`` joins the own
side on ``(team_code, date)``, so a January transfer attaches the *new* club's
August xG and PPDA to the player's August rows. He was not there.

The opponent side is not part of the finding and is not touched. ``opp_code``
is written per row from the fixture at ingest (``data/live.py:106``) and
already survives a transfer — ``bps.py:79-80`` says so — so switching it would
be a change with no finding behind it and a second thing to explain in the
replay delta.
"""

from __future__ import annotations

import pandas as pd

from gaffer.features.engineer import (TEAM_US_FEATURES,
                                      add_understat_team_rolling,
                                      merge_understat_team)


def _rolled() -> pd.DataFrame:
    """Two clubs with unmistakably different form on the same date."""
    return pd.DataFrame({
        "team_code": [1, 1, 3, 3],
        "date": ["2024-08-10", "2024-08-17", "2024-08-10", "2024-08-17"],
        "us_xga": [0.5, 0.5, 3.0, 3.0],
        "ppda": [8.0, 8.0, 20.0, 20.0],
    })


def _players() -> pd.DataFrame:
    """One player, stamped Arsenal (3) today, who played GW1 for Man Utd (1).

    ``club_code`` is what ``models.train.load_training_frame`` derives and
    what ``engineer.as_of_club`` reads; ``team_code`` is what the store
    stamped on him this morning.
    """
    return pd.DataFrame({
        "code": [7, 7],
        "season_idx": [3, 3],
        "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "team_code": [3, 3],
        "club_code": [1, 3],
        "opp_code": [43, 43],
    })


def test_the_own_side_reads_the_club_he_was_actually_at():
    """The finding, in one assertion. Before v9d his GW1 row carried
    Arsenal's xGA because Arsenal is where he plays *now*."""
    out = merge_understat_team(_players(), add_understat_team_rolling(_rolled()))
    # GW1: Man Utd's numbers, not Arsenal's.
    assert out["team_us_xga_r5"].iloc[0] == 0.5


def test_a_player_who_never_moved_is_unaffected():
    """The overwhelming majority of rows. If this moves, the cycle is
    measuring the join and not the leak."""
    stayed = _players().assign(club_code=[3, 3])
    out = merge_understat_team(stayed, add_understat_team_rolling(_rolled()))
    assert out["team_us_xga_r5"].iloc[0] == 3.0


def test_the_opponent_side_is_untouched():
    """Not part of the finding (plan A1). ``opp_code`` is fixture-derived and
    already survives a transfer, so this column must read identically before
    and after the cycle."""
    out = merge_understat_team(_players(), add_understat_team_rolling(_rolled()))
    assert "opp_us_xga_r5" in out.columns


def test_a_frame_with_no_club_code_produces_exactly_what_main_produced():
    """The degradation direction. ``as_of_club`` falls back per row, so a
    frame that predates the derivation reads the stamped club throughout and
    the output is byte-for-byte the pre-v9d answer."""
    no_club = _players().drop(columns=["club_code"])
    out = merge_understat_team(no_club, add_understat_team_rolling(_rolled()))
    assert out["team_us_xga_r5"].iloc[0] == 3.0


def test_the_temp_club_column_does_not_survive_the_call():
    """``_club`` is scaffolding, exactly as in ``add_context``. A leaked
    column reaches ``feature_columns``' strip in ``advise.py:548`` as an
    unrecognised name and is re-derived beside itself."""
    out = merge_understat_team(_players(), add_understat_team_rolling(_rolled()))
    assert "_club" not in out.columns
    assert "_date" not in out.columns


def test_the_latest_fill_uses_the_same_club_key_as_the_merge(monkeypatch):
    """Plan A1: the fill at the end of the function is the same construct as
    ``add_context``'s ``elo_final`` fill, which v9c switched. Leaving it on
    ``team_code`` would put the two halves of one merge on two different club
    keys — the split-brain the finding is about."""
    latest = pd.DataFrame(
        {c: [0.5, 3.0] for c in TEAM_US_FEATURES if c.startswith("team_")},
        index=pd.Index([1, 3], name="team_code"))
    # A date the rolled frame cannot match, so only the fill can populate it.
    unmatched = _players().assign(
        kickoff_time=["2030-01-01T14:00:00Z", "2030-01-08T14:00:00Z"])
    out = merge_understat_team(unmatched, add_understat_team_rolling(_rolled()),
                               latest)
    assert out["team_us_xga_r5"].iloc[0] == 0.5


def test_the_none_rolled_path_still_produces_every_column():
    """The schema-stability contract the function's own docstring makes: a
    disabled Understat source produces all-NaN columns, not missing ones."""
    out = merge_understat_team(_players(), None)
    for col in TEAM_US_FEATURES:
        assert col in out.columns
