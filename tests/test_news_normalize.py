"""The precedence table (spec §4). One row per player code, and the rules that
decide what each column says when the sources disagree."""

from __future__ import annotations

import pandas as pd

from gaffer.data.news.normalize import (AVAIL_COLS, availability_frame,
                                        gw_for_date)


def _official() -> pd.DataFrame:
    return pd.DataFrame([
        {"code": 100, "status": "a", "chance_of_playing": None},
        {"code": 101, "status": "d", "chance_of_playing": 75},
        {"code": 102, "status": "s", "chance_of_playing": 0},
        {"code": 103, "status": "i", "chance_of_playing": 0},
        {"code": 104, "status": "a", "chance_of_playing": None},
    ])


def _events() -> pd.DataFrame:
    return pd.DataFrame({
        "gw": [5, 6, 7, 8],
        "deadline_time": ["2026-09-05T10:00:00Z", "2026-09-12T10:00:00Z",
                          "2026-09-19T10:00:00Z", "2026-09-26T10:00:00Z"]})


def _injury(code, itype, status, date):
    return {"code": code, "injury_type": itype, "news_status": status,
            "expected_return_date": date, "source": "premierinjuries",
            "fetched_at": "2026-09-04T09:00:00+00:00"}


def test_output_shape_is_one_row_per_code_with_the_spec_columns():
    out = availability_frame(_official(), None, None, gw=5, events=_events())
    assert list(out.columns) == AVAIL_COLS
    assert out["code"].is_unique
    assert len(out) == 5


def test_all_empty_news_reproduces_the_official_flags_exactly():
    """The rail every degradation path leans on."""
    official = _official()
    out = availability_frame(official, None, None, gw=5, events=_events())
    merged = out.merge(official, on="code", suffixes=("", "_off"))
    assert (merged["status"] == merged["status_off"]).all()
    assert (merged["chance_of_playing"].fillna(-1).to_numpy()
            == merged["chance_of_playing_off"].fillna(-1).to_numpy()).all()
    assert out["p_start_hint"].isna().all()
    assert out["injury_type"].isna().all()


def test_a_ban_is_authoritative_and_news_never_lifts_it():
    """Spec §4 rule 1: official s/u/n outranks everything. A predicted XI that
    names a suspended player is the site being wrong, not news."""
    injuries = pd.DataFrame([_injury(102, "knock", "doubtful", None)])
    lineups = pd.DataFrame([{"code": 102, "p_start_hint": 1.0,
                             "source": "lineups", "fetched_at": "x"}])
    out = availability_frame(_official(), injuries, lineups, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[102, "status"] == "s"
    assert out.loc[102, "chance_of_playing"] == 0
    assert pd.isna(out.loc[102, "p_start_hint"])
    assert pd.isna(out.loc[102, "injury_type"])


def test_news_sharpens_an_unflagged_player_before_the_flag_catches_up():
    """Spec §4 rule 2, and the entire point of the source: the injury press
    has him out on Thursday, FPL flags him on Friday."""
    injuries = pd.DataFrame([
        _injury(100, "hamstring", "out", pd.Timestamp("2026-09-20").date())])
    out = availability_frame(_official(), injuries, None, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[100, "status"] == "i"
    assert out.loc[100, "chance_of_playing"] == 0
    assert out.loc[100, "injury_type"] == "hamstring"
    assert out.loc[100, "expected_return_gw"] == 8
    assert out.loc[100, "source"] == "premierinjuries"


def test_the_most_pessimistic_current_gw_view_wins():
    """Spec §4 rule 4. Official says 75%, the press says out until GW8: out
    wins. Benching a surprise starter costs a few points; captaining a late
    scratch costs the week."""
    injuries = pd.DataFrame([
        _injury(101, "calf", "out", pd.Timestamp("2026-09-20").date())])
    out = availability_frame(_official(), injuries, None, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[101, "chance_of_playing"] == 0
    assert out.loc[101, "status"] == "d"     # the official flag is not raised


def test_news_never_raises_a_players_official_chance():
    """The pessimism rule runs one way only: a "back this week" listing cannot
    upgrade a player FPL has at 25%."""
    official = pd.DataFrame([{"code": 101, "status": "d",
                              "chance_of_playing": 25}])
    injuries = pd.DataFrame([
        _injury(101, "knock", "doubtful", pd.Timestamp("2026-09-05").date())])
    out = availability_frame(official, injuries, None, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[101, "chance_of_playing"] == 25


def test_a_listed_injury_returning_this_week_is_a_doubt_not_a_zero():
    from gaffer.data.news.normalize import NEWS_RETURNS_THIS_GW

    injuries = pd.DataFrame([
        _injury(100, "knock", "doubtful", pd.Timestamp("2026-09-05").date())])
    out = availability_frame(_official(), injuries, None, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[100, "chance_of_playing"] == NEWS_RETURNS_THIS_GW
    assert out.loc[100, "expected_return_gw"] == 5


def test_an_injury_with_no_date_records_the_type_without_moving_the_flag():
    """No date is no claim about this gameweek. The type still rides along,
    because the horizon decay wants it even when the current GW does not."""
    injuries = pd.DataFrame([_injury(104, "illness", "doubtful", None)])
    out = availability_frame(_official(), injuries, None, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[104, "injury_type"] == "illness"
    assert out.loc[104, "status"] == "a"
    assert pd.isna(out.loc[104, "chance_of_playing"])


def test_a_start_hint_rides_along_without_touching_the_official_flag():
    """The hint is applied by apply_availability, not folded into
    chance_of_playing here — it is a GW1-only ceiling and this frame has no
    gameweek axis."""
    lineups = pd.DataFrame([{"code": 104, "p_start_hint": 0.25,
                             "source": "lineups", "fetched_at": "x"}])
    out = availability_frame(_official(), None, lineups, gw=5,
                             events=_events()).set_index("code")
    assert out.loc[104, "p_start_hint"] == 0.25
    assert out.loc[104, "status"] == "a"
    assert pd.isna(out.loc[104, "chance_of_playing"])


def test_news_rows_for_unknown_codes_are_dropped_not_appended():
    """The frame is keyed to the official roster: a code the bootstrap does
    not carry has nothing downstream to merge onto."""
    injuries = pd.DataFrame([_injury(999, "knee", "out", None)])
    out = availability_frame(_official(), injuries, None, gw=5,
                             events=_events())
    assert 999 not in set(out["code"])
    assert len(out) == 5


def test_gw_for_date_picks_the_first_gameweek_at_or_after_the_return():
    assert gw_for_date(_events(), pd.Timestamp("2026-09-13").date()) == 7
    assert gw_for_date(_events(), pd.Timestamp("2026-09-05").date()) == 5
    # Past the end of the calendar, and no calendar at all.
    assert gw_for_date(_events(), pd.Timestamp("2027-01-01").date()) is None
    assert gw_for_date(None, pd.Timestamp("2026-09-13").date()) is None
    assert gw_for_date(_events(), None) is None
