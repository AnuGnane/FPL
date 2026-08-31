"""Team identity and the week's fixture, joined onto an advice payload.

Nothing here computes anything. Every field is a lookup into a file the
backend already banks — ``players.parquet`` for a player's team,
``teams.parquet`` for its short name, ``fixtures_all.parquet`` for the week's
game — and the tests are therefore almost entirely about what happens when one
of those files is missing, short a column, or says nothing about a player.

The rule the whole module is shaped around (plan A2): **this never raises**.
This Week rendered its advice without any of these fields yesterday, and a
decoration that can 500 the page it decorates is worse than no decoration.
"""

from __future__ import annotations

import pandas as pd
import pytest

from gaffer.data import store
from gaffer.web import identity

PLAYERS = pd.DataFrame({
    # 44 "Nomad" carries a team_code no row in TEAMS claims — the null-short-
    # name case. 55 is the away side of the one GW5 fixture.
    "code": [11, 22, 33, 44, 55],
    "name": ["Saka", "Haaland", "Rice", "Nomad", "Mainoo"],
    "position": ["MID", "FWD", "MID", "DEF", "MID"],
    "team_id": [1, 13, 1, 99, 14],
    "team_code": [3, 43, 3, 91, 1],
    "now_cost": [101, 150, 65, 45, 50],
})

TEAMS = pd.DataFrame({
    "team_id": [1, 13, 14],
    "code": [3, 43, 1],
    "name": ["Arsenal", "Man City", "Man Utd"],
    "short_name": ["ARS", "MCI", "MUN"],
})

# GW5: Arsenal host Man Utd; Man City are blank. One finished GW4 row, so the
# "unfinished only" filter has something to exclude.
FIXTURES = pd.DataFrame({
    "gw": [4, 5],
    "home_id": [1, 1],
    "away_id": [13, 14],
    "kickoff_time": ["2026-09-05T14:00:00Z", "2026-09-12T14:00:00Z"],
    "home_goals": [2.0, None],
    "away_goals": [1.0, None],
    "finished": [True, False],
})

PAYLOAD = {
    "gw": 5,
    "xi": [{"code": 11, "name": "Saka", "position": "MID", "ep": 5.1}],
    "bench": [{"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2}],
    "buys": [{"code": 33, "name": "Rice", "position": "MID", "ep": 4.0}],
    "sells": [],
    "captain": {"code": 11, "name": "Saka", "position": "MID", "ep": 5.1},
    "vice": {"code": 22, "name": "Haaland", "position": "FWD", "ep": 6.2},
}


def _ticker(*cells):
    """A ``Ticker`` shaped exactly as ``routers/meta.ticker`` returns one.

    Stubbing the *ticker* rather than ``identity._difficulty_by_team`` keeps
    the module's own indexing under test in every case: A4's whole claim is
    that the chip's number is the ticker's number, and a stub that replaced
    the join would stop asserting it.
    """
    from gaffer.web.schemas import Ticker, TickerCell, TickerTeam

    return Ticker(gws=[5], source="odds", teams=[
        TickerTeam(code=code, name=str(code), short_name=str(code),
                   mean_difficulty=diff,
                   cells=[TickerCell(gw=gw, opponent="?", home=True,
                                     difficulty=diff)])
        for code, gw, diff in cells])


@pytest.fixture()
def banked(tmp_path, monkeypatch):
    from gaffer.web.routers import meta

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    FIXTURES.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                        index=False)
    # Arsenal rated 0.31 in GW5, Man Utd 0.69. The ticker's own odds/Elo reads
    # want banked odds files this fixture deliberately does not write.
    monkeypatch.setattr(meta, "ticker",
                        lambda weeks=8: _ticker((3, 5, 0.31), (1, 5, 0.69)))
    return tmp_path


# --- team identity --------------------------------------------------

def test_a_player_gains_his_team_short_name_and_code(banked):
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["team_short"] == "ARS"
    assert out["xi"][0]["team_code"] == 3


def test_every_player_key_is_enriched_not_only_the_xi(banked):
    """A3: the bench, the moves and both armbands, so v9b needs no edit."""
    out = identity.with_identity(PAYLOAD, 5)
    assert out["bench"][0]["team_short"] == "MCI"
    assert out["buys"][0]["team_short"] == "ARS"
    assert out["captain"]["team_short"] == "ARS"
    assert out["vice"]["team_short"] == "MCI"


def test_a_player_the_snapshot_has_never_heard_of_gets_nulls(banked):
    out = identity.with_identity(
        {"gw": 5, "xi": [{"code": 777, "name": "Ghost", "ep": 0.0}]}, 5)
    assert out["xi"][0]["team_short"] is None
    assert out["xi"][0]["team_code"] is None
    assert out["xi"][0]["next_fixture"] is None


def test_a_team_code_with_no_row_in_teams_gets_a_null_short_name(banked):
    """A6: nulls, never a sentinel. A ``team_code`` of 0 would be a real
    request to the CDN for a shirt that does not exist."""
    out = identity.with_identity(
        {"gw": 5, "xi": [{"code": 44, "name": "Nomad", "ep": 1.0}]}, 5)
    assert out["xi"][0]["team_code"] == 91
    assert out["xi"][0]["team_short"] is None


def test_a_snapshot_without_a_team_code_column_is_nulls_not_a_raise(
        banked, tmp_path, capsys):
    """G2's rail, at the source."""
    PLAYERS.drop(columns=["team_code"]).to_parquet(
        tmp_path / "data/live/players.parquet", index=False)
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["team_code"] is None
    assert out["xi"][0]["team_short"] is None
    assert "identity" in capsys.readouterr().out


# --- the fixture ----------------------------------------------------

def test_the_fixture_names_the_opponent_the_side_and_the_kickoff(banked):
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx == {"opponent_short": "MUN", "home": True,
                  "kickoff_utc": "2026-09-12T14:00:00Z", "difficulty": 0.31}


def test_the_away_side_reads_as_away_with_the_other_opponent(banked):
    """One fixture, two rows: the home team's player sees (H) and the away
    team's sees (A), and neither borrows the other's opponent."""
    home = identity.with_identity(
        {"gw": 5, "xi": [{"code": 11, "name": "Saka", "ep": 5.1}]}, 5)
    away = identity.with_identity(
        {"gw": 5, "xi": [{"code": 55, "name": "Mainoo", "ep": 3.0}]}, 5)
    assert home["xi"][0]["next_fixture"]["home"] is True
    assert home["xi"][0]["next_fixture"]["opponent_short"] == "MUN"
    assert away["xi"][0]["next_fixture"]["home"] is False
    assert away["xi"][0]["next_fixture"]["opponent_short"] == "ARS"


def test_a_blank_gameweek_is_a_null_fixture_not_an_empty_one(banked):
    """D2: the chip says "blank" honestly rather than drawing a chip with
    nothing in it."""
    out = identity.with_identity(
        {"gw": 5, "bench": [{"code": 22, "name": "Haaland", "ep": 6.2}]}, 5)
    assert out["bench"][0]["next_fixture"] is None


def test_a_finished_fixture_in_the_same_gameweek_is_not_offered(banked,
                                                                tmp_path):
    played = FIXTURES.copy()
    played.loc[1, "finished"] = True
    played.to_parquet(tmp_path / "data/live/fixtures_all.parquet",
                      index=False)
    assert identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"] is None


def test_a_double_gameweek_keeps_only_the_first_fixture(banked, tmp_path):
    """D2, explicitly: the second fixture is a v9b question."""
    dgw = pd.concat([FIXTURES, pd.DataFrame({
        "gw": [5], "home_id": [14], "away_id": [1],
        "kickoff_time": ["2026-09-15T19:00:00Z"],
        "home_goals": [None], "away_goals": [None], "finished": [False]})],
        ignore_index=True)
    dgw.to_parquet(tmp_path / "data/live/fixtures_all.parquet", index=False)
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["kickoff_utc"] == "2026-09-12T14:00:00Z"
    assert fx["home"] is True


def test_a_fixture_with_no_kickoff_yet_still_renders_as_a_fixture(banked,
                                                                   tmp_path):
    """A5: "MCI (H) TBC" is true; an invented kickoff is not."""
    tbc = FIXTURES.copy()
    tbc.loc[1, "kickoff_time"] = None
    tbc.to_parquet(tmp_path / "data/live/fixtures_all.parquet", index=False)
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["opponent_short"] == "MUN"
    assert fx["kickoff_utc"] is None


def test_an_absent_fixture_file_nulls_every_fixture_and_keeps_identity(
        banked, tmp_path, capsys):
    (tmp_path / "data/live/fixtures_all.parquet").unlink()
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["next_fixture"] is None
    assert out["xi"][0]["team_short"] == "ARS"     # identity is independent
    assert "identity" in capsys.readouterr().out


def test_a_corrupt_fixture_file_is_a_printed_line_not_a_raise(banked,
                                                              tmp_path,
                                                              capsys):
    (tmp_path / "data/live/fixtures_all.parquet").write_bytes(b"not parquet")
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["next_fixture"] is None
    assert "identity" in capsys.readouterr().out


# --- the difficulty -------------------------------------------------

def test_the_difficulty_is_the_tickers_own_number(banked):
    """A4: not a second calculation drawn in the same colour scale.

    Arsenal are rated 0.31 by the stubbed ticker and 0.31 is what lands on
    Saka's chip — the join, keyed on ``(team_code, gw)``, is what is under
    test here.
    """
    assert identity.with_identity(PAYLOAD, 5)[
        "xi"][0]["next_fixture"]["difficulty"] == 0.31


def test_each_side_takes_its_own_rating_not_the_fixtures(banked):
    """The ticker rates a fixture once from the home side and gives the away
    side the complement; both numbers are already in its cells, so the join
    must not hand one team the other's."""
    away = identity.with_identity(
        {"gw": 5, "xi": [{"code": 55, "name": "Mainoo", "ep": 3.0}]}, 5)
    assert away["xi"][0]["next_fixture"]["difficulty"] == 0.69


def test_a_fixture_the_ticker_cannot_rate_keeps_everything_but_the_tint(
        banked, monkeypatch):
    """A4: a chip in a neutral colour is the whole feature minus its tint."""
    from gaffer.web.routers import meta

    monkeypatch.setattr(meta, "ticker", lambda weeks=8: _ticker())
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["difficulty"] is None
    assert fx["opponent_short"] == "MUN"


def test_a_ticker_that_raises_is_swallowed_into_no_difficulty(banked,
                                                              monkeypatch,
                                                              capsys):
    from gaffer.web.routers import meta

    monkeypatch.setattr(meta, "ticker", lambda weeks=8: (_ for _ in ()).throw(
        RuntimeError("no odds, no elo, no fixtures")))
    fx = identity.with_identity(PAYLOAD, 5)["xi"][0]["next_fixture"]
    assert fx["difficulty"] is None
    assert "difficulty" in capsys.readouterr().out


# --- the never-raises rule ------------------------------------------

@pytest.mark.parametrize("payload", [
    {}, {"gw": 5}, {"gw": 5, "xi": None}, {"gw": 5, "xi": "nonsense"},
    {"gw": 5, "xi": [None, 3, "x"]}, {"gw": 5, "captain": {"name": "no code"}},
])
def test_a_payload_whose_shape_has_drifted_comes_back_unharmed(banked,
                                                               payload):
    assert identity.with_identity(payload, 5) is not None


def test_a_cold_clone_with_no_snapshots_at_all_returns_the_payload(tmp_path,
                                                                   monkeypatch,
                                                                   capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(store, "DATA_DIR", tmp_path / "data")
    out = identity.with_identity(PAYLOAD, 5)
    assert out["xi"][0]["name"] == "Saka"
    assert out["xi"][0]["team_short"] is None


def test_the_pre_existing_fields_are_byte_identical(banked):
    """G2: the enrichment is additive and touches nothing that was there."""
    out = identity.with_identity(PAYLOAD, 5)
    before = PAYLOAD["xi"][0]
    after = out["xi"][0]
    assert all(after[k] == v for k, v in before.items())
    assert set(after) - set(before) == {"team_short", "team_code",
                                        "next_fixture"}


def test_the_input_payload_is_not_mutated(banked):
    """The caller hands us ``load_advice``'s dict; a route that mutated it
    would leak enrichment into anything that cached it."""
    identity.with_identity(PAYLOAD, 5)
    assert "team_short" not in PAYLOAD["xi"][0]
