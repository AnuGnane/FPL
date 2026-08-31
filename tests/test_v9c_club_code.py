"""Which club did this player actually play for that week?

``data/live.py`` rebuilds the whole player history each run and stamps the
player's *current* ``team_code`` onto every row of it (``live.py:170``, via
``history_to_rows``'s ``row.update(player_meta)``). So a January transfer
silently rewrites his August rows under his new club, and three feature
builders that key on club — the position-by-club prior, manager-spell
scoping, and the team-Elo merge — read a squad he had not joined yet.

``opp_code`` does not have this problem: it is written per row from the
fixture (``live.py:106``). That asymmetry is the whole derivation. Join the
fixture list on ``(season_idx, gw, kickoff_time)``, find the fixture whose
opponent matches, and the player's club is the *other* side.

``bps.fixture_key`` already does this join for the BPS restatement, including
the semantics that matter when the data is bad, so this is an extraction and
not a second implementation.
"""

from __future__ import annotations

import pandas as pd

from gaffer.features.bps import as_of_club_code, fixture_key


def _fixtures() -> pd.DataFrame:
    """Two seasons. Arsenal (3) host Man Utd (1) in each."""
    return pd.DataFrame({
        "season_idx": [3, 3, 4],
        "gw": [1, 2, 1],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z",
                         "2025-08-16T14:00:00Z"],
        "home_code": [3, 43, 3],
        "away_code": [1, 3, 1],
        "home_goals": [1.0, 2.0, 0.0],
        "away_goals": [0.0, 2.0, 3.0],
    })


def _transferred() -> pd.DataFrame:
    """One player, stamped as Arsenal (3) today, who played GW1 for Man Utd.

    His GW1 row says ``opp_code = 3`` — he faced Arsenal — while ``team_code``
    claims he *was* Arsenal. Both cannot be true, and the fixture list is the
    one that was written at the time.
    """
    return pd.DataFrame({
        "code": [7, 7],
        "season_idx": [3, 3],
        "gw": [1, 2],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
        "team_code": [3, 3],
        "opp_code": [3, 43],
        "was_home": [False, True],
    })


# --- the derivation -------------------------------------------------

def test_a_transferred_players_old_rows_carry_his_old_club():
    """The finding, in one assertion."""
    club = as_of_club_code(_transferred(), _fixtures())
    assert club.iloc[0] == 1        # he was Man Utd in GW1
    assert club.iloc[1] == 3        # and Arsenal by GW2


def test_a_player_who_never_moved_gets_the_same_club_he_is_stamped_with():
    """The overwhelming majority of rows. The column must be a no-op for
    them, or the delta this cycle measures is measuring the join and not the
    leak."""
    stayed = _transferred().assign(team_code=[1, 1], opp_code=[3, 3],
                                   gw=[1, 1], season_idx=[3, 4],
                                   was_home=[False, False],
                                   kickoff_time=["2024-08-17T14:00:00Z",
                                                 "2025-08-16T14:00:00Z"])
    club = as_of_club_code(stayed, _fixtures())
    assert club.tolist() == [1, 1]


def test_was_home_cross_checks_the_side_and_a_disagreement_falls_back():
    """A row whose ``was_home`` contradicts the side the join assigned is
    describing a different match from the fixture it matched. Trusting the
    join there would invent a club; the fallback at least says something the
    store already believed."""
    lying = _transferred().assign(was_home=[True, True])
    club = as_of_club_code(lying, _fixtures())
    assert club.iloc[0] == 3        # fell back to team_code


# --- what happens when the join misses ------------------------------

def test_a_row_matching_no_fixture_falls_back_to_the_stamped_club():
    orphan = _transferred().assign(gw=[97, 98])
    assert as_of_club_code(orphan, _fixtures()).tolist() == [3, 3]


def test_a_season_with_no_fixture_list_at_all_falls_back_wholesale():
    """Older seasons in ``history/`` predate the fixture archive. They keep
    the stamped club and the cycle records how many rows that is (spec §3:
    backfilling them is out of scope)."""
    club = as_of_club_code(_transferred(), _fixtures().iloc[0:0])
    assert club.tolist() == [3, 3]


def test_an_ambiguous_fixture_key_falls_back_rather_than_mis_keying():
    """``fixture_key``'s corrupt-duplicate semantics, inherited: a
    ``(season, gw, kickoff, team)`` claimed by two different fixtures is
    poisoned to ``None`` rather than resolved last-wins, so the row falls
    back. A mis-keyed club is worse than a stale one — it is a club the
    player has never played for."""
    dupes = pd.concat([_fixtures(), _fixtures().iloc[[0]].assign(away_code=99)],
                      ignore_index=True)
    assert as_of_club_code(_transferred(), dupes).iloc[0] == 3


def test_the_result_is_never_nan_and_never_a_float():
    """G2's rail. A NaN here would scatter every downstream groupby into a
    silent extra bucket, and a float club code would not compare equal to the
    int one in the Elo frame."""
    club = as_of_club_code(_transferred(), _fixtures())
    assert club.notna().all()
    assert str(club.dtype).startswith("int") or club.map(
        lambda v: float(v).is_integer()).all()


def test_a_frame_missing_the_join_columns_degrades_instead_of_raising():
    thin = _transferred().drop(columns=["kickoff_time"])
    assert as_of_club_code(thin, _fixtures()).tolist() == [3, 3]


# --- the extraction did not move fixture_key ------------------------

def test_fixture_key_still_answers_exactly_what_it_did():
    """Belt and braces beside ``tests/test_bps.py``, which must pass
    unmodified: the extraction is a refactor, and a refactor that changes an
    answer is a rewrite."""
    keys = fixture_key(_transferred(), _fixtures())
    assert keys.notna().all()
    assert keys.iloc[0] != keys.iloc[1]
