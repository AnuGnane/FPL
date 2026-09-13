"""v18d §2 — the fixture rating, out of the web layer and into the core.

Two claims. The arithmetic still says what it said when it lived inside
``routers/meta.ticker``: one rating per fixture, taken from the home side,
with the away side on the complement. And the route now serves exactly those
numbers, because it is a shape adapter over this function and nothing else —
which is what keeps the golden board byte-identical.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer import difficulty
from gaffer.data import store
from gaffer.data.elo import expected_score

TEAMS = pd.DataFrame({
    "team_id": [1, 2],
    "code": [3, 43],
    "name": ["Arsenal", "Man City"],
    "short_name": ["ARS", "MCI"],
})

# One unfinished GW5 fixture, Arsenal at home. No ``live/fixtures.parquet``,
# so there is nothing to run Elo over and both sides default to 1500.
FIXTURES = pd.DataFrame({
    "gw": [5],
    "home_id": [1],
    "away_id": [2],
    "finished": [False],
})


@pytest.fixture()
def tiny(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    return tmp_path


def test_two_level_teams_are_rated_off_elo_and_the_halves_complement(tiny):
    rated = difficulty.rate_fixtures(weeks=8)

    assert rated.gws == [5]
    assert rated.source == "elo"          # no odds directory on disk
    by_code = {team.code: team for team in rated.teams}
    home = by_code[3].cells[0]
    away = by_code[43].cells[0]
    want = round(1.0 - expected_score(1500.0, 1500.0, home=True), 3)
    assert home.home is True and home.opponent == "MCI"
    assert home.difficulty == want
    assert away.home is False and away.opponent == "ARS"
    assert away.difficulty == round(1.0 - want, 3)
    assert by_code[3].mean_difficulty == want


def test_the_route_serves_the_cores_numbers_unchanged(tiny):
    """The adapter converts field for field; it must not round or reorder."""
    from gaffer.web.app import create_app

    rated = difficulty.rate_fixtures(weeks=8)
    body = TestClient(create_app()).get("/api/fixtures/ticker").json()

    assert body["gws"] == rated.gws and body["source"] == rated.source
    assert [t["code"] for t in body["teams"]] == [t.code for t in rated.teams]
    assert [[c["difficulty"] for c in t["cells"]] for t in body["teams"]] == \
        [[c.difficulty for c in t.cells] for t in rated.teams]
    assert [t["mean_difficulty"] for t in body["teams"]] == \
        [t.mean_difficulty for t in rated.teams]
    assert [[c["opponent"], c["home"], c["gw"]]
            for t in body["teams"] for c in t["cells"]] == \
        [[c.opponent, c.home, c.gw]
         for t in rated.teams for c in t.cells]
