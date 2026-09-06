"""v15 §5.1 — every league the entry is in, private and public."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.config import LOCAL_OVERLAY, serving_config
from gaffer.web.app import create_app
from gaffer.web.routers import league as mod

ME = 1


def _league(id_, name, type_, rank_count, rank, last_rank):
    return {"id": id_, "name": name, "league_type": type_,
            "rank_count": rank_count, "entry_rank": rank,
            "entry_last_rank": last_rank, "scoring": "c"}


ENTRY = {
    "summary_overall_points": 300, "current_event": 5,
    "leagues": {"classic": [
        _league(314, "Overall", "s", 10_409_391, 430_473, 2_562_053),
        _league(261, "England", "s", 2_923_703, 128_302, 762_621),
        _league(5, "Focus FC League", "x", 3, 1, 2),
        _league(9, "NLT", "x", 60, 55, 58),
        _league(99, "Next Season", "x", None, 3, 0),
        _league(77, "Duo", "x", 1, 1, 1),
    ], "h2h": []},
}

# League 5: I lead on 300 over 290. League 9: sixty entries, I am 55th and
# NOT on page 1, so my total comes from the entry payload. League 77: only me.
STANDINGS = {
    5: {"standings": {"has_next": False, "results": [
        {"entry": ME, "entry_name": "Mine", "player_name": "Me", "rank": 1,
         "last_rank": 2, "total": 300, "event_total": 60},
        {"entry": 2, "entry_name": "Second", "player_name": "S", "rank": 2,
         "last_rank": 1, "total": 290, "event_total": 50},
        {"entry": 3, "entry_name": "Third", "player_name": "T", "rank": 3,
         "last_rank": 3, "total": 100, "event_total": 10}]}},
    9: {"standings": {"has_next": True, "results": [
        {"entry": 20, "entry_name": "Leader", "player_name": "L", "rank": 1,
         "last_rank": 1, "total": 412, "event_total": 70}]}},
    77: {"standings": {"has_next": False, "results": [
        {"entry": ME, "entry_name": "Mine", "player_name": "Me", "rank": 1,
         "last_rank": 1, "total": 300, "event_total": 60}]}},
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_entry(self, entry_id):
        self.calls.append(("entry", entry_id))
        return ENTRY

    def get_league_standings(self, league_id, page=1):
        self.calls.append(("standings", league_id, page))
        return STANDINGS[league_id]


def _artifacts(tmp_path, league_id=5, lam=0.4):
    (tmp_path / "config.toml").write_text(
        f"[fpl]\nentry_id = {ME}\nleague_id = {league_id}\n")
    players = pd.DataFrame([{"code": 100, "element": 7, "name": "Salah",
                             "position": "MID", "team_id": 1,
                             "team_code": 300, "now_cost": 130}])
    save_solve_state(SolveState(
        gw=6, gws=[6], deadline="2026-09-19T17:30:00Z",
        generated_at="2026-09-18T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=[100], lam=lam, league_eo={},
        avail_by_gw={6: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                           "cost": 130, "sell": 128}]),
            players, [100], {(100, 6): 6.4}, [6])))


@pytest.fixture()
def fake():
    return FakeClient()


@pytest.fixture()
def client(tmp_path, monkeypatch, fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    yield TestClient(create_app())
    serving_config.cache_clear()


def test_private_and_public_are_split_by_the_league_type_flag(client):
    body = client.get("/api/league/leagues").json()
    assert [r["name"] for r in body["public"]] == ["Overall", "England"]
    assert {r["name"] for r in body["private"]} == {
        "Focus FC League", "NLT", "Next Season", "Duo"}
    assert body["gw"] == 5


def test_private_rows_are_ordered_by_rank_then_size(client):
    body = client.get("/api/league/leagues").json()
    assert [r["name"] for r in body["private"]] == [
        "Focus FC League", "Duo", "Next Season", "NLT"]


def test_the_focus_row_is_marked_and_named(client):
    body = client.get("/api/league/leagues").json()
    assert body["focus_league_id"] == 5
    assert body["focus_name"] == "Focus FC League"
    assert body["focus_warning"] is None
    focus = [r for r in body["private"] if r["is_focus"]]
    assert [r["league_id"] for r in focus] == [5]


def test_a_leader_is_ahead_of_second_and_would_defend(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 5)
    assert (row["rank"], row["last_rank"], row["entries"]) == (1, 2, 3)
    assert row["started"] is True
    assert (row["gap"], row["gap_kind"], row["would"]) == (10, "ahead", "defend")


def test_off_page_one_the_gap_uses_the_entry_payloads_total(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 9)
    assert (row["gap"], row["gap_kind"], row["would"]) == (112, "behind", "chase")


def test_a_league_of_one_has_no_gap(client):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 77)
    assert row["started"] and row["gap"] is None and row["would"] is None


def test_a_league_not_started_has_no_gap_and_says_so(client, fake):
    row = next(r for r in client.get("/api/league/leagues").json()["private"]
               if r["league_id"] == 99)
    assert row["started"] is False
    assert row["entries"] is None and row["gap"] is None
    assert ("standings", 99, 1) not in fake.calls


def test_public_rows_carry_rank_last_rank_and_size_only(client):
    row = client.get("/api/league/leagues").json()["public"][0]
    assert row == {"league_id": 314, "name": "Overall", "rank": 430_473,
                   "last_rank": 2_562_053, "entries": 10_409_391}


def test_the_stance_and_the_focus_tilt_come_from_config_and_solve_state(
        client):
    body = client.get("/api/league/leagues").json()
    assert body["stance"] == "auto"
    assert body["focus_stance"] == "chase" and body["focus_lam"] == 0.4


def test_a_manual_stance_shows_at_the_cap_before_any_advise(
        client, tmp_path):
    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nstance = "defend"\n')
    serving_config.cache_clear()
    body = client.get("/api/league/leagues").json()
    assert body["stance"] == "defend"
    assert body["focus_stance"] == "defend" and body["focus_lam"] == -0.5


def test_a_focus_that_is_not_private_is_a_warning_not_a_refusal(
        tmp_path, monkeypatch, fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path, league_id=42)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    body = TestClient(create_app()).get("/api/league/leagues").json()
    assert body["focus_name"] is None
    assert "42" in body["focus_warning"]
    assert not any(r["is_focus"] for r in body["private"])


def test_no_league_id_at_all_still_lists_the_leagues(tmp_path, monkeypatch,
                                                    fake):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path, league_id=0)
    monkeypatch.setattr(mod, "fpl_client", lambda: fake)
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    resp = TestClient(create_app()).get("/api/league/leagues")
    assert resp.status_code == 200
    assert resp.json()["focus_warning"] is not None
    assert len(resp.json()["private"]) == 4


def test_the_rows_are_cached_for_five_minutes_per_entry(client, fake):
    client.get("/api/league/leagues")
    first = len(fake.calls)
    assert first == 3                # the entry, then leagues 5 and 9; 77 is
                                     # a league of one and 99 has not started
    client.get("/api/league/leagues")
    assert len(fake.calls) == first
    mod._OVERVIEW.clear()
    client.get("/api/league/leagues")
    assert len(fake.calls) == 2 * first


def test_the_cache_does_not_hold_the_focus_or_the_stance(client, tmp_path):
    client.get("/api/league/leagues")
    (tmp_path / LOCAL_OVERLAY).write_text('[league]\nfocus = 9\n')
    serving_config.cache_clear()
    body = client.get("/api/league/leagues").json()
    assert body["focus_league_id"] == 9 and body["focus_name"] == "NLT"


def test_a_dead_api_is_a_retriable_422(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _artifacts(tmp_path)

    class Dead(FakeClient):
        def get_entry(self, entry_id):
            raise RuntimeError("connection refused")

    monkeypatch.setattr(mod, "fpl_client", lambda: Dead())
    monkeypatch.setattr(mod, "_OVERVIEW", {})
    serving_config.cache_clear()
    resp = TestClient(create_app()).get("/api/league/leagues")
    assert resp.status_code == 422
    assert "retry" in resp.json()["detail"]
