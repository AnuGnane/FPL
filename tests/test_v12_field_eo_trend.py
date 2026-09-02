"""Spec §3.3, at the grain the log has: gameweek to gameweek.

Three measured facts decide this and each is in the plan's A4:

* ``run_field_scrape`` exits on ``_already_banked`` before it builds a client,
  so the Sunday plist never writes a second sample for one gameweek — the live
  log holds 123 rows, one gameweek, one snap_date;
* picks are frozen after the deadline (the scrape is deliberately
  post-deadline, ``field.py:280-291``), so two same-gameweek samples would
  differ only by which ~300 entries were drawn;
* ``eo_from_picks`` returns **percent** with captaincy counted double, so the
  live log's maximum is 214.7 and the spec's clamp to [0, 1] would floor the
  entire instrument.

So the trend is between the latest sample of the requested gameweek and the
latest sample of the newest earlier gameweek, and ``deadline_eo`` extrapolates
**one gameweek forward** — the only interval over which field ownership moves
at all, since nobody's picks for the next gameweek are public before its
deadline.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import field


def _log(rows):
    """``(season, gw, snap_date, element, eo)`` -> a field-EO log frame."""
    return pd.DataFrame(
        [{"season": s, "gw": g, "snap_date": d, "element": e, "eo": v,
          "se": 2.0, "n": 300} for s, g, d, e, v in rows])


@pytest.fixture()
def logged(monkeypatch):
    def install(rows):
        monkeypatch.setattr(field, "load_field_eo", lambda: _log(rows))
    return install


def test_one_gameweek_of_samples_has_no_trend(logged):
    """Today's state, and it must read as "no trend" rather than as zero
    drift. A delta of 0.0 is a measurement; this is the absence of one."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0)])
    out = field.field_eo_trend("2026-27", 2)
    assert out[100]["trend_available"] is False
    assert out[100]["delta"] is None
    assert out[100]["deadline_eo"] == 40.0
    assert out[100]["eo_last"] == 40.0


def test_two_gameweeks_extrapolate_one_gameweek_forward(logged):
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[100]["trend_available"] is True
    assert out[100]["eo_first"] == 40.0
    assert out[100]["eo_last"] == 46.0
    assert out[100]["delta"] == 6.0
    assert out[100]["gws_between"] == 1
    assert out[100]["deadline_eo"] == 52.0


def test_a_gap_in_the_log_divides_the_delta_by_the_gap(logged):
    """GW2 and GW5 with nothing between: six points over three gameweeks is
    two a week, not six."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 5, "2026-09-21", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 5)
    assert out[100]["gws_between"] == 3
    assert out[100]["deadline_eo"] == 48.0


def test_the_latest_snapshot_of_each_gameweek_is_the_one_used(logged):
    logged([("2026-27", 2, "2026-08-30", 100, 30.0),
            ("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-06", 100, 44.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert (out[100]["eo_first"], out[100]["eo_last"]) == (40.0, 46.0)


def test_the_extrapolation_is_clamped_to_what_the_sampler_can_produce(logged):
    """EO is a percentage that captaincy doubles, so the ceiling is 200 and
    not 1.0 — the live log's own maximum today is 214.7, which is a *triple*
    captain's contribution and the reason the clamp is generous rather than
    tight. The floor is 0: a negative ownership is not a thing."""
    logged([("2026-27", 2, "2026-08-31", 100, 150.0),
            ("2026-27", 3, "2026-09-07", 100, 190.0),
            ("2026-27", 2, "2026-08-31", 200, 20.0),
            ("2026-27", 3, "2026-09-07", 200, 4.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[100]["deadline_eo"] == 200.0
    assert out[200]["deadline_eo"] == 0.0


def test_a_player_the_earlier_gameweek_never_sampled_has_no_trend(logged):
    """``eo_from_picks`` omits an element nobody started, so absence from the
    earlier table is "nobody had him", not "we did not look" — but a
    zero-based delta off a sparse table would read a promoted bench player as
    a 40-point riser. He gets no trend."""
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0),
            ("2026-27", 3, "2026-09-07", 200, 40.0)])
    out = field.field_eo_trend("2026-27", 3)
    assert out[200]["trend_available"] is False
    assert out[200]["deadline_eo"] == 40.0


def test_the_season_is_required_and_filters(logged):
    """Element ids are re-issued every August: the same integer is a different
    footballer on the other side of a rollover."""
    logged([("2025-26", 3, "2025-09-07", 100, 90.0),
            ("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    assert field.field_eo_trend("2026-27", 3)[100]["eo_first"] == 40.0
    assert field.field_eo_trend("2025-26", 3)[100]["trend_available"] is False
    with pytest.raises(TypeError):
        field.field_eo_trend(3)          # season is positional and required


def test_gw_none_reads_the_newest_gameweek_in_the_season(logged):
    logged([("2026-27", 2, "2026-08-31", 100, 40.0),
            ("2026-27", 3, "2026-09-07", 100, 46.0)])
    assert field.field_eo_trend("2026-27", None)[100]["deadline_eo"] == 52.0


def test_an_unreadable_log_is_an_empty_map_and_never_an_exception(
        monkeypatch):
    """``latest_field_eo``'s contract, kept: F4 is display and a missing
    display column is the documented degradation."""
    def boom():
        raise OSError("parquet is a directory today")

    monkeypatch.setattr(field, "load_field_eo", boom)
    assert field.field_eo_trend("2026-27", 3) == {}


def test_a_log_with_no_season_column_is_an_empty_map(monkeypatch):
    """A log banked before v8c's season column. Empty rather than scored:
    without the column there is no way to know which season's element 100 the
    rows describe, and the guard has no fallback by design."""
    frame = _log([("2026-27", 3, "2026-09-07", 100, 46.0)]).drop(
        columns=["season"])
    monkeypatch.setattr(field, "load_field_eo", lambda: frame)
    assert field.field_eo_trend("2026-27", 3) == {}
