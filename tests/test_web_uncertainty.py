"""Bands on the two payloads that already carry an expected-points number.

Additive, in the strict sense: every field these endpoints served before must
come back byte-identical, and the new ones must be *absent* rather than zero
whenever their input is. The second half of that is the part worth testing —
a band of 0.0-0.0 on a player the minutes model has never seen is a stronger
and more wrong claim than no band at all.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, save_components, save_solve_state
from gaffer.web.app import create_app

GW = 5

COMPONENTS = pd.DataFrame([
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW, "opp_code": 4,
     "opp_name": "City", "was_home": 1.0, "kickoff_time": "2026-09-01T14:00",
     "p_play": 0.95, "p60": 0.9, "ep": 5.0, "ep_goals": 2.0,
     "ep_assists": 1.0, "ep_minutes": 2.0},
    {"code": 11, "element": 1, "name": "Saka", "position": "MID",
     "team_code": 3, "team_name": "Arsenal", "gw": GW + 1, "opp_code": 5,
     "opp_name": "Spurs", "was_home": 0.0, "kickoff_time": "2026-09-08T14:00",
     "p_play": 0.95, "p60": 0.9, "ep": 4.0, "ep_goals": 1.5,
     "ep_assists": 0.5, "ep_minutes": 2.0},
    {"code": 22, "element": 2, "name": "Sub", "position": "FWD",
     "team_code": 4, "team_name": "City", "gw": GW, "opp_code": 3,
     "opp_name": "Arsenal", "was_home": 0.0,
     "kickoff_time": "2026-09-01T14:00", "p_play": 0.25, "p60": 0.1,
     "ep": 1.2, "ep_goals": 0.8, "ep_minutes": 0.4},
])

PLAYERS = pd.DataFrame({
    "code": [11, 22], "element": [1, 2], "name": ["Saka", "Sub"],
    "position": ["MID", "FWD"], "team_id": [1, 2], "team_code": [3, 4],
    "now_cost": [100, 60], "status": ["a", "a"], "news": ["", ""],
    "chance_of_playing": [None, None], "selected_by_percent": [40.0, 2.0],
    "form": [5.0, 1.0], "points_per_game": [5.0, 1.0],
    "ep_next": [5.0, 1.2], "price_change_percent": [0.0, 0.0],
    "price_change_calibrating": [False, False],
    "penalties_order": [1.0, None], "direct_freekicks_order": [None, None],
    "corners_and_indirect_freekicks_order": [1.0, None]})

TEAMS = pd.DataFrame({"code": [3, 4], "id": [1, 2],
                      "name": ["Arsenal", "City"],
                      "short_name": ["ARS", "MCI"]})

POOL = pd.DataFrame([
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW, "ep_raw": 5.0},
    {"code": 11, "name": "Saka", "position": "MID", "team_code": 3,
     "cost": 100, "sell": 100, "owned": True, "gw": GW + 1, "ep_raw": 4.0},
    {"code": 22, "name": "Sub", "position": "FWD", "team_code": 4,
     "cost": 60, "sell": 60, "owned": False, "gw": GW, "ep_raw": 1.2},
])


def _state() -> SolveState:
    return SolveState(
        gw=GW, gws=[GW, GW + 1], deadline="2026-09-01T11:00:00Z",
        generated_at="2026-08-31T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=[11], lam=0.0, league_eo={},
        avail_by_gw={GW: [], GW + 1: []},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "horizon": 2, "hit_cost": 4,
             "max_transfers": 2, "bank_weight": 0.0},
        pool=POOL)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "live").mkdir(parents=True)
    PLAYERS.to_parquet(tmp_path / "data/live/players.parquet", index=False)
    TEAMS.to_parquet(tmp_path / "data/live/teams.parquet", index=False)
    (tmp_path / "reports").mkdir()
    save_components(COMPONENTS, GW)
    save_solve_state(_state())
    return TestClient(create_app())


def _player(body: dict, code: int) -> dict:
    return next(p for p in body["players"] if p["code"] == code)


# --- /api/components/{gw} ---------------------------------------------

def test_the_band_brackets_the_gameweeks_own_ep_not_the_horizon(client):
    """A2: ``ep`` is a horizon sum, so the band is drawn round ``ep_gw``."""
    body = client.get(f"/api/components/{GW}").json()
    saka = _player(body, 11)
    assert saka["ep"] == pytest.approx(9.0)      # 5.0 + 4.0, unchanged
    assert saka["ep_gw"] == pytest.approx(5.0)
    assert saka["ep_lo"] < saka["ep_gw"] < saka["ep_hi"]


def test_a_rotation_risk_carries_a_wider_band_than_a_starter(client,
                                                             monkeypatch):
    """Pinned to the heuristic arm, because that is the arm where the claim
    is true. The calibrated σ is *absolute*, so a 1.2-EP sub genuinely has a
    smaller residual than a 5.0-EP starter and the shipped table says so — a
    fact, not a bug. The relative-width claim belongs to the multiplicative
    scale, so the test pins it there through the module's one asset seam."""
    monkeypatch.setattr("gaffer.uncertainty.scenario_noise", lambda: None)
    body = client.get(f"/api/components/{GW}").json()
    starter, sub = _player(body, 11), _player(body, 22)
    starter_width = starter["ep_hi"] - starter["ep_lo"]
    sub_width = sub["ep_hi"] - sub["ep_lo"]
    # Per point of EP: the sub's EP is smaller, so compare the relative width.
    assert sub_width / sub["ep_gw"] > starter_width / starter["ep_gw"]


def test_the_tails_come_back_as_probabilities(client):
    saka = _player(client.get(f"/api/components/{GW}").json(), 11)
    assert 0.0 <= saka["p_haul"] <= 1.0
    assert 0.0 <= saka["p_blank"] <= 1.0
    assert saka["sigma"] > 0.0


def test_a_frame_with_no_minutes_model_serves_no_bands(client, tmp_path):
    """A3 end to end: nulls, not zeros, and the rest of the payload intact."""
    save_components(COMPONENTS.drop(columns=["p_play", "p60"]), GW)
    saka = _player(client.get(f"/api/components/{GW}").json(), 11)
    assert saka["ep"] == pytest.approx(9.0)
    assert saka["ep_lo"] is None and saka["ep_hi"] is None
    assert saka["p_haul"] is None and saka["p_blank"] is None
    assert saka["sigma"] is None
    # ``ep_gw`` is arithmetic on the frame, not on the noise model, so it
    # survives a frame that carries no minutes at all.
    assert saka["ep_gw"] == pytest.approx(5.0)


def test_the_code_filter_still_narrows_the_payload(client):
    body = client.get(f"/api/components/{GW}?codes=22").json()
    assert [p["code"] for p in body["players"]] == [22]
    assert body["players"][0]["ep_lo"] is not None


# --- /api/players ------------------------------------------------------

def test_the_explorer_bands_the_number_it_shows(client):
    """A4: the band brackets ``ep_next``, which comes from the pool, not from
    the components frame."""
    from gaffer.uncertainty import band_for, xmins_by_player_gw

    rows = client.get("/api/players").json()
    saka = next(r for r in rows if r["code"] == 11)
    want = band_for(saka["ep_next"],
                    xmins_by_player_gw(COMPONENTS)[(11, GW)])
    assert saka["ep_lo"] == pytest.approx(want.ep_lo)
    assert saka["ep_hi"] == pytest.approx(want.ep_hi)
    assert saka["p_haul"] == pytest.approx(want.p_haul)
    assert saka["p_blank"] == pytest.approx(want.p_blank)


def test_a_clone_with_no_components_still_lists_players(client, tmp_path):
    """The explorer has to render on a clone that has only ever solved."""
    (tmp_path / f"reports/components_gw{GW}.parquet").unlink()
    rows = client.get("/api/players").json()
    saka = next(r for r in rows if r["code"] == 11)
    assert saka["ep_next"] == pytest.approx(5.0)
    assert saka["ep_lo"] is None and saka["p_haul"] is None


def test_an_unreadable_components_file_is_a_missing_band_not_a_500(
        client, tmp_path):
    (tmp_path / f"reports/components_gw{GW}.parquet").write_text("garbage")
    response = client.get("/api/players")
    assert response.status_code == 200
    assert all(r["ep_lo"] is None for r in response.json())
