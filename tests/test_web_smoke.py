"""One app, every read-only endpoint, against a complete fixture directory.

This is the test that catches a router that imports cleanly but blows up on
the first request — the failure mode the per-router tests cannot see, because
each of them writes only the artifacts its own endpoint reads, and several of
them stub out the expensive parts (``/api/chips/plan``'s real chip solves,
for one) that only a whole-app pass exercises.

The fixture is therefore a *legal* saved state rather than a minimal one: a
full 15-man squad over six clubs plus three alternatives, so the chip planner
has something the MILP can actually solve. The fake client answers as though
GW3 were in play, so the live paths in ``/api/live`` and
``/api/league/rivals/{id}`` run rather than short-circuiting on "no gameweek
in progress".
"""

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import (COMPONENT_COLS, SolveState, pool_rows,
                              save_components, save_solve_state)
from gaffer.web.app import create_app

TEAMS = pd.DataFrame([
    {"team_id": 1, "code": 300, "name": "Liverpool", "short_name": "LIV"},
    {"team_id": 2, "code": 301, "name": "Arsenal", "short_name": "ARS"},
    {"team_id": 3, "code": 302, "name": "Chelsea", "short_name": "CHE"},
    {"team_id": 4, "code": 303, "name": "Everton", "short_name": "EVE"},
    {"team_id": 5, "code": 304, "name": "Fulham", "short_name": "FUL"},
    {"team_id": 6, "code": 305, "name": "Brentford", "short_name": "BRE"},
])

# 15 owned (2 GKP / 5 DEF / 5 MID / 3 FWD, at most three per club) plus three
# affordable alternatives — the shape a real solve state has.
POSITIONS = ["MID", "GKP", "GKP", "DEF", "DEF", "DEF", "DEF", "DEF", "MID",
             "MID", "MID", "MID", "FWD", "FWD", "FWD", "DEF", "MID", "FWD"]
CODES = [100 + i for i in range(len(POSITIONS))]
OWNED = CODES[:15]
TEAM_OF = {code: 300 + i % 6 for i, code in enumerate(CODES)}
NAME_OF = {code: ("Salah" if code == 100 else f"Player {code}")
           for code in CODES}
EP_OF = {code: round(6.4 - 0.2 * i, 2) for i, code in enumerate(CODES)}

PLAYERS = pd.DataFrame([{
    "code": code, "element": 7 + i, "name": NAME_OF[code],
    "position": POSITIONS[i], "team_id": TEAM_OF[code] - 299,
    "team_code": TEAM_OF[code], "now_cost": 45, "status": "a", "news": "",
    "chance_of_playing": None, "selected_by_percent": 45.0 - i,
    "form": 5.0, "points_per_game": 6.0, "ep_next": EP_OF[code],
    "price_change_percent": 0.0, "price_change_calibrating": False,
    "penalties_order": 1.0 if code == 100 else None,
    "direct_freekicks_order": None,
    "corners_and_indirect_freekicks_order": None}
    for i, code in enumerate(CODES)])

ELEMENT_OF = dict(zip(PLAYERS["code"], PLAYERS["element"]))

STANDINGS = [
    {"entry": 1, "entry_name": "You FC", "player_name": "Me",
     "rank": 1, "last_rank": 1, "total": 106, "event_total": 55},
    {"entry": 2, "entry_name": "Rival FC", "player_name": "Them",
     "rank": 2, "last_rank": 2, "total": 98, "event_total": 47},
]


class FakeClient:
    """Every FPL call the read-only endpoints make, answered from memory."""

    def get_event_status(self):
        return {"status": [{"event": 3, "points": "l", "bonus_added": False}],
                "leagues": "Updating"}

    def get_event_live(self, gw):
        return {"elements": [{"id": int(e),
                              "stats": {"total_points": 4, "minutes": 90,
                                        "bps": 20}}
                             for e in PLAYERS["element"]]}

    def get_league_standings(self, league_id, page=1):
        return {"standings": {"has_next": False, "results": STANDINGS}}

    def get_entry_history(self, entry_id):
        return {"current": [{"event": 2, "points": 55, "total_points": 106}],
                "chips": []}

    def get_entry_picks(self, entry_id, gw):
        return {"picks": [{"element": int(ELEMENT_OF[code]),
                           "position": i + 1,
                           "multiplier": 2 if i == 0 else (1 if i < 11 else 0)}
                          for i, code in enumerate(OWNED)],
                "entry_history": {"bank": 5, "value": 1000,
                                  "total_points": 106, "points": 55}}

    def get_fixtures(self):
        return [{"id": 11, "event": 3, "started": True, "finished": False,
                 "team_h": 1, "team_a": 2, "stats": []}]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[fpl]\nentry_id = 1\nleague_id = 5\n')
    live = tmp_path / "data" / "live"
    live.mkdir(parents=True, exist_ok=True)
    PLAYERS.to_parquet(live / "players.parquet", index=False)
    TEAMS.to_parquet(live / "teams.parquet", index=False)
    pd.DataFrame([{"gw": 3, "home_id": home, "away_id": away,
                   "kickoff_time": "2026-09-12T14:00:00Z",
                   "home_goals": None, "away_goals": None, "finished": False}
                  for home, away in ((1, 2), (3, 4), (5, 6))]).to_parquet(
        live / "fixtures_all.parquet", index=False)
    pd.DataFrame([{"code": code, "gw": 2, "total_points": 6, "minutes": 90,
                   "value": 44} for code in OWNED]).to_parquet(
        live / "player_gw.parquet", index=False)
    pd.DataFrame([{"gw": 3, "deadline_time": "2026-09-11T17:30:00Z",
                   "is_current": False, "is_next": True, "finished": False,
                   "data_checked": False}]).to_parquet(
        live / "events.parquet", index=False)
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "gw3-advice.json").write_text(json.dumps({
        "gw": 3, "deadline": "2026-09-11T17:30:00Z", "buys": [], "sells": [],
        "hits": 0,
        "xi": [{"code": c, "name": NAME_OF[c], "ep": EP_OF[c]}
               for c in OWNED[:11]],
        "bench": [{"code": c, "name": NAME_OF[c], "ep": EP_OF[c]}
                  for c in OWNED[11:]],
        "captain": {"code": 100, "name": "Salah", "ep": 6.4},
        "vice": {"code": 101, "name": NAME_OF[101], "ep": EP_OF[101]},
        "captain_options": [], "chip_table": [], "wildcard_now": None,
        "alternatives": [], "threats": [], "price_alerts": [],
        "expected_pts": 61.5, "plan_by_gw": [], "strategy": None,
        "win_probs": [], "mode": "weekly"}))
    save_solve_state(SolveState(
        gw=3, gws=[3], deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=5,
        free_transfers=1, owned_codes=OWNED, lam=0.0,
        league_eo={100: 60.0}, avail_by_gw={3: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool_rows(
            pd.DataFrame([{"code": code, "position": POSITIONS[i],
                           "team_code": TEAM_OF[code], "cost": 45,
                           "sell": 45} for i, code in enumerate(CODES)]),
            PLAYERS, OWNED, {(code, 3): EP_OF[code] for code in CODES}, [3])))
    rows = []
    for i, code in enumerate(CODES):
        row = {c: 0.0 for c in COMPONENT_COLS}
        row.update({"code": code, "element": int(ELEMENT_OF[code]),
                    "name": NAME_OF[code], "position": POSITIONS[i],
                    "team_code": TEAM_OF[code],
                    "team_name": "Liverpool", "gw": 3, "opp_code": 301,
                    "opp_name": "Arsenal", "was_home": True,
                    "kickoff_time": "2026-09-12T14:00:00Z",
                    "ep": EP_OF[code], "ep_minutes": 1.0,
                    "ep_goals": EP_OF[code] - 1.0})
        rows.append(row)
    save_components(pd.DataFrame(rows)[COMPONENT_COLS], 3)
    for module in ("league", "live"):
        monkeypatch.setattr(f"gaffer.web.routers.{module}.fpl_client",
                            lambda: FakeClient())
    return TestClient(create_app())


GETS = [
    "/api/ping",
    "/api/advice/latest",
    "/api/chips/plan",
    "/api/league/race",
    "/api/league/rivals",
    "/api/league/rivals/2",
    "/api/live",
    "/api/players",
    "/api/players/100/explain",
    "/api/history",
    "/api/health",
    "/api/fixtures/ticker?weeks=4",
]


@pytest.mark.parametrize("path", GETS)
def test_every_read_endpoint_answers(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, f"{path}: {resp.text}"
    assert resp.json() is not None


def test_the_fixture_exercises_the_network_paths_not_the_empty_ones(client):
    """Guard against a 200 that only means "nothing to do".

    ``/api/live`` returns an inactive shell between gameweeks and
    ``/api/league/rivals`` an empty list when you are the only entry — both
    are 200s that would let a broken router through unnoticed.
    """
    live = client.get("/api/live").json()
    assert live["active"] is True and live["gw"] == 3
    assert len(live["players"]) == 15 and live["my_points"] > 0
    assert len(client.get("/api/league/rivals").json()) == 1
    assert len(client.get("/api/players").json()) == len(CODES)


def test_job_status_reports_a_submitted_job(client):
    job_id = client.app.state.jobs.submit(lambda: {"rows": 1}, timeout_s=10)
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == job_id


def test_unknown_job_is_a_404_not_a_crash(client):
    resp = client.get("/api/jobs/nope")
    assert resp.status_code == 404
    assert "no such job" in resp.json()["detail"]
