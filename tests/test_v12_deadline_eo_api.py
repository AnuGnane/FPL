"""``deadline_eo`` beside ``field_eo``, on both seams that read the EO log.

The rule both inherit from ``field_eo`` (schemas.py:405-414): **None means
unknown and never 0.0**. A projected ownership of zero is a real and different
statement — nobody in the top 10k starts him — and a page that printed it for
"we have one gameweek of samples" would be making a claim the log cannot back.
"""

from __future__ import annotations

from gaffer.web import field_frame
from gaffer.web.routers import players as players_router

TREND = {
    100: {"eo_first": 40.0, "eo_last": 46.0, "delta": 6.0, "gws_between": 1,
          "deadline_eo": 52.0, "trend_available": True},
    200: {"eo_first": None, "eo_last": 12.0, "delta": None,
          "gws_between": None, "deadline_eo": 12.0,
          "trend_available": False},
}


def test_the_row_carries_the_projection_and_the_delta(monkeypatch):
    monkeypatch.setattr(players_router, "field_eo_trend", lambda s, g: TREND)
    row = players_router._trend_fields(TREND, 100)
    assert row == {"field_eo_deadline": 52.0, "field_eo_delta": 6.0}


def test_no_trend_is_null_on_both_fields_and_never_zero(monkeypatch):
    assert players_router._trend_fields(TREND, 200) == {
        "field_eo_deadline": None, "field_eo_delta": None}


def test_an_element_the_trend_never_saw_is_null_too():
    assert players_router._trend_fields(TREND, 999) == {
        "field_eo_deadline": None, "field_eo_delta": None}


def test_an_unreadable_trend_costs_the_columns_and_not_the_page(monkeypatch):
    def boom(season, gw):
        raise OSError("log is a directory today")

    monkeypatch.setattr(players_router, "field_eo_trend", boom)
    assert players_router._trend_table(3, "2026-27") == {}


def test_the_captain_frame_carries_the_projection(monkeypatch):
    monkeypatch.setattr(field_frame, "_field_table",
                        lambda gw: {100: {"eo": 46.0, "se": 2.0, "n": 300,
                                          "gw": 3}})
    monkeypatch.setattr(field_frame, "_trend_table", lambda gw: TREND)
    monkeypatch.setattr(field_frame, "_elements_by_code", lambda: {55: 100})
    monkeypatch.setattr(field_frame, "_modal_captain", lambda gw: None)
    out = field_frame.with_field_frame(
        {"captain": {"code": 55, "name": "Salah"}}, 3)
    assert out["captain_field"]["deadline_eo"] == 52.0
    assert out["captain_field"]["eo_delta"] == 6.0


def test_the_captain_frame_is_absent_when_there_is_nothing_to_say(
        monkeypatch):
    """Task 2 of v10b's rule, kept: the key is absent, not null."""
    monkeypatch.setattr(field_frame, "_field_table", lambda gw: {})
    monkeypatch.setattr(field_frame, "_trend_table", lambda gw: {})
    monkeypatch.setattr(field_frame, "_elements_by_code", lambda: {55: 100})
    monkeypatch.setattr(field_frame, "_modal_captain", lambda gw: None)
    payload = {"captain": {"code": 55, "name": "Salah"}}
    assert field_frame.with_field_frame(payload, 3) == payload
