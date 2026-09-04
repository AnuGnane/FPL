"""v13 §3 — the transfer ladder's arithmetic, on a hand-built saved state."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from gaffer.artifacts import SolveState, pool_rows, save_solve_state

OWNED = [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 16, 17, 18]


def _pool_frame():
    rows, code = [], 1
    for pos, n in [("GKP", 2), ("DEF", 6), ("MID", 7), ("FWD", 5)]:
        for _ in range(n):
            rows.append({"code": code, "position": pos,
                         "team_code": code % 8, "cost": 50, "sell": 50})
            code += 1
    return pd.DataFrame(rows)


def save_state(opt_extra=None, star=9.0, second=7.0, gws=(1, 2)):
    """Code 20 is worth a free transfer, code 19 is worth a hit (5 EP/GW over
    two weeks against a 4-point hit), nothing else moves."""
    frame = _pool_frame()
    players = pd.DataFrame({"code": frame["code"],
                            "name": [f"P{c}" for c in frame["code"]]})
    ep = {20: star, 19: second}
    ep_by = {(int(c), g): ep.get(int(c), 2.0)
             for c in frame["code"] for g in gws}
    save_solve_state(SolveState(
        gw=gws[0], gws=list(gws), deadline="2026-09-11T17:30:00Z",
        generated_at="2026-09-10T09:00:00Z", mode="weekly", bank=0,
        free_transfers=1, owned_codes=list(OWNED), lam=0.0, league_eo={},
        avail_by_gw={g: [] for g in gws},
        opt={"decay": 0.85, "bench_weight": 0.1, "vice_weight": 0.1,
             "ft_value": 1.5, "itb_value": 0.05, "hit_cost": 4,
             "horizon": len(gws), **(opt_extra or {})},
        pool=pool_rows(frame, players, OWNED, ep_by, list(gws))))
    return ep_by


@pytest.fixture()
def board(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return save_state({"max_hits": 2, "max_transfers": 15})


def _zero_noise(monkeypatch):
    from gaffer import ladder

    monkeypatch.setattr(ladder, "OUTCOME_VAR_PER_EP", 0.0)
    monkeypatch.setattr(ladder, "sigma_table", lambda gw: ({}, "outcome_only"))


def test_with_no_noise_every_probability_is_zero_or_one_and_mean_is_horizon(
        board, monkeypatch):
    from gaffer.ladder import build_ladder

    _zero_noise(monkeypatch)
    out = build_ladder(1, n_draws=25, seed=1)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert len(distinct) >= 2
    for r in distinct:
        assert r["mean_pts"] == pytest.approx(r["horizon_pts"], abs=0.01)
        assert r["p10_pts"] == pytest.approx(r["mean_pts"], abs=0.01)
        for key in ("p_beats_bank", "p_beats_top"):
            assert r[key] in (None, 0.0, 1.0)
    assert out["sigma_source"] == "outcome_only"


def test_the_rungs_come_in_ladder_order_and_coincident_ones_say_so(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=25, seed=1)
    keys = [r["key"] for r in out["rungs"]]
    assert keys[:5] == ["bank", "hits0", "hits1", "hits2", "hits3"]
    by = {r["key"]: r for r in out["rungs"]}
    assert by["bank"]["transfers"] == 0 and by["bank"]["p_beats_bank"] is None
    assert [b["code"] for b in by["hits0"]["plan_by_gw"][0]["buys"]] == [20]
    assert sorted(b["code"] for b in by["hits1"]["plan_by_gw"][0]["buys"]) \
        == [19, 20]
    assert by["hits1"]["hits"] == 1 and by["hits1"]["cost"] == 4
    # Nothing is worth a second hit, so the two upper rungs collapse onto
    # hits1 and carry no numbers of their own.
    assert by["hits2"]["same_as"] == "hits1"
    assert by["hits3"]["same_as"] == "hits1"
    assert by["hits3"]["mean_pts"] is None and by["hits3"]["plan_by_gw"] == []
    assert "open" not in keys


def test_p_best_sums_to_one_over_the_distinct_rungs(board):
    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=40, seed=3)
    distinct = [r for r in out["rungs"] if r["same_as"] is None]
    assert sum(r["p_best"] for r in distinct) == pytest.approx(1.0, abs=1e-6)
    for r in distinct:
        for key in ("p_beats_bank", "p_beats_top", "p_best"):
            assert r[key] is None or 0.0 <= r[key] <= 1.0


def test_the_cap_rung_and_the_recommended_rung(board, monkeypatch):
    """cap_rung follows the saved caps; recommended matches the served
    advice's first-week buys, sells and captain when an advice is on disk."""
    import json
    from pathlib import Path

    from gaffer.ladder import build_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": 2, "max_transfers": None}
    assert out["cap_rung"] == "hits2"
    assert out["recommended"] is None          # no gw1-advice.json yet

    hits1 = next(r for r in out["rungs"] if r["key"] == "hits1")
    first = hits1["plan_by_gw"][0]
    Path("reports").mkdir(exist_ok=True)
    Path("reports/gw1-advice.json").write_text(json.dumps({
        "buys": [{"code": b["code"]} for b in first["buys"]],
        "sells": [{"code": s["code"]} for s in first["sells"]],
        "captain": {"code": first["captain"]["code"]}}))
    assert build_ladder(1, n_draws=10, seed=1)["recommended"] == "hits1"


def test_a_bank_cap_and_an_uncapped_state_pick_their_rungs(tmp_path,
                                                            monkeypatch):
    from gaffer.ladder import build_ladder

    monkeypatch.chdir(tmp_path)
    save_state({"max_hits": 15, "max_transfers": 0})
    assert build_ladder(1, n_draws=10, seed=1)["cap_rung"] == "bank"
    save_state({})
    out = build_ladder(1, n_draws=10, seed=1)
    assert out["cap"] == {"max_hits": None, "max_transfers": None}
    assert out["cap_rung"] == out["rungs"][-1]["key"]


def test_the_seed_reproduces_the_payload(board):
    from gaffer.ladder import build_ladder

    a = build_ladder(1, n_draws=30, seed=11)
    b = build_ladder(1, n_draws=30, seed=11)
    for payload in (a, b):
        payload.pop("generated_at"), payload.pop("wall_s")
    assert a == b


def test_the_payload_is_banked_and_reloads(board):
    from gaffer.ladder import build_ladder, ladder_path, load_ladder

    out = build_ladder(1, n_draws=10, seed=1)
    assert ladder_path(1).exists()
    assert load_ladder(1)["rungs"][0]["key"] == out["rungs"][0]["key"]
    assert load_ladder(7) is None


def test_score_plan_uses_one_shared_draw_per_player_week():
    from gaffer.ladder import score_plan

    draws = {(1, 1): np.array([3.0, 5.0]), (2, 1): np.array([1.0, 2.0])}
    plan = SimpleNamespace(gw=1, xi=[1, 2], captain=1, hits=1)
    a = score_plan([plan], draws, hit_cost=4, n_draws=2)
    b = score_plan([plan], draws, hit_cost=4, n_draws=2)
    # XI 4/7, captain again 3/5, minus one hit: 3 and 8, identically twice.
    assert a.tolist() == [3.0, 8.0] and b.tolist() == a.tolist()


def test_p_best_splits_ties():
    from gaffer.ladder import p_best

    shares = p_best({"a": np.array([1.0, 2.0]), "b": np.array([1.0, 1.0])})
    assert shares == {"a": 0.75, "b": 0.25}


def test_vs_below_is_set_arithmetic_on_the_first_week():
    from gaffer.ladder import vs_below

    meta = {19: {"name": "P19", "position": "FWD"},
            20: {"name": "P20", "position": "FWD"},
            16: {"name": "P16", "position": "FWD"},
            17: {"name": "P17", "position": "FWD"}}
    ep_by = {(19, 1): 7.0, (20, 1): 9.0, (16, 1): 2.0, (17, 1): 2.0}
    below = SimpleNamespace(gw=1, buys=[20], sells=[16], hits=0)
    rung = SimpleNamespace(gw=1, buys=[19, 20], sells=[16, 17], hits=1)
    out = vs_below(below, rung, prev_mean=100.0, mean=103.5, hit_cost=4,
                   meta=meta, ep_by=ep_by)
    assert [p["code"] for p in out["extra_buys"]] == [19]
    assert [p["code"] for p in out["extra_sells"]] == [17]
    assert out["dropped_buys"] == [] and out["dropped_sells"] == []
    assert out["delta_mean_pts"] == 3.5 and out["delta_cost"] == 4
