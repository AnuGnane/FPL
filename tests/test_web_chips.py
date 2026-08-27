"""GET /api/chips — the workbench's read model."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import POOL_COLS, SolveState, save_solve_state
from gaffer.web.app import create_app

ADVICE = {
    "gw": 5,
    "deadline": "2026-09-05T10:00:00Z",
    "expected_pts": 61.5,
    "chip_table": [
        {"chip": "wildcard", "gw": 5, "gain": 9.4, "per_week": 3.1,
         "threshold": 8.0, "play_now": True},
        {"chip": "bboost", "gw": 6, "gain": 2.0, "per_week": 2.0,
         "threshold": 4.0, "play_now": False},
        {"chip": "freehit", "gw": 7, "gain": 5.0, "per_week": 5.0,
         "threshold": 4.0, "play_now": True, "note": "conservative lower "
                                                     "bound"},
    ],
    "wildcard_now": {"gain_over_horizon": 9.4, "wc_squad": [100, 102],
                     "recommend": True},
}


def _pool() -> pd.DataFrame:
    rows = [
        {"code": 100, "name": "Salah", "position": "MID", "team_code": 14,
         "cost": 130, "sell": 130, "owned": True, "gw": 5, "ep_raw": 6.4},
        {"code": 101, "name": "Watkins", "position": "FWD", "team_code": 7,
         "cost": 90, "sell": 90, "owned": True, "gw": 5, "ep_raw": 4.1},
        {"code": 102, "name": "Wirtz", "position": "MID", "team_code": 14,
         "cost": 85, "sell": 85, "owned": False, "gw": 5, "ep_raw": 5.2},
    ]
    return pd.DataFrame(rows, columns=POOL_COLS)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app(), raise_server_exceptions=False)


def _write(tmp_path, advice=None, owned=(100, 101)):
    (tmp_path / "reports").mkdir(exist_ok=True)
    save_solve_state(SolveState(
        gw=5, gws=[5, 6, 7], deadline="2026-09-05T10:00:00Z",
        generated_at="2026-09-04T09:00:00+00:00", mode="weekly", bank=5,
        free_transfers=1, owned_codes=list(owned), lam=0.0, league_eo={},
        avail_by_gw={5: ["wildcard"], 6: [], 7: []},
        opt={"decay": 0.9, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.0, "itb_value": 0.1, "hit_cost": 4,
             "horizon": 3},
        pool=_pool()))
    (tmp_path / "reports" / "gw5-advice.json").write_text(
        json.dumps(advice if advice is not None else ADVICE))


def test_chips_without_an_advice_run_is_a_friendly_404(client):
    response = client.get("/api/chips")
    assert response.status_code == 404
    assert "gaffer advise" in response.json()["detail"]


def test_chips_returns_the_table_with_its_thresholds(client, tmp_path):
    _write(tmp_path)
    body = client.get("/api/chips").json()
    assert body["gw"] == 5
    rows = {(r["chip"], r["gw"]): r for r in body["chips"]}
    assert rows[("wildcard", 5)]["gain"] == 9.4
    assert rows[("wildcard", 5)]["threshold"] == 8.0
    assert rows[("wildcard", 5)]["play_now"] is True
    assert rows[("bboost", 6)]["play_now"] is False
    assert rows[("freehit", 7)]["note"] == "conservative lower bound"


def test_chips_resolves_the_wildcard_squad_into_a_three_way_diff(client,
                                                                 tmp_path):
    """Kept / out / in, computed server-side: the page renders columns, it
    does not do set arithmetic over codes."""
    _write(tmp_path)
    wildcard = client.get("/api/chips").json()["wildcard"]
    assert wildcard["recommend"] is True
    assert wildcard["gain_over_horizon"] == 9.4
    assert [p["name"] for p in wildcard["kept"]] == ["Salah"]
    assert [p["name"] for p in wildcard["dropped"]] == ["Watkins"]
    assert [p["name"] for p in wildcard["added"]] == ["Wirtz"]
    added = wildcard["added"][0]
    assert added["price"] == 8.5 and added["ep"] == 5.2
    assert added["position"] == "MID"


def test_chips_without_a_wildcard_assessment_is_a_null_not_an_error(client,
                                                                    tmp_path):
    """GW1, or a half where the wildcard is already spent."""
    advice = dict(ADVICE, wildcard_now=None)
    _write(tmp_path, advice)
    body = client.get("/api/chips").json()
    assert body["wildcard"] is None
    assert len(body["chips"]) == 3


def test_chips_tolerates_a_squad_code_the_pool_no_longer_knows(client,
                                                               tmp_path):
    """A saved state and an advice file can disagree after a partial re-run.
    An unknown code is shown by its number rather than 500ing the page."""
    advice = dict(ADVICE, wildcard_now={"gain_over_horizon": 1.0,
                                        "wc_squad": [100, 999],
                                        "recommend": False})
    _write(tmp_path, advice)
    added = client.get("/api/chips").json()["wildcard"]["added"]
    assert [p["code"] for p in added] == [999]
    assert added[0]["name"] == "999" and added[0]["price"] == 0.0


def test_chips_with_an_empty_table_is_an_empty_list(client, tmp_path):
    _write(tmp_path, dict(ADVICE, chip_table=[], wildcard_now=None))
    body = client.get("/api/chips").json()
    assert body["chips"] == [] and body["wildcard"] is None
