"""A real (tiny) MILP re-solve against a hand-built solve state."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gaffer.artifacts import SolveState, pool_rows, save_solve_state
from gaffer.web.app import create_app

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool_frame(star_ep=9.0):
    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": 50, "sell": 50})
            code += 1
    return pd.DataFrame(rows), star_ep


def _save_state(gws=(1, 2), star_ep=9.0, lam=0.0, league_eo=None,
                chips=("wildcard", "bboost"), cover=None):
    frame, star_ep = _pool_frame(star_ep)
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    ep_by = {(int(c), g): (star_ep if c == 20 else 2.0)
             for c in frame["code"] for g in gws}
    save_solve_state(SolveState(
        gw=gws[0], gws=list(gws), deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=lam,
        league_eo=league_eo or {},
        avail_by_gw={g: list(chips) for g in gws},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": len(gws)},
        pool=pool_rows(frame, players, OWNED, ep_by, list(gws)),
        cover=cover))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_state()
    return TestClient(create_app())


def _run(client, body):
    resp = client.post("/api/whatif", json=body)
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    for _ in range(2000):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
    raise AssertionError("job never finished")


def test_banning_the_star_costs_expected_points(client):
    job = _run(client, {"ban": [20]})
    assert job["status"] == "done", job["error"]
    result = job["result"]
    assert 20 not in [p["code"] for p in result["yours"]["xi"]]
    assert 20 in [p["code"] for p in result["baseline"]["buys"]]
    assert result["delta_xpts"] < 0
    assert "expected points" in result["verdict"]


def test_locking_a_player_keeps_him_in_the_squad(client):
    job = _run(client, {"lock": [1]})
    assert job["status"] == "done", job["error"]
    codes = ([p["code"] for p in job["result"]["yours"]["xi"]]
             + [p["code"] for p in job["result"]["yours"]["bench"]])
    assert 1 in codes


def test_lock_and_ban_of_the_same_player_is_a_structured_422(client):
    resp = client.post("/api/whatif", json={"lock": [5], "ban": [5]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["constraint"] == "lock_and_ban"
    assert detail["players"] == [5]


def test_unknown_player_is_a_structured_422(client):
    resp = client.post("/api/whatif", json={"lock": [4242]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["constraint"] == "unknown_player"
    assert detail["players"] == [4242]


def test_unavailable_chip_is_rejected_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_state()
    # avail_by_gw carries wildcard and bboost only; triple captain is spent.
    resp = TestClient(create_app()).post("/api/whatif", json={"chip": "tc"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["constraint"] == "chip_unavailable"
    assert "3xc" in detail["error"]


def test_impossible_constraints_land_in_the_job_record_not_a_crash(client):
    # Six locked forwards cannot fit a squad that holds exactly three.
    job = _run(client, {"lock": [16, 17, 18, 19, 20]})
    if job["status"] == "error":
        assert "constraint" in job["error"] or "Infeasible" in job["error"]
    else:                                     # five FWDs is already illegal
        assert job["status"] == "error"


def test_horizon_override_shortens_the_plan(client):
    job = _run(client, {"horizon": 1})
    assert job["status"] == "done", job["error"]
    assert job["result"]["yours"]["gw"] == 1


def test_an_available_chip_is_solved(client):
    job = _run(client, {"chip": "wc", "max_hits": 0})
    assert job["status"] == "done", job["error"]
    # A wildcard makes transfers free, so the cap must not have blocked it.
    assert job["result"]["yours"]["hits"] == 0
    assert 20 in [p["code"] for p in job["result"]["yours"]["xi"]]


def test_free_hit_honours_force_in(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _save_state(chips=("freehit",))
    client = TestClient(create_app())
    job = _run(client, {"chip": "fh", "force_in": [19]})
    assert job["status"] == "done", job["error"]
    codes = ([p["code"] for p in job["result"]["yours"]["xi"]]
             + [p["code"] for p in job["result"]["yours"]["bench"]])
    assert 19 in codes


def test_forcing_in_a_player_you_already_own_is_a_structured_422(client):
    resp = client.post("/api/whatif", json={"force_in": [1]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["constraint"] == "force_in_owned"
    assert detail["players"] == [1]
    assert "lock" in detail["error"]


def test_displayed_points_are_raw_not_tilted(tmp_path, monkeypatch):
    """The tilt shapes the pool only; every number shown is untilted."""
    monkeypatch.chdir(tmp_path)
    _save_state(lam=0.5, league_eo={20: 0.0})
    client = TestClient(create_app())
    job = _run(client, {})
    assert job["status"] == "done", job["error"]
    star = [p for p in job["result"]["yours"]["xi"] if p["code"] == 20]
    assert star and star[0]["ep"] == 9.0     # not 9.0 * 1.5


# --- B1: the re-solve tilts on a cover *fraction*, never on an EO percent --


def _recorded_cover(tmp_path, monkeypatch, **state_kw) -> dict:
    """Run one solve_whatif and hand back the cover table tilt_ep was given."""
    from gaffer.web.routers import whatif as whatif_mod
    from gaffer.web.schemas import WhatIfRequest

    monkeypatch.chdir(tmp_path)
    _save_state(**state_kw)
    seen: list[dict] = []
    real = whatif_mod.tilt_ep

    def spy(ep_by, cover, lam):
        seen.append(dict(cover))
        return real(ep_by, cover, lam)

    monkeypatch.setattr(whatif_mod, "tilt_ep", spy)
    whatif_mod.solve_whatif(WhatIfRequest(), 1)
    assert len(seen) == 1
    return seen[0]


def test_an_old_state_tilts_on_the_eo_converted_to_a_fraction(tmp_path,
                                                              monkeypatch):
    """A state written before ``cover`` existed still has league_eo, which is
    a *percent*. Feeding 90.0 straight into a formula expecting [0, 1] clamps
    every non-trivial EO to 1.0 and silently kills the tilt."""
    cover = _recorded_cover(tmp_path, monkeypatch, lam=0.5,
                            league_eo={20: 90.0})
    assert cover == pytest.approx({20: 0.9})


def test_the_saved_cover_table_is_what_the_re_solve_tilts_on(tmp_path,
                                                             monkeypatch):
    """advise tilts on the threat-weighted cover table, not on league EO; a
    re-solve that used EO instead would optimise a different board."""
    cover = _recorded_cover(tmp_path, monkeypatch, lam=0.5,
                            league_eo={20: 90.0}, cover={20: 0.25})
    assert cover == pytest.approx({20: 0.25})


def test_a_state_saved_without_cover_still_loads(tmp_path, monkeypatch):
    """Forward compatibility: the field defaults to None on an old artifact."""
    import json

    from gaffer.artifacts import load_solve_state, solve_state_paths

    monkeypatch.chdir(tmp_path)
    _save_state(lam=0.5, league_eo={20: 90.0})
    _, meta = solve_state_paths(1)
    raw = json.loads(meta.read_text())
    raw.pop("cover", None)
    meta.write_text(json.dumps(raw))
    assert load_solve_state(1).cover is None


# --- B7: the web re-solve must price like the advice that saved the state --


def _state_with(opt_extra):
    frame, star_ep = _pool_frame()
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    gws = (1, 2)
    ep_by = {(int(c), g): (star_ep if c == 20 else 2.0)
             for c in frame["code"] for g in gws}
    return SolveState(
        gw=1, gws=list(gws), deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={g: [] for g in gws},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": 2, **opt_extra},
        pool=pool_rows(frame, players, OWNED, ep_by, list(gws)))


def test_a_state_saved_before_v4c_still_re_solves():
    """Old states carry only the original six keys and no priors flag."""
    from gaffer.artifacts import solve_kw_from_state

    kw = solve_kw_from_state(_state_with({}))
    assert set(kw) == {"decay", "bench_weight", "vice_weight", "ft_value",
                       "itb_value", "hit_cost"}


def test_the_objective_craft_knobs_ride_on_the_saved_state():
    from gaffer.artifacts import solve_kw_from_state

    kw = solve_kw_from_state(_state_with(
        {"ft_use_penalty": 0.3, "bench_curve": [0.21, 0.06, 0.002]}))
    assert kw["ft_use_penalty"] == 0.3
    assert kw["bench_curve"] == [0.21, 0.06, 0.002]
    assert "ft_lambda" not in kw


def test_the_priors_flag_rebuilds_the_lambda_lookup_from_the_asset():
    """The flag is the whole point: without it the What-If baseline prices
    banked transfers at zero while the advice priced them off the asset."""
    from gaffer.artifacts import solve_kw_from_state

    kw = solve_kw_from_state(_state_with({"decision_priors": True}))
    assert "ft_lambda" in kw
    assert not kw["ft_lambda"].empty


def test_both_re_solving_routers_use_the_shared_bundle():
    import inspect

    from gaffer.web.routers import meta, whatif

    assert "solve_kw_from_state(state)" in inspect.getsource(
        whatif.solve_whatif)
    assert "solve_kw_from_state(state)" in inspect.getsource(meta.chips_plan)
