"""v12 W5 §6.4 — the ledger row names the projections it was graded against."""
from __future__ import annotations

import pandas as pd
import pytest

from gaffer import review
from gaffer.artifacts import POOL_COLS, save_projection_snapshot

SEASON = "2026-27"
DEADLINE = "2026-09-04T17:30:00+00:00"


def _pool():
    return pd.DataFrame([{"code": 100, "name": "P", "position": "MID",
                          "team_code": 1, "cost": 80, "sell": 80,
                          "owned": True, "gw": 5, "ep_raw": 5.0}],
                        columns=POOL_COLS)


@pytest.fixture()
def graded(tmp_path, monkeypatch):
    """A gameweek that grades, with the snapshot writing left to the test."""
    monkeypatch.chdir(tmp_path)
    mine = {"xi": [100] * 11, "bench": [100] * 4, "captain": 100, "vice": 100,
            "hits": 0, "chip": None, "official_gross": 60, "official_cost": 0,
            "notices": []}
    monkeypatch.setattr(review, "my_decisions", lambda gw, **kw: dict(mine))
    monkeypatch.setattr(review, "actuals_for_gw",
                        lambda gw: pd.DataFrame(
                            [{"code": 100, "total_points": 6, "minutes": 90,
                              "position": "MID"}]))
    monkeypatch.setattr(review, "code_of_element", lambda: {1: 100})
    monkeypatch.setattr(review, "names_by_code", lambda: {100: "P"})
    monkeypatch.setattr(
        review, "model_decisions",
        lambda gw: {"xi": [100] * 11, "bench": [100] * 4, "captain": 100,
                    "vice": 100, "buys": [], "sells": [], "hits": 0,
                    "chip": None, "names": {100: "P"},
                    "positions": {100: "MID"}, "post_deadline": False,
                    "deadline": DEADLINE})
    return type("Cfg", (), {"current_season": SEASON, "entry_id": 1,
                            "sim_n": 10})()


def test_a_row_names_the_snapshot_it_was_graded_against(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260903T090000Z"
    assert row["projection_post_deadline"] is False


def test_the_snapshot_chosen_is_the_last_one_before_the_deadline(graded):
    for at in ("2026-09-01T09:00:00+00:00", "2026-09-04T09:00:00+00:00",
               "2026-09-05T09:00:00+00:00"):
        save_projection_snapshot(_pool(), 5, at, SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260904T090000Z"


def test_a_gameweek_whose_every_run_was_late_is_flagged(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-05T09:00:00+00:00", SEASON)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] == "20260905T090000Z"
    assert row["projection_post_deadline"] is True


def test_no_snapshot_is_None_and_the_row_still_grades(graded):
    """Every row already in the ledger is in this state and always will be:
    grades are banked and never re-derived (review.py:24-26)."""
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_snapshot"] is None
    assert row["projection_post_deadline"] is False
    assert row["my_points"] is not None


def test_a_row_with_no_surviving_advice_still_names_a_snapshot(graded,
                                                              monkeypatch):
    """The snapshot is on disk under (season, gw) and does not depend on the
    advice payload surviving the 20-run prune."""
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    monkeypatch.setattr(review, "model_decisions", lambda gw: None)
    row = review.grade_gw(5, cfg=graded)
    assert row["no_advice"] is True
    assert row["projection_snapshot"] == "20260903T090000Z"


def test_a_missing_deadline_takes_the_newest_and_flags_it(graded, monkeypatch):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    monkeypatch.setattr(review, "model_decisions", lambda gw: None)
    row = review.grade_gw(5, cfg=graded)
    assert row["projection_post_deadline"] is True


def test_a_payload_that_predates_the_deadline_field_reads_as_None(monkeypatch):
    """model_decisions carries whatever the run banked and does not invent
    one. An artifact written before ``deadline`` was saved into the payload
    has no deadline, and ``None`` is what sends grade_gw down its late
    branch rather than a guess that reads as a measurement."""
    monkeypatch.setattr(
        review, "latest_run_per_gw",
        lambda: {5: {"gw": 5, "post_deadline": False, "xi": [], "bench": [],
                     "buys": [], "sells": [], "hits": 0}})
    model = review.model_decisions(5)
    assert "deadline" in model
    assert model["deadline"] is None


def test_an_advice_payload_with_no_deadline_flags_the_snapshot(graded,
                                                               monkeypatch):
    """The real shape of the second cause: the advice survived the prune but
    predates the field, so an in-time snapshot exists on disk with nothing to
    compare its stamp against. Flagged, not silently trusted."""
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", SEASON)
    monkeypatch.setattr(
        review, "model_decisions",
        lambda gw: {"xi": [100] * 11, "bench": [100] * 4, "captain": 100,
                    "vice": 100, "buys": [], "sells": [], "hits": 0,
                    "chip": None, "names": {100: "P"},
                    "positions": {100: "MID"}, "post_deadline": False,
                    "deadline": None})
    row = review.grade_gw(5, cfg=graded)
    assert row["no_advice"] is False
    assert row["projection_snapshot"] == "20260903T090000Z"
    assert row["projection_post_deadline"] is True


def test_another_seasons_snapshot_is_not_read(graded):
    save_projection_snapshot(_pool(), 5, "2026-09-03T09:00:00+00:00", "2025-26")
    assert review.grade_gw(5, cfg=graded)["projection_snapshot"] is None


def test_the_schema_defaults_both_fields_for_an_old_ledger():
    from gaffer.web.schemas import ReviewGw

    row = ReviewGw(gw=1)
    assert row.projection_snapshot is None
    assert row.projection_post_deadline is False
