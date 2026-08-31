"""``/api/watchlist``: three verbs over a store that must never 500.

The write path is the ``/api/overrides`` write path with its numeric
validation removed, so the tests that remain are the ones about the parts that
did not go away: the unknown code, the cap, the note length, and a delete of
something that was never there.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

PLAYERS = pd.DataFrame({
    "code": [11, 22, 33],
    "name": ["Saka", "Haaland", "Rice"],
    "position": ["MID", "FWD", "MID"],
    "team_code": [3, 4, 3],
    "now_cost": [101, 150, 65],
})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    return TestClient(create_app())


def test_an_empty_watchlist_is_a_200_with_no_rows(client):
    assert client.get("/api/watchlist").json() == {"rows": []}


def test_starring_answers_the_whole_panel_name_resolved(client):
    body = client.post("/api/watchlist",
                       json={"code": 11, "note": "presser"}).json()
    assert body["rows"] == [{"code": 11, "name": "Saka", "note": "presser",
                             "set_at": body["rows"][0]["set_at"]}]


def test_the_rows_come_back_sorted_by_code(client):
    for code in (33, 11, 22):
        client.post("/api/watchlist", json={"code": code})
    assert [r["code"] for r in client.get("/api/watchlist").json()["rows"]] \
        == [11, 22, 33]


def test_an_unknown_player_is_a_structured_422(client):
    response = client.post("/api/watchlist", json={"code": 999})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "unknown_player"
    assert response.json()["detail"]["players"] == [999]


def test_a_clone_with_no_player_snapshot_says_what_to_run(client, tmp_path):
    (tmp_path / "data/live/players.parquet").unlink()
    response = client.post("/api/watchlist", json={"code": 11})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "no_player_list"
    assert "gaffer advise" in response.json()["detail"]["error"]


def test_reading_still_works_with_no_player_snapshot(client, tmp_path):
    """A read is never worth a 500: a panel with a code where a name should
    be is worth more than an error page."""
    client.post("/api/watchlist", json={"code": 11})
    (tmp_path / "data/live/players.parquet").unlink()
    body = client.get("/api/watchlist").json()
    assert body["rows"][0]["name"] == "11"


def test_a_long_note_is_a_422_naming_the_limit(client):
    response = client.post("/api/watchlist",
                           json={"code": 11, "note": "x" * 500})
    assert response.status_code == 422
    assert response.json()["detail"]["constraint"] == "watch_value"


def test_unstarring_answers_the_remaining_panel(client):
    client.post("/api/watchlist", json={"code": 11})
    client.post("/api/watchlist", json={"code": 22})
    assert [r["code"] for r in
            client.delete("/api/watchlist/11").json()["rows"]] == [22]


def test_unstarring_something_that_was_never_starred_is_a_404(client):
    assert client.delete("/api/watchlist/11").status_code == 404


def test_a_corrupt_store_reads_as_an_empty_panel(client, tmp_path):
    (tmp_path / "reports/watchlist.json").write_text("{not json")
    assert client.get("/api/watchlist").json() == {"rows": []}
