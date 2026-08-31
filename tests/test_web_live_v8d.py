"""``GET /api/live``, v8d: the projection, the race and the safety strip.

One real fifteen, and three fixture states chosen so every new number has a
hand-checkable answer. Team 1 has finished and everybody in it played; team 2
is still on the pitch; team 3 has finished and element 11 — a starter — never
came on, which is the one situation that triggers a projected substitution.

Every BPS is zero, so provisional bonus is zero everywhere and the arithmetic
under test is not entangled with v6's.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import gaffer.web.routers.live as live_mod
from gaffer.web.app import create_app

# XI: 1 GKP, 2-4 DEF, 5-8 MID, 9-11 FWD (9 is captain, 10 vice).
# Bench, in order: 12 GKP, 13 DEF, 14 MID, 15 FWD.
POSITION_OF = {1: "GKP", 2: "DEF", 3: "DEF", 4: "DEF",
               5: "MID", 6: "MID", 7: "MID", 8: "MID",
               9: "FWD", 10: "FWD", 11: "FWD",
               12: "GKP", 13: "DEF", 14: "MID", 15: "FWD"}
TEAM_OF = {**{e: 1 for e in range(1, 11)}, 11: 3, 12: 1,
           13: 2, 14: 2, 15: 2}
FIXTURE_OF = {1: 11, 2: 12, 3: 13}                  # team -> fixture id
MINUTES_OF = {**{e: 90 for e in range(1, 11)}, 11: 0, 12: 0, 13: 60,
              14: 0, 15: 0}
POINTS_OF = {**{e: 2 for e in range(1, 11)}, 9: 9, 11: 0, 12: 0, 13: 4,
             14: 0, 15: 0}
EP_OF = {**{e: 1.0 for e in range(1, 16)}, 9: 6.0, 13: 3.0}

LIVE = {"elements": [
    {"id": e,
     "stats": {"total_points": POINTS_OF[e], "bps": 0,
               "minutes": MINUTES_OF[e], "bonus": 0},
     "explain": [{"fixture": FIXTURE_OF[TEAM_OF[e]],
                  "stats": [{"identifier": "bps", "value": 0}]}]}
    for e in range(1, 16)]}

FIXTURES = [
    {"id": 11, "event": 3, "team_h": 1, "team_a": 21,
     "started": True, "finished": True},
    {"id": 12, "event": 3, "team_h": 2, "team_a": 22,
     "started": True, "finished": False},
    {"id": 13, "event": 3, "team_h": 3, "team_a": 23,
     "started": True, "finished": True},
]

MY_PICKS = {"picks": [
    {"element": e, "position": e,
     "multiplier": (2 if e == 9 else 0 if e > 11 else 1),
     "is_captain": e == 9, "is_vice_captain": e == 10}
    for e in range(1, 16)],
    "entry_history": {"total_points": 126, "points": 20}}

# The two figures every assertion below is measured against, computed by hand:
#   live      = nine starters on 2, the captain's 9 doubled, 11 on nothing
#             = 18 + 18 + 0 = 36
#   projected = the same, with 13 (four points, and on the pitch) replacing 11
#             = 40
MY_LIVE = 36
MY_PROJECTED = 40


class FakeClient:
    def __init__(self, standings=True, fixtures=None):
        self.standings = standings
        self.fixtures = FIXTURES if fixtures is None else fixtures

    def get_event_status(self):
        return {"status": [{"event": 3, "points": "p", "bonus_added": False}],
                "leagues": "Updating"}

    def get_event_live(self, gw):
        return LIVE

    def get_fixtures(self):
        return self.fixtures

    def get_entry_picks(self, entry_id, gw):
        return MY_PICKS          # the rival fields the same fifteen

    def get_league_standings(self, league_id, page=1):
        if not self.standings:
            raise RuntimeError("no league")
        return {"standings": {"has_next": False, "results": [
            {"entry": 1, "entry_name": "You FC", "player_name": "Me",
             "rank": 1, "last_rank": 1, "total": 106, "event_total": 20},
            {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
             "rank": 2, "last_rank": 2, "total": 100, "event_total": 20}]}}


PLAYERS = pd.DataFrame([
    {"code": 100 + e, "element": e, "name": f"P{e}",
     "position": POSITION_OF[e], "team_id": TEAM_OF[e],
     "team_code": 300 + TEAM_OF[e]}
    for e in range(1, 16)])
for _col, _default in (("now_cost", 50), ("status", "a"), ("news", ""),
                       ("chance_of_playing", None),
                       ("selected_by_percent", 5.0), ("form", 1.0),
                       ("points_per_game", 2.0), ("ep_next", 2.0),
                       ("price_change_percent", 0.0),
                       ("price_change_calibrating", False),
                       ("penalties_order", None),
                       ("direct_freekicks_order", None),
                       ("corners_and_indirect_freekicks_order", None)):
    PLAYERS[_col] = _default

COMPONENTS = pd.DataFrame(
    [{"element": e, "gw": 3, "ep": EP_OF[e]} for e in range(1, 16)]
    + [{"element": 9, "gw": 4, "ep": 9.9}])      # next week: never counted


def _setup(tmp_path, components=True, advice=True):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    (tmp_path / "reports").mkdir(exist_ok=True)
    if components:
        COMPONENTS.to_parquet(tmp_path / "reports/components_gw3.parquet",
                              index=False)
    if advice:
        (tmp_path / "reports/gw3-advice.json").write_text(
            json.dumps({"gw": 3, "expected_pts": 61.5}))


@pytest.fixture(autouse=True)
def _clean_series():
    """The race series is per process, so it outlives a test unless cleared."""
    live_mod.RACE_SERIES.clear()
    yield
    live_mod.RACE_SERIES.clear()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    return TestClient(create_app())


def _client_with(tmp_path, monkeypatch, fixtures):
    """The same page, with a hand-built fixture list for this gameweek."""
    monkeypatch.chdir(tmp_path)
    _setup(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client",
                        lambda: FakeClient(fixtures=fixtures))
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})
    return TestClient(create_app())


def test_the_pinned_live_score_is_unchanged_by_the_projection(client):
    """``entry_live_points`` still scores the XI exactly as picked."""
    assert client.get("/api/live").json()["my_points"] == MY_LIVE


def test_the_projected_score_brings_the_substitute_on(client):
    assert client.get("/api/live").json()["my_projected_points"] == MY_PROJECTED


def test_a_finished_blank_is_chipped_on_both_players(client):
    body = client.get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[11]["projected_out"] is True
    assert by_element[11]["sub_partner"] == 13
    assert by_element[13]["projected_in"] is True
    assert by_element[13]["sub_partner"] == 11
    assert by_element[13]["sub_reason"] == "played"
    assert by_element[12]["projected_in"] is False    # the keeper stays put


def test_each_player_carries_what_he_still_owes(client):
    body = client.get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[9]["remaining_ep"] == 0.0     # team 1 has finished
    assert by_element[11]["remaining_ep"] == 0.0    # team 3 has finished
    assert by_element[13]["remaining_ep"] == 1.0    # 3.0 x (1 - 60/90)
    # 14 is on the bench and is not projected to come on, so whatever he does
    # this afternoon he cannot do it for me.
    assert by_element[14]["remaining_ep"] == 0.0


def test_the_race_is_the_projection_plus_what_is_left(client):
    """Only 13 is both on the projected pitch and in an unfinished match, so
    the whole of the remaining EP is his one point."""
    body = client.get("/api/live").json()
    assert body["my_race"] == MY_PROJECTED + 1.0


def test_the_reference_line_is_this_gameweeks_saved_plan(client):
    assert client.get("/api/live").json()["race_reference"] == 61.5


def test_the_series_grows_one_point_per_poll_and_is_never_written_to_disk(
        client, tmp_path):
    first = client.get("/api/live").json()
    assert len(first["race_series"]) == 1
    assert first["race_series"][0]["you"] == first["my_race"]
    second = client.get("/api/live").json()
    assert len(second["race_series"]) == 2
    assert not list(tmp_path.glob("**/race*"))


def test_the_series_is_capped(client, monkeypatch):
    monkeypatch.setattr(live_mod, "RACE_SERIES_MAX", 3)
    for _ in range(5):
        body = client.get("/api/live").json()
    assert len(body["race_series"]) == 3


def test_a_new_gameweek_drops_the_previous_ones_trajectory(client):
    live_mod.RACE_SERIES[2] = [{"at": "old", "you": 1.0, "leader": None}]
    client.get("/api/live")
    assert list(live_mod.RACE_SERIES) == [3]


def test_the_safety_strip_prices_the_league_place(client):
    body = client.get("/api/live").json()
    strip = {s["role"]: s for s in body["safety"]}
    assert set(strip) == {"below"}          # I lead this two-entry league
    assert strip["below"]["name"] == "Ten Hag Hive"
    assert strip["below"]["margin"] == -6   # 100 + 40 against my 106 + 40
    assert strip["below"]["need"] == 0
    assert body["leader_name"] == "Ten Hag Hive"


def test_the_table_carries_the_race_beside_the_projection(client):
    body = client.get("/api/live").json()
    me = next(r for r in body["table"] if r["entry"] == 1)
    assert me["live"] == MY_LIVE
    assert me["projected_live"] == MY_PROJECTED
    assert me["race"] == me["projected_live"] + me["remaining_ep"]
    # The deliberate contract change: the season projection is built from the
    # auto-sub-aware gameweek, not from the raw live figure.
    assert me["projected"] == me["pre_total"] + MY_PROJECTED


# --- the blank gameweek: a team with no fixture at all -----------------
#
# Team 3 disappears from the fixture list, so element 11 — a starter — has no
# match to play in this gameweek at all.

BLANK_MID_GW = [FIXTURES[0], FIXTURES[1]]              # team 2 still playing
BLANK_GW_OVER = [FIXTURES[0], {**FIXTURES[1], "finished": True}]


def test_a_blank_gameweek_starter_is_left_alone_while_matches_remain(
        tmp_path, monkeypatch):
    """Mid-afternoon a team with no fixture is indistinguishable from one
    whose match is still to come, so nothing is claimed about him."""
    client = _client_with(tmp_path, monkeypatch, BLANK_MID_GW)
    by_element = {p["element"]: p
                  for p in client.get("/api/live").json()["players"]}
    assert by_element[11]["projected_out"] is False


def test_a_blank_gameweek_starter_is_subbed_out_once_the_gameweek_is_over(
        tmp_path, monkeypatch):
    """Every fixture finished and he never had one: FPL will substitute him."""
    body = _client_with(tmp_path, monkeypatch, BLANK_GW_OVER) \
        .get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[11]["projected_out"] is True
    assert by_element[11]["sub_partner"] == 13


# --- the double gameweek ----------------------------------------------
#
# Team 2 gets a second fixture that has not kicked off, so element 13 — who
# has played 60 minutes of the first — still owes the whole of the second.

DGW = FIXTURES + [{"id": 14, "event": 3, "team_h": 2, "team_a": 24,
                   "started": False, "finished": False}]


def test_a_double_gameweek_still_owes_the_fixture_not_yet_played(
        tmp_path, monkeypatch):
    """One of two fixtures unplayed plus a third of the other in play:
    (1 + 1/3) / 2 of 3.0 banked EP, at his projected multiplier of 1."""
    body = _client_with(tmp_path, monkeypatch, DGW).get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[13]["remaining_ep"] == 2.0


# --- what a player still owes is what *my* eleven would score -----------


def test_a_bench_player_who_is_not_coming_on_owes_me_nothing(client):
    """He may well play; he cannot score for me, so the column reads zero."""
    body = client.get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[14]["remaining_ep"] == 0.0


def test_the_captains_remaining_ep_is_doubled(tmp_path, monkeypatch):
    """Element 9 wears the armband; with his match still on, what he owes me
    is twice what he owes the game."""
    unfinished = [{**f, "finished": False} for f in FIXTURES]
    body = _client_with(tmp_path, monkeypatch, unfinished) \
        .get("/api/live").json()
    by_element = {p["element"]: p for p in body["players"]}
    assert by_element[9]["remaining_ep"] == 0.0     # 6.0 x 2 x (1 - 90/90)
    assert by_element[11]["remaining_ep"] == 1.0    # 1.0 x 1, yet to play
    unfinished_early = [{**f, "started": False, "finished": False}
                        for f in FIXTURES]
    early = {p["element"]: p for p in _client_with(
        tmp_path, monkeypatch, unfinished_early).get("/api/live").json()[
            "players"]}
    assert early[9]["remaining_ep"] == 12.0         # 6.0 x 2 x 1.0


def test_the_rival_is_projected_on_the_same_terms(client):
    """Spec §3 left rival remaining-EP to the planner; their picks are already
    fetched and the EP table is one read, so they get the full treatment."""
    body = client.get("/api/live").json()
    rival = next(r for r in body["table"] if r["entry"] == 2)
    assert rival["projected_live"] == MY_PROJECTED
    assert rival["remaining_ep"] == 1.0
    assert rival["race"] == MY_PROJECTED + 1.0
