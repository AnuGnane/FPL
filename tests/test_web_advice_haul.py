"""Two quantities, one name, one page — and which one is which.

``assemble.p_haul`` is P(2 or more attacking returns) under a Poisson on
expected goals plus assists. ``uncertainty.Band.p_haul`` is P(total points
>= 10) in the tail of a normal on the whole forecast. They answer different
questions on different scales, and both were served as ``p_haul``.

The internal names do not move: the attacking one lives inside ``advise.py``
and ``optimize/differentials.py``, both protected, and a rename there would
cost an authorization to buy a label. So the split is resolved where the
payload leaves the process — a third serve-time decoration beside
``with_positions`` and ``with_identity``, which exist for exactly this reason
(v9a plan A2). The artifact on disk keeps ``p_haul``, so ``digest.py`` and
the since-last-run diff go on reading what they always read.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app
from gaffer.web.routers.advice import with_attacking_haul

PAST = "2026-08-01T17:30:00Z"
FUTURE = "2099-09-18T17:30:00Z"
GW = 3

ADVICE = {
    "gw": GW, "deadline": PAST,
    "buys": [{"code": 100, "name": "Salah", "ep": 6.4, "tag": "cover"}],
    "sells": [], "hits": 0,
    "xi": [{"code": 100, "name": "Salah", "ep": 6.4}],
    "bench": [], "captain": {"code": 100, "name": "Salah", "ep": 6.4},
    "vice": None,
    "captain_options": [{"code": 100, "name": "Salah", "ep": 6.4,
                         "p_haul": 0.55}],
    "chip_table": [], "wildcard_now": None,
    "alternatives": [{"code": 11, "name": "Saka", "ep": 8.0, "p_haul": 0.4,
                      "league_eo": 80.0}],
    "threats": [], "price_alerts": [], "expected_pts": 61.5, "plan_by_gw": [],
    "strategy": {}, "win_probs": [], "mode": "weekly",
}


def _write(root, advice=None):
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / f"gw{GW}-advice.json").write_text(
        json.dumps(advice if advice is not None else ADVICE))
    pool = pool_rows(
        pd.DataFrame([{"code": 100, "position": "MID", "team_code": 300,
                       "cost": 130, "sell": 128}]),
        pd.DataFrame([{"code": 100, "name": "Salah"}]),
        owned_codes=[100], ep_by={(100, GW): 6.4}, gws=[GW])
    save_solve_state(SolveState(
        gw=GW, gws=[GW], deadline=PAST,
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=12,
        free_transfers=2, owned_codes=[100], lam=0.25, league_eo={100: 62.5},
        avail_by_gw={GW: ["wildcard"]},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4, "horizon": 1},
        pool=pool))
    events = pd.DataFrame([{"gw": GW, "deadline_time": PAST,
                            "is_current": False, "is_next": True,
                            "finished": False, "data_checked": False}])
    (root / "data" / "live").mkdir(parents=True, exist_ok=True)
    events.to_parquet(root / "data" / "live" / "events.parquet", index=False)
    return root / "reports" / f"gw{GW}-advice.json"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(tmp_path)
    return TestClient(create_app())


# --- the attacking quantity, renamed --------------------------------

def test_the_alternatives_arrive_renamed(client):
    body = client.get("/api/advice/latest").json()["advice"]
    assert body["alternatives"][0]["p_attacking_haul"] == 0.4
    assert "p_haul" not in body["alternatives"][0]


def test_the_captain_options_arrive_renamed_too(client):
    body = client.get("/api/advice/latest").json()["advice"]
    assert body["captain_options"][0]["p_attacking_haul"] == 0.55
    assert "p_haul" not in body["captain_options"][0]


def test_every_other_field_on_an_alternative_row_is_untouched(client):
    body = client.get("/api/advice/latest").json()["advice"]
    row = body["alternatives"][0]
    assert row["code"] == 11 and row["name"] == "Saka" and row["ep"] == 8.0
    assert row["league_eo"] == 80.0


def test_the_artifact_on_disk_still_says_p_haul(tmp_path, monkeypatch):
    """The rename is a decoration on the way out. ``digest.py`` reads this
    file, the since-last-run diff compares it against the previous run, and
    every advice file already banked must go on being readable."""
    monkeypatch.chdir(tmp_path)
    path = _write(tmp_path)
    before = path.read_bytes()
    TestClient(create_app()).get("/api/advice/latest")
    assert path.read_bytes() == before
    assert b"p_attacking_haul" not in before
    assert b"p_haul" in before


# --- the band quantity, which must NOT be renamed -------------------

def test_the_band_field_keeps_its_name_on_the_players_schema():
    """The other direction, and the one that makes the rename mean anything:
    if both fields were renamed the page would be exactly as ambiguous as it
    was, in a new vocabulary. Asserted on the typed schemas, which is where
    the band quantity is actually named — the routers serve these models."""
    from gaffer.web.schemas import ComponentPlayer, PlayerRow

    for model in (PlayerRow, ComponentPlayer):
        assert "p_haul" in model.model_fields
        assert "p_attacking_haul" not in model.model_fields


def test_the_two_definitions_now_cross_reference_each_other():
    """The half of D3 that survives a reader who never opens the router."""
    from gaffer.models.assemble import p_haul as attacking
    from gaffer.uncertainty import Band

    assert "uncertainty" in attacking.__doc__
    assert "p_attacking_haul" in attacking.__doc__
    assert "assemble" in Band.__doc__


# --- the transform itself, defensively ------------------------------

def test_a_payload_with_no_alternatives_at_all_is_a_no_op():
    """``advise.py`` writes an empty frame when there is no buy to find an
    alternative to, and a cold clone has neither key."""
    payload = {"gw": 3, "captain": {"code": 1}}
    assert with_attacking_haul(payload) == payload


def test_a_row_that_never_had_the_field_is_left_alone():
    """Advice files banked before this cycle, and any row where the optimizer
    wrote a partial record. Renaming a key that is not there must not invent
    a null."""
    out = with_attacking_haul({"alternatives": [{"code": 1, "ep": 2.0}]})
    assert out["alternatives"][0] == {"code": 1, "ep": 2.0}
    assert "p_attacking_haul" not in out["alternatives"][0]


def test_a_key_that_is_not_a_list_passes_through(client):
    assert with_attacking_haul({"alternatives": None})["alternatives"] is None
    assert with_attacking_haul({"captain_options": 7})["captain_options"] == 7


def test_a_non_dict_entry_in_the_list_survives():
    out = with_attacking_haul({"alternatives": [None, "x", {"p_haul": 1.0}]})
    assert out["alternatives"][:2] == [None, "x"]
    assert out["alternatives"][2] == {"p_attacking_haul": 1.0}


def test_the_transform_does_not_mutate_the_loaded_payload():
    """``with_positions``' rule, for ``with_positions``' reason: the route is
    handed ``load_advice``'s dict and anything that cached it would inherit
    the rename."""
    payload = {"alternatives": [{"code": 11, "p_haul": 0.4}]}
    with_attacking_haul(payload)
    assert payload["alternatives"][0] == {"code": 11, "p_haul": 0.4}


def test_the_renamed_key_keeps_its_column_position():
    """Order matters to anything reading the payload as a table."""
    out = with_attacking_haul(
        {"alternatives": [{"code": 1, "p_haul": 0.4, "ep": 2.0}]})
    assert list(out["alternatives"][0]) == ["code", "p_attacking_haul", "ep"]
