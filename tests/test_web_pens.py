"""GET /api/pens: the browser renders the tracker the CLI writes.

Disk-only, exactly like /api/quality: `gaffer track-pens` reads two parquets
and joins Understat, which is not something a page load may start.
"""

import json

import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

REPORT = {
    "season": "2026-27",
    "gws": [
        {"gw": 1, "instrument": "xg_gap", "rows": 520, "covered_rows": 498,
         "team_games": 10, "component_rows": 520,
         "predicted_ep_pen_taker": 3.2, "predicted_takers": 12,
         "pens_taken": 2.0, "pens_by_first_choice": 2.0,
         "taker_hit_rate": 1.0, "pens_per_team_game": 0.2,
         "realized_pen_points": 6.4},
        {"gw": 2, "instrument": "pens_missed_only", "rows": 515,
         "covered_rows": 0, "team_games": 10, "component_rows": 515,
         "predicted_ep_pen_taker": 2.9, "predicted_takers": 12,
         "pens_taken": 1.0, "pens_by_first_choice": 0.0,
         "taker_hit_rate": 0.0, "pens_per_team_game": 0.1,
         "realized_pen_points": 3.2},
        {"gw": 3, "error": "the week would not read"},
    ],
    "season_totals": {
        "gws": 2, "instruments": ["pens_missed_only", "xg_gap"],
        "team_games": 20, "predicted_ep_pen_taker": 6.1, "pens_taken": 3.0,
        "pens_by_first_choice": 2.0, "taker_hit_rate": 0.667,
        "pens_per_team_game": 0.15, "league_pens_pg_served": 0.13,
        "realized_pen_points": 9.6},
    "notes": ["penalties counted from pens_missed only"],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # artifacts.REPORTS is the relative Path("reports"), so chdir is the whole
    # of the redirection — the same fixture tests/test_web_quality.py uses.
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def test_pens_without_a_report_tells_you_to_run_track_pens(client):
    response = client.get("/api/pens")
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "no pen tracker report — run `gaffer track-pens` first"
    )


@pytest.mark.parametrize(
    "body",
    [
        "{not json at all",  # half-written by an interrupted run
        json.dumps({"gws": "not a list"}),  # right file, wrong shape
    ],
)
def test_an_unreadable_report_is_a_422_not_a_500(client, tmp_path, body):
    """A truncated or stale-shaped artifact is an operator problem with a
    known fix, not a server fault: say what to re-run rather than 500."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(body)
    response = client.get("/api/pens")
    assert response.status_code == 422
    assert response.json()["detail"] == (
        "pen tracker report is unreadable — re-run `gaffer track-pens`"
    )


def test_pens_serves_the_season_and_every_gameweek(client, tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(REPORT))
    body = client.get("/api/pens").json()
    assert body["season"] == "2026-27"
    assert [g["gw"] for g in body["gws"]] == [1, 2, 3]
    assert body["gws"][1]["instrument"] == "pens_missed_only"
    assert body["season_totals"]["taker_hit_rate"] == 0.667
    assert body["season_totals"]["league_pens_pg_served"] == 0.13
    assert body["notes"] == ["penalties counted from pens_missed only"]


def test_an_unreadable_gameweek_is_served_as_its_error(client, tmp_path):
    """safe_gw_block writes {"gw": N, "error": ...} for one bad week; the
    endpoint must carry it rather than 500 on the missing fields."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(REPORT))
    broken = client.get("/api/pens").json()["gws"][2]
    assert broken["error"] == "the week would not read"
    assert broken["instrument"] is None
    assert broken["pens_taken"] is None


def test_a_degraded_report_with_no_gameweeks_still_serves(client, tmp_path):
    """track_pens never raises: a season with nothing on disk is an empty
    report carrying a note, and that is a 200, not an error."""
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "pen_tracker.json").write_text(json.dumps(
        {"season": "", "gws": [], "season_totals": {},
         "notes": ["no live season on disk — run `gaffer refresh` first"]}))
    body = client.get("/api/pens").json()
    assert body["gws"] == []
    assert body["season_totals"]["pens_taken"] is None
    assert "gaffer refresh" in body["notes"][0]
