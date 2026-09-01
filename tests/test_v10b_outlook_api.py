"""``GET /api/fixtures/outlook`` — the doubles and blanks ahead.

Every failure here is a **200 with a note**, never a 422 and never the empty
payload the matrix returns. The Outlook card renders beside populated cards on
the Chips tab, and a 422 there is indistinguishable from a broken endpoint —
v9d's ``/api/model/calibration`` reasoning, applied to the same UI problem.

The interesting case is the ordinary one. Today's published list has ten
fixtures in every one of thirty-eight gameweeks and twenty teams appearing
once each, so ``has_doubles`` and ``has_blanks`` are both false and will stay
false until the cup rounds. That is what the panel shows for the next four
months, so it is what this file tests hardest.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from pathlib import Path

from gaffer.data import store
from gaffer.web.app import create_app

REPO_ROOT = Path(__file__).resolve().parents[1]
"""Captured at import, before any fixture has changed the process CWD."""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def _teams() -> pd.DataFrame:
    return pd.DataFrame([
        {"team_id": 1, "code": 14, "name": "Liverpool", "short_name": "LIV"},
        {"team_id": 2, "code": 43, "name": "Man City", "short_name": "MCI"},
        {"team_id": 3, "code": 3, "name": "Arsenal", "short_name": "ARS"},
        {"team_id": 4, "code": 8, "name": "Chelsea", "short_name": "CHE"},
    ])


def _fixtures() -> pd.DataFrame:
    """GW2 doubles team 1 and blanks team 4; GW1 is finished and ordinary."""
    return pd.DataFrame([
        {"gw": 1, "home_id": 1, "away_id": 2, "finished": True},
        {"gw": 1, "home_id": 3, "away_id": 4, "finished": True},
        {"gw": 2, "home_id": 1, "away_id": 3, "finished": False},
        {"gw": 2, "home_id": 2, "away_id": 1, "finished": False},
    ])


def _bank(fixtures=None, teams=None):
    if fixtures is not None:
        store.save(fixtures, "live/fixtures_all.parquet")
    if teams is not None:
        store.save(teams, "live/teams.parquet")


def test_no_fixture_file_is_a_200_with_nothing_and_a_reason(client):
    """Not a 422, and not the matrix's silent EMPTY: the card has to be able
    to say *why* it is empty, and "no fixture list yet" and "no doubles this
    season" are two very different sentences."""
    body = client.get("/api/fixtures/outlook").json()
    assert client.get("/api/fixtures/outlook").status_code == 200
    assert body["weeks"] == []
    assert body["note"]


def test_no_teams_file_degrades_to_codes_are_ids(client):
    """The counts are true either way; only the short names are missing.
    Losing the whole answer over a cosmetic join is the wrong trade, and the
    payload says which happened."""
    _bank(fixtures=_fixtures())
    body = client.get("/api/fixtures/outlook").json()
    assert body["teams_known"] is False
    assert body["has_doubles"] is True
    week = next(w for w in body["weeks"] if w["gw"] == 2)
    assert [t["code"] for t in week["doubles"]] == [1]
    assert week["doubles"][0]["short_name"] is None
    assert body["note"]


def test_a_populated_file_round_trips_with_codes_and_short_names(client):
    _bank(fixtures=_fixtures(), teams=_teams())
    body = client.get("/api/fixtures/outlook").json()
    assert body["teams_known"] is True
    week = next(w for w in body["weeks"] if w["gw"] == 2)
    assert week["doubles"] == [{"code": 14, "short_name": "LIV"}]
    assert week["blanks"] == [{"code": 8, "short_name": "CHE"}]
    assert body["has_doubles"] is True and body["has_blanks"] is True


def test_the_flags_are_declared_rather_than_left_to_the_client(client):
    """v9d's ``available``, again. The empty state is the common case for
    months, and a client branching on ``weeks.every(w => !w.doubles.length)``
    is a client that will one day branch on ``weeks.length`` by mistake."""
    _bank(fixtures=pd.DataFrame([
        {"gw": 2, "home_id": 1, "away_id": 2, "finished": False},
        {"gw": 2, "home_id": 3, "away_id": 4, "finished": False},
    ]), teams=_teams())
    body = client.get("/api/fixtures/outlook").json()
    assert body["has_doubles"] is False and body["has_blanks"] is False
    assert body["weeks"]


def test_from_defaults_to_the_first_unfinished_gameweek(client):
    """The planner's question is about the season *ahead*: GW1 is played and
    a chip cannot be spent on it."""
    _bank(fixtures=_fixtures(), teams=_teams())
    body = client.get("/api/fixtures/outlook").json()
    assert body["from_gw"] == 2
    assert {w["gw"] for w in body["weeks"]} == {2}


def test_from_slices_explicitly(client):
    _bank(fixtures=_fixtures(), teams=_teams())
    body = client.get("/api/fixtures/outlook?from=1").json()
    assert {w["gw"] for w in body["weeks"]} == {1, 2}
    assert body["from_gw"] == 1


def test_todays_real_shape_answers_honestly(client, monkeypatch, tmp_path):
    """38 weeks, every one with empty doubles and blanks. Skipped on a clone
    with no data directory."""
    monkeypatch.chdir(REPO_ROOT)
    if not store.exists("live/fixtures_all.parquet"):
        pytest.skip("no fixture list on this clone")
    body = TestClient(create_app()).get("/api/fixtures/outlook?from=1").json()
    assert len(body["weeks"]) == 38
    assert body["has_doubles"] is False and body["has_blanks"] is False


def test_a_from_beyond_the_season_says_so_rather_than_going_quiet(client):
    """An empty ``weeks`` has two causes and the client can only render one
    sentence for it. "Nothing unusual is scheduled" is a claim about the
    season; asking for GW60 of a 38-week season is a claim about the request,
    and falling through to the first is how a typo reads as a fact."""
    _bank(fixtures=_fixtures(), teams=_teams())
    body = client.get("/api/fixtures/outlook?from=20").json()
    assert body["weeks"] == []
    assert "beyond" in body["note"]
    assert body["has_doubles"] is False and body["has_blanks"] is False


def test_a_null_finished_flag_does_not_read_as_played():
    """``bool(nan)`` is ``True``, so ``~frame["finished"].astype(bool)``
    dropped the row: an unset flag read as a *finished* match and the season
    ahead began after it. A fixture whose result is not recorded has not been
    played — asserted on the frame directly, because a parquet round trip
    normalises the null and would hide the arithmetic under test."""
    from gaffer.web.routers.fixtures import _first_unfinished

    frame = pd.DataFrame({"gw": [1, 2], "home_id": [1, 3], "away_id": [2, 4],
                          "finished": [float("nan"), 0.0]})
    assert _first_unfinished(frame) == 1


def test_the_matrix_and_the_ticker_are_unaffected(client):
    _bank(fixtures=_fixtures(), teams=_teams())
    assert client.get("/api/fixtures/matrix").status_code == 200
    assert client.get("/api/fixtures/matrix").json() == {
        "gws": [], "teams": [], "source": "none"}


def test_the_openapi_paths_gained_exactly_the_outlook(client):
    paths = set(create_app().openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/fixtures")} == {
        "/api/fixtures/matrix", "/api/fixtures/ticker",
        "/api/fixtures/outlook"}
