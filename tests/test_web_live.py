import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.web.app import create_app

LIVE = {"elements": [
    {"id": 7, "stats": {"total_points": 9, "bps": 33, "minutes": 90,
                        "bonus": 0},
     "explain": [{"fixture": 11, "stats": [{"identifier": "bps",
                                            "value": 33}]}]},
    {"id": 8, "stats": {"total_points": 2, "bps": 12, "minutes": 45,
                        "bonus": 0},
     "explain": [{"fixture": 11, "stats": [{"identifier": "bps",
                                            "value": 12}]}]},
]}

FIXTURES = [{"id": 11, "event": 3, "team_h": 1, "team_a": 2,
             "started": True, "finished": False}]

# Salah's match (team 1) is over; Dud's (team 2) is still going.
SPLIT_FIXTURES = [{"id": 11, "event": 3, "team_h": 1, "team_a": 3,
                   "started": True, "finished": True},
                  {"id": 12, "event": 3, "team_h": 2, "team_a": 4,
                   "started": True, "finished": False}]

MY_PICKS = {"picks": [{"element": 7, "position": 1, "multiplier": 2},
                      {"element": 8, "position": 2, "multiplier": 1}],
            "entry_history": {"total_points": 126, "points": 20}}


class FakeClient:
    def __init__(self, active=True, fixtures=None):
        self.active = active
        self.fixtures = FIXTURES if fixtures is None else fixtures

    def get_event_status(self):
        if not self.active:
            return {"status": [{"event": 3, "points": "r",
                                "bonus_added": True}], "leagues": "Updated"}
        return {"status": [{"event": 3, "points": "p", "bonus_added": False}],
                "leagues": "Updating"}

    def get_event_live(self, gw):
        return LIVE

    def get_fixtures(self):
        return self.fixtures

    def get_entry_picks(self, entry_id, gw):
        return MY_PICKS

    def get_league_standings(self, league_id, page=1):
        return {"standings": {"has_next": False, "results": [
            {"entry": 1, "entry_name": "You FC", "player_name": "Me",
             "rank": 2, "last_rank": 2, "total": 106, "event_total": 20},
            {"entry": 2, "entry_name": "Ten Hag Hive", "player_name": "Riv",
             "rank": 1, "last_rank": 1, "total": 190, "event_total": 20}]}}


def _config(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    players = pd.DataFrame([
        {"code": 100, "element": 7, "name": "Salah", "position": "MID",
         "team_id": 1, "team_code": 300, "now_cost": 130, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 45.0,
         "form": 5.0, "points_per_game": 6.0, "ep_next": 6.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": 1.0, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None},
        {"code": 101, "element": 8, "name": "Dud", "position": "DEF",
         "team_id": 2, "team_code": 301, "now_cost": 45, "status": "a",
         "news": "", "chance_of_playing": None, "selected_by_percent": 5.0,
         "form": 1.0, "points_per_game": 2.0, "ep_next": 2.0,
         "price_change_percent": 0.0, "price_change_calibrating": False,
         "penalties_order": None, "direct_freekicks_order": None,
         "corners_and_indirect_freekicks_order": None}])
    (tmp_path / "data" / "live").mkdir(parents=True, exist_ok=True)
    players.to_parquet(tmp_path / "data/live/players.parquet", index=False)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.live.fpl_client",
                        lambda: FakeClient(active=True))
    return TestClient(create_app())


def test_live_reports_points_provisional_bonus_and_the_league_table(client):
    body = client.get("/api/live").json()
    assert body["active"] is True and body["gw"] == 3
    # Salah 9 + provisional 3 bonus, captained; Dud 2 + 2 bonus.
    assert body["my_points"] == 2 * (9 + 3) + (2 + 2)
    assert body["matches_in_play"] == 1
    salah = next(p for p in body["players"] if p["name"] == "Salah")
    assert salah["provisional_bonus"] == 3 and salah["status"] == "playing"
    assert [r["name"] for r in body["table"]][0] in ("You FC",
                                                     "Ten Hag Hive")


def test_player_status_follows_his_own_fixture_not_the_gameweek(tmp_path,
                                                                monkeypatch):
    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(
        "gaffer.web.routers.live.fpl_client",
        lambda: FakeClient(active=True, fixtures=SPLIT_FIXTURES))
    body = TestClient(create_app()).get("/api/live").json()
    status = {p["name"]: p["status"] for p in body["players"]}
    assert status["Salah"] == "played"       # his match has finished
    assert status["Dud"] == "playing"        # his has not


def test_live_between_gameweeks_is_a_quiet_inactive_payload(tmp_path,
                                                            monkeypatch):
    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr("gaffer.web.routers.live.fpl_client",
                        lambda: FakeClient(active=False))
    body = TestClient(create_app()).get("/api/live").json()
    assert body == {"active": False, "gw": None, "my_points": 0,
                    "matches_in_play": 0, "players": [], "table": [],
                    "notice": None}


# --- v4d: tier-resolved EO -------------------------------------------------

def test_live_players_carry_tier_eo_and_overall_ownership(tmp_path,
                                                          monkeypatch):
    """The tracker's player table gains the top-10k sample and the overall
    ownership already on the snapshot."""
    import gaffer.web.routers.live as live_mod

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {
                            7: {"eo": 143.5, "se": 2.1, "n": 300}})

    body = TestClient(create_app()).get("/api/live").json()
    salah = next(p for p in body["players"] if p["element"] == 7)
    assert salah["tier_eo"] == 143.5
    assert salah["tier_eo_se"] == 2.1
    assert salah["selected_by_percent"] == 45.0
    assert body["notice"] is None
    dud = next(p for p in body["players"] if p["element"] == 8)
    assert dud["tier_eo"] is None          # not in the sample: no number


def test_live_degrades_to_a_notice_when_tier_eo_fails(tmp_path, monkeypatch):
    """Rate limit, page shape change, anything: the tracker still renders."""
    import gaffer.web.routers.live as live_mod

    def _boom(client, gw, sample=300):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table", _boom)

    body = TestClient(create_app()).get("/api/live").json()
    assert body["active"] is True
    assert body["players"][0]["tier_eo"] is None
    assert "top-10k EO unavailable" in body["notice"]


def test_live_says_so_when_the_tier_sample_came_back_empty(tmp_path,
                                                           monkeypatch):
    """No exception, no data — every sampled entry private, or the gameweek
    has no picks yet. Rendering a blank column silently would read as 'the
    top 10k own nobody'."""
    import gaffer.web.routers.live as live_mod

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)
    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table",
                        lambda client, gw, sample=300: {})

    body = TestClient(create_app()).get("/api/live").json()
    assert body["active"] is True
    assert all(p["tier_eo"] is None for p in body["players"])
    assert body["notice"] == "top-10k EO empty this gameweek — league EO only"


def test_live_skips_tier_eo_entirely_when_it_is_switched_off(tmp_path,
                                                             monkeypatch):
    import gaffer.web.routers.live as live_mod

    monkeypatch.chdir(tmp_path)
    _config(tmp_path)                       # writes the players snapshot too
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n[league]\ntier_eo = false\n')

    def _boom(client, gw, sample=300):
        raise AssertionError("tier EO fetched with tier_eo = false")

    monkeypatch.setattr(live_mod, "fpl_client", lambda: FakeClient())
    monkeypatch.setattr(live_mod, "tier_eo_table", _boom)

    body = TestClient(create_app()).get("/api/live").json()
    assert body["notice"] is None
    assert body["players"][0]["tier_eo"] is None
