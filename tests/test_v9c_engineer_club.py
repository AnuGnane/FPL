"""The as-of club, where the features actually read it.

``bps.as_of_club_code`` derives the column; this file is about what happens
once it is in the frame. Three builders switched — the position-by-club prior,
manager-spell scoping, and the own side of the Elo merge — and one thing
deliberately did not: ``opp_code``, which is fixture-sourced and already
survives a transfer.

The assertion worth reading twice is
``test_future_rows_keep_their_elo_because_the_fallback_is_per_row``. The
tempting shape for :func:`gaffer.features.engineer.as_of_club` is a
column-presence check, and it is wrong in exactly the place that matters:
``build_prediction_frame`` concatenates history (which carries ``club_code``)
with future rows (which cannot), so a frame-level check sees the column
present and reads NaN for every serving row. The Elo merge would then miss on
all of them and the model would predict against a null opponent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from gaffer.features.engineer import (add_context, add_rotation_priors,
                                      as_of_club, build_prediction_frame,
                                      feature_columns)


# --- the helper itself ----------------------------------------------

def test_as_of_club_is_a_per_row_coalesce():
    df = pd.DataFrame({"team_code": [1, 2, 3],
                       "club_code": [7.0, float("nan"), 9.0]})
    assert as_of_club(df).tolist() == [7.0, 2.0, 9.0]


def test_as_of_club_without_the_column_is_the_stamped_club_and_does_not_raise():
    df = pd.DataFrame({"team_code": [1, 2, 3]})
    assert as_of_club(df).tolist() == [1, 2, 3]


def test_club_code_is_not_a_feature_column_so_advise_never_strips_it():
    """Plan A10, pinned without editing a protected file. ``advise.py:548``
    strips ``feature_columns()`` off the training frame before re-deriving;
    ``club_code`` is not in that list, so it rides to serve time for free and
    train and serve see the same club for the same historical row."""
    assert "club_code" not in feature_columns()

    frame = pd.DataFrame({"code": [1], "team_code": [5], "club_code": [9],
                          **{c: [0.0] for c in feature_columns()}})
    stripped = frame.drop(columns=[c for c in feature_columns()
                                   if c in frame.columns])
    assert "club_code" in stripped.columns


# --- the Elo merge --------------------------------------------------

def _elo() -> pd.DataFrame:
    return pd.DataFrame({"season_idx": [3, 3, 3, 3],
                         "gw": [1, 1, 2, 2],
                         "code": [1, 3, 1, 3],
                         "elo_pre": [1500.0, 1600.0, 1510.0, 1590.0]})


def _rows() -> pd.DataFrame:
    """One transferred player: GW1 at club 1, GW2 at club 3, stamped 3."""
    return pd.DataFrame({
        "code": [7, 7],
        "season_idx": [3, 3],
        "gw": [1, 2],
        "team_code": [3, 3],
        "club_code": [1, 3],
        "opp_code": [3, 1],
        "was_home": [False, True],
        "kickoff_time": ["2024-08-17T14:00:00Z", "2024-08-24T14:00:00Z"],
    })


def test_the_elo_merge_uses_the_as_of_club_on_the_own_side():
    out = add_context(_rows(), _elo(), None)
    # GW1: he was at club 1, so 1500 — not club 3's 1600.
    assert out["team_elo"].iloc[0] == 1500.0
    assert out["team_elo"].iloc[1] == 1590.0


def test_the_opponent_side_of_the_elo_merge_is_untouched():
    """Plan A9, asserted explicitly because a regression here would be silent
    and expensive. ``opp_code`` is written per row from the fixture at ingest
    and is already correct through a transfer."""
    out = add_context(_rows(), _elo(), None)
    assert out["opp_elo"].iloc[0] == 1600.0     # faced club 3 in GW1
    assert out["opp_elo"].iloc[1] == 1510.0     # faced club 1 in GW2
    assert out["elo_diff"].iloc[0] == 1500.0 - 1600.0


def test_add_context_leaves_no_scratch_column_behind():
    out = add_context(_rows(), _elo(), None)
    assert "_club" not in out.columns


def test_a_frame_with_no_club_code_merges_exactly_as_it_did_on_main():
    """The degradation direction: with the column absent, the own side reads
    ``team_code`` and every number is what it was before this cycle."""
    without = _rows().drop(columns=["club_code"])
    out = add_context(without, _elo(), None)
    assert out["team_elo"].tolist() == [1600.0, 1590.0]


def test_elo_final_fills_on_the_as_of_club_too():
    rows = _rows().assign(gw=[9, 9])
    out = add_context(rows, _elo(), {1: 1234.0, 3: 4321.0})
    assert out["team_elo"].iloc[0] == 1234.0    # club 1, not the stamped 3


# --- the prediction frame -------------------------------------------

def _future() -> pd.DataFrame:
    return pd.DataFrame({
        "code": [7], "season_idx": [3], "gw": [3], "team_code": [3],
        "opp_code": [1], "was_home": [True], "position": ["MID"],
        "kickoff_time": ["2024-08-31T14:00:00Z"],
    })


def _hist() -> pd.DataFrame:
    return _rows().assign(position=["MID", "MID"], minutes=[90.0, 90.0],
                          starts=[1.0, 1.0], total_points=[5.0, 6.0])


def test_future_rows_keep_their_elo_because_the_fallback_is_per_row():
    """The most valuable single assertion in this file (plan A6). History
    carries ``club_code``; future rows cannot. A ``"club_code" in df.columns``
    check would see it present on the combined frame and read NaN for every
    future row, and every serving prediction would be made against a null
    opponent strength."""
    elo = pd.concat([_elo(), pd.DataFrame(
        {"season_idx": [3, 3], "gw": [3, 3], "code": [1, 3],
         "elo_pre": [1520.0, 1580.0]})], ignore_index=True)
    out = build_prediction_frame(_hist(), _future(), elo=elo,
                                 elo_final=None, tenures=_tenures())
    assert out["team_elo"].notna().all()
    assert out["team_elo"].iloc[0] == 1580.0    # his current club
    assert out["opp_elo"].iloc[0] == 1520.0


# --- the position-by-club prior -------------------------------------

def test_the_shrunken_prior_groups_by_the_as_of_club():
    """A transferred player's pre-transfer contributions belong in his old
    club's ``(position, club)`` bucket, not the new one."""
    from gaffer.features.engineer import _shrunk_ratio

    df = pd.DataFrame({
        "code": [7, 7, 8, 8],
        "position": ["MID"] * 4,
        "season_idx": [3] * 4,
        "gw": [1, 2, 1, 2],
        "team_code": [3, 3, 1, 1],
        "club_code": [1, 3, 1, 1],
    })
    val = pd.Series([4.0, 1.0, 4.0, 4.0])
    den = pd.Series([1.0, 1.0, 1.0, 1.0])

    as_of = _shrunk_ratio(df, val, den, k=1.0)
    stamped = _shrunk_ratio(df.drop(columns=["club_code"]), val, den, k=1.0)
    # Player 8's GW2 prior sees player 7's GW1 row only under the as-of club.
    assert not np.allclose(as_of.to_numpy(), stamped.to_numpy(),
                           equal_nan=True)


# --- manager spells -------------------------------------------------

def _tenures() -> pd.DataFrame:
    return pd.DataFrame({
        "team_code": [1, 3],
        "club": ["Old FC", "New FC"],
        "manager": ["Old Boss", "New Boss"],
        "start_date": pd.to_datetime(["2020-01-01T00:00:00Z"] * 2, utc=True),
        "end_date": pd.to_datetime([None, None], utc=True),
    })


def test_manager_spell_scoping_keys_on_the_as_of_club():
    """The pre-transfer rows belong to the old club's manager, so a
    transferred player has two spells and not one."""
    hist = _hist()
    with_club = add_rotation_priors(hist, _tenures())
    without = add_rotation_priors(hist.drop(columns=["club_code"]),
                                  _tenures())
    # Under the stamped club both rows sit in one spell, so the second row's
    # tenure count is 1; under the as-of club the transfer resets it to 0.
    assert with_club["manager_tenure_matches"].tolist() != \
        without["manager_tenure_matches"].tolist()


def test_a_frame_with_no_club_code_still_builds_the_priors():
    out = add_rotation_priors(_hist().drop(columns=["club_code"]), _tenures())
    assert "manager_tenure_matches" in out.columns
    assert len(out) == 2
